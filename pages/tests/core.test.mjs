import test from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";
import {
  compare,
  normalize,
  similarityTransform,
  LANDMARK_TARGETS,
  decodeYunet,
} from "../src/face-math.js";
import { Vault } from "../src/vault.js";

test("ambiguous and absent reference faces are never auto accepted", () => {
  assert.equal(compare([1, 0], {}).accepted, false);
  assert.equal(
    compare([1, 0], { a: [[1, 0]], b: [[0.999, 0.001]] }).accepted,
    false,
  );
  assert.equal(compare([1, 0], { a: [[1, 0]], b: [[0, 1]] }).child, "a");
  assert.equal(compare([1, 0], { a: [[1, 0]], b: [[0, 1]] }).accepted, true);
  assert.equal(
    compare([0.55, Math.sqrt(1 - 0.55 ** 2)], { a: [[1, 0]] }).accepted,
    false,
  );
  assert.throws(() => normalize([0, 0]));
});
test("similarity transform recovers rotation scale and translation", () => {
  const angle = 0.3,
    scale = 2.5,
    c = Math.cos(angle),
    s = Math.sin(angle);
  const source = LANDMARK_TARGETS.map(([x, y]) => [
    scale * (c * x - s * y) + 30,
    scale * (s * x + c * y) - 14,
  ]);
  const [a, b, cc, d, e, f] = similarityTransform(source);
  source.forEach(([x, y], i) => {
    assert.ok(Math.abs(a * x + cc * y + e - LANDMARK_TARGETS[i][0]) < 1e-8);
    assert.ok(Math.abs(b * x + d * y + f - LANDMARK_TARGETS[i][1]) < 1e-8);
  });
});
test("YuNet decodes grid offsets and removes overlapping detections", () => {
  const out = {};
  for (const s of [8, 16, 32])
    for (const [name, mult] of [
      ["cls", 1],
      ["obj", 1],
      ["bbox", 4],
      ["kps", 10],
    ])
      out[`${name}_${s}`] = { data: new Float32Array((640 / s) ** 2 * mult) };
  for (const s of [8, 16]) {
    out[`cls_${s}`].data[0] = 0.95;
    out[`obj_${s}`].data[0] = 0.95;
    out[`bbox_${s}`].data.set([
      40 / s,
      40 / s,
      Math.log(32 / s),
      Math.log(32 / s),
    ]);
  }
  const result = decodeYunet(out);
  assert.equal(result.length, 1);
  result[0].bbox.forEach((n, i) =>
    assert.ok(Math.abs(n - [24, 24, 56, 56][i]) < 1e-5),
  );
});
test("IndexedDB isolates same IDs by Firebase user and table", async () => {
  const a = new Vault("alice"),
    b = new Vault("bob");
  await a.putMany([
    { table: "children", id: "same", value: { name: "김민준" } },
    { table: "originals", id: "same", value: new Blob(["original"]) },
  ]);
  await b.put("children", "same", { name: "이서연" });
  assert.deepEqual(await a.all("children"), [{ name: "김민준" }]);
  assert.deepEqual(await b.get("children", "same"), { name: "이서연" });
  assert.equal(await b.get("originals", "same"), undefined);
  assert.equal(await (await a.get("originals", "same")).text(), "original");
});
test("stale signed-out account cannot read or write its library", async () => {
  let active = true;
  const v = new Vault("stale", () => active);
  await v.put("children", "one", "한글 이름");
  active = false;
  await assert.rejects(v.get("children", "one"), /로그인이 바뀌/);
  await assert.rejects(v.put("children", "two", "blocked"), /로그인이 바뀌/);
});
