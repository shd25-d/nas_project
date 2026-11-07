# 모루 · moru

Docker로 실행하는 개인용 NAS 웹앱입니다. PC·휴대폰 브라우저에서 파일을 보관하고 확인합니다.
React 화면과 FastAPI 서버를 앱 컨테이너 하나로 실행하며 파일 원본은 호스트 폴더에 저장합니다.

## 빠른 시작

Docker Engine 또는 Docker Desktop과 Docker Compose v2가 필요합니다. **Docker 엔진을 먼저 실행하세요.**

```sh
cp .env.example .env
mkdir -p data/files data/app
id -u
id -g
```

`.env`의 `NAS_UID`, `NAS_GID`를 위에서 확인한 현재 사용자의 UID/GID로 바꾸세요.
두 폴더는 해당 사용자에게 읽기·쓰기·디렉터리 탐색 권한이 있어야 합니다.
이미 다른 디스크에 파일이 있다면 `NAS_FILES_PATH`를 그 폴더의 절대 경로로 바꿀 수 있습니다.
`NAS_APP_PATH`는 파일 저장소 **밖에 있는 별도 폴더**를 사용하세요.
Compose가 저장 경로를 자동으로 만들지 않으므로 지정한 폴더를 먼저 생성해야 합니다.

```sh
docker compose up -d --build
docker compose exec nas python -m server.cli create-owner
```

