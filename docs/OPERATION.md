# OPERATION

이 문서는 런타임 동작, 관측 포인트, 장애 대응만 다룹니다.
설치/환경변수 설정은 `docs/SETUP.md`를 참고하세요.

## 1. 런타임 요약

1. 조회 기간 계산(`today - LOOKBACK_DAYS` ~ `today + 1`)
2. 지역별 조회(순차 또는 제한 병렬, 전송은 사이클마다 시작 지역 라운드로빈)
3. 상태 저장소 upsert 및 미전송 전송
4. 헬스 평가/알림, 필요 시 복구 backfill
5. 주기 대기 후 반복

복구 backfill 예산(기본):
- `HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS=1` (백필 조회 윈도우 일수)
- `HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE=3` (사이클당 최대 백필 윈도우 수)

핵심 코드:
- `app/usecases/process_cycle.py`
- `app/entrypoints/service_loop.py`
- `app/services/weather_api.py`
- `app/services/notifier.py`

## 2. 운영 기본 규칙

- 이벤트 표준은 `docs/EVENTS.md`를 단일 기준으로 사용
- 중복 방지 키는 이벤트 ID(불완전 시 해시) 사용
- 전송 실패는 `sent=false`로 유지되어 다음 사이클 재시도
- 자동 cleanup 기본값은 전송완료(`sent=true`) 데이터만 삭제(`CLEANUP_INCLUDE_UNSENT=false`)
- `DRY_RUN=true`는 전송 없이 로그만 기록

## 3. 운영 체크리스트

- API 키/웹훅/지역코드 설정 유효성 확인
- 상태 저장소 파일 경로/권한/디스크 여유 확인
- 실패 이벤트(`area.failed`, `notification.final_failure`) 증가 추이 확인
- 민감정보 마스킹(`serviceKey`, `apiKey`, `SERVICE_API_KEY`) 확인

## 4. 빠른 런북

API 실패 지속:
- `area.failed`의 `error_code` 분포로 원인 분리(네트워크/timeout/기타)

Webhook 실패 지속:
- `notification.final_failure`의 `attempts`, `error` 확인

상태 파일 손상:
- `.broken-<timestamp>` 백업 파일 생성 여부 확인 후 복구 절차 수행
- 복구 전/배포 전 무결성 점검:

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

- 성공 기준: `state.migration.complete`
- 실패 시: `state.migration.failed` 확인 후 `STATE_REPOSITORY_TYPE=json` 롤백

## 5. 알람 매핑

| 신호(Event) | 기본 임계값(예시) | 확인 필드 | 1차 대응 | 후속 조치 |
|---|---|---|---|---|
| `cycle.cost.metrics` | 1시간 평균 대비 `api_fetch_calls` 또는 `notification_attempts` `>= 2x` | `api_fetch_calls`, `notification_attempts`, `notification_failures`, `pending_total` | 호출량/전송량 급증 구간 확인, 최근 설정/장애 이벤트와 상관관계 점검 | `AREA_CODES`, 재시도/주기 설정 재조정 후 24시간 추세 재평가 |
| `area.failed` | 5분 합계 `>= 20` | `error_code`, `area_code`, `error` | 네트워크/API 상태 점검, 실패 지역 편중 여부 확인 | 임시로 `CYCLE_INTERVAL_SEC` 상향 후 장애 원인 분리 |
| `notification.final_failure` | 10분 합계 `>= 5` | `attempts`, `event_id`, `error` | Webhook URL/권한/수신 시스템 상태 점검 | 실패 이벤트 재전송 여부 확인, 웹훅 교체 시 설정 반영 |
| `notification.circuit.opened` | 단일 이벤트 즉시 경고 | `consecutive_failures`, `reset_sec` | 반복 실패 폭주로 판단, 웹훅/네트워크 즉시 점검 | 회로 닫힘(`notification.circuit.closed`) 이후 정상 전송 복구 여부 확인 |
| `notification.backpressure.applied` | 10분 합계 `>= 1` | `area_code`, `max_attempts_per_cycle`, `skipped` | 사이클 전송 예산 도달 여부 확인, 실패 누적 원인 확인 | `NOTIFIER_MAX_ATTEMPTS_PER_CYCLE` 조정 및 실패 원인 제거 |
| `health.notification.sent` (`outage_detected`) | 단일 이벤트 즉시 경고 | `health_event` | 장애 공지 전파, 외부 의존성 상태 확인 | heartbeat 발생 추세 모니터링 및 복구 조건 점검 |
| `health.notification.sent` (`outage_heartbeat`) | 2회 연속 발생 | `health_event` | 장기 장애로 분류, 우회 경로 검토 | API 실패 코드 분포 기준으로 공급자/네트워크 이슈 분리 |
| `state.cleanup.failed` | 단일 이벤트 즉시 경고 | `state_file`, `error` | 파일 권한/경로/디스크 용량 확인 | 스토리지 정책 수정 및 cleanup 재실행 |
| `state.migration.failed` | 단일 이벤트 즉시 경고 | `json_state_file`, `sqlite_state_file`, `error` | 마이그레이션 중지 후 JSON 모드 롤백 | 원인 제거 후 재마이그레이션, 완료 이벤트 확인 |

