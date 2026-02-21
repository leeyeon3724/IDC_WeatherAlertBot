# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하고, 이 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21` (신뢰성/안정성 리뷰 액션 아이템 반영)

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `pytest --cov`
- 테스트: `210 passed`
- 커버리지: `93.87%` (최저 기준 `80%`)
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (문서 근거 기반)

- 상태: `완료`
  - 항목: 자동 cleanup에서 미전송(`sent=false`) 데이터 보존 기본값으로 전환
  - 근거: `CLEANUP_INCLUDE_UNSENT=true` 기본 설정 시 장기 webhook/API 장애 동안 재시도 대기 알림이 삭제될 수 있음
  - 완료 기준:
    - 기본값을 보수적으로 조정하고(미전송 보존)
    - 관련 테스트/예제 환경변수/운영 문서 동기화

- 상태: `완료`
  - 항목: 전송 backpressure 공정성 개선(지역 순서 고정으로 인한 기아 완화)
  - 근거: `NOTIFIER_MAX_ATTEMPTS_PER_CYCLE` 제한 시 앞선 지역 backlog가 뒤 지역 전송 기회를 지속적으로 선점할 수 있음
  - 완료 기준:
    - 사이클 간 공정한 분배(라운드로빈 등) 적용
    - 다중 지역 시나리오 회귀 테스트 추가

- 상태: `완료`
  - 항목: 비치명 반복 예외 시 최소 재시도 간격 보장
  - 근거: `CYCLE_INTERVAL_SEC=0` 설정에서 반복 오류 발생 시 무지연 루프가 CPU/로그/API 재시도 폭주를 유발할 수 있음
  - 완료 기준:
    - 예외 경로에서 최소 backoff 적용
    - 관련 테스트/운영 문서 반영

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
