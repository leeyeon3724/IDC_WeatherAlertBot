# TESTING 가이드

## 1) 목적
- 회귀를 빠르게 감지하고, 운영 계약(문서/설정/규칙)과 코드의 일관성을 유지합니다.

## 2) 현재 스냅샷

- 테스트 수: `-`
- 전체 커버리지: `-`
- 최소 커버리지 기준: `80%`

## 3) 현재 기준
- PR 최소 기준: `make test`
- 머지 전 권장: `make test-cov`, `make lint`, `make typecheck`
- 운영 계약 점검: `make check-docs`, `make check-alarm-rules`
- 통합 점검: `make gate`

## 4) 명령 요약
```bash
make test
make test-cov
make testing-snapshot
```

## 5) 원칙
- 테스트는 기능 단위 책임을 명확히 검증해야 합니다.
- 외부 연동은 mock/fake로 격리하고, 재현 가능한 실패를 우선합니다.
- 테스트 문서 스냅샷은 `make testing-snapshot`으로 갱신합니다.
