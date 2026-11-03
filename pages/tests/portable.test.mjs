import test from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";
import { zipSync } from "fflate";
import { Vault } from "../src/vault.js";
import { Project, sha256 } from "../src/project.js";
import { importPortable } from "../src/portable.js";
const encoder = new TextEncoder();
const create = async () =>
  new Project(
    new Vault(crypto.randomUUID()),
    async () => {},
    async () => {},
  ).init();
async function archive({ part = 1, parts = 1, broken = false } = {}) {
  const bytes = encoder.encode("untouched-original"),
    hash = await sha256(new Blob([bytes]));
  const manifest = {
    format: "PhotoJoy-portable-v1",
    model: "YuNet-2023mar/SFace-2021dec",
    created: 123,
    part,
    parts,
    records: [
      {
        table: "children",
        id: "kid",
        value: { id: "kid", name: "한글이름", group_name: "햇살반" },
      },
      {
        table: "media",
        id: "photo",
        value: {
          id: "photo",
          name: "sample.jpg",
          hash,
          children: ["kid"],
          faces: [],
          state: "organized",
          userChecked: true,
          captured: "2026-11-03",
          history: [],
        },
      },
      {
        table: "originals",
        id: "photo",
        blob: "photo.jpg",
        name: "sample.jpg",
        type: "image/jpeg",
      },
      {
        table: "references",
        id: "ref",
        value: {
          id: "ref",
          child: "kid",
          embedding: Array.from({ length: 128 }, (_, i) => (i ? 0 : 1)),
          active: true,
        },
      },
    ],
  };
  return new File(
    [
      zipSync({
        "manifest.json": encoder.encode(JSON.stringify(manifest)),
        "photo.jpg": broken ? encoder.encode("broken") : bytes,
      }),
    ],
    `part-${part}.zip`,
  );
}
test("portable import preserves Korean names, original bytes and reference embeddings; repeat is idempotent", async () => {
  const p = await create(),
    zip = await archive();
  await importPortable(p, [zip]);
  await importPortable(p, [zip]);
  assert.equal((await p.media()).length, 1);
  assert.equal((await p.kids())[0].name, "한글이름");
  assert.equal((await p.refs())[0].embedding.length, 128);
  assert.equal(
    await (await p.v.get("originals", "photo")).text(),
    "untouched-original",
  );
});
test("incomplete split backup is rejected before import; broken later part restores prior metadata", async () => {
  const p = await create();
  await p.addChild("보존할 아이", "", "existing");
  const first = await archive({ part: 1, parts: 2 });
  await assert.rejects(importPortable(p, [first]), /모두/);
  await assert.rejects(
    importPortable(p, [
      first,
      await archive({ part: 2, parts: 2, broken: true }),
    ]),
    /해시/,
  );
  assert.deepEqual(
    (await p.kids()).map((k) => k.id),
    ["existing"],
  );
  assert.equal((await p.media()).length, 0);
});
