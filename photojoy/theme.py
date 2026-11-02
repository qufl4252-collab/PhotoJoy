from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer


PATHS = {
    'camera': '<path d="M8 5l2-2h4l2 2h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"/><circle cx="12" cy="13" r="5"/><path d="M10 13l2 2 3-4"/>',
    'image': '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="M3 17l6-6 4 4 3-3 5 5"/>',
    'check': '<circle cx="12" cy="12" r="9"/><path d="M7 12l3 3 7-7"/>',
    'edit': '<path d="M4 16L16 4l4 4L8 20H4zM13 7l4 4M3 22h18"/>',
    'folder': '<path d="M3 7V5a2 2 0 0 1 2-2h5l3 3h6a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7zM3 9h18"/>',
    'people': '<circle cx="9" cy="7" r="3"/><path d="M3 21v-4a6 6 0 0 1 12 0v4zM17 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 5v2"/>',
    'send': '<path d="M22 2L9 15M22 2l-8 20-5-7-7-5z"/>',
    'chart': '<rect x="3" y="13" width="4" height="8" rx="1"/><rect x="10" y="8" width="4" height="13" rx="1"/><rect x="17" y="3" width="4" height="18" rx="1"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>',
    'gear': '<path d="M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z"/><circle cx="12" cy="12" r="3"/>',
    'refresh': '<path d="M20 7a9 9 0 0 0-15-2L2 8M2 2v6h6M4 17a9 9 0 0 0 15 2l3-3M22 22v-6h-6"/>',
    'plus': '<path d="M12 4v16M4 12h16"/>',
    'grid': '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    'list': '<path d="M8 5h13M8 12h13M8 19h13M3 5h1M3 12h1M3 19h1"/>',
    'left': '<path d="M15 5l-7 7 7 7"/>',
    'right': '<path d="M9 5l7 7-7 7"/>',
    'min': '<path d="M5 12h14"/>',
    'max': '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    'restore': '<path d="M9 5V3h12v12h-2"/><rect x="3" y="9" width="12" height="12" rx="1"/>',
    'close': '<path d="M5 5l14 14M19 5L5 19"/>',
    'book': '<path d="M12 5C8 2 5 3 2 4v16c3-1 6-2 10 1 4-3 7-2 10-1V4c-3-1-6-2-10 1v16"/>',
}


def icon(name, color='#557a9a', size=24):
    body = PATHS.get(name, PATHS['image'])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


STYLE = """
QWidget { font-family: 'Malgun Gothic', 'Segoe UI'; font-size: 13px; color: #24354a; }
QMainWindow, QDialog { background: #f7fafc; }
QWidget#shell { background: #fafbfc; border: 1px solid #d9e5ee; }
QWidget#sidebar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #dff2ff,stop:0.36 #fffaf3,stop:1 #f3f9eb); border-right: 1px solid #e5edf3; }
QWidget#titlebar { background: #fafbfc; }
QLabel#brand { font-size: 25px; font-weight: 800; color: #23425b; }
QLabel#pageTitle { font-size: 26px; font-weight: 800; }
QLabel#muted { color: #738296; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; }
QLabel#metric { font-size: 21px; font-weight: 800; color: #24354a; }
QLabel#blueTitle { font-size: 17px; font-weight: 700; color: #1783d5; }
QFrame#panel, QWidget#panel { background: white; border: 1px solid #dfe8f0; border-radius: 16px; }
QFrame#softPanel { background: #ecf7ff; border: 1px solid #d6ebfb; border-radius: 16px; }
QLabel { background: transparent; border: none; }
QPushButton { background: white; border: 1px solid #d0deea; border-radius: 10px; padding: 8px 13px; min-height: 20px; font-weight: 600; }
QPushButton:hover { background: #edf7ff; border-color: #80bff3; }
QPushButton:pressed { background: #d7ecff; }
QPushButton:disabled { color: #a8b4c2; background: #f2f5f7; border-color: #e4eaf0; }
QPushButton#primary { background: #168df0; color: white; border-color: #168df0; }
QPushButton#primary:hover { background: #087fdd; }
QPushButton#nav { text-align: left; border: none; background: transparent; border-radius: 14px; padding: 10px 15px; font-size: 16px; font-weight: 700; }
QPushButton#nav:hover { background: #e6f2fc; }
QPushButton#nav:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #168df0,stop:1 #46a9ee); color: white; }
QPushButton#windowControl { background: transparent; border: none; border-radius: 6px; padding: 4px; min-height: 22px; }
QPushButton#windowControl:hover { background: #e5eff8; }
QPushButton#windowClose { background: transparent; border: none; padding: 4px; border-radius: 6px; }
QPushButton#windowClose:hover { background: #ffe2e3; }
QPushButton#filter { border-radius: 15px; padding: 6px 11px; font-size: 12px; }
QPushButton#filter:checked { background: #deefff; color: #126ec2; border-color: #8cc6ff; }
QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox { background: white; border: 1px solid #d2dfe9; border-radius: 8px; padding: 7px; selection-background-color: #d2eaff; selection-color: #173951; }
QLineEdit:focus, QComboBox:focus { border: 2px solid #339ff3; }
QLineEdit#nameInput { font-size: 20px; min-height: 32px; }
QTableWidget, QListWidget, QTextBrowser, QPlainTextEdit { background: white; border: 1px solid #e1e9f0; border-radius: 10px; outline: none; gridline-color: #edf2f6; selection-background-color: #dfedfc; selection-color: #174a74; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #edf2f6; }
QHeaderView::section { background: #f5f9fc; border: none; border-bottom: 1px solid #e5edf4; padding: 10px 7px; color: #66788d; font-weight: 600; }
QListWidget#photoCards { background: #fbfdff; border: none; }
QListWidget#guideTopics::item { padding: 14px 10px; border-radius: 8px; }
QListWidget#guideTopics::item:selected { color: #167cd3; background: #e4f2ff; }
QProgressBar { background: #e8f2eb; border: none; border-radius: 5px; min-height: 8px; max-height: 8px; color: transparent; }
QProgressBar::chunk { background: #39c56d; border-radius: 5px; }
QSplitter::handle { background: #eef3f7; width: 7px; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: #cfdeea; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QToolTip { background: #203a50; color: white; border: none; padding: 6px; }
"""
