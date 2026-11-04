const requestResult = (request) =>
  new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
let opened;
function database() {
  if (!opened)
    opened = new Promise((resolve, reject) => {
      const request = indexedDB.open("PhotoJoy-v1", 1);
      request.onupgradeneeded = () => {
        const store = request.result.createObjectStore("records", {
          keyPath: "key",
        });
        store.createIndex("ownerTable", ["owner", "table"]);
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  return opened;
}
export class Vault {
  constructor(owner, guard = () => true) {
    if (!owner) throw new Error("로그인이 필요해요.");
    this.owner = owner;
    this.guard = guard;
  }
  check() {
    if (!this.guard())
      throw new Error("로그인이 바뀌었습니다. 다시 시도해 주세요.");
  }
  async get(table, id) {
    this.check();
    const db = await database();
    const row = await requestResult(
      db
        .transaction("records")
        .objectStore("records")
        .get([this.owner, table, id]),
    );
    this.check();
    return row?.value;
  }
  async all(table) {
    this.check();
    const db = await database();
    const rows = await requestResult(
      db
        .transaction("records")
        .objectStore("records")
        .index("ownerTable")
        .getAll([this.owner, table]),
    );
    this.check();
    return rows.map((r) => r.value);
  }
  async put(table, id, value) {
    return this.putMany([{ table, id, value }]);
  }
  async entries(table) {
    this.check();
    const db = await database();
    const rows = await requestResult(
      db
        .transaction("records")
        .objectStore("records")
        .index("ownerTable")
        .getAll([this.owner, table]),
    );
    this.check();
    return rows.map((r) => ({ id: r.key[2], value: r.value }));
  }
  async remove(table, id) {
    return this.putMany([{ table, id, remove: true }]);
  }
  async putMany(entries, { remote = false, ifStamp } = {}) {
    this.check();
    const db = await database();
    this.check();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("records", "readwrite");
      const records = tx.objectStore("records");
      let applied = false,
        rosterChanged = false;
      const put = (table, id, value) =>
        records.put({
          key: [this.owner, table, id],
          owner: this.owner,
          table,
          value,
        });
      const write = () => {
        applied = true;
        const changes = new Map();
        for (const { table, id, value, remove } of entries) {
          if (remove) records.delete([this.owner, table, id]);
          else put(table, id, value);
          if (
            this.trackRoster &&
            !remote &&
            (table === "children" || table === "references")
          )
            changes.set(table + "/" + id, { table, id, removed: !!remove });
        }
        for (const [key, change] of changes) {
          rosterChanged = true;
          const request = records.get([this.owner, "rosterVersions", key]);
          request.onsuccess = () => {
            const previous = Number(
              request.result?.value.rev.split("-")[0] || 0,
            );
            const rev =
              String(Math.max(Date.now(), previous + 1)).padStart(15, "0") +
              "-" +
              crypto.randomUUID();
            put("rosterVersions", key, { ...change, rev, dirty: true });
          };
        }
      };
      if (ifStamp) {
        const request = records.get([
          this.owner,
          "rosterVersions",
          ifStamp.key,
        ]);
        request.onsuccess = () => {
          if ((request.result?.value.rev ?? null) === ifStamp.rev) write();
        };
      } else write();
      tx.oncomplete = () => {
        try {
          this.check();
          if (rosterChanged) this.onRosterWrite?.();
          resolve(applied);
        } catch (error) {
          reject(error);
        }
      };
      tx.onerror = () =>
        reject(
          new Error(
            "브라우저 저장 공간이 부족하거나 저장할 수 없어요. 원본을 보관하고 공간을 확인해 주세요.",
          ),
        );
      tx.onabort = tx.onerror;
    });
  }
}
