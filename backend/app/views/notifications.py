"""Notification API views."""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services


@api_view(["GET", "POST"])
def notifications(request: Any):
    """Return in-app notifications for the authenticated actor."""
    if request.method == "POST":
        payload, status_code = services.mark_notifications_read(request)
        return Response(payload, status=status_code)

    payload, status_code = services.list_notifications(request)
    return Response(payload, status=status_code)
