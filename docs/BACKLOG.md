# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하며 본 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-22`
리뷰 기준: `app/` 코드 리뷰 (2026-02-21)

## 1) 현재 기준선 (참고)

품질 게이트·테스트·운영 기준은 아래 문서를 참고하세요:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (코드 리뷰 기반)

### 중간

```text
상태: 진행중
중요도: 중간
항목: service_loop 미예상 예외 관측 계약 테스트 강화
근거: 예외 전파 정책 변경 시 shutdown.unexpected_error 이벤트 누락이 재발 가능
완료 기준: 미예상 예외(TypeError 등) 발생 시 이벤트 로깅 + 예외 재전파를 테스트로 고정
```

```text
상태: 진행중
중요도: 중간
항목: weather_api 필수 XML 태그 누락 테스트 매트릭스화
근거: 단일 태그 누락 중심 테스트로는 경계조건 회귀 탐지 한계
완료 기준: warnVar/warnStress/command/cancel/stnId/tmFc/tmSeq/resultCode 누락 케이스 파라미터화
```

### 낮음

```text
상태: 진행중
중요도: 낮음
항목: settings 테스트 필수 환경값 셋업 중복 제거
근거: test_settings.py 전반에 동일 monkeypatch 코드 반복으로 유지보수 비용 증가
완료 기준: 공통 helper/fixture 도입, 기존 테스트 동작/가독성 유지
```

## 3) 운영 규칙

- 상태 값은 `진행중`, `완료`만 사용
- 완료된 항목은 본 문서에서 제거하고 커밋 로그로 추적
- 항목은 작은 단위 커밋으로 진행하고 완료 즉시 상태 반영
