# PhotoJoy Web 0.3

Chrome에서 이용하는 PhotoJoy 웹 버전입니다. 기존 Windows 0.2 프로그램은 그대로 사용할 수 있습니다.

## 현재 완료된 범위

- 첫 화면의 아이디·비밀번호 로그인과 계정 만들기. 한글 아이디와 아이 이름 지원.
- 윈도우 / 안드로이드 / 아이폰 선택. 선택값을 로그인 세션에 저장하고 업로드 안내에 반영.
- PC·모바일 너비에 맞춘 반응형 화면. 기기 선택은 운영체제 자체를 바꾸거나 앱을 설치하지 않습니다.
- 아이·그룹 등록/수정, 사진·영상 업로드, 기존 YuNet + SFace 얼굴 검출·비교.
- 검출한 얼굴을 참고 얼굴로 등록하고 미확정 자료 다시 비교.
- 상태 필터·검색·정렬, 사진/얼굴 미리보기, 직접 배정·후보 확인·제외·검토 되돌리기.
- 확인한 자료를 아이별/날짜별 ZIP으로 다운로드, 아이별 통계 CSV.
- 가이드, 사진 보관 안내, 로그아웃.
- Google Identity Services 버튼 및 서버 토큰 검증 코드. 실제 Google 연결에는 웹 클라이언트 ID가 필요합니다.

**외부 공개 URL과 Google 실계정 로그인은 아직 활성화되지 않았습니다.** 호스팅 계정·비용 결정, Google Cloud 설정이 필요합니다. 설정 전에는 Google 버튼이 준비 중으로 표시되며, 가짜 로그인으로 통과하지 않습니다.

Windows 버전의 로컬 폴더 복사 계획/작업 되돌리기, 워터마크, 백업 복원 등 모든 데스크톱 기능을 웹으로 옮긴 버전은 아닙니다. 웹의 정리 결과는 ZIP 다운로드로 받습니다. 기존 Windows 보관함도 자동으로 업로드하거나 합치지 않습니다.

## 이 PC에서 열기

상위 폴더의 `PhotoJoy-Web.cmd` 또는 이 폴더의 같은 이름 파일을 실행하세요. 서버를 백그라운드에서 실행한 후 Chrome이 설치되어 있으면 Chrome으로 엽니다.

- 주소: http://127.0.0.1:8765
- 처음 접속하면 **계정 만들기**에서 본인의 아이디·비밀번호를 정하세요. 기본 관리자 비밀번호는 없습니다.
- 위 주소는 이 PC에서만 열립니다. 다른 사람에게 보낼 외부 공유 주소가 아닙니다.
- 사용자 자료는 `web-data/`에 저장하며 Git에서 제외합니다.
- 실행 로그: `web-data/server.log`. 수동 개발 실행은 아래 명령을 사용하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe scripts\prepare_models.py
.\.venv\Scripts\python.exe run_web.py
```

모델 준비 단계는 OpenCV 공식 모델을 내려받고 SHA-256을 검사합니다. 이미 준비된 모델은 다시 받지 않습니다.

## GitHub와 외부 공유

저장소: https://github.com/qufl4252-collab/PhotoJoy (비공개)

GitHub에는 소스·배포 설정·모델 출처와 라이선스만 올립니다. 사진·얼굴 특징·사용자 DB·비밀번호·테스트 출력·EXE·가상환경은 제외합니다. 소스 저장소의 공개 범위와 웹 서비스의 로그인 접근은 별도입니다.

GitHub Pages는 Python 서버를 실행하지 않습니다. 이 웹 버전은 **GitHub 저장소 + Python 웹 서버 + 영구 저장 공간** 구조입니다. 서버에서 인증과 얼굴 인식을 처리하고 같은 주소에서 화면을 제공합니다.

### Render 배포 준비

`render.yaml`은 단일 Python 서버와 10GB 영구 디스크를 정의합니다. 아직 서비스 생성이나 결제는 하지 않았습니다.

1. Render에 가입/로그인하고 GitHub에서 **PhotoJoy 저장소만** 접근하도록 연결합니다. 가입 약관 동의와 결제 정보 입력은 계정 소유자가 진행하세요.
2. Blueprint에서 비공개 PhotoJoy 저장소와 기본 브랜치를 선택합니다.
3. 생성될 서버·디스크·월 요금을 검토합니다. 기본 설정은 Starter 서버와 10GB 디스크입니다. 2026-11-03 공식 가격표 기준 기본 계산은 서버 $7 + 디스크 $2.50 = 월 $9.50이며, 세금·추가 트래픽은 별도입니다. 실제 결제 전 화면 가격을 다시 확인하세요.
4. Google 클라이언트 ID가 아직 없으면 빈 값으로 시작할 수 있습니다. Render가 제공하는 HTTPS 서비스 주소는 `RENDER_EXTERNAL_URL`에서 자동으로 읽습니다.
5. `/healthz` 응답과 실제 계정 생성·사진 업로드를 확인한 후 HTTPS 주소를 공유합니다.
6. 사용자 자료가 `/data` 영구 디스크에 저장되는지 재시작 후 확인하세요. 디스크 없는 무료 서비스는 재시작/배포 때 자료가 사라질 수 있어 이 구성에 사용하지 않습니다.

512MB Starter의 실제 대형 사진·동시 사용자 부하는 배포 후 확인해야 합니다. 필요하면 더 큰 서버를 선택합니다. 현재 서버는 단일 프로세스/단일 인스턴스용입니다. 여러 인스턴스 운영에는 DB·저장소·작업 큐 분리가 필요합니다.

다른 호스팅에서는 `Dockerfile`을 사용할 수 있습니다. Docker 실행 시 `/data`를 쓰기 가능한 영구 볼륨으로 연결하고 `PHOTOJOY_PUBLIC_URL`에 HTTPS 주소를 설정하세요. 로컬 Docker 빌드는 이 PC에 Docker가 없어 검증하지 않았습니다.

## Google 로그인 연결

Google 로그인은 사진 접근 권한이나 Google Drive 접근 권한을 요구하지 않습니다. Google은 사용자 인증에만 사용됩니다.

1. Google Cloud에서 프로젝트를 만들고 Google Auth Platform의 브랜딩·지원 이메일·대상을 설정합니다. 처음 이용하는 계정의 약관 동의는 계정 소유자가 완료합니다.
2. OAuth 클라이언트의 앱 유형은 **웹 애플리케이션**을 선택합니다.
3. 승인된 JavaScript 원본에 실제 HTTPS 서비스 주소를 추가합니다. 로컬 확인이 필요하면 `http://localhost`와 `http://localhost:8765`를 추가합니다.
4. 발급된 `...apps.googleusercontent.com` 웹 클라이언트 ID를 서버의 `GOOGLE_CLIENT_ID` 환경변수에 입력하고 다시 배포합니다. 이 방식에는 클라이언트 보안 비밀번호가 필요 없습니다.
5. 테스트 모드라면 허용한 테스트 계정으로 확인하고, 외부 사용자에게 제공할 때는 Google의 게시/검증 요구사항을 충족하세요.

