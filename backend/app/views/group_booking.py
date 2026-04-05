"""Group booking and split payment API views."""

from __future__ import annotations

from typing import Any

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import group_booking
from ..permissions import ROLE_CUSTOMER, role_required


@api_view(["GET", "POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_sessions(request: Any):
    """List customer group sessions or create a new session as host."""
    if request.method == "GET":
        payload, status_code = group_booking.list_group_booking_sessions(request)
        return Response(payload, status=status_code)

    payload, status_code = group_booking.create_group_booking_session(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def group_booking_session_detail(request: Any, session_id: int):
    """Get one group booking session by numeric id."""
    payload, status_code = group_booking.get_group_booking_session_by_id(request, session_id)
    return Response(payload, status=status_code)


@api_view(["GET"])
@role_required(ROLE_CUSTOMER)
def group_booking_session_by_invite(request: Any, invite_code: str):
    """Get one group booking session by invite code."""
    payload, status_code = group_booking.get_group_booking_session_by_invite(request, invite_code)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_join(request: Any, invite_code: str):
    """Join a group booking session by invite code."""
    payload, status_code = group_booking.join_group_booking_session(request, invite_code)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_assign_seats(request: Any, session_id: int):
    """Assign or update participant seats for seat-based group split mode."""
    payload, status_code = group_booking.update_group_participant_seats(request, session_id)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_manual_split(request: Any, session_id: int):
    """Apply manual amount split across session participants (host only)."""
    payload, status_code = group_booking.apply_group_manual_split(request, session_id)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_initiate_payment(request: Any, session_id: int):
    """Initiate an individual participant payment for a group session."""
    payload, status_code = group_booking.initiate_group_payment(request, session_id)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_complete_payment(request: Any, session_id: int, payment_id: int):
    """Mark participant payment success/failure and finalize session when fully paid."""
    payload, status_code = group_booking.complete_group_payment(request, session_id, payment_id)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_drop_out(request: Any, session_id: int):
    """Allow a participant to leave before payment is processed."""
    payload, status_code = group_booking.drop_group_participant(request, session_id)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def group_booking_cancel(request: Any, session_id: int):
    """Cancel an active group booking session (host only)."""
    payload, status_code = group_booking.cancel_group_booking_session(request, session_id)
    return Response(payload, status=status_code)
