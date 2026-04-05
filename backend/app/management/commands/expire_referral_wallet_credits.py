"""Management command to expire due referral wallet credits."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from app import services


class Command(BaseCommand):
    """Expire unused referral wallet credits and pending referrals past expiry."""

    help = "Expire due referral wallet credits for all users or an optional user id."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Optional user id to run expiry for one user only.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user_id = options.get("user_id")
        result = services.expire_referral_wallet_credits(user_id=user_id)
        self.stdout.write(
            self.style.SUCCESS(
                "Referral wallet expiry complete: "
                f"expired_transactions={result.get('expired_transactions', 0)}, "
                f"expired_amount={result.get('expired_amount', 0)}, "
                f"expired_referrals={result.get('expired_referrals', 0)}"
            )
        )
