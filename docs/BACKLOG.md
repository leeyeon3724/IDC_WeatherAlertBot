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
