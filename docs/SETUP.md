# SETUP

## 1) 사전 조건
- Python 3.11+
- 네트워크 접근 가능 환경(기상청 API, Dooray Webhook)
- `pip` 사용 가능

## 2) 설치
```bash
make install-dev
```

## 3) 환경 변수 설정
```bash
cp .env.example .env
```
필수값:
- `SERVICE_API_KEY`
- `SERVICE_HOOK_URL`
- `AREA_CODES` (JSON 배열)
- `AREA_CODE_MAPPING` (JSON 객체)

권장값:
- `STATE_REPOSITORY_TYPE=sqlite`
- `SQLITE_STATE_FILE=./data/sent_messages.db`

주의:
- `SERVICE_API_KEY`는 원본 값을 그대로 사용합니다(미리 URL 인코딩하지 않음).

## 4) 최초 실행
안전 점검(전송 없이):
```bash
make dry-run
```
정상 실행:
```bash
make run
```

## 5) 품질 게이트(개발/배포 전)
```bash
make gate
```
`gate`에는 lint, typecheck, 아키텍처/문서/설정 동기화 체크, 테스트 커버리지가 포함됩니다.

## 6) 선택 실행
- 로컬 E2E: `make live-e2e-local`
- Docker 기동: `make compose-up`
- Docker 중지: `make compose-down`
