# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하며 본 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21`

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `check_area_mapping_sync`, `pytest --cov`
- 테스트/커버리지 최신 수치: `docs/TESTING.md`의 `## 2) 현재 스냅샷`을 단일 기준으로 사용
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (문서 근거 기반)

상태: 진행중
중요도: 높음
항목: 복구 백필 부분 처리의 지속 실행 보장
근거: `recovered` 이벤트 시점에만 백필이 1회 실행되고, `HEALTH_RECOVERY_BACKFILL_MAX_WINDOWS_PER_CYCLE` 제한으로 남은 구간이 다음 사이클에서 자동 이어지지 않아 장기 장애 후 일부 기간 누락 위험이 존재함.
완료 기준: 백필 진행 상태(예: remaining_days/cursor)를 health state에 영속화하고, 매 사이클 예산 내에서 이어서 처리되며, 재시작 후에도 재개되는 테스트를 추가함.

상태: 진행중
중요도: 중간
항목: `cleanup-state` CLI 인자/동작 정합성 개선
근거: `STATE_REPOSITORY_TYPE=sqlite`일 때 `--state-file`이 사실상 무시되어 운영자가 정리 대상 파일을 오인할 수 있음.
완료 기준: 저장소 타입별 인자 체계를 분리하거나(예: `--json-state-file`, `--sqlite-state-file`) 무시되는 인자 사용 시 명시 오류를 반환하고, 도움말/운영 문서/테스트를 함께 갱신함.

상태: 진행중
중요도: 중간
항목: 런타임 리소스 생명주기(HTTP Session) 정리
근거: 외부 연동 클라이언트의 세션 close 경로가 서비스 종료 흐름에 일관되게 연결되어 있지 않아 장기 실행/테스트에서 리소스 누수 위험이 있음.
완료 기준: notifier/weather client에 일관된 close 인터페이스를 부여하고, `run_loop` 종료(`run_once`, `KeyboardInterrupt`, fatal error) 시 `finally`에서 정리되도록 연결하며, 종료 경로 테스트를 추가함.

상태: 진행중
중요도: 낮음
항목: SQLite 상태 검증기의 DB 연결 정리 보장
근거: 상태 검증 로직의 조기 반환 경로에서 SQLite 연결 close가 명시적으로 보장되지 않음.
완료 기준: 검증 로직을 context manager 또는 `try/finally`로 재구성해 모든 분기에서 close를 보장하고, 반복 호출 시 리소스 누수가 없음을 확인하는 테스트를 추가함.

상태: 진행중
중요도: 중간
항목: 기능 변경 대응을 위한 기상청 코드맵/메시지 규칙 외부화
근거: 경보 코드/명령 코드 매핑이 `app/domain/code_maps.py`와 메시지 빌더 조건문에 하드코딩되어 있어, 신규 코드 추가·의미 변경 시 코드 배포 없이 즉시 반영하기 어렵고 회귀 위험이 큼.
완료 기준: 코드맵/메시지 규칙을 버전된 설정 파일로 분리하고 로딩/검증 계층을 추가하며, 미매핑 코드에 대한 fail-fast 또는 운영 정책 기반 처리 테스트를 마련함.

상태: 진행중
중요도: 중간
항목: 유지보수를 위한 `ProcessCycleUseCase` 책임 분리
근거: 조회, 변환, 상태 upsert, 전송, 백프레셔, 통계 집계가 단일 클래스에 집중되어 기능 추가/삭제 시 영향 범위가 넓고 테스트 픽스처 복잡도가 증가함.
완료 기준: fetch/track/dispatch/statistics를 독립 컴포넌트로 분리하고 public contract를 고정한 뒤, 단위 테스트에서 컴포넌트 단독 검증과 통합 경로 회귀 검증을 분리함.

상태: 진행중
중요도: 중간
항목: 운영 배포 안정화를 위한 graceful shutdown/컨테이너 헬스체크 정비
근거: 런루프는 `KeyboardInterrupt` 중심 종료만 처리하고 SIGTERM 종료 시 정리 동작 보장이 부족하며, 컨테이너 정의에 `HEALTHCHECK`가 없어 오케스트레이터가 비정상 상태를 표준 방식으로 감지하기 어려움.
완료 기준: SIGTERM 수신 시 안전 종료 플로우(사이클 종료/리소스 정리/종료 이벤트 로깅)를 구현하고, Dockerfile 또는 compose에 헬스체크를 추가해 배포 환경에서 자동 감시/재시작 정책과 연동함.

신규 리스크 등록 템플릿:

```text
상태: 진행중
중요도: 높음|중간|낮음
항목: 한 줄 제목
근거: 실패 경로/회귀 위험/재현 조건
완료 기준: 테스트·문서·검증 명확 기준
```

## 3) 운영 규칙

- 상태 값은 `진행중`, `완료`만 사용
- 완료된 항목은 본 문서에서 제거하고 커밋 로그로 추적
- 항목은 작은 단위 커밋으로 진행하고 완료 즉시 상태 반영
