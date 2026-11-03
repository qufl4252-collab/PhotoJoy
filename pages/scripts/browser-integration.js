import { Project, sha256 } from "../src/project.js";
import { Vault } from "../src/vault.js";
import { analyzeFile, captureDate } from "../src/media-adapter.js";
import { makeExports } from "../src/export.js";
import { unzipSync } from "fflate";
export async function realPipeline(out) {
  const started = performance.now(),
    owner = "test-real-" + crypto.randomUUID(),
    p = await new Project(new Vault(owner), analyzeFile, captureDate).init();
  const load = async (name) =>
    new File(
      [await (await fetch("./test-output/fixtures/" + name)).blob()],
      name,
      { type: name.endsWith("png") ? "image/png" : "image/jpeg" },
    );
  const astronaut = await load("astronaut.png"),
    grace = await load("grace_hopper.jpg");
  const a = await analyzeFile(astronaut, {});
  await p.addChild("공개 성인 A", "검증", "a");
  await p.addReference("a", astronaut, a, 0);
  const bitmap = await createImageBitmap(astronaut),
    variants = [];
  for (let i = 0; i < 10; i++) {
    const c = document.createElement("canvas");
    c.width = 512;
    c.height = 512;
    const ctx = c.getContext("2d");
    ctx.filter = `brightness(${0.9 + i * 0.02})`;
    ctx.drawImage(bitmap, 0, 0);
    const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
    variants.push(new File([blob], `sample-${i}.jpg`, { type: "image/jpeg" }));
  }
  bitmap.close();
  const ticks = [];
  p.change = async () => {
    const s = await p.snapshot();
    ticks.push(s.jobCounts.finished);
    out.textContent = `실모델 파이프라인: ${s.jobCounts.finished}/${s.jobCounts.total}`;
  };
  await p.enqueue([...variants, grace, variants[0]]);
  await p.run();
  let snapshot = await p.snapshot();
  const report = {
    fixture:
      "Public adult photos; ten derivatives of one source, not independent child accuracy data",
    single10: snapshot.media
      .filter((m) => m.name.startsWith("sample-"))
      .map((m) => ({
        name: m.name,
        state: m.state,
        children: m.children,
        faces: m.faces.length,
      })),
    unknown: snapshot.media.find((m) => m.name === grace.name)?.state,
    duplicate: snapshot.jobCounts.duplicate,
    counts: snapshot.counts,
  };
  const unknown = snapshot.media.find((m) => m.name === grace.name);
  await p.addChild("공개 성인 B", "검증", "b");
  await p.correctFace(unknown.id, unknown.faces[0].id, "b", true);
  report.corrected = (await p.v.get("media", unknown.id)).children;
  const left = await createImageBitmap(astronaut),
    right = await createImageBitmap(grace),
    group = document.createElement("canvas");
  group.width = 1024;
  group.height = 600;
  group.getContext("2d").drawImage(left, 0, 0, 512, 512);
  group.getContext("2d").drawImage(right, 512, 0, 512, 600);
  left.close();
  right.close();
  const groupFile = new File(
    [await new Promise((r) => group.toBlob(r, "image/jpeg", 0.95))],
    "public-two-adults.jpg",
    { type: "image/jpeg" },
  );
  await p.enqueue([groupFile]);
  await p.run();
  snapshot = await p.snapshot();
  const g = snapshot.media.find((m) => m.name === groupFile.name);
  report.group = {
    state: g.state,
    faces: g.faces.length,
    children: g.children,
    paths: g.paths,
  };
  const exports = await makeExports(p, { children: ["a"] });
  const zipped = unzipSync(
    new Uint8Array(
      await (await p.v.get("exportBlobs", exports[0].id)).arrayBuffer(),
    ),
  );
  const first = snapshot.media.find((m) => m.name === "sample-0.jpg"),
    path = Object.keys(zipped).find((n) => n.includes(first.hash.slice(0, 12)));
  report.originalHashPreserved =
    (await sha256(new Blob([zipped[path]]))) === first.hash;
  report.seconds = (performance.now() - started) / 1000;
  report.jobCounts = snapshot.jobCounts;
  report.owner = owner;
  out.textContent = JSON.stringify(report, null, 2);
}
