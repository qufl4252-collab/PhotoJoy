"""Reusable desktop widgets: window controls, photo cards and Korean name entry."""
import sys
from html import escape

from PySide6.QtCore import Qt, QSize, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QFont, QPainterPath, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QDialog, QLineEdit,
    QFormLayout, QListWidget, QListView, QAbstractItemView, QStyledItemDelegate,
    QStyle, QFrame, QApplication, QCheckBox,
)
from .theme import icon
from .hangul import compose


CARD_ROLE = Qt.ItemDataRole.UserRole + 1


def panel(layout_type=QVBoxLayout, soft=False):
    widget = QFrame()
    widget.setObjectName('softPanel' if soft else 'panel')
    layout = layout_type(widget)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    return widget, layout


def label(text, style=None):
    widget = QLabel(text)
    if style:
        widget.setObjectName(style)
    return widget


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.setObjectName('titlebar')
        self.setFixedHeight(38)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 3, 5, 3)
        title = label('PhotoJoy  ·  아이들의 순간을 모으다', 'muted')
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(title)
        row.addStretch()
        self.guide = QPushButton('  가이드')
        self.guide.setIcon(icon('gear', '#4784ad', 18))
        self.guide.setObjectName('windowControl')
        self.guide.setToolTip('사용 방법 보기 (F1)')
        self.guide.setAccessibleName('가이드')
        self.guide.clicked.connect(window.show_guide)
        row.addWidget(self.guide)
        self.minimize = self.control('min', '최소화', window.showMinimized)
        self.maximize = self.control('max', '전체화면 / 창모드', self.toggle_maximized)
        self.close_button = self.control('close', '창 닫기', window.close)
        self.close_button.setObjectName('windowClose')
        for control in (self.minimize, self.maximize, self.close_button):
            row.addWidget(control)

    def control(self, name, text, callback):
        control = QPushButton()
        control.setIcon(icon(name, '#354658', 16))
        control.setObjectName('windowControl')
        control.setToolTip(text)
        control.setAccessibleName(text)
        control.setFixedSize(40, 30)
        control.clicked.connect(callback)
        return control

    def toggle_maximized(self):
        self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()
        self.maximize.setIcon(icon('restore' if self.owner.isMaximized() else 'max', '#354658', 16))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()


