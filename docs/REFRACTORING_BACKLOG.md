# Refactoring Backlog

## Current Status

완료:

- `P0`: 관측 이벤트 taxonomy 도입 (`app/observability/events.py`)
- `P1`: Weather API 페이지네이션 + 수집 요약 로그
- `P2`: `cli.py` / `process_cycle.py` 오케스트레이션 분해
- `P3`: 저장소 추상화 + SQLite 저장소 도입
- 테스트 적절성 문서화 (`docs/TESTING.md`) + 보완 테스트 추가

현재 기준 문서 경계:

- `README.md`: 프로젝트 진입
- `docs/SETUP.md`: 설치/설정
- `docs/OPERATION.md`: 운영/장애 대응
- `docs/TESTING.md`: 테스트 전략/평가
- `docs/REFRACTORING_BACKLOG.md`: 개선 계획

## Backlog

| ID | Priority | Status | 작업 | 완료 조건 |
|---|---|---|---|---|
| RB-11 | P1 | Done | 로그 이벤트 사전 문서화(운영자용) | 이벤트별 필수 필드/샘플 로그 문서화 |
| RB-12 | P1 | Open | `area.fetch.summary` 대시보드 지표 정의 | 수집량/실패율/재시도율 기준 확정 |
| RB-13 | P2 | Open | JSON -> SQLite 마이그레이션 유틸 추가 | 샘플 데이터 마이그레이션 검증 테스트 |
| RB-14 | P2 | Open | 저장소 선택 운영 가이드 보강 | `json/sqlite` 선택 기준과 롤백 절차 문서화 |
| RB-15 | P3 | Open | 진입점 테스트에서 monkeypatch 의존 축소 | 통합 성격 테스트 추가로 대체 |
| RB-16 | P1 | Done | 상태/파싱 유틸 경계 테스트 보강 | `tests/test_state_models.py` 추가 |
| RB-17 | P1 | Done | 페이지네이션 경계 테스트 보강 | NODATA 페이지/invalid totalCount 테스트 추가 |

## Maintenance Rules

- 기능 변경은 작은 단위로 반영하고 단계별로 테스트 통과 확인
- 의미 있는 변경 단위마다 커밋 수행(Conventional Commits)
- 문서는 역할 경계를 유지하고 중복 설명은 제거
