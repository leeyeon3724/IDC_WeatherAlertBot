# BACKLOG

이 문서는 코드베이스 평가와 리팩토링 우선순위를 단일 기준으로 관리합니다.
기준 브랜치: `main`
평가일: `2026-02-21`

## 1) Current Assessment

| 관점 | 점수(5점) | 평가 |
|---|---:|---|
| 제품 신뢰성 | 4.5 | 핵심 알림 흐름 정확성/안정성/보안(redaction) 기준 충족 |
| 설계·코드 품질 | 4.6 | 계층 규율, 복잡도 관리, 기술부채/위생 자동검사 기반 확보 |
| 검증력(테스트·계약) | 4.7 | 단위/통합 + 이벤트·설정·CLI 계약 스냅샷으로 회귀 탐지력 높음 |
| 배포·변경 효율 | 4.5 | `make gate`, 런타임 매트릭스, PR 체크 자동검증으로 누락 위험 축소 |
| 운영 관측·추적성 | 4.5 | 이벤트 스키마 버전/문서 정합성/알람 매핑으로 운영 추적 기반 안정 |
| 성능·비용 효율 | 4.6 | perf trend + 샘플 보존 정책, `cycle.cost.metrics`로 비용 관점 모니터링 가능 |

## 1.1) Service Requirement Validation

| ID | 실제 서비스 요구사항 | 수용 기준(검증 조건) | 자동 검증 근거 | 운영 검증 신호 | 상태 |
|---|---|---|---|---|---|
| SR-01 | 신규 특보는 중복 없이 1회 전송되고, 실패 건은 재시도되어 최종 전송 가능해야 함 | 동일 `event_id` 재실행 시 중복 전송 0건, 실패 후 다음 사이클 전송 복구 | `tests/test_process_cycle.py` | `notification.sent`, `notification.final_failure`, `pending_total` | 충족 |
| SR-02 | Weather API 오류/타임아웃/페이지네이션/NODATA를 안전하게 처리해야 함 | 재시도 후 성공 또는 명시적 오류 코드로 실패 기록 | `tests/test_weather_api.py` | `area.fetch.retry`, `area.failed(error_code)` | 충족 |
| SR-03 | 상태 저장소(JSON/SQLite) 이상 시 서비스 연속성이 유지되어야 함 | 손상 JSON 백업 후 복구, read/persist 실패 로깅, SQLite 경로 정상 동작 | `tests/test_json_state_repo.py`, `tests/test_sqlite_state_repo.py`, `tests/test_main_smoke.py` | `state.invalid_json`, `state.read_failed`, `state.persist_failed` | 충족 |
| SR-04 | API 장애 감지/heartbeat/복구(backfill)가 정책대로 동작해야 함 | 장애 감지/지속/복구 시나리오에서 알림/백필 흐름이 예측대로 수행 | `tests/test_health_monitor.py`, `tests/test_main_smoke.py`, `tests/test_service_loop.py` | `health.notification.sent`, `health.backfill.*`, `health.evaluate` | 충족 |
| SR-05 | 잘못된 설정/허용되지 않은 URL은 즉시 차단되어야 함 | 시작 단계에서 설정 오류로 실패하고 민감정보는 마스킹됨 | `tests/test_settings.py`, `tests/test_main.py` | `startup.invalid_config` | 충족 |
| SR-06 | 릴리스 전 품질 게이트가 단일 경로로 강제되어야 함 | `make gate` + PR checklist + runtime smoke 통과 시에만 병합 | `.github/workflows/ci.yml`, `scripts/check_pr_checklist.py` | CI summary/artifacts | 충족 |
| SR-07 | 실제 외부 의존성(API/Webhook)과의 통합 건전성을 주기적으로 확인해야 함 | 스테이징 canary에서 실제 API 호출 + 웹훅 전송 경로 주기 검증 | `.github/workflows/canary.yml`, `scripts/canary_report.py` | canary 결과 이벤트/아티팩트 | 검증대기 |
| SR-08 | 장시간 실행 시 안정성(메모리/상태증가/중복재처리)이 유지되어야 함 | 24h soak에서 비정상 메모리 증가/상태 누수/중복 전송 이상 없음 | `.github/workflows/soak.yml`, `scripts/soak_report.py`, `tests/test_soak_report.py` | `cycle.cost.metrics` 장기 추세 + soak 리포트 | 검증대기 |
| SR-09 | 테스트용 실자격증명(API/Webhook)은 보호된 실행 경로에서만 사용되어야 함 | 전용 환경 승인 후에만 실행되고, 실행 이력/결과 아티팩트가 남아야 함 | `.github/workflows/live-e2e.yml` | live-e2e Summary/artifacts | 검증대기 |

