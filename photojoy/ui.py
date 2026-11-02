from datetime import date
from pathlib import Path
import json
import threading
import traceback

from PySide6.QtCore import Qt, QThread, Signal, QDate, QUrl, QSize, QSettings, QItemSelectionModel
from PySide6.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QSplitter, QFileDialog,
    QMessageBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QInputDialog,
    QComboBox, QCheckBox, QProgressBar, QPlainTextEdit, QDateEdit, QDoubleSpinBox,
    QFormLayout, QLineEdit, QHeaderView, QSizePolicy,
)

from .engine import SFaceEngine
from .exporting import make_zips, export_csv, backup
from .media import IMAGE_EXT, MEDIA_EXT
from .organize import Organizer
from .paths import inside
from .service import Service, Cancelled
from .store import Store, now
from .design import DesignMixin, action
from .widgets import ChildDialog


STATUS = {"review": "검토 필요", "confirmed": "확인 완료", "excluded": "제외", "no_face": "얼굴 없음", "error": "읽기 실패"}
OP_STATUS = {"planned": "대기", "copying": "복사 중/중단", "prepared": "확정 대기", "done": "완료", "error": "실패", "cancelled": "취소", "undoing": "되돌리는 중", "undone": "되돌림"}


class Worker(QThread):
    progress = Signal(int, int, str)

    def __init__(self, task):
        super().__init__()
        self.task, self.cancel = task, threading.Event()
        self.result = self.error = None

    def run(self):
        try:
            self.result = self.task(self.progress.emit, self.cancel)
        except Cancelled as exc:
            self.error = str(exc)
        except Exception:
            self.error = traceback.format_exc()


def button(text, callback):
    value = QPushButton(text)
    value.clicked.connect(callback)
    return value


def table(headers, multi=True):
    value = QTableWidget(0, len(headers))
    value.setHorizontalHeaderLabels(headers)
    value.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    value.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multi else QAbstractItemView.SelectionMode.SingleSelection)
    value.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    value.verticalHeader().hide()
    value.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    value.horizontalHeader().setStretchLastSection(True)
    return value


def set_row(widget, row, values, identifier=None):
    widget.insertRow(row)
    for col, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        if col == 0:
            item.setData(Qt.ItemDataRole.UserRole, identifier)
        widget.setItem(row, col, item)


def selected_ids(widget):
    if isinstance(widget, QListWidget):
        return [item.data(Qt.ItemDataRole.UserRole) for item in widget.selectedItems()]
    return [widget.item(index.row(), 0).data(Qt.ItemDataRole.UserRole) for index in widget.selectionModel().selectedRows()]