알람 규칙 단일 기준:
- 스키마: `docs/alarm_rules.json`
- 동기화 검증: `python3 -m scripts.check_alarm_rules_sync`

## 6. 성능 리포트 정책

- 기준 스크립트: `python3 -m scripts.perf_baseline --max-samples 20`
- 샘플 정책: baseline 계산 시 입력 리포트 중 최근 `20`개만 유지/집계
- 추세 확인: baseline markdown의 `trend` 컬럼으로 지표 변화 방향을 우선 확인
- PR 회귀 게이트: `scripts.compare_perf_reports --max-regression-pct 20 --fail-on-regression`
- 예외 처리: 임시 허용 지표는 `PERF_ALLOW_REGRESSION_METRICS`(comma-separated)로 제한하고, 안정화 후 즉시 제거

## 7. Canary 운영 검증

- 워크플로: `.github/workflows/canary.yml`
- 트리거: `schedule(매일)`, `pull_request(main, 관련 경로)`, `workflow_dispatch`
- 목적: 스테이징 성격의 실 API + 분리 webhook 채널 건전성 점검
- 필수 시크릿: `SERVICE_API_KEY`, `CANARY_SERVICE_HOOK_URL`
- 결과 산출물: `artifacts/canary/service.log`, `artifacts/canary/webhook_probe.json`, `artifacts/canary/report.*`

판정 규칙:
- 성공 조건: `startup.ready`, `cycle.start`, `cycle.complete`, `shutdown.run_once_complete` 이벤트 존재 + webhook probe 성공 + 주요 실패 이벤트 부재
- 실패 이벤트: `startup.invalid_config`, `shutdown.unexpected_error`, `area.failed`, `notification.final_failure`, `state.read_failed`, `state.persist_failed`

## 8. Live E2E 운영 검증(보호 환경)

- 워크플로: `.github/workflows/live-e2e.yml`
- 트리거: `schedule(주 1회)`, `workflow_dispatch`
- 목적: 테스트용 실자격증명(API/Webhook)으로 실제 전송 경로를 보호 환경에서 검증
- 필수 시크릿: `LIVE_E2E_SERVICE_API_KEY`, `LIVE_E2E_WEBHOOK_URL`
- 필수 조건: GitHub Environment `live-e2e` 보호 규칙(승인자/브랜치 제한) 적용
- 결과 산출물: `artifacts/live-e2e/service.log`, `artifacts/live-e2e/webhook_probe.json`, `artifacts/live-e2e/report.*`

판정 규칙:
- 성공 조건: canary와 동일한 필수 이벤트 집합 + webhook probe 성공 + 주요 실패 이벤트 부재
- 실패 시 분리 원칙: 코드 회귀(서비스 exit code, 필수 이벤트 누락)와 외부 장애(webhook/API 네트워크)를 각각 분류

로컬 실행: `docs/SETUP.md` §5 참고.

## 9. Soak 안정성 검증

- 워크플로: `.github/workflows/soak.yml`
- 트리거: `schedule(매일)`, `workflow_dispatch`, `pull_request(quick soak)`
- 리포트: `artifacts/soak/report.json`, `artifacts/soak/report.md`
- 로컬 실행: `make soak-report` 또는 `python3 -m scripts.soak_report ...`

