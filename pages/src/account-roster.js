const tables = ["children", "references"];
const idOk = (id) =>
  typeof id === "string" &&
  /^[a-zA-Z0-9:_-]{1,300}$/.test(id) &&
  !["__proto__", "prototype", "constructor"].includes(id);
const revisionOk = (rev) =>
  typeof rev === "string" && /^\d{15}-[a-f0-9-]{36}$/.test(rev);
const imageTypes = ["image/jpeg", "image/png", "image/webp"];
const maxCrop = 384 * 1024;
function base64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
const decode = (value) =>
  Uint8Array.from(atob(value), (ch) => ch.charCodeAt(0));

async function pack(v, stamp) {
  const { table, id, rev } = stamp;
  const row = await v.get(table, id);
  if (!row || stamp.removed || (table === "references" && row.active === false))
    return { rev, removed: true };
  if (table === "children")
    return { rev, name: row.name, group: row.group_name || "" };
  const floats = Float32Array.from(row.embedding || []);
  if (
    floats.length !== 128 ||
    !floats.every(Number.isFinite) ||
    !idOk(row.child)
  )
    throw Error(
      "호환되지 않는 참고 얼굴이 있습니다. 아이 관리에서 확인해 주세요.",
    );
  const crop = await v.get(
    "crops",
    row.cropId || row.faceId || id.split(":")[0],
  );
  if (
    crop &&
    (crop.size > maxCrop || (crop.type && !imageTypes.includes(crop.type)))
  )
    throw Error("참고 얼굴 이미지의 형식이나 크기를 확인해 주세요.");
  return {
    rev,
    child: row.child,
    vector: base64(new Uint8Array(floats.buffer)),
    image: crop ? base64(new Uint8Array(await crop.arrayBuffer())) : "",
    mime: crop?.type || "image/jpeg",
  };
}

async function unpack(v, table, id, row) {
  if (row.removed === true) return [{ table, id, remove: true }];
  if (table === "children") {
    if (
      typeof row.name !== "string" ||
      !row.name.trim() ||
      row.name.length > 80 ||
      typeof row.group !== "string" ||
      row.group.length > 80
    )
      throw Error("계정의 아이 정보 형식을 확인해 주세요.");
    return [
      {
        table,
        id,
        value: {
          ...(await v.get(table, id)),
          id,
          name: row.name,
          group_name: row.group,
        },
      },
    ];
  }
  if (
    !idOk(row.child) ||
    typeof row.vector !== "string" ||
    row.vector.length !== 684 ||
    typeof row.image !== "string" ||
    row.image.length > (maxCrop * 4) / 3 ||
    !imageTypes.includes(row.mime)
  )
    throw Error("계정의 참고 얼굴 형식을 확인해 주세요.");
  const raw = decode(row.vector);
  if (raw.length !== 512)
    throw Error("얼굴 비교값의 크기가 올바르지 않습니다.");
  const embedding = Array.from(new Float32Array(raw.buffer));
  if (!embedding.every(Number.isFinite))
    throw Error("얼굴 비교값이 올바르지 않습니다.");
  const current = await v.get(table, id);
  const cropId = "account-" + id;
  const entries = [
    {
      table,
      id,
      value: {
        ...current,
        id,
        child: row.child,
        embedding,
        active: true,
        cropId: row.image ? cropId : current?.cropId || cropId,
        origin: current?.origin || "계정 참고 얼굴",
      },
    },
  ];
  if (row.image)
    entries.push({
      table: "crops",
      id: cropId,
      value: new Blob([decode(row.image)], { type: row.mime }),
    });
  return entries;
}

