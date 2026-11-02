# PhotoJoy Web 0.3 검증

검증일: 2026-11-03

- 전체 테스트: **48 passed** (32.82초). 기존 핵심/GUI/한글 35개 + 웹 13개.
- 웹 테스트: 아이디·비밀번호/한글 계정, 윈도우·안드로이드·아이폰 세션 저장, scrypt 비밀번호 해시, 세션 토큰 해시/만료/로그아웃 폐기.
- 동일 원본 요청 제한, 호스트 검증, 계정별 사진·아이·얼굴·ZIP 접근 격리, 파일 크기/보관 용량/중복/잘못된 형식/긴 한글 파일명/경로 탈출 방어 확인.
- 아이 등록·수정, 참고 얼굴 등록→다시 비교→후보 확인→ZIP 원본 바이트 일치→통계→되돌리기 확인.
- Google 비활성 상태, 실패한 서명 검증, nonce 불일치/재사용 거부, 세션 발급 연결 테스트. 테스트용 검증 응답을 사용했으므로 Google 실계정 로그인을 검증한 것은 아님.
- 별도 127.0.0.1:8766 테스트 서버에서 **실제 YuNet/SFace 모델** + 공개 성인 사진으로 얼굴 1개 검출, 참고 얼굴 비교·검토·ZIP 파일 원본 일치 확인. 결과 `test-output/web-real-smoke.json`은 Git에서 제외.
- Chromium 기반 앱 내 브라우저에서 로그인 화면, 접속 환경 선택, 실제 로그인과 사진·얼굴 미리보기 시각 확인.
- Chrome 확장 프로그램의 열린 UI가 자동 제어를 막아 Chrome 자동 테스트는 미완료. 실행기는 Chrome이 설치되어 있으면 Chrome으로 열도록 구성.
- 모바일 반응형 CSS 구현. 실제 Android/iPhone 기기 검증은 미완료.
- 이 PC에는 Docker가 없어 Docker/Linux 컨테이너 빌드는 미검증. 호스팅 배포, 서비스 재시작 후 영구 저장, 외부 사용자 Google 로그인은 서비스 개설 후 검증 필요.
- Starlette에서 기존 httpx 테스트 클라이언트에 대한 deprecation 경고 1건. 테스트 실패는 없음.

테스트 명령:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp=test-output/pytest-web03-full
node --check photojoy_web/static/app.js
```

Windows 제한 실행 환경에서는 asyncio 내부 소켓 생성이 멈추는 현상이 확인되어 일반 실행 권한에서 테스트했습니다.
