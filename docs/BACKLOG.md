# BACKLOG

이 문서는 코드베이스/문서/테스트 평가와 리팩토링 백로그를 통합 관리합니다.
기준 브랜치: `main`
평가일: `2026-02-20`

## 1) Current Assessment

| 관점 | 점수(5점) | 평가 |
|---|---:|---|
| 정확성 | 4.1 | 핵심 알림/중복 방지/헬스 흐름은 안정적이나, JSON->SQLite 마이그레이션 시 타임스탬프 보존이 부족함 |
| 가독성 | 4.2 | 엔트리포인트 분리 후 책임 경계가 개선됨 |
| 복잡성 | 4.0 | 복잡도는 낮아졌지만 `service_loop` 분기 테스트가 충분하지 않음 |
| 응집도/결합도 | 4.2 | 프로토콜 기반 의존성으로 결합도 개선, 저장소 간 공통 모델 정리는 추가 여지 존재 |
| 테스트 가능성 | 4.0 | 전체 게이트는 안정적이나 `commands/service_loop/health_state_repo` 커버리지가 상대적으로 낮음 |
| 확장성 | 4.2 | JSON/SQLite 이중 저장소 + 마이그레이션 커맨드로 운영 전환 유연성 확보 |
| 성능 | 4.2 | SQLite WAL/busy_timeout/batch 최적화 반영, cleanup 경로 추가 최적화 여지 있음 |
| 안정성 | 4.2 | 재시도/백오프/헬스 감지/복구 체계 동작, CLI 실패 경로의 명시적 핸들링 보강 필요 |
| 보안 | 3.9 | Weather API `http-only` 제약을 허용목록으로 보완했으나 운영 통제/로그 가드 강화 여지 있음 |
| 일관성 | 4.1 | 재시도 로그 구조화는 완료, 일부 저장소 에러 로그는 구조화 이벤트 미적용 |
| 기술부채 | 4.0 | 1차 백로그 완료, 다음 단계는 정확성/운영 내구성 중심으로 축소됨 |

## 2) Evidence Snapshot

- 품질 게이트
- `python3 -m ruff check .` 통과
- `python3 -m mypy` 통과
- `python3 -m pytest -q --cov=app --cov-report=term --cov-config=.coveragerc` 통과
- 테스트/커버리지
- `85 passed`
- 총 커버리지 `87.48%`
- 상대적 취약 구간
- `app/entrypoints/service_loop.py` 72%
- `app/entrypoints/commands.py` 80%
- `app/repositories/health_state_repo.py` 79%
- 문서 적합성
- 문서 체계(SETUP/OPERATION/EVENTS/TESTING/BACKLOG)는 유지됨
- 테스트 문서의 우선순위 항목 중 일부는 완료 상태 반영이 더 필요함

## 3) Active Refactoring Backlog

