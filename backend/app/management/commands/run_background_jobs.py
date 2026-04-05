"""Management command to process queued background jobs."""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand

from app import services
from app.models import BackgroundJob


class Command(BaseCommand):
    """Process queued notification and analytics export jobs."""

    help = "Process queued background jobs (notification emails and analytics report exports)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process one batch and exit.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=20,
            help="Maximum number of jobs to claim per batch.",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=2.0,
            help="Sleep seconds between empty polling cycles when running continuously.",
        )
        parser.add_argument(
            "--job-type",
            action="append",
            choices=[
                BackgroundJob.TYPE_NOTIFICATION_EMAIL,
                BackgroundJob.TYPE_ANALYTICS_MONITOR_EXPORT,
            ],
            help="Optional job type filter (can be passed multiple times).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        run_once = bool(options.get("once"))
        batch_size = max(int(options.get("batch_size") or 20), 1)
        poll_interval = max(float(options.get("poll_interval") or 2.0), 0.2)
        job_types = options.get("job_type") or None

        while True:
            summary = services.process_background_jobs(
                batch_size=batch_size,
                job_types=job_types,
            )
            claimed = int(summary.get("claimed") or 0)
            if claimed > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        "Background queue batch processed: "
                        f"claimed={summary.get('claimed', 0)}, "
                        f"completed={summary.get('completed', 0)}, "
                        f"failed={summary.get('failed', 0)}, "
                        f"requeued={summary.get('requeued', 0)}"
                    )
                )

            if run_once:
                if claimed == 0:
                    self.stdout.write("No background jobs were ready to process.")
                break

            if claimed == 0:
                time.sleep(poll_interval)
