"""Seat layout and seat status management API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services
from ..permissions import vendor_required


@api_view(["GET", "POST"])
@vendor_required
def vendor_seat_layout(request: Any):
    """List or save vendor hall seat layout."""
    if request.method == "GET":
        payload, status_code = services.list_vendor_seat_layout(request)
        return Response(payload, status=status_code)

    payload, status_code = services.create_or_update_vendor_seat_layout(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@vendor_required
def vendor_seat_status(request: Any):
    """Update vendor seat statuses for a selected show."""
    payload, status_code = services.update_vendor_seat_status(request)
    return Response(payload, status=status_code)