| ID | Priority | 상태 | 영역 | 작업 | 기대효과 | 완료조건(DoD) |
|---|---|---|---|---|---|---|
| RB-201 | P0 | 완료 | 정확성/데이터무결성 | JSON->SQLite 마이그레이션 시 `first_seen_at/updated_at/last_sent_at/sent` 원본 보존 | 상태 이관 후 cleanup/운영 지표 왜곡 방지 | 마이그레이션 후 타임스탬프/전송상태 동일성 테스트 추가 |
| RB-202 | P0 | 완료 | 안정성/운영성 | `migrate-state`/`cleanup-state` 실패 경로 예외 처리 + 구조화 실패 이벤트(`state.*.failed`) 추가 | 운영 중 CLI 실패 원인 추적 가능, 종료코드 일관화 | 실패 시 이벤트 로그/종료코드 테스트 추가 |
| RB-203 | P1 | 완료 | 테스트가능성 | `service_loop.py`, `commands.py` 단위 테스트 보강(분기/예외/retry 시나리오) | 회귀 탐지력 향상, 리팩토링 내성 강화 | 대상 모듈 커버리지 상향(`service_loop >= 85%`, `commands >= 90%`) |
| RB-204 | P1 | 완료 | 일관성/관측성 | `health_state_repo.py` 에러 로그를 `log_event()` + `docs/EVENTS.md` 이벤트 사전으로 통일 | 장애 분석 속도/일관성 향상 | 비구조 문자열 로그 제거, 이벤트 문서 반영 |
| RB-205 | P1 | 예정 | 문서품질 | `docs/TESTING.md` 우선순위/리스크를 현재 상태에 맞춰 정합성 갱신 | 문서-코드 상태 불일치 제거 | 테스트 현황/우선순위가 실제 코드와 일치 |
| RB-206 | P2 | 예정 | 성능/안정성 | `SqliteStateRepository.cleanup_stale()` SQL 기반 필터링 최적화 및 대량 데이터 검증 | 대규모 상태 파일에서 cleanup 비용/락 시간 감소 | 성능 회귀 테스트 또는 비교 벤치 결과 기록 |
| RB-207 | P2 | 예정 | 보안/운영 | 운영 로그 민감정보(서비스키/원본 URL query) 노출 가드 테스트 및 정책 문서화 | 실운영 로그 안전성 강화 | redaction 정책 문서 + 회귀 테스트 추가 |
| RB-208 | P3 | 예정 | 운영성 | 마이그레이션/롤백/장애 대응 runbook 확장 (`docs/OPERATION.md`) | 온콜 절차 표준화 | 체크리스트 기반 runbook 섹션 추가 |

## 4) Iteration Plan

1. Iteration A (정확성/안정성 우선)
- RB-201, RB-202

2. Iteration B (테스트/일관성 강화)
- RB-203, RB-204, RB-205

3. Iteration C (성능/운영 고도화)
- RB-206, RB-207, RB-208

## 5) Completed History

| ID | Priority | 상태 | 영역 | 작업 |
|---|---|---|---|---|
| RB-101 | P0 | 완료 | 보안/정확성 | 기상청 API `http-only` 제약 반영 보완 통제(허용 도메인/경로 검증 + 운영 통제) |
| RB-102 | P0 | 완료 | 보안 | URL 검증 정책 분리(Webhook=`https` 강제, Weather API=허용목록 기반 `http`) |
| RB-103 | P1 | 완료 | 결합도 | `HealthStateRepository` 프로토콜 도입 및 `ApiHealthMonitor` 추상화 의존 전환 |
| RB-104 | P1 | 완료 | 복잡성 | `cli.py`를 `runtime_builder.py`, `service_loop.py`, `commands.py`로 분리 |
| RB-105 | P1 | 완료 | 가독성/응집도 | `settings.py` 코드 매핑 상수 분리(`domain/code_maps.py`) |
| RB-106 | P1 | 완료 | 일관성 | notifier/weather_api 재시도 로그를 `log_event()`로 통일 |
| RB-107 | P2 | 완료 | 성능/안정성 | SQLite `PRAGMA busy_timeout`, WAL 모드 적용 |
| RB-108 | P2 | 완료 | 성능 | SQLite upsert/mark 경로 batch 최적화(`executemany`) |
| RB-109 | P2 | 완료 | 성능 | JSON 저장소 `pending_count` 비용 최적화 |
| RB-110 | P2 | 완료 | 테스트가능성 | `tests/test_main.py` monkeypatch 의존 축소(헬퍼/스모크 분리) |
| RB-111 | P3 | 완료 | 운영성 | 이벤트 사전 문서(`docs/EVENTS.md`) 신설 |
| RB-112 | P3 | 완료 | 운영성 | JSON->SQLite 마이그레이션 유틸 추가 |

## 6) Maintenance Rules

- 변경 단위별 품질 게이트(`ruff`, `mypy`, `pytest`) 통과 후 병합
- 기능 변경은 작은 PR/커밋 단위로 진행
- 문서 경계는 `README/SETUP/OPERATION/TESTING/EVENTS/BACKLOG`로 유지
