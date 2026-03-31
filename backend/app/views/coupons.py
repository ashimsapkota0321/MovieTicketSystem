"""Coupon management API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services
from ..models import Coupon
from ..permissions import admin_required


@api_view(["GET", "POST"])
@admin_required
def admin_coupons(request: Any):
    """List or create promo coupons for admins."""
    if request.method == "GET":
        coupons = services.list_admin_coupons()
        return Response({"coupons": coupons}, status=status.HTTP_200_OK)

    payload, status_code = services.create_admin_coupon(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@admin_required
def admin_coupon_detail(request: Any, coupon_id: int):
    """Update or delete one coupon."""
    coupon = Coupon.objects.filter(id=coupon_id).first()
    if not coupon:
        return Response({"message": "Coupon not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = services.update_admin_coupon(request, coupon)
        return Response(payload, status=status_code)

    payload, status_code = services.delete_admin_coupon(coupon)
    return Response(payload, status=status_code)
