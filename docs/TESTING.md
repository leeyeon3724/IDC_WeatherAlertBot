# TESTING

이 문서는 테스트 전략, 현재 적절성 평가, 보완 방향을 다룹니다.

## 1. 실행 명령

```bash
python3 -m ruff check .
python3 -m mypy
python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc
```

## 2. 현재 스냅샷

- 테스트 수: `131`
- 전체 커버리지: `92.64%`
- 최소 커버리지 기준: `80%`

## 3. 테스트 적절성 평가

강점:

- 핵심 비즈니스 흐름(중복 방지, 재시도, 장애/복구)은 테스트로 보호됨
- `json/sqlite` 저장소가 각각 독립 테스트로 검증됨
- 설정 파싱/검증 실패 케이스가 비교적 촘촘함

리스크/보완 포인트:

- 운영 문서의 알람 룰과 실제 이벤트 필드 변경 간 정합성을 자동 점검하는 장치가 부족함

## 4. 최근 보완 사항

- `state_models` 파싱 경계값 테스트 추가 (`tests/test_state_models.py`)
- Weather API 페이지네이션 경계 테스트 추가 (`tests/test_weather_api.py`)
- 엔트리포인트 테스트를 helper/smoke 구조로 분리 (`tests/main_test_harness.py`, `tests/test_main_smoke.py`)
- JSON->SQLite 마이그레이션 회귀 테스트 추가 (`tests/test_state_migration.py`)
- `service_loop` 분기/예외/sleep 경로 테스트 추가 (`tests/test_service_loop.py`)
- `commands` 실패 이벤트/종료코드 테스트 추가 (`tests/test_commands.py`)
- `health.py` 경계/정규화 테스트 추가 (`tests/test_health_domain.py`)
- `json_state_repo` 손상/백업 실패/정규화 분기 테스트 추가 (`tests/test_json_state_repo.py`)
- `json_state_repo` 오류 로그를 구조화 이벤트(`log_event`)로 통일하고 이벤트 필드 단언 테스트 반영
- `health_state_repo` backup/persist 실패 경로 테스트 추가 (`tests/test_health_state_repo.py`)
- `json_state_repo` persist 실패 경로 테스트 추가 (`tests/test_json_state_repo.py`)
- `settings.from_env`를 섹션별 파서로 분해하고 네트워크/런타임 경계 테스트 추가 (`tests/test_settings.py`)
- `weather_api` 결과코드/페이지네이션/파싱 경계 테스트 확장 (`tests/test_weather_api.py`)
- `process_cycle` 에러 이벤트의 민감정보 redaction 통합 시나리오 테스트 추가 (`tests/test_process_cycle.py`)
- `sqlite_state_repo` 대량 경로 배치 실행(`executemany`) 회귀 가드 테스트 추가 (`tests/test_sqlite_state_repo.py`)
- `health_monitor` 정책 조합(짧은 heartbeat/긴 recovery window) 시뮬레이션 테스트 추가 (`tests/test_health_monitor.py`)
- 장애 감지→heartbeat→복구→backfill 통합 스모크 테스트 추가 (`tests/test_service_loop_integration.py`)

## 5. 다음 개선 우선순위

1. 이벤트 기반 알람 룰과 운영 대응(runbook) 간 매핑 자동 점검 보강
2. CI에서 Python 버전/실행 환경 차이에도 안정적인 성능 회귀 신호를 남길 수 있는 경량 벤치 리포트 추가
3. 운영 이벤트 스키마 변경 시(`events.py`) 문서 누락을 감지하는 문서 정합성 검사 추가
