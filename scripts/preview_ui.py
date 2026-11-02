"""Launch a temporary sample library for desktop QA without changing last-library settings."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from photojoy.ui import MainWindow
from photojoy.widgets import ChildDialog

app = QApplication([])
library = json.loads((ROOT/'test-output/latest-smoke.json').read_text(encoding='utf-8'))['library']
window = MainWindow(library, remember=False)
window.setWindowTitle('PhotoJoy 0.2 — UI 검증')
window.navigate(2)
window.show()


def diagnose():
    import ctypes
    from ctypes import wintypes
    dialog = ChildDialog(window)
    window.diagnostic_dialog = dialog
    dialog.show()
    def log_ime():
        user, imm = ctypes.WinDLL('user32'), ctypes.WinDLL('imm32')
        user.GetKeyboardLayout.argtypes=[wintypes.DWORD]; user.GetKeyboardLayout.restype=wintypes.HANDLE
        imm.ImmIsIME.argtypes=[wintypes.HANDLE]; imm.ImmIsIME.restype=wintypes.BOOL
        imm.ImmGetContext.argtypes=[wintypes.HWND]; imm.ImmGetContext.restype=wintypes.HANDLE
        imm.ImmGetConversionStatus.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD),ctypes.POINTER(wintypes.DWORD)]
        imm.ImmReleaseContext.argtypes=[wintypes.HWND,wintypes.HANDLE]
        layout=user.GetKeyboardLayout(0); hwnd=int(dialog.winId()); context=imm.ImmGetContext(hwnd)
        conversion,sentence=wintypes.DWORD(),wintypes.DWORD()
        success=imm.ImmGetConversionStatus(context,ctypes.byref(conversion),ctypes.byref(sentence)) if context else False
        if context: imm.ImmReleaseContext(hwnd,context)
        report=dict(layout=hex(layout or 0),is_ime=bool(imm.ImmIsIME(layout)),context=bool(context),conversion=conversion.value,query_ok=bool(success),locale=app.inputMethod().locale().name(),hint=dialog.ime_hint.text())
        (ROOT/'test-output/input-diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    QTimer.singleShot(1000,log_ime)


if '--input-diagnostic' in sys.argv:
    QTimer.singleShot(300,diagnose)
sys.exit(app.exec())
