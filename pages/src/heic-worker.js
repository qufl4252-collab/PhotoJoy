import { heicTo } from "heic-to/next";
self.onmessage = async ({ data }) => {
  try {
    self.postMessage({
      blob: await heicTo({ blob: data, type: "image/jpeg", quality: 1 }),
    });
  } catch (error) {
    self.postMessage({
      error: "HEIC를 읽을 수 없습니다. 원본은 보존됩니다. " + error.message,
    });
  }
};
