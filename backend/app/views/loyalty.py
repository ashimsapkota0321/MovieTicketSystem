"""Loyalty and rewards API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import loyalty
from ..models import LoyaltyPromotion, Reward
from ..permissions import (
    ROLE_CUSTOMER,
    admin_required,
    resolve_vendor,
    role_required,
    vendor_required,
)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def loyalty_dashboard(request: Any):
    """Return loyalty wallet summary and recent ledger entries for current customer."""
    payload, status_code = loyalty.get_customer_dashboard(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def loyalty_transactions(request: Any):
    """Return loyalty transaction history for current customer."""
    payload, status_code = loyalty.list_customer_transactions(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def loyalty_rewards(request: Any):
    """Return active rewards that the current customer can browse/redeem."""
    payload, status_code = loyalty.list_rewards_for_customer(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def loyalty_checkout_preview(request: Any):
    """Preview points/reward discount outcome before checkout payment step."""
    payload, status_code = loyalty.preview_checkout_for_customer(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def loyalty_redeem_reward(request: Any):
    """Redeem a reward directly and create an unused redemption entry."""
    payload, status_code = loyalty.redeem_reward_for_customer(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def loyalty_redemptions(request: Any):
    """Return reward redemption history for current customer."""
    payload, status_code = loyalty.list_customer_redemptions(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def loyalty_referral_bonus(request: Any):
    """Apply one-time referral bonus points for current customer."""
    payload, status_code = loyalty.apply_referral_bonus(request)
    return Response(payload, status=status_code)


@api_view(["GET", "PATCH"])
@admin_required
def admin_loyalty_rule(request: Any):
    """Fetch or update central admin loyalty rule settings."""
    if request.method == "GET":
        payload, status_code = loyalty.list_admin_loyalty_rules()
        return Response(payload, status=status_code)

    payload, status_code = loyalty.update_admin_loyalty_rule(request)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@admin_required
def admin_loyalty_rewards(request: Any):
    """List or create central admin-managed rewards."""
    if request.method == "GET":
        payload, status_code = loyalty.list_admin_rewards()
        return Response(payload, status=status_code)

    payload, status_code = loyalty.create_admin_reward(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@admin_required
def admin_loyalty_reward_detail(request: Any, reward_id: int):
    """Update or delete one central admin-managed reward."""
    reward = Reward.objects.filter(id=reward_id, vendor__isnull=True).first()
    if not reward:
        return Response({"message": "Reward not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = loyalty.update_admin_reward(request, reward)
        return Response(payload, status=status_code)

    payload, status_code = loyalty.delete_admin_reward(reward)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@admin_required
def admin_loyalty_promotions(request: Any):
    """List or create central admin-managed loyalty promotions."""
    if request.method == "GET":
        payload, status_code = loyalty.list_admin_promotions()
        return Response(payload, status=status_code)

    payload, status_code = loyalty.create_admin_promotion(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@admin_required
def admin_loyalty_promotion_detail(request: Any, promotion_id: int):
    """Update or delete one central admin-managed promotion."""
    promotion = LoyaltyPromotion.objects.filter(id=promotion_id, vendor__isnull=True).first()
    if not promotion:
        return Response({"message": "Promotion not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = loyalty.update_admin_promotion(request, promotion)
        return Response(payload, status=status_code)

    payload, status_code = loyalty.delete_admin_promotion(promotion)
    return Response(payload, status=status_code)


@api_view(["GET", "PATCH"])
@vendor_required
def vendor_loyalty_rule(request: Any):
    """Get or update vendor-specific loyalty earning override rule."""
    if request.method == "GET":
        payload, status_code = loyalty.get_vendor_rule(request)
        return Response(payload, status=status_code)

    payload, status_code = loyalty.update_vendor_rule(request)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_loyalty_rewards(request: Any):
    """List or create vendor-owned rewards."""
    if request.method == "GET":
        payload, status_code = loyalty.list_vendor_rewards(request)
        return Response(payload, status=status_code)

    payload, status_code = loyalty.create_vendor_reward(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_loyalty_reward_detail(request: Any, reward_id: int):
    """Update or delete one vendor-owned reward."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    reward = Reward.objects.filter(id=reward_id, vendor_id=vendor.id).first()
    if not reward:
        return Response({"message": "Reward not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = loyalty.update_vendor_reward(request, reward)
        return Response(payload, status=status_code)

    payload, status_code = loyalty.delete_vendor_reward(reward)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_loyalty_promotions(request: Any):
    """List or create vendor loyalty promotions (festival/daily/weekly/referral)."""
    if request.method == "GET":
        payload, status_code = loyalty.list_vendor_promotions(request)
        return Response(payload, status=status_code)

    payload, status_code = loyalty.create_vendor_promotion(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_loyalty_promotion_detail(request: Any, promotion_id: int):
    """Update or delete one vendor-owned loyalty promotion."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    promotion = LoyaltyPromotion.objects.filter(id=promotion_id, vendor_id=vendor.id).first()
    if not promotion:
        return Response({"message": "Promotion not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = loyalty.update_vendor_promotion(request, promotion)
        return Response(payload, status=status_code)

    payload, status_code = loyalty.delete_vendor_promotion(promotion)
    return Response(payload, status=status_code)
