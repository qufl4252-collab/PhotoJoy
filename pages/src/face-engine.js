const canvas = (w, h) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
};
export const asBlob = (c) =>
  new Promise((resolve, reject) =>
    c.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("미리보기 생성 실패"))),
      "image/jpeg",
      0.88,
    ),
  );
let worker;
const pending = new Map();
export async function analyzeFrame(source, options = {}) {
  if (!worker) {
    worker = new Worker(new URL("./face-worker.js", import.meta.url), {
      type: "module",
    });
    worker.onmessage = ({ data }) => {
      const job = pending.get(data.id);
      pending.delete(data.id);
      if (job)
        data.error
          ? job.reject(new Error(data.error))
          : job.resolve(data.result);
    };
    worker.onerror = () => {
      for (const job of pending.values())
        job.reject(
          new Error("얼굴 분석 작업이 중단되었습니다. 다시 시도해 주세요."),
        );
      pending.clear();
      worker.terminate();
      worker = null;
    };
  }
  const bitmap = await createImageBitmap(source),
    id = crypto.randomUUID();
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, bitmap, options }, [bitmap]);
  });
}
function waitEvent(element, event, timeout = 20000) {
  return new Promise((resolve, reject) => {
    const done = () => {
      clearTimeout(timer);
      element.removeEventListener(event, ok);
      element.removeEventListener("error", bad);
    };
    const ok = () => {
        done();
        resolve();
      },
      bad = () => {
        done();
        reject(
          new Error(
            "이 브라우저에서 파일을 읽을 수 없어요. JPG·PNG 또는 MP4 파일로 다시 선택해 주세요.",
          ),
        );
      };
    const timer = setTimeout(bad, timeout);
    element.addEventListener(event, ok, { once: true });
    element.addEventListener("error", bad, { once: true });
  });
}
export async function readFrames(file, receive) {
  let readable = file;
  if (/\.(heic|heif)$/i.test(file.name) || /image\/hei[cf]/i.test(file.type))
    readable = await new Promise((resolve, reject) => {
      const decoder = new Worker(new URL("./heic-worker.js", import.meta.url), {
        type: "module",
      });
      const timer = setTimeout(() => {
        decoder.terminate();
        reject(
          new Error("HEIC 변환 시간이 초과되었습니다. 원본은 보존됩니다."),
        );
      }, 60000);
      decoder.onmessage = ({ data }) => {
        clearTimeout(timer);
        decoder.terminate();
        data.error ? reject(new Error(data.error)) : resolve(data.blob);
      };
      decoder.onerror = () => {
        clearTimeout(timer);
        decoder.terminate();
        reject(new Error("HEIC 변환에 실패했습니다. 원본은 보존됩니다."));
      };
      decoder.postMessage(file);
    });
  const url = URL.createObjectURL(readable);
  let media;
  try {
    const video =
      file.type.startsWith("video/") ||
      /\.(mp4|mov|m4v|webm)$/i.test(file.name);
    if (video) {
      media = document.createElement("video");
      media.muted = true;
      media.playsInline = true;
      media.preload = "auto";
      const loaded = waitEvent(media, "loadeddata");
      media.src = url;
      await loaded;
      if (!Number.isFinite(media.duration) || media.duration <= 0)
        throw new Error("영상 길이를 읽을 수 없어요.");
      for (let i = 0; i < 8; i++) {
        const time = Math.max(
          0,
          Math.min(media.duration - 0.05, (media.duration * i) / 8),
        );
        if (Math.abs(media.currentTime - time) > 0.005) {
          const seek = waitEvent(media, "seeked");
          media.currentTime = time;
          await seek;
        }
        const ratio = Math.min(
            1,
            1600 / Math.max(media.videoWidth, media.videoHeight),
          ),
          frame = canvas(
            Math.round(media.videoWidth * ratio),
            Math.round(media.videoHeight * ratio),
          );
        frame
          .getContext("2d")
          .drawImage(media, 0, 0, frame.width, frame.height);
        await receive(frame, time);
      }
    } else {
      media = new Image();
      const loaded = waitEvent(media, "load");
      media.src = url;
      await loaded;
      if (!media.naturalWidth || !media.naturalHeight)
        throw new Error("사진을 읽을 수 없어요.");
      const ratio = Math.min(
          1,
          1600 / Math.max(media.naturalWidth, media.naturalHeight),
        ),
        frame = canvas(
          Math.round(media.naturalWidth * ratio),
          Math.round(media.naturalHeight * ratio),
        );
      frame.getContext("2d").drawImage(media, 0, 0, frame.width, frame.height);
      await receive(frame, null);
    }
  } finally {
    if (media instanceof HTMLVideoElement) {
      media.pause();
      media.removeAttribute("src");
      media.load();
    }
    URL.revokeObjectURL(url);
  }
}
