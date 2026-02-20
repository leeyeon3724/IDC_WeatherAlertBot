# SETUP

## 1. 실행 환경

- Python 3.11+
- `pip`
- 네트워크 접근 가능 환경(기상청 API, Dooray Webhook)

## 2. 설치

```bash
pip install -r requirements.txt
```

## 3. 환경변수 파일(.env) 준비

템플릿 복사:

```bash
cp .env.example .env
```

앱은 실행 시 기본적으로 프로젝트 루트의 `.env`를 자동으로 읽습니다.
같은 키가 OS 환경변수로 이미 설정되어 있으면 OS 환경변수가 우선합니다.

## 4. 필수 환경변수

`app/settings.py`는 아래 값을 사용합니다.

- `SERVICE_API_KEY`: 기상청 Open API 서비스 키
- `SERVICE_HOOK_URL`: Dooray Incoming Webhook URL
- `AREA_CODES`: 조회 지역코드 목록(JSON 배열 문자열)
- `AREA_CODE_MAPPING`: 지역코드-지역명 매핑(JSON 객체 문자열)

선택값:

- `WEATHER_ALERT_DATA_API_URL` (기본값: `http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd`)
- `SENT_MESSAGES_FILE` (기본값: `./data/sent_messages.json`)
- `REQUEST_TIMEOUT_SEC` (기본값: `5`)
- `MAX_RETRIES` (기본값: `3`)
- `RETRY_DELAY_SEC` (기본값: `5`)
- `NOTIFIER_MAX_RETRIES` (기본값: `3`)
- `NOTIFIER_RETRY_DELAY_SEC` (기본값: `1`)
- `LOOKBACK_DAYS` (기본값: `0`, 오늘보다 이전 일자 조회 확장)
- `CYCLE_INTERVAL_SEC` (기본값: `10`)
- `AREA_INTERVAL_SEC` (기본값: `5`)
- `CLEANUP_ENABLED` (기본값: `true`, 서비스 내 자동 정리 활성화)
- `CLEANUP_RETENTION_DAYS` (기본값: `30`)
- `CLEANUP_INCLUDE_UNSENT` (기본값: `true`, 미전송 포함 정리)
- `BOT_NAME` (기본값: `기상특보알림`)
- `TIMEZONE` (기본값: `Asia/Seoul`)
- `LOG_LEVEL` (기본값: `INFO`)
- `DRY_RUN` (기본값: `false`, `true`면 전송 없이 로그만 기록)
- `RUN_ONCE` (기본값: `false`, `true`면 1사이클 실행 후 종료)

예시:

```bash
SERVICE_API_KEY="YOUR_SERVICE_KEY"
SERVICE_HOOK_URL="https://hook.dooray.com/services/..."
AREA_CODES='["11B00000","11C20000"]'
AREA_CODE_MAPPING='{"11B00000":"서울","11C20000":"강원"}'
```

직접 export 방식도 지원합니다.

## 5. 로컬 실행

```bash
python main.py
```

로그는 표준출력으로 출력되며, 시간은 KST 기준으로 표시됩니다.

1회 dry-run 점검:

```bash
export DRY_RUN=true
export RUN_ONCE=true
python main.py
```

## 6. Docker 실행

이미지 빌드:

```bash
docker build -t weather-alert-bot .
```

또는 Compose 사용:

```bash
docker compose up -d --build
docker compose logs -f weather-alert-bot
```

`docker-compose.yml`은 운영 기준으로 `DRY_RUN=false`, `RUN_ONCE=false`를 고정합니다.
또한 매일 1회 자동 상태 정리(`30일`, 미전송 포함)를 기본값으로 고정합니다.

컨테이너 실행(예시):

```bash
docker run --rm \
  --env-file .env \
  weather-alert-bot
```

또는 개별 `-e` 옵션:

```bash
docker run --rm \
  -e SERVICE_API_KEY="YOUR_SERVICE_KEY" \
  -e SERVICE_HOOK_URL="https://hook.dooray.com/services/..." \
  -e AREA_CODES='["11B00000","11C20000"]' \
  -e AREA_CODE_MAPPING='{"11B00000":"서울","11C20000":"강원"}' \
  weather-alert-bot
```

## 7. 상태 파일(sent_messages.json) 주의사항

- 기본 저장 경로는 `./data/sent_messages.json`입니다.
- 이 파일은 이벤트 ID 단위로 전송 상태를 저장해 중복 전송을 막습니다.
- 컨테이너 재시작 후 상태를 유지하려면 볼륨 마운트로 파일을 영속화하세요.
- 상태 파일 JSON이 손상되면 `.broken-<UTC_TIMESTAMP>`로 백업 후 빈 상태로 복구합니다.
- 통보문 URL 파라미터(`stn_id/tm_fc/tm_seq`)가 불완전하면 URL 첨부를 차단합니다.

상태 파일 정리(기본 30일):

```bash
python main.py cleanup-state --days 30
```

미전송 이벤트도 포함 정리:

```bash
python main.py cleanup-state --days 30 --include-unsent
```

## 8. 커밋 메시지 규칙 강제

Conventional Commits 규칙을 로컬 훅으로 강제합니다.

```bash
make setup-hooks
```

형식:

```text
<type>(<scope>): <subject>
```

예시:

- `feat(alert): add dry-run logging`
- `fix(notifier): handle webhook timeout`
