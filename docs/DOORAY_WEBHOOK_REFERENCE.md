# 두레이 인커밍 웹훅 명세 문서

**문서 버전**: 1.0  
**작성일**: 2026-02-21  
**대상**: 두레이 웹훅 연동 개발자

이 문서는 두레이(Dooray) 인커밍 웹훅의 상태 코드 처리, 응답 구조, 사용 방식을 체계적으로 정리한 것입니다.
명세 기반 권장 처리와 이 프로젝트의 현재 구현 상태를 분리해 기록합니다.

## 0) 문서 범위

- 명세/권장 처리:
  Dooray 공식 도움말 기준의 권장 성공 판정/재시도 정책
- 프로젝트 현재 구현:
  `app/services/notifier.py`의 실제 동작 기준(운영 시점 판정 로직)

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

두레이 응답은 HTTP 상태 코드와 응답 JSON의 `header` 블록을 함께 봐야 합니다.
HTTP 200만으로 성공 처리하지 말고 `header.isSuccessful`를 반드시 확인합니다.

### 2-1) HTTP 상태 코드

| 코드 | 의미 | 처리 지침 |
|---:|---|---|
| 200 | 성공(요청 도달 및 처리) | 바디 `header` 확인 필수 |
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

- `header.isSuccessful == true`: 성공
- `header.isSuccessful == false`: 실패
- `header` 파싱 실패: 실패로 간주(방어 처리)

## 3) 구현 체크리스트

1. POST 요청 전송 (`application/json`)
2. HTTP 200 여부 확인
3. 응답 JSON 파싱
4. `header.isSuccessful == true` 확인
5. 실패 시 `resultCode`/`resultMessage` 로그 기록
6. 4xx는 재시도하지 않고 설정/요청 수정
7. 5xx/타임아웃은 지수 백오프 재시도

샘플(PHP/cURL):

```php
$payload = ['botName' => '서버 모니터링', 'text' => '상태 알림'];
$data = json_encode($payload);

$ch = curl_init();
curl_setopt($ch, CURLOPT_URL, '두레이_웹훅_URL');
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
curl_setopt($ch, CURLOPT_POSTFIELDS, $data);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($httpCode === 200) {
    $json = json_decode($response, true);
    if (!empty($json['header']['isSuccessful'])) {
        echo "성공";
    } else {
        error_log("실패: " . ($json['header']['resultMessage'] ?? 'unknown'));
    }
} else {
    error_log("HTTP 오류: $httpCode");
}
```

## 4) 재시도 및 모니터링 전략

| 시나리오 | 권장 동작 |
|---|---|
| HTTP 4xx | 로그 + 즉시 알림(요청/설정 오류), 자동 재시도 금지 |
| HTTP 5xx 또는 타임아웃 | 지수 백오프 재시도(예: 1s -> 2s -> 4s, 최대 3회) |
| `isSuccessful=false` | `resultCode` 분기 처리 + 원문 로그 보존 |

운영 관측 권장 항목:

- HTTP 상태 코드 분포
- `resultCode` 상위 N개
- 재시도 횟수/최종 실패율
- 타임아웃/5xx 급증 시점 알림

## 5) 이 프로젝트 적용 상태 (2026-02-21 기준)

- 구현 파일: `app/services/notifier.py`
- 성공 판정: HTTP 상태 코드 기반(`response.raise_for_status()`), 응답 바디 `header.isSuccessful`는 현재 미검증
- 재시도 대상: `requests.RequestException` 전반(타임아웃/연결오류/HTTP 오류 포함)
- 재시도 횟수/백오프: `NOTIFIER_MAX_RETRIES`, `NOTIFIER_RETRY_DELAY_SEC` 환경변수로 제어
- 회로 차단기: `NOTIFIER_CIRCUIT_*` 환경변수로 제어, 연속 실패 시 차단/복구

정합성 메모:

- 명세 권장과 현재 구현 사이에 차이(바디 성공 판정, 4xx 비재시도 정책)가 있으므로 개선 작업은 `docs/BACKLOG.md`에서 추적

주의: 두레이 정책/응답 스키마 변경 가능성이 있으므로 운영 적용 전 공식 도움말을 최우선 기준으로 재확인하세요.
