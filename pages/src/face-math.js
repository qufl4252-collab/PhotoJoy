// Model decoding and alignment equations implemented for browser canvases.
export const LANDMARK_TARGETS = [
  [38.2946, 51.6963],
  [73.5318, 51.5014],
  [56.0252, 71.7366],
  [41.5493, 92.3655],
  [70.7299, 92.2041],
];
export function normalize(values) {
  const norm = Math.hypot(...values);
  if (!Number.isFinite(norm) || norm < 1e-8)
    throw new Error("얼굴 특징을 읽을 수 없습니다.");
  return Float32Array.from(values, (v) => v / norm);
}
export function compare(query, references, threshold = 0.5, margin = 0.08) {
  const q = normalize(query),
    scores = [];
  for (const [child, vectors] of Object.entries(references)) {
    const values = vectors
      .filter((v) => v.length === q.length)
      .map((v) => normalize(v).reduce((sum, n, i) => sum + n * q[i], 0))
      .sort((a, b) => b - a)
      .slice(0, 3);
    if (values.length) scores.push([child, referenceScore(values)]);
  }
  scores.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (!scores.length)
    return {
      child: null,
      score: null,
      runner_up: null,
      accepted: false,
      reason: "등록된 참고 얼굴 없음",
    };
  const [child, score] = scores[0],
    runner = scores[1]?.[1] ?? null;
  const accepted =
    score >= threshold + (runner === null ? 0.08 : 0) &&
    (runner === null || score - runner >= margin);
  return {
    child,
    score: Math.min(1, score),
    runner_up: runner,
    accepted,
    reason: accepted
      ? "사진 속 아이를 확인해 주세요"
      : "유사도 부족 또는 후보가 비슷함",
  };
}
// Multiple views should support a strong match instead of averaging it away.
// The runner-up margin, quality gate and empirical calibration still apply.
export function referenceScore(scores) {
  const top = [...scores].sort((a, b) => b - a).slice(0, 3);
  return top.length
    ? 0.8 * top[0] + (0.2 * top.reduce((a, b) => a + b, 0)) / top.length
    : 0;
}
export function similarityTransform(source, target = LANDMARK_TARGETS) {
  if (source.length !== target.length || source.length < 2)
    throw new Error("얼굴 정렬 기준점이 올바르지 않습니다.");
  const n = source.length,
    mean = (p) => [
      p.reduce((s, v) => s + v[0], 0) / n,
      p.reduce((s, v) => s + v[1], 0) / n,
    ];
  const s = mean(source),
    t = mean(target);
  let dot = 0,
    cross = 0,
    energy = 0;
  for (let i = 0; i < n; i++) {
    const x = source[i][0] - s[0],
      y = source[i][1] - s[1],
      u = target[i][0] - t[0],
      v = target[i][1] - t[1];
    dot += x * u + y * v;
    cross += x * v - y * u;
    energy += x * x + y * y;
  }
  if (!Number.isFinite(energy) || energy < 1e-8)
    throw new Error("얼굴을 정렬할 수 없습니다.");
  const a = dot / energy,
    b = cross / energy;
  return [a, b, -b, a, t[0] - a * s[0] + b * s[1], t[1] - b * s[0] - a * s[1]];
}
export function iou(a, b) {
  const intersection =
    Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) *
    Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  const union =
    (a[2] - a[0]) * (a[3] - a[1]) +
    (b[2] - b[0]) * (b[3] - b[1]) -
    intersection;
  return union > 0 ? intersection / union : 0;
}
export function decodeYunet(outputs, width = 640, threshold = 0.85) {
  const proposals = [];
  for (const stride of [8, 16, 32]) {
    const cls = outputs[`cls_${stride}`].data,
      obj = outputs[`obj_${stride}`].data,
      boxes = outputs[`bbox_${stride}`].data,
      points = outputs[`kps_${stride}`].data;
    const cols = width / stride;
    for (let i = 0; i < cls.length; i++) {
      const score = Math.sqrt(
        Math.max(0, Math.min(1, cls[i])) * Math.max(0, Math.min(1, obj[i])),
      );
      if (score < threshold) continue;
      const x = i % cols,
        y = Math.floor(i / cols),
        cx = (x + boxes[i * 4]) * stride,
        cy = (y + boxes[i * 4 + 1]) * stride;
      const w = Math.exp(boxes[i * 4 + 2]) * stride,
        h = Math.exp(boxes[i * 4 + 3]) * stride;
      const landmarks = Array.from({ length: 5 }, (_, p) => [
        (points[i * 10 + p * 2] + x) * stride,
        (points[i * 10 + p * 2 + 1] + y) * stride,
      ]);
      proposals.push({
        score,
        bbox: [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2],
        landmarks,
      });
    }
  }
  proposals.sort((a, b) => b.score - a.score);
  const selected = [];
  for (const face of proposals.slice(0, 5000))
    if (selected.every((other) => iou(face.bbox, other.bbox) <= 0.3)) {
      selected.push(face);
      if (selected.length === 100) break;
    }
  return selected;
}
