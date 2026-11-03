import * as ort from "onnxruntime-web/wasm";
import {
  decodeYunet,
  normalize,
  similarityTransform,
  iou,
} from "./face-math.js";
ort.env.wasm.numThreads = 1;
ort.env.wasm.wasmPaths = new URL(
  `${import.meta.env.BASE_URL}ort/`,
  self.location.origin,
).href;
ort.env.logLevel = "error";
let ready;
async function sessions() {
  if (!ready)
    ready = (async () => {
      const response = await fetch(
        import.meta.env.BASE_URL + "models/manifest.json",
      );
      if (!response.ok) throw new Error("모델 목록을 읽을 수 없습니다.");
      const manifest = await response.json(),
        models = [];
      for (const model of manifest.models) {
        const response = await fetch(
          import.meta.env.BASE_URL + "models/" + model.file,
        );
        if (!response.ok) throw new Error("모델 다운로드 실패");
        const bytes = await response.arrayBuffer(),
          hash = Array.from(
            new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
            (n) => n.toString(16).padStart(2, "0"),
          ).join("");
        if (hash !== model.sha256) throw new Error("모델 파일 검증 실패");
        models.push(
          await ort.InferenceSession.create(bytes, {
            executionProviders: ["wasm"],
            graphOptimizationLevel: "all",
            logSeverityLevel: 3,
          }),
        );
      }
      return models;
    })().catch((error) => {
      ready = null;
      throw error;
    });
  return ready;
}
function tensor(canvas, bgr = false) {
  const { data } = canvas
      .getContext("2d", { willReadFrequently: true })
      .getImageData(0, 0, canvas.width, canvas.height),
    size = canvas.width * canvas.height,
    values = new Float32Array(size * 3);
  for (let i = 0; i < size; i++) {
    values[i] = data[i * 4 + (bgr ? 2 : 0)];
    values[size + i] = data[i * 4 + 1];
    values[size * 2 + i] = data[i * 4 + (bgr ? 0 : 2)];
  }
  return new ort.Tensor("float32", values, [1, 3, canvas.height, canvas.width]);
}
function quality(canvas, pixelSize) {
  const { data } = canvas.getContext("2d").getImageData(0, 0, 112, 112),
    gray = new Float32Array(112 * 112);
  let sum = 0,
    squares = 0,
    total = 0;
  for (let i = 0; i < gray.length; i++) {
    gray[i] = (data[i * 4] + data[i * 4 + 1] + data[i * 4 + 2]) / 3;
    sum += gray[i];
  }
  for (let y = 1; y < 111; y++)
    for (let x = 1; x < 111; x++) {
      const i = y * 112 + x,
        lap =
          4 * gray[i] -
          gray[i - 1] -
          gray[i + 1] -
          gray[i - 112] -
          gray[i + 112];
      squares += lap * lap;
      total++;
    }
  const brightness = sum / gray.length,
    sharpness = squares / total;
  return {
    brightness,
    sharpness,
    usable: brightness > 18 && brightness < 242 && sharpness > 12,
    referenceUsable:
      pixelSize >= 45 && brightness > 25 && brightness < 235 && sharpness > 20,
  };
}
async function analyze(bitmap, options = {}) {
  const start = performance.now(),
    [detector, recognizer] = await sessions(),
    w = bitmap.width,
    h = bitmap.height,
    proposals = [];
  const regions = [
    { x: 0, y: 0, w, h, size: 640 },
    { x: 0, y: 0, w, h, size: 320 },
  ];
  if (Math.max(w, h) > 900) {
    const rw = w * 0.64,
      rh = h * 0.64;
    for (const x of [0, w - rw])
      for (const y of [0, h - rh])
        regions.push({ x, y, w: rw, h: rh, size: 640 });
  }
  for (const region of regions) {
    const c = new OffscreenCanvas(640, 640),
      ctx = c.getContext("2d"),
      scale = Math.min(region.size / region.w, region.size / region.h);
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, 640, 640);
    ctx.drawImage(
      bitmap,
      region.x,
      region.y,
      region.w,
      region.h,
      0,
      0,
      region.w * scale,
      region.h * scale,
    );
    const input = tensor(c, true);
    let out;
    try {
      out = await detector.run({ [detector.inputNames[0]]: input });
    } finally {
      input.dispose();
    }
    for (const face of decodeYunet(
      out,
      640,
      options.detectorThreshold ?? 0.75,
    )) {
      face.bbox = face.bbox.map(
        (v, i) => v / scale + (i % 2 ? region.y : region.x),
      );
      face.landmarks = face.landmarks.map(([x, y]) => [
        x / scale + region.x,
        y / scale + region.y,
      ]);
      if (
        face.bbox[2] > 0 &&
        face.bbox[3] > 0 &&
        face.bbox[0] < w &&
        face.bbox[1] < h
      )
        proposals.push(face);
    }
    Object.values(out).forEach((t) => t.dispose());
  }
  proposals.sort((a, b) => b.score - a.score);
  const selected = [];
  for (const proposal of proposals)
    if (selected.every((f) => iou(f.bbox, proposal.bbox) < 0.35))
      selected.push(proposal);
  const faces = [];
  let embeddingFailures = 0;
  for (const proposal of selected) {
    const crop = new OffscreenCanvas(112, 112),
      ctx = crop.getContext("2d");
    let embedding = [],
      embeddingError = "";
    try {
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, 112, 112);
      ctx.setTransform(...similarityTransform(proposal.landmarks));
      ctx.drawImage(bitmap, 0, 0);
      ctx.resetTransform();
      const input = tensor(crop);
      let output;
      try {
        output = await recognizer.run({ [recognizer.inputNames[0]]: input });
      } finally {
        input.dispose();
      }
      try {
        embedding = Array.from(
          normalize(output[recognizer.outputNames[0]].data),
        );
      } finally {
        Object.values(output).forEach((t) => t.dispose());
      }
    } catch (error) {
      embeddingFailures++;
      embeddingError = error.message;
    }
    const bbox = proposal.bbox.map((v, i) =>
      Math.max(0, Math.min(1, v / (i % 2 ? h : w))),
    );
    const pixelSize = Math.min(
      (bbox[2] - bbox[0]) * w,
      (bbox[3] - bbox[1]) * h,
    );
    faces.push({
      id: crypto.randomUUID(),
      bbox,
      embedding,
      embeddingError,
      detectionScore: proposal.score,
      pixelSize,
      quality: quality(crop, pixelSize),
      crop: await crop.convertToBlob({ type: "image/jpeg", quality: 0.9 }),
    });
  }
  return {
    faces,
    diagnostics: {
      passes: regions.length,
      detected: selected.length,
      embeddingFailures,
      seconds: (performance.now() - start) / 1000,
      model: "YuNet 2023mar + SFace 2021dec",
    },
  };
}
let chain = Promise.resolve();
self.onmessage = ({ data }) => {
  chain = chain.then(async () => {
    try {
      self.postMessage({
        id: data.id,
        result: await analyze(data.bitmap, data.options),
      });
    } catch (error) {
      self.postMessage({ id: data.id, error: error.message });
    } finally {
      data.bitmap.close();
    }
  });
};
