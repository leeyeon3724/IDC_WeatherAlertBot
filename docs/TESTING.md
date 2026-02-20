# TESTING

이 문서는 테스트 전략, 현재 적절성 평가, 보완 방향을 다룹니다.

## 1. 실행 명령

```bash
python3 -m ruff check .
python3 -m mypy
python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc
```

## 2. 현재 스냅샷

- 테스트 수: `85`
- 전체 커버리지: `87.48%`
- 최소 커버리지 기준: `80%`

## 3. 테스트 적절성 평가

강점:

- 핵심 비즈니스 흐름(중복 방지, 재시도, 장애/복구)은 테스트로 보호됨
- `json/sqlite` 저장소가 각각 독립 테스트로 검증됨
- 설정 파싱/검증 실패 케이스가 비교적 촘촘함

리스크/보완 포인트:

- 엔트리포인트 분리 후에도 `service_loop/commands`의 예외 분기 테스트 밀도가 낮음
- `health_state_repo` 손상 파일/마이그레이션 경계 케이스는 커버리지 개선 여지가 있음
- 마이그레이션은 상태 개수/sent 여부는 검증되지만 타임스탬프 보존 검증이 부족함

## 4. 최근 보완 사항

- `state_models` 파싱 경계값 테스트 추가 (`tests/test_state_models.py`)
- Weather API 페이지네이션 경계 테스트 추가 (`tests/test_weather_api.py`)
- 엔트리포인트 테스트를 helper/smoke 구조로 분리 (`tests/main_test_harness.py`, `tests/test_main_smoke.py`)
- JSON->SQLite 마이그레이션 회귀 테스트 추가 (`tests/test_state_migration.py`)

## 5. 다음 개선 우선순위

1. `service_loop.py`, `commands.py` 분기/예외 테스트 보강
2. JSON->SQLite 마이그레이션 타임스탬프 보존 회귀 테스트 추가
3. 운영 장애 시나리오(장애 감지 -> heartbeat -> 복구 -> backfill) 통합 성격 테스트 강화
