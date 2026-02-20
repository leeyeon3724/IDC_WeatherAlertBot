# Refactoring Backlog

## Current Status

진행 완료:

- `P0`: 관측 이벤트 taxonomy 도입 (`app/observability/events.py`)
- `P1`: Weather API 페이지네이션 + 수집 요약 로그
- `P2`: `cli.py` / `process_cycle.py` 오케스트레이션 분해
- `P3`: 저장소 추상화 + SQLite 저장소 도입

현재 프로젝트 기본 구조:

- `app/entrypoints`: 실행 진입점/런타임 조립
- `app/usecases`: 사이클/헬스 유스케이스
- `app/services`: 외부 연동(API/Webhook)
- `app/repositories`: 상태 저장소 구현(json/sqlite) + 인터페이스
- `app/domain`: 도메인 모델/메시지
- `app/observability`: 로그 이벤트 상수

## Active Backlog

| ID | Priority | 작업 | 완료 조건 |
|---|---|---|---|
| RB-11 | P1 | 로그 이벤트 사전 문서화(운영자용) | 이벤트별 필수 필드/샘플 로그 문서화 |
| RB-12 | P1 | `area.fetch.summary` 대시보드 지표 정의 | 수집량/실패율/재시도율 기준 확정 |
| RB-13 | P2 | JSON -> SQLite 마이그레이션 유틸 추가 | 샘플 데이터 마이그레이션 검증 테스트 |
| RB-14 | P2 | 저장소 선택 운영 가이드 보강 | `json/sqlite` 선택 기준과 롤백 절차 문서화 |
| RB-15 | P3 | 진입점 테스트에서 monkeypatch 의존 축소 | 통합 성격 테스트 추가로 대체 |

## Maintenance Rules

- 기능 변경은 “작은 단위”로 반영하고 각 단위마다 테스트 통과 확인
- 의미 있는 변경 단위마다 커밋 수행(Conventional Commits)
- 문서는 `README(진입) / SETUP(설치) / OPERATION(운영) / BACKLOG(계획)` 경계 유지
