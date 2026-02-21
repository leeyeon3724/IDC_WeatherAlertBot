# TESTING

이 문서는 테스트 실행 기준, 현재 적절성, 남은 리스크를 간결하게 관리합니다.

## 1) 실행 명령

```bash
make gate
python3 -m scripts.perf_report --output artifacts/perf/local.json --markdown-output artifacts/perf/local.md
python3 -m scripts.perf_baseline --reports artifacts/perf/local.json --output artifacts/perf/baseline.local.json --markdown-output artifacts/perf/baseline.local.md
```

## 2) 현재 스냅샷

- 테스트 수: `131`
- 전체 커버리지: `92.64%`
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

## 5) 다음 우선순위

1. 아키텍처 의존성 규칙 자동검사 도입 (`RB-701`)
2. 계약 안정성 테스트 계층 도입 (`RB-702`)
3. perf 추세 시각화 포맷 정의 및 운영 반영 (`RB-506`)
