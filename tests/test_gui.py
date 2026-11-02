import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from photojoy.ui import MainWindow


def test_ui_loads_library_and_all_tabs(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(str(tmp_path / "라이브러리"), remember=False)
    window.store.add_child("샘플 아이")
    window.refresh()
    window.show()
    app.processEvents()
    assert window.tabs.count() == 9
    for index, page in enumerate((5,6,1,1,7,0,2,8,3)):
        window.navigate(index)
        assert window.tabs.currentIndex() == page
    assert window.children_table.rowCount() == 1
    assert window.stats_table.rowCount() == 1
    assert window.store.db.is_file()
    window.close()


def test_korean_name_composition_and_store_roundtrip(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QInputMethodEvent
    from PySide6.QtTest import QTest
    from photojoy.widgets import ChildDialog
    from photojoy.store import Store
    app = QApplication.instance() or QApplication([])
    dialog = ChildDialog()
    # Check IME composition, rather than assigning an already finished string.
    QApplication.sendEvent(dialog.name_edit, QInputMethodEvent('ㄱ', []))
    assert dialog.name_edit.preedit == 'ㄱ'
    event = QInputMethodEvent('민', [])
    event.setCommitString('김')
    QApplication.sendEvent(dialog.name_edit, event)
    event = QInputMethodEvent()
    event.setCommitString('민준')
    QApplication.sendEvent(dialog.name_edit, event)
    assert dialog.name_edit.text() == '김민준'
    QTest.keyClick(dialog, Qt.Key.Key_Return)
    assert dialog.result() != dialog.DialogCode.Accepted
    dialog.accept()
    assert dialog.result() == dialog.DialogCode.Accepted
    store = Store(tmp_path/'한글 이름')
    identifier = store.add_child(*dialog.values())
    store.update_child(identifier, '박서연', '햇살반', True)
    row = Store(store.root).children()[0]
    assert row['name'] == '박서연' and row['group_name'] == '햇살반'


def test_card_filters_and_selection_do_not_target_hidden_photos(tmp_path):
    import json
    from PySide6.QtCore import Qt
    from photojoy.paths import uid
    from photojoy.store import now
    from photojoy.ui import selected_ids
    app = QApplication.instance() or QApplication([])
    window = MainWindow(str(tmp_path/'카드'),remember=False)
    child = window.store.add_child('김민준')
    media = []
    for index in range(3):
        key = uid(); media.append(key)
        window.store.execute('INSERT INTO media(id,path,sha256,kind,captured,date_source,created) VALUES (?,?,?,?,?,?,?)',
            (key,f'사진{index}.jpg',key,'photo','2026-11-02','파일명',now()))
    window.store.review(media[:2],[child])
    window.refresh()
    window.navigate(2)
    for index in range(window.media_table.count()):
        item = window.media_table.item(index)
        if item.data(Qt.ItemDataRole.UserRole) in media[:2]:
            item.setSelected(True)
    selected = set(selected_ids(window.media_table))
    window.refresh()
    assert set(selected_ids(window.media_table)) == selected
    window.set_review_filter('pending')
    assert window.media_table.count() == 1
    assert not selected_ids(window.media_table)
    window.media_table.setCurrentRow(0)
    assert selected_ids(window.media_table) == [media[2]]
    window.media_search.setText('존재하지않는이름')
    assert window.media_table.count() == 0
    assert not selected_ids(window.media_table) and window.current_media is None
    window.close()


def test_guide_available_before_library_and_window_controls(tmp_path):
    from photojoy.widgets import TitleBar
    app = QApplication.instance() or QApplication([])
    window = MainWindow(str(tmp_path/'가이드'),remember=False)
    window.show_guide()
    assert window.guide_dialog.isVisible()
    window.guide_dialog.topics.setCurrentRow(1)
    assert '한글 입력 켜기' in window.guide_dialog.content.toPlainText()
    window.guide_dialog.open_step()
    assert window.current_nav == 5
    assert window.titlebar.layout().indexOf(window.titlebar.guide) < window.titlebar.layout().indexOf(window.titlebar.minimize)
    window.titlebar.toggle_maximized()
    assert window.isMaximized()
    window.titlebar.toggle_maximized()
    assert not window.isMaximized()
    window.close()
    app.processEvents()


def test_worker_returns_to_gui_thread(tmp_path):
    import time
    from PySide6.QtCore import QThread
    app = QApplication.instance() or QApplication([])
    window = MainWindow(str(tmp_path / "작업"), remember=False)
    finished = []
    window.run_job("test", lambda p, c: window.store.add_child("백그라운드 등록"), lambda result: finished.append((result, QThread.currentThread() == app.thread())))
    deadline = time.monotonic() + 10
    while window.worker and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert finished and finished[0][1]
    assert window.children_table.rowCount() == 1
    window.close()