class BrandArt(QWidget):
    """Small code-drawn illustration; no reference product artwork is bundled."""
    def __init__(self, school=False):
        super().__init__()
        self.school = school
        self.setFixedHeight(118 if school else 80)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(self.width()/210, self.height()/(118 if self.school else 80))
        p.setPen(Qt.PenStyle.NoPen)
        for x, y in [(20, 24), (171, 17)]:
            p.setBrush(QColor('#bce5ff'))
            p.drawEllipse(QRectF(x, y, 24, 14))
            p.drawEllipse(QRectF(x+9, y-7, 18, 20))
        if self.school:
            p.setBrush(QColor('#d1e8a8'))
            p.drawEllipse(QRectF(-25, 78, 270, 70))
            p.setBrush(QColor('#ffe8ba'))
            p.drawRoundedRect(QRectF(53, 51, 106, 60), 5, 5)
            roof = QPainterPath()
            roof.moveTo(44, 54); roof.lineTo(106, 13); roof.lineTo(169, 54); roof.closeSubpath()
            p.setBrush(QColor('#ffada8')); p.drawPath(roof)
            p.setBrush(QColor('#a4d9f7'))
            for x in (65, 129):
                p.drawRoundedRect(QRectF(x, 65, 18, 19), 3, 3)
            p.setBrush(QColor('#77bbdf')); p.drawRoundedRect(QRectF(94, 79, 24, 32), 9, 9)
            p.setBrush(QColor('white')); p.drawEllipse(QRectF(96, 45, 20, 20))
            p.setPen(QPen(QColor('#dd947b'), 2)); p.drawLine(106, 49, 106, 56); p.drawLine(106, 56, 111, 56)
            p.setPen(Qt.PenStyle.NoPen)
            for x in (25, 184):
                p.setBrush(QColor('#b3ca84')); p.drawRoundedRect(QRectF(x-12, 69, 25, 34), 12, 12)
                p.setBrush(QColor('#ac976a')); p.drawRect(QRectF(x-2, 85, 4, 27))
        else:
            p.setBrush(QColor('#fff1b8')); p.drawEllipse(QRectF(157, 47, 12, 12))
            p.setPen(QPen(QColor('#3e7095'), 2.7)); p.setBrush(QColor('#8fd0ff'))
            p.drawRoundedRect(QRectF(76, 18, 59, 44), 10, 10)
            p.drawRoundedRect(QRectF(94, 11, 22, 11), 4, 4)
            p.setBrush(QColor('#ffffff')); p.drawEllipse(QRectF(91, 27, 29, 29))
            p.setPen(QPen(QColor('#fc857f'), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(100, 39, 106, 46); p.drawLine(106, 46, 113, 37)
            p.setPen(QPen(QColor('#ffcf52'), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(145, 17, 150, 12); p.drawLine(149, 29, 157, 29)
        p.end()


class CardDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent)
        self.grid = True

    def sizeHint(self, option, index):
        return self.parent().gridSize()

    def paint(self, painter, option, index):
        data = index.data(CARD_ROLE) or {}
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QPen(QColor('#1595ff' if selected else '#dae5ee'), 2 if selected else 1))
        painter.setBrush(QColor('#f6fbff' if selected else '#ffffff'))
        painter.drawRoundedRect(rect, 13, 13)
        image_rect = rect.adjusted(4, 4, -4, -76) if self.grid else QRectF(rect.x()+5, rect.y()+5, 108, rect.height()-10)
        pixmap = data.get('pixmap')
        clip = QPainterPath(); clip.addRoundedRect(image_rect, 10, 10)
        painter.save(); painter.setClipPath(clip)
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(image_rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(image_rect.x()+(image_rect.width()-scaled.width())/2, image_rect.y()+(image_rect.height()-scaled.height())/2, scaled)
        else:
            painter.fillRect(image_rect, QColor('#eaf2f8'))
            painter.setPen(QColor('#8b9eaf')); painter.drawText(image_rect, Qt.AlignmentFlag.AlignCenter, '미리보기 없음')
        painter.restore()
        color, bg = {'candidate': ('#2a963f','#e4f8df'), 'confirmed': ('#167bcb','#e2f1ff'), 'pending': ('#c18015','#fff1d3'), 'excluded': ('#8793a2','#eef1f5')}.get(data.get('category'), ('#c35158','#ffe9eb'))
        x = rect.x()+11 if self.grid else image_rect.right()+14
        y = image_rect.bottom()+8 if self.grid else rect.y()+12
        badge = QRectF(x, y, min(rect.right()-x-8, 125), 23)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(bg)); painter.drawRoundedRect(badge, 10, 10)
        font = QFont('Malgun Gothic', 9); font.setBold(True); painter.setFont(font)
        painter.setPen(QColor(color)); painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, data.get('badge','검토 필요'))
        font.setBold(False); painter.setFont(font); painter.setPen(QColor('#607286'))
        info_rect = QRectF(x, y+28, rect.right()-x-10, 20)
        painter.drawText(info_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, data.get('date','')+'   ·   '+data.get('kind','사진'))
        painter.setPen(QColor('#354960'))
        text_rect = QRectF(x, y+49, rect.right()-x-10, 19) if self.grid else QRectF(x+140,y,rect.right()-x-150,50)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(data.get('names') or data.get('filename',''), Qt.TextElideMode.ElideRight, int(text_rect.width())))
        if selected:
            painter.setPen(QPen(QColor('white'), 2)); painter.setBrush(QColor('#168df0'))
            painter.drawEllipse(QRectF(rect.x()+8, rect.y()+8, 22, 22))
            painter.drawLine(int(rect.x()+14),int(rect.y()+19),int(rect.x()+18),int(rect.y()+23))
            painter.drawLine(int(rect.x()+18),int(rect.y()+23),int(rect.x()+25),int(rect.y()+15))
        painter.restore()


