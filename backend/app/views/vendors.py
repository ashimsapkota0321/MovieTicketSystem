"""Vendor and cinema listing API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services
from ..permissions import admin_required


@api_view(["GET", "POST"])
@admin_required
def manage_vendors(request: Any):
    """List vendors or create a vendor account."""
    if request.method == "GET":
        vendors = services.list_vendors_payload(request)
        return Response({"vendors": vendors}, status=status.HTTP_200_OK)

    payload, status_code = services.create_vendor(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
def list_cinemas(request: Any):
    """Return cinema vendors for public listings."""
    payload = services.list_cinemas_payload(request)
    return Response({"vendors": payload}, status=status.HTTP_200_OK)
