# TESTING

이 문서는 테스트 전략, 현재 적절성 평가, 보완 방향을 다룹니다.

## 1. 실행 명령

```bash
python3 -m ruff check .
python3 -m mypy
python3 -m pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc
```

## 2. 현재 스냅샷

- 테스트 수: `67`
- 전체 커버리지: `85.82%`
- 최소 커버리지 기준: `80%`

## 3. 테스트 적절성 평가

강점:

- 핵심 비즈니스 흐름(중복 방지, 재시도, 장애/복구)은 테스트로 보호됨
- `json/sqlite` 저장소가 각각 독립 테스트로 검증됨
- 설정 파싱/검증 실패 케이스가 비교적 촘촘함

리스크/보완 포인트:

- 진입점(`cli.py`)은 monkeypatch 중심 테스트 비중이 높아 리팩토링 내성이 낮을 수 있음
- 파서/시간 유틸처럼 작은 단위 모듈은 경계값 테스트가 누락되기 쉬움
- 페이지네이션 분기는 외부 API 변형(예: NODATA 페이지, 잘못된 totalCount) 대응 테스트가 필요함

## 4. 최근 보완 사항

- `state_models` 파싱 경계값 테스트 추가 (`tests/test_state_models.py`)
- Weather API 페이지네이션 경계 테스트 추가 (`tests/test_weather_api.py`)
- 저장소 팩토리 선택 경로 테스트 보강 (`tests/test_main.py`)

## 5. 다음 개선 우선순위

1. `cli.py`의 helper 단위 테스트 추가(루프 내부 분기별)
2. JSON->SQLite 마이그레이션 유틸 도입 시 회귀 테스트 템플릿 추가
3. 운영 장애 시나리오(장애 감지 -> heartbeat -> 복구 -> backfill) 통합 성격 테스트 강화
