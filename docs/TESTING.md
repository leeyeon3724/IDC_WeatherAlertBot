# TESTING

이 문서는 테스트 실행 기준, 현재 적절성, 남은 리스크를 간결하게 관리합니다.

## 1) 실행 명령

```bash
make gate
python3 -m scripts.perf_report --output artifacts/perf/local.json --markdown-output artifacts/perf/local.md
python3 -m scripts.perf_baseline --reports artifacts/perf/local.json --max-samples 20 --output artifacts/perf/baseline.local.json --markdown-output artifacts/perf/baseline.local.md
```

## 2) 현재 스냅샷

- 테스트 수: `143`
- 전체 커버리지: `92.67%`
- 최소 커버리지 기준: `80%`

## 3) 적절성 평가

강점:

- 핵심 비즈니스 흐름(조회-중복방지-전송-헬스)은 회귀 테스트로 보호됨
- JSON/SQLite 저장소, 설정 파싱, 경계 입력(`weather_api`) 검증이 충분히 강화됨
- 문서 정합성(`events.py` ↔ 문서)과 성능 리포트 생성이 CI 단계에 포함됨

잔여 리스크:

- 문서 정합성 체크는 이벤트 "존재/매핑" 중심이라 필드 의미 변화까지는 완전 탐지하지 못함
- 성능 리포트는 참고 지표이며 장기 기준선 정책(보존/판정 규칙)은 추가 정리가 필요함

## 4) 최근 보완 (요약)

- 상태 저장소 실패 분기(`read/backup/persist`) 테스트 및 구조화 로그 통일
- `settings.from_env` 섹션 분해 + 정책별 테스트 강화
- `weather_api` 결과코드/페이지네이션/파싱 경계 테스트 확장
- redaction 통합 시나리오(`area.failed`, `notification.final_failure`) 테스트 추가
- CI: `make gate` 단일 품질 게이트 + perf report/compare/baseline + docs consistency check + PR 체크리스트 도입
- 아키텍처 의존성 경계 자동검사 도입 (`scripts/check_architecture_rules.py`, `tests/test_architecture_rules.py`)
- 이벤트/설정/CLI 계약 스냅샷 테스트 도입 (`tests/test_contract_snapshots.py`, `tests/contracts/*.json`)
- CI 런타임 smoke 매트릭스 도입 (Python 3.11/3.12, `tests/test_main.py`, `tests/test_main_smoke.py`, `tests/test_commands.py`, `main.py --help`)
- 이벤트 스키마 버전/Change Log 동기화 검증 도입 (`EVENT_SCHEMA_VERSION`, `scripts/check_event_docs_sync.py`, `tests/test_event_docs_sync.py`)
- 비용 관점 사이클 지표 이벤트 도입 (`cycle.cost.metrics`, `api_fetch_calls`, `notification_attempts`, `notification_failures`)
- 저장소 위생 점검 도입 (`scripts/check_repo_hygiene.py`, `tests/test_repo_hygiene.py`, `make check-hygiene`)
- 성능 baseline 추세 시각화/샘플 정책 표준화 (`trend` 컬럼, `--max-samples 20`, `tests/test_perf_baseline.py`)

## 5) 다음 우선순위

1. PR 체크 항목-실제 검증 연계 강화 (`RB-605`)
