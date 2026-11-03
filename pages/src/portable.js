import { unzipSync } from "fflate";
import { sha256 } from "./project.js";
const allowed = new Set([
  "children",
  "references",
  "media",
  "originals",
  "crops",
  "previews",
  "referenceSources",
]);
const validId = (id) =>
  typeof id === "string" &&
  id.length <= 300 &&
  /^[a-zA-Z0-9:_-]+$/.test(id) &&
  !["__proto__", "constructor", "prototype"].includes(id);
export async function importPortable(project, files) {
  project.assertIdle();
  if (!files.length) return 0;
  // Validate all selected parts before changing any records.
  const parts = [];
  for (const file of files) {
    if (file.size > 256 * 1024 * 1024)
      throw new Error("백업 파일은 분할본 기준 256MB 이하로 선택하세요.");
    const list = unzipSync(new Uint8Array(await file.arrayBuffer()), {
      filter: (e) =>
        e.name === "manifest.json" && e.originalSize <= 32 * 1024 * 1024,
    });
    if (!list["manifest.json"])
      throw new Error("PhotoJoy 백업 목록이 없습니다.");
    const m = JSON.parse(new TextDecoder().decode(list["manifest.json"]));
    if (
      m.format !== "PhotoJoy-portable-v1" ||
      m.model !== "YuNet-2023mar/SFace-2021dec" ||
      !Array.isArray(m.records)
    )
      throw new Error("지원하지 않는 PhotoJoy 백업 형식입니다.");
    parts.push(m);
  }
  const expected = parts[0].parts;
  if (
    !Number.isInteger(expected) ||
    parts.length !== expected ||
    new Set(parts.map((m) => m.part)).size !== expected ||
    parts.some(
      (m) =>
        m.parts !== expected ||
        m.created !== parts[0].created ||
        m.part < 1 ||
        m.part > expected,
    )
  )
    throw new Error("같은 백업의 분할 ZIP 파일을 모두 한 번씩 선택해 주세요.");
  const existingMedia = await project.v.all("media");
  for (const m of parts)
    for (const row of m.records) {
      if (
        row.table === "media" &&
        existingMedia.some(
          (old) => old.hash === row.value?.hash && old.id !== row.id,
        )
      )
        throw new Error(
          "다른 ID로 같은 원본이 이미 있습니다. 기존 자료를 보존하기 위해 가져오기를 중단했습니다.",
        );
    }
  const backup = await project.backup("기존 자료 가져오기 전");
  let count = 0;
  try {
    for (const file of files) {
      if (file.size > 256 * 1024 * 1024)
        throw new Error("백업 파일은 분할본 기준 256MB 이하로 선택하세요.");
      let total = 0;
      const zip = unzipSync(new Uint8Array(await file.arrayBuffer()), {
        filter: (entry) => {
          total += entry.originalSize;
          if (total > 300 * 1024 * 1024)
            throw new Error("백업 압축 해제 한도를 초과했습니다.");
          return true;
        },
      });
      if (
        !zip["manifest.json"] ||
        zip["manifest.json"].length > 32 * 1024 * 1024
      )
        throw new Error("PhotoJoy 백업 목록이 없습니다.");
      const manifest = JSON.parse(
        new TextDecoder().decode(zip["manifest.json"]),
      );
      if (
        manifest.format !== "PhotoJoy-portable-v1" ||
        manifest.model !== "YuNet-2023mar/SFace-2021dec" ||
        !Array.isArray(manifest.records)
      )
        throw new Error("지원하지 않는 PhotoJoy 백업 형식입니다.");
      const entries = [];
      for (const row of manifest.records) {
        if (!allowed.has(row.table) || !validId(row.id))
          throw new Error("백업 항목이 올바르지 않습니다.");
        if (row.blob) {
          const bytes = zip[row.blob];
          if (!bytes) throw new Error("백업 원본이 누락되었습니다.");
          const blob =
            row.table === "originals"
              ? new File([bytes], row.name || "photo", {
                  type: row.type,
                  lastModified: row.lastModified,
                })
              : new Blob([bytes], { type: row.type });
          if (row.table === "originals") {
            const media = manifest.records.find(
              (r) => r.table === "media" && r.id === row.id,
            )?.value;
            if (!media || (await sha256(blob)) !== media.hash)
              throw new Error("백업 원본의 해시가 일치하지 않습니다.");
          }
          entries.push({ table: row.table, id: row.id, value: blob });
        } else {
          if (
            !row.value ||
            typeof row.value !== "object" ||
            (row.value.id && row.value.id !== row.id)
          )
            throw new Error("백업 메타데이터 오류");
          if (
            row.table === "children" &&
            (!validId(row.value.id) || typeof row.value.name !== "string")
          )
            throw new Error("아이 정보 오류");
          if (
            row.table === "media" &&
            (!validId(row.value.id) ||
              typeof row.value.name !== "string" ||
              !/^[a-f0-9]{64}$/.test(row.value.hash) ||
              !Array.isArray(row.value.children) ||
              row.value.children.some((id) => !validId(id)) ||
              !Array.isArray(row.value.faces) ||
              row.value.faces.some(
                (f) =>
                  !validId(f.id) ||
                  !Array.isArray(f.bbox) ||
                  f.bbox.length !== 4 ||
                  f.bbox.some((n) => !Number.isFinite(n) || n < 0 || n > 1),
              ))
          )
            throw new Error("사진 정보 오류");
          if (row.table === "references" && !validId(row.value.child))
            throw new Error("참고 얼굴 아이 정보 오류");
          if (
            row.table === "references" &&
            (!Array.isArray(row.value.embedding) ||
              row.value.embedding.length !== 128 ||
              row.value.embedding.some((n) => !Number.isFinite(n)))
          )
            throw new Error("참고 얼굴 모델이 호환되지 않습니다.");
          const old = await project.v.get(row.table, row.id);
          if (row.table === "media" && old && old.hash !== row.value.hash)
            throw new Error(
              "같은 ID의 다른 원본이 있습니다. 가져오기를 중단했습니다.",
            );
          entries.push({ table: row.table, id: row.id, value: row.value });
        }
      }
      entries.push({ table: "settings", id: "schema", value: 5 });
      await project.v.putMany(entries);
      count++;
    }
    await project.reorganize();
    await project.rematch();
    return count;
  } catch (error) {
    await project.restore(backup.id);
    throw error;
  }
}
