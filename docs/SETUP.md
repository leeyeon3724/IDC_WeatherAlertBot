# SETUP

이 문서는 설치/설정/실행만 다룹니다.
운영 정책과 장애 대응은 `docs/OPERATION.md`를 참고하세요.
테스트 전략/품질 기준은 `docs/TESTING.md`를 참고하세요.

## 1. 요구사항

- Python 3.11+
- `pip`
- 외부 네트워크 접근(기상청 API, Dooray Webhook)

## 2. 설치

```bash
pip install -r requirements.txt
```

개발/테스트 도구까지 설치:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## 3. 환경변수 준비

```bash
cp .env.example .env
```

- 애플리케이션은 기본적으로 프로젝트 루트의 `.env`를 읽습니다.
- 동일 키가 OS 환경변수에 있으면 OS 환경변수가 우선합니다.

## 4. 필수 환경변수

- `SERVICE_API_KEY`: 기상청 Open API 서비스 키
- `SERVICE_HOOK_URL`: Dooray Incoming Webhook URL (`https`만 허용)
- `AREA_CODES`: 조회 지역코드 목록(JSON 배열)
- `AREA_CODE_MAPPING`: 지역코드-지역명 매핑(JSON 객체)

예시:

```bash
SERVICE_API_KEY=YOUR_SERVICE_KEY
SERVICE_HOOK_URL=https://hook.dooray.com/services/your/path
AREA_CODES=["L1012000","L1070100"]
AREA_CODE_MAPPING={"L1012000":"판교(성남)","L1070100":"대구"}
```

## 5. 주요 선택 환경변수

### 조회/전송

- `WEATHER_ALERT_DATA_API_URL` (기본: `http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd`, 해당 API는 현재 `https` 미지원)
- `WEATHER_API_ALLOWED_HOSTS` (기본: `["apis.data.go.kr"]`)
- `WEATHER_API_ALLOWED_PATH_PREFIXES` (기본: `["/1360000/WthrWrnInfoService/"]`)
- `MAX_RETRIES`, `RETRY_DELAY_SEC`
- `NOTIFIER_MAX_RETRIES`, `NOTIFIER_RETRY_DELAY_SEC`
- `REQUEST_CONNECT_TIMEOUT_SEC`, `REQUEST_READ_TIMEOUT_SEC`
- `NOTIFIER_CONNECT_TIMEOUT_SEC`, `NOTIFIER_READ_TIMEOUT_SEC`

### 실행 제어

- `DRY_RUN` (기본: `false`)
- `RUN_ONCE` (기본: `false`)
- `CYCLE_INTERVAL_SEC` (기본: `10`)
- `AREA_MAX_WORKERS` (기본: `1`)
- `AREA_INTERVAL_SEC` (기본: `5`, 순차 모드에서만 사용)
- `LOOKBACK_DAYS` (기본: `0`)

### 상태 파일

- `SENT_MESSAGES_FILE` (기본: `./data/sent_messages.json`)
- `STATE_REPOSITORY_TYPE` (기본: `json`, 값: `json` 또는 `sqlite`)
- `SQLITE_STATE_FILE` (기본: `./data/sent_messages.db`)
- `HEALTH_STATE_FILE` (기본: `./data/api_health_state.json`)
- `CLEANUP_ENABLED` (기본: `true`)
- `CLEANUP_RETENTION_DAYS` (기본: `30`)
- `CLEANUP_INCLUDE_UNSENT` (기본: `true`)

### 헬스 알림 정책

- `HEALTH_ALERT_ENABLED` (기본: `true`)
- `HEALTH_OUTAGE_WINDOW_SEC` / `HEALTH_OUTAGE_FAIL_RATIO_THRESHOLD`
- `HEALTH_OUTAGE_MIN_FAILED_CYCLES` / `HEALTH_OUTAGE_CONSECUTIVE_FAILURES`
- `HEALTH_RECOVERY_WINDOW_SEC` / `HEALTH_RECOVERY_MAX_FAIL_RATIO`
- `HEALTH_RECOVERY_CONSECUTIVE_SUCCESSES`
- `HEALTH_HEARTBEAT_INTERVAL_SEC`
- `HEALTH_BACKOFF_MAX_SEC`
- `HEALTH_RECOVERY_BACKFILL_MAX_DAYS`

## 6. 로컬 실행

서비스 실행:

```bash
python3 main.py
```

1회 dry-run:

```bash
DRY_RUN=true RUN_ONCE=true python3 main.py
```

상태 정리:

```bash
python3 main.py cleanup-state --days 30
python3 main.py cleanup-state --days 30 --include-unsent
```

## 7. Docker 실행

빌드:

```bash
docker build -t weather-alert-bot .
```

Compose:

```bash
docker compose up -d --build
docker compose logs -f weather-alert-bot
```

컨테이너 단독 실행:

```bash
docker run --rm --env-file .env weather-alert-bot
```