로컬 Google 확인 시 서버 환경도 `PHOTOJOY_PUBLIC_URL=http://localhost:8765`로 맞추고 `http://localhost:8765`에서 접속하세요. 기본 실행기 주소는 127.0.0.1이므로 수동 개발 실행을 이용합니다. 한 번에 한 서비스 원본만 허용합니다.

Google 서버 서명·대상 클라이언트·발급자·만료를 공식 `google-auth`로 검사하고, 브라우저별 nonce를 한 번만 소비합니다. 이메일이 같다는 이유로 기존 아이디 계정을 자동 병합하지 않습니다.

## 환경변수

| 이름 | 용도 |
| --- | --- |
| `PHOTOJOY_PUBLIC_URL` | 서비스의 정확한 원본 주소. 경로나 마지막 `/` 없이 HTTPS 주소 지정. 로컬 기본값은 `http://127.0.0.1:8765`. |
| `PHOTOJOY_DATA_DIR` | 계정 DB·사진·얼굴 특징·내보내기 저장 폴더. 로컬은 `web-data`, 배포는 `/data`. |
| `GOOGLE_CLIENT_ID` | Google 웹 OAuth 클라이언트 ID. 비어 있으면 Google 로그인 비활성. |
| `PHOTOJOY_REGISTRATION` | `true`면 새 계정 허용. `false`면 기존 계정 로그인만 허용. |
| `PHOTOJOY_USER_QUOTA_MB` | 계정별 원본 업로드 용량. 기본 2048MB. 생성 미리보기·ZIP·DB는 별도이므로 서버 디스크 사용량도 관리하세요. |
| `PORT` | 수신 포트. 기본 8765. |

`.env.example`은 참고용입니다. 앱이 `.env`를 자동으로 읽지는 않으므로 호스팅 환경변수 또는 실행 셸에 설정하세요. 외부 공개 주소에는 HTTPS가 필요합니다.

## 자료 보관과 검증

- 비밀번호는 scrypt로 해시하며 세션은 서버에서 만료·폐기 가능한 무작위 토큰입니다. 세션 쿠키는 HttpOnly, 외부 HTTPS에서는 Secure입니다.
- 수정 요청은 동일 원본과 전용 헤더를 검사합니다. 다른 계정의 사진/얼굴/ZIP 주소는 접근할 수 없습니다.
- 원본은 사용자가 선택해서 업로드한 경우에만 서버로 전송합니다. 기기 파일은 변경하지 않습니다.
- 영상은 최대 8개 프레임을 분석합니다. 유사도는 확률/정확도가 아닙니다. 사람이 검토한 사진만 ZIP에 포함합니다.
- 서버 운영자는 저장 자료에 접근할 수 있습니다. 사용자 데이터의 삭제·백업 정책은 운영자가 마련해야 합니다. 셀프 계정 삭제·비밀번호 복구 화면은 현재 제공하지 않습니다.
- 회원가입/로그인 시도 제한은 서버가 확인한 접속 IP와 아이디에 적용합니다. 프록시 뒤에서는 여러 접속자가 같은 IP로 처리될 수 있으므로 공개 운영 시 호스팅의 신뢰 가능한 프록시 설정을 검토하세요.

검증 결과는 `WEB_TEST_RESULTS.md`에 기록했습니다.

## 공식 참고 자료

- GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site
- Render 배포: https://render.com/docs/deploy-fastapi
- Render 영구 디스크: https://render.com/docs/disks
- Render 요금: https://render.com/pricing
- Google 설정: https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- Google 토큰 검증: https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
