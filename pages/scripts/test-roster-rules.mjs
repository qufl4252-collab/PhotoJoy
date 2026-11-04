import assert from "node:assert/strict";
import { initializeApp, deleteApp } from "firebase/app";
import {
  getDatabase,
  connectDatabaseEmulator,
  ref,
  get,
  set,
  goOffline,
} from "firebase/database";
import { accountCloud } from "../src/roster-cloud.js";
import { AccountRoster } from "../src/account-roster.js";
import { Vault } from "../src/vault.js";
import "fake-indexeddb/auto";

const apps = [];
function client(name, uid) {
  const app = initializeApp(
    {
      projectId: "demo-photojoy",
      databaseURL: "https://demo-photojoy-default-rtdb.firebaseio.com",
    },
    name,
  );
  const db = getDatabase(app);
  connectDatabaseEmulator(
    db,
    "127.0.0.1",
    9000,
    uid ? { mockUserToken: { sub: uid } } : {},
  );
  apps.push({ app, db });
  return db;
}
const dbA = client("phone", "teacherA"),
  dbB = client("visitor", "teacherB"),
  guest = client("guest"),
  pc = client("pc", "teacherA");
const row = {
  rev: "001800000000000-00000000-0000-4000-8000-000000000001",
  name: "테스트",
  group: "연두반",
};
try {
  const path = "rosters/teacherA/children/test";
  await set(ref(dbA, path), row);
  assert.equal((await get(ref(dbA, path))).val().name, "테스트");
  for (const outsider of [dbB, guest]) {
    await assert.rejects(get(ref(outsider, "rosters/teacherA")));
    await assert.rejects(set(ref(outsider, path), row));
    await assert.rejects(get(ref(outsider, "rosters")));
  }
  await assert.rejects(
    set(ref(dbA, path), { ...row, original: "not-allowed" }),
  );
  await assert.rejects(
    set(ref(dbA, "rosters/teacherA/originals/file"), "not-allowed"),
  );
  const phoneVault = new Vault("phone-cache"),
    pcVault = new Vault("pc-cache");
  // The two emulated app instances have independent caches and identical authenticated UIDs.
  const cloud = (db) => accountCloud({ owner: "teacherA", check() {} }, db);
  const phone = new AccountRoster(phoneVault, cloud(dbA)),
    desktop = new AccountRoster(pcVault, cloud(pc));
  await phone.init();
  const vector = Array.from({ length: 128 }, (_, i) => +(i === 0));
  await phoneVault.putMany([
    {
      table: "children",
      id: "child",
      value: { id: "child", name: "아이", group_name: "반" },
    },
    {
      table: "crops",
      id: "face",
      value: new Blob(["selected-crop"], { type: "image/jpeg" }),
    },
    {
      table: "references",
      id: "ref",
      value: { id: "ref", child: "child", cropId: "face", embedding: vector },
    },
  ]);
  await phone.sync();
  await desktop.init();
  assert.equal((await pcVault.get("children", "child")).name, "아이");
  const restored = await pcVault.get("references", "ref");
  assert.deepEqual(restored.embedding, vector);
  assert.equal(
    await (await pcVault.get("crops", restored.cropId)).text(),
    "selected-crop",
  );
  await assert.rejects(get(ref(dbB, "rosters/teacherA/references/ref")));
  await phoneVault.put("references", "ref", {
    ...(await phoneVault.get("references", "ref")),
    active: false,
  });
  await phone.sync();
  await desktop.sync();
  assert.equal(await pcVault.get("references", "ref"), undefined);
  assert.equal(
    (await get(ref(dbA, "rosters/teacherA/references/ref/image"))).val(),
    null,
  );
  console.log(
    "Owner read/write, two devices, restored face crop/embedding, retirement, field limits and guest/other-account denial passed.",
  );
} finally {
  for (const { app, db } of apps) {
    goOffline(db);
    await deleteApp(app);
  }
}
