# OPERATION

이 문서는 런타임 동작, 관측 포인트, 장애 대응을 다룹니다.
설치/환경변수는 `docs/SETUP.md`, 테스트 전략은 `docs/TESTING.md`를 참고하세요.

## 1. 런타임 요약

1. 조회 기간 계산(`today - LOOKBACK_DAYS` ~ `today + 1`)
2. 지역별 조회(순차 또는 제한 병렬)
3. 상태 저장소 upsert 및 미전송 재시도 전송
4. 헬스 평가/알림, 필요 시 복구 backfill
5. 주기 대기 후 반복

안전장치:
- 비치명 반복 예외 발생 시 재시도 대기는 최소 `1초` 보장
- 자동 cleanup 기본값은 전송완료(`sent=true`) 데이터만 삭제(`CLEANUP_INCLUDE_UNSENT=false`)
- 복구 backfill 기본 예산: `HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS=1`, `HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE=3`
- `SIGTERM`/`SIGINT` 수신 시 현재 사이클 경계에서 안전 종료 후 리소스(`processor`, `notifier`)를 정리
- graceful 종료 대기 예산은 `SHUTDOWN_TIMEOUT_SEC`(기본 30초)로 제어하며, 초과 시 `shutdown.forced` 이벤트를 기록
- 컨테이너 `HEALTHCHECK`는 `scripts/container_healthcheck.py`로 `HEALTH_STATE_FILE` 최신성(최근 사이클 기록) 기반 상태를 판단
- 단, `RUN_ONCE=true` 모드에서는 stale 판정을 건너뛰어 단발성 실행의 오탐을 방지

핵심 코드:
- `app/entrypoints/service_loop.py`
- `app/usecases/process_cycle.py`
- `app/services/weather_api.py`
- `app/services/notifier.py`

## 2. 운영 기본 규칙

- 이벤트 표준은 `docs/EVENTS.md`를 단일 기준으로 사용
- 중복 방지 키는 이벤트 ID(불완전 시 해시)를 사용
- 전송 실패 항목은 `sent=false`로 유지되어 다음 사이클에서 재시도
- `DRY_RUN=true`는 전송 없이 로그만 기록
- 민감정보(`serviceKey`, `apiKey`, `SERVICE_API_KEY`)는 로그에서 마스킹
- 두레이 웹훅 상세 명세는 `docs/DOORAY_WEBHOOK_REFERENCE.md`를 기준으로 참고
- 웹훅 성공 판정은 HTTP 상태 코드 + 응답 바디 `header.isSuccessful`를 함께 확인
- API 조회 보호는 `API_SOFT_RATE_LIMIT_PER_SEC`(기본 30 req/sec), 웹훅 전송 보호는 `NOTIFIER_SEND_RATE_LIMIT_PER_SEC`(기본 1 req/sec)로 전역 적용

## 3. 일상 점검 체크리스트

- API 키/웹훅/지역코드 설정 유효성 확인
- 상태 저장소 경로/권한/디스크 여유 확인
- `area.failed`, `notification.final_failure`, `pending_total` 추세 확인
- `area.mapping_coverage_warning` 발생 시 누락된 지역코드 매핑 보강
- `notification.circuit.*`, `notification.backpressure.applied` 급증 여부 확인

## 4. 장애 대응 런북

API 실패 지속:
- `area.failed`의 `error_code` 분포로 네트워크/API 장애를 분리
- `error_code=api_result_error`가 반복될 때 `error` 본문의 `resultCode`(예: `22`)를 함께 확인
- 필요 시 `CYCLE_INTERVAL_SEC` 상향으로 장애 파급 완화

Webhook 실패 지속:
- `notification.final_failure`의 `attempts`, `error` 확인
- `attempts=1` 반복 시 4xx 또는 바디 검증 실패(`resultCode`) 가능성을 우선 점검
- 회로 오픈(`notification.circuit.opened`) 발생 시 수신 시스템/네트워크 우선 점검

상태 저장소 손상/의심:
- `.broken-<timestamp>` 백업 파일 생성 여부 확인
- 복구 전 무결성 점검:

```bash
python3 main.py verify-state \
  --json-state-file ./data/sent_messages.json \
  --sqlite-state-file ./data/sent_messages.db \
  --strict
```

JSON -> SQLite 마이그레이션:

