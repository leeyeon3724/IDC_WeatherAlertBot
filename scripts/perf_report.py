from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from app.domain.models import AlertNotification
from app.repositories.sqlite_state_repo import SqliteStateRepository


@dataclass(frozen=True)
class Metric:
    value: float
    unit: str
    better: str
    samples: list[float]


def _build_notifications(count: int) -> list[AlertNotification]:
    notifications: list[AlertNotification] = []
    for index in range(count):
        notifications.append(
            AlertNotification(
                event_id=f"perf:event:{index}",
                area_code="11B00000",
                message=f"perf message {index}",
                report_url="https://example.com/report",
            )
        )
    return notifications


def _round_samples(values: list[float]) -> list[float]:
    return [round(value, 3) for value in values]


def _median(values: list[float]) -> float:
    return round(float(statistics.median(values)), 3)


def _ops_per_sec(item_count: int, duration_ms: float) -> float:
    if duration_ms <= 0:
        return 0.0
    return round(item_count / (duration_ms / 1000.0), 3)


def build_report(*, item_count: int, repeats: int) -> dict[str, object]:
    notifications = _build_notifications(item_count)
    event_ids = [notification.event_id for notification in notifications]
    now = datetime(2026, 2, 21, tzinfo=UTC)
    old_time = "2020-01-01T00:00:00Z"

    upsert_samples_ms: list[float] = []
    mark_samples_ms: list[float] = []
    cleanup_samples_ms: list[float] = []

    with tempfile.TemporaryDirectory(prefix="sqlite-perf-") as temp_dir:
        temp_path = Path(temp_dir)
        for index in range(repeats):
            repo = SqliteStateRepository(temp_path / f"bench-{index}.db")

            start = perf_counter()
            inserted = repo.upsert_notifications(notifications)
            upsert_duration_ms = (perf_counter() - start) * 1000.0
            if inserted != item_count:
                raise RuntimeError(
                    f"unexpected insert count at repeat {index}: {inserted} != {item_count}"
                )

            start = perf_counter()
            marked = repo.mark_many_sent(event_ids)
            mark_duration_ms = (perf_counter() - start) * 1000.0
            if marked != item_count:
                raise RuntimeError(
                    f"unexpected mark count at repeat {index}: {marked} != {item_count}"
                )

            with repo._connect() as conn:
                conn.execute(
                    """
                    UPDATE notifications
                    SET updated_at = ?, last_sent_at = ?
                    """,
                    (old_time, old_time),
                )

            start = perf_counter()
            removed = repo.cleanup_stale(
                days=30,
                include_unsent=False,
                now=now,
            )
            cleanup_duration_ms = (perf_counter() - start) * 1000.0
            if removed != item_count:
                raise RuntimeError(
                    f"unexpected cleanup count at repeat {index}: {removed} != {item_count}"
                )

            upsert_samples_ms.append(upsert_duration_ms)
            mark_samples_ms.append(mark_duration_ms)
            cleanup_samples_ms.append(cleanup_duration_ms)

    upsert_ops = [_ops_per_sec(item_count, sample) for sample in upsert_samples_ms]
    mark_ops = [_ops_per_sec(item_count, sample) for sample in mark_samples_ms]
    cleanup_ops = [_ops_per_sec(item_count, sample) for sample in cleanup_samples_ms]

    metrics = {
        "sqlite.upsert.duration_ms": Metric(
            value=_median(upsert_samples_ms),
            unit="ms",
            better="lower",
            samples=_round_samples(upsert_samples_ms),
        ),
        "sqlite.mark_many_sent.duration_ms": Metric(
            value=_median(mark_samples_ms),
            unit="ms",
            better="lower",
            samples=_round_samples(mark_samples_ms),
        ),
        "sqlite.cleanup_stale.duration_ms": Metric(
            value=_median(cleanup_samples_ms),
            unit="ms",
            better="lower",
            samples=_round_samples(cleanup_samples_ms),
        ),
        "sqlite.upsert.ops_per_sec": Metric(
            value=_median(upsert_ops),
            unit="ops/s",
            better="higher",
            samples=_round_samples(upsert_ops),
        ),
        "sqlite.mark_many_sent.ops_per_sec": Metric(
            value=_median(mark_ops),
            unit="ops/s",
            better="higher",
            samples=_round_samples(mark_ops),
        ),
        "sqlite.cleanup_stale.ops_per_sec": Metric(
            value=_median(cleanup_ops),
            unit="ops/s",
            better="higher",
            samples=_round_samples(cleanup_ops),
        ),
    }

    return {
        "meta": {
            "created_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "item_count": item_count,
            "repeats": repeats,
        },
        "metrics": {
            name: {
                "value": metric.value,
                "unit": metric.unit,
                "better": metric.better,
                "samples": metric.samples,
            }
            for name, metric in metrics.items()
        },
    }


def render_markdown(report: dict[str, object]) -> str:
    meta = report["meta"]
    metrics: dict[str, dict[str, object]] = report["metrics"]  # type: ignore[assignment]
    lines = [
        "## Lightweight Performance Report",
        "",
        (
            f"- created_at_utc: `{meta['created_at_utc']}`"
            f" / python: `{meta['python_version']}`"
            f" / platform: `{meta['platform']}`"
        ),
        f"- items: `{meta['item_count']}` / repeats: `{meta['repeats']}`",
        "",
        "| metric | value | unit | better | samples |",
        "|---|---:|---|---|---|",
    ]
    for name in sorted(metrics):
        metric = metrics[name]
        lines.append(
            f"| `{name}` | {metric['value']} | {metric['unit']} | {metric['better']} | "
            f"`{metric['samples']}` |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a lightweight SQLite perf report.")
    parser.add_argument(
        "--items",
        type=int,
        default=400,
        help="Number of notifications per benchmark run.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Number of repeated benchmark runs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/perf/report.json"),
        help="JSON output path.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=None,
        help="Optional markdown output path.",
    )
    args = parser.parse_args()

    if args.items <= 0:
        parser.error("--items must be > 0")
    if args.repeats <= 0:
        parser.error("--repeats must be > 0")

    report = build_report(item_count=args.items, repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    markdown = render_markdown(report)
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown + "\n", encoding="utf-8")

    print(f"perf report written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
