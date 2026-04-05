"""Vendor offer API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import offers
from ..models import VendorOffer
from ..permissions import ROLE_CUSTOMER, resolve_vendor, role_required, vendor_required


@api_view(["GET", "POST"])
@vendor_required
def vendor_offers(request: Any):
    """List or create vendor-specific offers."""
    if request.method == "GET":
        payload, status_code = offers.list_vendor_offers(request)
        return Response(payload, status=status_code)

    payload, status_code = offers.create_vendor_offer(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_offer_detail(request: Any, offer_id: int):
    """Update or disable one vendor-owned offer."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    offer = VendorOffer.objects.filter(id=offer_id, vendor_id=vendor.id).first()
    if not offer:
        return Response({"message": "Offer not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = offers.update_vendor_offer(request, offer)
        return Response(payload, status=status_code)

    payload, status_code = offers.delete_vendor_offer(offer)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def user_vendor_offers(request: Any):
    """List currently active vendor offers available to customers."""
    payload, status_code = offers.list_offers_for_customer(request)
    return Response(payload, status=status_code)
