"""Show management API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import selectors, services
from ..permissions import (
    is_admin_request,
    is_vendor_request,
    resolve_vendor,
    vendor_required,
)
from ..utils import coalesce


@api_view(["GET", "POST"])
def shows(request: Any):
    """List shows or create a new show."""
    if request.method == "GET":
        dashboard_scope = is_admin_request(request) or is_vendor_request(request)
        movie_id = request.query_params.get("movie_id") or request.query_params.get(
            "movieId"
        )
        vendor_id = request.query_params.get("vendor_id") or request.query_params.get(
            "vendorId"
        )
        # Admin/vendor dashboards own their scope already; avoid city over-filtering.
        city = None
        if not dashboard_scope:
            city = coalesce(request.query_params, "city", "location")
        shows_qs = selectors.list_shows(
            request=request,
            movie_id=movie_id,
            vendor_id=vendor_id,
            city=city,
        )
        running_status_label = "ongoing" if dashboard_scope else None
        payload = [
            selectors.build_show_payload(show, running_status_label=running_status_label)
            for show in shows_qs
        ]
        return Response({"shows": payload}, status=status.HTTP_200_OK)

    payload, status_code = services.create_show(request)
    return Response(payload, status=status_code)


@api_view(["DELETE"])
def show_detail(request: Any, show_id: int):
    """Delete a show by ID."""
    show = selectors.get_show(show_id)
    if not show:
        return Response({"message": "Show not found"}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.delete_show(request, show)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_quick_hall_swap(request: Any, show_id: int):
    """Preview or execute a quick hall swap for one vendor-owned show."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

    show = selectors.get_show(show_id)
    if not show or show.vendor_id != vendor.id:
        return Response({"message": "Show not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        payload, status_code = services.preview_vendor_quick_hall_swap(show)
        return Response(payload, status=status_code)

    payload, status_code = services.quick_swap_show_hall(request, show)
    return Response(payload, status=status_code)
