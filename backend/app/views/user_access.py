"""Customer alias endpoints for wallet, subscription, and reward redemption."""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import loyalty, services, subscription
from ..permissions import ROLE_CUSTOMER, role_required


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def user_wallet(request: Any):
    """Return consolidated wallet payload for customer-facing UI."""
    loyalty_payload, loyalty_status = loyalty.get_customer_dashboard(request)
    if loyalty_status != 200:
        return Response(loyalty_payload, status=loyalty_status)

    referral_payload, referral_status = services.get_customer_referral_dashboard(request)
    if referral_status != 200:
        return Response(referral_payload, status=referral_status)

    return Response(
        {
            "loyalty": loyalty_payload.get("wallet"),
            "loyalty_recent_transactions": loyalty_payload.get("transactions", []),
            "referral_wallet": referral_payload.get("wallet"),
            "referral_recent_transactions": referral_payload.get("transactions", []),
        },
        status=200,
    )


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def user_subscription(request: Any):
    """Return active subscription payload for customer-facing UI."""
    payload, status_code = subscription.get_active_subscription_payload(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def user_redeem(request: Any):
    """Redeem a loyalty reward through customer alias route."""
    payload, status_code = loyalty.redeem_reward_for_customer(request)
    return Response(payload, status=status_code)
