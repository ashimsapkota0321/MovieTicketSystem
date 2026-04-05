"""Referral and referral wallet API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services
from ..models import Referral
from ..permissions import ROLE_CUSTOMER, admin_required, role_required


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def referral_dashboard(request: Any):
    """Return referral code, referral status, wallet summary, and recent activity."""
    payload, status_code = services.get_customer_referral_dashboard(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def referral_wallet_transactions(request: Any):
    """Return referral wallet transaction history for current customer."""
    payload, status_code = services.list_customer_referral_wallet_transactions(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def referral_wallet_checkout_preview(request: Any):
    """Preview referral wallet deduction before checkout."""
    payload, status_code = services.preview_customer_referral_wallet_checkout(request)
    return Response(payload, status=status_code)


@api_view(["GET", "PATCH"])
@admin_required
def admin_referral_controls(request: Any):
    """Get or update central referral policy and operational summary."""
    if request.method == "GET":
        payload, status_code = services.get_admin_referral_control_payload(request)
        return Response(payload, status=status_code)

    payload, status_code = services.update_admin_referral_policy(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@admin_required
def admin_referral_status(request: Any, referral_id: int):
    """Update referral status with admin approval/rejection/reversal actions."""
    referral = Referral.objects.filter(id=referral_id).first()
    if not referral:
        return Response({"message": "Referral not found."}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.update_admin_referral_status(request, referral)
    return Response(payload, status=status_code)
