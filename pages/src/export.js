import { zipSync } from "fflate";
import { safeName, dateFolder } from "./classification.js";
const cell = (value) =>
  '"' +
  String(value ?? "")
    .replace(/^[=+@\-\t\r]/, "'$&")
    .replaceAll('"', '""') +
  '"';
export const csv = (rows) =>
  "\uFEFF" + rows.map((r) => r.map(cell).join(",")).join("\r\n");
export function statistics(kids, media) {
  return kids.map((k) => {
    const own = media.filter(
      (m) =>
        m.children.includes(k.id) && !m.deletedAt && m.state !== "excluded",
    );
    return {
      ...k,
      photos: own.filter((m) => m.kind === "photo").length,
      videos: own.filter((m) => m.kind === "video").length,
      total: own.length,
    };
  });
}
export async function makeExports(
  project,
  { children = [], start = "0001-01-01", end = "9999-12-31", all = false },
) {
  if (start > end) throw new Error("기간을 확인하세요.");
  const kids = await project.kids(),
    media = (await project.media()).filter(
      (m) => m.captured >= start && m.captured <= end,
    ),
    settings = await project.settings();
  const targets = all
      ? [{ id: "all", name: "전체 정리" }]
      : kids.filter((k) => children.includes(k.id)),
    results = [];
  for (const target of targets) {
    let files = {},
      size = 0,
      part = 1,
      count = 0;
    const flush = async () => {
      if (!count) return;
      const id = crypto.randomUUID(),
        name = `${safeName(target.name)}_${start}_${end}_${part++}.zip`,
        record = {
          id,
          name,
          count,
          created: Date.now(),
          child: target.id,
          start,
          end,
          sentAt: null,
        };
      files["분류기록/안내.txt"] = new TextEncoder().encode(
        "PhotoJoy: 원본은 변환하지 않고 복사합니다. 자동 정리는 신원 일치 보증이 아닙니다. ZIP 생성은 발송 완료가 아닙니다. 주차: 매월 1~7일 1주차, 8~14일 2주차.",
      );
      files["분류기록/분류.csv"] = new TextEncoder().encode(
        csv([
          ["파일명", "촬영일", "상태", "배정 아이", "보류 얼굴"],
          ...media
            .filter(
              (m) => target.id === "all" || m.children.includes(target.id),
            )
            .map((m) => [
              m.name,
              m.captured,
              m.state,
              target.id === "all"
                ? m.children
                    .map((id) => kids.find((k) => k.id === id)?.name || id)
                    .join(" / ")
                : target.name,
              m.unresolved || 0,
            ]),
        ]),
      );
      await project.v.putMany([
        {
          table: "exportBlobs",
          id,
          value: new Blob([zipSync(files, { level: 0 })], {
            type: "application/zip",
          }),
        },
        { table: "exports", id, value: record },
      ]);
      results.push(record);
      files = {};
      size = 0;
      count = 0;
    };
    for (const m of media) {
      let paths = [];
      if (target.id === "all") {
        paths = m.paths || [];
        if (m.needsReview || m.state === "failed")
          paths = [
            ...paths,
            `보류/${dateFolder(m.captured, settings.unit)}/${m.hash.slice(0, 12)}_${safeName(m.name)}`,
          ];
      } else if (m.children.includes(target.id) && m.state !== "excluded")
        paths = [
          `${dateFolder(m.captured, settings.unit)}/${m.hash.slice(0, 12)}_${safeName(m.name)}`,
        ];
      if (!paths.length) continue;
      const blob = await project.v.get("originals", m.id);
      if (!blob) throw new Error("보관한 원본이 없습니다.");
      const bytes = new Uint8Array(await blob.arrayBuffer());
      for (const path of paths) {
        if (count && size + bytes.length > 64 * 1024 * 1024) await flush();
        files[path] = bytes;
        size += bytes.length;
        count++;
      }
    }
    await flush();
  }
  return results;
}
