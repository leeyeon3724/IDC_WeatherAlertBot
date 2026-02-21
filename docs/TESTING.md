# TESTING

이 문서는 테스트 실행 기준, 현재 적절성, 남은 리스크를 간결하게 관리합니다.

## 1) 실행 명령

```bash
make gate              # 전체 품질 게이트(lint/type/test/cov)
make testing-snapshot  # docs/TESTING.md 수치 자동 갱신
make live-e2e-local    # 실자격증명 1회 검증(ENABLE_LIVE_E2E=true 필요)
```

## 2) 현재 스냅샷

- 테스트 수: `289`
- 전체 커버리지: `94.73%`
- 최소 커버리지 기준: `80%`

## 3) 현재 기준

- 기본 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `check_area_mapping_sync`, `pytest --cov`
- 테스트 스냅샷 자동화: `make testing-snapshot`으로 테스트 수/커버리지 수치를 문서에 반영
- CI 계층:
  - 기본 CI(`ci.yml`): gate + runtime smoke + 상태 무결성 smoke(`migrate-state` -> `verify-state --strict`)
  - PR fast(`pr-fast.yml`): 변경 파일 기반 선택 실행, 미매핑 시 full fallback
  - Nightly full(`nightly-full.yml`): 주기적 `make gate` 전체 회귀 점검
- 외부 연동 계층:
  - Canary(`canary.yml`): 실 API + webhook 경로 점검
  - Live E2E(`live-e2e.yml`): 보호 환경 실자격증명 검증
  - 로컬 Live E2E: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`
- 운영/성능 계층:
  - Soak(`soak.yml`): 장시간 합성 부하 예산 검증
  - SLO(`scripts/slo_report.py`): 성공률/실패율/지연/잔량 산출
  - 성능 회귀(`scripts.compare_perf_reports`): 핵심 지표 회귀율 `> 20%` 실패
- 계약 회귀: 이벤트 이름/페이로드, 설정, CLI 스냅샷 테스트 유지

## 4) 남은 리스크

- 이벤트 문서 동기화는 이름/핵심 필드 중심이므로 필드 의미 변경은 코드리뷰 보완 필요
- 성능 baseline/soak는 합성 지표이므로 실운영 장애 판단은 canary/live-e2e/운영 관측과 함께 해석 필요
- live-e2e 실패는 코드 회귀와 외부 의존성 장애를 분리해서 판정해야 함

## 5) 우선순위

- 현재 활성 테스트 백로그 없음
- 신규 리스크는 `docs/BACKLOG.md`에 등록 후 진행
