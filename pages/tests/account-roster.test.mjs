import test from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";
import { Vault } from "../src/vault.js";
import { AccountRoster } from "../src/account-roster.js";
function cloudStore() {
  const rows = { children: {}, references: {} };
  return {
    rows,
    read: async () => structuredClone(rows),
    async merge(key, value) {
      const [table, id] = key.split("/");
      if (!rows[table][id] || rows[table][id].rev < value.rev)
        rows[table][id] = structuredClone(value);
      return structuredClone(rows[table][id]);
    },
  };
}
test("existing roster is explicitly merged once, with the selected face but no source photo, then reused for recognition", async () => {
  const v = new Vault(crypto.randomUUID()),
    c = cloudStore(),
    vector = Array.from({ length: 128 }, (_, i) => +(i === 42));
  await v.putMany([
    {
      table: "children",
      id: "kid",
      value: { id: "kid", name: "예린", group_name: "꽃반" },
    },
    {
      table: "references",
      id: "kid:ref",
      value: {
        id: "kid:ref",
        child: "kid",
        cropId: "face",
        sourceHash: "private",
        embedding: vector,
      },
    },
    {
      table: "crops",
      id: "face",
      value: new Blob(["face only"], { type: "image/jpeg" }),
    },
    {
      table: "referenceSources",
      id: "private",
      value: new Blob(["whole group photo"]),
    },
    { table: "media", id: "private", value: { name: "private-photo.jpg" } },
  ]);
  const phone = new AccountRoster(v, c);
  await phone.init();
  assert.equal(phone.enabled, false);
  assert.deepEqual(c.rows, { children: {}, references: {} });
  await phone.enable();
  assert.equal(c.rows.children.kid.group, "꽃반");
  const encoded = c.rows.references["kid:ref"];
  assert.deepEqual(Object.keys(encoded).sort(), [
    "child",
    "image",
    "mime",
    "rev",
    "vector",
  ]);
  assert.equal(atob(encoded.image), "face only");
  const second = new Vault(crypto.randomUUID()),
    pc = new AccountRoster(second, c);
  await pc.init();
  assert.equal((await second.get("children", "kid")).name, "예린");
  const reference = await second.get("references", "kid:ref");
  assert.deepEqual(reference.embedding, vector);
  assert.equal(
    await (await second.get("crops", reference.cropId)).text(),
    "face only",
  );
  await pc.sync();
  assert.equal((await second.all("references")).length, 1);
});
test("offline edits survive a restart, merge independent changes, and retiring a reference removes its remote image", async () => {
  const c = cloudStore(),
    v = new Vault(crypto.randomUUID()),
    phone = new AccountRoster(v, c);
  await phone.init();
  const { read, merge } = c;
  c.read = c.merge = async () => {
    throw Error("offline");
  };
  await v.put("children", "a", { id: "a", name: "수정", group_name: "햇살" });
  await phone.sync();
  phone.close();
  const r = await v.get("rosterVersions", "children/a");
  assert.equal(r.dirty, true);
  c.read = read;
  c.merge = merge;
  const restored = new AccountRoster(v, c);
  await restored.init();
  assert.equal(c.rows.children.a.name, "수정");
  assert.equal((await v.get("rosterVersions", "children/a")).dirty, false);
  const other = new Vault(crypto.randomUUID()),
    pc = new AccountRoster(other, c);
  await pc.init();
  await Promise.all([
    v.put("children", "a", { id: "a", name: "최신", group_name: "해" }),
    other.put("children", "b", { id: "b", name: "둘", group_name: "달" }),
  ]);
  await Promise.all([restored.sync(), pc.sync()]);
  await restored.sync();
  assert.deepEqual(
    (await v.all("children")).map((k) => k.name).sort(),
    ["둘", "최신"].sort(),
  );
  await other.put("references", "r", { id: "r", child: "a", active: false });
  await pc.sync();
  assert.equal(c.rows.references.r.removed, true);
  assert.equal(c.rows.references.r.vector, undefined);
});
test("a stale response cannot clear or overwrite a new local edit", async () => {
  const v = new Vault(crypto.randomUUID());
  v.trackRoster = true;
  const save = (name) =>
    v.put("children", "a", { id: "a", name, group_name: "반" });
  await save("이전");
  const old = await v.get("rosterVersions", "children/a");
  await save("새 이름");
  assert.equal(
    await v.putMany([{ table: "children", id: "a", remove: true }], {
      remote: true,
      ifStamp: { key: "children/a", rev: old.rev },
    }),
    false,
  );
  assert.equal((await v.get("children", "a")).name, "새 이름");
  assert.equal((await v.get("rosterVersions", "children/a")).dirty, true);
});
