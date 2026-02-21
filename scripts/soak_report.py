from __future__ import annotations

import argparse
import json
import logging
import time
import tracemalloc
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.domain.models import AlertEvent
from app.repositories.json_state_repo import JsonStateRepository
from app.services.notifier import NotificationError
from app.settings import Settings
from app.usecases.process_cycle import ProcessCycleUseCase


class _SyntheticWeatherClient:
    def __init__(self, *, new_event_every: int) -> None:
        self._cycle_index = 0
        self._new_event_every = max(0, new_event_every)

    def set_cycle(self, cycle_index: int) -> None:
        self._cycle_index = cycle_index

    def fetch_alerts(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        area_name: str,
    ) -> list[AlertEvent]:
        cycle_seed = f"{self._cycle_index:010d}"
        base_alert = AlertEvent(
            area_code=area_code,
            area_name=area_name,
            warn_var="호우",
            warn_stress="주의보",
            command="발표",
            cancel="정상",
            start_time=f"2026년 2월 21일 오전 {self._cycle_index % 12 + 1}시",
            end_time=None,
            stn_id=area_code[-4:],
            tm_fc="202602210000",
            tm_seq="1",
        )
        alerts = [base_alert]

        if self._new_event_every > 0 and self._cycle_index > 0:
            if self._cycle_index % self._new_event_every == 0:
                alerts.append(
                    AlertEvent(
                        area_code=area_code,
                        area_name=area_name,
                        warn_var="강풍",
                        warn_stress="주의보",
                        command="발표",
                        cancel="정상",
                        start_time=f"2026년 2월 21일 오후 {self._cycle_index % 12 + 1}시",
                        end_time=None,
                        stn_id=area_code[-4:],
                        tm_fc="202602210000",
                        tm_seq=cycle_seed,
                    )
                )
        return alerts


class _CaptureNotifier:
    def __init__(self, *, fail_every: int = 0) -> None:
        self.fail_every = max(0, fail_every)
        self.attempt_count = 0
        self.failure_count = 0
        self._delivery_counts: Counter[tuple[str, str | None]] = Counter()

    def send(self, message: str, report_url: str | None = None) -> None:
        self.attempt_count += 1
        if self.fail_every > 0 and self.attempt_count % self.fail_every == 0:
            self.failure_count += 1
            error = RuntimeError("synthetic notifier failure")
            raise NotificationError(
                "synthetic notifier failure",
                attempts=1,
                last_error=error,
            )
        self._delivery_counts[(message, report_url)] += 1

    @property
    def duplicate_delivery_count(self) -> int:
        return sum(max(0, count - 1) for count in self._delivery_counts.values())

    @property
    def unique_delivery_count(self) -> int:
        return len(self._delivery_counts)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("weather_alert_bot.soak")
    logger.handlers = []
    logger.propagate = False
    logger.setLevel(logging.CRITICAL)
    logger.addHandler(logging.NullHandler())
    return logger


def _build_settings(*, state_file: Path, area_codes: list[str]) -> Settings:
    area_mapping = {code: f"지역-{index + 1}" for index, code in enumerate(area_codes)}
    return Settings(
        service_api_key="soak-key",
        service_hook_url="https://example.invalid/hook",
        weather_alert_data_api_url="http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd",
        sent_messages_file=state_file,
        area_codes=area_codes,
        area_code_mapping=area_mapping,
        state_repository_type="json",
        dry_run=False,
        run_once=True,
        area_interval_sec=0,
        cycle_interval_sec=0,
        lookback_days=0,
    )