예산(기본):
- `max_pending=0`
- `max_duplicate_deliveries=0`
- `max_state_growth=0` (`new_event_every=0` 기준)
- `max_memory_growth_kib=8192`

## 10. SLO 리포트 자동화

- 스크립트: `scripts/slo_report.py`
- 자동 생성: `.github/workflows/canary.yml`, `.github/workflows/live-e2e.yml` 내 SLO 리포트 단계
- 산출물: `artifacts/canary/slo_report.*`, `artifacts/live-e2e/slo_report.*`
- 로컬 실행: `make slo-report` 또는 `python3 -m scripts.slo_report --log-file <service.log>`
- 필드 누락 진단: `missing_field_causes`로 원인(`log_format`/`collection_gap`/`code_omission`)을 분류하고, 보정 시 `fallbacks_applied`에 근거 필드를 기록

기본 SLO 임계:
- 성공률(`success_rate`) `>= 1.0` (canary/live-e2e 기준)
- 실패율(`failure_rate`) `<= 0.0` (canary/live-e2e 기준)
- p95 사이클 지연(`cycle_latency_p95_sec`) `<= 600`
- 최신 미전송 잔량(`pending_latest`) `<= 0`

복구 backfill 지연 제어:
- `HEALTH_RECOVERY_BACKFILL_WINDOW_DAYS`, `HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE`를 조정해 한 사이클에서 처리할 backfill 양을 제한

## 11. 배포 전 상태 무결성 게이트

- CI 연동: `.github/workflows/ci.yml`의 `State integrity verification smoke` 단계
- 검증 경로: `migrate-state` -> `verify-state --strict`
- 산출물: `artifacts/state-check/verify.log`, `artifacts/state-check/verify.md`

## 12. PR/Nightly 검증 전략

- PR fast gate: `.github/workflows/pr-fast.yml`
  - 변경 파일 목록(`git diff`)을 `scripts/select_tests.py`로 분석해 관련 테스트 우선 실행
  - 매핑 불가능/고위험 변경은 full 테스트로 자동 폴백
- Nightly full gate: `.github/workflows/nightly-full.yml`
  - `make gate` 주기 실행으로 전체 회귀 탐지력 유지

## 13. GitHub Secrets/Vars 설정 가이드

설정 경로:
- GitHub 저장소 -> `Settings` -> `Secrets and variables` -> `Actions`
- 민감정보는 `Secrets`, 비민감 파라미터는 `Variables`에 등록

필수 `Secrets`:

| 이름 | 사용 워크플로 | 용도 | 비고 |
|---|---|---|---|
| SERVICE_API_KEY | `canary.yml` | 기상청 API 호출 인증 | canary/staging 검증용 |
| CANARY_SERVICE_HOOK_URL | `canary.yml` | canary webhook 검증 채널 | 운영 알림 채널과 분리 권장 |
| LIVE_E2E_SERVICE_API_KEY | `live-e2e.yml` | live-e2e API 호출 인증 | 보호 환경에서만 사용 |
| LIVE_E2E_WEBHOOK_URL | `live-e2e.yml` | live-e2e webhook 채널 | canary/운영 채널과 분리 |

권장 `Variables`:

| 이름 | 사용 워크플로 | 기본값 | 용도 |
|---|---|---:|---|
| CANARY_AREA_CODES | `canary.yml` | `["L1090000"]` | canary 대상 지역코드 |
| CANARY_AREA_CODE_MAPPING | `canary.yml` | `{"L1090000":"서울"}` | canary 지역명 매핑 |
| LIVE_E2E_AREA_CODES | `live-e2e.yml` | `["L1090000"]` | live-e2e 대상 지역코드 |
| LIVE_E2E_AREA_CODE_MAPPING | `live-e2e.yml` | `{"L1090000":"서울"}` | live-e2e 지역명 매핑 |
| SOAK_CYCLES | `soak.yml` | `6000` | soak 사이클 수 |
| SOAK_AREA_COUNT | `soak.yml` | `3` | soak 합성 지역 수 |
| SOAK_NEW_EVENT_EVERY | `soak.yml` | `0` | 주기적 신규 이벤트 주입 간격 |
| SOAK_MAX_MEMORY_GROWTH_KIB | `soak.yml` | `8192` | 메모리 증가 예산 |
