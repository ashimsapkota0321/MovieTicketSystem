"""Management command to sync show lifecycle statuses."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from app import selectors


class Command(BaseCommand):
    """Synchronize show statuses based on current server time."""

    help = "Update show status flow (upcoming/running/completed) using current time."

    def handle(self, *args: Any, **options: Any) -> None:
        now = timezone.now()
        updated = selectors.sync_show_lifecycle_statuses(now=now)
        self.stdout.write(
            self.style.SUCCESS(
                "Show lifecycle sync complete: "
                f"upcoming={updated.get(selectors.SHOW_STATUS_UPCOMING, 0)}, "
                f"running={updated.get(selectors.SHOW_STATUS_RUNNING, 0)}, "
                f"completed={updated.get(selectors.SHOW_STATUS_COMPLETED, 0)}"
            )
        )
