# TESTING

이 문서는 테스트 전략, 현재 적절성 평가, 보완 방향을 다룹니다.

## 1. 실행 명령

```bash
python3 -m ruff check .
python3 -m mypy
python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc
```

## 2. 현재 스냅샷

- 테스트 수: `109`
- 전체 커버리지: `91.05%`
- 최소 커버리지 기준: `80%`

## 3. 테스트 적절성 평가

강점:

- 핵심 비즈니스 흐름(중복 방지, 재시도, 장애/복구)은 테스트로 보호됨
- `json/sqlite` 저장소가 각각 독립 테스트로 검증됨
- 설정 파싱/검증 실패 케이스가 비교적 촘촘함

리스크/보완 포인트:

- `health_state_repo`의 파일 I/O 예외 분기는 핵심 경로 대비 커버리지가 낮은 편
- `json_state_repo`는 분기 테스트가 강화됐지만 로그 이벤트를 문자열로 직접 구성해 일관성 개선 여지 존재
- redaction은 단위 테스트는 있으나 이벤트 로그 통합 시나리오 검증 범위를 더 넓힐 수 있음
- `settings.py`는 환경변수 파싱 책임이 커서 회귀 시 영향 반경이 넓고 섹션 단위 검증 강화가 필요
- `weather_api.py`는 경계 입력(`totalCount` 비정상, 페이지 경계 NODATA) 커버리지 여지가 남아 있음

## 4. 최근 보완 사항

- `state_models` 파싱 경계값 테스트 추가 (`tests/test_state_models.py`)
- Weather API 페이지네이션 경계 테스트 추가 (`tests/test_weather_api.py`)
- 엔트리포인트 테스트를 helper/smoke 구조로 분리 (`tests/main_test_harness.py`, `tests/test_main_smoke.py`)
- JSON->SQLite 마이그레이션 회귀 테스트 추가 (`tests/test_state_migration.py`)
- `service_loop` 분기/예외/sleep 경로 테스트 추가 (`tests/test_service_loop.py`)
- `commands` 실패 이벤트/종료코드 테스트 추가 (`tests/test_commands.py`)
- `health.py` 경계/정규화 테스트 추가 (`tests/test_health_domain.py`)
- `json_state_repo` 손상/백업 실패/정규화 분기 테스트 추가 (`tests/test_json_state_repo.py`)
- 장애 감지→heartbeat→복구→backfill 통합 스모크 테스트 추가 (`tests/test_service_loop_integration.py`)

## 5. 다음 개선 우선순위

1. `health_state_repo`의 파일 I/O 실패 분기(backup/persist) 테스트 확대
2. `json_state_repo` 로그 이벤트를 `log_event()` 기반으로 통일하고 회귀 테스트 보강
3. `settings.from_env`를 섹션 단위로 분해할 수 있도록 테스트를 정책별(네트워크/저장소/헬스)로 보강
4. `weather_api`의 결과코드/페이지네이션 경계 케이스 회귀 테스트 확대
5. redaction이 적용된 이벤트 로그 통합 시나리오 테스트 추가
