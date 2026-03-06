"""Show management API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import selectors, services


@api_view(["GET", "POST"])
def shows(request: Any):
    """List shows or create a new show."""
    if request.method == "GET":
        movie_id = request.query_params.get("movie_id") or request.query_params.get(
            "movieId"
        )
        vendor_id = request.query_params.get("vendor_id") or request.query_params.get(
            "vendorId"
        )
        shows_qs = selectors.list_shows(
            request=request, movie_id=movie_id, vendor_id=vendor_id
        )
        payload = [selectors.build_show_payload(show) for show in shows_qs]
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
