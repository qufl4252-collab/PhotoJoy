import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from photojoy.hangul import compose


@pytest.mark.parametrize('keys,expected',[
    ('rlaalswns','김민준'), ('qkrtjdus','박서연'), ('dlehdbs','이도윤'),
    ('chldbwls','최유진'), ('gottkf','햇살'), ('gksmf','하늘'),
    ('dlfrdj','읽어'), ('dkswdk','앉아'), ('rkqtk','갑사'),
    ('rhk','과'), ('rnjs','권'), ('RkRk','까까'), ('dlTdj','있어'),
    ('dkssud gktpdy','안녕 하세요'), ('',''),
])
def test_two_set_hangul(keys, expected):
    assert compose(keys) == expected


def test_direct_typing_backspace_selection_paste_and_mode():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt, QEvent
    from PySide6.QtGui import QKeyEvent
    from photojoy.widgets import NameEdit
    app = QApplication.instance() or QApplication([])
    edit = NameEdit()
    edit.set_direct_korean(True)
    QTest.keyClicks(edit,'rlaalswns')
    assert edit.text() == '김민준'
    QTest.keyClick(edit,Qt.Key.Key_Backspace)
    assert edit.text() == '김민주'
    QTest.keyClicks(edit,'s')
    assert edit.text() == '김민준'
    QTest.keyClick(edit,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(edit,'qkrtjdus')
    assert edit.text() == '박서연'
    QApplication.sendEvent(edit,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Hangul,Qt.KeyboardModifier.NoModifier))
    assert not edit.direct_korean
    QTest.keyClicks(edit,' Jane')
    assert edit.text() == '박서연 Jane'
    QTest.keyClick(edit,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    app.clipboard().setText('김하늘')
    QTest.keyClick(edit,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
    assert edit.text() == '김하늘'
