import argparse
import json
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication
from .ui import MainWindow


def main():
    parser = argparse.ArgumentParser(description="PhotoJoy")
    parser.add_argument("--library")
    parser.add_argument("--diagnose-output", help="모델 로드 진단 JSON을 저장하고 종료")
    parser.add_argument("--diagnose-image", help="진단할 사진 경로")
    args = parser.parse_args()
    if args.diagnose_output:
        from .engine import SFaceEngine
        from .media import read_image
        engine = SFaceEngine()
        engine.load()
        result = {"engine": engine.fingerprint, "loaded": True}
        if args.diagnose_image:
            faces = engine.detect_and_embed(read_image(Path(args.diagnose_image)))
            result.update(face_count=len(faces), dimensions=[int(f.embedding.size) for f in faces])
        Path(args.diagnose_output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PhotoJoy")
    window = MainWindow(args.library)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