## 2) Evidence Snapshot

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_repo_hygiene`, `pytest --cov` 통과
- 테스트/커버리지: `167 passed`, 총 커버리지 `91.54%`
- 대표 커버리지: `service_loop 98%`, `commands 94%`, `weather_api 99%`, `settings 90%`
- canary 운영 검증 기반: `.github/workflows/canary.yml` + `scripts/canary_report.py` 도입(시크릿 구성 후 운영 검증 필요)
- live-e2e 보호 검증 기반: `.github/workflows/live-e2e.yml` 도입(보호 환경 승인 + 전용 시크릿 필요)
- live-e2e 로컬 검증 기반: `scripts/run_live_e2e_local.sh` + `.env.live-e2e(비추적)` 경로 도입
- soak 안정성 검증 기반: `.github/workflows/soak.yml` + `scripts/soak_report.py` 도입(운영 추세 관측 축적 필요)
- 운영 SLO 리포트 자동화: `scripts/slo_report.py` + canary 워크플로 연동(`slo_report.json/md`)
- 알림 폭주 완화 정책: notifier 회로차단(`notification.circuit.*`) + 사이클 예산 기반 backpressure(`notification.backpressure.applied`) 도입
- 이벤트 payload 계약 검증: `tests/contracts/event_payload_contract.json` + `scripts/event_payload_contract.py` 도입
- 상태 무결성 점검 CLI: `python3 main.py verify-state ... --strict` 도입
- CI 상태 무결성 스모크: `migrate-state` + `verify-state --strict` 자동 검증 단계 도입
- 변경영향 기반 테스트 전략: PR fast gate(`pr-fast.yml`) + nightly full gate(`nightly-full.yml`) 도입
- 서비스 요구사항 충족도: `6/9` (`SR-07`, `SR-08`, `SR-09` 검증대기)

## 3) Active Backlog

| ID | Priority | 상태 | 근거 관점 | 요구사항 연결 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|---|
| RB-801 | P1 | 검증대기 | 제품 신뢰성 / 운영 관측·추적성 | SR-07 | 스테이징 canary 워크플로/리포트 도입(실 API + webhook 검증 채널) | 일/PR 기준 canary 결과와 실패 원인이 아티팩트/이벤트로 추적 가능 |
| RB-802 | P1 | 검증대기 | 제품 신뢰성 / 성능·비용 효율 | SR-08 | 장시간 soak 테스트(예: 24h) + 안정성 예산(메모리/상태크기/중복전송률) 정의(합성 soak 자동화 도입) | soak 리포트 자동 생성, 허용 임계치 초과 시 CI/운영 경고 |
| RB-804 | P2 | 검증대기 | 제품 신뢰성 / 성능·비용 효율 | SR-01, SR-04 | 전송 실패 폭주 완화(알림 backpressure/circuit-breaker) 정책 도입 | 반복 실패 시 과도한 재시도/전송 시도가 제한되고 복구 시 자동 정상화 |
| RB-805 | P2 | 검증대기 | 운영 관측·추적성 / 변경 효율 | SR-06 | 운영 SLO 리포트 자동화(성공 전송률/실패율/지연/미전송 잔량) | 배포/운영 후 SLO 리포트가 주기적으로 생성되고 임계 초과 시 경고 |
| RB-808 | P2 | 검증대기 | 제품 신뢰성 / 보안·운영통제 | SR-09 | live-e2e 보호 환경 워크플로(전용 시크릿/환경 승인) 도입 | 승인 없는 실행 차단, 결과 아티팩트/요약으로 실행 증적 확보 |
| RB-806 | P3 | 검증대기 | 설계·코드 품질 / 변경 효율 | SR-03 | 상태 저장소 점검 CLI(`verify-state`) 도입(JSON/SQLite 무결성/마이그레이션 전 검사) | 배포 전 상태 무결성 점검을 자동 수행하고 실패 원인을 표준 출력으로 제공 |
| RB-807 | P3 | 검증대기 | 변경 효율 / 검증력(테스트·계약) | SR-06 | 변경영향 기반 테스트 선택 실행(빠른 PR 게이트 + 야간 full gate) 전략 정립 | PR 리드타임 단축, full gate 회귀 탐지력 유지, 정책이 CI 문서와 일치 |

## 3.1) 검증대기 완료 전환 기준(운영데이터)

| ID | 운영데이터 관찰 구간 | 완료 전환 기준(정량) | 근거 데이터/아티팩트 |
|---|---|---|---|
| RB-801 | 최근 14일 canary 실행 이력 | `canary_report` 성공률 `>= 95%`(최소 13/14), `webhook_probe_passed=true` 100%, `failed_reasons=[]` | `artifacts/canary/report.json`, `artifacts/canary/slo_report.json`, Actions Summary |
| RB-802 | 최근 7일 soak 실행 이력 | `soak_report` 7/7 PASS, `duplicate_delivery_count=0`, `max_pending_seen=0`, `memory_growth_kib <= budget` | `artifacts/soak/report.json`, `soak.yml` Summary |
| RB-804 | 최근 30일(실제 장애 또는 drill 1회 이상 포함) | `notification.circuit.opened` 발생 건의 100%에서 `notification.circuit.closed` 확인, `notification.backpressure.applied` 발생 구간에서 미전송 잔량(`pending_total`)이 2개 사이클 내 감소 추세 | 구조화 로그(`notification.circuit.*`, `notification.backpressure.applied`, `cycle.cost.metrics`) |
| RB-805 | 최근 14일 canary SLO 리포트 | `slo_report` 생성률 100%, `success_rate >= 1.0`, `failure_rate <= 0.0`, `pending_latest <= 0`, `p95_cycle_latency_sec <= 600` | `artifacts/canary/slo_report.json`, Actions Summary |
| RB-808 | 최근 30일 live-e2e 실행 이력 | live-e2e 실행 4회 이상, 100% 보호환경 승인 이력 존재, `webhook_probe_passed=true` 100% | `artifacts/live-e2e/report.json`, environment deployment history |
| RB-806 | 최근 14일 CI + 최근 3회 배포 | CI `State integrity verification smoke` 100% PASS + 최근 3회 배포 전 `verify-state --strict` 수행 로그에서 실패 0 | `artifacts/state-check/verify.log`, 배포 체크리스트 증적 |
| RB-807 | 최근 30개 PR + 최근 14일 nightly | PR의 `fast` 모드 적용률 `>= 70%`, `fast` 모드 median 실행시간이 full 대비 `<= 60%`, nightly full gate 성공률 `>= 95%` | `artifacts/pr-fast/selection.json`, `pr-fast.yml`/`nightly-full.yml` run history |

## 4) Completed (Compact)

| 구간 | 완료 범위 | 핵심 성과 |
|---|---|---|
| Foundation Wave | RB-101~RB-208 | URL/저장소/CLI 기반 정리 |
| Reliability Wave | RB-301~RB-407 | 도메인/저장소/루프 회귀 보호 강화 |
| CI & Governance Wave | RB-501~RB-505 | CI 품질/문서 정합/PR 템플릿 기반 구축 |
| Release Gate Wave | RB-604 | `make gate` 단일 게이트 |
| Architecture Guard Wave | RB-701 | 계층 의존성 자동검사 |
| Contract Stability Wave | RB-702 | 이벤트/설정/CLI 계약 스냅샷 |
| Runtime Matrix Wave | RB-601 | Python 3.11/3.12 smoke |
| Schema Governance Wave | RB-602 | 이벤트 스키마 버전 거버넌스 |
| Cost Observability Wave | RB-603 | 비용 관점 사이클 지표 |
| Hygiene Guard Wave | RB-703 | 저장소 위생 자동검사 |
| Perf Trend Wave | RB-506~RB-507 | 성능 추세 시각화 + 보존 정책 |
| PR Governance Wave | RB-605 | PR 체크리스트 자동검증 |
| Payload Contract Wave | RB-803 | 이벤트 payload 키 스냅샷 계약 검증 |

## 5) Maintenance Rules

- 변경 단위별 품질 게이트(`ruff`, `mypy`, `scripts.check_architecture_rules`, `scripts.check_event_docs_sync`, `scripts.check_repo_hygiene`, `pytest`) 통과 후 병합
- PR에서는 `scripts.check_pr_checklist` 통과로 템플릿 체크 항목과 변경 영향 검증의 일치 여부를 확인
- 기능 변경은 작은 커밋 단위로 분리하고, 각 단위에서 백로그 상태를 함께 갱신
- 문서 경계는 `README/SETUP/OPERATION/TESTING/EVENTS/BACKLOG`로 고정
