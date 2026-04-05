"""Subscription and membership API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import subscription
from ..models import SubscriptionPlan
from ..permissions import (
    ROLE_CUSTOMER,
    admin_required,
    resolve_vendor,
    role_required,
    vendor_required,
)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def subscription_plans(request: Any):
    """List public subscription plans (global + vendor-scoped)."""
    payload, status_code = subscription.list_plans_for_customer(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def subscription_plan_detail(request: Any, plan_id: int):
    """Return details for a single public subscription plan."""
    payload, status_code = subscription.get_plan_detail_for_customer(plan_id, request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def subscription_dashboard(request: Any):
    """Return subscription dashboard including active plan and transaction history."""
    payload, status_code = subscription.get_customer_dashboard(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def subscription_active(request: Any):
    """Return active subscription for current customer."""
    payload, status_code = subscription.get_active_subscription_payload(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def subscription_subscribe(request: Any):
    """Purchase and activate a subscription plan for current customer."""
    payload, status_code = subscription.subscribe_customer(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def subscription_upgrade(request: Any):
    """Upgrade current active subscription with prorated credit handling."""
    payload, status_code = subscription.upgrade_customer(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def subscription_cancel(request: Any):
    """Cancel current active subscription immediately or at period end."""
    payload, status_code = subscription.cancel_customer_subscription(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def subscription_checkout_preview(request: Any):
    """Preview how current subscription affects booking checkout totals."""
    payload, status_code = subscription.preview_checkout_for_customer(request)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@admin_required
def admin_subscription_plans(request: Any):
    """List or create admin-controlled global subscription plans."""
    if request.method == "GET":
        payload, status_code = subscription.list_admin_plans(request)
        return Response(payload, status=status_code)

    payload, status_code = subscription.create_admin_plan(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@admin_required
def admin_subscription_plan_detail(request: Any, plan_id: int):
    """Update or disable/delete one admin-controlled global subscription plan."""
    plan = SubscriptionPlan.objects.filter(id=plan_id, vendor__isnull=True).first()
    if not plan:
        return Response({"message": "Subscription plan not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = subscription.update_admin_plan(request, plan)
        return Response(payload, status=status_code)

    payload, status_code = subscription.delete_admin_plan(request, plan)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_subscription_plans(request: Any):
    """List or create subscription plans owned by current vendor."""
    if request.method == "GET":
        payload, status_code = subscription.list_vendor_plans(request)
        return Response(payload, status=status_code)

    payload, status_code = subscription.create_vendor_plan(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_subscription_plan_detail(request: Any, plan_id: int):
    """Update or disable one vendor-owned subscription plan."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    plan = SubscriptionPlan.objects.filter(id=plan_id, vendor_id=vendor.id).first()
    if not plan:
        return Response({"message": "Subscription plan not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = subscription.update_vendor_plan(request, plan)
        return Response(payload, status=status_code)

    payload, status_code = subscription.delete_vendor_plan(plan)
    return Response(payload, status=status_code)
