from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

from app.entrypoints.runtime_builder import ServiceRuntime, log_startup
from app.observability import events
from app.repositories.state_repository import StateRepository
from app.services.notifier import DoorayNotifier
from app.usecases.health_monitor import ApiHealthMonitor
from app.usecases.process_cycle import ProcessCycleUseCase
from tests.main_test_harness import make_settings


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _build_runtime(
    tmp_path: Path,
    **setting_overrides: object,
) -> tuple[ServiceRuntime, _CaptureHandler]:
    settings = make_settings(tmp_path, **setting_overrides)
    logger = logging.getLogger("test.runtime_builder.startup")
    logger.handlers = []
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _CaptureHandler()
    logger.addHandler(handler)
    runtime = ServiceRuntime(
        settings=settings,
        logger=logger,
        state_repo=cast(StateRepository, object()),
        notifier=cast(DoorayNotifier, object()),
        processor=cast(ProcessCycleUseCase, object()),
        health_monitor=cast(ApiHealthMonitor, object()),
    )
    return runtime, handler


def test_log_startup_logs_ready_event(tmp_path: Path) -> None:
    runtime, handler = _build_runtime(
        tmp_path,
        area_codes=["L1012000"],
        area_code_mapping={"L1012000": "판교"},
    )

    log_startup(runtime)

    payloads = [json.loads(message) for message in handler.messages]
    assert any(payload.get("event") == events.STARTUP_READY for payload in payloads)
    assert not any(
        payload.get("event") == events.AREA_MAPPING_COVERAGE_WARNING for payload in payloads
    )


def test_log_startup_logs_area_mapping_coverage_warning_when_mapping_missing(
    tmp_path: Path,
) -> None:
    runtime, handler = _build_runtime(
        tmp_path,
        area_codes=["L1012000", "L1012100"],
        area_code_mapping={"L1012000": "판교"},
    )

    log_startup(runtime)

    payloads = [json.loads(message) for message in handler.messages]
    warning_payloads = [
        payload
        for payload in payloads
        if payload.get("event") == events.AREA_MAPPING_COVERAGE_WARNING
    ]
    assert len(warning_payloads) == 1
    warning_payload = warning_payloads[0]
    assert warning_payload["area_codes_count"] == 2
    assert warning_payload["mapped_count"] == 1
    assert warning_payload["missing_count"] == 1
    assert warning_payload["missing_area_codes"] == ["L1012100"]
    assert warning_payload["coverage_pct"] == 50.0
