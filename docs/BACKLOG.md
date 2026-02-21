# BACKLOG

이 문서는 코드베이스 평가와 리팩토링 우선순위를 단일 기준으로 관리합니다.
기준 브랜치: `main`
평가일: `2026-02-21`

## 1) Current Assessment

| 관점 | 점수(5점) | 평가 |
|---|---:|---|
| 정확성 | 4.6 | 핵심 알림/중복방지/헬스 흐름 안정 |
| 가독성/복잡성 | 4.4 | 엔트리포인트/설정 파서 분리로 변경 영향 축소 |
| 테스트 가능성 | 4.7 | 핵심 경로 회귀 탐지력 높음 |
| 안정성 | 4.5 | 실패 이벤트 표준화 + 저장소 실패 가드 보강 |
| 보안 | 4.4 | redaction 검증으로 로그 민감정보 노출 위험 감소 |
| 성능 | 4.9 | baseline 추세 차트 + `max_samples=20` 정책 정착 |
| 일관성 | 4.7 | 이벤트/운영 문서 정합성 자동검사 정착 |
| 기술부채 | 4.8 | 핵심 부채 정리 후 운영 고도화 단계 |
| 배포 신뢰성 | 4.8 | 런타임 매트릭스 + PR 체크 검증으로 누락 위험 감소 |
| 운영 비용 효율성 | 4.3 | `cycle.cost.metrics` 기반 호출/전송량 추적 가능 |
| 감사 가능성/추적성 | 4.4 | 스키마 버전 + 변경로그 동기화 검증 도입 |
| 변경 리드타임 | 4.2 | 자동화 기반 확보, 릴리스 판단 단순화 여지 잔존 |
| 아키텍처 규율 | 4.5 | 계층 의존성 규칙 자동검사로 역참조 차단 |
| 릴리스 게이트 단일화 | 4.5 | `make gate`로 로컬/CI 진입점 통일 |
| 계약 안정성 | 4.6 | 이벤트/설정/CLI 계약 스냅샷 회귀 방지 |
| 코드 수명주기 위생 | 4.5 | 저장소 위생 점검 자동 강제 |

## 2) Evidence Snapshot

- 품질 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_repo_hygiene`, `pytest --cov` 통과
- 테스트/커버리지: `145 passed`, 총 커버리지 `92.67%`
- 대표 커버리지: `service_loop 98%`, `commands 94%`, `weather_api 99%`, `settings 90%`

## 3) Active Backlog

| ID | Priority | 상태 | 근거 관점 | 작업 | 완료조건(DoD) |
|---|---|---|---|---|---|
| - | - | - | - | 현재 활성 과제 없음 | 신규 과제 수집 대기 |

## 4) Completed (Compact)

| 구간 | 완료 범위 | 핵심 성과 |
|---|---|---|
| Foundation Wave | RB-101~RB-208 | URL/저장소/CLI 기반 정리 |
| Reliability Wave | RB-301~RB-407 | 도메인/저장소/루프 회귀 보호 강화 |
| CI & Governance Wave | RB-501~RB-505 | CI 품질/문서 정합/PR 템플릿 기반 구축 |
| Release Gate Wave | RB-604 | `make gate` 단일 게이트 |
| Architecture Guard Wave | RB-701 | 계층 의존성 자동검사 |
| Contract Stability Wave | RB-702 | 이벤트/설정/CLI 계약 스냅샷 |
| Runtime Matrix Wave | RB-601 | Python 3.11/3.12 smoke |
| Schema Governance Wave | RB-602 | 이벤트 스키마 버전 거버넌스 |
| Cost Observability Wave | RB-603 | 비용 관점 사이클 지표 |
| Hygiene Guard Wave | RB-703 | 저장소 위생 자동검사 |
| Perf Trend Wave | RB-506~RB-507 | 성능 추세 시각화 + 보존 정책 |
| PR Governance Wave | RB-605 | PR 체크리스트 자동검증 |

## 5) Maintenance Rules

- 변경 단위별 품질 게이트(`ruff`, `mypy`, `scripts.check_architecture_rules`, `scripts.check_event_docs_sync`, `scripts.check_repo_hygiene`, `pytest`) 통과 후 병합
- PR에서는 `scripts.check_pr_checklist` 통과로 템플릿 체크 항목과 변경 영향 검증의 일치 여부를 확인
- 기능 변경은 작은 커밋 단위로 분리하고, 각 단위에서 백로그 상태를 함께 갱신
- 문서 경계는 `README/SETUP/OPERATION/TESTING/EVENTS/BACKLOG`로 고정
