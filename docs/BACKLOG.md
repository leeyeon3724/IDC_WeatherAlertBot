# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하고, 이 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21` (계약/스냅샷·테스트인프라 패치 완료 반영)

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `pytest --cov`
- 테스트: `214 passed`
- 커버리지: `94.02%` (최저 기준 `80%`)
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (문서 근거 기반)

- 상태: `완료`
  - 항목: 도메인 메시지/URL 검증 테스트 분기 보강
  - 근거: `tests/test_domain.py`가 `invalid_tm_seq`, 무파라미터 URL(`report_url=None, error=None`), 시간 누락 시 `"특정 시간"` 메시지 분기를 검증하지 않아 핵심 분기 회귀 탐지력이 제한됨
  - 완료 기준:
    - `invalid_tm_seq`/무파라미터/시간 누락 템플릿 테스트 추가
    - `event_id` 검증을 접두사 중심에서 핵심 구성요소 포함 검증으로 강화

- 상태: `완료`
  - 항목: 헬스 알림 메시지 테스트 정합성/탐지력 강화
  - 근거: `tests/test_health_message_builder.py`는 `startswith`/부분 문자열 위주 단정으로 템플릿 회귀(필드 누락, 비율/지속시간 포맷 오류) 탐지력이 낮음
  - 완료 기준:
    - 이벤트별 필수 라인/필드(비율, 카운트, duration, representative_error) 단정 추가
    - 미지원 이벤트(empty message) 및 duration 경계(0분/시간 전환) 케이스 추가

- 상태: `완료`
  - 항목: 헬스 모니터 정책 경계/누적 상태 테스트 보강
  - 근거: `tests/test_health_monitor.py`는 backoff multiplier(2/4/8), max_backoff cap, incident counter/error_counts 누적/복구 reset 분기 검증이 부족함
  - 완료 기준:
    - `suggested_cycle_interval_sec`의 임계 단계 및 cap 단정 추가
    - 장애 중 누적 카운터/에러 집계와 recovery 시 reset 동작 단정 추가

- 상태: `완료`
  - 항목: 로깅 유틸 테스트의 전역 logger 상태 격리(순서 의존 제거)
  - 근거: `tests/test_logging_utils.py`가 `weather_alert_bot` logger의 handler/propagate를 전역으로 변경해, `tests/test_json_state_repo.py`/`tests/test_health_state_repo.py`의 caplog 검증이 실행 순서에 따라 실패할 수 있음(재현: logging_utils 선실행 시 7건 실패)
  - 완료 기준:
    - 로깅 테스트에 teardown/fixture로 logger 상태 완전 복원
    - 순서 의존 회귀 검증(`logging_utils` + 저장소 로그 테스트 조합) 추가

- 상태: `완료`
  - 항목: 외부 연동 서비스 테스트의 실패 경로 탐지력 보강(weather_api/notifier)
  - 근거: `tests/test_weather_api.py`는 `fetch_alerts` 경로의 API result-code 오류(`API_ERROR_RESULT`) 통합 검증이 없고, `tests/test_notifier.py`는 circuit breaker 비활성 경로/양수 backoff 증가 시퀀스 검증이 부족함
  - 완료 기준:
    - weather_api result-code 오류 통합 시나리오 추가
    - notifier의 circuit disabled 및 backoff(1,2,4...) 경로 단정 추가

- 상태: `완료`
  - 항목: 상태 저장소/검증 테스트의 경계·오류 분기 보강
  - 근거: `tests/test_json_state_repo.py`/`tests/test_sqlite_state_repo.py`에 `cleanup_stale(days<0)` 예외 경로, `mark_sent` 미존재 ID 경로 검증이 부족하고 `tests/test_state_verifier.py`는 aggregate(strict/non-strict) 경계 시나리오 보강 여지 있음
  - 완료 기준:
    - json/sqlite 저장소의 음수 days/미존재 event_id 경계 테스트 추가
    - verifier aggregate 경계(strict false warning-only pass, strict true fail) 단정 추가

- 상태: `완료`
  - 항목: 품질 게이트 동기화 테스트의 실패 경로/스키마 불일치 분기 보강
  - 근거: `tests/test_alarm_rules_sync.py`, `tests/test_event_docs_sync.py`, `tests/test_env_defaults_sync.py`가 pass + 단일 불일치 케이스 중심이라 duplicate rule key, unknown/missing 이벤트, 파싱 실패(구조화 로그/compose/env) 경로 회귀 탐지력이 낮음
  - 완료 기준:
    - alarm/event/env sync 계열에 duplicate/missing/unknown/invalid parse 분기 테스트 추가
    - 실패 리포트 필드(`*_mismatches`, `missing_*`, `unknown_*`)를 정확 키 단위로 단정

