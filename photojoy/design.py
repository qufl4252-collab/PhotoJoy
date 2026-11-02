"""PhotoJoy's navigation and reference-inspired review layout."""
import json
from collections import Counter
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QItemSelectionModel
from PySide6.QtGui import QPixmap, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QSplitter, QComboBox, QLineEdit, QListWidgetItem, QProgressBar,
    QPlainTextEdit, QSizeGrip, QSizePolicy, QButtonGroup, QHeaderView, QMenu,
)
from .widgets import TitleBar, BrandArt, PhotoCards, CARD_ROLE, MonthChart, panel, label
from .theme import STYLE, icon
from .guide import GuideDialog


NAV = [
    ('최초 설정', 'gear', 5, '작업 폴더를 선택하고 아이들의 참고 얼굴을 준비하세요.'),
    ('사진 분류', 'image', 6, '사진과 영상을 추가하면 등록된 얼굴을 기준으로 후보를 찾습니다.'),
    ('결과 검토', 'check', 1, '분류된 사진을 확인하고, 아이별로 올바르게 배정되었는지 검토하세요.'),
    ('교정', 'edit', 1, '보류된 사진을 확인하고 실제 등장한 아이를 직접 배정하세요.'),
    ('정리 계획', 'folder', 7, '복사할 자료와 대상 폴더를 확인한 뒤 원본을 보존하며 정리합니다.'),
    ('아이 관리', 'people', 0, '아이 정보와 참고 얼굴을 등록하고 관리하세요.'),
    ('보내기 준비', 'send', 2, '기간과 아이를 선택하여 ZIP 파일을 준비하세요.'),
    ('통계', 'chart', 8, '확인한 사진·영상 수량과 아이별 현황을 살펴보세요.'),
    ('작업 이력·설정', 'clock', 3, '작업 결과를 확인하고 재시도·되돌리기·백업을 관리하세요.'),
]


def action(text, callback, symbol=None, primary=False):
    button = QPushButton(text)
    if symbol:
        button.setIcon(icon(symbol, '#ffffff' if primary else '#6285a3', 19))
    if primary:
        button.setObjectName('primary')
    button.clicked.connect(callback)
    return button


