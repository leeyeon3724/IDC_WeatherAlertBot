# 기상청 기상특보 OpenAPI 참조 (프로젝트 적용본)

**문서 목적**: 프로젝트 구현(`app/services/weather_api.py`)과 직접 연관된 명세만 유지하고, 원문 전체 사양의 중복 서술은 제거합니다.  
**정리일**: 2026-02-21  
**원문 소스**:
- https://www.data.go.kr/data/15000415/openapi.do
- `기상청21_기상특보 조회서비스_오픈API활용가이드` 및 부속 엑셀(특보구역코드)

## 1) 서비스 요약

- 서비스: `WthrWrnInfoService`
- 베이스 URL: `http://apis.data.go.kr/1360000/WthrWrnInfoService`
- 프로젝트 사용 엔드포인트: `getPwnCd` (특보코드조회)
- 응답 포맷: XML (기본), 필요 시 JSON
- 성능 기준(원문): 최대 TPS 30

원문에는 10개 엔드포인트가 정의되어 있으나, 현재 프로젝트는 `getPwnCd`만 사용합니다.

## 2) 프로젝트 사용 범위

현재 코드가 실제로 요청/파싱하는 항목:

- 요청: `serviceKey`, `numOfRows`, `pageNo`, `dataType`, `fromTmFc`, `toTmFc`, `areaCode`
- 선택 요청: `warningType`, `stnId`
- 응답 공통: `resultCode`, `totalCount`
- 응답 아이템: `areaName`, `warnVar`, `warnStress`, `command`, `cancel`, `startTime`, `endTime`, `stnId`, `tmFc`, `tmSeq`

코드 기준 파일:
- `app/services/weather_api.py`
- `app/domain/code_maps.py`

## 3) getPwnCd 요청 명세 (프로젝트 기준)

| 파라미터 | 필수 | 설명 |
|---|---|---|
| `serviceKey` | Y | 인증키 |
| `numOfRows` | Y | 페이지 크기 (프로젝트 기본: 100) |
| `pageNo` | Y | 페이지 번호 |
| `dataType` | N | 응답 형식 (프로젝트 기본: XML) |
| `fromTmFc` | Y | 조회 시작일 (`yyyyMMdd`) |
| `toTmFc` | Y | 조회 종료일 (`yyyyMMdd`) |
| `areaCode` | Y | 특보구역코드 |
| `warningType` | N | 특보 유형 필터 |
| `stnId` | N | 지점코드 필터 |

중요 계약:
- 원문은 `serviceKey(URL Encode)`로 표기되어 있지만, 본 프로젝트는 `requests`가 쿼리 인코딩을 수행하므로 `.env`에는 **raw/decoded 키**를 입력합니다.
- 설정 방어 로직은 pre-encoded 키를 거부합니다.
  - 관련: `app/settings.py`, `.env.example`, `docs/SETUP.md`

## 4) resultCode 처리 정책

| resultCode | 의미 | 프로젝트 동작 |
|---|---|---|
| `00` 또는 `0` | 정상 | 성공 처리 |
| `03` | NODATA | 1페이지면 빈 결과, 이후 페이지면 페이징 종료 |
| `22` | 요청제한 초과 | 지수 백오프 재시도 후 소진 시 실패 |
| 그 외 | API 오류 | `api_result_error`로 실패 처리 |

관측 포인트:
- `area.fetch.retry` (`error_code=api_result_error`)
- `area.failed` (`error_code=api_result_error`)
- 운영 문서: `docs/OPERATION.md`

## 5) 코드값 매핑 정책

프로젝트 매핑:
- `warnVar`, `warnStress`, `command`, `cancel` 매핑은 `app/domain/code_maps.py` 사용
- 미매핑 코드 fallback은 가공 문자열이 아닌 **원문 코드(raw code)** 보존
- 미매핑 감지는 `area.code_unmapped` 이벤트로 기록

## 6) 지역코드 매핑 정책

- `AREA_CODES`와 `AREA_CODE_MAPPING`은 `.env.example` 기준으로 동기화 관리
- 누락/불일치 자동 점검:
  - `python3 -m scripts.check_area_mapping_sync`
- 런타임 누락 경고 이벤트:
  - `area.mapping_coverage_warning`

## 7) 호출률/재시도 정책

- API 소프트 호출률 제한: `API_SOFT_RATE_LIMIT_PER_SEC` (기본 30, `0` 비활성)
- 네트워크/HTTP/XML 파싱 오류: `MAX_RETRIES`, `RETRY_DELAY_SEC`로 재시도
- 병렬 조회(`AREA_MAX_WORKERS>1`)에서도 API soft rate limit은 전역 적용

## 8) 문서/테스트 동기화 체크

변경 시 필수 확인:
- `tests/test_weather_api.py`
- `docs/OPERATION.md`
- `docs/EVENTS.md`
- `python3 -m scripts.check_event_docs_sync`
- `python3 -m scripts.check_area_mapping_sync`

## 9) 비고

원문 전체 엔드포인트(예: `getWthrWrnList`, `getWthrWrnMsg`, `getWthrInfo*`, `getWthrBrkNews*`, `getWthrPwn*`, `getPwnStatus`)는 현재 코드 미사용 범위이므로 본 문서에서 상세 표를 제거했습니다.
필요 시 원문 가이드를 기준으로 별도 확장 문서를 추가합니다.
