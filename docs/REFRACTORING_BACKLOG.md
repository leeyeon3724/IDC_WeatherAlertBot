# Refactoring Backlog

기준: `docs/CODEBASE_ASSESSMENT.md`의 평가 결과 기반

## Prioritized Backlog

| ID | Priority | 상태 | 영역 | 작업 | 기대효과 | 완료조건(DoD) |
|---|---|---|---|---|---|---|
| RB-101 | P0 | 완료 | 보안/정확성 | 기상청 API `http-only` 제약 반영한 보완 통제 적용(허용 도메인/경로 검증 + 운영 통제) | 불가능한 `https` 전환 과제 제거, 현실적 보안 강화 | 문서/설정검증/테스트 동시 반영 |
| RB-102 | P0 | 완료 | 보안 | URL 검증 정책 분리(Webhook=`https` 강제, Weather API=허용목록 기반 `http`) | 오설정/취약 URL 입력 차단 | 설정 검증 테스트 추가 |
| RB-103 | P1 | 완료 | 결합도 | `HealthStateRepository` 프로토콜 도입 및 `ApiHealthMonitor` 추상화 의존으로 전환 | 저장소 교체 용이성/테스트 단순화 | health monitor 테스트 무회귀 |
| RB-104 | P1 | 완료 | 복잡성 | `cli.py`를 `runtime_builder.py`, `service_loop.py`, `commands.py`로 분리 | 진입점 복잡도/변경 충돌 감소 | 기존 엔트리 동작 동일 + 테스트 통과 |
| RB-105 | P1 | 완료 | 가독성/응집도 | `settings.py`의 코드 매핑 상수 분리(`domain/code_maps.py`) | 설정 책임 명확화 | weather/settings 테스트 무회귀 |
| RB-106 | P1 | 완료 | 일관성 | notifier/weather_api 재시도 로그를 `log_event()`로 통일 | 관측 일관성 향상 | 비구조 로그 제거 |
| RB-107 | P2 | 완료 | 성능/안정성 | SQLite에 `PRAGMA busy_timeout`, WAL 모드 적용 | 락 충돌 내성/쓰기 안정성 향상 | 동시 접근 테스트 추가 |
| RB-108 | P2 | 완료 | 성능 | SQLite upsert/mark 경로 batch 최적화(`executemany`) | 대량 이벤트 처리 성능 개선 | 벤치마크/회귀 테스트 통과 |
| RB-109 | P2 | 완료 | 성능 | JSON 저장소 `pending_count` 비용 최적화 | 반복 조회 부하 축소 | 기존 기능/테스트 무회귀 |
| RB-110 | P2 | 대기 | 테스트가능성 | `tests/test_main.py` monkeypatch 의존도 축소(헬퍼/통합 스모크 분리) | 테스트 유지보수성 향상 | 테스트 구조 단순화 및 커버리지 유지 |
| RB-111 | P3 | 대기 | 운영성 | 이벤트 사전 문서(`docs/EVENTS.md`) 신설 | 온콜 대응/대시보드 표준화 | 핵심 이벤트 필드 정의 완료 |
| RB-112 | P3 | 대기 | 운영성 | JSON->SQLite 마이그레이션 유틸 추가 | 저장소 전환 리스크 축소 | 샘플 마이그레이션 검증 테스트 |

## Suggested Iteration Plan

1. Iteration 1 (안전성 우선)
- RB-101, RB-102, RB-103

2. Iteration 2 (구조 정리)
- RB-104, RB-105, RB-106

3. Iteration 3 (성능/운영)
- RB-107, RB-108, RB-109, RB-110

4. Iteration 4 (운영 완성)
- RB-111, RB-112

## Maintenance Rules

- 변경 단위별 품질 게이트(`ruff`, `mypy`, `pytest`) 통과 후 병합
- 기능 변경은 작은 PR/커밋 단위로 진행
- 문서는 `README/SETUP/OPERATION/TESTING/BACKLOG` 경계 유지
