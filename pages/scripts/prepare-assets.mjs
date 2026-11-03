import { readFile, mkdir, copyFile, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";
const root = fileURLToPath(new URL("../", import.meta.url));
const project = path.dirname(root);
const manifest = JSON.parse(
  await readFile(path.join(project, "models/manifest.json"), "utf8"),
);
for (const name of ["models", "ort", "licenses"])
  await mkdir(path.join(root, "public", name), { recursive: true });
for (const model of manifest.models) {
  let bytes;
  try {
    bytes = await readFile(path.join(project, "models", model.file));
  } catch {}
  if (
    !bytes ||
    createHash("sha256").update(bytes).digest("hex") !== model.sha256
  ) {
    const response = await fetch(model.url);
    if (!response.ok)
      throw new Error(`Model download failed: ${response.status}`);
    bytes = Buffer.from(await response.arrayBuffer());
  }
  if (
    bytes.length !== model.bytes ||
    createHash("sha256").update(bytes).digest("hex") !== model.sha256
  )
    throw new Error(`Model checksum mismatch: ${model.file}`);
  await writeFile(path.join(root, "public/models", model.file), bytes);
  console.log("Verified model:", model.file);
}
await writeFile(
  path.join(root, "public/models/manifest.json"),
  JSON.stringify(manifest),
);
for (const name of [
  "ort-wasm-simd-threaded.wasm",
  "ort-wasm-simd-threaded.mjs",
])
  await copyFile(
    path.join(root, "node_modules/onnxruntime-web/dist", name),
    path.join(root, "public/ort", name),
  );
for (const name of ["YuNet-MIT.txt", "SFace-Apache-2.0.txt"])
  await copyFile(
    path.join(project, "licenses", name),
    path.join(root, "public/licenses", name),
  );
for (const name of [
  "Firebase-Apache-2.0.txt",
  "ONNXRuntime-MIT.txt",
  "ONNXRuntime-ThirdPartyNotices.txt",
])
  await copyFile(
    path.join(project, "licenses", name),
    path.join(root, "public/licenses", name),
  );
for (const name of ["fflate", "exifr", "heic-to"])
  await copyFile(
    path.join(root, "node_modules", name, "LICENSE"),
    path.join(root, "public/licenses", `${name}-LICENSE.txt`),
  );
await copyFile(
  path.join(project, "THIRD_PARTY_PAGES.md"),
  path.join(root, "public/licenses/README.md"),
);
await writeFile(path.join(root, "public/.nojekyll"), "");