class Preview(QLabel):
    def __init__(self):
        super().__init__("사진을 선택하세요")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(260, 120)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.original = QPixmap()

    def show_file(self, path, box=None, annotations=()):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.original = QPixmap()
            self.setText("미리보기 없음")
            return
        if box or annotations:
            painter = QPainter(pixmap)
            painter.setPen(QPen(QColor("#22aa66"), max(2, pixmap.width()/250)))
            for bounds, name in ([(box, '')] if box else annotations):
                x1, y1, x2, y2 = bounds
                x, y, w, h = round(x1*pixmap.width()), round(y1*pixmap.height()), round((x2-x1)*pixmap.width()), round((y2-y1)*pixmap.height())
                painter.drawRoundedRect(x, y, w, h, 7, 7)
                if name:
                    font = QFont('Malgun Gothic'); font.setPixelSize(max(14, pixmap.width()//45)); font.setBold(True); painter.setFont(font)
                    text_width = painter.fontMetrics().horizontalAdvance(name)+12
                    text_height = painter.fontMetrics().height()+5
                    tx, ty = min(x,max(0,pixmap.width()-text_width)), min(y+h+3,pixmap.height()-text_height)
                    painter.fillRect(tx,ty,text_width,text_height,QColor('#e3ffdf'))
                    painter.drawText(tx+6,ty+painter.fontMetrics().ascent()+2,name)
            painter.end()
        self.original = pixmap
        self._fit()

    def _fit(self):
        if not self.original.isNull():
            self.setPixmap(self.original.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class ChildPicker(QDialog):
    def __init__(self, children, title="배정할 아이 선택", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(360, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("사진에 나온 아이를 모두 체크하세요."))
        self.list = QListWidget()
        for child in children:
            item = QListWidgetItem(f"{child['name']}  [{child['id'][:6]}]")
            item.setData(Qt.ItemDataRole.UserRole, child["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(self.accept)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)

    def ids(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.CheckState.Checked]


class MainWindow(DesignMixin, QMainWindow):
    def __init__(self, library=None, remember=True):
        super().__init__()
        self.settings = QSettings("PhotoJoy", "PhotoJoy")
        self.remember = remember
        self.store = self.service = self.organizer = self.worker = None
        self.current_media = None
        self.face_rows = []
        self.build_shell()
        initial = library or self.settings.value("library", "")
        if initial and (library or Path(initial).is_dir()):
            self.open_library(initial)

    def _children_tab(self):
        layout = self._tab("1. 아이 등록")
        layout.addWidget(QLabel("아이를 추가한 뒤 얼굴이 잘 보이는 참고 사진 3~5장을 등록하세요. 동명이인은 ID로 구분합니다."))
        row = QHBoxLayout()
        for label, callback in [("아이 추가", self.add_child), ("이름·그룹 수정", self.edit_child), ("졸업 / 복귀", self.toggle_child), ("참고 사진 등록", self.register_photos), ("등록 얼굴 관리", self.manage_references)]:
            row.addWidget(button(label, callback))
        layout.addLayout(row)
        self.children_table = table(["이름", "그룹", "참고 얼굴", "상태", "아이 ID"], False)
        self.children_table.itemDoubleClicked.connect(self.edit_child)
        layout.addWidget(self.children_table)

    def _review_tab(self):
        self.build_review_page(Preview, table)

    def _export_tab(self):
        layout = self._tab("3. ZIP·통계")
        row = QHBoxLayout()
        self.start_date = QDateEdit(QDate(2000, 1, 1))
        self.end_date = QDateEdit(QDate.currentDate().addYears(1))
        for widget in (self.start_date, self.end_date):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            widget.dateChanged.connect(self.refresh_stats)
        row.addWidget(QLabel("기간"))
        row.addWidget(self.start_date)
        row.addWidget(QLabel("~"))
        row.addWidget(self.end_date)
        row.addWidget(button("새로고침", self.refresh_stats))
        row.addWidget(button("CSV 저장", self.save_csv))
        layout.addLayout(row)
        self.stats_table = table(["아이", "사진", "영상", "합계", "최근 준비 / 발송 확인"])
        layout.addWidget(self.stats_table)
        row = QHBoxLayout()
        self.logo_label = QLabel("워터마크 없음")
        self.logo_path = None
        row.addWidget(self.logo_label, 1)
        row.addWidget(button("워터마크 PNG", self.choose_logo))
        row.addWidget(button("로고 해제", self.clear_logo))
        row.addWidget(button("선택 아이 ZIP", self.export_zips))
        row.addWidget(button("직접 보냈음 확인", self.mark_sent))
        row.addWidget(button("전송묶음 열기", self.open_exports))
        layout.addLayout(row)
        layout.addWidget(QLabel("ZIP은 자료 준비 상태입니다. 카카오톡·알림장 발송 후 '직접 보냈음 확인'으로 기록하세요."))

    def _history_tab(self):
        layout = self._tab("작업 이력")
        layout.addWidget(action('인식 설정 · 모델 진단', self.open_settings, 'gear'))
        self.history_table = table(["시간", "단위", "작업 수", "상태", "작업 ID"], False)
        layout.addWidget(self.history_table)
        row = QHBoxLayout()
        row.addWidget(button("중단·실패 작업 재시도", self.retry_batch))
        row.addWidget(button("선택 정리 되돌리기", self.undo_batch))
        row.addWidget(button("정리 폴더 열기", self.open_organized))
        row.addWidget(button("데이터 백업", self.make_backup))
        layout.addLayout(row)
        layout.addWidget(QLabel("되돌리기는 PhotoJoy가 만든 복사본에 적용됩니다. 원본이 없거나 정리본이 수정되면 보존합니다. 백업에는 원본 사진이 포함되지 않습니다."))

    def _settings_tab(self):
        layout = self._tab("설정·정보")
        self.model_label = QLabel("기본 엔진: OpenCV YuNet + SFace (CPU)")
        layout.addWidget(self.model_label)
        layout.addWidget(button("실제 얼굴 모델 로드 확인", self.check_model))
        form = QFormLayout()
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.1, .99)
        self.threshold.setSingleStep(.02)
        self.threshold.setValue(.50)
        self.margin = QDoubleSpinBox()
        self.margin.setRange(0, .5)
        self.margin.setSingleStep(.01)
        self.margin.setValue(.08)
        form.addRow("후보 승인 유사도", self.threshold)
        form.addRow("1·2위 최소 차이", self.margin)
        layout.addLayout(form)
        layout.addWidget(button("비교 설정 저장", self.save_settings))
        text = QLabel("PhotoJoy 0.2 · 모든 자료는 확인 후 정리합니다.\n유사도는 확률이 아니며 현재 기준은 실제 어린이 사진으로 보정되지 않았습니다.\n사진·영상 원본은 보존됩니다. 영상은 최대 8개 프레임만 분석합니다.\nHEIC 읽기를 지원합니다. MOV 변환·하이라이트·백업 복원 UI는 후속 버전 범위입니다.")
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addWidget(action('작업 이력으로 돌아가기', lambda: self.navigate(8), 'left'))
        layout.addStretch()

    def open_settings(self):
        self.tabs.setCurrentIndex(4)
        self.page_title.setText('인식 설정')
        self.page_description.setText('실제 얼굴 모델을 진단하고 미확정 후보의 비교 기준을 조정합니다.')

    def info(self, text):
        self.log.appendPlainText(text)

    def error(self, exc):
        self.info(str(exc))
        self.log.show()
        QMessageBox.warning(self, "PhotoJoy", str(exc))

    def choose_library(self):
        path = QFileDialog.getExistingDirectory(self, "PhotoJoy 작업 폴더 선택")
        if path:
            self.open_library(path)

    def open_library(self, path):
        try:
            self.store = Store(Path(path))
            self.service = Service(self.store)
            self.organizer = Organizer(self.store)
            if self.remember:
                self.settings.setValue("library", str(self.store.root))
            self.library_label.setText(str(self.store.root))
            self.library_label.setToolTip(str(self.store.root))
            self.tabs.setEnabled(True)
            self.threshold.setValue(self.store.get_setting("threshold", .50))
            self.margin.setValue(self.store.get_setting("margin", .08))
            self.refresh()
            self.navigate(2 if self._media_cache else 0)
            self.info("작업 폴더를 열었습니다. 아이 등록 → 분석 → 검토 → 정리 순서로 사용하세요.")
        except Exception as exc:
            self.error(exc)

    def run_job(self, title, task, callback=None):
        if self.worker:
            return
        self.info(title)
        self.tabs.setEnabled(False)
        self.choose_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress_title.setText(title)
        self.progress_label.setText('처리를 시작합니다…')
        worker = Worker(task)
        self.worker = worker
        worker.progress.connect(self.job_progress)

        def finished():
            self.worker = None
            self.tabs.setEnabled(True)
            self.choose_button.setEnabled(True)
            self.cancel_button.setEnabled(False)
            self.progress.setRange(0, 100)
            self.refresh()
            if worker.error:
                self.error(worker.error)
            elif callback:
                try:
                    callback(worker.result)
                except Exception as exc:
                    self.error(exc)
            else:
                self.info(f"완료: {worker.result}")
            worker.deleteLater()
        worker.finished.connect(finished)
        worker.start()

    def job_progress(self, current, total, text):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{text}  %p%")
        self.progress_label.setText(f'{text}  ·  {current:,} / {total:,}')

    def cancel_job(self):
        if self.worker:
            self.worker.cancel.set()
            self.cancel_button.setEnabled(False)
            self.info("현재 파일 처리의 안전한 지점에서 취소합니다.")

    def refresh(self):
        if not self.store:
            return
        selected_children = selected_ids(self.children_table)
        self.children_table.setRowCount(0)
        for i, c in enumerate(self.store.children(True)):
            set_row(self.children_table, i, [c["name"], c["group_name"], c["refs"], "등록" if c["active"] else "졸업", c["id"][:6]], c["id"])
            self.children_table.setRowHeight(i,48)
            if c['id'] in selected_children:
                self.children_table.selectRow(i)
        self.refresh_media()
        self.refresh_stats()
        self.refresh_history()

    def refresh_media(self):
        self.refresh_cards()

    def one_child(self):
        ids = selected_ids(self.children_table)
        if not ids:
            raise ValueError("아이 한 명을 선택하세요.")
        return next(c for c in self.store.children(True) if c["id"] == ids[0])

    def add_child(self):
        dialog = ChildDialog(self)
        if dialog.exec():
            try:
                child_id = self.store.add_child(*dialog.values())
                self.refresh()
                for row in range(self.children_table.rowCount()):
                    if self.children_table.item(row,0).data(Qt.ItemDataRole.UserRole)==child_id:
                        self.children_table.selectRow(row)
                        break
            except Exception as exc:
                self.error(exc)

    def edit_child(self):
        try:
            child = self.one_child()
            dialog = ChildDialog(self,child)
            if dialog.exec():
                name, group = dialog.values()
                self.store.update_child(child["id"], name, group, child["active"])
                self.refresh()
        except Exception as exc:
            self.error(exc)

    def toggle_child(self):
        try:
            child = self.one_child()
            self.store.update_child(child["id"], child["name"], child["group_name"], not child["active"])
            self.refresh()
        except Exception as exc:
            self.error(exc)

    def register_photos(self):
        try:
            child = self.one_child()
            if not child["active"]:
                raise ValueError("졸업한 아이는 먼저 복귀 처리하세요.")
            paths, _ = QFileDialog.getOpenFileNames(self, "참고 사진 선택", "", "사진 (" + " ".join("*"+e for e in IMAGE_EXT) + ")")
            queue = list(paths)

            def next_photo():
                if not queue:
                    self.refresh()
                    return
                path = Path(queue.pop(0))

                def ready(result):
                    faces, sha = result
                    if not faces:
                        self.info(f"얼굴을 찾지 못했습니다: {path.name}")
                    else:
                        dialog = QDialog(self)
                        dialog.setWindowTitle(f"{child['name']}의 얼굴 선택 — {path.name}")
                        layout = QVBoxLayout(dialog)
                        layout.addWidget(QLabel("등록할 아이의 얼굴 하나를 선택하세요."))
                        items = QListWidget()
                        items.setIconSize(QSize(100, 100))
                        from PySide6.QtGui import QImage
                        import cv2
                        for i, face in enumerate(faces):
                            rgb = cv2.cvtColor(face.crop, cv2.COLOR_BGR2RGB)
                            image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
                            item = QListWidgetItem(QIcon(QPixmap.fromImage(image)), f"얼굴 {i+1}")
                            items.addItem(item)
                        items.setCurrentRow(0)
                        layout.addWidget(items)
                        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
                        actions.accepted.connect(dialog.accept)
                        actions.rejected.connect(dialog.reject)
                        layout.addWidget(actions)
                        if dialog.exec() and items.currentRow() >= 0:
                            index = items.currentRow()
                            self.service.register(child["id"], path, faces[index], index, sha)
                            self.info(f"등록: {child['name']} / {path.name}")
                    next_photo()
                self.run_job(f"참고 얼굴 분석: {path.name}", lambda p, c: self.service.registration_candidates(path), ready)
            next_photo()
        except Exception as exc:
            self.error(exc)

    def manage_references(self):
        try:
            child = self.one_child()
            rows = self.store.rows("SELECT * FROM reference_faces WHERE child_id=? AND active=1 ORDER BY created", (child["id"],))
            dialog = QDialog(self)
            dialog.setWindowTitle(f"{child['name']} — 등록 얼굴 관리")
            layout = QVBoxLayout(dialog)
            items = QListWidget()
            items.setIconSize(QSize(80, 80))
            for row in rows:
                item = QListWidgetItem(QIcon(row["crop"]), f"{Path(row['source']).name}\n{row['engine'][:20]}")
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                items.addItem(item)
            layout.addWidget(items)
            def disable():
                item = items.currentItem()
                if item:
                    self.store.execute("UPDATE reference_faces SET active=0 WHERE id=?", (item.data(Qt.ItemDataRole.UserRole),))
                    items.takeItem(items.currentRow())
                    self.refresh()
            layout.addWidget(button("선택 특징 사용 중지", disable))
            layout.addWidget(button("닫기", dialog.accept))
            dialog.resize(430, 450)
            dialog.exec()
        except Exception as exc:
            self.error(exc)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "분석할 사진·영상", "", "미디어 (" + " ".join("*"+e for e in MEDIA_EXT) + ")")
        if paths:
            self.run_job("사진·영상 분석", lambda p, c: self.service.analyze(paths, p, c))

    def add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "분석할 폴더 (하위 폴더 포함)")
        if path:
            self.run_job("폴더 분석", lambda p, c: self.service.analyze([path], p, c))

    def rematch_all(self):
        paths = [r["path"] for r in self.store.media() if not r["reviewed"]]
        self.run_job("등록 얼굴로 후보 다시 비교", lambda p, c: self.service.analyze(paths, p, c))

    def media_selected(self):
        ids = selected_ids(self.media_table)
        current = self.media_table.currentItem()
        current_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.current_media = current_id if current_id in ids else (ids[0] if ids else None)
        self.face_table.setRowCount(0)
        self.face_rows = []
        self.selection_label.setText(f'선택 {len(ids)}개  ·  Ctrl+클릭으로 다중 선택')
        self.preview_position.setText(f'{self.media_table.currentRow()+1 if ids else 0} / {self.media_table.count()}')
        self.faces_title.setText('인식 결과')
        self.face_detail.setText('유사도는 확률이 아닙니다. 후보를 직접 확인해 주세요.')
        if not ids:
            self.preview.show_file("")
            self.media_info.clear()
            return
        row = self.store.one_media(self.current_media)
        self.media_info.setText(f"{Path(row['path']).name} · {row['captured']}" )
        self.media_info.setToolTip(row['path']+'\n'+row['error'])
        names = {c["id"]: c["name"] for c in self.store.children(True)}
        self.face_rows = self.store.faces(self.current_media)
        self.faces_title.setText(f'인식 결과 ({len(self.face_rows)}개 얼굴)')
        self.face_table.setColumnHidden(4,row['kind']=='photo')
        annotations = []
        for i, face in enumerate(self.face_rows):
            candidate = json.loads(face["candidate"])
            score = "—" if candidate["score"] is None else f"{candidate['score']:.3f}"
            candidate_name = names.get(candidate['child'],'미등록')
            set_row(self.face_table, i, [i+1, candidate_name, score, '후보' if candidate['accepted'] else '보류', "—" if face["frame"] is None else f"{face['frame']:.1f}"], face["id"])
            self.face_table.item(i, 0).setIcon(QIcon(face["crop"]))
            self.face_table.item(i, 3).setToolTip(candidate['reason'])
            self.face_table.setRowHeight(i, 39)
            if row['kind']=='photo':
                annotations.append((json.loads(face['bbox']),candidate_name))
        self.preview.show_file(row['thumbnail'],annotations=annotations)

    def face_selected(self):
        selected = self.face_table.currentRow()
        if 0 <= selected < len(self.face_rows):
            face = self.face_rows[selected]
            self.preview.show_file(face["preview"], json.loads(face["bbox"]))
            candidate = json.loads(face['candidate'])
            self.face_detail.setText(f"판단 근거: {candidate['reason']}")
            self.face_detail.setToolTip(self.face_detail.text())

    def open_source(self):
        if self.current_media:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.store.one_media(self.current_media)["path"]))

    def confirm(self):
        try:
            self.service.confirm_candidates(selected_ids(self.media_table))
            self.refresh()
        except Exception as exc:
            self.error(exc)

    def assign(self):
        ids = selected_ids(self.media_table)
        if not ids:
            return
        dialog = ChildPicker(self.store.children(), parent=self)
        if dialog.exec():
            try:
                self.store.review(ids, dialog.ids())
                self.refresh()
            except Exception as exc:
                self.error(exc)

    def exclude(self):
        self.store.review(selected_ids(self.media_table), [], excluded=True)
        self.refresh()

    def undo_review(self):
        try:
            for media_id in selected_ids(self.media_table):
                self.store.undo_review(media_id)
            self.refresh()
        except Exception as exc:
            self.error(exc)

    def learn_face(self):
        selected = selected_ids(self.face_table)
        children = self.store.children()
        if not selected or not children:
            return
        labels = [f"{c['name']} [{c['id'][:6]}]" for c in children]
        choice, ok = QInputDialog.getItem(self, "참고 얼굴 등록", "선택 얼굴의 실제 아이", labels, 0, False)
        if ok:
            self.service.learn_face(selected[0], children[labels.index(choice)]["id"])
            self.info("선택 얼굴만 등록했습니다. '미확정 후보 다시 비교'로 반영하세요.")
            self.refresh()

    def change_date(self):
        ids = selected_ids(self.media_table)
        if not ids:
            return
        value, ok = QInputDialog.getText(self, "날짜 수정", "YYYY-MM-DD", text=self.store.one_media(ids[0])["captured"])
        if ok:
            try:
                value = date.fromisoformat(value).isoformat()
                for media_id in ids:
                    self.store.execute("UPDATE media SET captured=?,date_source='사용자 지정' WHERE id=?", (value, media_id))
                self.refresh()
            except Exception as exc:
                self.error(exc)

    def organize(self):
        ids = selected_ids(self.media_table) or [r["id"] for r in self.store.confirmed()]
        unit = self.unit.currentData()
        def ready(plan):
            if not plan["operations"]:
                QMessageBox.information(self, "PhotoJoy", "새로 정리할 자료가 없습니다. 먼저 결과를 확인·배정하세요.")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("정리 계획 — 원본 보존 복사")
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(f"복사 {len(plan['operations'])}개 · 이미 정리됨 {plan['skipped']}개"))
            listing = QPlainTextEdit()
            listing.setReadOnly(True)
            listing.setPlainText("\n\n".join(f"{op['source']}\n→ {op['destination']}" for op in plan["operations"]))
            layout.addWidget(listing)
            actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            actions.accepted.connect(dialog.accept)
            actions.rejected.connect(dialog.reject)
            layout.addWidget(actions)
            dialog.resize(850, 500)
            if dialog.exec():
                batch = self.organizer.create_batch(plan)
                self.run_job("원본 보존 정리", lambda p, c: self.organizer.run(batch, p, c))
        self.run_job("정리 계획 계산", lambda p, c: self.organizer.plan(ids, unit), ready)

    def dates(self):
        values = [self.start_date.date().toString("yyyy-MM-dd"), self.end_date.date().toString("yyyy-MM-dd")]
        return sorted(values)

    def refresh_stats(self):
        if not self.store:
            return
        start, end = self.dates()
        self.stats_table.setRowCount(0)
        selected = selected_ids(self.summary_table) if hasattr(self,'summary_table') else []
        if hasattr(self,'summary_table'):
            self.summary_table.setRowCount(0)
        for i, child in enumerate(self.store.statistics(start, end)):
            exports = self.store.rows("SELECT * FROM exports WHERE child_id=? AND start=? AND end=? ORDER BY rowid DESC LIMIT 1", (child["id"], start, end))
            status = "미준비" if not exports else ("직접 발송 확인: " + exports[0]["sent_at"] if exports[0]["sent_at"] else "ZIP 준비됨")
            total = child["photos"]+child["videos"]
            set_row(self.stats_table, i, [child["name"], child["photos"], child["videos"], total, status], child["id"])
            self.stats_table.setRowHeight(i,44)
            if hasattr(self,'summary_table'):
                set_row(self.summary_table,i,[child['name'],child['photos'],child['videos'],total],child['id'])
                self.summary_table.setRowHeight(i,44)
            if not total:
                for col in range(5):
                    self.stats_table.item(i, col).setForeground(QColor("#b42318"))
        if hasattr(self,'month_chart'):
            from collections import Counter
            counts = Counter(row['captured'][:7] for row in self.store.confirmed(start,end))
            self.month_chart.set_values(sorted(counts.items()))
            self.statistics_heading.setText(f'확인 완료 자료 · {start} ~ {end} (최근 촬영 6개월 표시)')

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "워터마크 로고", "", "PNG (*.png)")
        if path:
            self.logo_path = path
            self.logo_label.setText(Path(path).name)

    def clear_logo(self):
        self.logo_path = None
        self.logo_label.setText("워터마크 없음")

    def export_zips(self):
        children = selected_ids(self.stats_table)
        if not children:
            self.error("ZIP을 만들 아이를 선택하세요. 여러 아이는 Ctrl+클릭으로 선택합니다.")
            return
        start, end = self.dates()
        logo = self.logo_path
        self.run_job("아이별 ZIP 준비", lambda p, c: make_zips(self.store, children, start, end, logo, p, c))

    def mark_sent(self):
        start, end = self.dates()
        for child in selected_ids(self.stats_table):
            rows = self.store.rows("SELECT id FROM exports WHERE child_id=? AND start=? AND end=? ORDER BY rowid DESC LIMIT 1", (child, start, end))
            if rows:
                self.store.execute("UPDATE exports SET sent_at=? WHERE id=?", (now(), rows[0]["id"]))
        self.refresh_stats()

    def save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "통계 CSV", "PhotoJoy_통계.csv", "CSV (*.csv)")
        if path:
            export_csv(self.store, path, *self.dates())
            self.info(f"CSV 저장: {path}")

    def refresh_history(self):
        self.history_table.setRowCount(0)
        for i, batch in enumerate(self.store.rows("SELECT * FROM batches ORDER BY rowid DESC")):
            statuses = self.store.rows("SELECT state,COUNT(*) AS n FROM file_operations WHERE batch_id=? GROUP BY state", (batch["id"],))
            text = ", ".join(f"{OP_STATUS.get(s['state'],s['state'])} {s['n']}" for s in statuses)
            set_row(self.history_table, i, [batch["created"], "일별" if batch["unit"] == "day" else "주차별", sum(s["n"] for s in statuses), text, batch["id"][:8]], batch["id"])

    def retry_batch(self):
        ids = selected_ids(self.history_table)
        if ids:
            self.run_job("정리 작업 재시도", lambda p, c: self.organizer.run(ids[0], p, c))

    def undo_batch(self):
        ids = selected_ids(self.history_table)
        if ids and QMessageBox.question(self, "정리 되돌리기", "선택 작업이 만든 복사본을 제거할까요? 원본을 확인할 수 없는 항목과 수정된 파일은 보존합니다.") == QMessageBox.StandardButton.Yes:
            self.run_job("정리 되돌리기", lambda p, c: self.organizer.undo(ids[0], p, c))

    def make_backup(self):
        self.run_job("DB·참고 얼굴·미리보기 백업 (원본 제외)", lambda p, c: backup(self.store))

    def open_exports(self):
        self.open_folder("전송묶음")

    def open_organized(self):
        self.open_folder("정리")

    def open_folder(self, name):
        folder = inside(self.store.root, self.store.root / name)
        folder.mkdir(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def check_model(self):
        def task(p, c):
            self.service.engine.load()
            return self.service.engine.fingerprint
        self.run_job("실제 모델 로드 확인", task, lambda value: self.model_label.setText(f"모델 로드 성공 · {value}"))

    def save_settings(self):
        self.store.set_setting("threshold", self.threshold.value())
        self.store.set_setting("margin", self.margin.value())
        self.info("저장했습니다. 미확정 후보 다시 비교를 실행하면 반영됩니다.")

    def closeEvent(self, event):
        if self.worker:
            self.cancel_job()
            self.info("작업 취소가 끝난 뒤 창을 닫아주세요.")
            event.ignore()
        else:
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'quick_panel'):
            self.quick_panel.setVisible(self.height() >= 860)
