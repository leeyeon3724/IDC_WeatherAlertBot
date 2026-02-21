# OPERATION

이 문서는 런타임 동작, 관측 포인트, 장애 대응만 다룹니다.
설치/환경변수 설정은 `docs/SETUP.md`를 참고하세요.

## 1. 사이클 동작 요약

1. 조회 기간 계산(`today - LOOKBACK_DAYS` ~ `today + 1`)
2. 지역별 특보 조회(순차 또는 제한 병렬)
3. 특보 이벤트를 알림 메시지로 변환
4. 상태 저장소에 upsert(신규/기존)
5. 미전송 이벤트만 Dooray 전송 후 sent 마킹

관련 코드:

- `app/usecases/process_cycle.py`
- `app/services/weather_api.py`
- `app/services/notifier.py`
- `app/repositories/json_state_repo.py`

## 2. 중복 방지/재전송 규칙

- 기본 이벤트 키: `stn_id + tm_fc + tm_seq + command + cancel`
- 기본 키가 불완전하면 필드 기반 해시 키 사용
- Webhook 실패 이벤트는 `sent=false` 유지 후 다음 사이클 재시도
- `DRY_RUN=true`면 전송 없이 로그만 기록

## 3. 장애 감지/복구 정책

### 장애 감지(outage_detected)

- 최근 `HEALTH_OUTAGE_WINDOW_SEC` 구간에서 심각 실패 사이클 수가 기준 이상
- 연속 심각 실패 횟수가 기준 이상
- 심각 실패 기준: `area_fail_ratio >= HEALTH_OUTAGE_FAIL_RATIO_THRESHOLD`

### 장애 지속(outage_heartbeat)

- 장애 열림 상태에서 `HEALTH_HEARTBEAT_INTERVAL_SEC`마다 heartbeat 전송

### 복구(recovered)

- 최근 `HEALTH_RECOVERY_WINDOW_SEC` 실패 비율이 기준 이하
- 연속 안정 사이클 횟수가 기준 이상
- 복구 시 outage 길이에 따라 1회 backfill 조회 실행(상한: `HEALTH_RECOVERY_BACKFILL_MAX_DAYS`)

## 4. 로그 관측 포인트

- 이벤트 이름/필드 표준은 `docs/EVENTS.md`를 단일 기준으로 사용
- 대시보드/알람은 아래 핵심 이벤트를 우선 추적
- 정상 동작: `startup.ready`, `cycle.complete`, `notification.sent`
- 경고/실패: `area.failed`, `notification.final_failure`, `health.notification.failed`
- 상태 관리: `state.cleanup.auto`, `state.cleanup.complete`, `state.migration.complete`

## 5. 운영 체크리스트

- API 키/웹훅 유효성 확인
- `AREA_CODES`, `AREA_CODE_MAPPING` JSON 형식 확인
- `STATE_REPOSITORY_TYPE`에 맞는 상태 파일 경로/권한 확인
- `data/` 볼륨 영속화 확인(컨테이너 운영 시)
- 실패 로그(`area.failed`, `notification.final_failure`) 증가 추이 확인
- 민감정보 마스킹 확인(`serviceKey`, `apiKey`, `SERVICE_API_KEY` 값이 로그에 노출되지 않는지 점검)

## 6. 자주 발생하는 문제

### API 호출 실패가 지속될 때

- 네트워크/서비스키/호출 제한 상태 확인
- `area.failed`의 `error_code` 분포 확인

### 전송 실패가 지속될 때

- Webhook URL 변경 여부 확인
- `notification.final_failure`의 `attempts`, `error` 확인

### 상태 파일 이상(손상/포맷 오류)

- 저장소는 손상 JSON 감지 시 `.broken-<timestamp>` 백업 후 빈 상태로 복구
- 이후 중복 방지 상태가 초기화될 수 있으므로 운영 로그로 영향 범위 확인

## 7. 마이그레이션/롤백 런북

### JSON -> SQLite 마이그레이션

1. 서비스 중지 또는 `RUN_ONCE=true`로 단일 실행 상태 전환
2. 기존 JSON 상태 백업
3. 마이그레이션 실행

