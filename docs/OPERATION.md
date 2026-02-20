# OPERATION

## 1. 처리 흐름

`app/entrypoints/cli.py` + `app/usecases/process_cycle.py`가 아래 순서로 동작합니다.

1. 현재 시각(KST) 기준으로 조회 범위 계산(`오늘~내일`)
2. `AREA_CODES`를 순회하며 지역별 특보 조회
3. XML 파싱 후 메시지 텍스트 생성
4. 이벤트 ID 기준으로 신규 특보를 상태 저장소에 등록
5. 지역별 미전송 이벤트를 Dooray로 발송하고 `sent=true`로 변경
6. 상태 파일(`sent_messages.json`) 저장

`DRY_RUN=true`인 경우 5단계 전송은 수행하지 않고 `notification.dry_run` 로그만 남깁니다.

## 2. 재시도/지연 정책

- API 호출 실패 시 최대 `MAX_RETRIES`만큼 재시도
- 재시도 간격은 `RETRY_DELAY_SEC` 기반 백오프 적용
- Webhook 전송 실패 시 `NOTIFIER_MAX_RETRIES`만큼 재시도
- Webhook 최종 실패는 `notification.final_failure` 로그로 기록
- 조회 시작일은 `LOOKBACK_DAYS`로 과거 확장 가능
- 지역 API 조회는 `AREA_MAX_WORKERS` 범위에서 제한 병렬 처리
- 지역 간 지연: `AREA_INTERVAL_SEC` (순차 모드에서만 적용)
- 병렬 모드(`AREA_MAX_WORKERS > 1`)에서는 지역 간 지연을 무시하고
  `cycle.area_interval_ignored` 로그를 남김
- 사이클 간 지연: `CYCLE_INTERVAL_SEC`

## 3. 타임아웃 정책

- API 요청 timeout:
  - `REQUEST_CONNECT_TIMEOUT_SEC`
  - `REQUEST_READ_TIMEOUT_SEC`
- Webhook 요청 timeout:
  - `NOTIFIER_CONNECT_TIMEOUT_SEC`
  - `NOTIFIER_READ_TIMEOUT_SEC`

## 4. 상태 정리 정책

- 서비스 프로세스가 하루 1회 자동 정리를 수행합니다.
- 기본 정책:
  - 보존 기간: `30일`
  - 삭제 대상: `sent/unsent` 모두
- 관련 설정:
  - `CLEANUP_ENABLED`
  - `CLEANUP_RETENTION_DAYS`
  - `CLEANUP_INCLUDE_UNSENT`

## 5. 중복 전송 방지 방식

- 이벤트 식별자(`stn_id`,`tm_fc`,`tm_seq`,`command`,`cancel`)를 우선 키로 사용합니다.
- 식별자가 없는 경우 이벤트 필드 기반 해시 키를 사용합니다.
- 상태값:
  - `sent=false`: 미전송
  - `sent=true`: 전송 완료
- 전송 완료 상태는 사이클 내 배치 저장으로 반영합니다.

## 6. 전송 메시지 구성

- 특보 본문: 특보 종류/강도/지역/발표-해제 상태 기반으로 생성
- 첨부 링크: `stn_id`, `tm_fc`, `tm_seq`가 있으면 기상청 통보문 URL 첨부
- URL 파라미터가 불완전/유효하지 않으면 첨부를 차단하고 `notification.url_attachment_blocked` 로그를 남깁니다.

## 7. 운영 체크리스트

1. `SERVICE_API_KEY`, `SERVICE_HOOK_URL`가 유효한지 확인
2. `AREA_CODES`, `AREA_CODE_MAPPING` JSON 형식이 올바른지 확인
3. `sent_messages.json` 파일 권한/영속화 설정 확인
4. 로그에서 아래 키워드 모니터링
   - `notification.sent`
   - `notification.dry_run`
   - `notification.url_attachment_blocked`
   - `notification.final_failure`
   - `area.failed`

## 8. 장애 대응 포인트

- API 응답 코드 오류: `WeatherApiError` 발생 후 해당 지역 실패 로그
- 네트워크 오류: 백오프 재시도 후 실패 시 `area.failed` 로그
- Webhook 오류: 실패 이벤트는 미전송 상태로 유지되어 다음 주기에 재시도
