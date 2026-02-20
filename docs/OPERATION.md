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
- `app/repositories/state_repo.py`

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

### 정상 동작 확인

- `startup.ready`
- `cycle.start`
- `notification.sent`
- `cycle.complete`

### 주의/경고

- `notification.url_attachment_blocked`
- `area.failed`
- `notification.final_failure`

### 장애 관련

- `health.evaluate`
- `health.notification.sent`
- `health.notification.failed`
- `health.backfill.start`
- `health.backfill.complete`

## 5. 운영 체크리스트

- API 키/웹훅 유효성 확인
- `AREA_CODES`, `AREA_CODE_MAPPING` JSON 형식 확인
- `STATE_REPOSITORY_TYPE`에 맞는 상태 파일 경로/권한 확인
- `data/` 볼륨 영속화 확인(컨테이너 운영 시)
- 실패 로그(`area.failed`, `notification.final_failure`) 증가 추이 확인

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
