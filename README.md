# NHN_IDC_WeatherAlertBot

기상청 특보(Open API)를 주기적으로 조회해 중복을 제거한 뒤, 신규 특보만 Dooray Incoming Webhook으로 전송하는 알림 봇입니다.

## 빠른 시작

1. 의존성 설치
```bash
pip install -r requirements.txt
```
2. 환경변수 파일 생성
```bash
cp .env.example .env
```
3. `.env` 값 수정
4. 실행
```bash
python main.py
```

설정 상세는 `docs/SETUP.md`를 참고하세요.
`.env` 파일은 `.gitignore`로 제외되어 커밋되지 않습니다.

## 문서 인덱스

- `docs/SETUP.md`: 설치, 환경변수, 로컬/도커 실행
- `docs/OPERATION.md`: 처리 흐름, 재시도/중복방지, 로그 및 운영 체크포인트

## 코드 구조

- `app/entrypoints/cli.py`: 애플리케이션 CLI/서비스 진입점
- `main.py`: 하위 호환 실행 래퍼
- `app/settings.py`: 환경변수 로드 및 검증
- `app/usecases/process_cycle.py`: 1개 사이클 처리 오케스트레이션
- `app/services/weather_api.py`: 기상청 API 조회/파싱
- `app/services/notifier.py`: Dooray Webhook 전송
- `app/repositories/state_repo.py`: 상태 저장소(JSON, 원자적 저장)
- `app/domain/models.py`: 도메인 모델 및 이벤트 식별자
- `app/domain/message_builder.py`: 특보 메시지 생성
- `Dockerfile`: 컨테이너 실행 정의
- `data/sent_messages.json`: 전송 상태 파일(런타임 생성)
- `.env.example`: 로컬 설정 템플릿

## 테스트

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

CI와 동일한 로컬 품질 게이트 실행:

```bash
python -m ruff check .
python -m mypy
pytest -q --cov=app --cov-report=term-missing --cov-config=.coveragerc
```

## 1회 Dry-Run

```bash
export DRY_RUN=true
export RUN_ONCE=true
python main.py
```

## 상태 정리

```bash
python main.py cleanup-state --days 30
```

서비스 실행 중에는 기본값으로 하루 1회 자동 정리(`30일`, sent/unsent 모두 삭제)가 수행됩니다.

`LOOKBACK_DAYS`를 설정하면 오늘 이전 특보까지 조회 범위를 확장할 수 있습니다.
`AREA_MAX_WORKERS`를 설정하면 지역 API 조회를 제한 병렬 처리할 수 있습니다.

## API 장애 알림/복구

- 단기 실패는 즉시 알리지 않고 장애 강도 기준을 충족할 때만 알림을 보냅니다.
- 장애 감지 기준(기본값):
  - 최근 10분 심각 실패 사이클 6회 이상
  - 연속 심각 실패 4회 이상
  - 심각 실패 기준: `area_fail_ratio >= 0.7`
- 복구 기준(기본값):
  - 최근 15분 실패비율 `<= 0.1`
  - 연속 안정 사이클 8회 이상
- 장애 지속 중 heartbeat 알림 주기: `HEALTH_HEARTBEAT_INTERVAL_SEC` (기본 3600초)
- 장애 중에는 사이클 간격을 자동 완화(backoff)하며, 복구 시 outage 길이에 따라 1회 backfill 조회를 수행합니다.

## Makefile

```bash
make install
make install-dev
make setup-hooks
make dry-run
make test
make quality
```

## Docker Compose

```bash
docker compose up -d --build
docker compose logs -f weather-alert-bot
```

Compose 설정은 운영 기준(`DRY_RUN=false`, `RUN_ONCE=false`)으로 동작합니다.

## Commit Message Rules

커밋 메시지는 Conventional Commits 형식으로 강제됩니다.

```text
<type>(<scope>): <subject>
```

예시:

- `feat(alert): add run-once mode`
- `fix(url): use special-report endpoint`
- `docs(setup): add env-file instructions`

설치:

```bash
make setup-hooks
```
