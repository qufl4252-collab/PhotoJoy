import test from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";
import { unzipSync } from "fflate";
import { Vault } from "../src/vault.js";
import { Project } from "../src/project.js";
import {
  classify,
  calibration,
  dateFolder,
  summarize,
  STATES,
} from "../src/classification.js";
import { makeExports, statistics } from "../src/export.js";
const vectors = {
  a: [1, 0, 0, 0],
  b: [0, 1, 0, 0],
  c: [0, 0, 1, 0],
  unknown: [0, 0, 0, 1],
};
function face(person) {
  return {
    id: crypto.randomUUID(),
    embedding: vectors[person],
    pixelSize: 100,
    bbox: [0.1, 0.1, 0.3, 0.3],
    quality: { usable: true, referenceUsable: true },
    frame: null,
  };
}
const file = (text, name = "photo.jpg") =>
  new File([text], name, { type: "image/jpeg", lastModified: 1793664000000 });
async function fixture() {
  const v = new Vault(crypto.randomUUID()),
    p = await new Project(
      v,
      async (f) => {
        const text = await f.text();
        if (text.startsWith("fail")) throw new Error("decode failed");
        const faces = text
          .split(":")[0]
          .split(",")
          .filter((p) => vectors[p])
          .map(face);
        return {
          faces,
          entries: [],
          previewId: null,
          diagnostics: [{ detected: faces.length }],
        };
      },
      async () => ({ captured: "2026-11-03", date_source: "fixture" }),
    ).init();
  for (const id of ["a", "b", "c"]) {
    await p.addChild(
      { a: "김하늘", b: "김민준", c: "박서연" }[id],
      "햇살반",
      id,
    );
    for (let i = 0; i < 3; i++)
      await v.put("references", id + i, {
        id: id + i,
        child: id,
        embedding: vectors[id],
        active: true,
      });
  }
  return p;
}
test("A: 10 clear photos organize without user approval, ZIP preserves originals", async () => {
  const p = await fixture();
  await p.enqueue(Array.from({ length: 10 }, (_, i) => file("a:" + i)));
  await p.run();
  const snapshot = await p.snapshot();
  assert.equal(snapshot.counts.organized, 10);
  assert.ok(
    snapshot.media.every(
      (m) =>
        m.userChecked === false &&
        m.children[0] === "a" &&
        m.paths[0].includes("26-11월1주차"),
    ),
  );
  assert.equal(statistics(snapshot.kids, snapshot.media)[0].total, 10);
  const result = await makeExports(p, { children: ["a"] });
  assert.equal(result[0].sentAt, null);
  const zip = unzipSync(
    new Uint8Array(
      await (await p.v.get("exportBlobs", result[0].id)).arrayBuffer(),
    ),
  );
  assert.equal(Object.keys(zip).filter((n) => n.endsWith(".jpg")).length, 10);
  assert.ok(
    Object.values(zip).some(
      (bytes) => new TextDecoder().decode(bytes) === "a:0",
    ),
  );
});
test("B: group photo is logically shared with all three children", async () => {
  const p = await fixture();
  await p.enqueue([file("a,b,c")]);
  await p.run();
  const m = (await p.media())[0];
  assert.equal(m.state, "organized");
  assert.deepEqual(m.children, ["a", "b", "c"]);
  assert.equal(m.paths.length, 3);
  assert.equal((await p.v.all("originals")).length, 1);
});
test("C: unknown face is held, known face in same image still organizes", async () => {
  const p = await fixture();
  await p.enqueue([file("unknown"), file("a,unknown")]);
  await p.run();
  const m = await p.media();
  assert.ok(m.every((x) => x.state === "review"));
  assert.equal(m.filter((x) => !x.children.length).length, 1);
  assert.deepEqual(m.find((x) => x.faces.length === 2).children, ["a"]);
  assert.equal(m.find((x) => x.faces.length === 2).paths.length, 1);
});
test("D/G: 105 files run sequentially; failure does not stop queue; state sum equals total", async () => {
  const p = await fixture();
  await p.enqueue(
    Array.from({ length: 105 }, (_, i) =>
      file((i === 50 ? "fail" : "a") + ":" + i),
    ),
  );
  let active = 0,
    max = 0;
  const analyze = p.analyzer;
  p.analyzer = async (...a) => {
    max = Math.max(max, ++active);
    try {
      return await analyze(...a);
    } finally {
      active--;
    }
  };
  await p.run();
  const s = await p.snapshot();
  assert.equal(max, 1);
  assert.equal(s.counts.organized, 104);
  assert.equal(s.counts.failed, 1);
  assert.equal(
    Object.keys(STATES).reduce((n, k) => n + s.counts[k], 0),
    105,
  );
  assert.equal(s.jobCounts.finished, 105);
  assert.ok(
    await p.v.get("originals", s.media.find((m) => m.state === "failed").id),
  );
});
test("E: only explicitly corrected face updates gallery; undo deactivates learned face", async () => {
  const p = await fixture();
  await p.enqueue([file("unknown:1"), file("unknown:2")]);
  await p.run();
  const before = await p.media(),
    m = before[0];
  await p.correctFace(m.id, m.faces[0].id, "a", true);
  const after = await p.media();
  assert.equal(after.find((x) => x.id !== m.id).children[0], "a");
  assert.equal(after.find((x) => x.id !== m.id).state, "organized");
  assert.equal((await p.refs()).length, 10);
  await p.undo(m.id);
  assert.equal((await p.refs()).length, 9);
  await p.rematch();
  assert.equal((await p.media()).find((x) => x.id !== m.id).state, "review");
});
test("F: same data/different filename deduplicates, same filename/different data survives", async () => {
  const p = await fixture();
  await p.enqueue([
    file("a:1", "same.jpg"),
    file("a:1", "other.jpg"),
    file("a:2", "same.jpg"),
  ]);
  await p.run();
  const s = await p.snapshot();
  assert.equal(s.media.length, 2);
  assert.equal(s.jobCounts.duplicate, 1);
  assert.equal(s.jobCounts.total, 3);
  await p.reanalyze([s.media[0].id]);
  assert.equal((await p.media()).length, 2);
});
test("migration backs up legacy references and corrections before transforming state", async () => {
  const v = new Vault(crypto.randomUUID());
  await v.put("media", "old", {
    id: "old",
    name: "old.jpg",
    children: ["a"],
    status: "confirmed",
    reviewed: true,
    faces: [],
    history: [{ status: "review", children: [], reviewed: false }],
  });
  await v.put("originals", "old", new Blob(["preserved"]));
  await v.put("references", "face:a", { child: "a", embedding: [1, 0] });
  const p = await new Project(
    v,
    () => {},
    () => {},
  ).init();
  assert.equal((await p.media())[0].state, "organized");
  assert.equal((await p.media())[0].history.length, 1);
  assert.equal(await (await v.get("originals", "old")).text(), "preserved");
  assert.equal((await v.all("backups")).length, 1);
  assert.equal(
    (await v.all("backups"))[0].tables.media[0].value.state,
    undefined,
  );
  assert.equal((await p.refs()).length, 1);
});

