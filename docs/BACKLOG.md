# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하고, 이 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21` (아키텍처 리뷰 반영)

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `pytest --cov`
- 테스트: `200 passed`
- 커버리지: `93.63%` (최저 기준 `80%`)
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (문서 근거 기반)

| ID | Priority | 상태 | 주제 | 문제/리스크 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|---|
| RB-901 | P1 | 완료 | 상태검증 신뢰성 강화 | `state_verifier` 커버리지(`73%`)가 상대적으로 낮아 회귀 탐지 사각 가능 | `tests/test_state_verifier.py`에 경계/오류 분기 테스트 추가, 누락 분기 커버 | `state_verifier` 커버리지 `>= 85%` + 관련 테스트 PASS |
| RB-902 | P1 | 완료 | 실연동 검증 결과 표준화 | 로컬 live-e2e는 로그 중심, canary/live-e2e CI는 report 중심이라 비교/추적 일관성 약함 | 로컬 실행 후 `canary_report`/`slo_report` 형식의 JSON/MD 아티팩트 생성 경로 추가 | 로컬/CI 모두 동일 필드(`status`, `required_events`, `SLO`)로 리포트 생성 |
| RB-903 | P2 | 완료 | 테스트 지표 문서 자동화 | `docs/TESTING.md`의 테스트 수/커버리지 수치가 수동 관리되어 드리프트 위험 | `make test-cov` 결과를 문서 스냅샷으로 갱신하는 스크립트/명령 추가 | 문서 수치가 자동 생성값과 일치, 수동 수정 포인트 제거 |
| RB-904 | P2 | 완료 | 환경 설정 일관성 점검 강화 | `.env.example`/`.env.live-e2e.example`/`docker-compose.yml` 간 기본값 차이를 사람이 놓칠 수 있음 | 설정 diff 체크 스크립트(허용 차이 allowlist 포함) + CI 검사 추가 | 허용되지 않은 설정 차이 발생 시 CI 실패 |
| RB-905 | P3 | 완료 | 유지보수 문서 경량화 | 문서 간 일부 내용이 중복되어 변경 시 동기화 비용 증가 | `README`는 진입점, 상세는 `SETUP/OPERATION/TESTING`에 위임하도록 중복 제거 | 문서 역할 경계 명확, 중복 섹션 최소화 |
| RB-906 | P1 | 완료 | 병렬 조회 스레드 안전성 강화 | 운영 문서상 지역 병렬 조회를 사용하며, HTTP 세션 공유 시 간헐 장애/비결정 동작 리스크 | 병렬 조회 경로에서 세션 격리(스레드별 세션/클라이언트) 또는 동시성 안전 구조로 리팩토링 | 병렬 경로 회귀 테스트 추가 + 장기 soak/canary에서 `area.failed` 비정상 증가 없음 |
| RB-907 | P1 | 완료 | 상태 저장소 기본전략 정비 | 운영 문서상 상태 무결성/마이그레이션 절차가 중요하며, JSON 기본 운용은 데이터 증가 시 성능/복구 부담 | 기본 저장소 전략을 SQLite 중심으로 정비하고 JSON은 호환/복구 경로로 역할 분리 | 신규 배포 기본값이 SQLite로 동작 + `migrate-state`/`verify-state --strict` CI 스모크 유지 |
| RB-908 | P1 | 완료 | 루프 장애 격리 및 자가회복 | 운영 가이드에 장애 분리 대응이 있으나, 단일 예외 전파 시 프로세스 중단 리스크가 큼 | 사이클 내부 예외를 범주화해 치명/비치명 분리, 비치명 오류는 서비스 지속 + 계측 강화 | 비치명 예외 주입 테스트에서 프로세스 계속 동작 + 치명 오류만 종료 |
| RB-909 | P2 | 완료 | 복구 백필 실행 예산화 | 운영 문서상 복구 후 backfill 수행 시 단일 사이클 지연이 커질 수 있어 알람 지연 위험 | backfill을 시간/건수 예산 기반으로 분할 실행하거나 별도 잡으로 분리 | 백필 중에도 주기 지연 상한 충족(`cycle_latency_p95`) + 기능 회귀 없음 |
| RB-910 | P2 | 완료 | SLO 리포트 강건성 개선 | `docs/TESTING.md` 리스크와 운영 SLO 자동화 기준 대비, 로그 필드 누락 시 판정 신뢰성 저하 | `slo_report`에 필드 누락 원인 분류(로그 포맷/수집 공백/코드 누락) 및 보정 로직 추가 | canary/live-e2e SLO 리포트에서 실패 원인 분류가 명확하고 재현 테스트 제공 |
| RB-911 | P2 | 완료 | 성능 회귀 게이트 구체화 | 문서상 perf baseline은 추세 지표라 절대 기준 부재, 회귀 탐지 자동화가 약함 | 핵심 지표별 허용 회귀율(예: +20%)을 정의하고 PR 비교 리포트에 fail 조건 추가 | 회귀율 초과 PR 자동 실패 + 허용치/예외 처리 규칙 문서화 |
| RB-912 | P3 | 완료 | 운영 알람 규칙 테스트화 | 운영 문서 알람 매핑은 정의돼 있으나 규칙 변경 시 회귀를 자동 검증하기 어려움 | 주요 이벤트/임계값 매핑을 스키마화하고 검증 스크립트+테스트 추가 | 알람 규칙 변경 시 문서/코드 불일치 CI 실패 + 샘플 로그 기반 테스트 PASS |
| RB-913 | P1 | 진행중 | WeatherClient Protocol 추상화 | `ProcessCycleUseCase._fetch_alerts_with_worker_client`가 `isinstance(WeatherAlertClient)` 구체 타입 검사로 Protocol 추상화를 깨뜨림. 모의 클라이언트 주입 시 병렬 경로가 의도치 않게 직렬 경로로 폴백됨 | `WeatherClient` Protocol에 `new_worker_client()` · `close()` 추가, `ProcessCycleUseCase`에서 `isinstance` 제거, 테스트용 `FakeWeatherClient`에 메서드 구현 | `isinstance` 제거 + mypy 통과 + 병렬 경로 회귀 테스트 PASS |
| RB-914 | P1 | 진행중 | SQLite upsert 원자성 통일 | `upsert_notifications`은 read-then-write 패턴으로 구현되어 있으나 `upsert_stored_notifications`는 `ON CONFLICT DO UPDATE`로 원자적 처리. 두 경로의 일관성이 없어 혼동 유발 | `upsert_notifications`을 `ON CONFLICT(event_id) DO UPDATE SET ... WHERE 필드가 변경된 경우`로 통일 | 단일 SQL 실행 + 기존 행위 동등성 테스트 PASS |
| RB-915 | P2 | 진행중 | 웹훅 URL 로그 마스킹 누락 | `redact_sensitive_text()`가 `SERVICE_API_KEY`는 마스킹하나 `SERVICE_HOOK_URL`(Dooray 토큰 포함)은 제외. 요청 예외 발생 시 로그에 웹훅 토큰이 노출될 수 있음 | `hook.dooray.com` URL 패턴을 redact 정규식에 추가 + 관련 테스트 추가 | 웹훅 URL이 로그에서 `***` 처리됨 + 테스트 PASS |
| RB-916 | P2 | 진행중 | mark_sent 이중 커넥션 제거 | `SqliteStateRepository.mark_sent()`가 `mark_many_sent()` 호출(커넥션 1) 후 행 존재 확인(커넥션 2)으로 불필요한 커넥션 오픈/클로즈 반복 | 단일 커넥션 내 UPDATE + SELECT로 통합 | 커넥션 1회만 사용 + 기존 행위 동등성 테스트 PASS |
| RB-917 | P2 | 진행중 | retry_delay_sec=0 백오프 버그 | `max(backoff_seconds * 2, 1)` 로직으로 `retry_delay_sec=0` 설정 시 첫 재시도 후 지연이 1초로 고정되어 "즉시 재시도" 설정이 무시됨 | `max(backoff_seconds * 2, self.retry_delay_sec)` 방식으로 수정. notifier/weather_api 두 곳 모두 적용 | `retry_delay_sec=0`에서 모든 재시도 지연 0 + 관련 테스트 PASS |
| RB-918 | P3 | 진행중 | _parse_str_env 헬퍼 추가 | `bot_name`, `timezone`, `log_level` 파싱에서 `os.getenv("K", "d").strip() or "d"` 이중 폴백 패턴이 반복되어 의도가 불명확하고 누락 시 버그 유발 가능 | `_parse_str_env(name, default)` 헬퍼 추출, 문자열 설정 파싱 일관화 | 헬퍼 함수 추가 + 관련 파싱 위임 + 기존 테스트 PASS |
| RB-919 | P3 | 진행중 | 죽은 코드 _parse_alerts 제거 | `WeatherAlertClient._parse_alerts()`가 어디서도 호출되지 않는 미사용 메서드로 유지보수 혼란 유발 | 메서드 제거 + 관련 참조 확인 | 메서드 제거 + mypy/테스트 PASS |
| RB-920 | P3 | 진행중 | 테스트 assert 스타일 개선 | `test_notifier.py`에서 `assert False, "NotificationError expected"` 패턴 사용으로 다른 예외 발생 시 오해를 유발하는 실패 메시지 출력 | `pytest.raises()` 컨텍스트 매니저로 교체 | `pytest.raises` 사용 + 테스트 PASS |
| RB-921 | P3 | 진행중 | 웹훅 페이로드 검증 테스트 추가 | `test_notifier.py`가 호출 횟수만 검증하고 실제 전송 payload(`botName`, `text`, `attachments`)를 검증하지 않아 필드 오기입 회귀를 탐지 못함 | payload 구조 검증 테스트 추가(`botName`, `text`, 첨부 포함/미포함 두 케이스) | 페이로드 내용 검증 테스트 PASS |

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