```bash
python3 main.py migrate-state \
  --json-state-file ./data/sent_messages.json \
  --sqlite-state-file ./data/sent_messages.db
```

4. `state.migration.complete` 이벤트 확인 후 `STATE_REPOSITORY_TYPE=sqlite` 적용

### 마이그레이션 실패 대응

- `state.migration.failed` 이벤트의 `error` 확인
- SQLite 파일 생성/권한/디스크 상태 점검
- 필요 시 기존 JSON 모드(`STATE_REPOSITORY_TYPE=json`)로 즉시 롤백

### 롤백 절차

1. `STATE_REPOSITORY_TYPE=json`으로 설정 복귀
2. 백업한 `sent_messages.json` 복원
3. `RUN_ONCE=true` 점검 실행 후 정상 알림/중복 방지 동작 확인

## 8. 알람 룰 템플릿

### 8.1 API 실패율 급증

- 지표: `area.failed` 이벤트 수 / 5분
- 예시 조건: 5분 합계 `>= 20` 이고 `error_code=timeout|connection` 비중 `>= 60%`
- 대응: 외부 네트워크/서비스 상태 확인, 필요 시 `CYCLE_INTERVAL_SEC` 임시 상향

### 8.2 Webhook 전송 실패 연속 발생

- 지표: `notification.final_failure` 이벤트 수 / 10분
- 예시 조건: 10분 합계 `>= 5`
- 대응: Webhook URL/권한 확인, Dooray 측 수신 상태 확인

### 8.3 장기 장애 상태

- 지표: `health.notification.sent` 중 `health_event=outage_heartbeat`
- 예시 조건: heartbeat 2회 이상 연속 발생(기본 1시간 간격 기준 2시간+)
- 대응: `area.failed` 주요 `error_code` 기준으로 원인 축소 후 우회/복구 수행

### 8.4 상태 정리/마이그레이션 실패

- 지표: `state.cleanup.failed`, `state.migration.failed`
- 예시 조건: 단일 이벤트 발생 시 즉시 경고
- 대응: 파일 권한/디스크 상태/경로 오설정 우선 확인

## 9. 알람-대응 매핑 표

| 신호(Event) | 기본 임계값(예시) | 확인 필드 | 1차 대응 | 후속 조치 |
|---|---|---|---|---|
| `area.failed` | 5분 합계 `>= 20` | `error_code`, `area_code`, `error` | 네트워크/API 상태 점검, 실패 지역 편중 여부 확인 | 임시로 `CYCLE_INTERVAL_SEC` 상향 후 장애 원인 분리 |
| `notification.final_failure` | 10분 합계 `>= 5` | `attempts`, `event_id`, `error` | Webhook URL/권한/수신 시스템 상태 점검 | 실패 이벤트 재전송 여부 확인, 웹훅 교체 시 설정 반영 |
| `health.notification.sent` (`outage_detected`) | 단일 이벤트 즉시 경고 | `health_event`, `incident_duration_sec` | 장애 공지 전파, 외부 의존성 상태 확인 | heartbeat 발생 추세 모니터링 및 복구 조건 점검 |
| `health.notification.sent` (`outage_heartbeat`) | 2회 연속 발생 | `health_event`, `incident_failed_cycles` | 장기 장애로 분류, 우회 경로 검토 | API 실패 코드 분포 기준으로 공급자/네트워크 이슈 분리 |
| `state.cleanup.failed` | 단일 이벤트 즉시 경고 | `state_file`, `error` | 파일 권한/경로/디스크 용량 확인 | 스토리지 정책 수정 및 cleanup 재실행 |
| `state.migration.failed` | 단일 이벤트 즉시 경고 | `json_state_file`, `sqlite_state_file`, `error` | 마이그레이션 중지 후 JSON 모드 롤백 | 원인 제거 후 재마이그레이션, 완료 이벤트 확인 |

운영 규칙:

- 알람 설명에는 반드시 해당 이벤트명과 핵심 필드(`error_code`, `attempts`, `state_file`)를 포함
- 런북 링크는 각 알람에 `8.x` 절차 번호를 명시
- 임계값은 고정값으로 두지 말고 최근 2주 평균 대비 비율로 주기 재조정
