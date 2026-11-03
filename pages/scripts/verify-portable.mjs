// Local-only verification: uses an in-memory IndexedDB, never prints names or embeddings.
import "fake-indexeddb/auto";
import { readFile } from "node:fs/promises";
import { Vault } from "../src/vault.js";
import { Project, sha256 } from "../src/project.js";
import { importPortable } from "../src/portable.js";
const files = [];
for (const name of process.argv.slice(2))
  files.push(new File([await readFile(name)], "backup.zip"));
if (!files.length)
  throw new Error("Pass every portable ZIP part as arguments.");
const p = await new Project(
  new Vault(crypto.randomUUID()),
  async () => {},
  async () => {},
).init();
await importPortable(p, files);
const media = await p.media();
let verified = 0;
for (const m of media) {
  const blob = await p.v.get("originals", m.id);
  if (!blob || (await sha256(blob)) !== m.hash)
    throw new Error("Original missing or changed");
  verified++;
}
console.log(
  JSON.stringify(
    {
      children: (await p.kids()).length,
      references: (await p.refs()).length,
      media: media.length,
      originalHashesVerified: verified,
      historyEntries: media.reduce((n, m) => n + (m.history?.length || 0), 0),
      counts: (await p.snapshot()).counts,
    },
    null,
    2,
  ),
);
