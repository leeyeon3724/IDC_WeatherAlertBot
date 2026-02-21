# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하고, 이 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21` (아키텍처 리뷰 2차 반영)

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `pytest --cov`
- 테스트: `204 passed`
- 커버리지: `93.82%` (최저 기준 `80%`)
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (문서 근거 기반)

| ID | Priority | 상태 | 주제 | 문제/리스크 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|---|
| RB-922 | P1 | 진행중 | DoorayNotifier 서킷브레이커 스레드 안전성 | `_consecutive_failures`/`_circuit_open_until_monotonic`이 스레드 비안전 변수. 병렬 `send()` 호출 시 레이스 컨디션으로 카운터 오염·서킷 미개방 가능 | `threading.Lock`을 `send()`·`_is_circuit_open()`·`_close_circuit_if_ready()` 진입부에 추가 | 다중 스레드 동시 `send()` 테스트에서 카운터 일관성 유지 + mypy/테스트 PASS |
| RB-923 | P2 | 진행중 | JSON 저장소 동시 쓰기 제한 문서화 | `json_state_repo.py`의 load-modify-write 패턴은 단일 프로세스 내 원자적이나 프로세스 간 파일 락 없음. 복구 스크립트와 서비스 동시 기동 시 데이터 손실 가능 | "단일 프로세스 전용" 제약을 class docstring 및 `docs/OPERATION.md`에 명시; 또는 `fcntl.flock`으로 파일 락 적용 | 동시 접근 제약이 문서화됨 + 기존 테스트 PASS |
| RB-924 | P2 | 진행중 | Settings 기동 시 timezone 유효성 검증 | `TIMEZONE` 환경변수가 런타임 `ZoneInfo()` 호출까지 검증되지 않아 첫 사이클 실행 전까지 오류 미검출 | `_parse_str_env` 이후 `ZoneInfo(value)` 시도, `KeyError` 발생 시 `SettingsError` 발생 | 잘못된 `TIMEZONE` 설정 시 `Settings.from_env()` 즉시 실패 + 테스트 추가 |
| RB-925 | P2 | 진행중 | AREA_CODE_MAPPING 완전성 검증 | `AREA_CODES`에 코드가 있어도 `AREA_CODE_MAPPING` 누락 시 "알 수 없는 지역"으로 무음 폴백. 운영자 설정 오류를 기동 시점에 탐지 못함 | `_parse_runtime_config()`에서 `set(area_codes) - set(mapping.keys())` 검사 후 비어 있지 않으면 `SettingsError` 발생 | 매핑 누락 시 기동 즉시 실패 + 테스트 추가 |
| RB-926 | P2 | 진행중 | process_cycle 누락 지역 에러 코드 구체화 | `_resolve_area_result()`에서 결과 없을 때 생성하는 `WeatherApiError`의 `code`가 `"unknown_error"` 기본값이라 운영 대시보드에서 "조회 미시도"와 "실제 API 실패"가 구분 불가 | `WeatherApiError` 생성 시 `code="missing_area_fetch_result"` 명시, `_handle_area_failure()` 통계 분류 확인 | 오류 카운터에 `missing_area_fetch_result`로 기록됨 + 테스트 추가 |
| RB-927 | P3 | 진행중 | notifier.py `type: ignore[operator]` 제거 | `DoorayNotifier.send()` line 80의 `# type: ignore[operator]`가 향후 로직 버그를 은폐할 수 있음. `assert`로 타입 좁히기 가능 | `assert self._circuit_open_until_monotonic is not None` 삽입 후 ignore 주석 제거 | mypy `--strict` 통과 + `type: ignore` 제거됨 |

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
