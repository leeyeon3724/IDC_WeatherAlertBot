# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하며 본 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21`

## 1) 현재 기준선 (참고)

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_alarm_rules_sync`, `check_repo_hygiene`, `check_env_defaults_sync`, `pytest --cov`
- 테스트: `265 passed`
- 커버리지: `94.97%` (최저 기준 `80%`)
- 핵심 검증 경로: `ci.yml`, `pr-fast.yml`, `nightly-full.yml`, `canary.yml`, `soak.yml`, `live-e2e.yml`
- 로컬 실자격증명 검증: `scripts/run_live_e2e_local.sh` + `.env.live-e2e`(비추적)

참조 문서:
- 실행/운영: `docs/OPERATION.md`
- 테스트 전략: `docs/TESTING.md`
- 이벤트 사전: `docs/EVENTS.md`

## 2) Active Refactoring Backlog (문서 근거 기반)

### 2-1) API 요청 파라미터 모델링/확장성 개선

```text
상태: 진행중
중요도: 중간
항목: 특보 API 요청 파라미터 빌더 분리 및 필터 확장 포인트 확보
근거: 요청 파라미터(serviceKey, from/to, areaCode)가 서비스 코드에 인라인되어 있고
      warningType/stnId/dataType 같은 API 옵션을 기능 확장 시 안전하게 추가하기 어렵다.
      (app/services/weather_api.py)
완료 기준:
- API 요청 파라미터를 전용 빌더/모델로 분리
- warningType/stnId 같은 선택 필터를 설정 기반으로 확장 가능한 구조로 정리
- 파라미터 스냅샷/회귀 테스트를 추가해 스키마 드리프트를 조기 탐지
```

### 2-2) 신규 지역 추가 경로 단순화(지역명 매핑 의존 완화)

```text
상태: 진행중
중요도: 중간
항목: AREA_CODE_MAPPING 누락 시 graceful fallback 및 정합성 검증 보강
근거: 신규 지역 코드 추가 시 AREA_CODE_MAPPING 누락만으로 기동 실패가 발생해
      운영 확장 속도를 저하시킨다. 응답 areaName 활용/불일치 검증 전략이 필요하다.
      (app/settings.py, app/services/weather_api.py, app/usecases/process_cycle.py)
완료 기준:
- 지역명 해석 우선순위(설정 매핑 > 응답 areaName > areaCode) 정책 정의
- 매핑 누락/불일치 시 경고 이벤트를 남기고 서비스는 지속 가능하도록 개선
- 신규 지역 추가/매핑 누락 시나리오 테스트 추가
```

### 2-3) 테스트-실운영 설정 정합성 보강

```text
상태: 진행중
중요도: 낮음
항목: 설정 제약(특히 API URL scheme/host/path)과 테스트 픽스처 정합성 강화
근거: 일부 테스트가 Settings.from_env 제약과 다른 직접 Settings 생성값을 사용하여
      환경 제약 회귀를 놓칠 수 있음.
      (app/settings.py, tests/test_weather_api.py)
완료 기준:
- 핵심 서비스 테스트에 from_env 검증 규칙과 동일한 제약을 반영
- 설정 제약 변경 시 테스트가 즉시 실패하도록 계약성 테스트 보강
```

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
