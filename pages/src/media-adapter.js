import exifr from "exifr";
import { analyzeFrame, asBlob, readFrames } from "./face-engine.js";
export async function analyzeFile(file, settings) {
  const entries = [],
    faces = [],
    diagnostics = [];
  let previewId;
  await readFrames(file, async (frame, time) => {
    const id = crypto.randomUUID();
    previewId ??= id;
    entries.push({ table: "previews", id, value: await asBlob(frame) });
    const result = await analyzeFrame(frame, settings);
    diagnostics.push({ frame: time, ...result.diagnostics });
    for (const face of result.faces) {
      entries.push({ table: "crops", id: face.id, value: face.crop });
      delete face.crop;
      faces.push({ ...face, previewId: id, frame: time });
    }
  });
  return { entries, faces, previewId, diagnostics };
}
const format = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
export async function captureDate(file) {
  try {
    const exif = await exifr.parse(file, ["DateTimeOriginal", "CreateDate"]);
    const date = exif?.DateTimeOriginal || exif?.CreateDate;
    if (date instanceof Date && !isNaN(date))
      return { captured: format(date), date_source: "EXIF 촬영일" };
  } catch {}
  const match = file.name.match(
    /((?:19|20)\d{2})[-_.]?([01]\d)[-_.]?([0-3]\d)/,
  );
  if (match) {
    const d = new Date(+match[1], +match[2] - 1, +match[3]);
    if (d.getMonth() === +match[2] - 1 && d.getDate() === +match[3])
      return { captured: format(d), date_source: "파일명" };
  }
  return {
    captured: format(new Date(file.lastModified || Date.now())),
    date_source: "파일 수정 시각",
  };
}
