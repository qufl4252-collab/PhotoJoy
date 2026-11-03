import {
  DEFAULT_SETTINGS,
  classify,
  organizedPaths,
  summarize,
  sequentialQueue,
} from "./classification.js";
import { iou } from "./face-math.js";
const uuid = () => crypto.randomUUID();
export const sha256 = async (blob) =>
  Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
    ),
    (n) => n.toString(16).padStart(2, "0"),
  ).join("");
const metaTables = [
  "children",
  "references",
  "media",
  "jobs",
  "settings",
  "exports",
];
export class Project {
  constructor(vault, analyzer, captureDate) {
    this.v = vault;
    this.analyzer = analyzer;
    this.captureDate = captureDate;
    this.running = false;
    this.stopped = false;
    this.change = () => {};
  }
  async init() {
    const schema = await this.v.get("settings", "schema");
    if (schema !== 5) {
      const snapshot = {
        id: uuid(),
        created: Date.now(),
        reason: "v5 상태 마이그레이션 전",
        tables: {},
      };
      for (const table of metaTables)
        snapshot.tables[table] = await this.v.entries(table);
      const entries = [{ table: "backups", id: snapshot.id, value: snapshot }];
      for (const { id, value } of snapshot.tables.media) {
        const m = structuredClone(value);
        m.state =
          m.status === "confirmed"
            ? "organized"
            : m.status === "excluded"
              ? "excluded"
              : "review";
        m.userChecked = !!m.reviewed;
        m.needsReview = m.state === "review";
        m.history = m.history || [];
        m.children = m.children || [];
        m.diagnostics = [];
        m.schema = 5;
        entries.push({ table: "media", id, value: m });
      }
      for (const { id, value: r } of snapshot.tables.references)
        entries.push({
          table: "references",
          id,
          value: {
            ...r,
            id,
            active: r.active !== false,
            origin: r.origin || "기존 사용자 등록",
          },
        });
      entries.push({ table: "settings", id: "schema", value: 5 });
      await this.v.putMany(entries);
    }
    const recover = async () => {
      for (const job of await this.v.all("jobs"))
        if (["analyzing", "classified"].includes(job.state)) {
          job.state = "queued";
          await this.v.put("jobs", job.id, job);
          const m = await this.v.get("media", job.media);
          if (m) {
            m.state = "queued";
            await this.v.put("media", m.id, m);
          }
        }
    };
    // A new tab must not reset another tab's active queue.
    if (globalThis.navigator?.locks)
      await navigator.locks.request(
        `photojoy-queue-${this.v.owner}`,
        { ifAvailable: true },
        async (lock) => {
          if (lock) await recover();
        },
      );
    else await recover();
    return this;
  }
  assertIdle() {
    if (this.running)
      throw new Error("현재 파일 처리를 마치고 일시정지한 뒤 수정해 주세요.");
  }
  async settings() {
    return {
      ...DEFAULT_SETTINGS,
      ...(await this.v.get("settings", "recognition")),
    };
  }
  async kids() {
    return this.v.all("children");
  }
  async refs() {
    return (await this.v.all("references")).filter((r) => r.active !== false);
  }
  async gallery() {
    const result = {};
    for (const r of await this.refs())
      (result[r.child] ??= []).push(r.embedding);
    return result;
  }
  async media() {
    return (await this.v.all("media")).filter((m) => !m.deletedAt);
  }
  async snapshot() {
    const media = await this.media(),
      kids = await this.kids(),
      refs = await this.refs(),
      jobs = await this.v.all("jobs");
    return {
      media,
      kids,
      refs,
      jobs,
      counts: summarize(media),
      jobCounts: summarize(jobs),
      settings: await this.settings(),
      running: this.running,
    };
  }
  async emit() {
    this.v.check();
    await this.change();
  }
  async saveSettings(values) {
    this.assertIdle();
    await this.v.put("settings", "recognition", {
      ...(await this.settings()),
      ...values,
    });
    await this.reorganize();
  }
  async addChild(name, group = "", id = uuid()) {
    this.assertIdle();
    if (!name.trim()) throw new Error("아이 이름을 입력해 주세요.");
    await this.v.put("children", id, {
      id,
      name: name.trim().slice(0, 80),
      group_name: group.trim().slice(0, 80),
    });
    await this.reorganize();
    return id;
  }
  async backup(reason) {
    const b = { id: uuid(), created: Date.now(), reason, tables: {} };
    for (const table of metaTables)
      b.tables[table] = await this.v.entries(table);
    await this.v.put("backups", b.id, b);
    return b;
  }
  async restore(id) {
    if (this.running) throw new Error("작업을 일시정지한 후 복원하세요.");
    const b = await this.v.get("backups", id);
    if (!b) throw new Error("백업을 찾을 수 없습니다.");
    await this.backup("복원 직전");
    const ops = [];
    for (const table of metaTables) {
      for (const row of await this.v.entries(table))
        ops.push({ table, id: row.id, remove: true });
      for (const row of b.tables[table] || []) ops.push({ table, ...row });
    }
    await this.v.putMany(ops);
    await this.init();
    await this.emit();
  }
  async enqueue(files) {
    const batch = uuid();
    let count = 0;
    for (const file of files) {
      this.v.check();
      const id = uuid(),
        job = {
          id,
          batch,
          name: file.name,
          created: Date.now(),
          state: "queued",
        };
      try {
        if (!file.size || file.size > 100 * 1024 * 1024)
          throw new Error(
            "빈 파일이거나 파일당 100MB 한도를 넘었습니다. 원본은 기기에 보존됩니다.",
          );
        const hash = await sha256(file),
          existing = (await this.v.all("media")).find((m) => m.hash === hash);
        if (existing) {
          job.state = "duplicate";
          job.media = existing.id;
          job.error = existing.deletedAt
            ? "휴지통에 같은 원본이 있습니다. 설정에서 복원하세요."
            : "";
        } else {
          const media = {
            id: uuid(),
            hash,
            name: file.name,
            kind:
              file.type.startsWith("video/") ||
              /\.(mov|mp4|webm|m4v)$/i.test(file.name)
                ? "video"
                : "photo",
            ...(await this.captureDate(file)),
            state: "queued",
            children: [],
            faces: [],
            needsReview: false,
            userChecked: false,
            history: [],
            created: Date.now(),
          };
          job.media = media.id;
          await this.v.putMany([
            { table: "originals", id: media.id, value: file },
            { table: "media", id: media.id, value: media },
            { table: "jobs", id: job.id, value: job },
          ]);
        }
      } catch (error) {
        job.state = "failed";
        job.error = error.message;
      }
      await this.v.put("jobs", job.id, job);
      count++;
      await this.emit();
    }
    return { batch, count };
  }
  async process(job) {
    const m = await this.v.get("media", job.media);
    if (!m || m.deletedAt) return { state: "excluded" };
    const file = await this.v.get("originals", m.id);
    if (!file) throw new Error("저장된 원본을 찾을 수 없습니다.");
    const previousState = job.previousState || m.state;
    await this.v.put("media", m.id, { ...m, state: "analyzing" });
    try {
      const settings = await this.settings(),
        result = await this.analyzer(file, settings);
      // Explicit whole-photo corrections survive reanalysis. New face candidates remain visible.
      for (const face of result.faces) {
        const old = (m.faces || []).find(
          (f) =>
            (f.manualChild || f.manualIgnored) &&
            f.frame === face.frame &&
            iou(f.bbox, face.bbox) > 0.5,
        );
        if (old) {
          face.manualChild = old.manualChild;
          face.manualIgnored = old.manualIgnored;
        }
      }
      const evaluated = classify(result.faces, await this.gallery(), settings);
      const updated = {
        ...m,
        ...evaluated,
        previewId: result.previewId,
        diagnostics: result.diagnostics,
        error: "",
        analyzed: Date.now(),
        schema: 5,
      };
      if (m.userChecked) {
        updated.children = m.children;
        updated.needsReview = false;
        updated.state =
          previousState === "excluded" || !m.children.length
            ? "excluded"
            : "classified";
      }
      updated.history = [
        ...(m.history || []),
        {
          before: { ...m, state: previousState },
          reason: "분석 전",
          created: Date.now(),
        },
      ]
        .slice(-20)
        .map((h) =>
          h.before ? { ...h, before: { ...h.before, history: [] } } : h,
        );
      updated.paths = organizedPaths(updated, await this.kids(), settings.unit);
      await this.v.putMany([
        ...result.entries,
        { table: "media", id: m.id, value: updated },
      ]);
      updated.state = updated.needsReview
        ? "review"
        : updated.state === "excluded"
          ? "excluded"
          : "organized";
      await this.v.put("media", m.id, updated);
      return { state: updated.state, error: "", completed: Date.now() };
    } catch (error) {
      m.state = "failed";
      m.error = error.message;
      m.needsReview = true;
      await this.v.put("media", m.id, m);
      throw error;
    }
  }
  async run() {
    if (this.running) return;
    this.running = true;
    this.stopped = false;
    try {
      const execute = async () => {
        await sequentialQueue(
          (await this.v.all("jobs")).sort((a, b) => a.created - b.created),
          (j) => this.process(j),
          async (j) => {
            await this.v.put("jobs", j.id, j);
            await this.emit();
          },
          () => this.stopped,
        );
      };
      if (globalThis.navigator?.locks)
        await navigator.locks.request(
          `photojoy-queue-${this.v.owner}`,
          { ifAvailable: true },
          async (lock) => {
            if (!lock)
              throw new Error(
                "다른 탭에서 분류 중입니다. 그 탭에서 작업을 마쳐 주세요.",
              );
            await execute();
          },
        );
      else await execute();
    } finally {
      this.running = false;
      await this.emit();
    }
  }
  pause() {
    this.stopped = true;
  }
  async reanalyze(ids) {
    if (this.running)
      throw new Error("현재 작업을 일시정지한 뒤 다시 분석하세요.");
    for (const id of ids) {
      const m = await this.v.get("media", id);
      if (!m || m.deletedAt) continue;
      await this.v.put("media", id, { ...m, state: "queued" });
      const job = {
        id: uuid(),
        media: id,
        name: m.name,
        state: "queued",
        created: Date.now(),
        batch: "재분석",
        previousState: m.state,
      };
      await this.v.put("jobs", job.id, job);
    }
    await this.emit();
    return this.run();
  }
  async rematch() {
    this.assertIdle();
    const gallery = await this.gallery(),
      settings = await this.settings(),
      kids = await this.kids();
    for (const m of await this.media())
      if (
        !m.userChecked &&
        m.faces?.length &&
        !["queued", "analyzing", "failed", "excluded"].includes(m.state)
      ) {
        const evaluated = classify(m.faces, gallery, settings);
        Object.assign(m, evaluated);
        m.paths = organizedPaths(m, kids, settings.unit);
        if (!m.needsReview) m.state = "organized";
        await this.v.put("media", m.id, m);
      }
    await this.emit();
  }
  async reorganize() {
    const unit = (await this.settings()).unit,
      kids = await this.kids();
    for (const m of await this.media()) {
      m.paths = organizedPaths(m, kids, unit);
      await this.v.put("media", m.id, m);
    }
    await this.emit();
  }
  async record(m, reason, extra = []) {
    const before = structuredClone(m);
    before.history = [];
    m.history = [
      ...(m.history || []),
      { before, reason, created: Date.now(), references: extra },
    ].slice(-20);
    return m;
  }
  async assign(ids, children, excluded = false) {
    this.assertIdle();
    const valid = new Set((await this.kids()).map((c) => c.id));
    if (children.some((c) => !valid.has(c)) || (!children.length && !excluded))
      throw new Error("배정할 아이를 선택하세요.");
    for (const id of ids) {
      const m = await this.v.get("media", id);
      await this.record(m, "사용자 일괄 배정");
      Object.assign(m, {
        children: [...new Set(children)],
        userChecked: true,
        needsReview: false,
        state: excluded ? "excluded" : "organized",
      });
      m.paths = organizedPaths(
        m,
        await this.kids(),
        (await this.settings()).unit,
      );
      await this.v.put("media", id, m);
    }
    await this.emit();
  }
  async correctFace(mediaId, faceId, child, learn = false) {
    this.assertIdle();
    const m = await this.v.get("media", mediaId),
      face = m.faces.find((f) => f.id === faceId);
    if (!face) throw new Error("얼굴을 찾을 수 없습니다.");
    if (child && !(await this.kids()).some((c) => c.id === child))
      throw new Error("등록한 아이를 선택하세요.");
    if (
      learn &&
      (!child ||
        !face.embedding?.length ||
        face.quality?.referenceUsable === false ||
        face.small)
    )
      throw new Error(
        "참고 얼굴로 쓰기에는 품질이 부족합니다. 더 선명한 사진을 등록하세요.",
      );
    const previous = (await this.v.entries("references")).filter(
      (r) => r.value.faceId === faceId,
    );
    await this.record(m, "얼굴 교정", previous);
    face.manualChild = child || null;
    face.manualIgnored = !child;
    const ops = [];
    for (const r of previous)
      ops.push({
        table: "references",
        id: r.id,
        value: { ...r.value, active: false },
      });
    if (learn) {
      const id = `corrected-${faceId}`;
      ops.push({
        table: "references",
        id,
        value: {
          id,
          child,
          faceId,
          embedding: face.embedding,
          cropId: face.id,
          active: true,
          origin: "사용자 얼굴 교정",
          created: Date.now(),
        },
      });
    }
    const updatedRefs = new Map(
      (await this.v.entries("references")).map((r) => [r.id, r.value]),
    );
    for (const op of ops) updatedRefs.set(op.id, op.value);
    const gallery = {};
    for (const ref of updatedRefs.values())
      if (ref.active !== false) (gallery[ref.child] ??= []).push(ref.embedding);
    Object.assign(m, classify(m.faces, gallery, await this.settings()));
    m.userChecked = false;
    m.paths = organizedPaths(
      m,
      await this.kids(),
      (await this.settings()).unit,
    );
    if (!m.needsReview) m.state = "organized";
    await this.v.putMany([...ops, { table: "media", id: m.id, value: m }]);
    await this.rematch();
  }
  async undo(id) {
    this.assertIdle();
    const m = await this.v.get("media", id),
      h = m.history?.pop();
    if (!h) throw new Error("되돌릴 기록이 없습니다.");
    if (!h.before) {
      Object.assign(m, h);
      await this.v.put("media", id, m);
      return this.emit();
    }
    const ops = [];
    if (h.reason === "얼굴 교정") {
      const changed = m.faces
        .filter(
          (f, i) =>
            f.manualChild !== h.before.faces[i]?.manualChild ||
            f.manualIgnored !== h.before.faces[i]?.manualIgnored,
        )
        .map((f) => f.id);
      for (const r of await this.v.entries("references"))
        if (changed.includes(r.value.faceId))
          ops.push({
            table: "references",
            id: r.id,
            value: { ...r.value, active: false },
          });
      for (const r of h.references || [])
        ops.push({ table: "references", ...r });
    }
    ops.push({
      table: "media",
      id,
      value: { ...h.before, history: m.history },
    });
    await this.v.putMany(ops);
    if (
      h.before.state === "queued" &&
      !(await this.v.all("jobs")).some(
        (j) => j.media === id && j.state === "queued",
      )
    ) {
      const jobId = uuid();
      await this.v.put("jobs", jobId, {
        id: jobId,
        media: id,
        name: m.name,
        state: "queued",
        created: Date.now(),
        batch: "되돌리기",
      });
    }
    await this.emit();
  }
  async addReference(child, file, analysis, faceIndex) {
    this.assertIdle();
    const face = analysis.faces[faceIndex];
    if (!face?.embedding?.length || face.quality?.referenceUsable === false)
      throw new Error("학습에 적합한 선명한 얼굴을 선택해 주세요.");
    const hash = await sha256(file),
      id = `${child}:${hash}:${faceIndex}`;
    await this.v.putMany([
      ...analysis.entries,
      { table: "referenceSources", id: hash, value: file },
      {
        table: "references",
        id,
        value: {
          id,
          child,
          embedding: face.embedding,
          sourceHash: hash,
          faceIndex,
          cropId: face.id,
          active: true,
          origin: "직접 참고 사진",
          created: Date.now(),
        },
      },
    ]);
    await this.rematch();
  }
  async retireReference(id) {
    this.assertIdle();
    const r = await this.v.get("references", id);
    if (r) {
      await this.backup("참고 얼굴 제외 전");
      r.active = false;
      await this.v.put("references", id, r);
      await this.rematch();
    }
  }
  async rebuildReferences(child) {
    this.assertIdle();
    await this.backup("참고 얼굴 재추출 전");
    let rebuilt = 0;
    const errors = [];
    for (const r of (await this.refs()).filter((r) => r.child === child)) {
      const source = await this.v.get("referenceSources", r.sourceHash || "");
      if (!source) {
        errors.push("원본 없는 기존 특징은 보존했습니다.");
        continue;
      }
      try {
        const result = await this.analyzer(source, await this.settings());
        if (result.faces.length !== 1)
          throw new Error(
            "얼굴을 다시 선택해야 합니다. 참고 사진을 새로 등록하세요.",
          );
        await this.addReference(child, source, result, 0);
        rebuilt++;
      } catch (error) {
        errors.push(error.message);
      }
    }
    return { rebuilt, errors };
  }
  async trash(ids) {
    this.assertIdle();
    for (const id of ids) {
      const m = await this.v.get("media", id);
      await this.record(m, "휴지통 이동");
      m.deletedAt = Date.now();
      m.children = [];
      m.paths = [];
      m.needsReview = false;
      m.state = "excluded";
      await this.v.put("media", id, m);
    }
    await this.emit();
  }
  async restoreTrash(id) {
    await this.undo(id);
  }
}
