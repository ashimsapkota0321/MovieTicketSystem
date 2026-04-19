"""Notification-related service helpers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from ..models import BackgroundJob, Admin, Booking, Movie, Notification, Payment, Refund, Screen, Seat, Show, Showtime, Ticket, User, Vendor
from ..permissions import is_authenticated, resolve_admin, resolve_customer, resolve_vendor
from ..utils import coalesce, get_payload, parse_bool


def _quantize_money(value: Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _seat_label(seat: Seat) -> str:
    row_label = str(getattr(seat, "row_label", "") or "").strip()
    seat_number = str(getattr(seat, "seat_number", "") or "").strip()
    if row_label and seat_number:
        return f"{row_label}-{seat_number}"
    if row_label:
        return row_label
    if seat_number:
        return seat_number
    return str(getattr(seat, "id", "") or "")


def _find_ticket_reference_for_booking(booking_id: int) -> Optional[str]:
    """Return the latest ticket reference linked to the given booking id."""
    if booking_id <= 0:
        return None

    try:
        ticket = (
            Ticket.objects.filter(payload__booking__booking_id=booking_id)
            .only("reference")
            .order_by("-id")
            .first()
        )
        if ticket:
            return str(ticket.reference)
    except Exception:
        ticket = None

    recent_tickets = Ticket.objects.only("reference", "payload").order_by("-id")[:500]
    for item in recent_tickets:
        payload = item.payload if isinstance(item.payload, dict) else {}
        booking_payload = payload.get("booking") if isinstance(payload, dict) else {}
        if not isinstance(booking_payload, dict):
            continue
        booking_id_value = booking_payload.get("booking_id") or booking_payload.get("id")
        try:
            payload_booking_id = int(booking_id_value)
        except (TypeError, ValueError):
            payload_booking_id = 0
        if payload_booking_id == booking_id:
            return str(item.reference)
    return None


def _get_latest_payment_for_booking(booking: Booking) -> Optional[Payment]:
    if not booking:
        return None
    return booking.payments.all().order_by("-payment_date", "-id").first()


def _get_latest_refund_for_booking(payment: Optional[Payment]) -> Optional[Refund]:
    if not payment:
        return None
    return payment.refunds.all().order_by("-refund_date", "-id").first()


def _create_notification(
    *,
    recipient_role: str,
    recipient_id: int,
    recipient_email: Optional[str],
    event_type: str,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
    send_email_too: bool = False,
) -> Notification:
    """Persist an in-app notification and optionally send a matching email."""
    channel = Notification.CHANNEL_BOTH if send_email_too else Notification.CHANNEL_IN_APP
    notification = Notification.objects.create(
        recipient_role=recipient_role,
        recipient_id=recipient_id,
        recipient_email=(str(recipient_email).strip() if recipient_email else None),
        event_type=event_type,
        channel=channel,
        title=title,
        message=message,
        metadata=metadata or {},
    )

    if send_email_too:
        _queue_notification_email(
            subject=title,
            message=message,
            recipient_email=recipient_email,
        )

    return notification


def _build_notification_payload(notification: Notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "recipient_role": notification.recipient_role,
        "recipient_id": notification.recipient_id,
        "recipient_email": notification.recipient_email,
        "event_type": notification.event_type,
        "channel": notification.channel,
        "title": notification.title,
        "message": notification.message,
        "metadata": notification.metadata or {},
        "is_read": bool(notification.is_read),
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def _build_booking_notification_metadata(
    booking: Booking,
    *,
    include_booking_detail: bool = False,
) -> dict[str, Any]:
    """Build rich booking/payment metadata for in-app notification payloads."""
    showtime = booking.showtime if booking else None
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    movie = getattr(showtime, "movie", None) if showtime else None
    latest_payment = _get_latest_payment_for_booking(booking)
    latest_refund = _get_latest_refund_for_booking(latest_payment)
    amount_basis = _quantize_money(booking.total_amount or Decimal("0"))
    seat_labels = [
        _seat_label(item.seat)
        for item in booking.booking_seats.select_related("seat").all()
        if item.seat
    ]

    metadata: dict[str, Any] = {
        "booking_id": booking.id,
        "booking_status": booking.booking_status,
        "booking_date": booking.booking_date.isoformat() if booking.booking_date else None,
        "user_id": booking.user_id,
        "user_email": booking.user.email if booking.user else None,
        "showtime_id": booking.showtime_id,
        "show_start_time": showtime.start_time.isoformat() if showtime and showtime.start_time else None,
        "show_end_time": showtime.end_time.isoformat() if showtime and showtime.end_time else None,
        "movie_id": movie.id if movie else None,
        "movie_title": movie.title if movie else None,
        "vendor_id": vendor.id if vendor else None,
        "vendor_name": vendor.name if vendor else None,
        "screen_id": screen.id if screen else None,
        "screen_number": screen.screen_number if screen else None,
        "seats": seat_labels,
        "seat_count": len(seat_labels),
        "amount_basis": float(amount_basis),
        "payment": {
            "id": latest_payment.id if latest_payment else None,
            "status": latest_payment.payment_status if latest_payment else None,
            "method": latest_payment.payment_method if latest_payment else None,
            "amount": float(_quantize_money(latest_payment.amount or Decimal("0"))) if latest_payment else 0.0,
            "paid_at": latest_payment.payment_date.isoformat() if latest_payment and latest_payment.payment_date else None,
        },
        "refund": {
            "id": latest_refund.id if latest_refund else None,
            "status": latest_refund.refund_status if latest_refund else None,
            "amount": float(_quantize_money(latest_refund.refund_amount or Decimal("0"))) if latest_refund else 0.0,
            "reason": latest_refund.refund_reason if latest_refund else None,
            "refunded_at": latest_refund.refund_date.isoformat() if latest_refund and latest_refund.refund_date else None,
        },
        "ticket_reference": _find_ticket_reference_for_booking(booking.id),
    }

    if include_booking_detail:
        from . import build_booking_detail_payload

        metadata["booking_detail"] = build_booking_detail_payload(booking)

    return metadata


def _notify_show_update(
    *,
    vendor: Vendor,
    movie: Movie,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=vendor.id,
        recipient_email=vendor.email,
        event_type=Notification.EVENT_SHOW_UPDATE,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )

    for admin in Admin.objects.filter(is_active=True).only("id", "email"):
        _create_notification(
            recipient_role=Notification.ROLE_ADMIN,
            recipient_id=admin.id,
            recipient_email=admin.email,
            event_type=Notification.EVENT_SHOW_UPDATE,
            title=title,
            message=message,
            metadata=metadata,
            send_email_too=True,
        )


def _notify_booking_created(booking: Booking, show: Show) -> None:
    title = "New booking confirmed"
    seat_count = booking.booking_seats.count()
    message = f"Your booking #{booking.id} for {show.movie.title} is confirmed with {seat_count} seat(s)."
    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "show_id": show.id,
            "showtime_id": booking.showtime_id,
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "seat_count": seat_count,
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=booking.user_id,
        recipient_email=booking.user.email,
        event_type=Notification.EVENT_NEW_BOOKING,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )

    vendor_message = f"New booking #{booking.id} received for {show.movie.title} ({seat_count} seat(s))."
    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=show.vendor_id,
        recipient_email=show.vendor.email,
        event_type=Notification.EVENT_NEW_BOOKING,
        title=title,
        message=vendor_message,
        metadata=metadata,
        send_email_too=True,
    )

    for admin in Admin.objects.filter(is_active=True).only("id", "email"):
        _create_notification(
            recipient_role=Notification.ROLE_ADMIN,
            recipient_id=admin.id,
            recipient_email=admin.email,
            event_type=Notification.EVENT_NEW_BOOKING,
            title=title,
            message=vendor_message,
            metadata=metadata,
            send_email_too=True,
        )


def _notify_payment_success(booking: Booking, show: Show) -> None:
    title = "Payment successful"
    message = f"Payment for booking #{booking.id} for {show.movie.title} was completed successfully."
    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "show_id": show.id,
            "showtime_id": booking.showtime_id,
            "amount": float(_quantize_money(booking.total_amount or Decimal("0"))),
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=booking.user_id,
        recipient_email=booking.user.email,
        event_type=Notification.EVENT_PAYMENT_SUCCESS,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )

    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=show.vendor_id,
        recipient_email=show.vendor.email,
        event_type=Notification.EVENT_PAYMENT_SUCCESS,
        title=title,
        message=f"Payment received for booking #{booking.id} ({show.movie.title}).",
        metadata=metadata,
        send_email_too=True,
    )


def _notify_vendor_when_show_fully_booked(
    *,
    show: Show,
    showtime: Showtime,
    screen: Screen,
) -> None:
    capacity = int(screen.capacity or 0) if screen and screen.capacity else 0
    if capacity <= 0:
        return

    sold_count = len(_collect_sold_labels_for_showtime(showtime, lock=False))
    if sold_count < capacity:
        return

    updated_rows = (
        Show.objects.filter(pk=show.id)
        .exclude(status__iexact="Sold Out")
        .update(status="Sold Out")
    )
    if updated_rows == 0:
        return
    show.status = "Sold Out"

    hall = str(screen.screen_number or show.hall or "").strip() or "Hall"
    show_date_text = show.show_date.isoformat() if show.show_date else "-"
    show_time_text = show.start_time.strftime("%H:%M") if show.start_time else "-"
    title = "Show fully booked"
    message = (
        f"{show.movie.title} on {show_date_text} at {show_time_text} in {hall} "
        f"is fully booked ({sold_count}/{capacity} seats)."
    )
    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=show.vendor_id,
        recipient_email=show.vendor.email,
        event_type=Notification.EVENT_SHOW_UPDATE,
        title=title,
        message=message,
        metadata={
            "show_id": show.id,
            "showtime_id": showtime.id,
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "hall": hall,
            "sold_seat_count": sold_count,
            "capacity": capacity,
            "is_fully_booked": True,
        },
        send_email_too=True,
    )


def _resolve_notification_actor(request: Any) -> tuple[Optional[str], Optional[int]]:
    if not is_authenticated(request):
        return None, None

    admin = resolve_admin(request)
    if admin:
        return Notification.ROLE_ADMIN, admin.id

    vendor = resolve_vendor(request)
    if vendor:
        return Notification.ROLE_VENDOR, vendor.id

    customer = resolve_customer(request)
    if customer:
        return Notification.ROLE_CUSTOMER, customer.id

    return None, None


def _ensure_customer_login_offer_notification(user: User) -> None:
    # Disabled: Do not send default offer notification on login
    return


def _notify_customer_cancel_request_rejected(
    booking: Booking,
    *,
    resolved_by: str,
    reason: Optional[str],
) -> None:
    customer = booking.user
    if not customer:
        return

    pending = (
        Notification.objects.filter(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=customer.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=booking.id,
        )
        .order_by("-created_at", "-id")
        .first()
    )

    message = f"Your cancellation request for booking #{booking.id} was rejected by the vendor."
    if reason:
        message = (
            f"Your cancellation request for booking #{booking.id} was rejected by the vendor. "
            f"Reason: {reason}."
        )

    if pending:
        metadata = dict(pending.metadata or {})
        metadata.update(
            {
                "request_status": "REJECTED",
                "resolved_by": resolved_by,
                "resolved_reason": reason,
                "resolved_at": timezone.now().isoformat(),
            }
        )
        pending.title = "Cancellation request rejected"
        pending.message = message
        pending.metadata = metadata
        pending.is_read = False
        pending.read_at = None
        pending.save(update_fields=["title", "message", "metadata", "is_read", "read_at"])
        return

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "request_status": "REJECTED",
            "resolved_by": resolved_by,
            "resolved_reason": reason,
        }
    )
    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        title="Cancellation request rejected",
        message=message,
        metadata=metadata,
        send_email_too=True,
    )


def _notify_customer_cancel_request_submitted(
    booking: Booking,
    *,
    quote: dict[str, Any],
    request_id: int,
) -> None:
    customer = booking.user
    if not customer:
        return

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "request_id": request_id,
            "request_status": "PENDING",
            "request_type": "CANCEL_AND_REFUND",
            "refund_preview": {
                "is_refund_available": bool(quote.get("is_refund_available")),
                "refund_percent": float(quote.get("refund_percent") or 0),
                "refund_amount": float(quote.get("refund_amount") or 0),
                "cancellation_charge_amount": float(quote.get("cancellation_charge_amount") or 0),
                "hours_until_show": quote.get("hours_until_show"),
            },
            "policy": quote.get("policy") or {},
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        title="Cancellation request submitted",
        message=(
            f"Your cancellation request for booking #{booking.id} was sent to the cinema. "
            "You will be notified once the vendor approves refund."
        ),
        metadata=metadata,
        send_email_too=True,
    )


def _notify_customer_booking_cancelled(
    booking: Booking,
    *,
    actor_label: str,
    reason: Optional[str],
) -> None:
    customer = booking.user
    if not customer:
        return

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "processed_by": actor_label,
            "processed_reason": reason,
            "refund_processed": {
                "refund_amount": 0.0,
                "refund_percent": 0.0,
                "cancellation_charge_amount": float(metadata.get("amount_basis") or 0),
                "hours_until_show": None,
                "is_refund_available": False,
            },
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=Notification.EVENT_BOOKING_CANCELLED,
        title="Booking cancelled",
        message=f"Your booking #{booking.id} has been cancelled.",
        metadata=metadata,
        send_email_too=True,
    )


def _notify_vendor_cancel_request(
    booking: Booking,
    *,
    vendor: Vendor,
    quote: dict[str, Any],
    reason: Optional[str],
) -> Notification:
    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "request_status": "PENDING",
            "request_type": "CANCEL_AND_REFUND",
            "requested_by": "customer",
            "requested_reason": reason,
            "refund_preview": {
                "is_refund_available": bool(quote.get("is_refund_available")),
                "refund_percent": float(quote.get("refund_percent") or 0),
                "refund_amount": float(quote.get("refund_amount") or 0),
                "cancellation_charge_amount": float(quote.get("cancellation_charge_amount") or 0),
                "hours_until_show": quote.get("hours_until_show"),
            },
            "policy": quote.get("policy") or {},
        }
    )

    return _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=vendor.id,
        recipient_email=vendor.email,
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        title="Refund request pending approval",
        message=(
            f"Customer requested cancellation/refund for booking #{booking.id}. "
            "Review and process manually from vendor bookings."
        ),
        metadata=metadata,
        send_email_too=True,
    )


def _notify_customer_refund_result(
    booking: Booking,
    *,
    quote: dict[str, Any],
    refund_amount: Decimal,
    actor_label: str,
    reason: Optional[str],
) -> None:
    customer = booking.user
    if not customer:
        return

    refunded = _quantize_money(refund_amount or Decimal("0"))
    charge_amount = _quantize_money(Decimal(str(quote.get("amount_basis") or 0)) - refunded)
    if charge_amount < Decimal("0"):
        charge_amount = Decimal("0")

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "processed_by": actor_label,
            "processed_reason": reason,
            "refund_processed": {
                "refund_amount": float(refunded),
                "refund_percent": float(quote.get("refund_percent") or 0),
                "cancellation_charge_amount": float(charge_amount),
                "hours_until_show": quote.get("hours_until_show"),
                "is_refund_available": bool(refunded > Decimal("0")),
            },
            "policy": quote.get("policy") or {},
        }
    )

    if refunded > Decimal("0"):
        event_type = Notification.EVENT_REFUND_PROCESSED
        title = "Refund processed successfully"
        message = f"Your booking #{booking.id} has been cancelled and refund of NPR {refunded} was processed."
    else:
        event_type = Notification.EVENT_BOOKING_CANCELLED
        title = "Booking cancelled"
        message = f"Your booking #{booking.id} has been cancelled. No refund is applicable under current policy."

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=event_type,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )


def _collect_sold_labels_for_showtime(showtime: Showtime, *, lock: bool = False) -> list[str]:
    queryset = Seat.objects.filter(bookingseat__booking__showtime=showtime)
    if lock:
        queryset = queryset.select_for_update()
    return [
        _seat_label(seat)
        for seat in queryset.distinct().order_by("row_label", "seat_number")
    ]


def list_notifications(request: Any) -> tuple[dict[str, Any], int]:
    actor_role, actor_id = _resolve_notification_actor(request)
    if not actor_role or not actor_id:
        return {"message": "Authentication required"}, status.HTTP_401_UNAUTHORIZED

    unread_only = parse_bool(request.query_params.get("unread"), default=False)
    base_queryset = Notification.objects.filter(
        recipient_role=actor_role,
        recipient_id=actor_id,
    )
    queryset = base_queryset.filter(is_read=False) if unread_only else base_queryset

    try:
        limit = int(request.query_params.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 100))

    notifications = list(queryset[:limit])
    unread_count = base_queryset.filter(is_read=False).count()
    total_count = base_queryset.count()
    return {
        "notifications": [_build_notification_payload(item) for item in notifications],
        "count": len(notifications),
        "total_count": total_count,
        "unread_count": unread_count,
    }, status.HTTP_200_OK


def mark_notifications_read(request: Any) -> tuple[dict[str, Any], int]:
    actor_role, actor_id = _resolve_notification_actor(request)
    if not actor_role or not actor_id:
        return {"message": "Authentication required"}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    mark_all = parse_bool(coalesce(payload, "all", "mark_all", "markAll"), default=False)
    queryset = Notification.objects.filter(
        recipient_role=actor_role,
        recipient_id=actor_id,
    )

    if not mark_all:
        raw_ids = coalesce(payload, "ids", "notification_ids", "notificationIds")
        if not isinstance(raw_ids, list):
            return {
                "message": "Provide ids as a list or set all=true to mark all notifications.",
            }, status.HTTP_400_BAD_REQUEST

        ids: list[int] = []
        for item in raw_ids:
            try:
                parsed = int(item)
            except (TypeError, ValueError):
                parsed = 0
            if parsed > 0:
                ids.append(parsed)
        if not ids:
            return {"message": "No valid notification ids supplied."}, status.HTTP_400_BAD_REQUEST
        queryset = queryset.filter(id__in=ids)

    updated = queryset.update(is_read=True, read_at=timezone.now())
    return {
        "message": "Notifications marked as read",
        "updated": updated,
    }, status.HTTP_200_OK


def _queue_notification_email(*, subject: str, message: str, recipient_email: Optional[str]) -> None:
    if not recipient_email:
        return
    from . import _enqueue_background_job
    from . import enqueue_notification_email_retry_job
    from . import _send_notification_email

    if _send_notification_email(
        subject=subject,
        message=message,
        recipient_email=recipient_email,
        html_message=None,
    ):
        return

    queued_job = _enqueue_background_job(
        job_type=BackgroundJob.TYPE_NOTIFICATION_EMAIL,
        payload={
            "subject": str(subject or "").strip(),
            "message": str(message or "").strip(),
            "recipient_email": str(recipient_email).strip(),
            "html_message": None,
        },
        max_attempts=3,
    )
    if queued_job:
        return

    retry_job = enqueue_notification_email_retry_job(
        subject=subject,
        message=message,
        recipient_email=recipient_email,
        html_message=None,
        metadata={"fallback": "primary_enqueue_failed"},
    )
    if retry_job:
        return
