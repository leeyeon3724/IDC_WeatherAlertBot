# Codebase Assessment

기준 시점: 현재 `main` 브랜치

## 1) 평가 요약

| 관점 | 점수(5점) | 판단 |
|---|---:|---|
| 정확성 | 4.2 | 페이지네이션/중복 방지/복구 로직이 안정적이며 핵심 플로우 테스트가 충분함 |
| 가독성 | 3.6 | 핵심 파일(`cli.py`, `settings.py`)이 길고 역할이 넓어 이해 비용이 큼 |
| 복잡성 | 3.4 | 분해는 되었지만 진입점/설정 파싱의 분기 수가 많아 복잡도 높음 |
| 응집도/결합도 | 3.7 | 저장소 추상화는 좋으나 헬스 모니터는 구체 구현 결합이 남아 있음 |
| 테스트 가능성 | 4.1 | 단위 테스트 폭이 넓고 품질 게이트 안정적, 진입점 테스트는 monkeypatch 의존 높음 |
| 확장성 | 4.0 | JSON/SQLite 이중 저장소와 observability 도입으로 확장 기반 확보 |
| 성능 | 3.5 | 기본 규모에서는 충분, JSON 저장소/SQLite 연결 전략은 고부하에서 비효율 가능 |
| 안정성 | 4.2 | 재시도/백오프/상태 복구/헬스 감지가 구현되어 운영 내성이 높음 |
| 보안 | 3.2 | 기본 API URL이 `http`이고 URL 검증/보안 정책이 최소 수준 |
| 일관성 | 3.7 | 이벤트 상수화는 진행됨, 일부 서비스 로그는 비구조 로그 유지 |
| 기술부채 | 3.5 | 빠른 진화 흔적이 있고 구조 개선 필요 항목이 명확함 |

## 2) 근거(주요 코드 포인트)

- 진입점 복잡도/길이: `app/entrypoints/cli.py:1`
- 설정 파싱 + 도메인 상수 혼재: `app/settings.py:9`, `app/settings.py:167`
- 페이지네이션/수집 요약 로그: `app/services/weather_api.py:64`, `app/services/weather_api.py:120`
- JSON 저장소 복구/마이그레이션: `app/repositories/json_state_repo.py:24`, `app/repositories/json_state_repo.py:71`
- SQLite 저장소 도입: `app/repositories/sqlite_state_repo.py:13`
- 유스케이스 분해 상태: `app/usecases/process_cycle.py:44`
- 헬스 모니터 결합 지점: `app/usecases/health_monitor.py:11`, `app/usecases/health_monitor.py:17`
- 재시도 정책(날것 로그 포함): `app/services/weather_api.py:187`, `app/services/notifier.py:77`
- 품질 게이트 기준/결과: `docs/TESTING.md:1`

## 3) 핵심 개선사항 도출

### A. 보안

- 기본 API URL을 `https`로 상향하고 문서/예시 동기화
- Webhook/API URL 검증(스킴, host 패턴) 옵션 추가
- 운영 로그에 URL/키 등 민감정보 노출 방지 정책 명시

### B. 가독성/복잡성

- `cli.py`를 `runtime_builder`, `service_loop`, `commands` 모듈로 분리
- `settings.py`에서 도메인 매핑 상수 분리(`app/domain/code_maps.py`)
- settings 파서 유틸 분리로 책임 축소

### C. 응집도/결합도

- `HealthStateRepository` 프로토콜 도입 후 `ApiHealthMonitor`의 구체 저장소 의존 제거
- 저장소 팩토리/선택 로직을 별도 모듈로 이동

### D. 테스트 가능성

- `tests/test_main.py`의 monkeypatch 중심 테스트를 helper 단위 테스트로 분해
- 진입점 통합 테스트 1~2개 추가(실제 sqlite/json 저장소 경로로 smoke)

### E. 성능/안정성

- SQLite 커넥션 전략 개선(`busy_timeout`, WAL, 배치 upsert/mark 최적화)
- JSON 저장소에서 `pending_count` 계산 비용 축소(캐시 또는 인덱스형 구조)

### F. 일관성/기술부채

- notifier/weather_api 재시도 로그를 `log_event()` 기반 구조 로그로 통일
- 운영 이벤트 사전 문서(이벤트명/필수 필드) 유지

## 4) 권장 실행 순서

1. 보안 하드닝(https 기본값 + URL 검증)
2. 헬스 저장소 추상화(결합 제거)
3. 진입점/설정 모듈 분리(복잡도 절감)
4. SQLite 성능/락 내성 강화
5. 테스트 구조 리팩토링(monkeypatch 축소)