명령에서 사용자 이름과 12자 이상 비밀번호를 입력합니다. 비밀번호는 화면에 표시하지 않습니다.
브라우저에서 [모루 열기](http://127.0.0.1:8080)에 접속해 로그인하세요.
계정을 만들기 전에는 웹에서 회원가입할 수 없습니다.

## 휴대폰과 VPN에서 접속

초기 설정은 이 컴퓨터에서만 접속할 수 있도록 `127.0.0.1`에 바인딩합니다.
휴대폰에서 사용하려면 서버에 고정 내부 IP를 할당하고 `.env`를 예를 들어 다음처럼 수정하세요.

```dotenv
NAS_BIND_IP=192.168.1.100
NAS_PORT=8080
```

```sh
docker compose up -d
```

같은 Wi-Fi에서는 `http://192.168.1.100:8080`으로 접속합니다.
외부에서는 라우터 VPN을 연결하고 같은 주소로 접속합니다. VPN에서 해당 내부 IP로의 라우팅과 접근이 허용되어 있어야 합니다.

웹서비스 포트를 인터넷으로 포트포워딩하지 마세요. 외부 차단은 라우터의 포트포워딩·UPnP·IPv6와 서버 방화벽 설정을 함께 확인해야 합니다.
특히 Docker 공개 포트는 Linux의 UFW 규칙만으로 제한되지 않을 수 있습니다.
실제 접속 환경에서 **휴대폰 Wi-Fi와 VPN을 모두 끈 상태로 서비스에 접근할 수 없는지** 확인하세요.
라우터/VPN 설정과 외부 접근 검증은 이 앱이 자동으로 수행하지 않습니다.

내부 HTTP 접속에서도 로그인·CSRF·경로 검사를 적용합니다. VPN은 외부 구간을 보호합니다.
내부망 구간까지 암호화하려면 HTTPS 역방향 프록시를 앞에 두세요.
이 경우 `NAS_SECURE_COOKIE=true`로 설정하고, 외부 HTTPS 요청의 `Origin`과 서버가 보는 주소가 일치하도록
신뢰하는 프록시와 원본 Host/스킴 전달을 별도로 구성해야 합니다. 기본 컨테이너는 전달 헤더를 신뢰하지 않습니다.

## 할 수 있는 작업

- 여러 파일 업로드, 다운로드, 폴더 생성, 이름 변경, 파일·폴더 이동, 영구 삭제
- PC 드래그앤드롭과 휴대폰 파일 선택, 진행률과 취소
- 현재 폴더 이름 검색, 이름·최신·크기 정렬, 목록·격자 보기, 종류 필터
- PDF 페이지 보기·확대, DOCX 내용 보기, 소스코드 줄 번호·구문 강조
- JPG/PNG/GIF/WEBP, MP4/WEBM, MP3/WAV/OGG 보기·재생

같은 이름이 있으면 덮어쓰지 않습니다. 이동할 대상 폴더는 먼저 만들어 주세요.
삭제는 **영구 삭제**입니다. 폴더 삭제 시 내용도 모두 삭제됩니다.

### 뷰어 제한

| 형식 | 범위 |
| --- | --- |
| PDF | 앱에 포함된 PDF.js로 표시. 암호화·손상된 PDF는 원본 다운로드 안내 |
| DOCX | 내용 위주 HTML 미리보기. Word와 페이지·배치가 다를 수 있음. 10 MiB 이하 |
| 코드·텍스트 | UTF-8, 2 MiB 이하. 200,000자까지 구문 강조. 실행·편집하지 않음 |
| 이미지·동영상·오디오 | 브라우저 지원 형식/코덱 기준. 서버 트랜스코딩 없음 |
| 기타 | 파일 정보와 원본 다운로드 |

PDF 폰트·문자맵·워커와 DOCX 변환은 서버/앱에 포함하며 외부 문서 뷰어나 CDN으로 파일을 보내지 않습니다.
DOCX는 XML 선언 검사, 압축 해제 총량 32 MiB/2,000개 항목 제한, 변환 CPU·시간·메모리 제한과 HTML 정화를 적용합니다.
기본 파일별 업로드 한도는 10 GiB이며 `.env`에서 바꿀 수 있습니다.
폴더 업로드·폴더 ZIP 다운로드·업로드 이어받기·공유 링크·휴지통·사진 자동 백업은 제공하지 않습니다.

## 데이터, 업데이트, 백업

- `data/files`: 일반 파일·폴더 원본. 각 업로드 대상 폴더의 `.nas-upload`는 앱이 관리하는 임시 폴더이므로 직접 변경하지 마세요.
- `data/app`: 계정·세션 DB. 웹에서 접근할 수 없습니다.
- 컨테이너 재시작이나 이미지 재빌드로 위 데이터는 삭제되지 않습니다.
- 중단된 업로드는 완성 파일로 보이지 않습니다. 최상위 임시 폴더는 앱 시작 때, 하위 폴더의 잔여 임시 파일은 재시작 후 해당 폴더에 처음 업로드할 때 정리합니다.
- **앱 인스턴스는 한 개, Uvicorn worker는 1개로 실행하세요.** 여러 인스턴스로 같은 저장소를 동시에 관리하지 마세요.
- 심볼릭 링크와 일반 파일·폴더 이외의 항목은 파일 탐색기에 표시하거나 따라가지 않습니다.
- 호스트에서 원본 파일을 변경할 수 있지만 앱에서 처리 중인 파일/폴더는 동시에 수정하지 마세요.

업데이트:

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 nas
```

일관된 백업이 필요하면 업로드가 끝난 뒤 앱을 정지하고 파일 저장 폴더와 앱 데이터 폴더를 **함께** 백업하세요.

```sh
docker compose stop
# NAS_FILES_PATH와 NAS_APP_PATH에 지정한 두 폴더를 백업
docker compose start
```

RAID나 컨테이너 자체는 백업이 아닙니다. 자동 백업은 이 앱의 범위에 포함되지 않습니다.
복원 시 두 폴더를 복원한 뒤 UID/GID와 쓰기 권한을 맞추고 시작하세요.

비밀번호를 잊었다면 서버에서 다음 명령을 실행합니다. 모든 기존 로그인이 만료됩니다.

```sh
docker compose exec nas python -m server.cli reset-owner
```

### mergerfs 저장소

`NAS_FILES_PATH`에 `/mnt/storage` 아래의 mergerfs 폴더를 지정할 수 있습니다.
업로드 완료 파일을 옮길 때 `RENAME_NOREPLACE`를 지원하지 않는 파일시스템에서는
완성 파일을 하드링크로 연결한 뒤 임시 이름을 제거합니다. 같은 이름이 있으면 실패하므로 기존 파일을 덮어쓰지 않습니다.
임시 폴더는 업로드 대상 폴더 아래에 두어 mergerfs의 경로 보존 정책에서 서로 다른 HDD를 가로지르는 문제를 줄입니다.

파일 이동도 같은 대체 방식을 사용할 수 있습니다. 두 경로 사이 하드링크가 불가능하면 저장소 정책을 확인하라는 오류를 표시합니다.
대체 방식으로 파일을 이동하는 도중 프로세스가 종료되면 원본과 대상 이름이 모두 남을 수 있습니다.
폴더는 하드링크 대체가 불가능하므로 `RENAME_NOREPLACE` 미지원 저장소에서는 폴더 이동·이름 변경을 지원하지 않습니다.
해당 작업은 서버의 파일 관리 도구에서 처리하세요.

## 로컬 개발과 검증

Node.js 22.12 이상과 Python 3.9 이상이 필요합니다. 배포 이미지는 Python 3.12를 사용합니다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --prefix web
npm run build --prefix web
.venv/bin/python -m server.cli create-owner
.venv/bin/uvicorn server.main:create_app --factory --host 127.0.0.1 --port 8765
```

개발 서버는 `http://127.0.0.1:8765`에서 열립니다. 화면 핫리로드가 필요하면 다른 터미널에서
`npm run dev --prefix web`을 실행하고 Vite가 출력한 주소를 사용하세요. API는 8765 포트로 프록시합니다.
PDF 정적 리소스는 최초 `npm run build` 때 준비됩니다.

```sh
.venv/bin/python -m pytest -q
npm run build --prefix web
npm test --prefix web
docker compose config --quiet
```

브라우저 테스트는 별도의 임시 저장소·테스트 계정을 생성하고 종료 시 지웁니다. 실제 개인 파일을 사용하지 않습니다.
8765 포트를 비워두세요. macOS의 Google Chrome을 자동 사용하며, 다른 환경에서는 먼저
`cd web` 후 `npx playwright install chromium`을 실행하세요.
의존성 버전은 `requirements*.txt`와 `web/package-lock.json`으로 고정합니다.

## 프로젝트 구조

```text
server/       인증, 파일 관리, 스트리밍, 문서 변환 API와 계정 CLI
web/src/      반응형 React 탐색기와 파일 뷰어
tests/        API·저장소 테스트 및 격리된 브라우저 테스트 서버
web/e2e/      실제 브라우저 사용 흐름 테스트
docs/         승인 설계와 구현·검증 기록
```
