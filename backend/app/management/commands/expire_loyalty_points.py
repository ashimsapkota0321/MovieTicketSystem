"""Management command to expire due loyalty points."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from app import loyalty


class Command(BaseCommand):
    """Expire loyalty points that crossed their expiry timestamp."""

    help = "Expire loyalty points for all users or an optional specific user id."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Optional user id to expire points only for that user.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user_id = options.get("user_id")
        result = loyalty.expire_points(user_id=user_id)
        self.stdout.write(
            self.style.SUCCESS(
                "Loyalty expiry complete: "
                f"expired_transactions={result.get('expired_transactions', 0)}, "
                f"expired_points={result.get('expired_points', 0)}"
            )
        )