- 상태: `완료`
  - 항목: 게이트 오케스트레이션 스크립트 테스트의 경계값/예외 처리 강화
  - 근거: `tests/test_pr_checklist.py`, `tests/test_select_tests.py`, `tests/test_update_testing_snapshot.py`, `tests/test_repo_hygiene.py`는 주 경로 검증 위주이며, 체크리스트 누락 품질 항목, 변경파일 비어있음/미매핑 full fallback, 스냅샷 섹션 미존재/파싱 실패, live-e2e JSON 타입 오류 등 핵심 에러 분기 검증이 부족함
  - 완료 기준:
    - PR checklist의 quality-check 미선택/이벤트 영향도 불필요 경로 분리 테스트 추가
    - select_tests의 empty/unknown/full-gate marker/테스트파일 직접 변경 경로 단정 추가
    - update_testing_snapshot 예외(`parse 실패`, `섹션 없음`) 테스트 추가
    - repo_hygiene JSON 타입 불일치(`expected_list`, `expected_dict`) 단정 추가

- 상태: `진행중`
  - 항목: 성능/운영 리포트 테스트의 SLO 게이트 경계·입력 검증 분기 보강
  - 근거: `tests/test_perf_baseline.py`, `tests/test_compare_perf_reports.py`, `tests/test_canary_report.py`, `tests/test_soak_report.py`, `tests/test_slo_report.py`에서 base=0 회귀 판정, better=higher 해석, canary webhook probe 파일 오류, soak 입력 검증(`cycles/area_count<=0`) 및 budget 분기, SLO p95/attempts fallback 미해결 분기 검증이 누락됨
  - 완료 기준:
    - perf baseline/compare의 zero-base, better=higher, invalid input(max_samples<=0) 테스트 추가
    - canary webhook probe missing/invalid payload 및 service exit-only 실패 분기 테스트 추가
    - soak 입력 예외 및 pending/duplicate/memory budget 초과 분기 테스트 추가
    - slo p95 초과/attempts fallback unresolved 경로 단정 추가

- 상태: `완료`
  - 항목: 계약/스냅샷 회귀 테스트의 실행 위치 독립성(CWD independence) 확보
  - 근거: `tests/test_contract_snapshots.py`의 `build_event_payload_contract(Path("app"))` 호출이 현재 작업 디렉터리에 의존해 `cd tests` 환경에서 실패함(재현: `cd tests && pytest -q test_contract_snapshots.py` -> `event_payload_contract` 비교 실패)
  - 완료 기준:
    - 계약 스냅샷 테스트에서 소스 루트를 `Path(__file__).resolve()` 기반 절대/프로젝트 루트 경로로 고정
    - 작업 디렉터리 변경 시에도 동일하게 통과하는 회귀 테스트(또는 동등 검증) 추가

- 상태: `완료`
  - 항목: 계약 스냅샷 테스트 정합성 강화(의미적 계약 vs 하드코딩 값 분리)
  - 근거: `tests/test_contract_snapshots.py`의 CLI 계약에서 `default_command`가 파서/엔트리포인트 파생값이 아닌 하드코딩(`"run"`)이고, settings 계약은 `name/has_default/default`만 검증해 타입/필수성 변경 회귀 탐지력이 제한됨
  - 완료 기준:
    - CLI default command를 파서/엔트리포인트 동작에서 유도해 계약화하고 하드코딩 제거
    - settings 계약에 필드 타입(또는 직렬화된 type id)과 기본값 존재성 규칙을 포함해 단정 보강
    - 스냅샷 비교 실패 시 변경 이벤트를 빠르게 식별할 수 있는 diff 중심 assertion 메시지 도입

- 상태: `완료`
  - 항목: 테스트 하네스(main_test_harness) 드리프트 정리 및 공용 픽스처 명확화
  - 근거: `tests/main_test_harness.py`가 현재 엔트리포인트 호출 경로에서 사용되지 않는 패치(`entrypoint.datetime`)를 포함하고, 런타임 패치 책임이 한 함수에 집중되어 리팩토링 후 무효 패치가 누적될 위험이 있음
  - 완료 기준:
    - 사용되지 않는/효과 없는 패치 제거 및 실제 호출 경로 기준 패치만 유지
    - 상태 저장소/노티파이어/프로세서 패치를 fixture 단위로 분리해 테스트 의도를 명시
    - 하네스 패치가 실제로 적용되었는지 확인하는 최소 검증 테스트 추가

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
