# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하며 본 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21`

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `pytest --cov`
- 테스트/커버리지 최신 수치: `docs/TESTING.md`의 `## 2) 현재 스냅샷`을 단일 기준으로 사용
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (문서 근거 기반)

상태: 진행중
중요도: 높음
항목: `resultCode=22`(요청제한 초과) 전용 재시도 경로 추가
근거: KMA 명세 적용 포인트에 `타임아웃/요청제한(코드 22) 재시도`가 명시되어 있으나, 현재 구현은 API resultCode 오류를 즉시 실패 처리함
완료 기준: `resultCode=22`에 대한 지수 백오프 재시도 구현, `tests/test_weather_api.py`에 성공/소진 케이스 추가, `docs/OPERATION.md`에 관측 포인트(`error_code=api_result_error`, `result_code=22`) 반영

상태: 진행중
중요도: 높음
항목: `SERVICE_API_KEY` 인코딩 계약(원문/URL-encoded) 명시 및 방어 로직 정리
근거: 스펙은 `serviceKey(URL Encode)`를 기술하지만, 런타임은 `requests` 쿼리 인코딩을 사용하므로 사전 인코딩 키 입력 시 이중 인코딩 위험이 있음
완료 기준: 정책 단일화(원문 키 권장 또는 encoded 허용 중 택1), 설정 검증/경고 로직 추가, `.env.example`·`docs/SETUP.md`·`README.md`에 동일 문구 반영, 회귀 테스트 추가

상태: 진행중
중요도: 중간
항목: 미매핑 코드 fallback의 원문 코드 보존 방식 정렬
근거: 문서 적용 포인트는 "미존재 매핑 코드 원문 보존"을 요구하나, 현재 저장 문자열은 `UNKNOWN(field:code)` 형태로 변형됨
완료 기준: 도메인 저장값에 원문 코드 보존(또는 원문 필드 병행 저장)으로 정책 확정, 알림 메시지 표현/로그 표현 분리, 관련 단위 테스트 및 이벤트 문서 갱신

상태: 진행중
중요도: 중간
항목: `AREA_CODE_MAPPING` 동기화 검증 자동화
근거: KMA 부속 엑셀 변경이력과 동기화가 요구되지만 현재는 누락/빈 매핑도 허용되어 운영 시 지역명 품질 저하 가능
완료 기준: 매핑 완전성 검사 스크립트(최소 `AREA_CODES` 포함 여부) 추가, CI 게이트 포함 여부 결정, 운영 모드에서 누락률 경고 이벤트 추가

상태: 진행중
중요도: 중간
항목: 병렬 조회 시 API 호출률 보호(소프트 레이트 리밋) 도입
근거: 엔드포인트 문서 성능 한계(TPS 30) 대비 현재 병렬 모드에서 지역 간 interval이 비활성화되어 순간 트래픽 스파이크 위험 존재
완료 기준: 글로벌 호출 슬롯/토큰 버킷 등 제한 기법 도입, `AREA_MAX_WORKERS`와의 상호작용 규칙 문서화, 부하/회귀 테스트 추가

신규 리스크 등록 템플릿:

```text
상태: 진행중
중요도: 높음|중간|낮음
항목: 한 줄 제목
근거: 실패 경로/회귀 위험/재현 조건
완료 기준: 테스트·문서·검증 명확 기준
```

## 3) 운영 규칙

- 상태 값은 `진행중`, `완료`만 사용
- 완료된 항목은 본 문서에서 제거하고 커밋 로그로 추적
- 항목은 작은 단위 커밋으로 진행하고 완료 즉시 상태 반영
