from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QTextBrowser, QPushButton
from .widgets import label


CHAPTERS = [
    ('처음 시작하기', 0, '사진 정리, 이 순서로 시작하세요', '''
    <p>PhotoJoy는 사진과 영상을 아이별로 찾아서 정리하는 프로그램입니다. 얼굴 분석은 이 PC 안에서 처리됩니다.</p>
    <ol><li><b>최초 설정</b>에서 작업 폴더를 고릅니다. PhotoJoy 데이터와 정리본이 저장될 곳입니다.</li>
    <li><b>아이 관리</b>에서 아이를 추가하고 참고 얼굴 사진을 등록합니다.</li>
    <li><b>사진 분류</b>에서 정리할 사진·영상 또는 폴더를 추가합니다.</li>
    <li><b>결과 검토</b>에서 후보를 확인하고 틀린 배정을 교정합니다.</li>
    <li><b>정리 계획</b>에서 복사 계획을 확인하고 정리합니다.</li>
    <li><b>보내기 준비</b>에서 아이별 ZIP을 만듭니다.</li></ol>
    <p>처음에는 적은 양으로 사용 흐름을 확인하세요. 정리는 원본을 보존하고 복사본을 만듭니다.</p>'''),
    ('아이 등록 · 한글 입력', 5, '이름과 참고 얼굴 등록하기', '''
    <ol><li><b>아이 추가</b>를 누르고 이름과 그룹 메모를 적은 뒤 <b>저장</b>합니다.</li>
    <li>영문만 나오면 <b>한글 입력 켜기</b>를 누른 뒤 이름칸에서 다시 입력하세요. <b>한글 직접 입력 (두벌식)</b> 모드가 켜지며 Windows 입력기가 응답하지 않아도 이름을 조합합니다. 영문을 입력하려면 해당 체크를 해제하세요.</li>
    <li>아이 행을 선택하고 <b>참고 사진 등록</b>을 누릅니다.</li>
    <li>얼굴이 여러 개면 등록할 아이의 얼굴을 직접 골라 확인합니다.</li></ol>
    <p>정면·약간 다른 각도에서 얼굴이 크게 나온 사진 3~5장을 권장합니다. 얼굴을 찾지 못한 사진은 등록되지 않습니다.</p>
    <p>이름 수정은 <b>이름·그룹 수정</b> 또는 아이 행 더블클릭으로 할 수 있습니다. 이름이 같은 아이도 고유 ID로 구분합니다.</p>
    <p><b>등록 얼굴 관리</b>에서 잘못 등록한 얼굴의 사용을 중지할 수 있습니다. 졸업 처리는 아이를 새 후보 비교에서 제외합니다.</p>'''),
    ('사진 · 영상 분석', 1, '정리할 자료 불러오기', '''
    <ol><li><b>사진·영상 추가</b>로 파일을 고르거나 <b>폴더 분석</b>으로 하위 폴더까지 읽습니다.</li>
    <li>상단 진행 상태를 확인합니다. 오래 걸리면 <b>작업 취소</b>로 안전한 지점에서 중단합니다.</li>
    <li>완료되면 <b>결과 검토</b>로 이동합니다.</li></ol>
    <p>이미 분석한 동일 파일은 캐시를 사용합니다. 참고 얼굴을 추가한 뒤에는 <b>다시 비교</b>를 눌러 미확정 후보를 갱신하세요.</p>
    <p>영상은 최대 8개 프레임에서 얼굴을 찾습니다. 잠깐 등장한 아이는 누락될 수 있으니 직접 확인하세요.</p>'''),
    ('결과 검토 · 교정', 2, '사진마다 배정할 아이 확인하기', '''
    <p>사진 카드를 클릭하면 오른쪽에 큰 미리보기와 얼굴별 후보가 나타납니다. 얼굴 행을 클릭하면 해당 얼굴의 위치를 표시합니다.</p>
    <ul><li><b>자동 승인 후보</b>: 실험적 기준을 통과한 후보이며 아직 사람이 확정하지 않은 자료입니다.</li>
    <li><b>검토 필요</b>: 낮은 유사도, 후보 간 혼동, 미검출, 읽기 실패 등 확인이 필요한 자료입니다.</li>
    <li><b>확인 완료</b>: 사용자가 후보를 승인하거나 직접 배정한 자료입니다.</li></ul>
    <p><b>후보대로 확인</b>은 후보를 검토한 뒤 누릅니다. 틀렸거나 여러 아이를 지정하려면 <b>직접 배정</b>에서 등장 아이를 모두 체크하세요.</p>
    <p>여러 사진은 <b>Ctrl+클릭</b>, 연속된 사진은 <b>Shift+클릭</b>으로 선택합니다. 필터를 바꾸면 숨겨진 사진은 선택에서 빠집니다.</p>
    <p><b>교정 취소</b>는 마지막 배정을 되돌립니다. <b>날짜 수정</b>으로 촬영 날짜를 바꿀 수 있습니다. 유사도는 확률이나 정확도 백분율이 아닙니다.</p>
    <p>교정한 얼굴을 다음 인식에 활용하려면 얼굴 하나를 선택하고 인식 결과 옆 <b>··· → 선택 얼굴을 참고 얼굴로 등록</b>을 누르세요.</p>'''),
    ('원본 보존 정리', 4, '복사 계획 확인 후 정리하기', '''
    <ol><li>자료를 확인 완료 상태로 만듭니다.</li><li><b>정리 계획</b>에서 일별 또는 주차별을 고릅니다.</li>
    <li><b>정리 계획 확인·실행</b>을 눌러 원본과 대상 경로를 확인합니다.</li><li>확인하면 작업 폴더의 <b>정리</b> 폴더에 아이별 복사본을 만듭니다.</li></ol>
    <p>선택한 사진이 있으면 선택 자료가 대상입니다. 선택이 없으면 확인 완료된 전체 자료가 대상입니다. 이미 성공한 같은 아이·자료 조합은 건너뜁니다.</p>
    <p>원본 파일이 분석 후 바뀌면 복사하지 않습니다. 원본을 삭제하거나 덮어쓰지 않습니다.</p>
    <p>중단된 정리는 <b>작업 이력·설정</b>에서 재시도할 수 있습니다. 되돌리기는 PhotoJoy가 만든 복사본에만 적용되며, 원본이 없거나 복사본이 수정되면 보존합니다.</p>'''),
    ('ZIP · 워터마크 · 통계', 6, '아이별 전송 자료 준비하기', '''
    <ol><li><b>보내기 준비</b>에서 날짜 범위를 정합니다.</li><li>아이를 선택합니다. 여러 아이는 Ctrl+클릭합니다.</li>
    <li>필요하면 PNG 로고를 선택하고 <b>선택 아이 ZIP</b>을 누릅니다.</li><li><b>전송묶음 열기</b>에서 ZIP을 확인합니다.</li></ol>
    <p>로고는 내보내는 사진에만 적용하고 원본은 변경하지 않습니다. 영상에는 워터마크를 넣지 않습니다.</p>
    <p>ZIP 생성은 실제 발송이 아닙니다. 카카오톡·알림장 등에 직접 보낸 후 <b>직접 보냈음 확인</b>으로 기록하세요.</p>
    <p><b>통계</b>는 확인 완료된 자료를 집계합니다. 아이가 함께 나온 사진은 각 아이의 수량에 포함됩니다. CSV로 저장할 수 있습니다.</p>'''),
    ('백업 · 인식 설정', 8, '데이터와 작업 이력 관리하기', '''
    <p><b>작업 이력·설정 → 데이터 백업</b>은 DB, 등록 얼굴과 미리보기를 ZIP으로 저장합니다. 원본 사진·영상은 포함하지 않으므로 별도로 보관하세요. 백업 복원 화면은 아직 제공하지 않습니다.</p>
    <p><b>인식 설정</b>에서 모델을 진단하고 비교 기준을 저장할 수 있습니다. 저장 후 <b>다시 비교</b>를 실행하면 미확정 후보에 반영됩니다.</p>
    <p>현재 기본 모델은 YuNet·SFace입니다. 성장, 가림, 옆모습, 비슷한 얼굴의 구분 정확도는 실제 사용 자료로 확인해야 합니다.</p>
    <p>가이드 왼쪽의 항목을 선택하거나 창 오른쪽 위의 톱니 <b>가이드</b> 버튼, <b>F1</b> 키로 도움말을 열 수 있습니다.</p>'''),
]