class PhotoCards(QListWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('photoCards')
        self.setAccessibleName('사진 목록')
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSpacing(3)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.delegate = CardDelegate(self)
        self.setItemDelegate(self.delegate)
        self.set_card_mode(True)

    def set_card_mode(self, grid):
        self.delegate.grid = grid
        self.setViewMode(QListView.ViewMode.IconMode if grid else QListView.ViewMode.ListMode)
        self.setFlow(QListView.Flow.LeftToRight if grid else QListView.Flow.TopToBottom)
        self.setWrapping(grid)
        self._size_items()

    def _size_items(self):
        width = max(200, self.viewport().width()-8)
        columns = max(1, width//210) if self.delegate.grid else 1
        self.setGridSize(QSize(max(190, (width-6*columns)//columns), 224 if self.delegate.grid else 96))
        self.doItemsLayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._size_items()


def enable_korean_input(widget):
    """Select an already installed Korean IME for this UI thread only."""
    widget.setFocus(Qt.FocusReason.OtherFocusReason)
    if sys.platform != 'win32':
        return False, '이름 입력칸에서 운영체제의 한국어 입력기를 선택하세요.'
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    imm = ctypes.WinDLL('imm32', use_last_error=True)
    handle = wintypes.HANDLE
    user.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(handle)]
    user.GetKeyboardLayoutList.restype = ctypes.c_int
    user.ActivateKeyboardLayout.argtypes = [handle, wintypes.UINT]
    user.ActivateKeyboardLayout.restype = handle
    layouts = (handle * 32)()
    count = user.GetKeyboardLayoutList(32, layouts)
    korean = next((layouts[i] for i in range(count) if int(layouts[i] or 0) & 0xffff == 0x0412), None)
    if not korean:
        return False, '설치된 한국어 입력기를 찾지 못했습니다. Windows 입력 언어에서 한국어를 선택하세요.'
    user.ActivateKeyboardLayout(korean, 0)
    hwnd = int(widget.window().winId())
    imm.ImmAssociateContextEx.argtypes = [wintypes.HWND, handle, wintypes.DWORD]
    imm.ImmAssociateContextEx.restype = wintypes.BOOL
    imm.ImmGetContext.argtypes = [wintypes.HWND]; imm.ImmGetContext.restype = handle
    imm.ImmReleaseContext.argtypes = [wintypes.HWND, handle]
    imm.ImmSetOpenStatus.argtypes = [handle, wintypes.BOOL]
    imm.ImmSetConversionStatus.argtypes = [handle, wintypes.DWORD, wintypes.DWORD]
    imm.ImmGetConversionStatus.argtypes = [handle, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    context = imm.ImmGetContext(hwnd)
    if not context:
        imm.ImmAssociateContextEx(hwnd, None, 0x10)  # IACE_DEFAULT, own dialog only.
        context = imm.ImmGetContext(hwnd)
    if not context:
        return False, '한국어 입력기를 선택했습니다. 입력칸을 클릭하고 한/영 키를 눌러주세요.'
    try:
        conversion, sentence = wintypes.DWORD(), wintypes.DWORD()
        imm.ImmGetConversionStatus(context, ctypes.byref(conversion), ctypes.byref(sentence))
        imm.ImmSetOpenStatus(context, True)
        ok = imm.ImmSetConversionStatus(context, conversion.value | 0x1, sentence.value)
    finally:
        imm.ImmReleaseContext(hwnd, context)
    QGuiApplication.inputMethod().update(Qt.InputMethodQuery.ImQueryAll)
    return bool(ok), '한국어 입력 준비 완료 · 한/영 키로 전환할 수 있습니다.' if ok else '한국어 입력기를 선택했습니다. 한/영 키로 전환해 주세요.'


class NameEdit(QLineEdit):
    mode_changed = Signal(bool)

    def __init__(self, text=''):
        super().__init__(text)
        self.preedit = ''
        self.direct_korean = False
        self._keys = ''
        self._composition_start = self._composition_length = 0
        self.setObjectName('nameInput')
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.setMaxLength(80)

    def inputMethodEvent(self, event):
        self.finish_direct()
        self.preedit = event.preeditString()
        super().inputMethodEvent(event)

    def finish_direct(self):
        self._keys = ''
        self._composition_length = 0

    def set_direct_korean(self, enabled):
        self.finish_direct()
        self.direct_korean = enabled

    def mousePressEvent(self, event):
        self.finish_direct()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        self.finish_direct()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Hangul:
            self.set_direct_korean(not self.direct_korean)
            self.mode_changed.emit(self.direct_korean)
            event.accept()
            return
        modifiers = event.modifiers()
        letter = event.text()
        plain = not modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
        if self.direct_korean and plain and len(letter)==1 and letter.isascii() and letter.isalpha():
            if not self._keys:
                self._composition_start = self.selectionStart() if self.hasSelectedText() else self.cursorPosition()
                self._composition_length = len(self.selectedText())
            previous = self._keys
            self._keys += letter
            composed = compose(self._keys)
            if len(self.text())-self._composition_length+len(composed) > self.maxLength():
                self._keys = previous
                event.accept()
                return
            self.setSelection(self._composition_start,self._composition_length)
            self.insert(composed)
            self._composition_length = len(composed)
            event.accept()
            return
        if self.direct_korean and plain and event.key()==Qt.Key.Key_Backspace and self._keys:
            self._keys = self._keys[:-1]
            composed = compose(self._keys)
            self.setSelection(self._composition_start,self._composition_length)
            self.insert(composed)
            self._composition_length = len(composed)
            event.accept()
            return
        self.finish_direct()
        super().keyPressEvent(event)


class ChildDialog(QDialog):
    def __init__(self, parent=None, child=None):
        super().__init__(parent)
        self.setWindowTitle('아이 정보 수정' if child else '아이 추가')
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24,24,24,24)
        layout.setSpacing(14)
        layout.addWidget(label(self.windowTitle(), 'pageTitle'))
        layout.addWidget(label('이름을 등록하고 얼굴이 잘 보이는 참고 사진을 추가해 주세요.', 'muted'))
        self.name_edit = NameEdit(child['name'] if child else '')
        self.name_edit.setAccessibleName('아이 이름')
        self.name_edit.setPlaceholderText('예: 김민준')
        self.group_edit = NameEdit(child['group_name'] if child else '')
        self.group_edit.setAccessibleName('그룹 메모')
        self.group_edit.setPlaceholderText('예: 햇살반 (선택)')
        form = QFormLayout()
        form.addRow('아이 이름', self.name_edit); form.addRow('그룹 메모', self.group_edit)
        layout.addLayout(form)
        self.ime_hint = label('한글이 입력되지 않으면 아래 ‘한글 입력 켜기’를 누르세요.', 'muted')
        self.ime_hint.setWordWrap(True); layout.addWidget(self.ime_hint)
        self.direct_mode = QCheckBox('한글 직접 입력 (두벌식)')
        self.direct_mode.toggled.connect(self.set_direct_mode)
        self.name_edit.mode_changed.connect(self.direct_mode.setChecked)
        self.group_edit.mode_changed.connect(self.direct_mode.setChecked)
        layout.addWidget(self.direct_mode)
        row = QHBoxLayout()
        self.korean_button = QPushButton('한글 입력 켜기')
        self.korean_button.setAutoDefault(False)
        self.korean_button.clicked.connect(self.force_korean)
        row.addWidget(self.korean_button); row.addStretch()
        cancel = QPushButton('취소'); cancel.setAutoDefault(False); cancel.clicked.connect(self.reject)
        self.save_button = QPushButton('저장'); self.save_button.setObjectName('primary')
        self.save_button.setAutoDefault(False); self.save_button.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(self.save_button)
        layout.addLayout(row)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self.enable_korean)

    def enable_korean(self):
        if not self.isVisible():
            return
        active = self.focusWidget()
        target = active if isinstance(active, NameEdit) else self.name_edit
        try:
            ok, message = enable_korean_input(target)
        except (OSError, AttributeError):
            ok, message = False, 'Windows 입력기 대신 한글 직접 입력을 사용합니다.'
        self.ime_hint.setText(message)
        if not ok:
            self.direct_mode.setChecked(True)

    def set_direct_mode(self, enabled):
        for edit in (self.name_edit,self.group_edit):
            edit.set_direct_korean(enabled)
        self.ime_hint.setText('한글 직접 입력 모드입니다. 두벌식 자판으로 입력하세요.' if enabled else '일반 입력 모드입니다. Windows 입력기의 한/영 상태를 따릅니다.')

    def force_korean(self):
        self.direct_mode.setChecked(True)
        self.name_edit.setFocus()

    def accept(self):
        QGuiApplication.inputMethod().commit()
        self.name_edit.clearFocus(); self.group_edit.clearFocus()
        if not self.name_edit.text().strip():
            self.ime_hint.setText('아이 이름을 입력해 주세요.')
            self.name_edit.setFocus()
            return
        super().accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Enter finalizes a composed syllable, never silently submits a name.
            QGuiApplication.inputMethod().commit()
            event.accept()
            return
        super().keyPressEvent(event)

    def values(self):
        return self.name_edit.text().strip(), self.group_edit.text().strip()


class MonthChart(QWidget):
    def __init__(self):
        super().__init__()
        self.values = []
        self.setMinimumHeight(150)

    def set_values(self, values):
        self.values = values[-6:]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.values:
            p.setPen(QColor('#8a9aac')); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '확인한 자료가 쌓이면 월별 수량이 표시됩니다.')
            return
        largest = max(1, max(n for _, n in self.values))
        step = self.width()/len(self.values)
        for i, (month, count) in enumerate(self.values):
            height = (self.height()-48)*count/largest
            rect = QRectF(i*step+step*.22, self.height()-27-height, step*.56, height)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#74bef9')); p.drawRoundedRect(rect, 6, 6)
            p.setPen(QColor('#526e87'))
            p.drawText(QRectF(i*step, self.height()-24, step, 22), Qt.AlignmentFlag.AlignCenter, month)
            p.drawText(QRectF(i*step, rect.top()-22, step, 20), Qt.AlignmentFlag.AlignCenter, str(count))
