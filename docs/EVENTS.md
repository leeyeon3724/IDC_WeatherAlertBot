# EVENTS

이 문서는 `log_event()`로 출력되는 이벤트 이름과 핵심 필드를 정의합니다.

## 공통 규칙

- 모든 구조화 로그는 JSON 문자열이며 최소 `event` 필드를 포함합니다.
- 필드명은 `snake_case`를 사용합니다.
- 동일한 의미의 필드는 이벤트 간 동일 키를 유지합니다.

## Event Schema

- schema_version: `1`
- 이벤트 계약(이름/핵심 필드) 변경 시 이 문서의 Change Log를 함께 갱신합니다.

## Schema Change Log

| version | date | change | compatibility |
|---|---|---|---|
| 1 | 2026-02-21 | 이벤트 스키마 버전 기준 수립 및 동기화 검증 도입 | Initial |

## Runtime Lifecycle

- `startup.invalid_config`: `error`
- `startup.ready`: `state_file`, `state_repository_type`, `sqlite_state_file`, `health_state_file`, `area_count`
- `shutdown.interrupt`: 없음
- `shutdown.run_once_complete`: 없음
- `shutdown.unexpected_error`: `error`

## Cycle

- `cycle.start`: `start_date`, `end_date`, `area_count`
- `cycle.complete`: `start_date`, `end_date`, `area_count`, `area_failures`, `sent_count`
- `cycle.parallel_fetch`: `workers`, `area_count`
- `cycle.area_interval_ignored`: `area_interval_sec`
- `cycle.interval.adjusted`: `base_interval_sec`, `adjusted_interval_sec`, `incident_open`

## Area Processing

- `area.start`: `area_code`, `area_name`
- `area.failed`: `area_code`, `area_name`, `error_code`, `error`
- `area.fetch.summary`: `area_code`, `area_name`, `fetched_items`, `page_count`, `total_count`
- `area.fetch.retry`: `area_code`, `attempt`, `max_retries`, `error_code`, `error`, `backoff_sec`

## Notifications

- `notification.sent`: `event_id`, `area_code`
- `notification.dry_run`: `event_id`, `area_code`
- `notification.retry`: `attempt`, `max_retries`, `error`, `backoff_sec`
- `notification.final_failure`: `event_id`, `area_code`, `attempts`, `error`
- `notification.url_attachment_blocked`: `event_id`, `area_code`, `reason`

## Health

- `health.evaluate`: `incident_open`, `health_event`, `should_notify`
- `health.notification.sent`: `health_event`
- `health.notification.failed`: `health_event`, `attempts`, `error`
- `health.backfill.start`: `lookback_days`, `incident_duration_sec`
- `health.backfill.complete`: `lookback_days`, `sent_count`, `pending_total`
- `health.backfill.failed`: `lookback_days`, `error`
- `health_state.invalid_json`: `file`, `backup`, `error`
- `health_state.read_failed`: `file`, `error`
- `health_state.backup_failed`: `file`, `error`
- `health_state.persist_failed`: `file`, `temp_file`, `error`

## State

- `state.invalid_json`: `file`, `backup`, `error`
- `state.read_failed`: `file`, `error`
- `state.backup_failed`: `file`, `error`
- `state.persist_failed`: `file`, `temp_file`, `error`
- `state.cleanup.auto`: `date`, `days`, `include_unsent`, `removed`, `total`, `pending`
- `state.cleanup.complete`: `state_file`, `days`, `include_unsent`, `dry_run`, `removed`, `total`, `pending`
- `state.cleanup.failed`: `state_file`, `days`, `include_unsent`, `dry_run`, `error`
- `state.migration.complete`: `json_state_file`, `sqlite_state_file`, `total_records`, `inserted_records`, `sent_records`, `marked_sent_records`
- `state.migration.failed`: `json_state_file`, `sqlite_state_file`, `error`
