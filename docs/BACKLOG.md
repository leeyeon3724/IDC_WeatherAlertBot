# BACKLOG

이 문서는 코드베이스 평가와 리팩토링 우선순위를 단일 기준으로 관리합니다.
기준 브랜치: `main`
평가일: `2026-02-21`

## 1) Current Assessment

| 관점 | 점수(5점) | 평가 |
|---|---:|---|
| 정확성 | 4.6 | 핵심 알림/중복 방지/헬스 흐름이 안정적이고 Weather API 경계 테스트가 강화됨 |
| 가독성/복잡성 | 4.4 | 엔트리포인트 분리와 설정 파서 분해로 변경 영향 범위가 감소함 |
| 테스트 가능성 | 4.7 | 핵심 경로(`service_loop`, `commands`, `weather_api`, 상태 저장소) 회귀 탐지력이 높음 |
| 안정성 | 4.5 | 실패 이벤트 표준화와 상태 저장소 실패 분기 가드로 운영 복원력이 향상됨 |
| 보안 | 4.4 | redaction 단위+통합 시나리오 검증으로 민감정보 로그 노출 리스크를 낮춤 |
| 성능 | 4.9 | baseline `trend` 차트와 `max_samples=20` 보존 정책으로 추세 해석·노이즈 제어 기준을 표준화 |
| 일관성 | 4.7 | `events.py`-`EVENTS.md`-`OPERATION.md` 정합성 점검 자동화로 문서 누락 리스크 감소 |
| 기술부채 | 4.8 | 기존 핵심 부채(RB-101~RB-505)가 대부분 해소되고 운영 고도화 단계로 진입 |
| 배포 신뢰성 (신규) | 4.5 | Python 3.11/3.12 런타임 smoke/startup 매트릭스로 배포 전 환경 차이 리스크를 조기 탐지 가능 |
| 운영 비용 효율성 (신규) | 4.3 | `cycle.cost.metrics` 도입으로 사이클당 호출/전송 비용 지표를 이벤트 기반으로 추적 가능 |
| 감사 가능성/추적성 (신규) | 4.4 | `EVENT_SCHEMA_VERSION` + 문서 Change Log 동기화 검증으로 변경 이력 추적성이 개선됨 |
| 변경 리드타임 (신규) | 4.2 | 자동 점검은 늘었지만 “한 번에 검증/릴리스 판단” 흐름은 더 단순화 여지 존재 |
| 아키텍처 규율 (추가) | 4.5 | 계층 의존성 규칙 자동검사로 구조 역참조를 CI에서 즉시 차단 가능 |
| 릴리스 게이트 단일화 (추가) | 4.5 | `make gate` 도입으로 로컬/CI 품질 검증 진입점이 단순화됨 |
| 계약 안정성 (추가) | 4.6 | 이벤트/설정/CLI 계약 스냅샷 테스트로 호환성 파손을 조기 탐지 가능 |
| 코드 수명주기 위생 (추가) | 4.5 | 저장소 위생 점검(`check_repo_hygiene`) 도입으로 문서 경계/환경변수 정합성을 자동 강제 가능 |

## 2) Evidence Snapshot

- 품질 게이트: `ruff`, `mypy`, `scripts.check_event_docs_sync`, `pytest --cov` 통과
- 테스트/커버리지: `143 passed`, 총 커버리지 `92.67%`
- 대표 커버리지: `service_loop 98%`, `commands 94%`, `weather_api 99%`, `settings 90%`

## 3) Active Backlog

| ID | Priority | 상태 | 근거 관점 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|
| RB-605 | P3 | 예정 | 배포 신뢰성/감사 가능성 | PR 템플릿 체크 항목을 CI에서 부분 강제(예: 이벤트 변경 시 문서 동기화 확인) | 템플릿 누락과 실제 검증 결과 간 괴리 감소 |

## 4) Completed (Compact)

| 구간 | 완료 범위 | 핵심 성과 |
|---|---|---|
| Foundation Wave | RB-101~RB-208 | URL 정책 분리, 저장소 안정화, CLI 실패 경로 표준화, 운영 문서 기반 확립 |
| Reliability Wave | RB-301~RB-407 | 도메인/저장소/루프 테스트 강화, 구조화 이벤트/운영 매핑 정착 |
| CI & Governance Wave | RB-501~RB-505 | 정책 시나리오 테스트, perf 리포트/기준선, 문서 정합성 검사, PR 체크리스트 도입 |
| Release Gate Wave | RB-604 | `make gate` 단일 검증 진입점 도입 및 CI 게이트 정렬 |
| Architecture Guard Wave | RB-701 | 계층 의존성 규칙 자동검사 및 회귀 테스트 도입 |
| Contract Stability Wave | RB-702 | 이벤트/설정/CLI 계약 스냅샷 테스트 도입 |
| Runtime Matrix Wave | RB-601 | Python 3.11/3.12 smoke + startup 체크 및 버전별 아티팩트 도입 |
| Schema Governance Wave | RB-602 | 이벤트 스키마 버전/변경로그 정책 및 동기화 검증 강화 |
| Cost Observability Wave | RB-603 | 사이클별 API/전송량 비용 지표 이벤트 및 운영 기준 수립 |
| Hygiene Guard Wave | RB-703 | 저장소 위생 점검 자동화 및 gate 통합으로 문서/설정 중복·잔재 리스크 축소 |
| Perf Trend Wave | RB-506~RB-507 | baseline trend 시각화 + 최근 20개 샘플 보존 정책 표준화 |

## 5) Maintenance Rules

- 변경 단위별 품질 게이트(`ruff`, `mypy`, `scripts.check_architecture_rules`, `scripts.check_event_docs_sync`, `scripts.check_repo_hygiene`, `pytest`) 통과 후 병합
- 기능 변경은 작은 커밋 단위로 분리하고, 각 단위에서 백로그 상태를 함께 갱신
- 문서 경계는 `README/SETUP/OPERATION/TESTING/EVENTS/BACKLOG`로 고정