class DesignMixin:
    def build_shell(self):
        self.setWindowTitle('PhotoJoy 0.2 — 아이 사진 정리')
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowIcon(icon('camera', '#168df0', 48))
        self.setStyleSheet(STYLE)
        self.setFont(QFont('Malgun Gothic', 10))
        self.setMinimumSize(1180, 740)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1510, available.width()-40), min(940, available.height()-40))
        self.guide_dialog = None
        self.review_filter = 'all'
        self.current_nav = 0
        self._media_cache, self._face_cache = [], {}
        root = QWidget(); root.setObjectName('shell'); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(1,1,1,1); outer.setSpacing(0)
        self.titlebar = TitleBar(self); outer.addWidget(self.titlebar)
        body = QHBoxLayout(); body.setSpacing(0); body.setContentsMargins(0,0,0,0)
        outer.addLayout(body,1)
        sidebar = QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(211)
        side = QVBoxLayout(sidebar); side.setContentsMargins(13,8,13,6); side.setSpacing(5)
        side.addWidget(BrandArt())
        brand = label('PhotoJoy', 'brand'); brand.setAlignment(Qt.AlignmentFlag.AlignCenter); side.addWidget(brand)
        tagline = label('아이들의 순간을 모으다', 'muted'); tagline.setAlignment(Qt.AlignmentFlag.AlignCenter); side.addWidget(tagline)
        side.addSpacing(15)
        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for index, (text, symbol, _, _) in enumerate(NAV):
            control = action(text, lambda checked=False, n=index: self.navigate(n), symbol)
            control.setObjectName('nav'); control.setCheckable(True); control.setIconSize(QSize(23,23))
            self.nav_group.addButton(control); self.nav_buttons.append(control); side.addWidget(control)
        side.addStretch()
        side.addWidget(BrandArt(school=True))
        tagline = label('원본 보존  ·  PC 안에서 처리', 'muted'); tagline.setAlignment(Qt.AlignmentFlag.AlignCenter); side.addWidget(tagline)
        body.addWidget(sidebar)
        main = QWidget(); main_layout = QVBoxLayout(main); main_layout.setContentsMargins(17,10,17,6); main_layout.setSpacing(12)
        body.addWidget(main,1)
        header = QHBoxLayout(); header.setSpacing(12)
        self.page_icon = QLabel(); self.page_icon.setFixedSize(44,44); header.addWidget(self.page_icon)
        titles = QVBoxLayout(); titles.setSpacing(4)
        self.page_title = label('최초 설정', 'pageTitle'); titles.addWidget(self.page_title)
        self.page_description = label('', 'muted'); self.page_description.setWordWrap(True); titles.addWidget(self.page_description)
        header.addLayout(titles,1)
        self.header_actions = QWidget(); header_actions = QHBoxLayout(self.header_actions); header_actions.setContentsMargins(0,0,0,0)
        header_actions.addWidget(action('다시 비교', self.rematch_all, 'refresh'))
        header_actions.addWidget(action('결과 폴더', self.open_organized, 'folder'))
        header_actions.addWidget(action('정리로 이동', lambda: self.navigate(4), 'check', True))
        header.addWidget(self.header_actions)
        self.choose_button = action('작업 폴더 선택', self.choose_library, 'folder')
        header.addWidget(self.choose_button)
        main_layout.addLayout(header)

        summary, line = panel(QHBoxLayout); line.setSpacing(20)
        progress_column = QVBoxLayout(); progress_column.setSpacing(8)
        self.progress_title = label('사진 정리 준비', 'sectionTitle'); progress_column.addWidget(self.progress_title)
        self.progress_label = label('작업 폴더를 선택하면 시작할 수 있습니다.', 'muted'); progress_column.addWidget(self.progress_label)
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); self.progress.setTextVisible(False)
        progress_column.addWidget(self.progress); line.addLayout(progress_column,3)
        self.metric_labels = []
        for title, symbol in [('전체 자료','image'), ('등록 아이','people'), ('촬영 기간','clock')]:
            metric = QVBoxLayout(); metric.setSpacing(3)
            heading = label(title, 'muted'); metric.addWidget(heading)
            value = label('—', 'metric'); metric.addWidget(value); self.metric_labels.append(value)
            line.addLayout(metric,2 if symbol=='clock' else 1)
        main_layout.addWidget(summary)
        self.tabs = QStackedWidget(); main_layout.addWidget(self.tabs,1)
        self._children_tab(); self._review_tab(); self._export_tab(); self._history_tab(); self._settings_tab()
        self._setup_page(); self._import_page(); self._plan_page(); self._statistics_page()
        self.library_label = label('작업 폴더 미선택', 'muted')
        self.library_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.library_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        footer = QHBoxLayout(); footer.addWidget(self.library_label,1)
        self.log_toggle = action('작업 메시지', self.toggle_log)
        self.cancel_button = action('작업 취소', self.cancel_job); self.cancel_button.setEnabled(False)
        footer.addWidget(self.log_toggle); footer.addWidget(self.cancel_button); footer.addWidget(QSizeGrip(self))
        main_layout.addLayout(footer)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(82); self.log.hide(); main_layout.addWidget(self.log)
        self.help_shortcut = QShortcut(QKeySequence('F1'), self); self.help_shortcut.activated.connect(self.show_guide)
        self.navigate(0)

    def _tab(self, title):
        widget = QWidget(); layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(12)
        self.tabs.addWidget(widget)
        return layout

    def navigate(self, index):
        if self.worker:
            return
        if not self.store and index != 0:
            index = 0
        self.current_nav = index
        title, symbol, page, description = NAV[index]
        self.page_title.setText(title); self.page_description.setText(description)
        self.page_icon.setPixmap(icon(symbol,'#168df0',42).pixmap(42,42))
        self.nav_buttons[index].setChecked(True)
        for i, control in enumerate(self.nav_buttons):
            control.setIcon(icon(NAV[i][1], '#ffffff' if i == index else '#6387a4', 23))
        self.tabs.setCurrentIndex(page)
        self.header_actions.setVisible(index in (2,3))
        self.choose_button.setVisible(index not in (2,3))
        if index in (2,3):
            self.set_review_filter('pending' if index == 3 else 'all')
        if index == 4:
            self.update_plan_summary()

    def toggle_log(self):
        self.log.setVisible(not self.log.isVisible())

    def show_guide(self):
        chapter = {0:0,1:2,2:3,3:3,4:4,5:1,6:5,7:5,8:6}.get(self.current_nav,0)
        if self.guide_dialog is None:
            self.guide_dialog = GuideDialog(self, chapter)
            self.guide_dialog.navigate.connect(self.navigate)
        self.guide_dialog.topics.setCurrentRow(chapter)
        self.guide_dialog.show(); self.guide_dialog.raise_(); self.guide_dialog.activateWindow()

    def _setup_page(self):
        layout = self._tab('최초 설정')
        welcome, box = panel(); box.addWidget(label('반가워요, PhotoJoy입니다.', 'pageTitle'))
        box.addWidget(label('작업 폴더와 참고 얼굴을 준비하면 사진 정리를 시작할 수 있어요.', 'muted'))
        self.setup_status = label('1. 정리본과 데이터를 저장할 작업 폴더를 선택하세요.', 'sectionTitle')
        self.setup_status.setWordWrap(True); box.addWidget(self.setup_status)
        row = QHBoxLayout(); row.addWidget(action('작업 폴더 선택', self.choose_library, 'folder', True))
        row.addWidget(action('아이 등록으로 이동', lambda: self.navigate(5), 'people')); row.addStretch(); box.addLayout(row)
        layout.addWidget(welcome)
        for title, body in [('01  아이 등록', '이름을 입력하고 해당 아이의 참고 얼굴 사진 3~5장을 등록하세요.'), ('02  사진 분석과 검토', '사진·영상을 추가하고 자동 후보가 맞는지 확인하세요.'), ('03  원본 보존 정리', '확인된 자료를 아이별로 복사하고 ZIP으로 준비하세요.')]:
            card, line = panel(); line.addWidget(label(title,'sectionTitle')); line.addWidget(label(body,'muted')); layout.addWidget(card)
        layout.addStretch(); layout.addWidget(action('처음 사용하는 분을 위한 가이드', self.show_guide, 'book'))

    def _import_page(self):
        layout = self._tab('사진 분류')
        card, box = panel(); box.setContentsMargins(40,32,40,32)
        picture = QLabel(); picture.setPixmap(icon('image','#5caff1',68).pixmap(68,68)); picture.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(picture)
        title = label('정리할 사진과 영상을 불러오세요', 'pageTitle'); title.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(title)
        subtitle = label('JPG · PNG · HEIC · MP4 · MOV 등  /  폴더 안의 자료도 함께 분석합니다.', 'muted'); subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(subtitle)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(action('사진·영상 추가', self.add_files, 'plus', True)); row.addWidget(action('폴더 분석', self.add_folder, 'folder')); row.addStretch(); box.addLayout(row)
        layout.addWidget(card)
        note, box = panel(soft=True); box.addWidget(label('분석 전에 확인해 주세요', 'sectionTitle'))
        text = label('아이 관리에서 참고 얼굴을 등록하면 이름 후보를 찾을 수 있습니다.\n영상은 최대 8개 프레임을 확인하므로 짧게 등장한 아이가 빠질 수 있습니다.\n분석이 끝나면 결과 검토에서 후보를 확인한 뒤 정리하세요.', 'muted'); text.setWordWrap(True); box.addWidget(text)
        layout.addWidget(note); layout.addStretch()
        row = QHBoxLayout(); row.addStretch(); row.addWidget(action('결과 검토로 이동', lambda: self.navigate(2), 'check', True)); layout.addLayout(row)

    def build_review_page(self, Preview, table):
        layout = self._tab('결과 검토')
        split = QSplitter(); split.setChildrenCollapsible(False)
        left, content = panel(); content.setContentsMargins(10,10,10,10); left.setMinimumWidth(480)
        filters = QHBoxLayout(); filters.setSpacing(5); self.filter_buttons = {}; self.filter_group = QButtonGroup(self)
        for key, text in [('all','전체'),('candidate','자동 승인 후보'),('pending','검토 필요'),('confirmed','확인 완료')]:
            control = action(text, lambda checked=False,k=key:self.set_review_filter(k)); control.setObjectName('filter'); control.setCheckable(True)
            self.filter_group.addButton(control); self.filter_buttons[key]=control; filters.addWidget(control)
        content.addLayout(filters)
        toolbar = QHBoxLayout(); self.media_search = QLineEdit(); self.media_search.setPlaceholderText('파일명 · 아이 이름 검색'); self.media_search.setClearButtonEnabled(True)
        self.media_search.textChanged.connect(self.render_cards); toolbar.addWidget(self.media_search,1)
        self.sort_order = QComboBox(); self.sort_order.addItems(['촬영일순 (최신순)','촬영일순 (오래된순)','파일명순']); self.sort_order.currentIndexChanged.connect(self.render_cards); toolbar.addWidget(self.sort_order)
        toolbar.addWidget(action('', lambda:self.media_table.set_card_mode(True),'grid'))
        toolbar.itemAt(toolbar.count()-1).widget().setToolTip('카드 보기')
        toolbar.addWidget(action('', lambda:self.media_table.set_card_mode(False),'list'))
        toolbar.itemAt(toolbar.count()-1).widget().setToolTip('목록 보기')
        content.addLayout(toolbar)
        self.media_table = PhotoCards(); self.media_table.itemSelectionChanged.connect(self.media_selected); self.media_table.itemDoubleClicked.connect(self.open_source)
        content.addWidget(self.media_table,1)
        self.empty_label = label('사진 분류에서 사진·영상을 추가해 주세요.', 'muted'); self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter); content.addWidget(self.empty_label)
        self.selection_label = label('Ctrl+클릭으로 여러 사진을 선택할 수 있습니다.', 'muted'); content.addWidget(self.selection_label)
        split.addWidget(left)
        right, box = panel(); right.setMinimumWidth(350); box.setContentsMargins(12,12,12,12); box.setSpacing(6)
        right.setStyleSheet('QPushButton {padding:4px 8px; min-height:18px;}')
        top = QHBoxLayout(); top.addWidget(label('선택한 사진 미리보기','sectionTitle'),1)
        top.addWidget(action('',lambda:self.move_media(-1),'left')); self.preview_position = label('0 / 0','muted'); top.addWidget(self.preview_position); top.addWidget(action('',lambda:self.move_media(1),'right')); box.addLayout(top)
        self.preview = Preview(); box.addWidget(self.preview,3)
        self.media_info = label('사진을 선택하면 인식 결과가 표시됩니다.', 'muted'); self.media_info.setFixedHeight(22); self.media_info.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed); box.addWidget(self.media_info)
        row = QHBoxLayout(); self.faces_title = label('인식 결과','sectionTitle'); row.addWidget(self.faces_title,1); row.addWidget(action('직접 배정', self.assign, 'edit'))
        more = QPushButton('···'); more.setFixedWidth(34); more.setToolTip('선택 얼굴의 추가 작업')
        menu = QMenu(more); menu.addAction('선택 얼굴을 참고 얼굴로 등록',self.learn_face); more.setMenu(menu); row.addWidget(more); box.addLayout(row)
        self.face_table = table(['얼굴','후보 이름','유사도','판단','영상 초'], False)
        self.face_table.setIconSize(QSize(32,32)); self.face_table.setMaximumHeight(150); self.face_table.setMinimumHeight(114)
        self.face_table.horizontalHeader().setFixedHeight(32)
        self.face_table.horizontalHeader().setDefaultSectionSize(70)
        self.face_table.itemSelectionChanged.connect(self.face_selected); box.addWidget(self.face_table,1)
        self.face_detail = label('유사도는 확률이 아닙니다. 후보를 직접 확인해 주세요.','muted'); self.face_detail.setFixedHeight(22); self.face_detail.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed); box.addWidget(self.face_detail)
        split.addWidget(right); split.setSizes([690,440]); layout.addWidget(split,1)
        actions = QHBoxLayout()
        actions.addWidget(action('후보대로 확인',self.confirm,'check',True)); actions.addWidget(action('직접 배정',self.assign,'edit')); actions.addWidget(action('정리 대상에서 제외',self.exclude))
        actions.addStretch(); actions.addWidget(action('교정 취소',self.undo_review,'refresh')); actions.addWidget(action('날짜 수정',self.change_date,'clock')); layout.addLayout(actions)
        quick, row = panel(QHBoxLayout, soft=True); row.setContentsMargins(12,10,12,10)
        self.quick_panel = quick
        self.quick_labels = []
        for title, text, symbol, target in [('아이 관리','참고 얼굴을 등록하고 관리해요.','people',5),('정리 계획','확인한 자료를 아이별로 복사해요.','folder',4),('통계','사진과 영상 수량을 확인해요.','chart',7)]:
            card, box = panel(); box.setContentsMargins(12,7,12,7)
            box.addWidget(action(title, lambda checked=False,n=target:self.navigate(n),symbol))
            detail = label(text,'muted'); box.addWidget(detail); self.quick_labels.append(detail); row.addWidget(card,1)
        layout.addWidget(quick)
        quick.setVisible(self.height() >= 860)

    def _plan_page(self):
        layout = self._tab('정리 계획')
        card, box = panel(); box.addWidget(label('확인한 자료를 안전하게 정리하세요', 'sectionTitle'))
        self.plan_summary = label('', 'muted'); self.plan_summary.setWordWrap(True); box.addWidget(self.plan_summary)
        row = QHBoxLayout(); self.unit = QComboBox(); self.unit.addItem('일별 정리','day'); self.unit.addItem('주차별 정리','week'); row.addWidget(self.unit)
        row.addWidget(action('정리 계획 확인·실행',self.organize,'folder',True)); row.addWidget(action('결과 폴더 열기',self.open_organized,'folder')); row.addStretch(); box.addLayout(row)
        layout.addWidget(card)
        card, box = panel(soft=True); box.addWidget(label('폴더 구성 예시', 'sectionTitle'))
        box.addWidget(label('작업 폴더\n  └ 정리\n      └ 아이 이름_고유ID\n          └ 촬영 날짜 또는 주차\n              └ 사진·영상 복사본'))
        box.addWidget(label('실제 복사 경로는 실행 전 정리 계획에서 확인할 수 있습니다.\n원본은 보존하며, 이미 정리한 같은 자료는 건너뜁니다.','muted')); layout.addWidget(card)
        layout.addStretch(); layout.addWidget(action('작업 이력에서 재시도·되돌리기',lambda:self.navigate(8),'clock'))

    def update_plan_summary(self):
        if not self.store:
            return
        count = len(self.store.confirmed()); selected = len(self.media_table.selectedItems())
        self.plan_summary.setText(f'확인 완료 {count:,}개  ·  현재 선택 {selected:,}개\n선택한 자료가 있으면 해당 자료를, 선택이 없으면 확인 완료된 전체 자료를 대상으로 계획합니다.')

    def _statistics_page(self):
        layout = self._tab('통계')
        card, box = panel(); self.statistics_heading = label('확인 완료 자료 집계','sectionTitle'); box.addWidget(self.statistics_heading)
        self.month_chart = MonthChart(); box.addWidget(self.month_chart); layout.addWidget(card)
        from .ui import table
        self.summary_table = table(['아이','사진','영상','합계']); layout.addWidget(self.summary_table,1)
        row = QHBoxLayout(); row.addWidget(action('기간 변경 · ZIP 준비',lambda:self.navigate(6),'send')); row.addWidget(action('CSV 저장',self.save_csv,'chart')); layout.addLayout(row)

    def set_review_filter(self, category):
        self.review_filter = category
        if hasattr(self,'filter_buttons'):
            self.filter_buttons[category].setChecked(True)
            self.render_cards()

    def refresh_cards(self):
        self._media_cache = self.store.media()
        self._face_cache = {}
        for face in self.store.rows('SELECT * FROM faces ORDER BY frame,id'):
            self._face_cache.setdefault(face['media_id'],[]).append(face)
        self._child_names = {c['id']:c['name'] for c in self.store.children(True)}
        counts = Counter(self.card_category(row) for row in self._media_cache)
        for key, control in self.filter_buttons.items():
            title = {'all':'전체','candidate':'자동 승인 후보','pending':'검토 필요','confirmed':'확인 완료'}[key]
            control.setText(f'{title} ({len(self._media_cache) if key=="all" else counts[key]:,})')
        self.render_cards()
        self.update_dashboard()

    def card_category(self, row):
        if row['status']=='confirmed': return 'confirmed'
        if row['status']=='excluded': return 'excluded'
        faces = self._face_cache.get(row['id'],[])
        if faces and all(json.loads(f['candidate']).get('accepted',False) for f in faces): return 'candidate'
        return 'pending'

    def render_cards(self, *_):
        if not hasattr(self,'media_table') or not self.store:
            return
        selected = {i.data(Qt.ItemDataRole.UserRole) for i in self.media_table.selectedItems()}
        current = self.current_media
        query = self.media_search.text().casefold().strip()
        rows = []
        for row in self._media_cache:
            category = self.card_category(row)
            ids = json.loads(row['assignments']) if row['reviewed'] else [json.loads(f['candidate']).get('child') for f in self._face_cache.get(row['id'],[])]
            names = ', '.join(dict.fromkeys(self._child_names.get(i,'') for i in ids if i))
            if self.review_filter != 'all' and category != self.review_filter: continue
            if query and query not in (Path(row['path']).name+' '+names).casefold(): continue
            rows.append((row,category,names))
        order = self.sort_order.currentIndex()
        rows.sort(key=lambda x:(Path(x[0]['path']).name.casefold() if order==2 else x[0]['captured'],x[0]['path']),reverse=order==0)
        self.media_table.blockSignals(True); self.media_table.clear()
        for row, category, names in rows:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole,row['id'])
            badge = {'confirmed':'✓ 확인 완료','candidate':'✓ 자동 승인 후보','pending':'? 검토 필요','excluded':'제외'}.get(category)
            if row['status'] in ('no_face','error'): badge = '얼굴 없음' if row['status']=='no_face' else '읽기 실패'
            pixmap = QPixmap(row['thumbnail'])
            if not pixmap.isNull(): pixmap = pixmap.scaled(420,300,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
            item.setData(CARD_ROLE,dict(category=category,badge=badge,date=row['captured'],kind='사진' if row['kind']=='photo' else '영상',names=names,filename=Path(row['path']).name,pixmap=pixmap))
            item.setToolTip(Path(row['path']).name+'\n'+names)
            self.media_table.addItem(item)
            if row['id'] in selected: item.setSelected(True)
            if row['id'] == current:
                self.media_table.setCurrentItem(item,QItemSelectionModel.SelectionFlag.NoUpdate)
        self.media_table.blockSignals(False)
        self.empty_label.setVisible(not rows)
        self.empty_label.setText('조건에 맞는 자료가 없습니다.' if self._media_cache else '사진 분류에서 사진·영상을 추가해 주세요.')
        self.media_selected()

    def move_media(self, offset):
        count = self.media_table.count()
        if count:
            self.media_table.setCurrentRow(max(0,min(count-1,self.media_table.currentRow()+offset)))

    def update_dashboard(self):
        if not self.store:
            return
        rows = self._media_cache; children = self.store.children()
        confirmed = sum(r['status']=='confirmed' for r in rows)
        errors = sum(r['status']=='error' for r in rows)
        self.metric_labels[0].setText(f'{len(rows):,}개')
        self.metric_labels[1].setText(f'{len(children):,}명')
        dates = sorted(r['captured'] for r in rows)
        self.metric_labels[2].setText(f'{dates[0]} ~ {dates[-1]}' if dates else '—')
        self.metric_labels[2].setStyleSheet('font-size:13px;font-weight:600;')
        if not self.worker:
            self.progress_title.setText('사진 분석·검토 현황')
            self.progress_label.setText(f'분석 자료 {len(rows):,}개  ·  확인 완료 {confirmed:,}개  ·  읽기 실패 {errors:,}개')
            self.progress.setRange(0,100); self.progress.setValue(round(100*confirmed/len(rows)) if rows else 0)
        self.setup_status.setText(f'작업 폴더 준비 완료 · 등록 아이 {len(children)}명\n{self.store.root}')
        self.quick_labels[0].setText(f'등록 아이 {len(children)}명 · 참고 얼굴을 관리해요.')
        self.quick_labels[1].setText(f'확인 완료 {confirmed}개 · 복사 계획을 살펴봐요.')
        self.quick_labels[2].setText(f'전체 자료 {len(rows)}개 · 아이별 수량을 확인해요.')