// Each roster change and its version are committed together in IndexedDB. Independent edits
// use separate remote keys. Concurrent edits of one record converge on the greater revision.
export class AccountRoster {
  constructor(vault, cloud, onStatus = () => {}, onPull = async () => {}) {
    this.v = vault;
    this.cloud = cloud;
    this.onStatus = onStatus;
    this.onPull = onPull;
    this.message = "계정 명단을 확인하고 있습니다…";
    this.enabled = false;
    this.closed = false;
    vault.trackRoster = true;
    vault.onRosterWrite = () => {
      if (this.enabled) this.sync(false);
    };
  }
  status(message) {
    if (!this.closed) {
      this.message = message;
      this.onStatus(this);
    }
  }
  async init() {
    this.enabled = !!(await this.v.get("rosterPrefs", "enabled"));
    if (
      !this.enabled &&
      ((await this.v.all("children")).length ||
        (await this.v.all("references")).length)
    ) {
      this.status(
        "이 기기에 등록한 아이가 있습니다. 계정에 보관하면 다른 기기에서도 불러올 수 있습니다.",
      );
      return;
    }
    await this.enable();
  }
  async enable() {
    await this.v.put("rosterPrefs", "enabled", true);
    this.enabled = true;
    await this.sync();
  }
  sync(pull = true) {
    if (this.closed || !this.enabled) return Promise.resolve();
    this.requested = true;
    this.pullRequested ||= pull;
    if (!this.task)
      this.task = this.drain().finally(() => {
        this.task = null;
        if (this.requested && !this.closed) this.sync();
      });
    return this.task;
  }
  async drain() {
    while (this.requested && !this.closed) {
      this.requested = false;
      const pull = this.pullRequested;
      this.pullRequested = false;
      this.status("아이 명단 동기화 중…");
      try {
        if (globalThis.navigator?.onLine === false) throw Error("offline");
        await this.exchange(pull);
        this.status("아이 명단이 계정에 저장되었습니다.");
      } catch (error) {
        this.status(
          "기기에 보관 중 · 동기화를 완료하지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요. " +
            (String(error.code || "")
              .toLowerCase()
              .includes("permission")
              ? "계정 접근 권한을 확인하세요."
              : ""),
        );
      }
    }
  }
  close() {
    this.closed = true;
    this.v.onRosterWrite = null;
  }
  check() {
    if (this.closed) throw Error("계정이 바뀌었습니다.");
    this.v.check();
  }
  async exchange(pull) {
    this.check();
    const remote = pull ? await this.cloud.read() : {};
    this.check();
    let changed = false;
    for (const table of pull ? tables : []) {
      for (const { id } of await this.v.entries(table)) {
        const key = table + "/" + id;
        if (!idOk(id)) throw Error("아이 명단 ID를 확인하세요.");
        if (
          !remote?.[table]?.[id] &&
          !(await this.v.get("rosterVersions", key))
        ) {
          // Seed legacy records once. A matching account record is authoritative on first import.
          const rev = "000000000000000-" + crypto.randomUUID();
          await this.v.putMany(
            [
              {
                table: "rosterVersions",
                id: key,
                value: { table, id, rev, dirty: true },
              },
            ],
            { remote: true, ifStamp: { key, rev: null } },
          );
        }
      }
      for (const [id, row] of Object.entries(remote?.[table] || {})) {
        this.check();
        if (!idOk(id) || !revisionOk(row?.rev))
          throw Error("명단 형식을 확인하세요.");
        const key = table + "/" + id,
          local = await this.v.get("rosterVersions", key);
        if (!local || row.rev > local.rev)
          changed =
            (await this.apply(table, id, row, local?.rev ?? null)) || changed;
      }
    }
    for (const { id: key, value: stamp } of await this.v.entries(
      "rosterVersions",
    )) {
      this.check();
      if (!stamp.dirty) continue;
      if (
        !tables.includes(stamp.table) ||
        !idOk(stamp.id) ||
        key !== stamp.table + "/" + stamp.id
      )
        throw Error("명단 키를 확인하세요.");
      const payload = await pack(this.v, stamp);
      this.check();
      // A second edit during preparation belongs to the next exchange.
      if ((await this.v.get("rosterVersions", key))?.rev !== stamp.rev) {
        this.requested = true;
        continue;
      }
      const winner = await this.cloud.merge(key, payload);
      this.check();
      if (!revisionOk(winner?.rev))
        throw Error("서버 저장을 확인하지 못했습니다.");
      if (winner.rev !== stamp.rev)
        changed =
          (await this.apply(stamp.table, stamp.id, winner, stamp.rev)) ||
          changed;
      else
        await this.v.putMany(
          [
            {
              table: "rosterVersions",
              id: key,
              value: { ...stamp, dirty: false },
            },
          ],
          { remote: true, ifStamp: { key, rev: stamp.rev } },
        );
    }
    if (changed) {
      this.check();
      await this.onPull();
    }
  }
  async apply(table, id, row, before) {
    const key = table + "/" + id,
      entries = await unpack(this.v, table, id, row);
    this.check();
    entries.push({
      table: "rosterVersions",
      id: key,
      value: {
        table,
        id,
        rev: row.rev,
        dirty: false,
        removed: row.removed === true,
      },
    });
    return this.v.putMany(entries, {
      remote: true,
      ifStamp: { key, rev: before },
    });
  }
}
