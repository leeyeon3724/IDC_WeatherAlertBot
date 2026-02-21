# TESTING

이 문서는 테스트 실행 기준, 현재 적절성, 남은 리스크를 간결하게 관리합니다.

## 1) 실행 명령

```bash
make gate
python3 -m scripts.perf_report --output artifacts/perf/local.json --markdown-output artifacts/perf/local.md
python3 -m scripts.perf_baseline --reports artifacts/perf/local.json --max-samples 20 --output artifacts/perf/baseline.local.json --markdown-output artifacts/perf/baseline.local.md
python3 -m scripts.soak_report --cycles 3000 --area-count 3 --max-memory-growth-kib 8192 --json-output artifacts/soak/local.json --markdown-output artifacts/soak/local.md
python3 -m scripts.slo_report --log-file artifacts/canary/service.log --json-output artifacts/slo/local.json --markdown-output artifacts/slo/local.md
```

## 2) 현재 스냅샷

- 테스트 수: `164`
- 전체 커버리지: `91.54%`
- 최소 커버리지 기준: `80%`

## 3) 현재 기준

- 기본 게이트: `ruff`, `mypy`, `check_architecture_rules`, `check_event_docs_sync`, `check_repo_hygiene`, `pytest --cov`
- CI 추가 검증: Python 3.11/3.12 runtime smoke, PR checklist validation
- CI 상태 무결성 스모크: `migrate-state` + `verify-state --strict` 경로를 샘플 상태 파일로 자동 검증
- 외부 연동 canary: `.github/workflows/canary.yml`에서 실 API + webhook 경로를 주기/PR 단위로 검증하고 리포트 아티팩트(`artifacts/canary`)를 남김
- 장시간 안정성 soak: `.github/workflows/soak.yml`에서 합성 장기부하 리포트(`artifacts/soak/report.json`)를 생성하고 예산 초과 시 실패 처리
- 운영 SLO 리포트: `scripts/slo_report.py`로 성공률/실패율/지연/미전송 잔량을 계산하고 canary에서 자동 생성
- 폭주 완화 검증: `tests/test_notifier.py`, `tests/test_process_cycle.py`에서 circuit-breaker/backpressure 동작 회귀 검증
- 계약 안정성: 이벤트 이름 + 이벤트 payload 키 + 설정 + CLI snapshot 테스트 유지

## 4) 남은 리스크

- 이벤트 문서 정합성은 이벤트 이름/존재 중심 검증이며 필드 의미 변경은 리뷰 보완이 필요
- 성능 baseline은 추세 지표이며 절대 성능 SLA 판정 용도로는 사용하지 않음
- soak는 합성 워크로드 기반이므로 실트래픽/실의존성 시나리오는 canary/운영 지표와 함께 해석 필요

## 5) 우선순위

- 현재 활성 테스트 백로그 없음
- 신규 리스크는 `docs/BACKLOG.md`에 등록 후 진행
