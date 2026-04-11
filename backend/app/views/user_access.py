"""Customer alias endpoints for wallet, subscription, and reward redemption."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from rest_framework.decorators import api_view
from rest_framework import status
from rest_framework.response import Response

from .. import loyalty, services, subscription
from ..models import UserWallet, UserWalletTransaction
from ..permissions import ROLE_CUSTOMER, resolve_customer, role_required


def _to_money(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        parsed = Decimal("0")
    return parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _serialize_cash_wallet(wallet: UserWallet) -> dict[str, Any]:
    return {
        "user_id": wallet.user_id,
        "balance": float(_to_money(wallet.balance)),
        "total_credited": float(_to_money(wallet.total_credited)),
        "total_debited": float(_to_money(wallet.total_debited)),
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
    }


def _serialize_cash_wallet_tx(tx: UserWalletTransaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "transaction_type": tx.transaction_type,
        "status": tx.status,
        "amount": float(_to_money(tx.amount)),
        "reference_id": tx.reference_id,
        "provider": tx.provider,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "processed_at": tx.processed_at.isoformat() if tx.processed_at else None,
        "metadata": tx.metadata if isinstance(tx.metadata, dict) else {},
    }


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def user_wallet(request: Any):
    """Return consolidated wallet payload for customer-facing UI."""
    customer = resolve_customer(request)
    if customer is None:
        return Response(
            {"message": "Customer access required."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    loyalty_payload, loyalty_status = loyalty.get_customer_dashboard(request)
    if loyalty_status != 200:
        return Response(loyalty_payload, status=loyalty_status)

    referral_payload, referral_status = services.get_customer_referral_dashboard(request)
    if referral_status != 200:
        return Response(referral_payload, status=referral_status)

    cash_wallet, _ = UserWallet.objects.get_or_create(user=customer)
    cash_wallet = services.recalculate_user_wallet_snapshot(cash_wallet)
    cash_rows = list(
        UserWalletTransaction.objects.filter(user=customer)
        .order_by("-created_at", "-id")[:20]
    )

    return Response(
        {
            "cash_wallet": _serialize_cash_wallet(cash_wallet),
            "cash_wallet_recent_transactions": [
                _serialize_cash_wallet_tx(item) for item in cash_rows
            ],
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
