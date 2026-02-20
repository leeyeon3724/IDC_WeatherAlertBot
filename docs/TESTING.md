# TESTING

이 문서는 테스트 전략, 현재 적절성 평가, 보완 방향을 다룹니다.

## 1. 실행 명령

```bash
python3 -m ruff check .
python3 -m mypy
python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc
```

## 2. 현재 스냅샷

- 테스트 수: `97`
- 전체 커버리지: `89.37%`
- 최소 커버리지 기준: `80%`

## 3. 테스트 적절성 평가

강점:

- 핵심 비즈니스 흐름(중복 방지, 재시도, 장애/복구)은 테스트로 보호됨
- `json/sqlite` 저장소가 각각 독립 테스트로 검증됨
- 설정 파싱/검증 실패 케이스가 비교적 촘촘함

리스크/보완 포인트:

- `health.py` 상태 전이 경계 케이스(조건 분기)가 상대적으로 미커버 상태
- `json_state_repo`의 손상/레거시 마이그레이션 경로 분기 커버리지가 낮은 편
- 외부 연동 예외 메시지 redaction은 단위 테스트가 있으나 통합 시나리오 보강 여지 존재

## 4. 최근 보완 사항

- `state_models` 파싱 경계값 테스트 추가 (`tests/test_state_models.py`)
- Weather API 페이지네이션 경계 테스트 추가 (`tests/test_weather_api.py`)
- 엔트리포인트 테스트를 helper/smoke 구조로 분리 (`tests/main_test_harness.py`, `tests/test_main_smoke.py`)
- JSON->SQLite 마이그레이션 회귀 테스트 추가 (`tests/test_state_migration.py`)
- `service_loop` 분기/예외/sleep 경로 테스트 추가 (`tests/test_service_loop.py`)
- `commands` 실패 이벤트/종료코드 테스트 추가 (`tests/test_commands.py`)

## 5. 다음 개선 우선순위

1. `health.py` 전이 조건(임계치/윈도우) 경계 테스트 보강
2. `json_state_repo` 손상/마이그레이션 분기 테스트 정밀화
3. 운영 장애 시나리오(장애 감지 -> heartbeat -> 복구 -> backfill) 통합 성격 테스트 강화
