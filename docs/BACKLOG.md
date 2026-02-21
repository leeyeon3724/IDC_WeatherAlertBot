# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하고, 이 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21`

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_repo_hygiene`, `pytest --cov`
- 테스트: `167 passed`
- 커버리지: `91.54%` (최저 기준 `80%`)
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog

| ID | Priority | 상태 | 주제 | 문제/리스크 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|---|
| RB-901 | P1 | 진행중 | 상태검증 신뢰성 강화 | `state_verifier` 커버리지(`73%`)가 상대적으로 낮아 회귀 탐지 사각 가능 | `tests/test_state_verifier.py`에 경계/오류 분기 테스트 추가, 누락 분기 커버 | `state_verifier` 커버리지 `>= 85%` + 관련 테스트 PASS |
| RB-902 | P1 | 진행중 | 실연동 검증 결과 표준화 | 로컬 live-e2e는 로그 중심, canary/live-e2e CI는 report 중심이라 비교/추적 일관성 약함 | 로컬 실행 후 `canary_report`/`slo_report` 형식의 JSON/MD 아티팩트 생성 경로 추가 | 로컬/CI 모두 동일 필드(`status`, `required_events`, `SLO`)로 리포트 생성 |
| RB-903 | P2 | 진행중 | 테스트 지표 문서 자동화 | `docs/TESTING.md`의 테스트 수/커버리지 수치가 수동 관리되어 드리프트 위험 | `make test-cov` 결과를 문서 스냅샷으로 갱신하는 스크립트/명령 추가 | 문서 수치가 자동 생성값과 일치, 수동 수정 포인트 제거 |
| RB-904 | P2 | 진행중 | 환경 설정 일관성 점검 강화 | `.env.example`/`.env.live-e2e.example`/`docker-compose.yml` 간 기본값 차이를 사람이 놓칠 수 있음 | 설정 diff 체크 스크립트(허용 차이 allowlist 포함) + CI 검사 추가 | 허용되지 않은 설정 차이 발생 시 CI 실패 |
| RB-905 | P3 | 진행중 | 유지보수 문서 경량화 | 문서 간 일부 내용이 중복되어 변경 시 동기화 비용 증가 | `README`는 진입점, 상세는 `SETUP/OPERATION/TESTING`에 위임하도록 중복 제거 | 문서 역할 경계 명확, 중복 섹션 최소화 |

## 3) 운영 관찰 (참고, 완료 게이트 아님)

- canary/soak/live-e2e 성공률 추세
- `notification.circuit.*`, `notification.backpressure.applied`, `pending_total` 추세
- `State integrity verification smoke` 실패 추세
- fast/full 테스트 실행 비중 및 소요시간 추세

운영 관찰 세부 기준은 `docs/OPERATION.md`를 따릅니다.

## 4) 운영 규칙

- 상태 값은 `진행중`, `완료`만 사용
- 완료 판단은 **현재 코드/테스트/문서 기준**으로 수행
- 운영데이터는 완료 게이트가 아니라 `3) 운영 관찰`로 별도 추적
- 백로그 항목은 작은 단위 커밋으로 진행하고, 완료 시 본 문서 상태를 즉시 갱신
