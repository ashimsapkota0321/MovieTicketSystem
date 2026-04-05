"""Management command to expire subscriptions and notify upcoming expiries."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from app import subscription


class Command(BaseCommand):
    """Expire due subscriptions and dispatch optional pre-expiry notifications."""

    help = "Expire active subscriptions whose end time has passed and notify upcoming expiries."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Optional user id to process one customer only.",
        )
        parser.add_argument(
            "--notify-hours",
            type=int,
            default=48,
            help="Send expiring notifications within this many upcoming hours.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        user_id = options.get("user_id")
        notify_hours = options.get("notify_hours")

        expiry_result = subscription.expire_subscriptions(user_id=user_id)
        notify_result = subscription.notify_expiring_subscriptions(
            notify_hours=notify_hours,
            user_id=user_id,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Subscription sweep complete: "
                f"expired_subscriptions={expiry_result.get('expired_subscriptions', 0)}, "
                f"expiring_notifications={notify_result.get('expiring_notifications', 0)}, "
                f"notify_hours={notify_result.get('notify_hours', notify_hours)}"
            )
        )
