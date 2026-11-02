"""Render the application's own widgets for layout QA, using generated sample data."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from photojoy.ui import MainWindow
app = QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgun.ttf')
QFontDatabase.addApplicationFont('C:/Windows/Fonts/malgunbd.ttf')
library = json.loads((ROOT/'test-output/latest-smoke.json').read_text(encoding='utf-8'))['library']
window = MainWindow(library,remember=False)
window.resize(1510,940)
window.navigate(2)
window.show()
app.processEvents()
for index in range(window.media_table.count()):
    if '단체' in window.media_table.item(index).toolTip():
        window.media_table.setCurrentRow(index)
        break
app.processEvents()
assert window.media_table.visualItemRect(window.media_table.item(0)).height() > 100
window.grab().save(str(ROOT/'test-output/ui02-review.png'))
window.show_guide()
app.processEvents()
window.guide_dialog.grab().save(str(ROOT/'test-output/ui02-guide.png'))
window.guide_dialog.close()
window.resize(1180,740)
app.processEvents()
window.grab().save(str(ROOT/'test-output/ui02-compact.png'))
window.close()
print('Rendered review, guide and compact layouts.')
