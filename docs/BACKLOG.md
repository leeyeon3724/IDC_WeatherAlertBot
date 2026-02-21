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
| SR-07 | 실제 외부 의존성(API/Webhook)과의 통합 건전성을 주기적으로 확인해야 함 | 스테이징 canary에서 실제 API 호출 + 웹훅 전송 경로 검증 가능해야 함 | `.github/workflows/canary.yml`, `scripts/canary_report.py` | canary 결과 이벤트/아티팩트 | 충족(현재기준) |
| SR-08 | 장시간 실행 시 안정성(메모리/상태증가/중복재처리)이 유지되어야 함 | soak 테스트/예산 기반으로 안정성 이상을 탐지할 수 있어야 함 | `.github/workflows/soak.yml`, `scripts/soak_report.py`, `tests/test_soak_report.py` | `cycle.cost.metrics` 추세 + soak 리포트 | 충족(현재기준) |
| SR-09 | 테스트용 실자격증명(API/Webhook)은 보호된 실행 경로에서만 사용되어야 함 | 보호 환경 + 로컬 비추적 파일 기반 실자격증명 검증 경로를 제공해야 함 | `.github/workflows/live-e2e.yml`, `scripts/run_live_e2e_local.sh` | live-e2e Summary/artifacts | 충족(현재기준) |

## 2) Evidence Snapshot

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_repo_hygiene`, `pytest --cov` 통과
- 테스트/커버리지: `167 passed`, 총 커버리지 `91.54%`
- 대표 커버리지: `service_loop 98%`, `commands 94%`, `weather_api 99%`, `settings 90%`
- canary/soak/live-e2e 워크플로 및 리포트 스크립트 도입 완료
- 상태 무결성 점검 CLI/CI smoke, 변경영향 기반 fast gate/nightly gate 도입 완료
- 서비스 요구사항 충족도: `9/9` (현재 코드/테스트/문서 기준)
- 운영데이터 장기 추세는 완료 게이트가 아닌 `3.2 운영 관찰`에서 별도 추적

## 3) Active Backlog

현재 활성 과제 없음.

## 3.1) Recent Closures (현재기준)

| ID | Priority | 상태 | 근거 관점 | 요구사항 연결 | 작업 | 완료 근거 |
|---|---|---|---|---|---|---|
| RB-801 | P1 | 완료 | 제품 신뢰성 / 운영 관측·추적성 | SR-07 | 스테이징 canary 워크플로/리포트 도입(실 API + webhook 검증 채널) | `.github/workflows/canary.yml`, `scripts/canary_report.py` |
| RB-802 | P1 | 완료 | 제품 신뢰성 / 성능·비용 효율 | SR-08 | 장시간 soak 테스트 + 안정성 예산(합성 soak 자동화) 도입 | `.github/workflows/soak.yml`, `scripts/soak_report.py`, `tests/test_soak_report.py` |
| RB-804 | P2 | 완료 | 제품 신뢰성 / 성능·비용 효율 | SR-01, SR-04 | 전송 실패 폭주 완화(backpressure/circuit-breaker) 정책 도입 | `app/services/notifier.py`, `app/usecases/process_cycle.py`, 관련 테스트 |
| RB-805 | P2 | 완료 | 운영 관측·추적성 / 변경 효율 | SR-06 | 운영 SLO 리포트 자동화(성공률/실패율/지연/잔량) 도입 | `scripts/slo_report.py`, canary/live-e2e 워크플로 연동 |
| RB-808 | P2 | 완료 | 제품 신뢰성 / 보안·운영통제 | SR-09 | live-e2e 보호 환경 워크플로 + 로컬 실자격증명 검증 경로 도입 | `.github/workflows/live-e2e.yml`, `scripts/run_live_e2e_local.sh` |
| RB-806 | P3 | 완료 | 설계·코드 품질 / 변경 효율 | SR-03 | 상태 저장소 점검 CLI(`verify-state`) 도입 | `python3 main.py verify-state ... --strict`, CI smoke 연동 |
| RB-807 | P3 | 완료 | 변경 효율 / 검증력(테스트·계약) | SR-06 | 변경영향 기반 fast gate + nightly full gate 전략 도입 | `.github/workflows/pr-fast.yml`, `.github/workflows/nightly-full.yml`, `scripts/select_tests.py` |

## 3.2) 운영 관찰 (권장, 완료 게이트 아님)

| ID | 권장 관찰 지표 | 관찰 주기 | 근거 데이터 |
|---|---|---|---|
| RB-801 | canary 성공률, webhook probe 성공률, 실패 원인 분포 | 주간 | `artifacts/canary/report.json`, `artifacts/canary/slo_report.json` |
| RB-802 | soak PASS율, 메모리 증가량, 중복 전송/미전송 잔량 | 주간 | `artifacts/soak/report.json` |
| RB-804 | `notification.circuit.*`, `notification.backpressure.applied`, `pending_total` 추세 | 주간 | 구조화 로그, `cycle.cost.metrics` |
| RB-805 | SLO(`success_rate`, `failure_rate`, `p95`, `pending_latest`) 추세 | 주간 | `artifacts/*/slo_report.json` |
| RB-806 | `State integrity verification smoke` 실패 여부 | PR/배포 시 | CI artifacts (`artifacts/state-check/verify.log`) |
| RB-807 | fast/full 실행 비중, fast 리드타임 절감률, nightly 성공률 | 주간 | `artifacts/pr-fast/selection.json`, Actions history |
| RB-808 | 보호환경 live-e2e 실행 이력, 로컬 live-e2e 수동 점검 결과 | 주간 | Actions history, `artifacts/live-e2e/local/service.log` |

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
| Validation Flow Wave | RB-801, RB-802, RB-804, RB-805, RB-806, RB-807, RB-808 | 실연동/안정성/운영가시성 검증 경로 구축 |

## 5) Maintenance Rules

- 상태 정의: `진행중`, `완료`만 사용
- 운영 지표는 완료 게이트가 아니라 `3.2 운영 관찰`로 관리
- 변경 단위별 품질 게이트(`ruff`, `mypy`, `scripts.check_architecture_rules`, `scripts.check_event_docs_sync`, `scripts.check_repo_hygiene`, `pytest`) 통과 후 병합
- PR에서는 `scripts.check_pr_checklist` 통과로 템플릿 체크 항목과 변경 영향 검증의 일치 여부를 확인
- 기능 변경은 작은 커밋 단위로 분리하고, 각 단위에서 백로그 상태를 함께 갱신
- 문서 경계는 `README/SETUP/OPERATION/TESTING/EVENTS/BACKLOG`로 고정
