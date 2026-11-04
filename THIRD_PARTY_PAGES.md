# PhotoJoy Pages third-party notices

PhotoJoy independently implements its workflow and UI. Its browser build uses:

| Component | Version | License/source |
|---|---|---|
| Firebase JS SDK | 13.2.0 | Apache-2.0, https://github.com/firebase/firebase-js-sdk |
| ONNX Runtime Web/Common | 1.31.1 | MIT and bundled third-party notices, https://github.com/microsoft/onnxruntime |
| fflate | 0.8.3 | MIT, https://github.com/101arrowz/fflate |
| exifr | 7.1.3 | MIT, https://github.com/MikeKovarik/exifr |
| heic-to | 1.6.7 | LGPL-3.0-or-later, https://github.com/hoppergee/heic-to |
| YuNet | 2023mar | MIT, OpenCV Zoo (models/manifest.json) |
| SFace | 2021dec | Apache-2.0, OpenCV Zoo (models/manifest.json) |

License texts are included under `licenses/` in the published site. Firebase supplies Authentication and private account roster storage for child names, groups, selected face crops and comparison vectors. Classification and original media storage run in the browser.

## HEIC decoder replacement and source

The unmodified heic-to decoder is loaded in a separate worker on demand. Its corresponding source and build instructions, including the libheif decoder build, are available at https://github.com/hoppergee/heic-to (release 1.6.7) and https://github.com/strukturag/libheif. The upstream heic-to README describes the libheif/Emscripten build. Obtain the published package with `npm pack heic-to@1.6.7`.

You may modify or replace this library, including for debugging those modifications. Clone PhotoJoy, replace `pages/src/heic-worker.js` or the heic-to dependency with your compatible build, then run `npm install` and `npm run build` in `pages/`. The entire PhotoJoy integration source and lockfile are supplied; no signing key is needed to rebuild or run it. The source application is not dependent on the decoder for JPEG/PNG processing.
