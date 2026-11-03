import { compare, normalize, referenceScore } from "./face-math.js";
export const DEFAULT_SETTINGS = {
  sensitivity: "balanced",
  unit: "week",
  minFacePixels: 32,
  minRelative: 0,
  detectorThreshold: 0.75,
};
export const STATES = {
  queued: "대기 중",
  analyzing: "분석 중",
  classified: "자동 분류 완료",
  review: "확인 필요",
  duplicate: "중복",
  failed: "처리 실패",
  organized: "정리 완료",
  excluded: "제외",
};
const percentile = (values, p) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor((sorted.length - 1) * p)];
};
const dot = (a, b) => {
  const right = normalize(b);
  return normalize(a).reduce((sum, v, i) => sum + v * right[i], 0);
};
// Reference-only calibration: leave-one-out matches and cross-person impostors.
// This measures the supplied references, not general child recognition accuracy.
export function calibration(gallery, sensitivity = "balanced") {
  const entries = Object.entries(gallery).filter(([, v]) => v.length >= 3),
    positive = [],
    negative = [];
  const base = {
    bold: { threshold: 0.45, margin: 0.06 },
    balanced: { threshold: 0.5, margin: 0.08 },
    careful: { threshold: 0.58, margin: 0.12 },
  }[sensitivity] || { threshold: 0.5, margin: 0.08 };
  if (entries.length >= 2) {
    for (const [id, vectors] of entries)
      for (let i = 0; i < vectors.length; i++) {
        const own = vectors
          .filter((_, j) => j !== i)
          .map((v) => dot(vectors[i], v))
          .sort((a, b) => b - a)
          .slice(0, 3);
        positive.push(referenceScore(own));
        for (const [other, refs] of entries)
          if (other !== id) {
            const scores = refs
              .map((v) => dot(vectors[i], v))
              .sort((a, b) => b - a)
              .slice(0, 3);
            negative.push(referenceScore(scores));
          }
      }
  }
  if (!negative.length)
    return {
      ...base,
      calibrated: false,
      positive: 0,
      negative: 0,
      note: "검증 자료 부족: 보수적인 실험 초기값 사용. 아이 2명 이상, 각 3장 이상의 서로 다른 참고 얼굴을 등록하세요.",
    };
  const floor =
    percentile(negative, sensitivity === "bold" ? 0.98 : 1) +
    ({ bold: 0.02, balanced: 0.04, careful: 0.08 }[sensitivity] || 0.04);
  const threshold = Math.min(0.99, Math.max(base.threshold, floor));
  return {
    ...base,
    threshold,
    calibrated: true,
    positive: positive.length,
    negative: negative.length,
    referenceRecall:
      positive.filter((v) => v >= threshold).length / positive.length,
    note: "등록한 참고 얼굴의 교차 비교로 보정함. 현장 사진 정확도나 신원 일치 확률이 아닙니다.",
  };
}
export function classify(faces, gallery, settings = DEFAULT_SETTINGS) {
  settings = { ...DEFAULT_SETTINGS, ...settings };
  const policy = calibration(gallery, settings.sensitivity);
  const largest = Math.max(1, ...faces.map((f) => f.pixelSize || 0));
  const evaluated = faces.map((face) => {
    if (face.manualChild)
      return {
        ...face,
        candidate: {
          child: face.manualChild,
          accepted: true,
          score: null,
          reason: "사용자가 얼굴을 교정함",
        },
        ignored: false,
      };
    if (face.manualIgnored)
      return {
        ...face,
        ignored: true,
        candidate: {
          child: null,
          accepted: false,
          score: null,
          reason: "사용자가 미등록 인물로 제외함",
        },
      };
    const ignored =
      settings.minRelative > 0 &&
      (face.pixelSize || 0) / largest < settings.minRelative;
    let candidate = face.embedding?.length
      ? compare(face.embedding, gallery, policy.threshold, policy.margin)
      : {
          child: null,
          score: null,
          accepted: false,
          reason: face.embeddingError || "얼굴 특징 추출 실패",
        };
    const poor =
      (face.pixelSize ?? (face.small ? 0 : 100)) < settings.minFacePixels ||
      face.quality?.usable === false;
    if (poor)
      candidate = {
        ...candidate,
        accepted: false,
        reason: "얼굴 크기·선명도·밝기 부족",
      };
    if (ignored)
      candidate = {
        ...candidate,
        accepted: false,
        reason: "설정한 상대 크기보다 작은 얼굴: 제외",
      };
    return { ...face, ignored, candidate };
  });
  const children = [
    ...new Set(
      evaluated
        .filter((f) => !f.ignored && f.candidate.accepted)
        .map((f) => f.candidate.child),
    ),
  ];
  const unresolved = evaluated.filter(
    (f) => !f.ignored && !f.candidate.accepted,
  ).length;
  const needsReview = unresolved > 0 || !children.length;
  return {
    faces: evaluated,
    children,
    needsReview,
    unresolved,
    state: needsReview ? "review" : "classified",
    policy,
    reason: !faces.length
      ? "얼굴 검출 없음"
      : !children.length
        ? "등록된 아이를 확정할 수 없음"
        : unresolved
          ? "일부 얼굴 확인 필요"
          : "",
  };
}
export function dateFolder(date, unit = "week") {
  if (unit === "day") return date;
  const [year, month, day] = date.split("-").map(Number);
  // Month-contained weeks: 1–7, 8–14, ...; deterministic across time zones.
  return `${String(year).slice(-2)}-${String(month).padStart(2, "0")}월${Math.ceil(day / 7)}주차`;
}
export function safeName(name) {
  return (
    String(name)
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
      .replace(/^\.+|[ .]+$/g, "")
      .slice(0, 100) || "사진"
  );
}
export function organizedPaths(media, kids, unit) {
  return media.children.map(
    (id) =>
      `${safeName(kids.find((c) => c.id === id)?.name || "미등록")}_${id.slice(0, 6)}/${dateFolder(media.captured, unit)}/${media.hash.slice(0, 12)}_${safeName(media.name)}`,
  );
}
export function summarize(items) {
  const counts = Object.fromEntries(Object.keys(STATES).map((s) => [s, 0]));
  for (const item of items)
    counts[item.state in counts ? item.state : "failed"]++;
  return {
    ...counts,
    total: items.length,
    finished: items.filter(
      (i) => !["queued", "analyzing", "classified"].includes(i.state),
    ).length,
  };
}
export async function sequentialQueue(
  items,
  process,
  onChange = () => {},
  shouldStop = () => false,
) {
  for (const item of items) {
    if (shouldStop()) break;
    if (item.state !== "queued") continue;
    item.state = "analyzing";
    await onChange(item);
    try {
      const result = await process(item);
      Object.assign(item, result);
    } catch (error) {
      item.state = "failed";
      item.error = error.message;
    }
    await onChange(item);
  }
}
