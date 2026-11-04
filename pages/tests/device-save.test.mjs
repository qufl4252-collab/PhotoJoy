import test from "node:test";
import assert from "node:assert/strict";
import {
  deviceItems,
  readDeviceBatch,
  supportsFileShare,
} from "../src/device-save.js";

const kids = [
  { id: "a", name: "하늘" },
  { id: "b", name: "서연" },
];
const photo = (id, extra = {}) => ({
  id,
  name: "소풍.HEIC",
  children: ["a", "b"],
  state: "organized",
  captured: "2026-11-01",
  created: 100,
  ...extra,
});
test("device export uses only requested children, dates and selections, sharing a group photo once", () => {
  const media = [
    photo("group", { state: "review" }),
    photo("other", { children: ["b"] }),
    photo("deleted", { deletedAt: 1 }),
    photo("excluded", { state: "excluded" }),
    photo("unselected"),
    photo("old", { captured: "2025-11-01" }),
    photo("pending", { state: "queued" }),
  ];
  const options = {
    children: ["a"],
    ids: new Set(["group", "deleted", "excluded", "old", "other", "pending"]),
    start: "2026-11-01",
    end: "2026-11-01",
  };
  const items = deviceItems(media, kids, options);
  assert.deepEqual(
    items.map((i) => [i.media.id, i.prefix]),
    [["group", "하늘"]],
  );
  assert.equal(
    deviceItems([media[0]], kids, { children: ["b", "a"] }).length,
    1,
  );
  assert.throws(() => deviceItems(media, kids, { children: [] }), /아이/);
});
test("legacy untyped blobs become timestamped original files with a shareable MIME and unique Korean names", async () => {
  const items = deviceItems([photo("1"), photo("2")], kids, {
    children: ["a"],
  });
  const bytes = Uint8Array.of(0, 255, 39, 42);
  const vault = {
    get: async (table) => {
      assert.equal(table, "originals");
      return new Blob([bytes]);
    },
  };
  const { files } = await readDeviceBatch(vault, items, 0);
  assert.equal(new Set(files.map((f) => f.name)).size, 2);
  for (const f of files) {
    assert.match(f.name, /^하늘_.*\.HEIC$/);
    assert.equal(f.type, "image/heic");
    assert.equal(f.lastModified, 100);
    assert.deepEqual(new Uint8Array(await f.arrayBuffer()), bytes);
  }
});
test("large libraries prepare bounded batches without dropping originals, including an oversized file", async () => {
  const items = Array.from({ length: 13 }, (_, i) => ({
    media: photo(String(i)),
    prefix: "하늘",
  }));
  const large = new Blob([new Uint8Array(33 * 1024 * 1024)]);
  const vault = {
    get: async (_, id) =>
      id === "0" ? large : id === "2" ? null : new Blob([id]),
  };
  const first = await readDeviceBatch(vault, items, 0),
    second = await readDeviceBatch(vault, items, first.end),
    last = await readDeviceBatch(vault, items, second.end);
  assert.deepEqual([first.end, second.end, last.end], [1, 11, 13]);
  assert.equal(first.files[0].size, large.size);
  assert.equal(second.missing.length, 1);
  assert.equal(
    first.files.length + second.files.length + last.files.length,
    12,
  );
});
test("file sharing capability checks the actual files and handles browsers without file sharing", () => {
  const files = [new File(["sample"], "test.jpg", { type: "image/jpeg" })];
  assert.equal(supportsFileShare({}, files), false);
  assert.equal(
    supportsFileShare(
      {
        share() {},
        canShare() {
          throw Error();
        },
      },
      files,
    ),
    false,
  );
  assert.equal(
    supportsFileShare(
      {
        share() {},
        canShare(data) {
          return data.files === files;
        },
      },
      files,
    ),
    true,
  );
});
