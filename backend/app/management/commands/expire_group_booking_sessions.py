"""Management command to expire stale group booking sessions."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from app import group_booking


class Command(BaseCommand):
    """Expire timed-out group booking sessions and release locked seats."""

    help = "Expire active group booking sessions whose seat-hold timer has elapsed."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--session-id",
            type=int,
            default=None,
            help="Optionally expire one specific session id.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        session_id = options.get("session_id")
        result = group_booking.expire_group_booking_sessions(session_id=session_id)
        self.stdout.write(
            self.style.SUCCESS(
                "Group booking expiry complete: "
                f"expired_sessions={result.get('expired_sessions', 0)}, "
                f"released_seats={result.get('released_seats', 0)}"
            )
        )
