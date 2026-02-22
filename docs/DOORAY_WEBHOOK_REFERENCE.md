# 두레이 인커밍 웹훅 명세 문서

**작성일**: 2026-02-21  
**최종 수정**: 2026-02-22 (`HTTP 200` + JSON 파싱 실패 시 성공 처리 정책 반영)

이 문서는 두레이(Dooray) 인커밍 웹훅의 상태 코드 처리, 응답 구조, 사용 방식을 체계적으로 정리한 것입니다.
명세 기반 권장 처리와 이 프로젝트의 현재 구현 상태를 분리해 기록합니다.

## 1) 기본 개념 및 흐름

두레이 인커밍 웹훅은 외부 서비스에서 두레이 채팅방으로 HTTP POST 요청을 보내 메시지를 게시하는 기능입니다.

- 발급 방법:
  두레이 메신저 > 채팅방 설정 > 서비스 연동 > Incoming 추가 > 연동 URL 복사
- 전송 제한:
  초당 1회 발송 권장
- 요청 형식:
  JSON 바디 (`Content-Type: application/json`)
- 기본 페이로드:

```json
{
  "botName": "봇 이름",
  "text": "메시지 내용",
  "botIconImage": "아이콘 URL (선택)"
}
```

## 2) 상태 코드 및 성공 판정 기준

이 프로젝트는 실운영 안정성을 위해 `HTTP 200`을 우선 성공으로 간주합니다.
다만 응답 JSON을 파싱할 수 있고 `header.isSuccessful == false`가 확인되면 실패로 처리합니다.

### 2-1) HTTP 상태 코드

| 코드 | 의미 | 처리 지침 |
|---:|---|---|
| 200 | 성공(요청 도달 및 처리) | 기본 성공 처리, 단 JSON `header.isSuccessful=false`면 실패 |
| 301 | 리다이렉션(드물게 발생) | 재시도 또는 경고 로그 |
| 4xx | 클라이언트 오류(포맷/인증/요청 문제) | 요청 수정 후 재전송, 자동 재시도 금지 |
| 5xx | 서버 오류(두레이 측 장애) | 지수 백오프 재시도 |

### 2-2) 응답 바디 구조

응답은 JSON이며 핵심은 `header.isSuccessful`, `header.resultCode`, `header.resultMessage`입니다.

성공 예시:

```json
{
  "header": {
    "isSuccessful": true,
    "resultCode": "0",
    "resultMessage": "Success"
  },
  "result": {}
}
```

실패 예시:

```json
{
  "header": {
    "isSuccessful": false,
    "resultCode": "INVALID_PAYLOAD",
    "resultMessage": "text field is required."
  }
}
```

판정 기준:

- `HTTP 200` + JSON 파싱 실패: 성공(전송 완료로 간주)
- `HTTP 200` + `header.isSuccessful == true`: 성공
- `HTTP 200` + `header.isSuccessful == false`: 실패
- `HTTP 4xx/5xx`: 실패 (`5xx`는 재시도 대상)

## 3) 구현 체크리스트

1. POST 요청 전송 (`application/json`)
2. HTTP 200 여부 확인
3. 응답 JSON 파싱 시도(실패해도 `HTTP 200`이면 성공 처리)
4. JSON 파싱 성공 시 `header.isSuccessful == false` 여부 확인
5. 실패 시 `resultCode`/`resultMessage` 로그 기록
6. 4xx는 재시도하지 않고 설정/요청 수정
7. 5xx/타임아웃은 지수 백오프 재시도

## 4) 재시도 및 모니터링 전략

| 시나리오 | 권장 동작 |
|---|---|
| HTTP 4xx | 로그 + 즉시 알림(요청/설정 오류), 자동 재시도 금지 |
| HTTP 5xx 또는 타임아웃 | 지수 백오프 재시도(예: 1s -> 2s -> 4s, 최대 3회) |
| `isSuccessful=false` | `resultCode` 분기 처리 + 원문 로그 보존 |
| `HTTP 200` + JSON 파싱 실패 | 성공 처리(중복 재시도 방지), 운영 로그로 추적 |

운영 관측 권장 항목:

- HTTP 상태 코드 분포
- `resultCode` 상위 N개
- 재시도 횟수/최종 실패율
- 타임아웃/5xx 급증 시점 알림

## 5) 프로젝트 적용 상태

기준 코드:
- `app/services/notifier.py`
- `app/entrypoints/runtime_builder.py`
- `app/settings.py`

적용 현황:
- 응답 성공 판정:
  `HTTP 200`은 우선 성공 처리하고, JSON 파싱 성공 시에만 `header.isSuccessful`를 추가 검증
- 실패 전파:
  `isSuccessful=false` 또는 `header` 블록 불일치 시 `NotificationError.last_error`에 `resultCode`/`resultMessage` 포함 문자열 전파
- 재시도 분기:
  `HTTP 4xx`는 즉시 실패(재시도 없음), `HTTP 5xx`/`Timeout`/`ConnectionError`는 지수 백오프 재시도
- 전송률 제한:
  전역 전송률 제한 기본값 `NOTIFIER_SEND_RATE_LIMIT_PER_SEC=1.0`(초당 1회), `0`이면 비활성

운영 확인 포인트:
- `notification.retry`는 재시도 대상(5xx/timeout/연결오류)에만 기록
- `notification.final_failure.error`에서 `resultCode`/`resultMessage` 확인 가능
- 연속 실패 시 `notification.circuit.*` 이벤트와 함께 원인 분리

주의: 두레이 정책/응답 스키마 변경 가능성이 있으므로 운영 적용 전 공식 도움말을 최우선 기준으로 재확인하세요.
