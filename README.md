# NHN IDC Weather Alert Bot

기상청 특보(Open API)를 주기적으로 조회해, 중복을 제거한 신규 특보만 Dooray Incoming Webhook으로 전송하는 봇입니다.

## 빠른 시작

```bash
pip install -r requirements.txt
cp .env.example .env
# .env 값 수정
python3 main.py
```

1회 점검 실행:

```bash
DRY_RUN=true RUN_ONCE=true python3 main.py
```

## 주요 명령어

```bash
make install
make install-dev
make test
make gate
make check-arch
make check-hygiene
make perf-report
make perf-baseline
make soak-report
make check-docs
python3 main.py cleanup-state --days 30
python3 main.py migrate-state --json-state-file ./data/sent_messages.json --sqlite-state-file ./data/sent_messages.db
python3 main.py verify-state --json-state-file ./data/sent_messages.json --sqlite-state-file ./data/sent_messages.db --strict
```

## 문서

- `docs/SETUP.md`: 설치, 환경변수, 로컬/도커 실행
- `docs/OPERATION.md`: 런타임 동작, 로그 관측, 장애 대응
- `docs/EVENTS.md`: 구조화 로그 이벤트/필드 사전
- `docs/TESTING.md`: 테스트 전략, 적절성 평가, 보완 항목
- `docs/BACKLOG.md`: 코드베이스 평가 + 리팩토링 백로그 통합 문서

## 디렉터리 구조

- `app/entrypoints/`: CLI 진입점
- `app/usecases/`: 사이클/헬스 오케스트레이션
- `app/services/`: 외부 API/Webhook 연동
- `app/repositories/`: 상태 저장소(JSON/SQLite)
- `app/domain/`: 도메인 모델/메시지 생성
- `tests/`: 단위 테스트