class GuideDialog(QDialog):
    navigate = Signal(int)

    def __init__(self, parent=None, chapter=0):
        super().__init__(parent)
        self.setWindowTitle('PhotoJoy 사용 가이드')
        self.resize(870, 610)
        outer = QVBoxLayout(self); outer.setContentsMargins(22,20,22,20)
        outer.addWidget(label('PhotoJoy 사용 가이드', 'pageTitle'))
        outer.addWidget(label('처음 등록부터 검토·정리·보내기까지', 'muted'))
        row = QHBoxLayout()
        self.topics = QListWidget(); self.topics.setObjectName('guideTopics'); self.topics.setFixedWidth(207)
        self.topics.addItems([c[0] for c in CHAPTERS]); row.addWidget(self.topics)
        self.content = QTextBrowser(); self.content.setOpenExternalLinks(False); row.addWidget(self.content,1)
        outer.addLayout(row,1)
        buttons = QHBoxLayout(); buttons.addStretch()
        self.go = QPushButton('이 화면으로 이동'); self.go.setObjectName('primary'); self.go.clicked.connect(self.open_step)
        close = QPushButton('닫기'); close.clicked.connect(self.accept)
        buttons.addWidget(self.go); buttons.addWidget(close); outer.addLayout(buttons)
        self.topics.currentRowChanged.connect(self.select_chapter)
        self.topics.setCurrentRow(chapter)

    def select_chapter(self, index):
        _, _, title, body = CHAPTERS[index]
        self.content.setHtml('<html><head><style>body{font-family:Malgun Gothic;color:#334b60;font-size:14px;}h2{color:#1685d8;}p,li{line-height:160%;margin-bottom:12px;}b{color:#204f76;}</style></head><body><h2>'+title+'</h2>'+body+'</body></html>')

    def open_step(self):
        self.navigate.emit(CHAPTERS[self.topics.currentRow()][1])
        self.accept()
