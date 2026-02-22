# TESTING

이 문서는 테스트 실행 기준, 현재 적절성, 남은 리스크를 간결하게 관리합니다.

## 1) 실행 명령

```bash
make gate              # 전체 품질 게이트(lint/type/test/cov)
make testing-snapshot  # docs/TESTING.md 수치 자동 갱신
make live-e2e-local    # 실자격증명 1회 검증(ENABLE_LIVE_E2E=true 필요)
```

## 2) 현재 스냅샷

- 테스트 수: `340`
- 전체 커버리지: `92.72%`
- 최소 커버리지 기준: `80%`

## 3) 현재 기준

- 기본 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `check_settings_sync`, `check_area_mapping_sync`, `pytest --cov`
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

## 6) 테스트 그룹 분류(6개)

| 그룹 | 대상 파일(패턴) | 충분성 | 실질적 유효성 | 적절성 | 평가 |
|---|---|---|---|---|---|
| G1 런타임/오케스트레이션 | `test_main*.py`, `test_commands.py`, `test_runtime_builder.py`, `test_service_loop*.py`, `test_process_cycle*.py` | 상 | 상 | 중 | 핵심 실행 흐름과 장애 분기 검증은 충분. 다만 비예상 예외의 관측 계약 검증이 약함 |
| G2 도메인/규칙 | `test_alert_rules.py`, `test_domain.py`, `test_health_*.py`, `test_code_maps_deprecation.py` | 상 | 상 | 상 | 규칙 파싱/메시지/헬스 판단 기준이 명확히 검증됨 |
| G3 상태저장소/마이그레이션 | `test_json_state_repo.py`, `test_sqlite_state_repo.py`, `test_state_*.py`, `test_health_state_repo.py` | 상 | 상 | 중 | CRUD·정리·마이그레이션은 충분. 중복/공통 시나리오 표현 개선 여지 존재 |
| G4 외부연동/API | `test_weather_api.py`, `test_notifier.py`, `test_container_healthcheck.py`, `test_dockerfile_hardening.py` | 중 | 상 | 중 | 재시도/에러코드 중심 검증은 강함. 필수 XML 태그 누락 케이스는 매트릭스화 필요 |
| G5 거버넌스/계약/동기화 | `test_*_sync.py`, `test_architecture_rules.py`, `test_repo_hygiene.py`, `test_pr_checklist.py`, `test_contract_snapshots.py`, `test_select_tests.py`, `test_update_testing_snapshot.py` | 상 | 상 | 상 | 운영 규약·계약 회귀를 안정적으로 방어 |
| G6 운영/성능 리포트 | `test_perf_baseline.py`, `test_compare_perf_reports.py`, `test_slo_report.py`, `test_soak_report.py`, `test_canary_report.py` | 중 | 중 | 중 | 합성 시나리오 중심으로 실용적이나 경계값/가독성 리팩토링 여지 존재 |

## 7) 그룹 평가 기반 개선 항목

- G1: `service_loop`의 미예상 예외 경로에서 `shutdown.unexpected_error` 이벤트 계약을 명시 검증
- G4: `weather_api` 필수 XML 태그 누락 케이스를 파라미터 매트릭스로 보강
- G1/G3: `settings` 테스트의 필수 환경변수 준비 로직 중복 제거(공용 helper/fixture)
