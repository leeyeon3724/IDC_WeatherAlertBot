# BACKLOG

이 문서는 코드베이스 평가와 리팩토링 백로그를 통합 관리합니다.
기준 브랜치: `main`

## 1) Assessment Snapshot

| 관점 | 점수(5점) | 현재 판단 |
|---|---:|---|
| 정확성 | 4.4 | 페이지네이션/중복 방지/복구 로직이 안정적이고 핵심 흐름 테스트가 충분함 |
| 가독성 | 4.1 | 엔트리포인트 분리로 구조가 명확해졌고 책임 경계가 개선됨 |
| 복잡성 | 4.0 | `cli/runtime_builder/service_loop/commands` 분리로 진입점 복잡도 감소 |
| 응집도/결합도 | 4.2 | `HealthStateRepository` 프로토콜 도입으로 구체 저장소 결합 완화 |
| 테스트 가능성 | 4.3 | main 테스트가 harness/smoke 구조로 정리되어 유지보수성 향상 |
| 확장성 | 4.2 | JSON/SQLite 이중 저장소 + 마이그레이션 유틸로 전환 유연성 확보 |
| 성능 | 4.2 | SQLite WAL/busy_timeout/batch 처리, JSON pending 카운트 최적화 반영 |
| 안정성 | 4.4 | 재시도/백오프/헬스 감지/복구(backfill) 체계가 일관되게 동작 |
| 보안 | 3.8 | Weather API `http-only` 제약을 허용목록 검증 및 운영 통제로 보완 |
| 일관성 | 4.3 | notifier/weather_api 재시도 로그가 구조화 이벤트로 통일됨 |
| 기술부채 | 4.0 | 우선순위 백로그(P0~P3) 완료, 잔여 부채는 운영 최적화 중심 |

## 2) Prioritized Backlog

| ID | Priority | 상태 | 영역 | 작업 | 기대효과 | 완료조건(DoD) |
|---|---|---|---|---|---|---|
| RB-101 | P0 | 완료 | 보안/정확성 | 기상청 API `http-only` 제약 반영 보완 통제(허용 도메인/경로 검증 + 운영 통제) | 불가능한 `https` 전환 과제 제거, 현실적 보안 강화 | 문서/설정검증/테스트 동시 반영 |
| RB-102 | P0 | 완료 | 보안 | URL 검증 정책 분리(Webhook=`https` 강제, Weather API=허용목록 기반 `http`) | 오설정/취약 URL 입력 차단 | 설정 검증 테스트 추가 |
| RB-103 | P1 | 완료 | 결합도 | `HealthStateRepository` 프로토콜 도입 및 `ApiHealthMonitor` 추상화 의존 전환 | 저장소 교체 용이성/테스트 단순화 | health monitor 테스트 무회귀 |
| RB-104 | P1 | 완료 | 복잡성 | `cli.py`를 `runtime_builder.py`, `service_loop.py`, `commands.py`로 분리 | 진입점 복잡도/변경 충돌 감소 | 기존 엔트리 동작 동일 + 테스트 통과 |
| RB-105 | P1 | 완료 | 가독성/응집도 | `settings.py` 코드 매핑 상수 분리(`domain/code_maps.py`) | 설정 책임 명확화 | weather/settings 테스트 무회귀 |
| RB-106 | P1 | 완료 | 일관성 | notifier/weather_api 재시도 로그를 `log_event()`로 통일 | 관측 일관성 향상 | 비구조 로그 제거 |
| RB-107 | P2 | 완료 | 성능/안정성 | SQLite `PRAGMA busy_timeout`, WAL 모드 적용 | 락 충돌 내성/쓰기 안정성 향상 | 설정/테스트 반영 |
| RB-108 | P2 | 완료 | 성능 | SQLite upsert/mark 경로 batch 최적화(`executemany`) | 대량 이벤트 처리 성능 개선 | 회귀 테스트 통과 |
| RB-109 | P2 | 완료 | 성능 | JSON 저장소 `pending_count` 비용 최적화 | 반복 조회 부하 축소 | 기존 기능/테스트 무회귀 |
| RB-110 | P2 | 완료 | 테스트가능성 | `tests/test_main.py` monkeypatch 의존 축소(헬퍼/스모크 분리) | 테스트 유지보수성 향상 | 테스트 구조 단순화/커버리지 유지 |
| RB-111 | P3 | 완료 | 운영성 | 이벤트 사전 문서(`docs/EVENTS.md`) 신설 | 온콜 대응/대시보드 표준화 | 핵심 이벤트 필드 정의 완료 |
| RB-112 | P3 | 완료 | 운영성 | JSON->SQLite 마이그레이션 유틸 추가 | 저장소 전환 리스크 축소 | 샘플 마이그레이션 검증 테스트 |

## 3) Next Candidates

- SQLite 동시성 스트레스 테스트(멀티 프로세스/락 경합) 보강
- 운영 장애 시나리오 end-to-end 테스트(장애 감지 -> heartbeat -> 복구 -> backfill)
- 구조화 로그 기반 운영 대시보드/알람 룰 템플릿 정리

## 4) Maintenance Rules

- 변경 단위별 품질 게이트(`ruff`, `mypy`, `pytest`) 통과 후 병합
- 기능 변경은 작은 PR/커밋 단위로 진행
- 문서 경계는 `README/SETUP/OPERATION/TESTING/EVENTS/BACKLOG`로 유지
