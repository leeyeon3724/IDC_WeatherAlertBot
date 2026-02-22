# NHN IDC Weather Alert Bot

기상청 특보 API를 주기적으로 조회하고, 규칙 기반으로 Dooray Webhook 알림을 보내는 서비스입니다.

## 1) 핵심 기능
- 지역(`AREA_CODES`)별 특보 조회
- `config/alert_rules.v1.json` 기반 알림 필터링
- 중복 발송 방지(JSON/SQLite 상태 저장소)
- 헬스 상태 감지(장애/복구 이벤트)
- `DRY_RUN`, `RUN_ONCE` 운영 모드 지원

## 2) 빠른 시작
1. 의존성 설치
```bash
make install-dev
```
2. 환경 파일 준비
```bash
cp .env.example .env
```
3. 필수 환경값 설정
- `SERVICE_API_KEY` (원본 키 그대로, 사전 URL 인코딩 금지)
- `SERVICE_HOOK_URL`
- `AREA_CODES`
- `AREA_CODE_MAPPING`
4. 실행
```bash
make run
```

## 3) 자주 쓰는 명령
- 실행: `make run`
- 1회/드라이런: `make dry-run`
- 테스트: `make test`
- 커버리지: `make test-cov`
- 린트/타입체크: `make lint`, `make typecheck`
- 통합 품질 게이트: `make gate`

## 4) 문서 맵
- 설치/초기 설정: `docs/SETUP.md`
- 운영 절차: `docs/OPERATION.md`
- 이벤트 계약: `docs/EVENTS.md`
- 테스트 정책: `docs/TESTING.md`
- 작업 계획: `docs/BACKLOG.md`

## 5) 문서 유지 원칙
- 동일 내용을 여러 문서에 중복 작성하지 않습니다.
- 운영 계약은 `docs/OPERATION.md`, `docs/EVENTS.md`를 단일 기준으로 유지합니다.
- 완료된 작업 내역은 백로그가 아니라 Git 히스토리(PR/커밋)로 추적합니다.