```bash
python3 main.py migrate-state \
  --json-state-file ./data/sent_messages.json \
  --sqlite-state-file ./data/sent_messages.db
```

## 5. 검증 체계 요약

CI 워크플로:
- 기본 게이트: `.github/workflows/ci.yml`
- 변경영향 기반: `.github/workflows/pr-fast.yml`
- 야간 전체 회귀: `.github/workflows/nightly-full.yml`
- 외부 연동 canary: `.github/workflows/canary.yml`
- 보호 환경 live-e2e: `.github/workflows/live-e2e.yml`
- 장시간 안정성: `.github/workflows/soak.yml`

로컬 주요 명령:

```bash
python3 -m scripts.check_event_docs_sync
python3 -m scripts.check_alarm_rules_sync
python3 -m scripts.check_repo_hygiene
python3 -m scripts.check_env_defaults_sync
python3 -m scripts.check_area_mapping_sync
python3 -m scripts.perf_baseline --max-samples 20
python3 -m scripts.slo_report --log-file <service.log>
```

## 6. 알람 매핑

<!-- ALARM_RULES_TABLE:START -->
| 신호(Event) | 기본 임계값(예시) | 확인 필드 | 1차 대응 | 후속 조치 |
|---|---|---|---|---|
| `cycle.cost.metrics` | 1시간 평균 대비 api_fetch_calls 또는 notification_attempts >= 2x | `api_fetch_calls`, `notification_attempts`, `notification_failures`, `pending_total` | 호출량/전송량 급증 구간 확인, 최근 설정/장애 이벤트와 상관관계 점검 | `AREA_CODES`, 재시도/주기 설정 재조정 후 24시간 추세 재평가 |
| `area.failed` | 5분 합계 >= 20 | `error_code`, `area_code`, `error` | 네트워크/API 상태 점검, 실패 지역 편중 여부 확인 | 임시로 `CYCLE_INTERVAL_SEC` 상향 후 장애 원인 분리 |
| `notification.final_failure` | 10분 합계 >= 5 | `attempts`, `event_id`, `error` | Webhook URL/권한/수신 시스템 상태 점검 | 실패 이벤트 재전송 여부 확인, 웹훅 교체 시 설정 반영 |
| `notification.circuit.opened` | 단일 이벤트 즉시 경고 | `consecutive_failures`, `reset_sec` | 반복 실패 폭주로 판단, 웹훅/네트워크 즉시 점검 | 회로 닫힘(`notification.circuit.closed`) 이후 정상 전송 복구 여부 확인 |
| `notification.backpressure.applied` | 10분 합계 >= 1 | `area_code`, `max_attempts_per_cycle`, `skipped` | 사이클 전송 예산 도달 여부 확인, 실패 누적 원인 확인 | `NOTIFIER_MAX_ATTEMPTS_PER_CYCLE` 조정 및 실패 원인 제거 |
| `health.notification.sent` (`outage_detected`) | 단일 이벤트 즉시 경고 | `health_event` | 장애 공지 전파, 외부 의존성 상태 확인 | heartbeat 발생 추세 모니터링 및 복구 조건 점검 |
| `health.notification.sent` (`outage_heartbeat`) | 2회 연속 발생 | `health_event` | 장기 장애로 분류, 우회 경로 검토 | API 실패 코드 분포 기준으로 공급자/네트워크 이슈 분리 |
| `state.cleanup.failed` | 단일 이벤트 즉시 경고 | `state_file`, `error` | 파일 권한/경로/디스크 용량 확인 | 스토리지 정책 수정 및 cleanup 재실행 |
| `state.migration.failed` | 단일 이벤트 즉시 경고 | `json_state_file`, `sqlite_state_file`, `error` | 마이그레이션 중지 후 JSON 모드 롤백 | 원인 제거 후 재마이그레이션, 완료 이벤트 확인 |
<!-- ALARM_RULES_TABLE:END -->

알람 규칙 단일 기준:
- 스키마: `docs/alarm_rules.json`
- 동기화 검증: `python3 -m scripts.check_alarm_rules_sync`

## 7. 산출물 위치

- canary: `artifacts/canary/*`
- live-e2e: `artifacts/live-e2e/*`, 로컬 실행은 `artifacts/live-e2e/local/*`
- soak: `artifacts/soak/*`
- 상태 무결성 점검: `artifacts/state-check/*`
- 성능 baseline: `artifacts/perf_baseline/*`
