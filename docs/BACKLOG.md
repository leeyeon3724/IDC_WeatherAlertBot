# BACKLOG

이 문서는 코드베이스/문서/테스트 평가와 리팩토링 백로그를 통합 관리합니다.
기준 브랜치: `main`
평가일: `2026-02-20`

## 1) Current Assessment

| 관점 | 점수(5점) | 평가 |
|---|---:|---|
| 정확성 | 4.5 | 핵심 알림/중복 방지/헬스 흐름 안정적이며 health/json 경계 테스트가 보강됨 |
| 가독성 | 4.3 | 엔트리포인트/명령/루프 책임 분리와 이벤트 문서화가 정착됨 |
| 복잡성 | 4.3 | 고복잡 경로(`service_loop`)가 테스트로 보호되어 변경 리스크 감소 |
| 응집도/결합도 | 4.3 | 프로토콜 기반 의존으로 저장소 결합도 완화, 경계가 명확함 |
| 테스트 가능성 | 4.6 | `service_loop/commands/health/json_state_repo` 분기 테스트 보강 완료 |
| 확장성 | 4.3 | JSON/SQLite 이중 저장소 + 마이그레이션 커맨드 + runbook 확보 |
| 성능 | 4.4 | SQLite WAL/busy_timeout/batch + cleanup SQL 필터링 최적화 적용 |
| 안정성 | 4.4 | CLI 실패 경로 이벤트/종료코드 표준화로 운영 복원력 향상 |
| 보안 | 4.2 | 로그 민감정보 redaction 가드 및 운영 체크리스트 반영 |
| 일관성 | 4.4 | health_state 포함 주요 오류 로그가 구조화 이벤트로 통일 |
| 기술부채 | 4.3 | RB-201~RB-304 완료, 다음 부채는 운영 자동화/알람 규칙 고도화 중심 |

## 2) Evidence Snapshot

- 품질 게이트
- `python3 -m ruff check .` 통과
- `python3 -m mypy` 통과
- `python3 -m pytest -q --cov=app --cov-report=term --cov-config=.coveragerc` 통과
- 테스트/커버리지
- `109 passed`
- 총 커버리지 `91.05%`
- 주요 커버리지 지표
- `app/entrypoints/service_loop.py` 98%
- `app/entrypoints/commands.py` 94%
- `app/repositories/health_state_repo.py` 85%

## 3) Refactoring Backlog (Current Wave)

| ID | Priority | 상태 | 영역 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|
| RB-201 | P0 | 완료 | 정확성/데이터무결성 | JSON->SQLite 마이그레이션 시 `first_seen_at/updated_at/last_sent_at/sent` 원본 보존 | 타임스탬프/전송상태 동일성 테스트 추가 |
| RB-202 | P0 | 완료 | 안정성/운영성 | `migrate-state`/`cleanup-state` 실패 경로 예외 처리 + `state.*.failed` 이벤트 추가 | 실패 이벤트/종료코드 테스트 추가 |
| RB-203 | P1 | 완료 | 테스트가능성 | `service_loop.py`, `commands.py` 단위 테스트 보강 | `service_loop >= 85%`, `commands >= 90%` 달성 |
| RB-204 | P1 | 완료 | 일관성/관측성 | `health_state_repo.py` 에러 로그를 `log_event()`로 통일 | 비구조 문자열 로그 제거 + 이벤트 문서 반영 |
| RB-205 | P1 | 완료 | 문서품질 | `docs/TESTING.md` 리스크/우선순위 정합성 갱신 | 테스트 현황/우선순위가 실제 코드와 일치 |
| RB-206 | P2 | 완료 | 성능/안정성 | `SqliteStateRepository.cleanup_stale()` SQL 필터링 최적화 + 대량 데이터 검증 | bulk cleanup 테스트 추가 |
| RB-207 | P2 | 완료 | 보안/운영 | 민감정보(`serviceKey/apiKey/SERVICE_API_KEY`) 로그 redaction 가드 + 테스트/정책 문서화 | redaction 단위 테스트 + 운영 체크리스트 반영 |
| RB-208 | P3 | 완료 | 운영성 | 마이그레이션/롤백/장애 대응 runbook 확장 (`docs/OPERATION.md`) | 체크리스트 기반 절차 문서 추가 |

## 4) Next Candidates

| ID | Priority | 상태 | 영역 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|
| RB-301 | P1 | 완료 | 테스트가능성 | `health.py` 전이 조건(임계치/윈도우) 경계 테스트 강화 | `app/domain/health.py` 커버리지 90%+ |
| RB-302 | P1 | 완료 | 정확성 | `json_state_repo` 손상/레거시 마이그레이션 경로 정밀 테스트 | 손상/이관 분기 회귀 테스트 케이스 확장 |
| RB-303 | P2 | 완료 | 운영성 | 장애 감지→heartbeat→복구→backfill 통합 시나리오 테스트 | end-to-end 스모크 테스트 추가 |
| RB-304 | P2 | 완료 | 관측성 | 이벤트 기반 알람 룰/대시보드 템플릿 문서화 | `docs/OPERATION.md` 알람 기준 섹션 추가 |

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
| RB-201 | P0 | 완료 | 정확성/데이터무결성 | 마이그레이션 타임스탬프/전송상태 보존 |
| RB-202 | P0 | 완료 | 안정성/운영성 | CLI 실패 경로 표준화 + 실패 이벤트 추가 |
| RB-203 | P1 | 완료 | 테스트가능성 | `service_loop/commands` 테스트 보강 |
| RB-204 | P1 | 완료 | 일관성/관측성 | health_state 저장소 로그 구조화 |
| RB-205 | P1 | 완료 | 문서품질 | TESTING 문서 정합성 갱신 |
| RB-206 | P2 | 완료 | 성능/안정성 | SQLite cleanup SQL 최적화 + bulk 테스트 |
| RB-207 | P2 | 완료 | 보안/운영 | 로그 민감정보 redaction 가드 |
| RB-208 | P3 | 완료 | 운영성 | 마이그레이션/롤백 runbook 확장 |

## 6) Maintenance Rules

- 변경 단위별 품질 게이트(`ruff`, `mypy`, `pytest`) 통과 후 병합
- 기능 변경은 작은 PR/커밋 단위로 진행
- 문서 경계는 `README/SETUP/OPERATION/TESTING/EVENTS/BACKLOG`로 유지
