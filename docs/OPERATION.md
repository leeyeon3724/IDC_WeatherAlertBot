# OPERATION

이 문서는 런타임 동작, 관측 포인트, 장애 대응만 다룹니다.
설치/환경변수 설정은 `docs/SETUP.md`를 참고하세요.

## 1. 런타임 요약

1. 조회 기간 계산(`today - LOOKBACK_DAYS` ~ `today + 1`)
2. 지역별 조회(순차 또는 제한 병렬)
3. 상태 저장소 upsert 및 미전송 전송
4. 헬스 평가/알림, 필요 시 복구 backfill
5. 주기 대기 후 반복

핵심 코드:
- `app/usecases/process_cycle.py`
- `app/entrypoints/service_loop.py`
- `app/services/weather_api.py`
- `app/services/notifier.py`

## 2. 운영 기본 규칙

- 이벤트 표준은 `docs/EVENTS.md`를 단일 기준으로 사용
- 중복 방지 키는 이벤트 ID(불완전 시 해시) 사용
- 전송 실패는 `sent=false`로 유지되어 다음 사이클 재시도
- `DRY_RUN=true`는 전송 없이 로그만 기록

## 3. 운영 체크리스트

- API 키/웹훅/지역코드 설정 유효성 확인
- 상태 저장소 파일 경로/권한/디스크 여유 확인
- 실패 이벤트(`area.failed`, `notification.final_failure`) 증가 추이 확인
- 민감정보 마스킹(`serviceKey`, `apiKey`, `SERVICE_API_KEY`) 확인

## 4. 빠른 런북

API 실패 지속:
- `area.failed`의 `error_code` 분포로 원인 분리(네트워크/timeout/기타)

Webhook 실패 지속:
- `notification.final_failure`의 `attempts`, `error` 확인

상태 파일 손상:
- `.broken-<timestamp>` 백업 파일 생성 여부 확인 후 복구 절차 수행

JSON -> SQLite 마이그레이션:

```bash
python3 main.py migrate-state \
  --json-state-file ./data/sent_messages.json \
  --sqlite-state-file ./data/sent_messages.db
```

- 성공 기준: `state.migration.complete`
- 실패 시: `state.migration.failed` 확인 후 `STATE_REPOSITORY_TYPE=json` 롤백

## 5. 알람 매핑

| 신호(Event) | 기본 임계값(예시) | 확인 필드 | 1차 대응 | 후속 조치 |
|---|---|---|---|---|
| `cycle.cost.metrics` | 1시간 평균 대비 `api_fetch_calls` 또는 `notification_attempts` `>= 2x` | `api_fetch_calls`, `notification_attempts`, `notification_failures`, `pending_total` | 호출량/전송량 급증 구간 확인, 최근 설정/장애 이벤트와 상관관계 점검 | `AREA_CODES`, 재시도/주기 설정 재조정 후 24시간 추세 재평가 |
| `area.failed` | 5분 합계 `>= 20` | `error_code`, `area_code`, `error` | 네트워크/API 상태 점검, 실패 지역 편중 여부 확인 | 임시로 `CYCLE_INTERVAL_SEC` 상향 후 장애 원인 분리 |
| `notification.final_failure` | 10분 합계 `>= 5` | `attempts`, `event_id`, `error` | Webhook URL/권한/수신 시스템 상태 점검 | 실패 이벤트 재전송 여부 확인, 웹훅 교체 시 설정 반영 |
| `health.notification.sent` (`outage_detected`) | 단일 이벤트 즉시 경고 | `health_event`, `incident_duration_sec` | 장애 공지 전파, 외부 의존성 상태 확인 | heartbeat 발생 추세 모니터링 및 복구 조건 점검 |
| `health.notification.sent` (`outage_heartbeat`) | 2회 연속 발생 | `health_event`, `incident_failed_cycles` | 장기 장애로 분류, 우회 경로 검토 | API 실패 코드 분포 기준으로 공급자/네트워크 이슈 분리 |
| `state.cleanup.failed` | 단일 이벤트 즉시 경고 | `state_file`, `error` | 파일 권한/경로/디스크 용량 확인 | 스토리지 정책 수정 및 cleanup 재실행 |
| `state.migration.failed` | 단일 이벤트 즉시 경고 | `json_state_file`, `sqlite_state_file`, `error` | 마이그레이션 중지 후 JSON 모드 롤백 | 원인 제거 후 재마이그레이션, 완료 이벤트 확인 |

## 6. 성능 리포트 정책

- 기준 스크립트: `python3 -m scripts.perf_baseline --max-samples 20`
- 샘플 정책: baseline 계산 시 입력 리포트 중 최근 `20`개만 유지/집계
- 추세 확인: baseline markdown의 `trend` 컬럼으로 지표 변화 방향을 우선 확인
