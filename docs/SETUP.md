# SETUP

이 문서는 설치/설정/실행만 다룹니다.
운영 정책과 장애 대응은 `docs/OPERATION.md`를 참고하세요.
테스트 전략/품질 기준은 `docs/TESTING.md`를 참고하세요.
기상청 API/두레이 웹훅 상세 명세는 `docs/KMA_API_SPEC_REFERENCE.md`, `docs/DOORAY_WEBHOOK_REFERENCE.md`를 참고하세요.

## 1. 요구사항

- Python 3.11+
- `pip`
- `make` (선택, 없으면 스크립트/파이썬 명령으로 동일 실행 가능)
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
  - URL-encoded 값이 아닌 원문(raw/decoded) 키를 사용합니다.
- `SERVICE_HOOK_URL`: Dooray Incoming Webhook URL (`https`만 허용)
- `AREA_CODES`: 조회 지역코드 목록(JSON 배열)
- `AREA_CODE_MAPPING`: 지역코드-지역명 매핑(JSON 객체)

선택 환경변수는 `.env.example`을 기준으로 관리합니다.
주의: `WEATHER_ALERT_DATA_API_URL` 기본 엔드포인트는 현재 `http`만 지원합니다.
주의: `API_SOFT_RATE_LIMIT_PER_SEC` 기본값은 `30`이며(`0`은 비활성), 병렬 조회(`AREA_MAX_WORKERS>1`)에서도 전체 호출률 상한으로 적용됩니다.
주의: `NOTIFIER_SEND_RATE_LIMIT_PER_SEC` 기본값은 `1.0`이며, 두레이 발송을 전역 기준 초당 1회로 제한합니다(`0`은 비활성).
주의: `CLEANUP_INCLUDE_UNSENT` 기본값은 `false`이며, 자동 cleanup은 기본적으로 전송완료(`sent=true`) 데이터만 삭제합니다.
주의: `ALERT_RULES_FILE` 기본값은 `./config/alert_rules.v1.json`이며, 기상청 코드맵/메시지 규칙/미매핑 정책을 파일 단위로 관리합니다.

### 4.1 ALERT_RULES_FILE 스키마 마이그레이션(v1 -> v2)

- v1 파일 예시: `config/alert_rules.v1.json`
- v2 파일 예시: `config/alert_rules.v2.json`
- 운영 전환은 `ALERT_RULES_FILE` 경로만 교체하면 됩니다.

핵심 키 변경:
- `code_maps.warn_var` -> `mappings.warning_kind`
- `code_maps.warn_stress` -> `mappings.warning_level`
- `code_maps.command` -> `mappings.announcement_action`
- `code_maps.cancel` -> `mappings.cancel_status`
- `code_maps.response_code` -> `mappings.api_result`
- `unmapped_code_policy` -> `behavior.unmapped_code_policy`
- `message_rules.<template>` -> `messages.templates.<template>`

## 5. 로컬 실행

서비스 실행:

```bash
python3 main.py
```

1회 dry-run:

```bash
DRY_RUN=true RUN_ONCE=true python3 main.py
```

로컬 Live E2E(실제 테스트용 자격증명, 1회 검증):

```bash
cp .env.live-e2e.example .env.live-e2e
# .env.live-e2e 값 수정 (테스트용 API 키/웹훅 URL)
make live-e2e-local
# 또는
./scripts/run_live_e2e_local.sh .env.live-e2e
```

- `ENABLE_LIVE_E2E=true`가 없으면 실행되지 않습니다.
- 실행 시 `RUN_ONCE=true`, `DRY_RUN=false`가 강제됩니다.
- 상태 파일은 `artifacts/live-e2e/local/*` 경로로 분리됩니다.
- 실행 리포트는 `artifacts/live-e2e/local/report.json`, `artifacts/live-e2e/local/slo_report.json`으로 생성됩니다.

상태 정리:

```bash
python3 main.py cleanup-state \
  --state-repository-type sqlite \
  --sqlite-state-file ./data/sent_messages.db \
  --days 30

python3 main.py cleanup-state \
  --state-repository-type json \
  --json-state-file ./data/sent_messages.json \
  --days 30 \
  --include-unsent
```

- `--state-repository-type`를 생략하면 `STATE_REPOSITORY_TYPE`(없으면 `sqlite`)를 사용합니다.

JSON -> SQLite 상태 마이그레이션:

```bash
python3 main.py migrate-state \
  --json-state-file ./data/sent_messages.json \
  --sqlite-state-file ./data/sent_messages.db
```

상태 저장소 무결성 점검(JSON/SQLite):

```bash
python3 main.py verify-state \
  --json-state-file ./data/sent_messages.json \
  --sqlite-state-file ./data/sent_messages.db \
  --strict
```

## 6. Docker 실행

빌드:

```bash
docker build -t weather-alert-bot .
```

Compose:

```bash
docker compose up -d --build
docker compose logs -f weather-alert-bot
docker inspect --format='{{json .State.Health}}' weather-alert-bot
```

컨테이너 단독 실행:

```bash
docker run --rm --env-file .env weather-alert-bot
```