test("child ZIP logs do not reveal unrelated children or photos", async () => {
  const p = await fixture();
  await p.enqueue([file("a:own", "own.jpg"), file("b:private", "private.jpg")]);
  await p.run();
  const [out] = await makeExports(p, { children: ["a"] });
  const zip = unzipSync(
    new Uint8Array(await (await p.v.get("exportBlobs", out.id)).arrayBuffer()),
  );
  const log = new TextDecoder().decode(zip["분류기록/분류.csv"]);
  assert.match(log, /own.jpg/);
  assert.doesNotMatch(log, /private.jpg|김민준/);
});

test("undo after reanalysis restores final state and initial-analysis undo can resume", async () => {
  const p = await fixture();
  await p.enqueue([file("a")]);
  await p.run();
  const id = (await p.media())[0].id;
  await p.reanalyze([id]);
  await p.undo(id);
  assert.equal((await p.media())[0].state, "organized");
  await p.undo(id);
  assert.equal((await p.media())[0].state, "queued");
  await p.run();
  assert.equal((await p.media())[0].state, "organized");
});
test("user assignment and exclusion survive new reference comparisons", async () => {
  const p = await fixture();
  await p.enqueue([file("a")]);
  await p.run();
  const m = (await p.media())[0];
  await p.assign([m.id], ["b"]);
  await p.rematch();
  assert.deepEqual((await p.media())[0].children, ["b"]);
  await p.assign([m.id], [], true);
  assert.equal((await p.snapshot()).counts.excluded, 1);
  assert.equal((await p.snapshot()).counts.organized, 0);
});
test("pause leaves queued work resumable and deleted photos can be restored", async () => {
  const p = await fixture();
  await p.enqueue([file("a:1"), file("a:2")]);
  p.change = async () => {
    if ((await p.v.all("jobs")).some((j) => j.state === "organized")) p.pause();
  };
  await p.run();
  assert.equal((await p.snapshot()).counts.queued, 1);
  p.change = () => {};
  await p.run();
  const m = (await p.media())[0];
  await p.trash([m.id]);
  assert.equal((await p.media()).length, 1);
  await p.restoreTrash(m.id);
  assert.equal((await p.media()).length, 2);
});
test("calibration separates unknowns, small faces configurable, week rules deterministic", () => {
  const refs = {
    a: [vectors.a, vectors.a, vectors.a],
    b: [vectors.b, vectors.b, vectors.b],
  };
  assert.equal(calibration(refs).calibrated, true);
  assert.ok(
    calibration(refs, "careful").threshold >=
      calibration(refs, "bold").threshold,
  );
  assert.equal(classify([face("unknown")], refs).children.length, 0);
  const f = face("b");
  f.pixelSize = 20;
  const r = classify([face("a"), f], refs, {
    minRelative: 0.3,
    minFacePixels: 32,
  });
  assert.equal(r.needsReview, false);
  assert.equal(r.faces[1].ignored, true);
  assert.equal(dateFolder("2026-11-08"), "26-11월2주차");
  assert.equal(dateFolder("2026-11-08", "day"), "2026-11-08");
});
