from __future__ import annotations

import time
from dataclasses import asdict

from app.logging_utils import log_event, setup_logging
from app.repositories.state_repo import JsonStateRepository
from app.services.notifier import DoorayNotifier
from app.services.weather_api import WeatherAlertClient
from app.settings import Settings, SettingsError
from app.usecases.process_cycle import ProcessCycleUseCase


def main() -> int:
    bootstrap_logger = setup_logging()
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        bootstrap_logger.critical(log_event("startup.invalid_config", error=str(exc)))
        return 1

    logger = setup_logging(settings.log_level, settings.timezone)
    state_repo = JsonStateRepository(
        file_path=settings.sent_messages_file,
        logger=logger.getChild("state"),
    )
    weather_client = WeatherAlertClient(
        settings=settings,
        logger=logger.getChild("weather_api"),
    )
    notifier = DoorayNotifier(
        hook_url=settings.service_hook_url,
        bot_name=settings.bot_name,
        timeout_sec=settings.request_timeout_sec,
        logger=logger.getChild("notifier"),
    )
    processor = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=state_repo,
        logger=logger.getChild("processor"),
    )

    logger.info(
        log_event(
            "startup.ready",
            state_file=str(settings.sent_messages_file),
            area_count=len(settings.area_codes),
            dry_run=settings.dry_run,
            run_once=settings.run_once,
        )
    )

    try:
        while True:
            stats = processor.run_once()
            logger.info(log_event("cycle.complete", **asdict(stats)))
            if settings.run_once:
                logger.info(log_event("shutdown.run_once_complete"))
                return 0
            if settings.cycle_interval_sec > 0:
                time.sleep(settings.cycle_interval_sec)
    except KeyboardInterrupt:
        logger.info(log_event("shutdown.interrupt"))
        return 0
    except Exception as exc:  # pragma: no cover
        logger.critical(
            log_event("shutdown.unexpected_error", error=str(exc)),
            exc_info=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
