# KMA API Reference (Project Scope)

이 문서는 프로젝트에서 실제 사용하는 범위만 요약합니다.

## 1) Endpoint
- URL(기본): `http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd`
- Method: `GET`
- Response: `XML`

## 2) 요청 파라미터(사용분)
- 필수
  - `serviceKey`
  - `numOfRows`
  - `pageNo`
  - `dataType` (`XML`)
  - `fromTmFc`
  - `toTmFc`
  - `areaCode`
- 선택
  - `warningType`
  - `stnId`

## 3) 응답 필드(사용분)
- 공통
  - `resultCode`
  - `totalCount`
- item 필수 매핑
  - `warnVar`, `warnStress`, `command`, `cancel`
  - `stnId`, `tmFc`, `tmSeq`
- item 선택 매핑
  - `areaName`, `startTime`, `endTime`

## 4) 결과 코드 처리 기준
- `00`: 정상
- `03`: 데이터 없음(첫 페이지면 빈 결과 처리)
- 그 외: API 오류로 처리

## 5) 운영 제약
- 허용 호스트/경로는 설정으로 제한(`WEATHER_API_ALLOWED_HOSTS`, `WEATHER_API_ALLOWED_PATH_PREFIXES`)
- `SERVICE_API_KEY`는 원본 키를 그대로 전달
