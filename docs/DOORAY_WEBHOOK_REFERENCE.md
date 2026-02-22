# Dooray Webhook Reference (Project Scope)

이 문서는 프로젝트에서 실제 사용하는 Webhook 요청/검증 규칙만 요약합니다.

## 1) Endpoint
- `SERVICE_HOOK_URL` (필수, `https`)

## 2) 요청 Payload
- 기본 필드
  - `botName`
  - `text`
- 선택 필드
  - `attachments` (통보문 링크 포함 시)

예시:
```json
{
  "botName": "기상특보알림",
  "text": "[특보] ...",
  "attachments": [
    {
      "title": "> 해당 특보 통보문 바로가기",
      "titleLink": "https://...",
      "color": "blue"
    }
  ]
}
```

## 3) 성공 판정 규칙
- HTTP 2xx 응답
- 응답이 JSON이고 `header.isSuccessful`이 존재하면 `true`여야 성공
- 응답 본문이 비JSON/빈값이어도 HTTP 2xx이면 성공으로 처리

## 4) 재시도/보호 정책
- 재시도 가능 오류: timeout, connection, 5xx 등
- 재시도 제외: Dooray 비즈니스 실패(`isSuccessful=false`)
- 회로 차단기(circuit breaker): 연속 실패 임계치 도달 시 일정 시간 전송 차단
- 주요 설정: `NOTIFIER_MAX_RETRIES`, `NOTIFIER_RETRY_DELAY_SEC`, `NOTIFIER_CIRCUIT_*`
