# BACKLOG

이 문서는 **앞으로 진행할 리팩토링 작업만** 관리합니다.
완료 이력은 커밋 로그로 추적하며 본 문서에는 남기지 않습니다.
기준 브랜치: `main`
마지막 갱신: `2026-02-21`
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
항목: alert_rules 스키마 버전 확장성 개선
근거: alert_rules.py에서 v1/v2 각각 별도 함수(_parse_code_maps_v1/v2)로 분기 → 버전 추가 시 확장 곤란
완료 기준: strategy 또는 registry 패턴으로 전환, v3 추가 시 함수 1개만 등록하면 되는 구조
```

### 낮음

```text
상태: 진행중
중요도: 낮음
항목: env 파서 반복 코드 정리
근거: settings.py의 _parse_*_env() 함수 패턴이 유사(int, float, bool, str, choice, JSON)
완료 기준: 제네릭 파서 또는 팩토리로 통합, 기존 테스트 통과
```

```text
상태: 진행중
중요도: 낮음
항목: state_verifier JSON/SQLite 중복 추출
근거: repositories/state_verifier.py에서 JSON·SQLite 검증 로직 200줄+ 유사 패턴 반복
완료 기준: 공통 검증 로직 추출, 구현별 차이만 분리
```

```text
상태: 진행중
중요도: 낮음
항목: SQLite 연결 재사용
근거: sqlite_state_repo.py가 연산마다 연결 생성·해제 → 단일 프로세스에서 비효율
완료 기준: 연결 재사용 또는 풀링 도입, cleanup 시 명시적 close
```

```text
상태: 진행중
중요도: 낮음
항목: 넓은 except Exception 절 세분화
근거: service_loop.py 등에서 except Exception 사용 → 예상치 못한 에러 흡수 위험
완료 기준: 처리 대상 예외를 명시적으로 나열, 미예상 예외는 상위로 전파
```

## 3) 운영 규칙

- 상태 값은 `진행중`, `완료`만 사용
- 완료된 항목은 본 문서에서 제거하고 커밋 로그로 추적
- 항목은 작은 단위 커밋으로 진행하고 완료 즉시 상태 반영
