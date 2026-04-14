"""Notification API views."""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services
from ..permissions import admin_required, is_vendor_owner, vendor_required


@api_view(["GET", "POST"])
def notifications(request: Any):
    """Return in-app notifications for the authenticated actor."""
    if request.method == "POST":
        payload, status_code = services.mark_notifications_read(request)
        return Response(payload, status=status_code)

    payload, status_code = services.list_notifications(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@admin_required
def admin_vendor_custom_email(request: Any):
    """Send a custom message/email from admin to a vendor."""
    payload, status_code = services.send_admin_custom_email_to_vendor(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@vendor_required
def vendor_customer_custom_email(request: Any):
    """Send a custom message/email from vendor owner to one customer."""
    if not is_vendor_owner(request):
        return Response({"message": "Only vendor owner can send custom customer emails."}, status=403)
    payload, status_code = services.send_vendor_custom_email_to_customer(request)
    return Response(payload, status=status_code)