def run_soak(
    *,
    cycles: int,
    area_count: int,
    new_event_every: int,
    notifier_fail_every: int,
    state_file: Path,
    max_pending: int,
    max_duplicate_deliveries: int,
    max_state_growth: int,
    max_memory_growth_kib: int,
) -> dict[str, Any]:
    if cycles <= 0:
        raise ValueError("cycles must be >= 1")
    if area_count <= 0:
        raise ValueError("area_count must be >= 1")

    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        state_file.unlink()

    area_codes = [f"L109{index:04d}" for index in range(1, area_count + 1)]
    settings = _build_settings(state_file=state_file, area_codes=area_codes)
    logger = _build_logger()
    state_repo = JsonStateRepository(file_path=state_file, logger=logger.getChild("state"))
    weather_client = _SyntheticWeatherClient(new_event_every=new_event_every)
    notifier = _CaptureNotifier(fail_every=notifier_fail_every)
    processor = ProcessCycleUseCase(
        settings=settings,
        weather_client=weather_client,
        notifier=notifier,
        state_repo=state_repo,
        logger=logger.getChild("processor"),
    )

    tracemalloc.start()
    baseline_bytes = tracemalloc.get_traced_memory()[0]
    start_perf = time.perf_counter()

    total_sent = 0
    total_failures = 0
    max_pending_seen = 0
    max_state_size = 0

    for cycle_index in range(1, cycles + 1):
        weather_client.set_cycle(cycle_index)
        stats = processor.run_once(now=datetime(2026, 2, 21))
        total_sent += stats.sent_count
        total_failures += stats.send_failures
        max_pending_seen = max(max_pending_seen, stats.pending_total)
        max_state_size = max(max_state_size, state_repo.total_count)

    elapsed_sec = time.perf_counter() - start_perf
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    final_state_count = state_repo.total_count
    state_growth = max(0, final_state_count - area_count)
    memory_growth_kib = max(0, int((current_bytes - baseline_bytes) / 1024))
    peak_memory_kib = int(peak_bytes / 1024)

    failed_reasons: list[str] = []
    if max_pending_seen > max_pending:
        failed_reasons.append(
            f"pending_total exceeded budget ({max_pending_seen} > {max_pending})"
        )
    if notifier.duplicate_delivery_count > max_duplicate_deliveries:
        failed_reasons.append(
            "duplicate deliveries exceeded budget "
            f"({notifier.duplicate_delivery_count} > {max_duplicate_deliveries})"
        )
    if state_growth > max_state_growth:
        failed_reasons.append(f"state_growth exceeded budget ({state_growth} > {max_state_growth})")
    if memory_growth_kib > max_memory_growth_kib:
        failed_reasons.append(
            f"memory_growth_kib exceeded budget ({memory_growth_kib} > {max_memory_growth_kib})"
        )
    if total_failures > 0:
        failed_reasons.append(f"notification failures detected ({total_failures})")

    passed = not failed_reasons
    return {
        "passed": passed,
        "cycles": cycles,
        "area_count": area_count,
        "new_event_every": new_event_every,
        "notifier_fail_every": notifier_fail_every,
        "duration_sec": round(elapsed_sec, 3),
        "cycles_per_sec": round(cycles / max(elapsed_sec, 1e-9), 3),
        "total_sent": total_sent,
        "unique_delivery_count": notifier.unique_delivery_count,
        "duplicate_delivery_count": notifier.duplicate_delivery_count,
        "notification_failures": total_failures,
        "final_state_count": final_state_count,
        "max_state_size": max_state_size,
        "state_growth": state_growth,
        "max_pending_seen": max_pending_seen,
        "memory_growth_kib": memory_growth_kib,
        "peak_memory_kib": peak_memory_kib,
        "budgets": {
            "max_pending": max_pending,
            "max_duplicate_deliveries": max_duplicate_deliveries,
            "max_state_growth": max_state_growth,
            "max_memory_growth_kib": max_memory_growth_kib,
        },
        "failed_reasons": failed_reasons,
    }


def render_markdown(report: dict[str, Any]) -> str:
    status = "PASS" if report["passed"] else "FAIL"
    lines = [
        "## Soak Report",
        "",
        f"- status: `{status}`",
        f"- cycles: `{report['cycles']}`",
        f"- area_count: `{report['area_count']}`",
        f"- duration_sec: `{report['duration_sec']}`",
        f"- cycles_per_sec: `{report['cycles_per_sec']}`",
        f"- total_sent: `{report['total_sent']}`",
        f"- duplicate_delivery_count: `{report['duplicate_delivery_count']}`",
        f"- notification_failures: `{report['notification_failures']}`",
        f"- final_state_count: `{report['final_state_count']}`",
        f"- state_growth: `{report['state_growth']}`",
        f"- max_pending_seen: `{report['max_pending_seen']}`",
        f"- memory_growth_kib: `{report['memory_growth_kib']}`",
        f"- peak_memory_kib: `{report['peak_memory_kib']}`",
        f"- failed_reasons: `{report['failed_reasons']}`",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run synthetic soak test and build a report.")
    parser.add_argument("--cycles", type=int, default=3000, help="Number of processing cycles.")
    parser.add_argument("--area-count", type=int, default=3, help="Number of synthetic areas.")
    parser.add_argument(
        "--new-event-every",
        type=int,
        default=0,
        help="Inject a new event every N cycles (0 disables growth injection).",
    )
    parser.add_argument(
        "--notifier-fail-every",
        type=int,
        default=0,
        help="Inject synthetic notifier failure every N attempts (0 disables).",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("artifacts/soak/sent_messages.soak.json"),
        help="Path to synthetic state file.",
    )
    parser.add_argument(
        "--max-pending",
        type=int,
        default=0,
        help="Budget for max pending notifications.",
    )
    parser.add_argument(
        "--max-duplicate-deliveries",
        type=int,
        default=0,
        help="Budget for duplicate delivery count.",
    )
    parser.add_argument(
        "--max-state-growth",
        type=int,
        default=0,
        help="Budget for state growth from baseline area count.",
    )
    parser.add_argument(
        "--max-memory-growth-kib",
        type=int,
        default=8192,
        help="Budget for memory growth in KiB.",
    )
    parser.add_argument("--json-output", type=Path, default=None, help="Optional JSON output path.")
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    report = run_soak(
        cycles=args.cycles,
        area_count=args.area_count,
        new_event_every=args.new_event_every,
        notifier_fail_every=args.notifier_fail_every,
        state_file=args.state_file,
        max_pending=args.max_pending,
        max_duplicate_deliveries=args.max_duplicate_deliveries,
        max_state_growth=args.max_state_growth,
        max_memory_growth_kib=args.max_memory_growth_kib,
    )

    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    markdown = render_markdown(report)
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")

    print(markdown)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
