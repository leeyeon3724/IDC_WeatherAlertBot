from __future__ import annotations

# Runtime lifecycle
STARTUP_INVALID_CONFIG = "startup.invalid_config"
STARTUP_READY = "startup.ready"
SHUTDOWN_INTERRUPT = "shutdown.interrupt"
SHUTDOWN_RUN_ONCE_COMPLETE = "shutdown.run_once_complete"
SHUTDOWN_UNEXPECTED_ERROR = "shutdown.unexpected_error"

# Cycle
CYCLE_START = "cycle.start"
CYCLE_COMPLETE = "cycle.complete"
CYCLE_PARALLEL_FETCH = "cycle.parallel_fetch"
CYCLE_AREA_INTERVAL_IGNORED = "cycle.area_interval_ignored"
CYCLE_INTERVAL_ADJUSTED = "cycle.interval.adjusted"

# Area processing
AREA_START = "area.start"
AREA_FAILED = "area.failed"
AREA_FETCH_SUMMARY = "area.fetch.summary"
AREA_FETCH_RETRY = "area.fetch.retry"

# Notifications
NOTIFICATION_SENT = "notification.sent"
NOTIFICATION_DRY_RUN = "notification.dry_run"
NOTIFICATION_RETRY = "notification.retry"
NOTIFICATION_FINAL_FAILURE = "notification.final_failure"
NOTIFICATION_URL_ATTACHMENT_BLOCKED = "notification.url_attachment_blocked"

# Health
HEALTH_EVALUATE = "health.evaluate"
HEALTH_NOTIFICATION_SENT = "health.notification.sent"
HEALTH_NOTIFICATION_FAILED = "health.notification.failed"
HEALTH_BACKFILL_START = "health.backfill.start"
HEALTH_BACKFILL_COMPLETE = "health.backfill.complete"
HEALTH_BACKFILL_FAILED = "health.backfill.failed"
HEALTH_STATE_INVALID_JSON = "health_state.invalid_json"
HEALTH_STATE_READ_FAILED = "health_state.read_failed"
HEALTH_STATE_BACKUP_FAILED = "health_state.backup_failed"

# State
STATE_CLEANUP_AUTO = "state.cleanup.auto"
STATE_CLEANUP_COMPLETE = "state.cleanup.complete"
STATE_CLEANUP_FAILED = "state.cleanup.failed"
STATE_MIGRATION_COMPLETE = "state.migration.complete"
STATE_MIGRATION_FAILED = "state.migration.failed"
