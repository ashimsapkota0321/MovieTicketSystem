"""Booking administration API views."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from ..permissions import ROLE_CUSTOMER, admin_required, role_required, vendor_required
from .. import services


def _mark_booking_complete(booking: Any) -> tuple[dict[str, Any], int]:
    """Allow only one-way manual completion from pending to confirmed."""
    normalized_status = booking.normalize_booking_status(getattr(booking, "booking_status", None))
    if normalized_status != booking.Status.PENDING:
        return {
            "message": "Only pending bookings can be manually marked complete.",
            "booking": services.build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    booking.booking_status = booking.Status.CONFIRMED
    try:
        booking.save(update_fields=["booking_status"])
    except ValidationError as exc:
        message = "; ".join(exc.messages) if getattr(exc, "messages", None) else "Invalid booking status transition."
        return {"message": message}, status.HTTP_400_BAD_REQUEST

    refreshed = services._get_booking_or_none(booking.id) or booking
    return {
        "message": "Booking marked as complete.",
        "booking": services.build_booking_payload(refreshed),
    }, status.HTTP_200_OK


@api_view(["GET"])
@admin_required
def admin_bookings(request: Any):
    """List bookings for admin management."""
    payload = services.list_bookings_payload(request)
    return Response({"bookings": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
@admin_required
def admin_booking_dropoff_analytics(request: Any):
    """Return platform-level booking/payment drop-off analytics for admin dashboard."""
    payload = services.get_admin_dropoff_analytics()
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET", "DELETE"])
@admin_required
def admin_booking_detail(request: Any, booking_id: int):
    """Retrieve or delete a booking."""
    booking = services._get_booking_or_none(booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        payload = services.build_booking_detail_payload(booking)
        return Response({"booking": payload}, status=status.HTTP_200_OK)

    payload, status_code = services.admin_delete_booking(request, booking)
    return Response(payload, status=status_code)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def admin_booking_cancel(request: Any, booking_id: int):
    """Cancel a booking."""
    booking = services._get_booking_or_none(booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = services.admin_cancel_booking(request, booking)
    return Response(payload, status=status_code)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def admin_booking_refund(request: Any, booking_id: int):
    """Refund a booking."""
    booking = services._get_booking_or_none(booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = services.admin_refund_booking(request, booking)
    return Response(payload, status=status_code)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def admin_booking_mark_complete(request: Any, booking_id: int):
    """Mark a pending booking as complete (confirmed)."""
    booking = services._get_booking_or_none(booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = _mark_booking_complete(booking)
    return Response(payload, status=status_code)


@api_view(["GET"])
@vendor_required
def vendor_bookings(request: Any):
    """List bookings for the authenticated vendor only."""
    payload = services.list_bookings_payload(request)
    return Response({"bookings": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
@vendor_required
def vendor_booking_detail(request: Any, booking_id: int):
    """Retrieve one vendor-owned booking detail."""
    booking = services._get_vendor_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload = services.build_booking_detail_payload(booking)
    return Response({"booking": payload}, status=status.HTTP_200_OK)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@vendor_required
def vendor_bulk_assign_booking_seats(request: Any, booking_id: int):
    """Assign bulk seats for a corporate booking by category counts."""
    booking = services._get_vendor_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = services.bulk_assign_booking_seats(request, booking)
    return Response(payload, status=status_code)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@vendor_required
def vendor_booking_cancel(request: Any, booking_id: int):
    """Cancel a vendor-owned booking."""
    booking = services._get_vendor_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = services.vendor_cancel_booking(request, booking)
    return Response(payload, status=status_code)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@vendor_required
def vendor_booking_refund(request: Any, booking_id: int):
    """Refund a vendor-owned booking."""
    booking = services._get_vendor_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = services.vendor_refund_booking(request, booking)
    return Response(payload, status=status_code)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@vendor_required
def vendor_booking_mark_complete(request: Any, booking_id: int):
    """Mark a vendor-owned pending booking as complete (confirmed)."""
    booking = services._get_vendor_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = _mark_booking_complete(booking)
    return Response(payload, status=status_code)


@api_view(["DELETE"])
@vendor_required
def vendor_booking_delete(request: Any, booking_id: int):
    """Delete a vendor-owned booking."""
    booking = services._get_vendor_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = services.admin_delete_booking(request, booking)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def customer_bookings(request: Any):
    """List booking history for the authenticated customer."""
    payload = services.list_customer_bookings_payload(request)
    return Response({"bookings": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def customer_booking_detail(request: Any, booking_id: int):
    """Retrieve one customer-owned booking detail."""
    booking = services._get_customer_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload = services.build_booking_detail_payload(booking)
    return Response({"booking": payload}, status=status.HTTP_200_OK)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@role_required(ROLE_CUSTOMER)
def customer_booking_cancel(request: Any, booking_id: int):
    """Cancel customer booking from booking history using vendor policy."""
    booking = services._get_customer_booking_or_none(request, booking_id)
    if not booking:
        return Response({"message": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
    payload, status_code = services.customer_cancel_booking(request, booking)
    return Response(payload, status=status_code)
