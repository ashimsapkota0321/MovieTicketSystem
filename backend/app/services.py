"""Service layer helpers and business logic."""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import random
import re
import uuid
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db import IntegrityError
from django.db.models import Q, Count, Sum, F, DecimalField, Avg, Max, Min
from django.utils import timezone
from django.utils.html import escape
from PIL import Image, ImageDraw, ImageFont
from rest_framework import status

from .models import (
    User,
    Admin,
    Vendor,
    VendorStaff,
    Movie,
    Person,
    MovieCredit,
    Show,
    Banner,
    HomeSlide,
    Collaborator,
    OTPVerification,
    Ticket,
    Screen,
    Seat,
    Showtime,
    PricingRule,
    SeatAvailability,
    Coupon,
    Booking,
    BookingSeat,
    BulkTicketBatch,
    BulkTicketItem,
    Payment,
    PrivateScreeningRequest,
    Refund,
    Wallet,
    Transaction,
    FoodItem,
    BookingFoodItem,
    Notification,
    VendorPromoCode,
    VendorCampaign,
    VendorCampaignDispatch,
    VendorCancellationPolicy,
)
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileUpdateSerializer,
    AdminProfileUpdateSerializer,
    VendorProfileUpdateSerializer,
    generate_unique_username,
    HomeSlideAdminSerializer,
    CollabDetailsAdminSerializer,
    CollaboratorAdminSerializer,
    BannerCreateUpdateSerializer,
)
from .permissions import (
    is_admin_request,
    is_authenticated,
    issue_access_token,
    resolve_admin,
    resolve_customer,
    resolve_vendor,
)
from . import selectors
from .selectors import build_movie_payload, build_show_payload, get_ticket
from .utils import (
    coalesce,
    get_payload,
    get_profile_image_url,
    is_phone_like,
    normalize_phone_number,
    parse_date,
    parse_time,
    parse_bool,
    request_data_to_dict,
    short_label,
    slugify_text,
)

logger = logging.getLogger(__name__)

PHONE_REGEX = re.compile(r"^[0-9]{10,13}$")
DEFAULT_VENDOR_STATUS = "Active"
STATUS_BLOCKED = "Blocked"
AUTH_REQUIRED_MESSAGE = "Authentication required"
ADMIN_REQUIRED_MESSAGE = "Admin access required"
INVALID_PHONE_MESSAGE = "Invalid phone number format"
SEAT_STATUS_SOLD = "Sold"
SEAT_STATUS_BOOKED = "Booked"
SEAT_STATUS_AVAILABLE = "Available"
SEAT_STATUS_UNAVAILABLE = "Unavailable"
SEAT_STATUS_RESERVED = "Reserved"
BOOKING_STATUS_PENDING = "Pending"
BOOKING_STATUS_CONFIRMED = "Confirmed"
BOOKING_STATUS_CANCELLED = "Cancelled"
ESEWA_PAYMENT_METHOD_PREFIX = "ESEWA:"
DEFAULT_GUEST_EMAIL = "guest.booking@meroticket.local"
DEFAULT_GUEST_NAME = "Guest"
SEAT_CATEGORY_NORMAL = "Normal"
SEAT_CATEGORY_EXECUTIVE = "Executive"
SEAT_CATEGORY_PREMIUM = "Premium"
SEAT_CATEGORY_VIP = "VIP"
SEAT_CATEGORY_ORDER = [
    SEAT_CATEGORY_NORMAL,
    SEAT_CATEGORY_EXECUTIVE,
    SEAT_CATEGORY_PREMIUM,
    SEAT_CATEGORY_VIP,
]
SEAT_CATEGORY_KEYS = {
    SEAT_CATEGORY_NORMAL: "normal",
    SEAT_CATEGORY_EXECUTIVE: "executive",
    SEAT_CATEGORY_PREMIUM: "premium",
    SEAT_CATEGORY_VIP: "vip",
}
SEAT_CATEGORY_RULE_VALUES = {
    SEAT_CATEGORY_NORMAL: PricingRule.SEAT_CATEGORY_NORMAL,
    SEAT_CATEGORY_EXECUTIVE: PricingRule.SEAT_CATEGORY_EXECUTIVE,
    SEAT_CATEGORY_PREMIUM: PricingRule.SEAT_CATEGORY_PREMIUM,
    SEAT_CATEGORY_VIP: PricingRule.SEAT_CATEGORY_VIP,
}
SEAT_CATEGORY_SCREEN_FIELDS = {
    "normal": "normal_price",
    "executive": "executive_price",
    "premium": "premium_price",
    "vip": "vip_price",
}
BOOKED_STATUSES = {SEAT_STATUS_BOOKED.lower(), SEAT_STATUS_SOLD.lower()}
RESERVE_HOLD_MINUTES = 10
BOOKING_RESUME_NOTICE_WINDOW_MINUTES = RESERVE_HOLD_MINUTES
PLATFORM_COMMISSION_PERCENT = Decimal("10.00")
WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DEFAULT_REFUND_PERCENT_2H_PLUS = Decimal("100.00")
DEFAULT_REFUND_PERCENT_1_TO_2H = Decimal("70.00")
DEFAULT_REFUND_PERCENT_LESS_THAN_1H = Decimal("0.00")


def _normalize_show_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"", "open", "booking_open", "upcoming"}:
        return Show.STATUS_UPCOMING
    if raw in {"running", "live"}:
        return Show.STATUS_RUNNING
    if raw in {"completed", "closed", "ended"}:
        return Show.STATUS_COMPLETED
    return Show.STATUS_UPCOMING


def _ensure_show_is_bookable(show: Show) -> tuple[Optional[dict[str, Any]], Optional[int]]:
    """Return an error payload when booking is closed for the show lifecycle window."""
    selectors.sync_show_lifecycle_statuses()
    show.refresh_from_db(fields=["status", "show_date", "start_time", "end_time"])
    lifecycle = selectors.get_show_lifecycle_state(show)
    if lifecycle["status"] == selectors.SHOW_STATUS_COMPLETED:
        return {"message": "This show is completed. Booking is no longer available."}, status.HTTP_400_BAD_REQUEST
    if lifecycle["status"] == selectors.SHOW_STATUS_RUNNING:
        return {"message": "This show is already running. Booking is closed."}, status.HTTP_400_BAD_REQUEST
    if not lifecycle.get("booking_open"):
        return {
            "message": "Booking closes 30 minutes before show start time.",
            "booking_close_at": lifecycle["booking_close_at"].isoformat()
            if lifecycle.get("booking_close_at")
            else None,
        }, status.HTTP_400_BAD_REQUEST
    return None, None


def _send_notification_email(subject: str, message: str, recipient_email: Optional[str]) -> bool:
    """Send a notification email and return whether delivery was attempted successfully."""
    email = str(recipient_email or "").strip()
    if not email:
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@meroticket.local"
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[email],
            fail_silently=True,
        )
        return True
    except Exception:
        logger.exception("Failed to send notification email to %s", email)
        return False


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
    """Persist in-app notification and optionally send matching email."""
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
        _send_notification_email(title, message, recipient_email)

    return notification


def _build_notification_payload(notification: Notification) -> dict[str, Any]:
    """Serialize a notification for API responses."""
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


def _notify_show_update(
    *,
    vendor: Vendor,
    movie: Movie,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Send show update notifications to the owner vendor and active admins."""
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
    """Send booking-created notifications to customer, vendor, and admins."""
    title = "New booking confirmed"
    seat_count = booking.booking_seats.count()
    message = (
        f"Your booking #{booking.id} for {show.movie.title} is confirmed with {seat_count} seat(s)."
    )
    metadata = _build_booking_notification_metadata(
        booking,
        include_booking_detail=True,
    )
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

    vendor_message = (
        f"New booking #{booking.id} received for {show.movie.title} ({seat_count} seat(s))."
    )
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


def _find_ticket_reference_for_booking(booking_id: int) -> Optional[str]:
    """Return the latest ticket reference linked to the given booking id."""
    if booking_id <= 0:
        return None

    # Use JSON lookup first; if unsupported by the DB backend, scan recent rows.
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
        payload_booking_id = _coerce_int(coalesce(booking_payload, "booking_id", "id"))
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
    amount_basis = _booking_amount_for_refund(booking, latest_payment=latest_payment)
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
        "show_start_time": showtime.start_time.isoformat()
        if showtime and showtime.start_time
        else None,
        "show_end_time": showtime.end_time.isoformat()
        if showtime and showtime.end_time
        else None,
        "movie_id": movie.id if movie else None,
        "movie_title": movie.title if movie else None,
        "vendor_id": vendor.id if vendor else None,
        "vendor_name": vendor.name if vendor else None,
        "screen_id": screen.id if screen else None,
        "screen_number": screen.screen_number if screen else None,
        "seats": seat_labels,
        "seat_count": len(seat_labels),
        "amount_basis": float(_quantize_money(amount_basis)),
        "payment": {
            "id": latest_payment.id if latest_payment else None,
            "status": latest_payment.payment_status if latest_payment else None,
            "method": latest_payment.payment_method if latest_payment else None,
            "amount": float(_quantize_money(latest_payment.amount or Decimal("0")))
            if latest_payment
            else 0.0,
            "paid_at": latest_payment.payment_date.isoformat()
            if latest_payment and latest_payment.payment_date
            else None,
        },
        "refund": {
            "id": latest_refund.id if latest_refund else None,
            "status": latest_refund.refund_status if latest_refund else None,
            "amount": float(_quantize_money(latest_refund.refund_amount or Decimal("0")))
            if latest_refund
            else 0.0,
            "reason": latest_refund.refund_reason if latest_refund else None,
            "refunded_at": latest_refund.refund_date.isoformat()
            if latest_refund and latest_refund.refund_date
            else None,
        },
        "ticket_reference": _find_ticket_reference_for_booking(booking.id),
    }

    if include_booking_detail:
        metadata["booking_detail"] = build_booking_detail_payload(booking)

    return metadata


def _notify_payment_success(booking: Booking, show: Show) -> None:
    """Send payment success notifications for a booking."""
    title = "Payment successful"
    message = (
        f"Payment for booking #{booking.id} for {show.movie.title} was completed successfully."
    )
    metadata = _build_booking_notification_metadata(
        booking,
        include_booking_detail=True,
    )
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
    *, show: Show, showtime: Showtime, screen: Screen
) -> None:
    """Notify vendor once when a show reaches full seat capacity."""
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
    """Resolve notification actor role and ID from authenticated request."""
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
    """Create one daily in-app offer notice for a customer after successful login."""
    if not user or not getattr(user, "id", None):
        return

    now = timezone.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    exists = Notification.objects.filter(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=user.id,
        event_type=Notification.EVENT_MARKETING_CAMPAIGN,
        metadata__notice_key="LOGIN_OFFER",
        created_at__gte=start_of_day,
    ).exists()
    if exists:
        return

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=user.id,
        recipient_email=user.email,
        event_type=Notification.EVENT_MARKETING_CAMPAIGN,
        title="New offers available",
        message="Check the latest movie offers and promo campaigns near you.",
        metadata={
            "notice_key": "LOGIN_OFFER",
            "source": "customer_login",
            "date": now.date().isoformat(),
        },
        send_email_too=False,
    )


def list_notifications(request: Any) -> tuple[dict[str, Any], int]:
    """List notifications scoped to the authenticated actor."""
    actor_role, actor_id = _resolve_notification_actor(request)
    if not actor_role or not actor_id:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

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
    """Mark one, many, or all scoped notifications as read."""
    actor_role, actor_id = _resolve_notification_actor(request)
    if not actor_role or not actor_id:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

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
            parsed = _coerce_int(item)
            if parsed and parsed > 0:
                ids.append(parsed)
        if not ids:
            return {"message": "At least one valid notification id is required."}, status.HTTP_400_BAD_REQUEST
        queryset = queryset.filter(id__in=ids)

    now = timezone.now()
    updated = queryset.filter(is_read=False).update(is_read=True, read_at=now)
    unread_count = Notification.objects.filter(
        recipient_role=actor_role,
        recipient_id=actor_id,
        is_read=False,
    ).count()

    return {
        "message": "Notifications updated.",
        "updated": int(updated),
        "unread_count": int(unread_count),
    }, status.HTTP_200_OK


def _quantize_money(value: Decimal) -> Decimal:
    """Normalize decimal amounts to 2 decimal places."""
    return (value if isinstance(value, Decimal) else Decimal(str(value or 0))).quantize(Decimal("0.01"))


def _resolve_vendor_commission_percent(vendor: Optional[Vendor]) -> Decimal:
    """Resolve effective commission percent from vendor override or global setting."""
    default_raw = getattr(settings, "PLATFORM_COMMISSION_PERCENT", PLATFORM_COMMISSION_PERCENT)
    try:
        default_percent = Decimal(str(default_raw))
    except (TypeError, ValueError, InvalidOperation):
        default_percent = PLATFORM_COMMISSION_PERCENT

    vendor_percent = getattr(vendor, "commission_percent", None) if vendor else None
    try:
        effective = Decimal(str(vendor_percent)) if vendor_percent is not None else default_percent
    except (TypeError, ValueError, InvalidOperation):
        effective = default_percent

    if effective < Decimal("0"):
        effective = Decimal("0")
    if effective > Decimal("100"):
        effective = Decimal("100")
    return _quantize_money(effective)


def _wallet_for_vendor(vendor: Vendor) -> Wallet:
    """Get or create vendor wallet."""
    wallet, _ = Wallet.objects.get_or_create(vendor=vendor)
    return wallet


def _pending_withdrawal_total(wallet: Wallet) -> Decimal:
    """Calculate pending withdrawal requests total for a wallet."""
    pending = wallet.transactions.filter(
        transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST,
        status=Transaction.STATUS_PENDING,
    ).aggregate(total=Sum("amount"))
    return _quantize_money(pending.get("total") or Decimal("0"))


def _record_vendor_booking_earning(booking: Booking, gross_amount: Optional[Decimal] = None) -> None:
    """Credit vendor wallet for a booking after platform commission deduction."""
    showtime = booking.showtime
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    if not vendor:
        return

    existing = Transaction.objects.filter(
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_EARNING,
    ).exists()
    if existing:
        return

    gross = _quantize_money(gross_amount if gross_amount is not None else booking.total_amount or Decimal("0"))
    commission_percent = _resolve_vendor_commission_percent(vendor)
    commission = _quantize_money((gross * commission_percent) / Decimal("100"))
    net = _quantize_money(gross - commission)

    wallet = _wallet_for_vendor(vendor)
    wallet.balance = _quantize_money((wallet.balance or Decimal("0")) + net)
    wallet.total_earnings = _quantize_money((wallet.total_earnings or Decimal("0")) + gross)
    wallet.total_commission = _quantize_money((wallet.total_commission or Decimal("0")) + commission)
    wallet.save(update_fields=["balance", "total_earnings", "total_commission", "updated_at"])

    Transaction.objects.create(
        wallet=wallet,
        vendor=vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_EARNING,
        amount=net,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Booking #{booking.id} earning",
    )
    Transaction.objects.create(
        wallet=wallet,
        vendor=vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_PLATFORM_COMMISSION,
        amount=commission,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Platform commission for booking #{booking.id}",
    )


def _reverse_vendor_booking_earning(booking: Booking, *, reason: Optional[str] = None) -> None:
    """Reverse wallet earning + commission for a refunded/cancelled booking once."""
    earning_txn = (
        Transaction.objects.select_for_update()
        .filter(
            booking=booking,
            transaction_type=Transaction.TYPE_BOOKING_EARNING,
            status=Transaction.STATUS_COMPLETED,
        )
        .order_by("-id")
        .first()
    )
    if not earning_txn:
        return

    already_reversed = Transaction.objects.filter(
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_REVERSAL,
        status=Transaction.STATUS_COMPLETED,
    ).exists()
    if already_reversed:
        return

    wallet = Wallet.objects.select_for_update().filter(id=earning_txn.wallet_id).first()
    if not wallet:
        return

    net = _quantize_money(earning_txn.amount or Decimal("0"))
    gross = _quantize_money(earning_txn.gross_amount or Decimal("0"))
    commission = _quantize_money(earning_txn.commission_amount or Decimal("0"))

    wallet.balance = _quantize_money((wallet.balance or Decimal("0")) - net)
    wallet.total_earnings = _quantize_money((wallet.total_earnings or Decimal("0")) - gross)
    wallet.total_commission = _quantize_money((wallet.total_commission or Decimal("0")) - commission)
    if wallet.balance < Decimal("0"):
        wallet.balance = Decimal("0")
    if wallet.total_earnings < Decimal("0"):
        wallet.total_earnings = Decimal("0")
    if wallet.total_commission < Decimal("0"):
        wallet.total_commission = Decimal("0")
    wallet.save(update_fields=["balance", "total_earnings", "total_commission", "updated_at"])

    description_suffix = f" ({reason})" if reason else ""
    Transaction.objects.create(
        wallet=wallet,
        vendor=earning_txn.vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_REVERSAL,
        amount=net,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Booking #{booking.id} earning reversed{description_suffix}",
    )
    Transaction.objects.create(
        wallet=wallet,
        vendor=earning_txn.vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_PLATFORM_COMMISSION_REVERSAL,
        amount=commission,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Platform commission reversed for booking #{booking.id}{description_suffix}",
    )


def get_vendor_wallet_balance(request: Any) -> tuple[dict[str, Any], int]:
    """Return wallet balance and summary for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    wallet = _wallet_for_vendor(vendor)
    pending_withdrawal = _pending_withdrawal_total(wallet)
    available = _quantize_money((wallet.balance or Decimal("0")) - pending_withdrawal)
    if available < Decimal("0"):
        available = Decimal("0")
    commission_percent = _resolve_vendor_commission_percent(vendor)

    return {
        "vendor_id": vendor.id,
        "wallet": {
            "balance": float(_quantize_money(wallet.balance or Decimal("0"))),
            "available_balance": float(available),
            "pending_withdrawals": float(pending_withdrawal),
            "total_earnings": float(_quantize_money(wallet.total_earnings or Decimal("0"))),
            "total_commission": float(_quantize_money(wallet.total_commission or Decimal("0"))),
            "total_withdrawn": float(_quantize_money(wallet.total_withdrawn or Decimal("0"))),
            "platform_commission_percent": float(commission_percent),
        },
    }, status.HTTP_200_OK


def create_vendor_withdrawal_request(request: Any) -> tuple[dict[str, Any], int]:
    """Create a withdrawal request for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    amount = _parse_price_amount(coalesce(payload, "amount", "withdraw_amount", "withdrawAmount"))
    if amount is None or amount <= Decimal("0"):
        return {"message": "Valid amount is required."}, status.HTTP_400_BAD_REQUEST

    wallet = _wallet_for_vendor(vendor)
    pending_withdrawal = _pending_withdrawal_total(wallet)
    available = _quantize_money((wallet.balance or Decimal("0")) - pending_withdrawal)
    if amount > available:
        return {
            "message": "Insufficient withdrawable balance.",
            "available_balance": float(max(available, Decimal("0"))),
        }, status.HTTP_400_BAD_REQUEST

    note = str(coalesce(payload, "note", "description", "remark") or "").strip() or None
    txn = Transaction.objects.create(
        wallet=wallet,
        vendor=vendor,
        transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST,
        amount=_quantize_money(amount),
        commission_amount=Decimal("0.00"),
        gross_amount=_quantize_money(amount),
        status=Transaction.STATUS_PENDING,
        description=note or "Withdrawal request",
    )

    return {
        "message": "Withdrawal request submitted.",
        "transaction": {
            "id": txn.id,
            "type": txn.transaction_type,
            "status": txn.status,
            "amount": float(txn.amount),
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
            "description": txn.description,
        },
    }, status.HTTP_201_CREATED


def list_vendor_wallet_transactions(request: Any) -> tuple[dict[str, Any], int]:
    """List authenticated vendor wallet transactions."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    wallet = _wallet_for_vendor(vendor)
    transactions = wallet.transactions.all().order_by("-created_at", "-id")
    tx_type = str(coalesce(request.query_params, "type", "transaction_type") or "").strip().upper()
    tx_status = str(coalesce(request.query_params, "status") or "").strip().upper()
    if tx_type:
        transactions = transactions.filter(transaction_type=tx_type)
    if tx_status:
        transactions = transactions.filter(status=tx_status)

    payload = []
    for txn in transactions[:200]:
        payload.append(
            {
                "id": txn.id,
                "type": txn.transaction_type,
                "status": txn.status,
                "amount": float(_quantize_money(txn.amount or Decimal("0"))),
                "gross_amount": float(_quantize_money(txn.gross_amount or Decimal("0"))),
                "commission_amount": float(_quantize_money(txn.commission_amount or Decimal("0"))),
                "booking_id": txn.booking_id,
                "vendor_id": txn.vendor_id,
                "description": txn.description,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
            }
        )

    return {"transactions": payload}, status.HTTP_200_OK


def list_admin_withdrawal_requests(request: Any) -> tuple[dict[str, Any], int]:
    """List withdrawal request transactions for admin review."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    queryset = Transaction.objects.filter(
        transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST,
    ).select_related("vendor", "wallet").order_by("-created_at", "-id")

    status_filter = str(coalesce(request.query_params, "status") or "").strip().upper()
    if status_filter in {Transaction.STATUS_PENDING, Transaction.STATUS_COMPLETED, Transaction.STATUS_REJECTED}:
        queryset = queryset.filter(status=status_filter)

    items = []
    for txn in queryset[:500]:
        items.append(
            {
                "id": txn.id,
                "vendor_id": txn.vendor_id,
                "vendor_name": txn.vendor.name if txn.vendor else None,
                "status": txn.status,
                "amount": float(_quantize_money(txn.amount or Decimal("0"))),
                "description": txn.description,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
            }
        )
    return {"withdrawals": items}, status.HTTP_200_OK


def _process_admin_withdrawal(
    request: Any,
    withdrawal_txn: Transaction,
    *,
    approve: bool,
) -> tuple[dict[str, Any], int]:
    """Approve or reject a pending vendor withdrawal request."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN
    if withdrawal_txn.transaction_type != Transaction.TYPE_WITHDRAWAL_REQUEST:
        return {"message": "Transaction is not a withdrawal request."}, status.HTTP_400_BAD_REQUEST

    with transaction.atomic():
        locked = (
            Transaction.objects.select_for_update()
            .select_related("wallet", "vendor")
            .filter(id=withdrawal_txn.id)
            .first()
        )
        if not locked:
            return {"message": "Withdrawal request not found."}, status.HTTP_404_NOT_FOUND
        if locked.status != Transaction.STATUS_PENDING:
            return {
                "message": "Withdrawal request already processed.",
                "status": locked.status,
            }, status.HTTP_400_BAD_REQUEST

        wallet = Wallet.objects.select_for_update().filter(id=locked.wallet_id).first()
        if not wallet:
            return {"message": "Wallet not found for withdrawal request."}, status.HTTP_404_NOT_FOUND

        payload = get_payload(request)
        note = str(coalesce(payload, "reason", "note", "description") or "").strip()
        amount = _quantize_money(locked.amount or Decimal("0"))

        if approve:
            pending_total = _pending_withdrawal_total(wallet)
            available = _quantize_money((wallet.balance or Decimal("0")) - pending_total + amount)
            if amount > available:
                return {"message": "Insufficient balance to approve this withdrawal."}, status.HTTP_400_BAD_REQUEST

            wallet.balance = _quantize_money((wallet.balance or Decimal("0")) - amount)
            if wallet.balance < Decimal("0"):
                wallet.balance = Decimal("0")
            wallet.total_withdrawn = _quantize_money((wallet.total_withdrawn or Decimal("0")) + amount)
            wallet.save(update_fields=["balance", "total_withdrawn", "updated_at"])

            locked.status = Transaction.STATUS_COMPLETED
            if note:
                locked.description = f"{locked.description or 'Withdrawal request'} | Approved: {note}"
            locked.save(update_fields=["status", "description"])

            Transaction.objects.create(
                wallet=wallet,
                vendor=locked.vendor,
                transaction_type=Transaction.TYPE_WITHDRAWAL_APPROVED,
                amount=amount,
                commission_amount=Decimal("0.00"),
                gross_amount=amount,
                status=Transaction.STATUS_COMPLETED,
                description=f"Withdrawal approved for request #{locked.id}",
            )

            return {
                "message": "Withdrawal approved.",
                "transaction_id": locked.id,
                "status": locked.status,
                "amount": float(amount),
            }, status.HTTP_200_OK

        locked.status = Transaction.STATUS_REJECTED
        if note:
            locked.description = f"{locked.description or 'Withdrawal request'} | Rejected: {note}"
        locked.save(update_fields=["status", "description"])
        Transaction.objects.create(
            wallet=wallet,
            vendor=locked.vendor,
            transaction_type=Transaction.TYPE_WITHDRAWAL_REJECTED,
            amount=amount,
            commission_amount=Decimal("0.00"),
            gross_amount=amount,
            status=Transaction.STATUS_REJECTED,
            description=f"Withdrawal rejected for request #{locked.id}",
        )
        return {
            "message": "Withdrawal rejected.",
            "transaction_id": locked.id,
            "status": locked.status,
            "amount": float(amount),
        }, status.HTTP_200_OK


def approve_admin_withdrawal_request(request: Any, withdrawal_txn: Transaction) -> tuple[dict[str, Any], int]:
    return _process_admin_withdrawal(request, withdrawal_txn, approve=True)


def reject_admin_withdrawal_request(request: Any, withdrawal_txn: Transaction) -> tuple[dict[str, Any], int]:
    return _process_admin_withdrawal(request, withdrawal_txn, approve=False)


def _normalize_coupon_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _serialize_coupon(coupon: Coupon) -> dict[str, Any]:
    return {
        "id": coupon.id,
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "discount_value": float(_quantize_money(coupon.discount_value or Decimal("0"))),
        "min_booking_amount": float(
            _quantize_money(coupon.min_booking_amount or Decimal("0"))
        ),
        "expiry_date": coupon.expiry_date.isoformat() if coupon.expiry_date else None,
        "usage_limit": coupon.usage_limit,
        "usage_count": coupon.usage_count,
        "is_active": bool(coupon.is_active),
        "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
    }


def _serialize_vendor_promo_code(promo: VendorPromoCode) -> dict[str, Any]:
    return {
        "id": promo.id,
        "vendor_id": promo.vendor_id,
        "code": promo.code,
        "title": promo.title,
        "description": promo.description,
        "discount_type": promo.discount_type,
        "discount_value": float(_quantize_money(promo.discount_value or Decimal("0"))),
        "min_booking_amount": float(_quantize_money(promo.min_booking_amount or Decimal("0"))),
        "max_discount_amount": float(_quantize_money(promo.max_discount_amount or Decimal("0")))
        if promo.max_discount_amount is not None
        else None,
        "usage_limit": promo.usage_limit,
        "usage_count": promo.usage_count,
        "per_user_limit": promo.per_user_limit,
        "seat_category_scope": promo.seat_category_scope,
        "requires_student": bool(promo.requires_student),
        "allowed_weekdays": _parse_allowed_weekdays(promo.allowed_weekdays),
        "valid_from": promo.valid_from.isoformat() if promo.valid_from else None,
        "valid_until": promo.valid_until.isoformat() if promo.valid_until else None,
        "is_flash_sale": bool(promo.is_flash_sale),
        "is_active": bool(promo.is_active),
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
    }


def _serialize_vendor_campaign(campaign: VendorCampaign) -> dict[str, Any]:
    return {
        "id": campaign.id,
        "vendor_id": campaign.vendor_id,
        "name": campaign.name,
        "message_template": campaign.message_template,
        "delivery_channel": campaign.delivery_channel,
        "status": campaign.status,
        "target_movie_id": campaign.target_movie_id,
        "recommended_movie_id": campaign.recommended_movie_id,
        "promo_code_id": campaign.promo_code_id,
        "promo_code": campaign.promo_code.code if campaign.promo_code_id and campaign.promo_code else None,
        "include_past_attendees_only": bool(campaign.include_past_attendees_only),
        "min_days_since_booking": int(campaign.min_days_since_booking or 0),
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "last_run_at": campaign.last_run_at.isoformat() if campaign.last_run_at else None,
        "sent_count": int(campaign.sent_count or 0),
        "failed_count": int(campaign.failed_count or 0),
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }


def _serialize_vendor_campaign_dispatch(dispatch: VendorCampaignDispatch) -> dict[str, Any]:
    return {
        "id": dispatch.id,
        "campaign_id": dispatch.campaign_id,
        "user_id": dispatch.user_id,
        "channel": dispatch.channel,
        "contact": dispatch.contact,
        "status": dispatch.status,
        "error_message": dispatch.error_message,
        "sent_at": dispatch.sent_at.isoformat() if dispatch.sent_at else None,
    }


def _parse_allowed_weekdays(value: Any) -> list[str]:
    text = str(value or "").strip().upper()
    if not text:
        return []
    output = []
    for token in re.split(r"[\s,;|]+", text):
        token = token.strip().upper()
        if token in WEEKDAY_CODES and token not in output:
            output.append(token)
    return output


def _parse_coupon_expiry(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed_date = parse_date(text)
        if not parsed_date:
            return None
        parsed = datetime.combine(parsed_date, time_cls.max)
    if getattr(settings, "USE_TZ", False) and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_datetime_value(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if getattr(settings, "USE_TZ", False) and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _resolve_vendor_id_from_discount_context(context: Optional[dict[str, Any]]) -> Optional[int]:
    if not isinstance(context, dict):
        return None

    vendor_id = _coerce_int(coalesce(context, "vendor_id", "vendorId", "cinema_id", "cinemaId"))
    if vendor_id:
        return vendor_id

    show_id = _coerce_int(coalesce(context, "show_id", "showId"))
    if show_id:
        show = Show.objects.filter(id=show_id).only("vendor_id").first()
        if show:
            return show.vendor_id

    showtime_id = _coerce_int(coalesce(context, "showtime_id", "showtimeId"))
    if showtime_id:
        showtime = Showtime.objects.select_related("screen").filter(id=showtime_id).first()
        if showtime and showtime.screen:
            return showtime.screen.vendor_id

    return None


def _resolve_discount_context_weekday(context: Optional[dict[str, Any]]) -> str:
    base_time = timezone.localtime(timezone.now())
    if isinstance(context, dict):
        show_date = parse_date(coalesce(context, "show_date", "showDate", "date"))
        if show_date:
            try:
                weekday_idx = show_date.weekday()
                return WEEKDAY_CODES[weekday_idx]
            except Exception:
                pass
    return WEEKDAY_CODES[base_time.weekday()]


def _normalize_seat_categories(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized = []
    for raw in values:
        text = str(raw or "").strip().upper()
        if not text:
            continue
        if text.startswith("EXEC"):
            text = VendorPromoCode.SEAT_CATEGORY_EXECUTIVE
        elif text.startswith("PREM"):
            text = VendorPromoCode.SEAT_CATEGORY_PREMIUM
        elif text.startswith("VIP"):
            text = VendorPromoCode.SEAT_CATEGORY_VIP
        else:
            text = VendorPromoCode.SEAT_CATEGORY_NORMAL
        if text not in normalized:
            normalized.append(text)
    return normalized


def _vendor_promo_discount_for_amount(
    promo: VendorPromoCode,
    subtotal: Decimal,
    seat_count: int,
) -> Decimal:
    subtotal = _quantize_money(subtotal)
    if subtotal <= Decimal("0"):
        return Decimal("0.00")

    if promo.discount_type == VendorPromoCode.DISCOUNT_TYPE_PERCENTAGE:
        discount = _quantize_money(
            (subtotal * _quantize_money(promo.discount_value or Decimal("0"))) / Decimal("100")
        )
    elif promo.discount_type == VendorPromoCode.DISCOUNT_TYPE_FIXED:
        discount = _quantize_money(promo.discount_value or Decimal("0"))
    else:
        if seat_count < 2:
            return Decimal("0.00")
        average_seat_price = _quantize_money(subtotal / Decimal(max(seat_count, 1)))
        free_seat_count = int(seat_count // 2)
        discount = _quantize_money(average_seat_price * Decimal(free_seat_count))

    if promo.max_discount_amount is not None:
        max_discount = _quantize_money(promo.max_discount_amount or Decimal("0"))
        if discount > max_discount:
            discount = max_discount
    if discount > subtotal:
        discount = subtotal
    return discount


def _validate_vendor_promo_for_subtotal(
    coupon_code: Any,
    subtotal: Decimal,
    *,
    context: Optional[dict[str, Any]] = None,
    lock_for_update: bool = False,
) -> tuple[Optional[VendorPromoCode], Optional[dict[str, Any]], int]:
    code = _normalize_coupon_code(coupon_code)
    if not code:
        return None, {"message": "coupon_code is required."}, status.HTTP_400_BAD_REQUEST

    vendor_id = _resolve_vendor_id_from_discount_context(context)
    if not vendor_id:
        return None, {"message": "Promo code requires vendor booking context."}, status.HTTP_400_BAD_REQUEST

    queryset = VendorPromoCode.objects.filter(vendor_id=vendor_id, code__iexact=code)
    if lock_for_update:
        queryset = queryset.select_for_update()
    promo = queryset.first()
    if not promo:
        return None, {"message": "Promo code not found for this cinema."}, status.HTTP_404_NOT_FOUND

    if not promo.is_active:
        return None, {"message": "Promo code is inactive."}, status.HTTP_400_BAD_REQUEST

    now = timezone.now()
    if promo.valid_from and promo.valid_from > now:
        return None, {"message": "Promo code is not active yet."}, status.HTTP_400_BAD_REQUEST
    if promo.valid_until and promo.valid_until < now:
        return None, {"message": "Promo code has expired."}, status.HTTP_400_BAD_REQUEST

    if promo.usage_limit is not None and promo.usage_count >= promo.usage_limit:
        return None, {"message": "Promo usage limit reached."}, status.HTTP_400_BAD_REQUEST

    normalized_subtotal = _quantize_money(subtotal)
    min_amount = _quantize_money(promo.min_booking_amount or Decimal("0"))
    if normalized_subtotal < min_amount:
        return (
            None,
            {
                "message": "Order amount does not meet promo minimum requirement.",
                "min_booking_amount": float(min_amount),
            },
            status.HTTP_400_BAD_REQUEST,
        )

    weekday_filters = _parse_allowed_weekdays(promo.allowed_weekdays)
    weekday_code = _resolve_discount_context_weekday(context)
    if weekday_filters and weekday_code not in weekday_filters:
        return None, {"message": "Promo code is not valid for this day."}, status.HTTP_400_BAD_REQUEST

    seat_categories = _normalize_seat_categories(coalesce(context or {}, "seat_categories", "seatCategories", default=[]))
    if promo.seat_category_scope != VendorPromoCode.SEAT_CATEGORY_ALL:
        if not seat_categories or promo.seat_category_scope not in seat_categories:
            return (
                None,
                {"message": "Promo code is not valid for selected seat category."},
                status.HTTP_400_BAD_REQUEST,
            )

    is_student = bool(parse_bool(coalesce(context or {}, "is_student", "isStudent"), default=False))
    if promo.requires_student and not is_student:
        return None, {"message": "Promo code is only valid for student bookings."}, status.HTTP_400_BAD_REQUEST

    user_id = _coerce_int(coalesce(context or {}, "user_id", "userId"))
    if promo.per_user_limit is not None and user_id:
        used_count = Booking.objects.filter(user_id=user_id, vendor_promo_code_id=promo.id).count()
        if used_count >= promo.per_user_limit:
            return None, {"message": "Per-user promo limit reached."}, status.HTTP_400_BAD_REQUEST

    return promo, None, status.HTTP_200_OK


def _coupon_discount_for_amount(coupon: Coupon, subtotal: Decimal) -> Decimal:
    subtotal = _quantize_money(subtotal)
    if subtotal <= Decimal("0"):
        return Decimal("0.00")

    if coupon.discount_type == Coupon.DISCOUNT_TYPE_PERCENTAGE:
        discount = _quantize_money(
            (subtotal * _quantize_money(coupon.discount_value or Decimal("0")))
            / Decimal("100")
        )
    else:
        discount = _quantize_money(coupon.discount_value or Decimal("0"))
    if discount > subtotal:
        discount = subtotal
    return discount


def _validate_coupon_for_subtotal(
    coupon_code: Any,
    subtotal: Decimal,
    *,
    lock_for_update: bool = False,
) -> tuple[Optional[Coupon], Optional[dict[str, Any]], int]:
    code = _normalize_coupon_code(coupon_code)
    if not code:
        return None, {"message": "coupon_code is required."}, status.HTTP_400_BAD_REQUEST

    queryset = Coupon.objects.filter(code__iexact=code)
    if lock_for_update:
        queryset = queryset.select_for_update()
    coupon = queryset.first()
    if not coupon:
        return None, {"message": "Coupon not found."}, status.HTTP_404_NOT_FOUND

    if not coupon.is_active:
        return None, {"message": "Coupon is inactive."}, status.HTTP_400_BAD_REQUEST

    now = timezone.now()
    if coupon.expiry_date and coupon.expiry_date < now:
        return None, {"message": "Coupon has expired."}, status.HTTP_400_BAD_REQUEST

    if coupon.usage_limit is not None and coupon.usage_count >= coupon.usage_limit:
        return None, {"message": "Coupon usage limit reached."}, status.HTTP_400_BAD_REQUEST

    normalized_subtotal = _quantize_money(subtotal)
    min_amount = _quantize_money(coupon.min_booking_amount or Decimal("0"))
    if normalized_subtotal < min_amount:
        return (
            None,
            {
                "message": "Order amount does not meet coupon minimum requirement.",
                "min_booking_amount": float(min_amount),
            },
            status.HTTP_400_BAD_REQUEST,
        )

    return coupon, None, status.HTTP_200_OK


def _apply_coupon_to_subtotal(
    coupon_code: Any,
    subtotal: Decimal,
    *,
    context: Optional[dict[str, Any]] = None,
    lock_for_update: bool = False,
    consume: bool = False,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    promo, promo_error, promo_status = _validate_vendor_promo_for_subtotal(
        coupon_code,
        subtotal,
        context=context,
        lock_for_update=lock_for_update,
    )
    if promo:
        seat_count = _coerce_int(coalesce(context or {}, "seat_count", "seatCount")) or 0
        discount = _vendor_promo_discount_for_amount(promo, subtotal, seat_count=seat_count)
        final_total = _quantize_money(_quantize_money(subtotal) - discount)

        if consume:
            promo.usage_count = int(promo.usage_count or 0) + 1
            promo.save(update_fields=["usage_count", "updated_at"])

        return {
            "coupon": None,
            "promo_code": _serialize_vendor_promo_code(promo),
            "discount_source": "VENDOR_PROMO",
            "discount_amount": float(discount),
            "subtotal": float(_quantize_money(subtotal)),
            "final_total": float(final_total),
        }, None, status.HTTP_200_OK

    coupon, error, status_code = _validate_coupon_for_subtotal(
        coupon_code,
        subtotal,
        lock_for_update=lock_for_update,
    )
    if error:
        if promo_error:
            return None, promo_error, promo_status
        return None, error, status_code

    discount = _coupon_discount_for_amount(coupon, subtotal)
    final_total = _quantize_money(_quantize_money(subtotal) - discount)

    if consume:
        coupon.usage_count = int(coupon.usage_count or 0) + 1
        coupon.save(update_fields=["usage_count", "updated_at"])

    payload = {
        "coupon": _serialize_coupon(coupon),
        "promo_code": None,
        "discount_source": "ADMIN_COUPON",
        "discount_amount": float(discount),
        "subtotal": float(_quantize_money(subtotal)),
        "final_total": float(final_total),
    }
    return payload, None, status.HTTP_200_OK


def list_admin_coupons() -> list[dict[str, Any]]:
    return [_serialize_coupon(item) for item in Coupon.objects.all().order_by("-created_at", "-id")]


def create_admin_coupon(request: Any) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    code = _normalize_coupon_code(coalesce(payload, "code", "coupon_code", "couponCode"))
    if not code:
        return {"message": "code is required."}, status.HTTP_400_BAD_REQUEST
    if Coupon.objects.filter(code__iexact=code).exists():
        return {"message": "Coupon code already exists."}, status.HTTP_400_BAD_REQUEST

    discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
    if discount_type not in {
        Coupon.DISCOUNT_TYPE_PERCENTAGE,
        Coupon.DISCOUNT_TYPE_FIXED,
    }:
        return {"message": "discount_type must be PERCENTAGE or FIXED."}, status.HTTP_400_BAD_REQUEST

    discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
    if discount_value is None:
        return {"message": "discount_value must be a non-negative number."}, status.HTTP_400_BAD_REQUEST

    min_booking_amount = _parse_price_amount(
        coalesce(payload, "min_booking_amount", "minBookingAmount")
    )
    if min_booking_amount is None:
        min_booking_amount = Decimal("0.00")

    usage_limit_raw = coalesce(payload, "usage_limit", "usageLimit")
    usage_limit = _coerce_int(usage_limit_raw)
    if usage_limit_raw not in (None, "") and (usage_limit is None or usage_limit < 1):
        return {"message": "usage_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST

    expiry_date = _parse_coupon_expiry(coalesce(payload, "expiry_date", "expiryDate"))
    if coalesce(payload, "expiry_date", "expiryDate") not in (None, "") and not expiry_date:
        return {"message": "expiry_date is invalid."}, status.HTTP_400_BAD_REQUEST

    coupon = Coupon.objects.create(
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        min_booking_amount=min_booking_amount,
        expiry_date=expiry_date,
        usage_limit=usage_limit,
        is_active=parse_bool(coalesce(payload, "is_active", "isActive"), default=True),
    )
    return {"message": "Coupon created.", "coupon": _serialize_coupon(coupon)}, status.HTTP_201_CREATED


def update_admin_coupon(request: Any, coupon: Coupon) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    updates: dict[str, Any] = {}

    if "code" in payload or "coupon_code" in payload or "couponCode" in payload:
        code = _normalize_coupon_code(coalesce(payload, "code", "coupon_code", "couponCode"))
        if not code:
            return {"message": "code cannot be empty."}, status.HTTP_400_BAD_REQUEST
        existing = Coupon.objects.filter(code__iexact=code).exclude(id=coupon.id).exists()
        if existing:
            return {"message": "Coupon code already exists."}, status.HTTP_400_BAD_REQUEST
        updates["code"] = code

    if "discount_type" in payload or "discountType" in payload:
        discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
        if discount_type not in {
            Coupon.DISCOUNT_TYPE_PERCENTAGE,
            Coupon.DISCOUNT_TYPE_FIXED,
        }:
            return {"message": "discount_type must be PERCENTAGE or FIXED."}, status.HTTP_400_BAD_REQUEST
        updates["discount_type"] = discount_type

    if "discount_value" in payload or "discountValue" in payload:
        discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
        if discount_value is None:
            return {"message": "discount_value must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["discount_value"] = discount_value

    if "min_booking_amount" in payload or "minBookingAmount" in payload:
        min_booking_amount = _parse_price_amount(
            coalesce(payload, "min_booking_amount", "minBookingAmount")
        )
        if min_booking_amount is None:
            return {"message": "min_booking_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["min_booking_amount"] = min_booking_amount

    if "usage_limit" in payload or "usageLimit" in payload:
        usage_limit_raw = coalesce(payload, "usage_limit", "usageLimit")
        usage_limit = _coerce_int(usage_limit_raw)
        if usage_limit_raw in (None, ""):
            updates["usage_limit"] = None
        elif usage_limit is None or usage_limit < 1:
            return {"message": "usage_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST
        else:
            updates["usage_limit"] = usage_limit

    if "usage_count" in payload:
        usage_count = _coerce_int(payload.get("usage_count"))
        if usage_count is None or usage_count < 0:
            return {"message": "usage_count must be zero or greater."}, status.HTTP_400_BAD_REQUEST
        updates["usage_count"] = usage_count

    if "expiry_date" in payload or "expiryDate" in payload:
        raw_expiry = coalesce(payload, "expiry_date", "expiryDate")
        if raw_expiry in (None, ""):
            updates["expiry_date"] = None
        else:
            expiry_date = _parse_coupon_expiry(raw_expiry)
            if not expiry_date:
                return {"message": "expiry_date is invalid."}, status.HTTP_400_BAD_REQUEST
            updates["expiry_date"] = expiry_date

    if "is_active" in payload or "isActive" in payload:
        updates["is_active"] = parse_bool(coalesce(payload, "is_active", "isActive"), default=True)

    if not updates:
        return {"message": "No coupon changes provided."}, status.HTTP_400_BAD_REQUEST

    for key, value in updates.items():
        setattr(coupon, key, value)
    coupon.save()
    return {"message": "Coupon updated.", "coupon": _serialize_coupon(coupon)}, status.HTTP_200_OK


def delete_admin_coupon(coupon: Coupon) -> tuple[dict[str, Any], int]:
    coupon.delete()
    return {"message": "Coupon deleted."}, status.HTTP_200_OK


def list_vendor_promo_codes(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
    promos = VendorPromoCode.objects.filter(vendor_id=vendor.id).order_by("-created_at", "-id")
    return {"promo_codes": [_serialize_vendor_promo_code(item) for item in promos]}, status.HTTP_200_OK


def _parse_promo_payload(payload: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    code = _normalize_coupon_code(coalesce(payload, "code", "promo_code", "promoCode"))
    title = str(coalesce(payload, "title", "name") or "").strip()
    discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
    discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
    if not code:
        return None, "code is required."
    if not title:
        return None, "title is required."
    if discount_type not in {
        VendorPromoCode.DISCOUNT_TYPE_PERCENTAGE,
        VendorPromoCode.DISCOUNT_TYPE_FIXED,
        VendorPromoCode.DISCOUNT_TYPE_BOGO,
    }:
        return None, "discount_type must be PERCENTAGE, FIXED, or BOGO."
    if discount_value is None:
        return None, "discount_value must be a non-negative number."

    min_booking_amount = _parse_price_amount(coalesce(payload, "min_booking_amount", "minBookingAmount"))
    if min_booking_amount is None:
        min_booking_amount = Decimal("0.00")

    max_discount_amount = _parse_price_amount(coalesce(payload, "max_discount_amount", "maxDiscountAmount"))
    usage_limit_raw = coalesce(payload, "usage_limit", "usageLimit")
    usage_limit = _coerce_int(usage_limit_raw)
    if usage_limit_raw not in (None, "") and (usage_limit is None or usage_limit < 1):
        return None, "usage_limit must be a positive integer."

    per_user_limit_raw = coalesce(payload, "per_user_limit", "perUserLimit")
    per_user_limit = _coerce_int(per_user_limit_raw)
    if per_user_limit_raw not in (None, "") and (per_user_limit is None or per_user_limit < 1):
        return None, "per_user_limit must be a positive integer."

    seat_scope = str(coalesce(payload, "seat_category_scope", "seatCategoryScope") or VendorPromoCode.SEAT_CATEGORY_ALL).strip().upper()
    if seat_scope not in {
        VendorPromoCode.SEAT_CATEGORY_ALL,
        VendorPromoCode.SEAT_CATEGORY_NORMAL,
        VendorPromoCode.SEAT_CATEGORY_EXECUTIVE,
        VendorPromoCode.SEAT_CATEGORY_PREMIUM,
        VendorPromoCode.SEAT_CATEGORY_VIP,
    }:
        return None, "seat_category_scope is invalid."

    valid_from = _parse_datetime_value(coalesce(payload, "valid_from", "validFrom"))
    valid_until = _parse_datetime_value(coalesce(payload, "valid_until", "validUntil"))
    if valid_from and valid_until and valid_from > valid_until:
        return None, "valid_until must be after valid_from."

    weekday_values = coalesce(payload, "allowed_weekdays", "allowedWeekdays", default="")
    if isinstance(weekday_values, (list, tuple, set)):
        weekdays_text = ",".join([str(item).strip().upper() for item in weekday_values])
    else:
        weekdays_text = str(weekday_values or "").strip().upper()

    return {
        "code": code,
        "title": title,
        "description": str(coalesce(payload, "description") or "").strip() or None,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "min_booking_amount": min_booking_amount,
        "max_discount_amount": max_discount_amount,
        "usage_limit": usage_limit,
        "per_user_limit": per_user_limit,
        "seat_category_scope": seat_scope,
        "requires_student": parse_bool(coalesce(payload, "requires_student", "requiresStudent"), default=False),
        "allowed_weekdays": weekdays_text or None,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "is_flash_sale": parse_bool(coalesce(payload, "is_flash_sale", "isFlashSale"), default=False),
        "is_active": parse_bool(coalesce(payload, "is_active", "isActive"), default=True),
    }, None


def create_vendor_promo_code(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    parsed, error_message = _parse_promo_payload(payload)
    if error_message:
        return {"message": error_message}, status.HTTP_400_BAD_REQUEST

    if VendorPromoCode.objects.filter(code__iexact=parsed["code"]).exists() or Coupon.objects.filter(code__iexact=parsed["code"]).exists():
        return {"message": "Promo code already exists."}, status.HTTP_400_BAD_REQUEST

    promo = VendorPromoCode.objects.create(vendor_id=vendor.id, **parsed)
    return {
        "message": "Vendor promo code created.",
        "promo_code": _serialize_vendor_promo_code(promo),
    }, status.HTTP_201_CREATED


def update_vendor_promo_code(request: Any, promo: VendorPromoCode) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    updates: dict[str, Any] = {}

    if "code" in payload or "promo_code" in payload or "promoCode" in payload:
        code = _normalize_coupon_code(coalesce(payload, "code", "promo_code", "promoCode"))
        if not code:
            return {"message": "code cannot be empty."}, status.HTTP_400_BAD_REQUEST
        if (
            VendorPromoCode.objects.filter(code__iexact=code).exclude(id=promo.id).exists()
            or Coupon.objects.filter(code__iexact=code).exists()
        ):
            return {"message": "Promo code already exists."}, status.HTTP_400_BAD_REQUEST
        updates["code"] = code

    if "title" in payload or "name" in payload:
        title = str(coalesce(payload, "title", "name") or "").strip()
        if not title:
            return {"message": "title cannot be empty."}, status.HTTP_400_BAD_REQUEST
        updates["title"] = title

    if "description" in payload:
        updates["description"] = str(payload.get("description") or "").strip() or None

    if "discount_type" in payload or "discountType" in payload:
        discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
        if discount_type not in {
            VendorPromoCode.DISCOUNT_TYPE_PERCENTAGE,
            VendorPromoCode.DISCOUNT_TYPE_FIXED,
            VendorPromoCode.DISCOUNT_TYPE_BOGO,
        }:
            return {"message": "discount_type must be PERCENTAGE, FIXED, or BOGO."}, status.HTTP_400_BAD_REQUEST
        updates["discount_type"] = discount_type

    if "discount_value" in payload or "discountValue" in payload:
        discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
        if discount_value is None:
            return {"message": "discount_value must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["discount_value"] = discount_value

    if "min_booking_amount" in payload or "minBookingAmount" in payload:
        min_amount = _parse_price_amount(coalesce(payload, "min_booking_amount", "minBookingAmount"))
        if min_amount is None:
            return {"message": "min_booking_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["min_booking_amount"] = min_amount

    if "max_discount_amount" in payload or "maxDiscountAmount" in payload:
        raw = coalesce(payload, "max_discount_amount", "maxDiscountAmount")
        if raw in (None, ""):
            updates["max_discount_amount"] = None
        else:
            max_amount = _parse_price_amount(raw)
            if max_amount is None:
                return {"message": "max_discount_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
            updates["max_discount_amount"] = max_amount

    if "usage_limit" in payload or "usageLimit" in payload:
        raw = coalesce(payload, "usage_limit", "usageLimit")
        if raw in (None, ""):
            updates["usage_limit"] = None
        else:
            usage_limit = _coerce_int(raw)
            if usage_limit is None or usage_limit < 1:
                return {"message": "usage_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST
            updates["usage_limit"] = usage_limit

    if "per_user_limit" in payload or "perUserLimit" in payload:
        raw = coalesce(payload, "per_user_limit", "perUserLimit")
        if raw in (None, ""):
            updates["per_user_limit"] = None
        else:
            per_user_limit = _coerce_int(raw)
            if per_user_limit is None or per_user_limit < 1:
                return {"message": "per_user_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST
            updates["per_user_limit"] = per_user_limit

    if "seat_category_scope" in payload or "seatCategoryScope" in payload:
        seat_scope = str(coalesce(payload, "seat_category_scope", "seatCategoryScope") or "").strip().upper()
        if seat_scope not in {
            VendorPromoCode.SEAT_CATEGORY_ALL,
            VendorPromoCode.SEAT_CATEGORY_NORMAL,
            VendorPromoCode.SEAT_CATEGORY_EXECUTIVE,
            VendorPromoCode.SEAT_CATEGORY_PREMIUM,
            VendorPromoCode.SEAT_CATEGORY_VIP,
        }:
            return {"message": "seat_category_scope is invalid."}, status.HTTP_400_BAD_REQUEST
        updates["seat_category_scope"] = seat_scope

    if "requires_student" in payload or "requiresStudent" in payload:
        updates["requires_student"] = parse_bool(
            coalesce(payload, "requires_student", "requiresStudent"),
            default=promo.requires_student,
        )

    if "allowed_weekdays" in payload or "allowedWeekdays" in payload:
        weekday_values = coalesce(payload, "allowed_weekdays", "allowedWeekdays", default="")
        if isinstance(weekday_values, (list, tuple, set)):
            weekdays_text = ",".join([str(item).strip().upper() for item in weekday_values])
        else:
            weekdays_text = str(weekday_values or "").strip().upper()
        updates["allowed_weekdays"] = weekdays_text or None

    if "valid_from" in payload or "validFrom" in payload:
        updates["valid_from"] = _parse_datetime_value(coalesce(payload, "valid_from", "validFrom"))

    if "valid_until" in payload or "validUntil" in payload:
        updates["valid_until"] = _parse_datetime_value(coalesce(payload, "valid_until", "validUntil"))

    if "is_flash_sale" in payload or "isFlashSale" in payload:
        updates["is_flash_sale"] = parse_bool(
            coalesce(payload, "is_flash_sale", "isFlashSale"),
            default=promo.is_flash_sale,
        )

    if "is_active" in payload or "isActive" in payload:
        updates["is_active"] = parse_bool(
            coalesce(payload, "is_active", "isActive"),
            default=promo.is_active,
        )

    if not updates:
        return {"message": "No promo code changes provided."}, status.HTTP_400_BAD_REQUEST

    for key, value in updates.items():
        setattr(promo, key, value)
    promo.save()

    return {
        "message": "Vendor promo code updated.",
        "promo_code": _serialize_vendor_promo_code(promo),
    }, status.HTTP_200_OK


def delete_vendor_promo_code(promo: VendorPromoCode) -> tuple[dict[str, Any], int]:
    promo.delete()
    return {"message": "Vendor promo code deleted."}, status.HTTP_200_OK


def _render_vendor_campaign_message(
    template: str,
    *,
    user: User,
    last_movie_title: str,
    recommended_movie_title: str,
    promo_code: Optional[str],
    promo_value: Optional[str],
) -> str:
    safe_template = str(template or "").strip() or (
        "Hey {first_name}, you watched {last_movie} with us. "
        "Book {next_movie} early with {promo_code}!"
    )
    full_name = " ".join(
        [part for part in [user.first_name, user.middle_name, user.last_name] if part]
    ).strip()
    values = {
        "first_name": user.first_name or "Customer",
        "full_name": full_name or user.email or "Customer",
        "last_movie": last_movie_title or "your recent movie",
        "next_movie": recommended_movie_title or "our latest show",
        "promo_code": promo_code or "a special offer",
        "discount_value": promo_value or "",
    }
    return safe_template.format(**values)


def _get_campaign_audience(campaign: VendorCampaign) -> list[tuple[User, str]]:
    queryset = Booking.objects.filter(showtime__screen__vendor_id=campaign.vendor_id).exclude(
        booking_status__iexact="Cancelled"
    ).select_related("user", "showtime__movie")

    if campaign.target_movie_id:
        queryset = queryset.filter(showtime__movie_id=campaign.target_movie_id)

    if campaign.min_days_since_booking and campaign.min_days_since_booking > 0:
        threshold = timezone.now() - timedelta(days=int(campaign.min_days_since_booking))
        queryset = queryset.filter(booking_date__lte=threshold)

    latest_by_user: dict[int, tuple[User, str]] = {}
    for booking in queryset.order_by("user_id", "-booking_date", "-id"):
        if booking.user_id in latest_by_user:
            continue
        movie_title = booking.showtime.movie.title if booking.showtime and booking.showtime.movie else ""
        latest_by_user[booking.user_id] = (booking.user, movie_title)

    return list(latest_by_user.values())


def _dispatch_vendor_campaign(campaign: VendorCampaign) -> dict[str, Any]:
    audience = _get_campaign_audience(campaign)
    sent_count = 0
    failed_count = 0
    recommended_movie_title = campaign.recommended_movie.title if campaign.recommended_movie_id and campaign.recommended_movie else ""
    promo_code = campaign.promo_code.code if campaign.promo_code_id and campaign.promo_code else None
    promo_value = (
        str(_quantize_money(campaign.promo_code.discount_value or Decimal("0")))
        if campaign.promo_code_id and campaign.promo_code
        else None
    )

    campaign.status = VendorCampaign.STATUS_RUNNING
    campaign.save(update_fields=["status", "updated_at"])

    for user, last_movie_title in audience:
        message = _render_vendor_campaign_message(
            campaign.message_template,
            user=user,
            last_movie_title=last_movie_title,
            recommended_movie_title=recommended_movie_title,
            promo_code=promo_code,
            promo_value=promo_value,
        )

        if campaign.delivery_channel in {VendorCampaign.CHANNEL_PUSH, VendorCampaign.CHANNEL_BOTH}:
            try:
                _create_notification(
                    recipient_role=Notification.ROLE_CUSTOMER,
                    recipient_id=user.id,
                    recipient_email=user.email,
                    event_type=Notification.EVENT_MARKETING_CAMPAIGN,
                    title=f"{campaign.vendor.name}: Special Offer",
                    message=message,
                    metadata={
                        "campaign_id": campaign.id,
                        "vendor_id": campaign.vendor_id,
                        "promo_code": promo_code,
                    },
                    send_email_too=False,
                )
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_PUSH,
                    contact=user.email,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_SENT,
                )
                sent_count += 1
            except Exception as exc:
                failed_count += 1
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_PUSH,
                    contact=user.email,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_FAILED,
                    error_message=str(exc)[:255],
                )

        if campaign.delivery_channel in {VendorCampaign.CHANNEL_SMS, VendorCampaign.CHANNEL_BOTH}:
            phone = str(user.phone_number or "").strip()
            if phone:
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_SMS,
                    contact=phone,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_SENT,
                )
                sent_count += 1
            else:
                failed_count += 1
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_SMS,
                    contact=None,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_FAILED,
                    error_message="User phone number is missing.",
                )

    campaign.sent_count = int(campaign.sent_count or 0) + sent_count
    campaign.failed_count = int(campaign.failed_count or 0) + failed_count
    campaign.last_run_at = timezone.now()
    campaign.status = VendorCampaign.STATUS_COMPLETED
    campaign.save(update_fields=["sent_count", "failed_count", "last_run_at", "status", "updated_at"])

    return {
        "audience_count": len(audience),
        "sent_count": sent_count,
        "failed_count": failed_count,
    }


def _sync_due_vendor_campaigns(vendor_id: int) -> None:
    now = timezone.now()
    campaigns = VendorCampaign.objects.filter(
        vendor_id=vendor_id,
        status=VendorCampaign.STATUS_SCHEDULED,
        scheduled_at__isnull=False,
        scheduled_at__lte=now,
    ).select_related("vendor", "promo_code", "recommended_movie")
    for campaign in campaigns:
        try:
            _dispatch_vendor_campaign(campaign)
        except Exception:
            logger.exception("Failed to auto-dispatch vendor campaign %s", campaign.id)


def list_vendor_campaigns(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    _sync_due_vendor_campaigns(vendor.id)

    campaigns = VendorCampaign.objects.filter(vendor_id=vendor.id).select_related(
        "promo_code", "target_movie", "recommended_movie"
    ).order_by("-created_at", "-id")
    return {"campaigns": [_serialize_vendor_campaign(item) for item in campaigns]}, status.HTTP_200_OK


def create_vendor_campaign(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    name = str(coalesce(payload, "name", "title") or "").strip()
    message_template = str(coalesce(payload, "message_template", "messageTemplate", "message") or "").strip()
    if not name:
        return {"message": "name is required."}, status.HTTP_400_BAD_REQUEST
    if not message_template:
        return {"message": "message_template is required."}, status.HTTP_400_BAD_REQUEST

    channel = str(coalesce(payload, "delivery_channel", "deliveryChannel") or VendorCampaign.CHANNEL_BOTH).strip().upper()
    if channel not in {VendorCampaign.CHANNEL_PUSH, VendorCampaign.CHANNEL_SMS, VendorCampaign.CHANNEL_BOTH}:
        return {"message": "delivery_channel must be PUSH, SMS, or BOTH."}, status.HTTP_400_BAD_REQUEST

    target_movie_id = _coerce_int(coalesce(payload, "target_movie_id", "targetMovieId"))
    recommended_movie_id = _coerce_int(coalesce(payload, "recommended_movie_id", "recommendedMovieId"))
    promo_code_id = _coerce_int(coalesce(payload, "promo_code_id", "promoCodeId"))

    promo_code = None
    if promo_code_id:
        promo_code = VendorPromoCode.objects.filter(id=promo_code_id, vendor_id=vendor.id, is_active=True).first()
        if not promo_code:
            return {"message": "promo_code_id is invalid."}, status.HTTP_400_BAD_REQUEST

    campaign = VendorCampaign.objects.create(
        vendor_id=vendor.id,
        name=name,
        message_template=message_template,
        delivery_channel=channel,
        status=VendorCampaign.STATUS_SCHEDULED
        if coalesce(payload, "scheduled_at", "scheduledAt")
        else VendorCampaign.STATUS_DRAFT,
        target_movie_id=target_movie_id,
        recommended_movie_id=recommended_movie_id,
        promo_code=promo_code,
        include_past_attendees_only=parse_bool(
            coalesce(payload, "include_past_attendees_only", "includePastAttendeesOnly"),
            default=True,
        ),
        min_days_since_booking=max(0, _coerce_int(coalesce(payload, "min_days_since_booking", "minDaysSinceBooking")) or 0),
        scheduled_at=_parse_datetime_value(coalesce(payload, "scheduled_at", "scheduledAt")),
    )

    if parse_bool(coalesce(payload, "run_now", "runNow"), default=False):
        stats = _dispatch_vendor_campaign(campaign)
        return {
            "message": "Campaign created and dispatched.",
            "campaign": _serialize_vendor_campaign(campaign),
            "dispatch": stats,
        }, status.HTTP_201_CREATED

    return {
        "message": "Vendor campaign created.",
        "campaign": _serialize_vendor_campaign(campaign),
    }, status.HTTP_201_CREATED


def update_vendor_campaign(request: Any, campaign: VendorCampaign) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    updates: dict[str, Any] = {}

    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            return {"message": "name cannot be empty."}, status.HTTP_400_BAD_REQUEST
        updates["name"] = name

    if "message_template" in payload or "messageTemplate" in payload or "message" in payload:
        message_template = str(coalesce(payload, "message_template", "messageTemplate", "message") or "").strip()
        if not message_template:
            return {"message": "message_template cannot be empty."}, status.HTTP_400_BAD_REQUEST
        updates["message_template"] = message_template

    if "delivery_channel" in payload or "deliveryChannel" in payload:
        channel = str(coalesce(payload, "delivery_channel", "deliveryChannel") or "").strip().upper()
        if channel not in {VendorCampaign.CHANNEL_PUSH, VendorCampaign.CHANNEL_SMS, VendorCampaign.CHANNEL_BOTH}:
            return {"message": "delivery_channel must be PUSH, SMS, or BOTH."}, status.HTTP_400_BAD_REQUEST
        updates["delivery_channel"] = channel

    if "target_movie_id" in payload or "targetMovieId" in payload:
        updates["target_movie_id"] = _coerce_int(coalesce(payload, "target_movie_id", "targetMovieId"))

    if "recommended_movie_id" in payload or "recommendedMovieId" in payload:
        updates["recommended_movie_id"] = _coerce_int(coalesce(payload, "recommended_movie_id", "recommendedMovieId"))

    if "promo_code_id" in payload or "promoCodeId" in payload:
        promo_code_id = _coerce_int(coalesce(payload, "promo_code_id", "promoCodeId"))
        if promo_code_id:
            promo_code = VendorPromoCode.objects.filter(
                id=promo_code_id,
                vendor_id=campaign.vendor_id,
                is_active=True,
            ).first()
            if not promo_code:
                return {"message": "promo_code_id is invalid."}, status.HTTP_400_BAD_REQUEST
            updates["promo_code"] = promo_code
        else:
            updates["promo_code"] = None

    if "include_past_attendees_only" in payload or "includePastAttendeesOnly" in payload:
        updates["include_past_attendees_only"] = parse_bool(
            coalesce(payload, "include_past_attendees_only", "includePastAttendeesOnly"),
            default=campaign.include_past_attendees_only,
        )

    if "min_days_since_booking" in payload or "minDaysSinceBooking" in payload:
        updates["min_days_since_booking"] = max(
            0,
            _coerce_int(coalesce(payload, "min_days_since_booking", "minDaysSinceBooking")) or 0,
        )

    if "scheduled_at" in payload or "scheduledAt" in payload:
        updates["scheduled_at"] = _parse_datetime_value(coalesce(payload, "scheduled_at", "scheduledAt"))

    if "status" in payload:
        next_status = str(payload.get("status") or "").strip().upper()
        if next_status not in {
            VendorCampaign.STATUS_DRAFT,
            VendorCampaign.STATUS_SCHEDULED,
            VendorCampaign.STATUS_RUNNING,
            VendorCampaign.STATUS_COMPLETED,
        }:
            return {"message": "status is invalid."}, status.HTTP_400_BAD_REQUEST
        updates["status"] = next_status

    if not updates:
        return {"message": "No campaign changes provided."}, status.HTTP_400_BAD_REQUEST

    for key, value in updates.items():
        setattr(campaign, key, value)
    campaign.save()

    return {
        "message": "Vendor campaign updated.",
        "campaign": _serialize_vendor_campaign(campaign),
    }, status.HTTP_200_OK


def run_vendor_campaign(campaign: VendorCampaign) -> tuple[dict[str, Any], int]:
    stats = _dispatch_vendor_campaign(campaign)
    recent_dispatches = VendorCampaignDispatch.objects.filter(campaign_id=campaign.id).order_by("-id")[:20]
    return {
        "message": "Campaign dispatched.",
        "campaign": _serialize_vendor_campaign(campaign),
        "dispatch": stats,
        "recent_logs": [_serialize_vendor_campaign_dispatch(item) for item in recent_dispatches],
    }, status.HTTP_200_OK


def apply_coupon_for_booking(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    subtotal = _parse_price_amount(
        coalesce(payload, "subtotal", "ticket_total", "ticketTotal", "amount")
    )
    if subtotal is None or subtotal <= Decimal("0"):
        return {"message": "A valid subtotal amount is required."}, status.HTTP_400_BAD_REQUEST

    coupon_code = coalesce(payload, "coupon_code", "couponCode", "code")
    result, error, status_code = _apply_coupon_to_subtotal(
        coupon_code,
        subtotal,
        context=payload,
        lock_for_update=False,
        consume=False,
    )
    if error:
        return error, status_code

    return {
        "message": "Coupon applied successfully.",
        "coupon": result["coupon"],
        "promo_code": result.get("promo_code"),
        "discount_source": result.get("discount_source"),
        "subtotal": result["subtotal"],
        "discount_amount": result["discount_amount"],
        "final_total": result["final_total"],
    }, status.HTTP_200_OK


def build_user_payload(user: User, request: Any) -> dict[str, Any]:
    """Build the API payload for a user."""
    full_name = " ".join(
        [part for part in [user.first_name, user.middle_name, user.last_name] if part]
    ).strip()
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "last_name": user.last_name,
        "full_name": full_name,
        "phone_number": user.phone_number,
        "profile_image": get_profile_image_url(request, user),
        "dob": user.dob.isoformat() if user.dob else None,
        "is_active": getattr(user, "is_active", True),
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
    }


def build_admin_payload(admin_user: Admin, request: Any) -> dict[str, Any]:
    """Build the API payload for an admin user."""
    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "username": admin_user.username,
        "full_name": admin_user.full_name,
        "phone_number": admin_user.phone_number,
        "is_active": admin_user.is_active,
        "profile_image": get_profile_image_url(request, admin_user),
        "date_joined": admin_user.date_joined.isoformat()
        if admin_user.date_joined
        else None,
    }


def build_vendor_payload(vendor_user: Vendor, request: Any) -> dict[str, Any]:
    """Build the API payload for a vendor user."""
    return {
        "id": vendor_user.id,
        "name": vendor_user.name,
        "email": vendor_user.email,
        "username": vendor_user.username,
        "phone_number": vendor_user.phone_number,
        "theatre": vendor_user.theatre,
        "city": vendor_user.city,
        "commission_percent": float(_resolve_vendor_commission_percent(vendor_user)),
        "status": vendor_user.status,
        "is_active": vendor_user.is_active,
        "created_at": vendor_user.created_at.isoformat() if vendor_user.created_at else None,
        "profile_image": get_profile_image_url(request, vendor_user),
    }


def build_vendor_staff_payload(staff_user: VendorStaff) -> dict[str, Any]:
    """Build the API payload for a vendor staff user."""
    return {
        "id": staff_user.id,
        "vendor_id": staff_user.vendor_id,
        "full_name": staff_user.full_name,
        "email": staff_user.email,
        "phone_number": staff_user.phone_number,
        "username": staff_user.username,
        "role": staff_user.role,
        "is_active": staff_user.is_active,
        "created_at": staff_user.created_at.isoformat() if staff_user.created_at else None,
        "updated_at": staff_user.updated_at.isoformat() if staff_user.updated_at else None,
    }


def _login_identity_query(
    identifier: str,
    phone_candidates: Optional[set[str]] = None,
    include_username: bool = True,
) -> Q:
    """Build a login query for email/phone/username."""
    query = Q(email__iexact=identifier)
    if phone_candidates:
        query |= Q(phone_number__in=phone_candidates)
    else:
        query |= Q(phone_number=identifier)
    if include_username:
        query |= Q(username__iexact=identifier)
    return query


def _admin_lookup_query_from_user(user: User) -> Q:
    """Build a query to find an Admin matching a User identity."""
    query = Q(email__iexact=user.email)
    if user.username:
        query |= Q(username__iexact=user.username)
    if user.phone_number:
        query |= Q(phone_number=user.phone_number)
    return query


def _admin_login_payload(admin: Admin, password: str, request: Any) -> tuple[dict[str, Any], int]:
    """Return the admin login response payload."""
    if not admin.is_active:
        return {"message": "Admin account is inactive"}, status.HTTP_403_FORBIDDEN
    if not admin.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED
    display_name = admin.full_name or admin.username or admin.email
    access_token = issue_access_token("admin", admin.id)
    return {
        "message": f"Admin login successful. Welcome {display_name}!",
        "role": "admin",
        "admin": build_admin_payload(admin, request),
        "access_token": access_token,
    }, status.HTTP_200_OK


def _vendor_login_payload(vendor: Vendor, password: str, request: Any) -> tuple[dict[str, Any], int]:
    """Return the vendor login response payload."""
    if not vendor.is_active or str(vendor.status).lower() == "blocked":
        return {"message": "Vendor account is inactive"}, status.HTTP_403_FORBIDDEN
    if not vendor.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED
    display_name = vendor.name or vendor.username or vendor.email
    access_token = issue_access_token("vendor", vendor.id)
    return {
        "message": f"Vendor login successful. Welcome {display_name}!",
        "role": "vendor",
        "vendor": build_vendor_payload(vendor, request),
        "vendor_staff": None,
        "access_token": access_token,
    }, status.HTTP_200_OK


def _vendor_staff_login_payload(
    staff: VendorStaff,
    password: str,
    request: Any,
) -> tuple[dict[str, Any], int]:
    """Return the vendor staff login payload as a vendor-scoped session."""
    vendor = staff.vendor
    if not staff.is_active:
        return {"message": "Vendor staff account is inactive"}, status.HTTP_403_FORBIDDEN
    if not vendor.is_active or str(vendor.status).lower() == "blocked":
        return {"message": "Vendor account is inactive"}, status.HTTP_403_FORBIDDEN
    if not staff.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED

    display_name = staff.full_name or staff.username or staff.email
    access_token = issue_access_token(
        "vendor",
        vendor.id,
        extras={
            "staff_id": staff.id,
            "staff_role": staff.role,
        },
    )
    return {
        "message": f"Vendor login successful. Welcome {display_name}!",
        "role": "vendor",
        "vendor": build_vendor_payload(vendor, request),
        "vendor_staff": build_vendor_staff_payload(staff),
        "access_token": access_token,
    }, status.HTTP_200_OK


def _is_truthy_flag(value: Any) -> bool:
    """Normalize common truthy flag values."""
    return str(value or "").lower() in ("1", "true", "yes")


def _update_profile_image(instance: Any, uploaded_image: Any, remove_avatar: bool) -> None:
    """Update or clear profile image based on inputs."""
    if remove_avatar:
        if instance.profile_image:
            instance.profile_image.delete(save=False)
        instance.profile_image = None
        instance.save()
        return
    if uploaded_image:
        if instance.profile_image:
            instance.profile_image.delete(save=False)
        instance.profile_image = uploaded_image
        instance.save()


def register_user(request: Any) -> tuple[dict[str, Any], int]:
    """Register a new user account."""
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        try:
            user = serializer.save()
            return {
                "message": "Registration successful",
                "user": build_user_payload(user, request),
            }, status.HTTP_201_CREATED
        except Exception as exc:
            logger.exception("Error saving user")
            return {
                "message": "Failed to create user",
                "error": str(exc),
            }, status.HTTP_500_INTERNAL_SERVER_ERROR

    return {
        "message": "Registration failed",
        "errors": serializer.errors,
    }, status.HTTP_400_BAD_REQUEST


def login_user(request: Any) -> tuple[dict[str, Any], int]:
    """Authenticate a user, vendor, or admin."""
    serializer = UserLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return {
            "message": "Invalid input",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    raw_identifier = serializer.validated_data["email_or_phone"].strip()
    password = serializer.validated_data["password"]
    phone_candidates: Optional[set[str]] = None
    if is_phone_like(raw_identifier):
        normalized_phone = normalize_phone_number(raw_identifier)
        if normalized_phone:
            phone_candidates = {normalized_phone, raw_identifier}

    try:
        admin = Admin.objects.filter(
            _login_identity_query(raw_identifier, phone_candidates)
        ).first()
        if admin:
            return _admin_login_payload(admin, password, request)

        vendor_query = _login_identity_query(raw_identifier, phone_candidates)
        if str(raw_identifier).isdigit():
            try:
                vendor_query |= Q(id=int(raw_identifier))
            except ValueError:
                pass

        vendor = Vendor.objects.filter(vendor_query).first()

        if vendor:
            return _vendor_login_payload(vendor, password, request)

        staff_query = _login_identity_query(raw_identifier, phone_candidates)
        staff = VendorStaff.objects.select_related("vendor").filter(staff_query).first()
        if staff:
            return _vendor_staff_login_payload(staff, password, request)

        user_phone_query = (
            Q(phone_number__in=phone_candidates)
            if phone_candidates
            else Q(phone_number=raw_identifier)
        )
        user = User.objects.filter(
            Q(email__iexact=raw_identifier) | user_phone_query
        ).first()

        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        admin_for_user = Admin.objects.filter(_admin_lookup_query_from_user(user)).first()
        if admin_for_user:
            return _admin_login_payload(admin_for_user, password, request)

        if hasattr(user, "is_active") and not user.is_active:
            return {"message": "User account is inactive"}, status.HTTP_403_FORBIDDEN

        if not user.check_password(password):
            return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED

        access_token = issue_access_token("customer", user.id)
        try:
            _ensure_customer_login_offer_notification(user)
        except Exception:
            logger.exception("Failed to create login offer notification for user %s", user.id)
        return {
            "message": f"Login successful. Welcome {user.first_name}!",
            "role": "customer",
            "user": build_user_payload(user, request),
            "access_token": access_token,
        }, status.HTTP_200_OK

    except Exception as exc:
        logger.exception("Login error")
        return {
            "message": "An error occurred during login",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def list_vendors_payload(request: Any) -> list[dict[str, Any]]:
    """Return vendor payloads for admin/vendor views."""
    vendors = Vendor.objects.all().order_by("-created_at")
    vendor = resolve_vendor(request)
    if vendor:
        vendors = vendors.filter(pk=vendor.pk)
    return [build_vendor_payload(vendor, request) for vendor in vendors]


def list_users_payload(request: Any) -> list[dict[str, Any]]:
    """Return user payloads for admin views."""
    users = User.objects.all().order_by("-date_joined")
    return [build_user_payload(user, request) for user in users]


def _seat_label(seat: Seat) -> str:
    """Return a readable seat label for admin booking views."""
    if seat.row_label:
        return f"{seat.row_label}{seat.seat_number}"
    return str(seat.seat_number or "")


def _status_from_payment(payment_status: Optional[str]) -> Optional[str]:
    if not payment_status:
        return None
    status_value = str(payment_status).strip().lower()
    if status_value in {"paid", "completed", "success", "confirmed"}:
        return "Paid"
    if status_value in {"failed", "declined"}:
        return "Pending"
    return None


def _refund_label(refund_status: Optional[str]) -> Optional[str]:
    if not refund_status:
        return None
    status_value = str(refund_status).strip().lower()
    if status_value == "refunded":
        return "Refunded"
    if status_value == "pending":
        return "Pending"
    return refund_status


def _latest_cancel_request_status(booking: Booking) -> Optional[str]:
    """Return latest cancellation request status from notification metadata."""
    item = (
        Notification.objects.filter(
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=booking.id,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if not item:
        return None
    status_value = str((item.metadata or {}).get("request_status") or "").strip().upper()
    return status_value or None


def _percent_decimal(value: Any, default: Decimal) -> Decimal:
    """Normalize percentage inputs into 0..100 range."""
    parsed = _parse_price_amount(value)
    if parsed is None:
        parsed = default
    if parsed < Decimal("0"):
        parsed = Decimal("0")
    if parsed > Decimal("100"):
        parsed = Decimal("100")
    return _quantize_money(parsed)


def _default_cancellation_policy_payload(
    *,
    vendor: Optional[Vendor] = None,
    screen: Optional[Screen] = None,
) -> dict[str, Any]:
    return {
        "id": None,
        "vendor_id": vendor.id if vendor else None,
        "screen_id": screen.id if screen else None,
        "screen_number": screen.screen_number if screen else None,
        "allow_customer_cancellation": True,
        "is_active": True,
        "refund_percent_2h_plus": float(DEFAULT_REFUND_PERCENT_2H_PLUS),
        "refund_percent_1_to_2h": float(DEFAULT_REFUND_PERCENT_1_TO_2H),
        "refund_percent_less_than_1h": float(DEFAULT_REFUND_PERCENT_LESS_THAN_1H),
        "note": None,
        "is_default": True,
        "source": "SYSTEM_DEFAULT",
        "updated_at": None,
    }


def _serialize_cancellation_policy(policy: VendorCancellationPolicy) -> dict[str, Any]:
    screen = policy.screen
    return {
        "id": policy.id,
        "vendor_id": policy.vendor_id,
        "screen_id": policy.screen_id,
        "screen_number": screen.screen_number if screen else None,
        "allow_customer_cancellation": bool(policy.allow_customer_cancellation),
        "is_active": bool(policy.is_active),
        "refund_percent_2h_plus": float(
            _percent_decimal(policy.refund_percent_2h_plus, DEFAULT_REFUND_PERCENT_2H_PLUS)
        ),
        "refund_percent_1_to_2h": float(
            _percent_decimal(policy.refund_percent_1_to_2h, DEFAULT_REFUND_PERCENT_1_TO_2H)
        ),
        "refund_percent_less_than_1h": float(
            _percent_decimal(
                policy.refund_percent_less_than_1h,
                DEFAULT_REFUND_PERCENT_LESS_THAN_1H,
            )
        ),
        "note": policy.note,
        "is_default": policy.screen_id is None,
        "source": "VENDOR_POLICY",
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def _resolve_cancellation_policy_for_booking(booking: Booking) -> dict[str, Any]:
    """Resolve effective cancellation policy for a booking with hall-level override."""
    showtime = booking.showtime
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    if not vendor:
        payload = _default_cancellation_policy_payload()
        payload["allow_customer_cancellation"] = False
        payload["is_active"] = False
        payload["source"] = "UNSCOPED"
        return payload

    scoped = VendorCancellationPolicy.objects.filter(
        vendor_id=vendor.id,
        is_active=True,
    )
    selected = None
    if screen:
        selected = scoped.filter(screen_id=screen.id).select_related("screen").first()
    if not selected:
        selected = scoped.filter(screen__isnull=True).first()
    if selected:
        payload = _serialize_cancellation_policy(selected)
        if screen and not selected.screen_id:
            payload["screen_id"] = screen.id
            payload["screen_number"] = screen.screen_number
            payload["source"] = "VENDOR_DEFAULT_FALLBACK"
        return payload
    return _default_cancellation_policy_payload(vendor=vendor, screen=screen)


def _booking_amount_for_refund(booking: Booking, latest_payment: Optional[Payment] = None) -> Decimal:
    amount = _quantize_money(booking.total_amount or Decimal("0"))
    if amount <= Decimal("0") and latest_payment:
        amount = _quantize_money(latest_payment.amount or Decimal("0"))
    return amount


def _compute_booking_cancellation_quote(
    booking: Booking,
    latest_payment: Optional[Payment] = None,
) -> dict[str, Any]:
    """Compute cancellation eligibility and refund values from vendor policy + showtime."""
    policy = _resolve_cancellation_policy_for_booking(booking)
    showtime = booking.showtime
    amount = _booking_amount_for_refund(booking, latest_payment=latest_payment)

    if not showtime or not showtime.start_time:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Show time is unavailable.",
            "hours_until_show": None,
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "policy": policy,
        }

    now = timezone.now()
    diff = showtime.start_time - now
    hours_until_show = diff.total_seconds() / 3600

    allow_customer = bool(policy.get("allow_customer_cancellation"))
    if not allow_customer:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Cancellation is disabled by vendor policy.",
            "hours_until_show": round(hours_until_show, 2),
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "policy": policy,
        }

    if hours_until_show <= 0:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Show has already started.",
            "hours_until_show": round(hours_until_show, 2),
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "policy": policy,
        }

    if hours_until_show >= 2:
        percent = _percent_decimal(
            policy.get("refund_percent_2h_plus"),
            DEFAULT_REFUND_PERCENT_2H_PLUS,
        )
    elif hours_until_show >= 1:
        percent = _percent_decimal(
            policy.get("refund_percent_1_to_2h"),
            DEFAULT_REFUND_PERCENT_1_TO_2H,
        )
    else:
        percent = _percent_decimal(
            policy.get("refund_percent_less_than_1h"),
            DEFAULT_REFUND_PERCENT_LESS_THAN_1H,
        )

    refund_amount = _quantize_money((amount * percent) / Decimal("100"))
    if refund_amount > amount:
        refund_amount = amount
    charge_amount = _quantize_money(amount - refund_amount)

    return {
        "is_cancellable": True,
        "is_refund_available": refund_amount > Decimal("0"),
        "reason": None,
        "hours_until_show": round(hours_until_show, 2),
        "refund_percent": float(percent),
        "refund_amount": float(refund_amount),
        "cancellation_charge_amount": float(charge_amount),
        "amount_basis": float(amount),
        "policy": policy,
    }


def build_booking_payload(booking: Booking) -> dict[str, Any]:
    """Build the admin booking payload for a single booking."""
    user = booking.user
    showtime = booking.showtime
    movie = getattr(showtime, "movie", None) if showtime else None
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None

    user_name = " ".join(
        [part for part in [user.first_name, user.middle_name, user.last_name] if part]
    ).strip()
    if not user_name:
        user_name = user.email or str(user.id)

    seat_labels = []
    for booking_seat in booking.booking_seats.all():
        if booking_seat.seat:
            seat_labels.append(_seat_label(booking_seat.seat))

    latest_payment = None
    if hasattr(booking, "payments"):
        latest_payment = (
            booking.payments.all().order_by("-payment_date", "-id").first()
        )
    latest_refund = None
    if latest_payment and hasattr(latest_payment, "refunds"):
        latest_refund = (
            latest_payment.refunds.all().order_by("-refund_date", "-id").first()
        )

    payment_status = getattr(latest_payment, "payment_status", None)
    refund_status = getattr(latest_refund, "refund_status", None)
    refund_label = _refund_label(refund_status)

    total_amount = booking.total_amount
    if total_amount is None and latest_payment is not None:
        total_amount = latest_payment.amount
    if total_amount is None:
        seat_prices = [
            seat.seat_price
            for seat in booking.booking_seats.all()
            if seat.seat_price is not None
        ]
        if seat_prices:
            total_amount = sum(seat_prices)
        elif showtime and showtime.price is not None:
            total_amount = showtime.price * max(len(seat_labels), 1)

    cancel_request_status = _latest_cancel_request_status(booking)

    status_label = None
    if refund_label and str(refund_label).lower() == "refunded":
        status_label = "Refunded"
    elif str(booking.booking_status).lower() == "cancelled":
        status_label = "Cancelled"
    elif cancel_request_status == "PENDING":
        status_label = "Cancel Pending"
    else:
        status_label = _status_from_payment(payment_status)
        if not status_label and str(booking.booking_status).lower() in {"confirmed", "paid"}:
            status_label = "Paid"
    if not status_label:
        status_label = "Pending"

    show_time = None
    if showtime and showtime.start_time:
        show_time = showtime.start_time.strftime("%Y-%m-%d %H:%M")

    cancellation_quote = _compute_booking_cancellation_quote(
        booking,
        latest_payment=latest_payment,
    )
    cancellation_quote["request_status"] = cancel_request_status

    return {
        "id": booking.id,
        "userId": user.id,
        "user": user_name,
        "movie": movie.title if movie else None,
        "vendor": vendor.name if vendor else None,
        "showTime": show_time,
        "seats": ", ".join(seat_labels),
        "seatCount": len(seat_labels),
        "total": float(total_amount) if total_amount is not None else None,
        "status": status_label,
        "paymentStatus": payment_status,
        "paymentMethod": getattr(latest_payment, "payment_method", None),
        "paymentAmount": float(getattr(latest_payment, "amount", 0) or 0),
        "refundStatus": refund_label or "N/A",
        "cancellation": cancellation_quote,
        "createdAt": booking.booking_date.isoformat() if booking.booking_date else None,
    }


def list_bookings_payload(request: Any) -> list[dict[str, Any]]:
    """Return booking payloads for admin views."""
    bookings = (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .order_by("-booking_date", "-id")
    )
    vendor = resolve_vendor(request)
    if vendor:
        bookings = bookings.filter(showtime__screen__vendor_id=vendor.id)
    return [build_booking_payload(booking) for booking in bookings]


def _get_booking_or_none(booking_id: int) -> Optional[Booking]:
    return (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(pk=booking_id)
        .first()
    )


def _get_vendor_booking_or_none(request: Any, booking_id: int) -> Optional[Booking]:
    """Return a booking only when it belongs to the authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return None
    return (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(pk=booking_id, showtime__screen__vendor_id=vendor.id)
        .first()
    )


def list_customer_bookings_payload(request: Any) -> list[dict[str, Any]]:
    """Return booking payloads for the authenticated customer only."""
    customer = resolve_customer(request)
    if not customer:
        return []

    cleanup_expired_pending_bookings(user_id=customer.id)

    bookings = (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(user_id=customer.id)
        .order_by("-booking_date", "-id")
    )
    return [build_booking_payload(booking) for booking in bookings]


def _get_customer_booking_or_none(request: Any, booking_id: int) -> Optional[Booking]:
    """Return one booking only if it belongs to the authenticated customer."""
    customer = resolve_customer(request)
    if not customer:
        return None

    cleanup_expired_pending_bookings(user_id=customer.id)

    return (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(pk=booking_id, user_id=customer.id)
        .first()
    )


def build_booking_detail_payload(booking: Booking) -> dict[str, Any]:
    """Build a detailed booking payload for admin views."""
    base = build_booking_payload(booking)
    payments = []
    for payment in booking.payments.all().order_by("-payment_date", "-id"):
        refunds = []
        for refund in payment.refunds.all().order_by("-refund_date", "-id"):
            refunds.append(
                {
                    "id": refund.id,
                    "amount": float(refund.refund_amount),
                    "status": refund.refund_status,
                    "reason": refund.refund_reason,
                    "refundedAt": refund.refund_date.isoformat()
                    if refund.refund_date
                    else None,
                }
            )
        payments.append(
            {
                "id": payment.id,
                "method": payment.payment_method,
                "status": payment.payment_status,
                "amount": float(payment.amount),
                "paidAt": payment.payment_date.isoformat()
                if payment.payment_date
                else None,
                "refunds": refunds,
            }
        )

    seats = []
    for booking_seat in booking.booking_seats.all():
        seat = booking_seat.seat
        if not seat:
            continue
        seats.append(
            {
                "id": seat.id,
                "label": _seat_label(seat),
                "row": seat.row_label,
                "number": seat.seat_number,
                "type": seat.seat_type,
                "price": float(booking_seat.seat_price)
                if booking_seat.seat_price is not None
                else None,
            }
        )

    base.update(
        {
            "userEmail": booking.user.email if booking.user else None,
            "payments": payments,
            "seatsDetail": seats,
        }
    )
    return base


def _release_booking_seats(booking: Booking) -> None:
    """Release seat availability for a booking if no other active booking holds it."""
    showtime = booking.showtime
    if not showtime:
        return
    for booking_seat in booking.booking_seats.select_related("seat"):
        seat = booking_seat.seat
        if not seat:
            continue
        still_sold = BookingSeat.objects.filter(
            seat=seat,
            booking__showtime=showtime,
        ).exclude(
            booking=booking
        ).exclude(
            booking__booking_status__iexact="Cancelled"
        ).exists()
        if still_sold:
            continue
        SeatAvailability.objects.filter(seat=seat, showtime=showtime).update(
            seat_status=SEAT_STATUS_AVAILABLE,
            locked_until=None,
        )


def cleanup_expired_pending_bookings(
    *,
    user_id: Optional[int] = None,
    ttl_seconds: Optional[int] = None,
) -> int:
    """Cancel stale pending eSewa bookings and release held seats.

    This keeps booking history accurate (Pending -> Cancelled) and frees seats if
    a payment was not completed within the hold window.
    """
    configured_ttl = ttl_seconds if ttl_seconds is not None else getattr(
        settings,
        "ESEWA_PENDING_TTL_SECONDS",
        1800,
    )
    try:
        hold_seconds = int(configured_ttl)
    except (TypeError, ValueError):
        hold_seconds = 1800
    hold_seconds = max(60, hold_seconds)

    cutoff = timezone.now() - timedelta(seconds=hold_seconds)
    pending_payments = Payment.objects.select_related("booking").filter(
        payment_status__iexact="Pending",
        payment_method__startswith=ESEWA_PAYMENT_METHOD_PREFIX,
        payment_date__lte=cutoff,
        booking__booking_status__iexact=BOOKING_STATUS_PENDING,
    )
    if user_id:
        pending_payments = pending_payments.filter(booking__user_id=user_id)

    expired = 0
    processed_booking_ids: set[int] = set()
    for payment in pending_payments.order_by("payment_date", "id"):
        booking = payment.booking
        if not booking or booking.id in processed_booking_ids:
            continue

        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().filter(pk=booking.id).first()
            if not locked_booking:
                continue
            if str(locked_booking.booking_status).strip().lower() != BOOKING_STATUS_PENDING.lower():
                continue

            _release_booking_seats(locked_booking)
            BookingSeat.objects.filter(booking=locked_booking).delete()
            locked_booking.booking_status = BOOKING_STATUS_CANCELLED
            locked_booking.save(update_fields=["booking_status"])
            Payment.objects.filter(
                booking=locked_booking,
                payment_status__iexact="Pending",
            ).update(payment_status="Failed")

        processed_booking_ids.add(booking.id)
        expired += 1

    return expired


def admin_cancel_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Cancel a booking and release seats."""
    if str(booking.booking_status).lower() == "cancelled":
        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    with transaction.atomic():
        booking.booking_status = "Cancelled"
        booking.save(update_fields=["booking_status"])
        _release_booking_seats(booking)

    return {
        "message": "Booking cancelled",
        "booking": build_booking_payload(booking),
    }, status.HTTP_200_OK


def _get_booking_vendor(booking: Booking) -> Optional[Vendor]:
    showtime = booking.showtime if booking else None
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    return vendor


def _find_pending_cancel_request_notification(
    booking: Booking,
    vendor: Vendor,
) -> Optional[Notification]:
    pending = (
        Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=booking.id,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if not pending:
        return None
    status_value = str((pending.metadata or {}).get("request_status") or "").upper()
    return pending if status_value in {"", "PENDING"} else None


def _close_cancel_request_notifications(
    booking: Booking,
    *,
    resolved_by: str,
    resolved_status: str,
) -> None:
    """Mark pending vendor cancel-request notifications as resolved."""
    rows = Notification.objects.filter(
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        metadata__booking_id=booking.id,
        metadata__request_status="PENDING",
    )
    for item in rows:
        metadata = dict(item.metadata or {})
        metadata["request_status"] = resolved_status
        metadata["resolved_by"] = resolved_by
        metadata["resolved_at"] = timezone.now().isoformat()
        item.metadata = metadata
        item.save(update_fields=["metadata"])


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
        send_email_too=False,
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
    charge_amount = _quantize_money((Decimal(str(quote.get("amount_basis") or 0)) - refunded))
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
        message = (
            f"Your booking #{booking.id} has been cancelled and refund of NPR {refunded} was processed."
        )
    else:
        event_type = Notification.EVENT_BOOKING_CANCELLED
        title = "Booking cancelled"
        message = (
            f"Your booking #{booking.id} has been cancelled. No refund is applicable under current policy."
        )

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


def _apply_booking_cancellation_with_policy(
    request: Any,
    booking: Booking,
    *,
    actor_label: str,
    require_policy_eligibility: bool,
    require_payment_for_refund: bool = False,
    close_pending_cancel_requests: bool = False,
) -> tuple[dict[str, Any], int]:
    """Cancel booking and apply refund according to effective vendor policy."""
    latest_payment = booking.payments.all().order_by("-payment_date", "-id").first()

    if str(booking.booking_status).lower() == "cancelled":
        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    quote = _compute_booking_cancellation_quote(booking, latest_payment=latest_payment)
    if require_policy_eligibility and not quote.get("is_cancellable"):
        return {
            "message": str(quote.get("reason") or "Cancellation is not allowed for this booking."),
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    reason_value = str(
        coalesce(get_payload(request), "reason", "refund_reason", "cancellation_reason") or ""
    ).strip()
    reason = reason_value or f"Cancelled by {actor_label}"
    refund_amount = _quantize_money(quote.get("refund_amount") or Decimal("0"))

    with transaction.atomic():
        locked_booking = Booking.objects.select_for_update().filter(pk=booking.id).first()
        if not locked_booking:
            return {"message": "Booking not found"}, status.HTTP_404_NOT_FOUND
        if str(locked_booking.booking_status).lower() == "cancelled":
            return {
                "message": "Booking already cancelled",
                "booking": build_booking_payload(locked_booking),
            }, status.HTTP_200_OK

        locked_payment = (
            Payment.objects.select_for_update()
            .filter(booking_id=locked_booking.id)
            .order_by("-payment_date", "-id")
            .first()
        )
        if require_payment_for_refund and not locked_payment:
            return {
                "message": "Payment record not found for booking.",
                "booking": build_booking_payload(locked_booking),
            }, status.HTTP_404_NOT_FOUND

        if locked_payment:
            locked_refund = (
                Refund.objects.select_for_update()
                .filter(payment_id=locked_payment.id)
                .order_by("-refund_date", "-id")
                .first()
            )
            if locked_refund and str(locked_refund.refund_status).lower() == "refunded":
                refund_amount = Decimal("0")
            elif refund_amount > Decimal("0"):
                Refund.objects.create(
                    payment=locked_payment,
                    refund_amount=refund_amount,
                    refund_reason=reason,
                    refund_status="Refunded",
                )
                full_amount = _quantize_money(locked_payment.amount or Decimal("0"))
                if refund_amount >= full_amount:
                    locked_payment.payment_status = "Refunded"
                else:
                    locked_payment.payment_status = "Partially Refunded"
                locked_payment.save(update_fields=["payment_status"])

        locked_booking.booking_status = BOOKING_STATUS_CANCELLED
        locked_booking.save(update_fields=["booking_status"])
        _release_booking_seats(locked_booking)

        if close_pending_cancel_requests:
            _close_cancel_request_notifications(
                locked_booking,
                resolved_by=actor_label,
                resolved_status="APPROVED",
            )

        if refund_amount > Decimal("0"):
            _reverse_vendor_booking_earning(locked_booking, reason=reason)

    refreshed = _get_booking_or_none(booking.id) or booking
    _notify_customer_refund_result(
        refreshed,
        quote=quote,
        refund_amount=refund_amount,
        actor_label=actor_label,
        reason=reason,
    )

    message = "Booking cancelled"
    if refund_amount > Decimal("0"):
        message = "Booking cancelled and refund processed"
    elif quote.get("is_cancellable") and not quote.get("is_refund_available"):
        message = "Booking cancelled. Refund not available for current policy window"
    return {
        "message": message,
        "booking": build_booking_payload(refreshed),
        "cancellation": quote,
    }, status.HTTP_200_OK


def customer_cancel_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Submit customer cancellation/refund request for vendor approval."""
    if str(booking.booking_status).lower() == "cancelled":
        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    quote = _compute_booking_cancellation_quote(booking, latest_payment=_get_latest_payment_for_booking(booking))
    showtime = booking.showtime
    if not showtime or not showtime.start_time:
        return {
            "message": "Show time is unavailable.",
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST
    if showtime.start_time <= timezone.now():
        return {
            "message": "Show has already started.",
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    vendor = _get_booking_vendor(booking)
    if not vendor:
        return {"message": "Vendor not found for booking."}, status.HTTP_400_BAD_REQUEST

    existing = _find_pending_cancel_request_notification(booking, vendor)
    if existing:
        return {
            "message": "Cancellation request is already pending vendor approval.",
            "request_id": existing.id,
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    payload = get_payload(request)
    reason = str(coalesce(payload, "reason", "refund_reason", "cancellation_reason") or "").strip() or None

    vendor_notification = _notify_vendor_cancel_request(
        booking,
        vendor=vendor,
        quote=quote,
        reason=reason,
    )
    _notify_customer_cancel_request_submitted(
        booking,
        quote=quote,
        request_id=vendor_notification.id,
    )

    return {
        "message": "Cancellation request submitted. Vendor will review and process refund manually.",
        "request_id": vendor_notification.id,
        "cancellation": quote,
        "booking": build_booking_payload(booking),
    }, status.HTTP_202_ACCEPTED


def vendor_cancel_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Cancel vendor-owned booking and apply policy-driven refund/charge."""
    return _apply_booking_cancellation_with_policy(
        request,
        booking,
        actor_label="vendor",
        require_policy_eligibility=False,
        require_payment_for_refund=False,
        close_pending_cancel_requests=True,
    )


def vendor_refund_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Vendor manual refund action; releases seats only after refund processing."""
    return _apply_booking_cancellation_with_policy(
        request,
        booking,
        actor_label="vendor",
        require_policy_eligibility=False,
        require_payment_for_refund=True,
        close_pending_cancel_requests=True,
    )


def admin_refund_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Refund a booking and release seats."""
    latest_payment = booking.payments.all().order_by("-payment_date", "-id").first()
    if not latest_payment:
        return {"message": "Payment record not found for booking."}, status.HTTP_404_NOT_FOUND

    latest_refund = latest_payment.refunds.all().order_by("-refund_date", "-id").first()
    if latest_refund and str(latest_refund.refund_status).lower() == "refunded":
        return {
            "message": "Booking already refunded",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    payload = get_payload(request)
    reason = str(payload.get("reason") or payload.get("refund_reason") or "").strip() or None
    amount_value = payload.get("amount") or payload.get("refund_amount")
    try:
        amount = float(amount_value) if amount_value is not None else float(latest_payment.amount)
    except (TypeError, ValueError):
        amount = float(latest_payment.amount)

    with transaction.atomic():
        Refund.objects.create(
            payment=latest_payment,
            refund_amount=amount,
            refund_reason=reason,
            refund_status="Refunded",
        )
        latest_payment.payment_status = "Refunded"
        latest_payment.save(update_fields=["payment_status"])
        booking.booking_status = "Cancelled"
        booking.save(update_fields=["booking_status"])
        _release_booking_seats(booking)
        if Decimal(str(amount)) > Decimal("0"):
            _reverse_vendor_booking_earning(booking, reason=reason or "Admin refund")

    return {
        "message": "Booking refunded",
        "booking": build_booking_payload(booking),
    }, status.HTTP_200_OK


def admin_delete_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Delete a booking and release seats."""
    with transaction.atomic():
        _release_booking_seats(booking)
        booking.delete()
    return {"message": "Booking deleted"}, status.HTTP_200_OK


def create_admin_user(request: Any) -> tuple[dict[str, Any], int]:
    """Create a user account from the admin panel."""
    payload = get_payload(request)

    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    middle_name = str(payload.get("middle_name") or "").strip() or None
    email = str(payload.get("email") or "").strip().lower()
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    password = str(payload.get("password") or "")
    dob_value = payload.get("dob")
    dob = parse_date(dob_value)
    is_active = parse_bool(payload.get("is_active"), default=True)

    if not first_name or not last_name or not email or not raw_phone or not password:
        return {
            "message": "First name, last name, email, phone number, and password are required"
        }, status.HTTP_400_BAD_REQUEST

    if dob is None:
        return {"message": "Date of birth is required"}, status.HTTP_400_BAD_REQUEST

    if not phone_number or not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if User.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST

    if User.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST

    if username and User.objects.filter(username__iexact=username).exists():
        return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST

    if not username:
        username = generate_unique_username(first_name, last_name)

    user = User(
        phone_number=phone_number,
        email=email,
        dob=dob,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        username=username,
        is_active=is_active,
    )
    user.set_password(password)
    user.save()

    return {
        "message": "User created",
        "user": build_user_payload(user, request),
    }, status.HTTP_201_CREATED


def update_admin_user(user: User, request: Any) -> tuple[dict[str, Any], int]:
    """Update a user account from the admin panel."""
    payload = get_payload(request)

    if "first_name" in payload:
        first_name = str(payload.get("first_name") or "").strip()
        if not first_name:
            return {"message": "First name is required"}, status.HTTP_400_BAD_REQUEST
        user.first_name = first_name

    if "last_name" in payload:
        last_name = str(payload.get("last_name") or "").strip()
        if not last_name:
            return {"message": "Last name is required"}, status.HTTP_400_BAD_REQUEST
        user.last_name = last_name

    if "middle_name" in payload:
        middle_name = str(payload.get("middle_name") or "").strip() or None
        user.middle_name = middle_name

    if "email" in payload:
        email = str(payload.get("email") or "").strip().lower()
        if not email:
            return {"message": "Email is required"}, status.HTTP_400_BAD_REQUEST
        if User.objects.filter(email__iexact=email).exclude(pk=user.id).exists():
            return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST
        user.email = email

    if "phone_number" in payload:
        raw_phone = str(payload.get("phone_number") or "").strip()
        phone_number = normalize_phone_number(raw_phone)
        if not raw_phone:
            return {"message": "Phone number is required"}, status.HTTP_400_BAD_REQUEST
        if not phone_number or not PHONE_REGEX.match(phone_number):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if (
            User.objects.filter(phone_number=phone_number)
            .exclude(pk=user.id)
            .exists()
        ):
            return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST
        user.phone_number = phone_number

    if "username" in payload:
        username = str(payload.get("username") or "").strip() or None
        if username and User.objects.filter(username__iexact=username).exclude(pk=user.id).exists():
            return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST
        user.username = username

    if "dob" in payload:
        dob_value = payload.get("dob")
        dob = parse_date(dob_value)
        if dob is None:
            return {"message": "Invalid date of birth"}, status.HTTP_400_BAD_REQUEST
        user.dob = dob

    if "is_active" in payload:
        user.is_active = parse_bool(payload.get("is_active"), default=True)

    if "password" in payload:
        password = str(payload.get("password") or "")
        if password:
            user.set_password(password)

    user.save()
    return {
        "message": "User updated",
        "user": build_user_payload(user, request),
    }, status.HTTP_200_OK


def create_vendor(request: Any) -> tuple[dict[str, Any], int]:
    """Create a vendor account."""
    payload = get_payload(request)

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    theatre = (
        str(payload.get("theatre") or payload.get("theatre_name") or "").strip()
        or None
    )
    city = str(payload.get("city") or "").strip() or None
    commission_percent = _parse_price_amount(
        coalesce(payload, "commission_percent", "commissionPercent", "platform_commission_percent")
    )
    if commission_percent is not None and (commission_percent < Decimal("0") or commission_percent > Decimal("100")):
        return {"message": "commission_percent must be between 0 and 100."}, status.HTTP_400_BAD_REQUEST
    status_label = str(payload.get("status") or DEFAULT_VENDOR_STATUS).strip() or DEFAULT_VENDOR_STATUS
    status_label = status_label.title()

    if not name or not email or not password:
        return {
            "message": "Name, email, and password are required"
        }, status.HTTP_400_BAD_REQUEST

    if Vendor.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST

    if raw_phone and not phone_number:
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and Vendor.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST

    if username and Vendor.objects.filter(username__iexact=username).exists():
        return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST

    is_active = status_label.lower() != STATUS_BLOCKED.lower()
    vendor = Vendor(
        name=name,
        email=email,
        phone_number=phone_number or None,
        username=username,
        theatre=theatre,
        city=city,
        commission_percent=commission_percent,
        status=status_label,
        is_active=is_active,
    )
    vendor.set_password(password)
    vendor.save()

    return {
        "message": "Vendor created",
        "vendor": build_vendor_payload(vendor, request),
    }, status.HTTP_201_CREATED


def list_vendor_staff_accounts(request: Any) -> tuple[dict[str, Any], int]:
    """List staff accounts for the authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    staff_accounts = VendorStaff.objects.filter(vendor_id=vendor.id).order_by("-created_at", "-id")
    return {
        "staff": [build_vendor_staff_payload(staff) for staff in staff_accounts],
    }, status.HTTP_200_OK


def _username_taken_across_accounts(username: str, current_staff_id: Optional[int] = None) -> bool:
    """Return whether a username already exists across account tables."""
    normalized = str(username or "").strip()
    if not normalized:
        return False
    if Admin.objects.filter(username__iexact=normalized).exists():
        return True
    if Vendor.objects.filter(username__iexact=normalized).exists():
        return True
    if User.objects.filter(username__iexact=normalized).exists():
        return True

    query = VendorStaff.objects.filter(username__iexact=normalized)
    if current_staff_id:
        query = query.exclude(id=current_staff_id)
    return query.exists()


def create_vendor_staff_account(request: Any) -> tuple[dict[str, Any], int]:
    """Create a staff sub-account for the authenticated vendor owner."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    full_name = str(payload.get("full_name") or payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    role = str(payload.get("role") or VendorStaff.ROLE_CASHIER).strip().upper()

    if not full_name or not email or not password:
        return {
            "message": "Full name, email, and password are required."
        }, status.HTTP_400_BAD_REQUEST

    if role not in {VendorStaff.ROLE_CASHIER, VendorStaff.ROLE_MANAGER}:
        return {"message": "Invalid staff role."}, status.HTTP_400_BAD_REQUEST

    if raw_phone and not phone_number:
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if Admin.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists() or Vendor.objects.filter(email__iexact=email).exists() or VendorStaff.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists."}, status.HTTP_400_BAD_REQUEST

    if phone_number and VendorStaff.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists."}, status.HTTP_400_BAD_REQUEST

    if username and _username_taken_across_accounts(username):
        return {"message": "Username already exists."}, status.HTTP_400_BAD_REQUEST

    staff = VendorStaff(
        vendor_id=vendor.id,
        full_name=full_name,
        email=email,
        phone_number=phone_number or None,
        username=username,
        role=role,
        is_active=parse_bool(payload.get("is_active"), default=True),
    )
    staff.set_password(password)
    staff.save()

    return {
        "message": "Vendor staff account created.",
        "staff": build_vendor_staff_payload(staff),
    }, status.HTTP_201_CREATED


def update_vendor_staff_account(
    request: Any,
    staff: VendorStaff,
) -> tuple[dict[str, Any], int]:
    """Update a vendor staff account."""
    payload = get_payload(request)

    if "full_name" in payload or "name" in payload:
        full_name = str(payload.get("full_name") or payload.get("name") or "").strip()
        if not full_name:
            return {"message": "Full name cannot be empty."}, status.HTTP_400_BAD_REQUEST
        staff.full_name = full_name

    if "email" in payload:
        email = str(payload.get("email") or "").strip().lower()
        if not email:
            return {"message": "Email cannot be empty."}, status.HTTP_400_BAD_REQUEST
        if Admin.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists() or Vendor.objects.filter(email__iexact=email).exists() or VendorStaff.objects.filter(email__iexact=email).exclude(id=staff.id).exists():
            return {"message": "Email already exists."}, status.HTTP_400_BAD_REQUEST
        staff.email = email

    if "phone_number" in payload:
        raw_phone = str(payload.get("phone_number") or "").strip()
        if not raw_phone:
            staff.phone_number = None
        else:
            phone_number = normalize_phone_number(raw_phone)
            if not phone_number or not PHONE_REGEX.match(phone_number):
                return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
            if VendorStaff.objects.filter(phone_number=phone_number).exclude(id=staff.id).exists():
                return {"message": "Phone number already exists."}, status.HTTP_400_BAD_REQUEST
            staff.phone_number = phone_number

    if "username" in payload:
        username = str(payload.get("username") or "").strip() or None
        if username and _username_taken_across_accounts(username, current_staff_id=staff.id):
            return {"message": "Username already exists."}, status.HTTP_400_BAD_REQUEST
        staff.username = username

    if "role" in payload:
        role = str(payload.get("role") or "").strip().upper()
        if role not in {VendorStaff.ROLE_CASHIER, VendorStaff.ROLE_MANAGER}:
            return {"message": "Invalid staff role."}, status.HTTP_400_BAD_REQUEST
        staff.role = role

    if "is_active" in payload:
        staff.is_active = parse_bool(payload.get("is_active"), default=staff.is_active)

    if "password" in payload:
        raw_password = str(payload.get("password") or "")
        if raw_password:
            staff.set_password(raw_password)

    staff.save()
    return {
        "message": "Vendor staff account updated.",
        "staff": build_vendor_staff_payload(staff),
    }, status.HTTP_200_OK


def list_cinemas_payload(request: Any, city: Optional[str] = None) -> list[dict[str, Any]]:
    """Return cinema vendor payloads for public views."""
    vendors = selectors.list_cinema_vendors(city=city)
    return build_cinemas_payload(vendors, request)


def build_cinemas_payload(
    vendors: Iterable[Vendor], request: Optional[Any] = None
) -> list[dict[str, Any]]:
    """Build cinema payloads for dropdowns and listings."""
    payload = []
    used_slugs = set()
    for vendor in vendors:
        display_name = (
            vendor.name
            or vendor.theatre
            or vendor.username
            or vendor.email
            or f"Vendor {vendor.id}"
        )
        slug_base = slugify_text(display_name)
        slug = slug_base or f"vendor-{vendor.id}"
        if slug in used_slugs:
            slug = f"{slug}-{vendor.id}"
        used_slugs.add(slug)
        payload.append(
            {
                "id": vendor.id,
                "name": display_name,
                "theatre": vendor.theatre,
                "city": vendor.city,
                "slug": slug,
                "short": short_label(display_name),
                "profile_image": get_profile_image_url(request, vendor),
            }
        )
    return payload


def _sync_collab_details(slide: HomeSlide, payload: dict[str, Any]) -> Optional[Any]:
    """Sync collaboration details for a slide."""
    if slide.slide_type != HomeSlide.SLIDE_COLLAB:
        if hasattr(slide, "collab_details"):
            slide.collab_details.delete()
        return None

    instance = getattr(slide, "collab_details", None)
    serializer = CollabDetailsAdminSerializer(
        instance=instance,
        data=payload,
        partial=instance is not None,
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(slide=slide)


def create_home_slide(data: dict[str, Any]) -> HomeSlide:
    """Create a home slide with optional collaboration details."""
    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, data)
    return slide


def update_home_slide(slide: HomeSlide, data: dict[str, Any]) -> HomeSlide:
    """Update a home slide with optional collaboration details."""
    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(slide, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, data)
    return slide


def toggle_home_slide(slide: HomeSlide) -> HomeSlide:
    """Toggle the active state for a home slide."""
    slide.is_active = not slide.is_active
    slide.save(update_fields=["is_active"])
    return slide


def create_collaborator(data: dict[str, Any]) -> Collaborator:
    """Create a collaborator."""
    serializer = CollaboratorAdminSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def update_collaborator(collaborator: Collaborator, data: dict[str, Any]) -> Collaborator:
    """Update a collaborator."""
    serializer = CollaboratorAdminSerializer(collaborator, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def toggle_collaborator(collaborator: Collaborator) -> Collaborator:
    """Toggle collaborator active state."""
    collaborator.is_active = not collaborator.is_active
    collaborator.save(update_fields=["is_active"])
    return collaborator


def create_banner(data: dict[str, Any]) -> Banner:
    """Create a banner."""
    serializer = BannerCreateUpdateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def update_banner(banner: Banner, data: dict[str, Any]) -> Banner:
    """Update a banner."""
    serializer = BannerCreateUpdateSerializer(banner, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def _coerce_list(value: Any) -> Optional[list[Any]]:
    """Normalize a payload field into a list if possible."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return None
    return None


def _normalize_credit_item(
    item: Any, default_role_type: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Normalize a credit payload into the canonical schema."""
    if not isinstance(item, dict):
        return None
    role_type = (
        item.get("role_type")
        or item.get("roleType")
        or item.get("credit_type")
        or item.get("creditType")
        or default_role_type
    )
    if not role_type:
        return None
    role_value = (
        item.get("role")
        or item.get("role_name")
        or item.get("roleName")
        or item.get("character_name")
        or item.get("characterName")
        or item.get("job_title")
        or item.get("jobTitle")
        or item.get("department")
    )
    character_name = (
        item.get("character_name")
        or item.get("characterName")
        or item.get("role_name")
        or item.get("roleName")
    )
    job_title = item.get("job_title") or item.get("jobTitle") or item.get("department")
    if not character_name and role_type == MovieCredit.ROLE_CAST:
        character_name = role_value
    if not job_title and role_type == MovieCredit.ROLE_CREW:
        job_title = role_value
    person_payload = item.get("person") or item.get("person_data") or {}
    if not person_payload:
        name_value = item.get("full_name") or item.get("fullName") or item.get("name")
        if name_value:
            person_payload = {"full_name": name_value}
    return {
        "id": item.get("id"),
        "role_type": role_type,
        "character_name": character_name,
        "job_title": job_title,
        "position": item.get("position") or item.get("order"),
        "person_id": item.get("person_id") or item.get("personId"),
        "person": person_payload,
    }


def _extract_credits_payload(payload: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """Extract normalized credits payload from request data."""
    if "credits" in payload:
        return _coerce_list(payload.get("credits")) or []
    cast = _coerce_list(payload.get("cast"))
    crew = _coerce_list(payload.get("crew"))
    if cast is None and crew is None:
        return None
    credits = []
    if cast:
        credits.extend(
            filter(
                None,
                [
                    _normalize_credit_item(item, default_role_type=MovieCredit.ROLE_CAST)
                    for item in cast
                ],
            )
        )
    if crew:
        credits.extend(
            filter(
                None,
                [
                    _normalize_credit_item(item, default_role_type=MovieCredit.ROLE_CREW)
                    for item in crew
                ],
            )
        )
    return credits


def _resolve_person_from_credit(request: Any, credit: dict[str, Any]) -> Optional[Person]:
    """Resolve or create a person from a credit payload."""
    person_id = credit.get("person_id")
    if person_id:
        return Person.objects.filter(pk=person_id).first()
    person_data = credit.get("person") if isinstance(credit.get("person"), dict) else {}
    if person_data.get("id"):
        return Person.objects.filter(pk=person_data.get("id")).first()
    full_name = (person_data.get("full_name") or person_data.get("fullName") or "").strip()
    if not full_name:
        return None
    existing = Person.objects.filter(full_name__iexact=full_name).first()
    if existing:
        return existing
    upload_key = person_data.get("photo_upload_key") or person_data.get("photoUploadKey")
    uploaded_photo = request.FILES.get(upload_key) if upload_key else None
    return Person.objects.create(
        full_name=full_name,
        photo=uploaded_photo or person_data.get("photo"),
        photo_url=person_data.get("photo_url") or person_data.get("photoUrl"),
        bio=person_data.get("bio"),
        date_of_birth=parse_date(person_data.get("date_of_birth") or person_data.get("dateOfBirth")),
        nationality=person_data.get("nationality"),
        instagram=person_data.get("instagram"),
        imdb=person_data.get("imdb"),
        facebook=person_data.get("facebook"),
    )


def _sync_movie_credits(
    request: Any, movie: Movie, credits_payload: Optional[list[dict[str, Any]]]
) -> None:
    """Synchronize movie credits with the provided payload."""
    if credits_payload is None:
        return
    existing = {credit.id: credit for credit in movie.credits.all()}
    seen_ids = set()
    for idx, item in enumerate(credits_payload):
        credit = _normalize_credit_item(item, default_role_type=item.get("role_type"))
        if not credit:
            continue
        person = _resolve_person_from_credit(request, credit)
        if not person:
            continue
        position = credit.get("position")
        if position is None:
            position = idx + 1
        credit_id = credit.get("id")
        if credit_id and credit_id in existing:
            instance = existing[credit_id]
            instance.role_type = credit.get("role_type")
            instance.character_name = credit.get("character_name")
            instance.job_title = credit.get("job_title")
            instance.position = position
            instance.person = person
            instance.save()
            seen_ids.add(instance.id)
        else:
            instance = MovieCredit.objects.create(
                movie=movie,
                person=person,
                role_type=credit.get("role_type"),
                character_name=credit.get("character_name"),
                job_title=credit.get("job_title"),
                position=position,
            )
            seen_ids.add(instance.id)
    for credit_id, instance in existing.items():
        if credit_id not in seen_ids:
            instance.delete()


def create_movie(request: Any) -> tuple[dict[str, Any], int]:
    """Create a movie (admin/vendor)."""
    admin_actor = resolve_admin(request)
    vendor_actor = resolve_vendor(request)
    if not admin_actor and not vendor_actor:
        return {"message": "Admin or vendor access required"}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    title = str(coalesce(payload, "title", "name", default="") or "").strip()
    if not title:
        return {"message": "Title is required"}, status.HTTP_400_BAD_REQUEST

    duration_minutes_value = coalesce(payload, "durationMinutes", "duration_minutes")
    try:
        duration_minutes_value = (
            int(duration_minutes_value) if duration_minutes_value is not None else None
        )
    except (TypeError, ValueError):
        duration_minutes_value = None

    movie = Movie(
        title=title,
        short_description=coalesce(payload, "shortDescription", "short_description"),
        description=coalesce(payload, "description", "synopsis"),
        long_description=coalesce(payload, "longDescription", "long_description"),
        language=coalesce(payload, "language", "lang"),
        genre=coalesce(payload, "genre", "category"),
        duration=coalesce(payload, "duration", "runtime"),
        duration_minutes=duration_minutes_value,
        rating=coalesce(payload, "rating", "censor"),
        release_date=parse_date(coalesce(payload, "releaseDate", "release_date")),
        poster_url=coalesce(payload, "posterUrl", "poster_url", "poster"),
        trailer_url=coalesce(payload, "trailerUrl", "trailer_url", "trailer"),
        status=coalesce(payload, "status", default=Movie.STATUS_COMING_SOON),
        is_active=coalesce(payload, "isActive", "is_active", default=True),
    )
    poster_image = request.FILES.get("poster_image") or request.FILES.get("posterImage")
    banner_image = request.FILES.get("banner_image") or request.FILES.get("bannerImage")
    if poster_image:
        movie.poster_image = poster_image
    if banner_image:
        movie.banner_image = banner_image
    movie.save()
    genre_ids = coalesce(payload, "genreIds", "genres")
    if genre_ids:
        try:
            movie.genres.set(genre_ids)
        except Exception:
            pass
    _sync_movie_credits(request, movie, _extract_credits_payload(payload))
    return {"movie": build_movie_payload(movie, request=request)}, status.HTTP_201_CREATED


def update_movie(request: Any, movie: Movie) -> tuple[dict[str, Any], int]:
    """Update a movie (admin only)."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    for field, keys in {
        "title": ("title", "name"),
        "short_description": ("shortDescription", "short_description"),
        "description": ("description", "synopsis"),
        "long_description": ("longDescription", "long_description"),
        "language": ("language", "lang"),
        "genre": ("genre", "category"),
        "duration": ("duration", "runtime"),
        "rating": ("rating", "censor"),
        "poster_url": ("posterUrl", "poster_url", "poster"),
        "trailer_url": ("trailerUrl", "trailer_url", "trailer"),
        "status": ("status",),
        "is_active": ("isActive", "is_active"),
    }.items():
        value = coalesce(payload, *keys)
        if value is not None:
            setattr(movie, field, value)

    duration_minutes_value = coalesce(payload, "durationMinutes", "duration_minutes")
    if duration_minutes_value is not None:
        try:
            movie.duration_minutes = int(duration_minutes_value)
        except (TypeError, ValueError):
            movie.duration_minutes = None

    release_value = coalesce(payload, "releaseDate", "release_date")
    if release_value is not None:
        movie.release_date = parse_date(release_value)

    poster_image = request.FILES.get("poster_image") or request.FILES.get("posterImage")
    banner_image = request.FILES.get("banner_image") or request.FILES.get("bannerImage")
    if poster_image:
        movie.poster_image = poster_image
    if banner_image:
        movie.banner_image = banner_image

    movie.save()
    genre_ids = coalesce(payload, "genreIds", "genres")
    if genre_ids is not None:
        try:
            movie.genres.set(genre_ids)
        except Exception:
            pass
    _sync_movie_credits(request, movie, _extract_credits_payload(payload))
    return {"movie": build_movie_payload(movie, request=request)}, status.HTTP_200_OK


def delete_movie(request: Any, movie: Movie) -> tuple[dict[str, Any], int]:
    """Delete a movie (admin only)."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    movie.delete()
    return {"message": "Movie deleted"}, status.HTTP_200_OK


def _parse_show_dates(payload: dict[str, Any], base_date: Optional[date_cls]) -> list[date_cls]:
    """Build the list of dates for show creation from explicit dates or repeat days."""
    raw_dates = coalesce(payload, "dates", "show_dates", "showDates")
    date_items: list[Any] = []

    if isinstance(raw_dates, list):
        date_items = raw_dates
    elif isinstance(raw_dates, str):
        parsed_list = _coerce_list(raw_dates)
        if isinstance(parsed_list, list):
            date_items = parsed_list
        else:
            date_items = [part.strip() for part in raw_dates.split(",") if part.strip()]

    parsed_dates: list[date_cls] = []
    seen: set[str] = set()
    for item in date_items:
        parsed = parse_date(item)
        if not parsed:
            continue
        iso = parsed.isoformat()
        if iso in seen:
            continue
        seen.add(iso)
        parsed_dates.append(parsed)

    if parsed_dates:
        return parsed_dates

    repeat_days_raw = coalesce(payload, "repeatDays", "repeat_days", default=1)
    try:
        repeat_days = int(repeat_days_raw)
    except (TypeError, ValueError):
        repeat_days = 1

    if repeat_days < 1:
        repeat_days = 1
    if repeat_days > 60:
        repeat_days = 60

    if not base_date:
        return []

    return [base_date + timedelta(days=offset) for offset in range(repeat_days)]


def create_show(request: Any) -> tuple[dict[str, Any], int]:
    """Create a show entry (admin/vendor only)."""
    if not is_authenticated(request):
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    vendor_id = coalesce(payload, "vendorId", "vendor_id")
    movie_id = coalesce(payload, "movieId", "movie_id")

    if not vendor_id or not movie_id:
        return {
            "message": "vendorId and movieId are required"
        }, status.HTTP_400_BAD_REQUEST

    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    if vendor_actor and str(vendor_id) != str(vendor_actor.id):
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN
    if not vendor_actor and not admin_actor:
        return {"message": "Vendor access required"}, status.HTTP_403_FORBIDDEN

    if vendor_actor:
        vendor_id = vendor_actor.id

    try:
        vendor = Vendor.objects.get(pk=vendor_id)
    except Vendor.DoesNotExist:
        return {"message": "Vendor not found"}, status.HTTP_404_NOT_FOUND

    try:
        movie = Movie.objects.get(pk=movie_id)
    except Movie.DoesNotExist:
        return {"message": "Movie not found"}, status.HTTP_404_NOT_FOUND

    # Ensure scheduled titles are visible in customer catalog.
    if not movie.is_active:
        movie.is_active = True
        movie.save(update_fields=["is_active"])

    base_show_date = parse_date(coalesce(payload, "date", "show_date", "showDate"))
    start_time = parse_time(coalesce(payload, "start", "start_time", "startTime"))
    end_time = parse_time(coalesce(payload, "end", "end_time", "endTime"))
    hall = " ".join(str(coalesce(payload, "hall") or "").split())

    if not hall:
        return {"message": "hall is required"}, status.HTTP_400_BAD_REQUEST

    if not start_time:
        return {"message": "show date and start time are required"}, status.HTTP_400_BAD_REQUEST

    show_dates = _parse_show_dates(payload, base_show_date)
    if not show_dates:
        return {"message": "show date and start time are required"}, status.HTTP_400_BAD_REQUEST

    if end_time and end_time <= start_time:
        return {"message": "end time must be after start time"}, status.HTTP_400_BAD_REQUEST

    created_payloads: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for show_date in show_dates:
        conflict_qs = Show.objects.filter(
            vendor=vendor,
            hall__iexact=hall,
            show_date=show_date,
            start_time=start_time,
        )
        if conflict_qs.exists():
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "duplicate",
                }
            )
            continue

        show = Show(
            vendor=vendor,
            movie=movie,
            hall=hall,
            slot=coalesce(payload, "slot"),
            screen_type=coalesce(payload, "screenType", "screen_type"),
            price=coalesce(payload, "price"),
            status=_normalize_show_status(coalesce(payload, "status")),
            listing_status=coalesce(
                payload, "listingStatus", "listing_status", default="Now Showing"
            ),
            show_date=show_date,
            start_time=start_time,
            end_time=end_time,
        )
        try:
            show.save()
        except IntegrityError:
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "duplicate",
                }
            )
            continue

        screen, _ = Screen.objects.get_or_create(
            vendor_id=vendor.id,
            screen_number=hall,
            defaults={
                "screen_type": show.screen_type,
                "status": "Active",
            },
        )
        show_screen_type = str(show.screen_type or "").strip()
        existing_screen_type = str(screen.screen_type or "").strip()
        if show_screen_type and show_screen_type != existing_screen_type:
            screen.screen_type = show_screen_type
            screen.save(update_fields=["screen_type"])

        created_payloads.append(build_show_payload(show))

    if not created_payloads:
        date_label = show_dates[0].isoformat() if show_dates else "selected date"
        return {
            "message": f"Hall {hall} already has a show at {start_time.strftime('%H:%M')} on {date_label}. Choose another hall or time.",
            "created_count": 0,
            "requested_count": len(show_dates),
            "conflicts": conflicts,
            "shows": [],
        }, status.HTTP_409_CONFLICT

    response_payload: dict[str, Any] = {
        "shows": created_payloads,
        "show": created_payloads[0],
        "created_count": len(created_payloads),
        "requested_count": len(show_dates),
        "conflicts": conflicts,
    }

    if conflicts:
        response_payload["message"] = (
            f"Created {len(created_payloads)} show(s). "
            f"Skipped {len(conflicts)} duplicate timing(s) for the same hall."
        )
    elif len(created_payloads) > 1:
        response_payload["message"] = f"Created {len(created_payloads)} shows successfully."

    first_created = created_payloads[0]
    show_date_text = first_created.get("show_date") or "selected date"
    show_time_text = first_created.get("start_time") or "selected time"
    notification_title = "Show schedule updated"
    notification_message = (
        f"{movie.title} was scheduled on {show_date_text} at {show_time_text} in hall {hall}."
    )
    _notify_show_update(
        vendor=vendor,
        movie=movie,
        title=notification_title,
        message=notification_message,
        metadata={
            "movie_id": movie.id,
            "vendor_id": vendor.id,
            "created_count": len(created_payloads),
            "show_ids": [entry.get("id") for entry in created_payloads if entry.get("id")],
        },
    )

    return response_payload, status.HTTP_201_CREATED


def delete_show(request: Any, show: Show) -> tuple[dict[str, Any], int]:
    """Delete a show entry (admin/vendor only)."""
    if not is_authenticated(request):
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    if vendor_actor and show.vendor_id != vendor_actor.id:
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN
    if not vendor_actor and not admin_actor:
        return {"message": "Vendor access required"}, status.HTTP_403_FORBIDDEN

    title = "Show schedule updated"
    show_date_text = show.show_date.isoformat() if show.show_date else "selected date"
    show_time_text = show.start_time.strftime("%H:%M") if show.start_time else "selected time"
    message = (
        f"{show.movie.title} show on {show_date_text} at {show_time_text} in hall {show.hall or '-'} was removed."
    )
    _notify_show_update(
        vendor=show.vendor,
        movie=show.movie,
        title=title,
        message=message,
        metadata={
            "show_id": show.id,
            "movie_id": show.movie_id,
            "vendor_id": show.vendor_id,
            "action": "deleted",
        },
    )

    show.delete()
    return {"message": "Show deleted"}, status.HTTP_200_OK


def _seat_category_key(value: Any) -> str:
    """Normalize seat type to a stable category key."""
    return SEAT_CATEGORY_KEYS.get(_normalize_seat_category(value), "normal")


def _booked_count_for_showtime(showtime: Showtime) -> int:
    """Count non-cancelled booked seats for a showtime."""
    return BookingSeat.objects.filter(showtime=showtime).exclude(
        booking__booking_status__iexact="Cancelled"
    ).count()


def _available_target_seats_for_showtime(showtime: Showtime, screen: Screen) -> list[Seat]:
    """Return currently available seats for a target showtime in deterministic order."""
    now = timezone.now()
    occupied_ids: set[int] = set(
        BookingSeat.objects.filter(showtime=showtime)
        .exclude(booking__booking_status__iexact="Cancelled")
        .values_list("seat_id", flat=True)
    )

    for availability in SeatAvailability.objects.filter(showtime=showtime).select_related("seat"):
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value in BOOKED_STATUSES or status_value == SEAT_STATUS_UNAVAILABLE.lower():
            occupied_ids.add(availability.seat_id)
            continue
        if availability.locked_until and availability.locked_until > now:
            occupied_ids.add(availability.seat_id)

    seats = list(
        Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
    )
    return [seat for seat in seats if seat.id not in occupied_ids]


def preview_vendor_quick_hall_swap(show: Show) -> tuple[dict[str, Any], int]:
    """Return candidate halls and capacity fit for one-click hall swap."""
    source_hall = str(show.hall or "").strip()
    if not source_hall:
        return {"message": "Source hall is not set for this show."}, status.HTTP_400_BAD_REQUEST

    source_screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=source_hall).first()
    source_showtime = _find_showtime_for_context(show, source_hall)
    if not source_showtime:
        _, source_showtime = _get_or_create_showtime_for_context(show, source_hall)

    booked_count = _booked_count_for_showtime(source_showtime)
    source_capacity = int(source_screen.capacity or 0) if source_screen else 0

    candidates = []
    screens = Screen.objects.filter(vendor_id=show.vendor_id).exclude(screen_number__iexact=source_hall)
    for screen in screens:
        hall_name = str(screen.screen_number or "").strip()
        if not hall_name:
            continue

        has_timing_conflict = Show.objects.filter(
            vendor_id=show.vendor_id,
            show_date=show.show_date,
            start_time=show.start_time,
            hall__iexact=hall_name,
        ).exclude(id=show.id).exists()

        target_start = _combine_show_datetime(show.show_date, show.start_time)
        target_showtime = Showtime.objects.filter(
            movie_id=show.movie_id,
            screen=screen,
            start_time=target_start,
        ).first()

        if target_showtime:
            available_target_seats = _available_target_seats_for_showtime(target_showtime, screen)
        else:
            available_target_seats = list(
                Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
            )
        total_capacity = int(screen.capacity or len(Seat.objects.filter(screen=screen)) or 0)
        free_capacity = len(available_target_seats)
        candidates.append(
            {
                "hall": hall_name,
                "capacity": total_capacity,
                "free_capacity": free_capacity,
                "can_fit": (not has_timing_conflict) and free_capacity >= booked_count,
                "timing_conflict": has_timing_conflict,
                "screen_type": screen.screen_type,
                "recommended": (not has_timing_conflict)
                and free_capacity >= booked_count
                and total_capacity > source_capacity,
            }
        )

    candidates.sort(
        key=lambda item: (
            0 if item["recommended"] else 1,
            0 if item["can_fit"] else 1,
            -int(item["capacity"] or 0),
            str(item["hall"]),
        )
    )

    return {
        "show": build_show_payload(show),
        "source": {
            "hall": source_hall,
            "capacity": source_capacity,
            "booked_seats": booked_count,
        },
        "candidates": candidates,
    }, status.HTTP_200_OK


def quick_swap_show_hall(request: Any, show: Show) -> tuple[dict[str, Any], int]:
    """Swap a show to another hall and remap booked seats to equivalent target seats."""
    payload = get_payload(request)
    target_hall = str(coalesce(payload, "target_hall", "targetHall", "hall") or "").strip()
    source_hall = str(show.hall or "").strip()

    if not target_hall:
        return {"message": "target_hall is required."}, status.HTTP_400_BAD_REQUEST
    if not source_hall:
        return {"message": "Source hall is not set for this show."}, status.HTTP_400_BAD_REQUEST
    if target_hall.lower() == source_hall.lower():
        return {"message": "Target hall must be different from source hall."}, status.HTTP_400_BAD_REQUEST

    target_screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=target_hall).first()
    if not target_screen:
        return {"message": "Target hall layout is not configured."}, status.HTTP_400_BAD_REQUEST

    if Show.objects.filter(
        vendor_id=show.vendor_id,
        show_date=show.show_date,
        start_time=show.start_time,
        hall__iexact=target_hall,
    ).exclude(id=show.id).exists():
        return {
            "message": f"Hall {target_hall} already has a show at this time.",
        }, status.HTTP_409_CONFLICT

    with transaction.atomic():
        source_screen, source_showtime = _get_or_create_showtime_for_context(show, source_hall)

        target_start = _combine_show_datetime(show.show_date, show.start_time)
        target_end = _combine_show_datetime(show.show_date, show.end_time) if show.end_time else None
        target_showtime, _ = Showtime.objects.get_or_create(
            movie_id=show.movie_id,
            screen=target_screen,
            start_time=target_start,
            defaults={"end_time": target_end, "price": show.price},
        )
        if target_end and not target_showtime.end_time:
            target_showtime.end_time = target_end
            target_showtime.save(update_fields=["end_time"])

        booking_seats = list(
            BookingSeat.objects.select_for_update()
            .select_related("seat", "booking")
            .filter(showtime=source_showtime)
            .exclude(booking__booking_status__iexact="Cancelled")
            .order_by("booking_id", "id")
        )
        original_source_seat_ids = {item.seat_id for item in booking_seats if item.seat_id}

        if not booking_seats:
            show.hall = target_hall
            if target_screen.screen_type:
                show.screen_type = target_screen.screen_type
            show.save(update_fields=["hall", "screen_type"])
            return {
                "message": f"Show moved to {target_hall}. No existing bookings required remapping.",
                "show": build_show_payload(show),
                "source_hall": source_hall,
                "target_hall": target_hall,
                "moved_booking_count": 0,
                "moved_seat_count": 0,
            }, status.HTTP_200_OK

        target_available = _available_target_seats_for_showtime(target_showtime, target_screen)
        if len(target_available) < len(booking_seats):
            return {
                "message": "Target hall does not have enough available seats for transfer.",
                "required_seats": len(booking_seats),
                "available_seats": len(target_available),
            }, status.HTTP_409_CONFLICT

        target_by_label: dict[str, Seat] = {}
        target_by_category: dict[str, list[Seat]] = {
            "normal": [],
            "executive": [],
            "premium": [],
            "vip": [],
        }
        for seat in target_available:
            label = _join_seat_label(seat.row_label, seat.seat_number)
            target_by_label[label] = seat
            target_by_category[_seat_category_key(seat.seat_type)].append(seat)

        for category in target_by_category:
            target_by_category[category].sort(key=lambda s: _seat_sort_key(_join_seat_label(s.row_label, s.seat_number)))

        target_remaining = sorted(
            target_available,
            key=lambda s: _seat_sort_key(_join_seat_label(s.row_label, s.seat_number)),
        )

        assigned_target_ids: set[int] = set()
        seat_mapping: list[dict[str, Any]] = []
        booking_updates: set[int] = set()

        for booking_seat in booking_seats:
            source_seat = booking_seat.seat
            source_label = _join_seat_label(source_seat.row_label, source_seat.seat_number)
            source_category = _seat_category_key(source_seat.seat_type)

            selected: Optional[Seat] = None
            exact = target_by_label.get(source_label)
            if exact and exact.id not in assigned_target_ids:
                selected = exact

            if not selected:
                for candidate in target_by_category.get(source_category, []):
                    if candidate.id in assigned_target_ids:
                        continue
                    selected = candidate
                    break

            if not selected:
                for candidate in target_remaining:
                    if candidate.id in assigned_target_ids:
                        continue
                    selected = candidate
                    break

            if not selected:
                return {
                    "message": "Unable to map all bookings to equivalent seats in target hall.",
                }, status.HTTP_409_CONFLICT

            assigned_target_ids.add(selected.id)
            booking_updates.add(booking_seat.booking_id)
            seat_mapping.append(
                {
                    "booking_id": booking_seat.booking_id,
                    "from_seat": source_label,
                    "to_seat": _join_seat_label(selected.row_label, selected.seat_number),
                    "from_category": _normalize_seat_category(source_seat.seat_type),
                    "to_category": _normalize_seat_category(selected.seat_type),
                }
            )

            booking_seat.seat = selected
            booking_seat.showtime = target_showtime
            booking_seat.save(update_fields=["seat", "showtime"])

        Booking.objects.filter(id__in=list(booking_updates)).update(showtime=target_showtime)

        for target_seat_id in assigned_target_ids:
            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat_id=target_seat_id,
                showtime=target_showtime,
                defaults={"seat_status": SEAT_STATUS_BOOKED},
            )
            availability.seat_status = SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

        for seat_id in original_source_seat_ids:
            still_booked = BookingSeat.objects.filter(
                showtime=source_showtime,
                seat_id=seat_id,
            ).exclude(booking__booking_status__iexact="Cancelled").exists()
            if still_booked:
                continue
            SeatAvailability.objects.filter(showtime=source_showtime, seat_id=seat_id).update(
                seat_status=SEAT_STATUS_AVAILABLE,
                locked_until=None,
            )

        show.hall = target_hall
        if target_screen.screen_type:
            show.screen_type = target_screen.screen_type
        show.save(update_fields=["hall", "screen_type"])

        _notify_show_update(
            vendor=show.vendor,
            movie=show.movie,
            title="Quick hall swap completed",
            message=(
                f"{show.movie.title} moved from {source_hall} to {target_hall}. "
                f"{len(booking_updates)} booking(s) were remapped automatically."
            ),
            metadata={
                "show_id": show.id,
                "vendor_id": show.vendor_id,
                "source_hall": source_hall,
                "target_hall": target_hall,
                "moved_booking_count": len(booking_updates),
                "moved_seat_count": len(seat_mapping),
            },
        )

    return {
        "message": (
            f"Swapped to {target_hall}. Transferred {len(booking_updates)} booking(s) and "
            f"{len(seat_mapping)} seat(s)."
        ),
        "show": build_show_payload(show),
        "source_hall": source_hall,
        "target_hall": target_hall,
        "moved_booking_count": len(booking_updates),
        "moved_seat_count": len(seat_mapping),
        "seat_mappings": seat_mapping[:30],
    }, status.HTTP_200_OK


def request_password_otp(email: Optional[str]) -> tuple[dict[str, Any], int]:
    """Create or refresh an OTP for password reset."""
    email = str(email or "").strip()
    if not email:
        return {"message": "Email is required"}, status.HTTP_400_BAD_REQUEST

    try:
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        otp = f"{random.randint(100000, 999999)}"
        OTPVerification.objects.create(email=email, otp=otp)

        logger.info("Generated OTP for %s: %s", email, otp)
        if getattr(settings, "DEBUG", False):
            print(f"DEBUG OTP for {email}: {otp}")

        return {"message": "OTP sent to your email"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("forgot_password error")
        return {
            "message": "Failed to send OTP",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def verify_password_otp(email: Optional[str], otp: Optional[str]) -> tuple[dict[str, Any], int]:
    """Verify a password reset OTP."""
    email = str(email or "").strip()
    otp = str(otp or "").strip()
    if not email or not otp:
        return {
            "message": "Email and OTP are required"
        }, status.HTTP_400_BAD_REQUEST

    try:
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(
                email__iexact=email, otp=otp, created_at__gte=cutoff
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return {
                "message": "Invalid or expired OTP"
            }, status.HTTP_400_BAD_REQUEST

        record.is_verified = True
        record.save()
        return {"message": "OTP verified"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("verify_otp error")
        return {
            "message": "Failed to verify OTP",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def reset_password_with_otp(
    email: Optional[str], otp: Optional[str], new_password: Optional[str]
) -> tuple[dict[str, Any], int]:
    """Reset a user's password using a verified OTP."""
    email = str(email or "").strip()
    otp = str(otp or "").strip()
    if not email or not otp or not new_password:
        return {
            "message": "Email, OTP and new_password are required"
        }, status.HTTP_400_BAD_REQUEST

    try:
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(
                email__iexact=email,
                otp=otp,
                created_at__gte=cutoff,
                is_verified=True,
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return {
                "message": "Invalid or unverified OTP"
            }, status.HTTP_400_BAD_REQUEST

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        user.set_password(new_password)
        user.save()

        record.is_verified = False
        record.save()

        return {"message": "Password reset successful"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("reset_password error")
        return {
            "message": "Failed to reset password",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def update_user_profile(request: Any, user: User) -> tuple[dict[str, Any], int]:
    """Update a user's profile information."""
    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("profile_image", None)

    for key in ("first_name", "middle_name", "last_name"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()
            if key == "middle_name" and data[key] == "":
                data[key] = None

    if "dob" in data and not str(data["dob"]).strip():
        data.pop("dob")

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = UserProfileUpdateSerializer(user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_user = serializer.save()

    _update_profile_image(updated_user, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "user": build_user_payload(updated_user, request),
    }, status.HTTP_200_OK


def update_admin_profile(request: Any, admin_user: Admin) -> tuple[dict[str, Any], int]:
    """Update an admin's profile information."""
    actor_admin = resolve_admin(request)
    actor_id = getattr(actor_admin, "id", None)
    if actor_admin and actor_id and int(actor_id) != int(admin_user.id):
        if not getattr(actor_admin, "is_superuser", False):
            return {"message": "Admin access denied"}, status.HTTP_403_FORBIDDEN

    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("email", None)
    data.pop("profile_image", None)

    if "full_name" in data and isinstance(data["full_name"], str):
        data["full_name"] = data["full_name"].strip()
        if data["full_name"] == "":
            data["full_name"] = None

    if "phone_number" in data:
        raw_phone = str(data["phone_number"]).strip()
        phone = normalize_phone_number(raw_phone)
        data["phone_number"] = phone or None
        if raw_phone and not phone:
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and not PHONE_REGEX.match(phone):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and Admin.objects.filter(phone_number=phone).exclude(pk=admin_user.id).exists():
            return {
                "message": "Phone number already exists"
            }, status.HTTP_400_BAD_REQUEST

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = AdminProfileUpdateSerializer(admin_user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_admin = serializer.save()

    _update_profile_image(updated_admin, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "admin": build_admin_payload(updated_admin, request),
    }, status.HTTP_200_OK


def update_vendor_profile(request: Any, vendor_user: Vendor) -> tuple[dict[str, Any], int]:
    """Update a vendor's profile information."""
    actor_vendor = resolve_vendor(request)
    if actor_vendor and actor_vendor.id != vendor_user.id:
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN

    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("email", None)
    data.pop("status", None)
    data.pop("is_active", None)
    data.pop("created_at", None)
    data.pop("profile_image", None)

    if "name" in data and isinstance(data["name"], str):
        data["name"] = data["name"].strip()
        if data["name"] == "":
            return {"message": "Vendor name is required"}, status.HTTP_400_BAD_REQUEST

    if "phone_number" in data:
        raw_phone = str(data["phone_number"]).strip()
        phone = normalize_phone_number(raw_phone)
        data["phone_number"] = phone or None
        if raw_phone and not phone:
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and not PHONE_REGEX.match(phone):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and Vendor.objects.filter(phone_number=phone).exclude(pk=vendor_user.id).exists():
            return {
                "message": "Phone number already exists"
            }, status.HTTP_400_BAD_REQUEST

    for key in ("theatre", "city"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip() or None

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = VendorProfileUpdateSerializer(vendor_user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_vendor = serializer.save()

    _update_profile_image(updated_vendor, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "vendor": build_vendor_payload(updated_vendor, request),
    }, status.HTTP_200_OK


def _safe_number(value: Any) -> float:
    """Coerce a value to a float, returning 0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_int(value: Any) -> Optional[int]:
    """Coerce a value to int if possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_flexible_time(value: Any) -> Optional[time_cls]:
    """Parse a time value from common 24h and 12h formats."""
    if not value:
        return None
    if isinstance(value, time_cls):
        return value

    parsed = parse_time(value)
    if parsed:
        return parsed

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%I:%M %p", "%I %p", "%H:%M:%S"):
        try:
            return datetime.strptime(text.upper(), fmt).time()
        except ValueError:
            continue
    return None


def _normalize_seat_labels(value: Any) -> list[str]:
    """Normalize seat labels into uppercase tokens like A10."""
    raw_labels: list[str] = []
    if isinstance(value, str):
        matches = re.findall(r"[A-Za-z]+\s*\d+[A-Za-z]?", value)
        if matches:
            raw_labels.extend(matches)
        elif value.strip():
            raw_labels.append(value.strip())
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            raw_labels.extend(_normalize_seat_labels(item))

    labels: list[str] = []
    seen = set()
    for label in raw_labels:
        normalized = re.sub(r"\s+", "", str(label)).upper()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        labels.append(normalized)
    return labels


def _split_seat_label(value: str) -> tuple[str, str]:
    """Split a seat label into row and seat number parts."""
    label = re.sub(r"\s+", "", str(value or "")).upper()
    if not label:
        return "", ""

    match = re.match(r"^([A-Z]+)(\d+[A-Z]?)$", label)
    if match:
        return match.group(1), match.group(2)

    match = re.match(r"^(\d+[A-Z]?)$", label)
    if match:
        return "", match.group(1)

    row = label[:1] if label and label[0].isalpha() else ""
    seat_number = label[len(row):] if row else label
    return row, seat_number


def _join_seat_label(row_label: Any, seat_number: Any) -> str:
    """Build a canonical seat label from row and seat number."""
    row = str(row_label or "").strip().upper()
    number = str(seat_number or "").strip().upper()
    return f"{row}{number}".strip()


def _seat_sort_key(label: str) -> tuple[str, int, str]:
    """Sort seat labels by row then seat number."""
    cleaned = re.sub(r"\s+", "", str(label or "")).upper()
    match = re.match(r"^([A-Z]+)?(\d+)?([A-Z]*)$", cleaned)
    if not match:
        return cleaned, 0, ""
    row = match.group(1) or ""
    number = int(match.group(2) or 0)
    suffix = match.group(3) or ""
    return row, number, suffix


def _combine_show_datetime(show_date: date_cls, show_time: time_cls) -> datetime:
    """Combine date and time into a timezone-aware datetime when needed."""
    combined = datetime.combine(show_date, show_time)
    if getattr(settings, "USE_TZ", False) and timezone.is_naive(combined):
        return timezone.make_aware(combined, timezone.get_current_timezone())
    return combined


def _resolve_booking_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract booking context fields from request/order payloads."""
    booking_data = payload.get("booking") if isinstance(payload.get("booking"), dict) else {}
    movie_data = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}

    cinema_id = _coerce_int(
        coalesce(
            booking_data,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
            default=coalesce(
                payload,
                "cinema_id",
                "cinemaId",
                "vendor_id",
                "vendorId",
                default=coalesce(movie_data, "cinemaId", "vendorId"),
            ),
        )
    )
    movie_id = _coerce_int(
        coalesce(
            booking_data,
            "movie_id",
            "movieId",
            "movie",
            default=coalesce(
                payload,
                "movie_id",
                "movieId",
                "movie",
                default=coalesce(movie_data, "movieId", "movie_id", "id"),
            ),
        )
    )
    show_id = _coerce_int(
        coalesce(
            booking_data,
            "show_id",
            "showId",
            default=coalesce(payload, "show_id", "showId"),
        )
    )
    show_date = parse_date(
        coalesce(
            booking_data,
            "date",
            "show_date",
            "showDate",
            default=coalesce(payload, "date", "show_date", "showDate"),
        )
    )
    show_time = _parse_flexible_time(
        coalesce(
            booking_data,
            "time",
            "start",
            "start_time",
            "startTime",
            default=coalesce(payload, "time", "start", "start_time", "startTime"),
        )
    )
    hall = str(
        coalesce(
            booking_data,
            "hall",
            "cinema_hall",
            "cinemaHall",
            default=coalesce(payload, "hall", "cinema_hall", "cinemaHall"),
        )
        or ""
    ).strip()
    selected_seats = _normalize_seat_labels(
        coalesce(
            booking_data,
            "selected_seats",
            "selectedSeats",
            "seats",
            default=coalesce(payload, "selected_seats", "selectedSeats", "seats"),
        )
    )
    user_id = _coerce_int(
        coalesce(booking_data, "user_id", "userId", default=coalesce(payload, "user_id", "userId"))
    )

    return {
        "show_id": show_id,
        "movie_id": movie_id,
        "cinema_id": cinema_id,
        "show_date": show_date,
        "show_time": show_time,
        "hall": hall or None,
        "selected_seats": selected_seats,
        "user_id": user_id,
    }


def _resolve_show_for_context(context: dict[str, Any]) -> Optional[Show]:
    """Resolve a Show row from booking context fields."""
    show_id = context.get("show_id")
    if show_id:
        return Show.objects.filter(pk=show_id).first()

    cinema_id = context.get("cinema_id")
    movie_id = context.get("movie_id")
    show_date = context.get("show_date")
    show_time = context.get("show_time")
    if not cinema_id or not movie_id or not show_date or not show_time:
        return None

    queryset = Show.objects.filter(
        vendor_id=cinema_id,
        movie_id=movie_id,
        show_date=show_date,
        start_time=show_time,
    )
    hall = context.get("hall")
    if hall:
        queryset = queryset.filter(hall__iexact=hall)
    return queryset.order_by("id").first()


def _resolve_screen_number(show: Show, hall_override: Optional[str] = None) -> str:
    """Resolve the screen number identifier for a show."""
    hall = str(hall_override or show.hall or "").strip()
    if hall:
        return hall
    return f"Hall-{show.id}"


def _find_showtime_for_context(show: Show, hall_override: Optional[str] = None) -> Optional[Showtime]:
    """Find an existing showtime row that maps to the selected show context."""
    screen_number = _resolve_screen_number(show, hall_override)
    screen = Screen.objects.filter(
        vendor_id=show.vendor_id, screen_number=screen_number
    ).first()
    if not screen:
        return None
    start_at = _combine_show_datetime(show.show_date, show.start_time)
    return Showtime.objects.filter(
        movie_id=show.movie_id,
        screen_id=screen.id,
        start_time=start_at,
    ).first()


def _get_or_create_showtime_for_context(
    show: Show, hall_override: Optional[str] = None
) -> tuple[Screen, Showtime]:
    """Get or create the Screen/Showtime records for a selected show."""
    screen_number = _resolve_screen_number(show, hall_override)
    screen, _ = Screen.objects.get_or_create(
        vendor_id=show.vendor_id,
        screen_number=screen_number,
        defaults={
            "screen_type": show.screen_type,
            "status": "Active",
        },
    )
    if show.screen_type and not screen.screen_type:
        screen.screen_type = show.screen_type
        screen.save(update_fields=["screen_type"])

    start_at = _combine_show_datetime(show.show_date, show.start_time)
    end_at = (
        _combine_show_datetime(show.show_date, show.end_time)
        if show.end_time
        else None
    )
    showtime, created = Showtime.objects.get_or_create(
        movie_id=show.movie_id,
        screen=screen,
        start_time=start_at,
        defaults={
            "end_time": end_at,
            "price": show.price,
        },
    )
    if not created:
        updated_fields: list[str] = []
        if end_at and not showtime.end_time:
            showtime.end_time = end_at
            updated_fields.append("end_time")
        if show.price is not None and showtime.price is None:
            showtime.price = show.price
            updated_fields.append("price")
        if updated_fields:
            showtime.save(update_fields=updated_fields)

    return screen, showtime


def _collect_sold_labels_for_showtime(showtime: Showtime, lock: bool = False) -> list[str]:
    """Collect sold seat labels from availability + confirmed bookings."""
    sold_labels = set()

    availability_qs = SeatAvailability.objects.filter(showtime=showtime).select_related(
        "seat"
    )
    if lock:
        availability_qs = availability_qs.select_for_update()
    for availability in availability_qs:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value not in BOOKED_STATUSES:
            continue
        sold_labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )

    booking_seat_qs = BookingSeat.objects.filter(
        booking__showtime=showtime,
    ).exclude(
        booking__booking_status__iexact="Cancelled"
    ).select_related("seat")
    if lock:
        booking_seat_qs = booking_seat_qs.select_for_update()
    for booking_seat in booking_seat_qs:
        sold_labels.add(
            _join_seat_label(booking_seat.seat.row_label, booking_seat.seat.seat_number)
        )

    return sorted(sold_labels, key=_seat_sort_key)


def _collect_unavailable_labels_for_showtime(
    showtime: Showtime, lock: bool = False
) -> list[str]:
    """Collect unavailable seat labels for a showtime."""
    labels = set()
    queryset = SeatAvailability.objects.filter(showtime=showtime).select_related("seat")
    if lock:
        queryset = queryset.select_for_update()
    for availability in queryset:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value != SEAT_STATUS_UNAVAILABLE.lower():
            continue
        labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )
    return sorted(labels, key=_seat_sort_key)


def _prune_expired_reservations(showtime: Showtime) -> None:
    """Clear expired seat reservations for a showtime."""
    now = timezone.now()
    SeatAvailability.objects.filter(
        showtime=showtime,
        locked_until__isnull=False,
        locked_until__lte=now,
    ).update(locked_until=None)


def _collect_reserved_labels_for_showtime(
    showtime: Showtime, lock: bool = False
) -> list[str]:
    """Collect reserved seat labels for a showtime based on locks."""
    now = timezone.now()
    queryset = SeatAvailability.objects.filter(
        showtime=showtime,
        locked_until__gt=now,
    ).select_related("seat")
    if lock:
        queryset = queryset.select_for_update()
    labels = set()
    for availability in queryset:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value in BOOKED_STATUSES:
            continue
        if status_value == SEAT_STATUS_UNAVAILABLE.lower():
            continue
        labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )
    return sorted(labels, key=_seat_sort_key)


def _next_guest_phone_number() -> str:
    """Generate a unique phone number for fallback guest users."""
    for suffix in range(1000):
        candidate = str(9800000000 + suffix)
        if not User.objects.filter(phone_number=candidate).exists():
            return candidate
    while True:
        candidate = str(random.randint(9000000000, 9999999999))
        if not User.objects.filter(phone_number=candidate).exists():
            return candidate


def _resolve_booking_user(context: dict[str, Any]) -> User:
    """Resolve booking user from payload or fallback guest account."""
    user_id = context.get("user_id")
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            return user

    guest = User.objects.filter(email__iexact=DEFAULT_GUEST_EMAIL).first()
    if guest:
        return guest

    guest_user = User(
        email=DEFAULT_GUEST_EMAIL,
        phone_number=_next_guest_phone_number(),
        dob=date_cls(2000, 1, 1),
        first_name=DEFAULT_GUEST_NAME,
        last_name="User",
        username=f"guest-{uuid.uuid4().hex[:8]}",
    )
    guest_user.set_password(uuid.uuid4().hex)
    guest_user.save()
    return guest_user


def _create_booking_from_order(order: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    """Create booking + sold seat records from order context."""
    cleanup_expired_pending_bookings()

    context = _resolve_booking_context(order)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return None, None, status.HTTP_200_OK

    if not context.get("movie_id") or not context.get("cinema_id") or not context.get("show_date") or not context.get("show_time"):
        return (
            None,
            {
                "message": "Booking context is incomplete. Provide cinema, movie, date, time, and selected seats.",
            },
            status.HTTP_400_BAD_REQUEST,
        )

    show = _resolve_show_for_context(context)
    if not show:
        return (
            None,
            {"message": "Selected show was not found."},
            status.HTTP_404_NOT_FOUND,
        )
    show_booking_error, show_booking_status = _ensure_show_is_bookable(show)
    if show_booking_error:
        return None, show_booking_error, int(show_booking_status)

    normalized_labels = _normalize_seat_labels(selected_seats)
    parsed_labels: list[tuple[str, str, str]] = []
    invalid_labels: list[str] = []
    for label in normalized_labels:
        row_label, seat_number = _split_seat_label(label)
        if not seat_number:
            invalid_labels.append(label)
            continue
        parsed_labels.append((label, row_label, seat_number))

    if invalid_labels:
        return (
            None,
            {"message": "Invalid seat labels in request.", "invalid_seats": invalid_labels},
            status.HTTP_400_BAD_REQUEST,
        )

    user = _resolve_booking_user(context)
    provided_ticket_total = _safe_number(
        coalesce(order, "ticketTotal", "ticket_total", default=order.get("total"))
    )
    coupon_code = coalesce(order, "coupon_code", "couponCode", "coupon")
    event_name = str(
        coalesce(order, "event", "event_name", "festival", "festival_name")
        or coalesce(context, "event", "event_name", "festival", "festival_name")
        or ""
    ).strip()

    with transaction.atomic():
        screen, showtime = _get_or_create_showtime_for_context(show, context.get("hall"))
        existing_sold = set(_collect_sold_labels_for_showtime(showtime, lock=True))
        conflicts = [label for label, _, _ in parsed_labels if label in existing_sold]
        if conflicts:
            return (
                None,
                {
                    "message": "Some selected seats are already sold.",
                    "sold_seats": sorted(conflicts, key=_seat_sort_key),
                },
                status.HTTP_409_CONFLICT,
            )

        seat_records: list[tuple[str, str, str, Seat, SeatAvailability, Optional[Decimal]]] = []
        persisted_seats: list[str] = []
        for label, row_label, seat_number in parsed_labels:
            seat, _ = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            )
            availability, created = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if not created and current_status in BOOKED_STATUSES:
                return (
                    None,
                    {
                        "message": "Some selected seats are already sold.",
                        "sold_seats": [label],
                    },
                    status.HTTP_409_CONFLICT,
                )
            if not created and current_status == SEAT_STATUS_UNAVAILABLE.lower():
                return (
                    None,
                    {
                        "message": "Some selected seats are unavailable.",
                        "unavailable_seats": [label],
                    },
                    status.HTTP_409_CONFLICT,
                )
            seat_price, _ = _resolve_dynamic_seat_price(
                show=show,
                showtime=showtime,
                screen=screen,
                seat_type=seat.seat_type,
                event_name=event_name,
            )
            seat_records.append((label, row_label, seat_number, seat, availability, seat_price))

        computed_total = Decimal("0.00")
        if seat_records:
            for *_, seat_price in seat_records:
                if seat_price is not None:
                    computed_total += seat_price

        subtotal_amount = _parse_price_amount(provided_ticket_total)
        if computed_total > Decimal("0"):
            subtotal_amount = computed_total
        if subtotal_amount is None:
            subtotal_amount = Decimal("0.00")

        coupon = None
        vendor_promo = None
        discount_amount = Decimal("0.00")
        total_amount = subtotal_amount
        if coupon_code:
            seat_categories = [
                seat.seat_type
                for _, _, _, seat, _, _ in seat_records
                if seat and seat.seat_type
            ]
            discount_context = {
                **context,
                "vendor_id": show.vendor_id,
                "show_id": show.id,
                "showtime_id": showtime.id,
                "seat_categories": seat_categories,
                "seat_count": len(seat_records),
                "user_id": user.id,
                "is_student": parse_bool(coalesce(order, "is_student", "isStudent"), default=False),
            }
            coupon_result, coupon_error, coupon_status = _apply_coupon_to_subtotal(
                coupon_code,
                subtotal_amount,
                context=discount_context,
                lock_for_update=True,
                consume=True,
            )
            if coupon_error:
                return None, coupon_error, coupon_status
            if coupon_result.get("coupon"):
                coupon = Coupon.objects.filter(id=coupon_result["coupon"]["id"]).first()
            if coupon_result.get("promo_code"):
                vendor_promo = VendorPromoCode.objects.filter(id=coupon_result["promo_code"]["id"]).first()
            discount_amount = _parse_price_amount(coupon_result.get("discount_amount")) or Decimal("0.00")
            total_amount = _parse_price_amount(coupon_result.get("final_total")) or subtotal_amount

        booking = Booking.objects.create(
            user=user,
            showtime=showtime,
            booking_status=BOOKING_STATUS_CONFIRMED,
            total_amount=total_amount,
            coupon=coupon,
            vendor_promo_code=vendor_promo,
            discount_amount=discount_amount,
        )

        for _, row_label, seat_number, seat, availability, seat_price in seat_records:
            availability.seat_status = SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

            BookingSeat.objects.create(
                booking=booking,
                showtime=showtime,
                seat=seat,
                seat_price=seat_price,
            )
            persisted_seats.append(_join_seat_label(row_label, seat_number))

        _record_vendor_booking_earning(booking, gross_amount=total_amount)

    try:
        _notify_booking_created(booking, show)
    except Exception:
        logger.exception("Failed to dispatch booking-created notifications for booking %s", booking.id)
    try:
        _notify_vendor_when_show_fully_booked(show=show, showtime=showtime, screen=screen)
    except Exception:
        logger.exception(
            "Failed to dispatch full-capacity notification for show %s (booking %s)",
            show.id,
            booking.id,
        )

    return (
        {
            "booking_id": booking.id,
            "show_id": show.id,
            "showtime_id": showtime.id,
            "screen": screen.screen_number,
            "sold_seats": sorted(persisted_seats, key=_seat_sort_key),
        },
        None,
        status.HTTP_201_CREATED,
    )


def list_sold_seats_for_context(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return sold seat labels for a selected movie/cinema/date/time context."""
    layout_payload, status_code = list_booking_seat_layout(payload)
    sold_labels = list(layout_payload.get("sold_seats") or [])
    unavailable_labels = list(layout_payload.get("unavailable_seats") or [])
    return {
        "sold_seats": sold_labels,
        "soldSeats": sold_labels,
        "unavailable_seats": unavailable_labels,
        "unavailableSeats": unavailable_labels,
        "show_id": layout_payload.get("show_id"),
        "showtime_id": layout_payload.get("showtime_id"),
    }, status_code


def list_available_seats_for_context(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return available seat entries for a selected movie/cinema/date/time context."""
    layout_payload, status_code = list_booking_seat_layout(payload)
    seats = layout_payload.get("seats") if isinstance(layout_payload.get("seats"), list) else []
    available = [seat for seat in seats if str(seat.get("status") or "").lower() == "available"]
    available_labels = [str(seat.get("label") or "").upper() for seat in available if seat.get("label")]
    return {
        "available_seats": available,
        "available_labels": sorted(available_labels, key=_seat_sort_key),
        "show_id": layout_payload.get("show_id"),
        "showtime_id": layout_payload.get("showtime_id"),
        "category_prices": layout_payload.get("category_prices") or {},
    }, status_code


def _build_pricing_rule_payload(rule: PricingRule) -> dict[str, Any]:
    """Serialize one pricing rule for API responses."""
    return {
        "id": rule.id,
        "name": rule.name,
        "vendor_id": rule.vendor_id,
        "movie_id": rule.movie_id,
        "hall": rule.hall,
        "seat_category": rule.seat_category,
        "day_type": rule.day_type,
        "is_festival_pricing": bool(rule.is_festival_pricing),
        "festival_name": rule.festival_name,
        "start_date": rule.start_date.isoformat() if rule.start_date else None,
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "adjustment_type": rule.adjustment_type,
        "adjustment_value": float(rule.adjustment_value),
        "priority": int(rule.priority or 0),
        "is_active": bool(rule.is_active),
    }


def _clean_pricing_rule_input(payload: dict[str, Any], partial: bool = False) -> tuple[dict[str, Any], Optional[str]]:
    """Validate and normalize pricing rule request payload."""
    cleaned: dict[str, Any] = {}

    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            return {}, "name is required."
        cleaned["name"] = name[:120]

    if "movie_id" in payload or "movieId" in payload:
        movie_id = _coerce_int(coalesce(payload, "movie_id", "movieId"))
        cleaned["movie_id"] = movie_id

    if "hall" in payload:
        cleaned["hall"] = str(payload.get("hall") or "").strip() or None

    if not partial or "seat_category" in payload:
        seat_category = str(coalesce(payload, "seat_category", "seatCategory") or PricingRule.SEAT_CATEGORY_ALL).upper()
        allowed = {
            PricingRule.SEAT_CATEGORY_ALL,
            PricingRule.SEAT_CATEGORY_NORMAL,
            PricingRule.SEAT_CATEGORY_EXECUTIVE,
            PricingRule.SEAT_CATEGORY_PREMIUM,
            PricingRule.SEAT_CATEGORY_VIP,
        }
        if seat_category not in allowed:
            return {}, "seat_category is invalid."
        cleaned["seat_category"] = seat_category

    if not partial or "day_type" in payload:
        day_type = str(coalesce(payload, "day_type", "dayType") or PricingRule.DAY_TYPE_ALL).upper()
        allowed = {
            PricingRule.DAY_TYPE_ALL,
            PricingRule.DAY_TYPE_WEEKDAY,
            PricingRule.DAY_TYPE_WEEKEND,
        }
        if day_type not in allowed:
            return {}, "day_type is invalid."
        cleaned["day_type"] = day_type

    if "is_festival_pricing" in payload or "isFestivalPricing" in payload:
        cleaned["is_festival_pricing"] = parse_bool(
            coalesce(payload, "is_festival_pricing", "isFestivalPricing"),
            default=False,
        )

    if "festival_name" in payload or "festivalName" in payload:
        cleaned["festival_name"] = str(coalesce(payload, "festival_name", "festivalName") or "").strip() or None

    if "start_date" in payload or "startDate" in payload:
        cleaned["start_date"] = parse_date(coalesce(payload, "start_date", "startDate"))
    if "end_date" in payload or "endDate" in payload:
        cleaned["end_date"] = parse_date(coalesce(payload, "end_date", "endDate"))
    if cleaned.get("start_date") and cleaned.get("end_date") and cleaned["start_date"] > cleaned["end_date"]:
        return {}, "start_date must be on or before end_date."

    if not partial or "adjustment_type" in payload:
        adjustment_type = str(coalesce(payload, "adjustment_type", "adjustmentType") or "").upper()
        allowed = {
            PricingRule.ADJUSTMENT_FIXED,
            PricingRule.ADJUSTMENT_INCREMENT,
            PricingRule.ADJUSTMENT_PERCENT,
            PricingRule.ADJUSTMENT_MULTIPLIER,
        }
        if adjustment_type not in allowed:
            return {}, "adjustment_type is invalid."
        cleaned["adjustment_type"] = adjustment_type

    if not partial or "adjustment_value" in payload or "adjustmentValue" in payload:
        adjustment_value = _parse_price_amount(coalesce(payload, "adjustment_value", "adjustmentValue"))
        if adjustment_value is None:
            return {}, "adjustment_value is required and must be non-negative."
        cleaned["adjustment_value"] = adjustment_value

    if "priority" in payload:
        cleaned["priority"] = _parse_positive_int(payload.get("priority"), default=100, minimum=1, maximum=9999)

    if "is_active" in payload or "isActive" in payload:
        cleaned["is_active"] = parse_bool(coalesce(payload, "is_active", "isActive"), default=True)

    return cleaned, None

def get_vendor_cancellation_policy(request: Any) -> tuple[dict[str, Any], int]:
    """Return vendor cancellation policy, optionally scoped to a screen/hall."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    screen_id = _coerce_int(
        coalesce(request.query_params, "screen_id", "screenId", "hall_id", "hallId")
    )
    screen = None
    if screen_id:
        screen = Screen.objects.filter(id=screen_id, vendor_id=vendor.id).first()
        if not screen:
            return {"message": "screen_id is invalid for this vendor."}, status.HTTP_400_BAD_REQUEST

    if screen:
        policy = VendorCancellationPolicy.objects.filter(
            vendor_id=vendor.id,
            screen_id=screen.id,
        ).select_related("screen").first()
        if policy:
            return {"policy": _serialize_cancellation_policy(policy)}, status.HTTP_200_OK

    default_policy = VendorCancellationPolicy.objects.filter(
        vendor_id=vendor.id,
        screen__isnull=True,
    ).first()
    if default_policy:
        payload = _serialize_cancellation_policy(default_policy)
        if screen and not payload.get("screen_id"):
            payload["screen_id"] = screen.id
            payload["screen_number"] = screen.screen_number
            payload["source"] = "VENDOR_DEFAULT_FALLBACK"
        return {"policy": payload}, status.HTTP_200_OK

    return {
        "policy": _default_cancellation_policy_payload(vendor=vendor, screen=screen),
    }, status.HTTP_200_OK


def update_vendor_cancellation_policy(request: Any) -> tuple[dict[str, Any], int]:
    """Create or update vendor cancellation policy for default scope or one screen."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    screen_id = _coerce_int(
        coalesce(payload, "screen_id", "screenId", "hall_id", "hallId")
        or coalesce(request.query_params, "screen_id", "screenId", "hall_id", "hallId")
    )
    screen = None
    if screen_id:
        screen = Screen.objects.filter(id=screen_id, vendor_id=vendor.id).first()
        if not screen:
            return {"message": "screen_id is invalid for this vendor."}, status.HTTP_400_BAD_REQUEST

    policy, created = VendorCancellationPolicy.objects.get_or_create(
        vendor_id=vendor.id,
        screen_id=screen.id if screen else None,
    )

    changed = False
    if "allow_customer_cancellation" in payload or "allowCustomerCancellation" in payload:
        policy.allow_customer_cancellation = parse_bool(
            coalesce(payload, "allow_customer_cancellation", "allowCustomerCancellation"),
            default=True,
        )
        changed = True

    if "is_active" in payload or "isActive" in payload:
        policy.is_active = parse_bool(coalesce(payload, "is_active", "isActive"), default=True)
        changed = True

    if "refund_percent_2h_plus" in payload or "refundPercent2hPlus" in payload:
        policy.refund_percent_2h_plus = _percent_decimal(
            coalesce(payload, "refund_percent_2h_plus", "refundPercent2hPlus"),
            DEFAULT_REFUND_PERCENT_2H_PLUS,
        )
        changed = True

    if "refund_percent_1_to_2h" in payload or "refundPercent1to2h" in payload:
        policy.refund_percent_1_to_2h = _percent_decimal(
            coalesce(payload, "refund_percent_1_to_2h", "refundPercent1to2h"),
            DEFAULT_REFUND_PERCENT_1_TO_2H,
        )
        changed = True

    if "refund_percent_less_than_1h" in payload or "refundPercentLessThan1h" in payload:
        policy.refund_percent_less_than_1h = _percent_decimal(
            coalesce(payload, "refund_percent_less_than_1h", "refundPercentLessThan1h"),
            DEFAULT_REFUND_PERCENT_LESS_THAN_1H,
        )
        changed = True

    if "note" in payload:
        policy.note = str(payload.get("note") or "").strip() or None
        changed = True

    if not changed and not created:
        return {
            "message": "No policy updates provided.",
            "policy": _serialize_cancellation_policy(policy),
        }, status.HTTP_400_BAD_REQUEST

    policy.save()
    message = "Cancellation policy created." if created else "Cancellation policy updated."
    return {
        "message": message,
        "policy": _serialize_cancellation_policy(policy),
    }, status.HTTP_200_OK


def list_vendor_pricing_rules(request: Any) -> list[dict[str, Any]]:
    """List pricing rules for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return []

    queryset = PricingRule.objects.filter(vendor_id=vendor.id)
    movie_id = _coerce_int(coalesce(request.query_params, "movie_id", "movieId"))
    if movie_id:
        queryset = queryset.filter(Q(movie_id=movie_id) | Q(movie_id__isnull=True))

    if "is_active" in request.query_params or "isActive" in request.query_params:
        is_active = parse_bool(coalesce(request.query_params, "is_active", "isActive"), default=True)
        queryset = queryset.filter(is_active=is_active)

    return [_build_pricing_rule_payload(rule) for rule in queryset.order_by("priority", "id")]


def create_vendor_pricing_rule(request: Any) -> tuple[dict[str, Any], int]:
    """Create a pricing rule for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    cleaned, error = _clean_pricing_rule_input(payload, partial=False)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    movie_id = cleaned.get("movie_id")
    if movie_id and not Movie.objects.filter(pk=movie_id).exists():
        return {"message": "movie_id is invalid."}, status.HTTP_400_BAD_REQUEST

    rule = PricingRule.objects.create(vendor_id=vendor.id, **cleaned)
    return {"message": "Pricing rule created.", "rule": _build_pricing_rule_payload(rule)}, status.HTTP_201_CREATED


def update_vendor_pricing_rule(request: Any, rule: PricingRule) -> tuple[dict[str, Any], int]:
    """Update one vendor pricing rule."""
    payload = get_payload(request)
    cleaned, error = _clean_pricing_rule_input(payload, partial=True)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST
    if not cleaned:
        return {"message": "No pricing rule changes provided."}, status.HTTP_400_BAD_REQUEST

    movie_id = cleaned.get("movie_id")
    if movie_id and not Movie.objects.filter(pk=movie_id).exists():
        return {"message": "movie_id is invalid."}, status.HTTP_400_BAD_REQUEST

    for key, value in cleaned.items():
        setattr(rule, key, value)
    rule.save()
    return {"message": "Pricing rule updated.", "rule": _build_pricing_rule_payload(rule)}, status.HTTP_200_OK


def delete_vendor_pricing_rule(rule: PricingRule) -> tuple[dict[str, Any], int]:
    """Delete one vendor pricing rule."""
    rule.delete()
    return {"message": "Pricing rule deleted."}, status.HTTP_200_OK


def _serialize_private_screening_request(item: PrivateScreeningRequest) -> dict[str, Any]:
    """Serialize private screening request for API responses."""
    return {
        "id": item.id,
        "requester_type": item.requester_type,
        "organization_name": item.organization_name,
        "contact_person": item.contact_person,
        "contact_email": item.contact_email,
        "contact_phone": item.contact_phone,
        "preferred_date": item.preferred_date.isoformat() if item.preferred_date else None,
        "preferred_start_time": item.preferred_start_time.strftime("%H:%M") if item.preferred_start_time else None,
        "attendee_count": item.attendee_count,
        "preferred_movie_title": item.preferred_movie_title,
        "hall_preference": item.hall_preference,
        "special_requirements": item.special_requirements,
        "estimated_budget": float(item.estimated_budget) if item.estimated_budget is not None else None,
        "status": item.status,
        "vendor_id": item.vendor_id,
        "vendor_name": item.vendor.name if item.vendor else None,
        "vendor_notes": item.vendor_notes,
        "quoted_amount": float(item.quoted_amount) if item.quoted_amount is not None else None,
        "counter_offer_amount": float(item.counter_offer_amount) if item.counter_offer_amount is not None else None,
        "invoice_number": item.invoice_number,
        "invoice_notes": item.invoice_notes,
        "invoiced_at": item.invoiced_at.isoformat() if item.invoiced_at else None,
        "finalized_at": item.finalized_at.isoformat() if item.finalized_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def create_private_screening_request(request: Any) -> tuple[dict[str, Any], int]:
    """Create a private screening quote request."""
    payload = get_payload(request)

    organization_name = str(coalesce(payload, "organization_name", "organizationName", "company_name", "companyName") or "").strip()
    contact_person = str(coalesce(payload, "contact_person", "contactPerson", "name") or "").strip()
    contact_email = str(coalesce(payload, "contact_email", "contactEmail", "email") or "").strip()
    if not organization_name or not contact_person or not contact_email:
        return {
            "message": "organization_name, contact_person, and contact_email are required.",
        }, status.HTTP_400_BAD_REQUEST

    attendee_count = _parse_positive_int(
        coalesce(payload, "attendee_count", "attendeeCount", "group_size", "groupSize"),
        default=0,
        minimum=1,
        maximum=5000,
    )
    if attendee_count <= 0:
        return {"message": "attendee_count must be at least 1."}, status.HTTP_400_BAD_REQUEST

    preferred_date = parse_date(coalesce(payload, "preferred_date", "preferredDate", "date"))
    preferred_start_time = parse_time(coalesce(payload, "preferred_start_time", "preferredStartTime", "time"))

    vendor = None
    vendor_id = _coerce_int(coalesce(payload, "vendor_id", "vendorId"))
    if vendor_id:
        vendor = Vendor.objects.filter(pk=vendor_id, is_active=True).exclude(status__iexact=STATUS_BLOCKED).first()
        if not vendor:
            return {"message": "vendor_id is invalid."}, status.HTTP_400_BAD_REQUEST

    estimated_budget = _parse_price_amount(coalesce(payload, "estimated_budget", "estimatedBudget", "budget"))
    if estimated_budget is not None and estimated_budget < Decimal("0"):
        return {"message": "estimated_budget must be non-negative."}, status.HTTP_400_BAD_REQUEST

    item = PrivateScreeningRequest.objects.create(
        requester_type=str(coalesce(payload, "requester_type", "requesterType", "type") or "").strip() or None,
        organization_name=organization_name,
        contact_person=contact_person,
        contact_email=contact_email,
        contact_phone=str(coalesce(payload, "contact_phone", "contactPhone", "phone") or "").strip() or None,
        preferred_date=preferred_date,
        preferred_start_time=preferred_start_time,
        attendee_count=attendee_count,
        preferred_movie_title=str(coalesce(payload, "preferred_movie_title", "preferredMovieTitle", "movie_title", "movieTitle") or "").strip() or None,
        hall_preference=str(coalesce(payload, "hall_preference", "hallPreference", "hall") or "").strip() or None,
        special_requirements=str(coalesce(payload, "special_requirements", "specialRequirements", "requirements") or "").strip() or None,
        estimated_budget=estimated_budget,
        vendor=vendor,
    )

    if vendor:
        _create_notification(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=vendor.id,
            recipient_email=vendor.email,
            event_type=Notification.EVENT_SHOW_UPDATE,
            title="New private screening request",
            message=f"{organization_name} requested a private screening quote.",
            metadata={"screening_request_id": item.id},
            send_email_too=False,
        )

    return {
        "message": "Private screening request submitted.",
        "request": _serialize_private_screening_request(item),
    }, status.HTTP_201_CREATED


def list_vendor_private_screening_requests(request: Any) -> tuple[dict[str, Any], int]:
    """List private screening requests for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    queryset = PrivateScreeningRequest.objects.filter(vendor_id=vendor.id)
    status_filter = str(coalesce(request.query_params, "status") or "").strip().upper()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    items = list(queryset.order_by("-created_at", "-id")[:300])
    return {
        "requests": [_serialize_private_screening_request(item) for item in items],
    }, status.HTTP_200_OK


def update_vendor_private_screening_request(request: Any, item: PrivateScreeningRequest) -> tuple[dict[str, Any], int]:
    """Update private screening request with vendor quote/counter/invoice actions."""
    payload = get_payload(request)

    next_status = str(coalesce(payload, "status", "action") or "").strip().upper()
    allowed_statuses = {
        PrivateScreeningRequest.STATUS_REVIEWED,
        PrivateScreeningRequest.STATUS_COUNTERED,
        PrivateScreeningRequest.STATUS_ACCEPTED,
        PrivateScreeningRequest.STATUS_REJECTED,
        PrivateScreeningRequest.STATUS_INVOICED,
        PrivateScreeningRequest.STATUS_COMPLETED,
    }
    if next_status and next_status not in allowed_statuses:
        return {"message": "status/action is invalid."}, status.HTTP_400_BAD_REQUEST

    quoted_amount = _parse_price_amount(coalesce(payload, "quoted_amount", "quotedAmount"))
    counter_offer = _parse_price_amount(coalesce(payload, "counter_offer_amount", "counterOfferAmount"))
    if quoted_amount is not None and quoted_amount < Decimal("0"):
        return {"message": "quoted_amount must be non-negative."}, status.HTTP_400_BAD_REQUEST
    if counter_offer is not None and counter_offer < Decimal("0"):
        return {"message": "counter_offer_amount must be non-negative."}, status.HTTP_400_BAD_REQUEST

    if quoted_amount is not None:
        item.quoted_amount = quoted_amount
    if counter_offer is not None:
        item.counter_offer_amount = counter_offer

    if "vendor_notes" in payload or "vendorNotes" in payload:
        item.vendor_notes = str(coalesce(payload, "vendor_notes", "vendorNotes") or "").strip() or None
    if "invoice_notes" in payload or "invoiceNotes" in payload:
        item.invoice_notes = str(coalesce(payload, "invoice_notes", "invoiceNotes") or "").strip() or None
    if "invoice_number" in payload or "invoiceNumber" in payload:
        item.invoice_number = str(coalesce(payload, "invoice_number", "invoiceNumber") or "").strip() or None

    if next_status:
        item.status = next_status
        if next_status == PrivateScreeningRequest.STATUS_INVOICED:
            item.invoiced_at = timezone.now()
            if not item.invoice_number:
                item.invoice_number = f"INV-{item.id}-{timezone.now().strftime('%Y%m%d')}"
        if next_status == PrivateScreeningRequest.STATUS_COMPLETED:
            item.finalized_at = timezone.now()

    item.save()

    return {
        "message": "Private screening request updated.",
        "request": _serialize_private_screening_request(item),
    }, status.HTTP_200_OK


def _serialize_bulk_ticket_item(
    item: BulkTicketItem,
    request: Any,
    *,
    include_qr: bool = False,
) -> dict[str, Any]:
    """Serialize one bulk ticket item with optional QR payload."""
    reference = item.ticket.reference
    details_url = request.build_absolute_uri(f"/api/ticket/{reference}/details/")
    payload: dict[str, Any] = {
        "id": item.id,
        "reference": reference,
        "employee_code": item.employee_code,
        "recipient_name": item.recipient_name,
        "recipient_email": item.recipient_email,
        "status": item.status,
        "details_url": details_url,
        "download_url": request.build_absolute_uri(f"/api/ticket/{reference}/download/"),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
    if include_qr:
        qr_image = _build_qr_image(details_url)
        payload["qr_code"] = _image_to_data_url(qr_image) if qr_image else None
    return payload


def _serialize_bulk_ticket_batch(batch: BulkTicketBatch) -> dict[str, Any]:
    """Serialize a bulk ticket batch summary."""
    tickets = list(batch.tickets.all())
    total_count = len(tickets)
    active_count = sum(1 for item in tickets if item.status == BulkTicketItem.STATUS_ACTIVE)
    redeemed_count = sum(1 for item in tickets if item.status == BulkTicketItem.STATUS_REDEEMED)
    return {
        "id": batch.id,
        "vendor_id": batch.vendor_id,
        "corporate_name": batch.corporate_name,
        "contact_person": batch.contact_person,
        "contact_email": batch.contact_email,
        "movie_title": batch.movie_title,
        "hall": batch.hall,
        "show_date": batch.show_date.isoformat() if batch.show_date else None,
        "show_time": batch.show_time.strftime("%H:%M") if batch.show_time else None,
        "valid_until": batch.valid_until.isoformat() if batch.valid_until else None,
        "unit_price": float(batch.unit_price or Decimal("0")),
        "total_amount": float(batch.total_amount or Decimal("0")),
        "status": batch.status,
        "notes": batch.notes,
        "ticket_count": total_count,
        "active_count": active_count,
        "redeemed_count": redeemed_count,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
    }


def create_vendor_bulk_ticket_batch(request: Any) -> tuple[dict[str, Any], int]:
    """Generate many valid ticket references for a corporate batch."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    corporate_name = str(coalesce(payload, "corporate_name", "corporateName", "company_name", "companyName") or "").strip()
    if not corporate_name:
        return {"message": "corporate_name is required."}, status.HTTP_400_BAD_REQUEST

    ticket_count = _parse_positive_int(
        coalesce(payload, "ticket_count", "ticketCount", "quantity", "count"),
        default=0,
        minimum=1,
        maximum=2000,
    )
    if ticket_count <= 0:
        return {"message": "ticket_count must be between 1 and 2000."}, status.HTTP_400_BAD_REQUEST

    unit_price = _parse_price_amount(coalesce(payload, "unit_price", "unitPrice", "price"))
    if unit_price is None:
        unit_price = Decimal("0.00")

    show_date = parse_date(coalesce(payload, "show_date", "showDate", "date"))
    show_time = parse_time(coalesce(payload, "show_time", "showTime", "time"))
    valid_until = parse_date(coalesce(payload, "valid_until", "validUntil", "expiry_date", "expiryDate"))

    recipient_items = payload.get("recipients") if isinstance(payload.get("recipients"), list) else []

    with transaction.atomic():
        batch = BulkTicketBatch.objects.create(
            vendor=vendor,
            corporate_name=corporate_name,
            contact_person=str(coalesce(payload, "contact_person", "contactPerson") or "").strip() or None,
            contact_email=str(coalesce(payload, "contact_email", "contactEmail") or "").strip() or None,
            movie_title=str(coalesce(payload, "movie_title", "movieTitle") or "").strip() or None,
            hall=str(coalesce(payload, "hall") or "").strip() or None,
            show_date=show_date,
            show_time=show_time,
            valid_until=valid_until,
            unit_price=unit_price,
            total_amount=(unit_price * Decimal(ticket_count)).quantize(Decimal("0.01")),
            notes=str(coalesce(payload, "notes", "note") or "").strip() or None,
            status=BulkTicketBatch.STATUS_GENERATED,
        )

        generated_items: list[BulkTicketItem] = []
        for index in range(ticket_count):
            recipient = recipient_items[index] if index < len(recipient_items) and isinstance(recipient_items[index], dict) else {}
            reference = uuid.uuid4().hex[:10].upper()
            details_url = request.build_absolute_uri(f"/api/ticket/{reference}/details/")
            movie_payload = {
                "title": batch.movie_title or "Corporate Ticket",
                "venue_name": vendor.theatre or vendor.name,
                "venue_location": vendor.city or "",
                "show_date": batch.show_date.isoformat() if batch.show_date else "",
                "show_time": batch.show_time.strftime("%I:%M %p") if batch.show_time else "",
                "theater": batch.hall or "Private Hall",
                "cinema_id": vendor.id,
            }
            ticket_payload = {
                "reference": reference,
                "movie": movie_payload,
                "selected_seats": [],
                "ticket_total": float(unit_price),
                "food_total": 0,
                "total": float(unit_price),
                "items": [],
                "user": {
                    "name": str(coalesce(recipient, "name", "recipient_name", "recipientName") or "").strip() or None,
                    "email": str(coalesce(recipient, "email", "recipient_email", "recipientEmail") or "").strip() or None,
                },
                "booking": {
                    "vendor_id": vendor.id,
                    "vendor_name": vendor.name,
                    "bulk_batch_id": batch.id,
                },
                "bulk": {
                    "batch_id": batch.id,
                    "corporate_name": batch.corporate_name,
                    "employee_code": str(coalesce(recipient, "employee_code", "employeeCode", default=f"EMP-{index + 1:04d}") or "").strip(),
                    "valid_until": batch.valid_until.isoformat() if batch.valid_until else None,
                },
                "created_at": timezone.now().isoformat(),
                "details_url": details_url,
            }
            ticket = Ticket.objects.create(reference=reference, payload=ticket_payload)
            generated_items.append(
                BulkTicketItem(
                    batch=batch,
                    ticket=ticket,
                    employee_code=str(coalesce(recipient, "employee_code", "employeeCode", default=f"EMP-{index + 1:04d}") or "").strip() or None,
                    recipient_name=str(coalesce(recipient, "name", "recipient_name", "recipientName") or "").strip() or None,
                    recipient_email=str(coalesce(recipient, "email", "recipient_email", "recipientEmail") or "").strip() or None,
                    status=BulkTicketItem.STATUS_ACTIVE,
                )
            )

        BulkTicketItem.objects.bulk_create(generated_items, batch_size=200)

    return {
        "message": "Bulk tickets generated successfully.",
        "batch": _serialize_bulk_ticket_batch(batch),
    }, status.HTTP_201_CREATED


def list_vendor_bulk_ticket_batches(request: Any) -> tuple[dict[str, Any], int]:
    """List bulk ticket batches for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    queryset = BulkTicketBatch.objects.filter(vendor_id=vendor.id).prefetch_related("tickets")
    status_filter = str(coalesce(request.query_params, "status") or "").strip().upper()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    batches = list(queryset.order_by("-created_at", "-id")[:120])
    return {
        "batches": [_serialize_bulk_ticket_batch(batch) for batch in batches],
    }, status.HTTP_200_OK


def export_vendor_bulk_ticket_batch(request: Any, batch: BulkTicketBatch) -> tuple[dict[str, Any], int]:
    """Export one batch with CSV payload and ticket QR data URLs."""
    include_qr = parse_bool(coalesce(request.query_params, "include_qr", "includeQr"), default=True)
    items = list(batch.tickets.select_related("ticket").order_by("id"))

    rows: list[dict[str, Any]] = []
    tickets_payload: list[dict[str, Any]] = []
    for item in items:
        serialized = _serialize_bulk_ticket_item(item, request, include_qr=include_qr)
        tickets_payload.append(serialized)
        rows.append(
            {
                "reference": serialized["reference"],
                "employee_code": serialized["employee_code"] or "",
                "recipient_name": serialized["recipient_name"] or "",
                "recipient_email": serialized["recipient_email"] or "",
                "status": serialized["status"],
                "details_url": serialized["details_url"],
                "download_url": serialized["download_url"],
                "qr_code": serialized.get("qr_code") or "",
            }
        )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "reference",
            "employee_code",
            "recipient_name",
            "recipient_email",
            "status",
            "details_url",
            "download_url",
            "qr_code",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

    if batch.status != BulkTicketBatch.STATUS_EXPORTED:
        batch.status = BulkTicketBatch.STATUS_EXPORTED
        batch.save(update_fields=["status", "updated_at"])

    encoded_csv = base64.b64encode(output.getvalue().encode("utf-8")).decode("ascii")
    return {
        "message": "Bulk ticket export prepared.",
        "batch": _serialize_bulk_ticket_batch(batch),
        "csv_base64": encoded_csv,
        "filename": f"bulk_tickets_batch_{batch.id}.csv",
        "tickets": tickets_payload,
    }, status.HTTP_200_OK


def calculate_dynamic_ticket_price(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Calculate final ticket price dynamically for selected seats and context."""
    context = _resolve_booking_context(payload)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND

    hall = context.get("hall") or show.hall
    showtime = _find_showtime_for_context(show, hall)
    screen = None
    if showtime:
        screen = showtime.screen
    if not screen and hall:
        screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=str(hall)).first()
    if not screen:
        screen = Screen.objects.filter(vendor_id=show.vendor_id).order_by("id").first()

    event_name = str(coalesce(payload, "event", "event_name", "festival", "festival_name") or "").strip()

    seats_payload: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for label in selected_seats:
        row_label, seat_number = _split_seat_label(label)
        if not seat_number:
            continue

        seat = None
        if screen:
            seat = Seat.objects.filter(screen=screen, row_label=row_label or None, seat_number=seat_number).first()
        seat_type = seat.seat_type if seat else SEAT_CATEGORY_NORMAL
        final_price, applied_rules = _resolve_dynamic_seat_price(
            show=show,
            showtime=showtime,
            screen=screen,
            seat_type=seat_type,
            event_name=event_name,
        )
        base_price = _seat_price_for_category(screen=screen, showtime=showtime, seat_type=seat_type)
        normalized_label = _join_seat_label(row_label, seat_number)
        if final_price is not None:
            total += final_price
        seats_payload.append(
            {
                "label": normalized_label,
                "seat_type": _normalize_seat_category(seat_type),
                "base_price": float(base_price) if base_price is not None else None,
                "final_price": float(final_price) if final_price is not None else None,
                "applied_rules": applied_rules,
            }
        )

    normalized_total = total.quantize(Decimal("0.01"))
    coupon_payload = None
    discount_amount = Decimal("0.00")
    payable_total = normalized_total

    coupon_code = coalesce(payload, "coupon_code", "couponCode", "code")
    if coupon_code:
        discount_context = {
            **(payload if isinstance(payload, dict) else {}),
            "vendor_id": show.vendor_id,
            "show_id": show.id,
            "showtime_id": showtime.id if showtime else None,
            "seat_categories": [seat.get("seat_type") for seat in seats_payload],
            "seat_count": len(seats_payload),
        }
        coupon_result, coupon_error, coupon_status = _apply_coupon_to_subtotal(
            coupon_code,
            normalized_total,
            context=discount_context,
            lock_for_update=False,
            consume=False,
        )
        if coupon_error:
            return coupon_error, coupon_status
        coupon_payload = coupon_result.get("coupon")
        promo_payload = coupon_result.get("promo_code")
        discount_amount = _parse_price_amount(coupon_result.get("discount_amount")) or Decimal("0.00")
        payable_total = _parse_price_amount(coupon_result.get("final_total")) or normalized_total
    else:
        promo_payload = None

    return {
        "show_id": show.id,
        "showtime_id": showtime.id if showtime else None,
        "currency": "NPR",
        "seat_count": len(seats_payload),
        "seats": seats_payload,
        "subtotal": float(normalized_total),
        "discount_amount": float(discount_amount),
        "total": float(payable_total),
        "coupon": coupon_payload,
        "promo_code": promo_payload,
    }, status.HTTP_200_OK


def _row_label_from_index(index: int) -> str:
    """Convert a zero-based row index into a label (A..Z, AA..)."""
    label = ""
    current = int(index)
    while True:
        current, remainder = divmod(current, 26)
        label = chr(65 + remainder) + label
        if current == 0:
            break
        current -= 1
    return label


def _row_label_sort_key(value: Any) -> int:
    """Sort row labels lexicographically in base-26 order."""
    label = str(value or "").strip().upper()
    score = 0
    for char in label:
        if not ("A" <= char <= "Z"):
            continue
        score = (score * 26) + (ord(char) - 64)
    return score


def _parse_positive_int(
    value: Any, default: int, minimum: int = 1, maximum: int = 100
) -> int:
    """Parse an int with bounds and fallback."""
    parsed = _coerce_int(value)
    if parsed is None:
        return default
    return max(minimum, min(maximum, parsed))


def _normalize_seat_category(value: Any) -> str:
    """Normalize free-text seat category labels."""
    text = str(value or "").strip().lower()
    if text.startswith("vip"):
        return SEAT_CATEGORY_VIP
    if text.startswith("prem"):
        return SEAT_CATEGORY_PREMIUM
    if text.startswith("exec"):
        return SEAT_CATEGORY_EXECUTIVE
    return SEAT_CATEGORY_NORMAL


def _parse_price_amount(value: Any) -> Optional[Decimal]:
    """Parse a price value into Decimal(0.01) or return None for invalid input."""
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < Decimal("0"):
        return None
    return parsed.quantize(Decimal("0.01"))


def _collect_screen_category_prices(
    screen: Optional[Screen],
    showtime: Optional[Showtime] = None,
) -> dict[str, Optional[Decimal]]:
    """Collect category prices from screen fields with showtime/base fallback."""
    base_price = None
    if showtime and showtime.price is not None:
        base_price = _parse_price_amount(showtime.price)

    prices: dict[str, Optional[Decimal]] = {}
    for key, field_name in SEAT_CATEGORY_SCREEN_FIELDS.items():
        screen_price = _parse_price_amount(getattr(screen, field_name, None) if screen else None)
        prices[key] = screen_price if screen_price is not None else base_price
    return prices


def _normalize_category_prices(
    payload: dict[str, Any],
    screen: Optional[Screen] = None,
    showtime: Optional[Showtime] = None,
) -> dict[str, Optional[Decimal]]:
    """Normalize category price payload with screen/showtime fallback values."""
    raw_prices = payload.get("category_prices") if isinstance(payload.get("category_prices"), dict) else {}
    prices = _collect_screen_category_prices(screen=screen, showtime=showtime)
    for key in ("normal", "executive", "premium", "vip"):
        incoming = coalesce(
            raw_prices,
            key,
            default=coalesce(payload, f"{key}_price", f"{key}Price"),
        )
        parsed = _parse_price_amount(incoming)
        if parsed is not None:
            prices[key] = parsed
    return prices


def _seat_price_for_category(
    screen: Optional[Screen],
    showtime: Optional[Showtime],
    seat_type: Any,
) -> Optional[Decimal]:
    """Resolve effective seat price for one category from screen/showtime values."""
    category_key = SEAT_CATEGORY_KEYS.get(_normalize_seat_category(seat_type), "normal")
    return _collect_screen_category_prices(screen=screen, showtime=showtime).get(category_key)


def _serialize_category_prices(prices: dict[str, Optional[Decimal]]) -> dict[str, Optional[float]]:
    """Serialize Decimal category prices for API payloads."""
    return {
        key: (float(value) if value is not None else None)
        for key, value in prices.items()
    }


def _is_weekend(value: Optional[date_cls]) -> bool:
    """Return True if date is weekend (Saturday/Sunday)."""
    if not value:
        return False
    return value.weekday() >= 5


def _normalize_rule_seat_category(seat_type: Any) -> str:
    """Map seat category labels to PricingRule seat category enum values."""
    category_label = _normalize_seat_category(seat_type)
    return SEAT_CATEGORY_RULE_VALUES.get(category_label, PricingRule.SEAT_CATEGORY_NORMAL)


def _apply_pricing_adjustment(
    price: Optional[Decimal],
    adjustment_type: str,
    adjustment_value: Optional[Decimal],
) -> Optional[Decimal]:
    """Apply one rule adjustment to a seat price."""
    if adjustment_value is None:
        return price

    current = price if price is not None else Decimal("0")
    kind = str(adjustment_type or "").upper()

    if kind == PricingRule.ADJUSTMENT_FIXED:
        result = adjustment_value
    elif kind == PricingRule.ADJUSTMENT_INCREMENT:
        result = current + adjustment_value
    elif kind == PricingRule.ADJUSTMENT_PERCENT:
        result = current + (current * (adjustment_value / Decimal("100")))
    elif kind == PricingRule.ADJUSTMENT_MULTIPLIER:
        result = current * adjustment_value
    else:
        result = current

    if result < Decimal("0"):
        result = Decimal("0")
    return result.quantize(Decimal("0.01"))


def _list_applicable_pricing_rules(
    show: Show,
    seat_category_rule: str,
    hall: Optional[str],
    show_date: Optional[date_cls],
    event_name: str = "",
) -> list[PricingRule]:
    """List active vendor pricing rules applicable to one show + seat category."""
    queryset = PricingRule.objects.filter(vendor_id=show.vendor_id, is_active=True).filter(
        Q(movie_id__isnull=True) | Q(movie_id=show.movie_id)
    )

    hall_text = str(hall or "").strip()
    if hall_text:
        queryset = queryset.filter(Q(hall__isnull=True) | Q(hall="") | Q(hall__iexact=hall_text))
    else:
        queryset = queryset.filter(Q(hall__isnull=True) | Q(hall=""))

    if show_date:
        queryset = queryset.filter(
            Q(start_date__isnull=True) | Q(start_date__lte=show_date),
            Q(end_date__isnull=True) | Q(end_date__gte=show_date),
        )

    day_type = PricingRule.DAY_TYPE_WEEKEND if _is_weekend(show_date) else PricingRule.DAY_TYPE_WEEKDAY
    queryset = queryset.filter(Q(day_type=PricingRule.DAY_TYPE_ALL) | Q(day_type=day_type))
    queryset = queryset.filter(
        Q(seat_category=PricingRule.SEAT_CATEGORY_ALL) | Q(seat_category=seat_category_rule)
    )

    event_text = str(event_name or "").strip().lower()
    rules = list(queryset.order_by("priority", "id"))
    applicable: list[PricingRule] = []
    for rule in rules:
        if not rule.is_festival_pricing:
            applicable.append(rule)
            continue

        rule_event = str(rule.festival_name or "").strip().lower()
        if not rule_event or not event_text or event_text == rule_event:
            applicable.append(rule)

    return applicable


def _resolve_dynamic_seat_price(
    show: Show,
    showtime: Optional[Showtime],
    screen: Optional[Screen],
    seat_type: Any,
    event_name: str = "",
) -> tuple[Optional[Decimal], list[dict[str, Any]]]:
    """Resolve final seat price after applying vendor pricing rules."""
    base_price = _seat_price_for_category(screen=screen, showtime=showtime, seat_type=seat_type)
    if base_price is None:
        base_price = _parse_price_amount(show.price)

    hall = None
    if screen and screen.screen_number:
        hall = str(screen.screen_number)
    elif show.hall:
        hall = str(show.hall)
    show_date = show.show_date
    seat_category_rule = _normalize_rule_seat_category(seat_type)
    rules = _list_applicable_pricing_rules(
        show=show,
        seat_category_rule=seat_category_rule,
        hall=hall,
        show_date=show_date,
        event_name=event_name,
    )

    current = base_price
    applied: list[dict[str, Any]] = []
    for rule in rules:
        adjustment_value = _parse_price_amount(rule.adjustment_value)
        before = current
        current = _apply_pricing_adjustment(current, rule.adjustment_type, adjustment_value)
        applied.append(
            {
                "rule_id": rule.id,
                "name": rule.name,
                "adjustment_type": rule.adjustment_type,
                "adjustment_value": float(adjustment_value) if adjustment_value is not None else None,
                "before": float(before) if before is not None else None,
                "after": float(current) if current is not None else None,
                "is_festival_pricing": bool(rule.is_festival_pricing),
                "festival_name": rule.festival_name,
            }
        )

    return current, applied


def _default_category_counts(total_rows: int) -> dict[str, int]:
    """Build default row distribution for seat categories."""
    rows = max(1, int(total_rows))
    normal = max(1, round(rows * 0.3))
    executive = max(1, round(rows * 0.3))
    premium = max(1, round(rows * 0.2))
    vip = max(1, rows - (normal + executive + premium))
    diff = rows - (normal + executive + premium + vip)
    normal += diff
    return {
        "normal": normal,
        "executive": executive,
        "premium": premium,
        "vip": vip,
    }


def _normalize_category_counts(total_rows: int, payload: dict[str, Any]) -> dict[str, int]:
    """Normalize category row counts from payload into a complete distribution."""
    category_rows = (
        payload.get("category_rows")
        if isinstance(payload.get("category_rows"), dict)
        else {}
    )
    counts = {
        "normal": _parse_positive_int(
            coalesce(
                category_rows,
                "normal",
                default=coalesce(payload, "normal_rows", "normalRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "executive": _parse_positive_int(
            coalesce(
                category_rows,
                "executive",
                default=coalesce(
                    payload, "executive_rows", "executiveRows", default=0
                ),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "premium": _parse_positive_int(
            coalesce(
                category_rows,
                "premium",
                default=coalesce(payload, "premium_rows", "premiumRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "vip": _parse_positive_int(
            coalesce(
                category_rows,
                "vip",
                default=coalesce(payload, "vip_rows", "vipRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
    }

    provided_total = sum(counts.values())
    if provided_total <= 0:
        return _default_category_counts(total_rows)

    if provided_total < total_rows:
        counts["normal"] += total_rows - provided_total
    elif provided_total > total_rows:
        overflow = provided_total - total_rows
        for key in ("vip", "premium", "executive", "normal"):
            if overflow <= 0:
                break
            reducible = min(counts[key], overflow)
            counts[key] -= reducible
            overflow -= reducible
        if overflow > 0:
            defaults = _default_category_counts(total_rows)
            return defaults
    return counts


def _build_row_category_map(
    row_labels: list[str], category_counts: dict[str, int]
) -> dict[str, str]:
    """Map each row label to its seat category in front-to-back order."""
    ordered_categories = [
        ("normal", SEAT_CATEGORY_NORMAL),
        ("executive", SEAT_CATEGORY_EXECUTIVE),
        ("premium", SEAT_CATEGORY_PREMIUM),
        ("vip", SEAT_CATEGORY_VIP),
    ]
    mapping: dict[str, str] = {}
    index = 0
    for key, label in ordered_categories:
        count = max(0, int(category_counts.get(key, 0)))
        for _ in range(count):
            if index >= len(row_labels):
                break
            mapping[row_labels[index]] = label
            index += 1
    while index < len(row_labels):
        mapping[row_labels[index]] = SEAT_CATEGORY_VIP
        index += 1
    return mapping


def _build_default_layout_payload() -> dict[str, Any]:
    """Return fallback seat layout payload compatible with existing frontend grid."""
    return {
        "seat_groups": [
            {"key": "normal", "label": SEAT_CATEGORY_NORMAL, "rows": ["A", "B", "C"]},
            {
                "key": "executive",
                "label": SEAT_CATEGORY_EXECUTIVE,
                "rows": ["D", "E", "F"],
            },
            {"key": "premium", "label": SEAT_CATEGORY_PREMIUM, "rows": ["G", "H"]},
            {"key": "vip", "label": SEAT_CATEGORY_VIP, "rows": ["I", "J"]},
        ],
        "seat_columns": list(range(1, 16)),
        "sold_seats": [],
        "unavailable_seats": [],
        "reserved_seats": [],
        "category_prices": {
            "normal": None,
            "executive": None,
            "premium": None,
            "vip": None,
        },
        "seats": [],
        "total_rows": 10,
        "total_columns": 15,
    }


def _resolve_vendor_for_payload(
    request: Any, payload: dict[str, Any]
) -> tuple[Optional[Vendor], Optional[dict[str, Any]], int]:
    """Resolve vendor identity from request or explicit payload values."""
    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    vendor_id = _coerce_int(
        coalesce(payload, "vendor_id", "vendorId", "cinema_id", "cinemaId")
    )

    if vendor_actor:
        if vendor_id and int(vendor_id) != int(vendor_actor.id):
            return None, {"message": "Vendor access denied."}, status.HTTP_403_FORBIDDEN
        return vendor_actor, None, status.HTTP_200_OK

    if admin_actor:
        if not vendor_id:
            return (
                None,
                {"message": "vendor_id is required for admin requests."},
                status.HTTP_400_BAD_REQUEST,
            )
        vendor = Vendor.objects.filter(pk=vendor_id).first()
        if not vendor:
            return None, {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
        return vendor, None, status.HTTP_200_OK

    if not vendor_id:
        return (
            None,
            {"message": "vendor_id is required."},
            status.HTTP_400_BAD_REQUEST,
        )

    vendor = Vendor.objects.filter(pk=vendor_id).first()
    if not vendor:
        return None, {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
    return vendor, None, status.HTTP_200_OK


def _resolve_show_for_vendor(vendor: Vendor, payload: dict[str, Any]) -> Optional[Show]:
    """Resolve a vendor-owned show from payload context."""
    show_id = _coerce_int(coalesce(payload, "show_id", "showId"))
    if show_id:
        return Show.objects.filter(pk=show_id, vendor_id=vendor.id).first()

    movie_id = _coerce_int(coalesce(payload, "movie_id", "movieId", "movie"))
    show_date = parse_date(coalesce(payload, "date", "show_date", "showDate"))
    show_time = _parse_flexible_time(
        coalesce(payload, "time", "start", "start_time", "startTime")
    )
    if not movie_id or not show_date or not show_time:
        return None

    queryset = Show.objects.filter(
        vendor_id=vendor.id,
        movie_id=movie_id,
        show_date=show_date,
        start_time=show_time,
    )
    hall = str(coalesce(payload, "hall", "cinema_hall", "cinemaHall") or "").strip()
    if hall:
        queryset = queryset.filter(hall__iexact=hall)
    return queryset.order_by("id").first()


def _build_screen_layout_payload(
    screen: Optional[Screen], showtime: Optional[Showtime] = None, show: Optional[Show] = None
) -> dict[str, Any]:
    """Build seat layout payload from screen seats and optional showtime statuses."""
    if not screen:
        return _build_default_layout_payload()

    seats = list(
        Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
    )
    if not seats:
        payload = _build_default_layout_payload()
        payload.update(
            {
                "screen_id": screen.id,
                "hall": screen.screen_number,
                "vendor_id": screen.vendor_id,
                "show_id": show.id if show else None,
                "showtime_id": showtime.id if showtime else None,
            }
        )
        return payload

    row_labels = sorted(
        {str(seat.row_label or "").strip().upper() for seat in seats if seat.row_label},
        key=_row_label_sort_key,
    )
    parsed_columns = []
    for seat in seats:
        number_text = str(seat.seat_number or "").strip()
        match = re.search(r"\d+", number_text)
        if not match:
            continue
        parsed_columns.append(int(match.group(0)))
    seat_columns = sorted(set(parsed_columns)) or list(range(1, 16))

    if showtime:
        _prune_expired_reservations(showtime)
    sold_labels = set(_collect_sold_labels_for_showtime(showtime, lock=False)) if showtime else set()
    unavailable_labels = (
        set(_collect_unavailable_labels_for_showtime(showtime, lock=False)) if showtime else set()
    )
    reserved_labels = (
        set(_collect_reserved_labels_for_showtime(showtime, lock=False)) if showtime else set()
    )
    category_prices = _collect_screen_category_prices(screen=screen, showtime=showtime)

    category_rows: dict[str, set[str]] = {
        category: set() for category in SEAT_CATEGORY_ORDER
    }
    seat_items = []
    for seat in seats:
        category_label = _normalize_seat_category(seat.seat_type)
        row_label = str(seat.row_label or "").strip().upper()
        seat_label = _join_seat_label(row_label, seat.seat_number)
        category_rows[category_label].add(row_label)

        seat_status = "available"
        if seat_label in sold_labels:
            seat_status = "booked"
        elif seat_label in unavailable_labels:
            seat_status = "unavailable"
        elif seat_label in reserved_labels:
            seat_status = "reserved"

        seat_items.append(
            {
                "id": seat.id,
                "row_label": row_label,
                "seat_number": str(seat.seat_number or ""),
                "label": seat_label,
                "seat_type": category_label,
                "seat_price": (
                    float(category_prices.get(SEAT_CATEGORY_KEYS[category_label]))
                    if category_prices.get(SEAT_CATEGORY_KEYS[category_label]) is not None
                    else None
                ),
                "status": seat_status,
            }
        )

    seat_groups = []
    for category_label in SEAT_CATEGORY_ORDER:
        rows = sorted(category_rows[category_label], key=_row_label_sort_key)
        seat_groups.append(
            {
                "key": SEAT_CATEGORY_KEYS[category_label],
                "label": category_label,
                "rows": rows,
            }
        )

    return {
        "screen_id": screen.id,
        "hall": screen.screen_number,
        "vendor_id": screen.vendor_id,
        "show_id": show.id if show else None,
        "showtime_id": showtime.id if showtime else None,
        "category_prices": _serialize_category_prices(category_prices),
        "seat_groups": seat_groups,
        "seat_columns": seat_columns,
        "row_labels": row_labels,
        "seats": seat_items,
        "sold_seats": sorted(sold_labels, key=_seat_sort_key),
        "unavailable_seats": sorted(unavailable_labels, key=_seat_sort_key),
        "reserved_seats": sorted(reserved_labels, key=_seat_sort_key),
        "total_rows": len(row_labels),
        "total_columns": len(seat_columns),
        "total_seats": len(seat_items),
    }


def list_vendor_seat_layout(request: Any) -> tuple[dict[str, Any], int]:
    """Return vendor seat layout for hall/show management."""
    query_payload = {
        key: request.query_params.get(key) for key in request.query_params.keys()
    }
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, query_payload)
    if error_payload:
        return error_payload, status_code

    show = _resolve_show_for_vendor(vendor, query_payload)
    hall = str(
        coalesce(query_payload, "hall", "cinema_hall", "cinemaHall", default=show.hall if show else "")
        or ""
    ).strip()

    screen = None
    if hall:
        screen = Screen.objects.filter(vendor_id=vendor.id, screen_number=hall).first()
    if not screen:
        screen = Screen.objects.filter(vendor_id=vendor.id).order_by("id").first()

    showtime = None
    if show:
        showtime = _find_showtime_for_context(show, hall or None)

    payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "hall": hall or payload.get("hall"),
            "reservedSeats": payload.get("reserved_seats") or [],
        }
    )
    return payload, status.HTTP_200_OK


def create_or_update_vendor_seat_layout(request: Any) -> tuple[dict[str, Any], int]:
    """Create or update seat layout rows/columns/categories for a vendor hall."""
    payload = get_payload(request)
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, payload)
    if error_payload:
        return error_payload, status_code

    hall = str(coalesce(payload, "hall", "cinema_hall", "cinemaHall") or "").strip()
    if not hall:
        return {"message": "hall is required."}, status.HTTP_400_BAD_REQUEST

    total_rows = _parse_positive_int(
        coalesce(payload, "rows", "row_count", "rowCount"), default=10, minimum=1, maximum=52
    )
    total_columns = _parse_positive_int(
        coalesce(payload, "columns", "cols", "column_count", "columnCount"),
        default=15,
        minimum=1,
        maximum=40,
    )
    raw_category_rows = (
        payload.get("category_rows")
        if isinstance(payload.get("category_rows"), dict)
        else {}
    )
    provided_counts = {
        "normal": _parse_positive_int(
            coalesce(raw_category_rows, "normal", default=coalesce(payload, "normal_rows", "normalRows", default=0)),
            default=0,
            minimum=0,
            maximum=52,
        ),
        "executive": _parse_positive_int(
            coalesce(
                raw_category_rows,
                "executive",
                default=coalesce(payload, "executive_rows", "executiveRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=52,
        ),
        "premium": _parse_positive_int(
            coalesce(raw_category_rows, "premium", default=coalesce(payload, "premium_rows", "premiumRows", default=0)),
            default=0,
            minimum=0,
            maximum=52,
        ),
        "vip": _parse_positive_int(
            coalesce(raw_category_rows, "vip", default=coalesce(payload, "vip_rows", "vipRows", default=0)),
            default=0,
            minimum=0,
            maximum=52,
        ),
    }
    provided_total = sum(provided_counts.values())
    if provided_total > 0:
        total_rows = max(1, min(52, provided_total))
    category_counts = _normalize_category_counts(total_rows, payload)

    screen, _ = Screen.objects.get_or_create(
        vendor_id=vendor.id,
        screen_number=hall,
        defaults={
            "screen_type": coalesce(payload, "screen_type", "screenType"),
            "status": "Active",
        },
    )
    screen.capacity = total_rows * total_columns
    provided_screen_type = coalesce(payload, "screen_type", "screenType")
    if provided_screen_type:
        screen.screen_type = provided_screen_type
    category_prices = _normalize_category_prices(payload, screen=screen)
    screen.normal_price = category_prices.get("normal")
    screen.executive_price = category_prices.get("executive")
    screen.premium_price = category_prices.get("premium")
    screen.vip_price = category_prices.get("vip")
    screen.status = "Active"
    screen.save(
        update_fields=[
            "capacity",
            "screen_type",
            "normal_price",
            "executive_price",
            "premium_price",
            "vip_price",
            "status",
        ]
    )

    row_labels = [_row_label_from_index(index) for index in range(total_rows)]
    row_category_map = _build_row_category_map(row_labels, category_counts)

    desired_pairs = set()
    for row_label in row_labels:
        seat_category = row_category_map.get(row_label, SEAT_CATEGORY_NORMAL)
        for col in range(1, total_columns + 1):
            seat_number = str(col)
            desired_pairs.add((row_label, seat_number))
            seat, created = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label,
                seat_number=seat_number,
                defaults={"seat_type": seat_category},
            )
            if not created and _normalize_seat_category(seat.seat_type) != seat_category:
                seat.seat_type = seat_category
                seat.save(update_fields=["seat_type"])

    existing_seats = Seat.objects.filter(screen=screen)
    for seat in existing_seats:
        pair = (str(seat.row_label or "").upper(), str(seat.seat_number or ""))
        if pair in desired_pairs:
            continue
        if seat.booking_seats.exists() or seat.availabilities.exists():
            continue
        seat.delete()

    show = _resolve_show_for_vendor(vendor, payload)
    showtime = _find_showtime_for_context(show, hall) if show else None
    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "category_rows": category_counts,
            "category_prices": _serialize_category_prices(category_prices),
            "message": "Seat layout saved.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def update_vendor_seat_status(request: Any) -> tuple[dict[str, Any], int]:
    """Update per-show seat status for vendor seats."""
    payload = get_payload(request)
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, payload)
    if error_payload:
        return error_payload, status_code

    show = _resolve_show_for_vendor(vendor, payload)
    if not show:
        return {"message": "show_id or valid show context is required."}, status.HTTP_400_BAD_REQUEST

    target_status = str(coalesce(payload, "status", "seat_status") or "").strip().lower()
    if target_status not in (
        SEAT_STATUS_AVAILABLE.lower(),
        SEAT_STATUS_UNAVAILABLE.lower(),
    ):
        return {"message": "status must be Available or Unavailable."}, status.HTTP_400_BAD_REQUEST

    status_label = (
        SEAT_STATUS_UNAVAILABLE
        if target_status == SEAT_STATUS_UNAVAILABLE.lower()
        else SEAT_STATUS_AVAILABLE
    )
    seat_labels = _normalize_seat_labels(
        coalesce(payload, "seat_labels", "seatLabels", "selected_seats", "selectedSeats", "seats")
    )
    if not seat_labels:
        return {"message": "seat_labels are required."}, status.HTTP_400_BAD_REQUEST

    hall = str(
        coalesce(payload, "hall", "cinema_hall", "cinemaHall", default=show.hall) or ""
    ).strip()
    screen, showtime = _get_or_create_showtime_for_context(show, hall or None)

    conflicts = {"booked": [], "invalid": []}
    updated = []
    with transaction.atomic():
        for label in seat_labels:
            row_label, seat_number = _split_seat_label(label)
            if not seat_number:
                conflicts["invalid"].append(label)
                continue

            seat, _ = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
                defaults={"seat_type": SEAT_CATEGORY_NORMAL},
            )
            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                conflicts["booked"].append(label)
                continue

            availability.seat_status = status_label
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])
            updated.append(label)

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "updated_seats": sorted(updated, key=_seat_sort_key),
            "conflicts": {
                "booked": sorted(conflicts["booked"], key=_seat_sort_key),
                "invalid": sorted(conflicts["invalid"], key=_seat_sort_key),
            },
            "message": "Seat status updated.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def list_booking_seat_layout(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return booking seat layout with category rows and seat statuses."""
    context = _resolve_booking_context(payload)
    show = _resolve_show_for_context(context)
    if not show:
        fallback = _build_default_layout_payload()
        fallback.update({"show_id": None, "showtime_id": None})
        return fallback, status.HTTP_200_OK

    show_booking_error, _ = _ensure_show_is_bookable(show)
    if show_booking_error:
        fallback = _build_default_layout_payload()
        fallback.update(
            {
                "show_id": show.id,
                "showtime_id": None,
                "booking_enabled": False,
                "message": show_booking_error.get("message"),
                "booking_close_at": show_booking_error.get("booking_close_at"),
            }
        )
        return fallback, status.HTTP_200_OK

    hall = str(context.get("hall") or show.hall or "").strip()
    screen = None
    if hall:
        screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number=hall).first()
    if not screen:
        screen = Screen.objects.filter(vendor_id=show.vendor_id).order_by("id").first()

    showtime = _find_showtime_for_context(show, hall or None)
    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "show_id": show.id,
            "hall": hall or layout_payload.get("hall"),
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "date": show.show_date.isoformat() if show.show_date else None,
            "time": show.start_time.strftime("%H:%M") if show.start_time else None,
            "reservedSeats": layout_payload.get("reserved_seats") or [],
        }
    )
    return layout_payload, status.HTTP_200_OK


def reserve_booking_seats(request: Any) -> tuple[dict[str, Any], int]:
    """Reserve seats temporarily for a booking context."""
    payload = get_payload(request)
    context = _resolve_booking_context(payload)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND
    show_booking_error, show_booking_status = _ensure_show_is_bookable(show)
    if show_booking_error:
        return show_booking_error, int(show_booking_status)

    hall = context.get("hall") or show.hall
    screen, showtime = _get_or_create_showtime_for_context(show, hall)
    _prune_expired_reservations(showtime)

    now = timezone.now()
    lock_until = now + timedelta(minutes=RESERVE_HOLD_MINUTES)
    conflicts = {"sold": [], "unavailable": [], "reserved": [], "invalid": []}
    updated = []

    with transaction.atomic():
        for label in selected_seats:
            row_label, seat_number = _split_seat_label(label)
            if not seat_number:
                conflicts["invalid"].append(label)
                continue

            seat, _ = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            )
            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                conflicts["sold"].append(label)
                continue
            if current_status == SEAT_STATUS_UNAVAILABLE.lower():
                conflicts["unavailable"].append(label)
                continue
            if availability.locked_until and availability.locked_until > now:
                conflicts["reserved"].append(label)
                continue

            availability.seat_status = SEAT_STATUS_AVAILABLE
            availability.locked_until = lock_until
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])
            updated.append(label)

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "show_id": show.id,
            "hall": hall or layout_payload.get("hall"),
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "date": show.show_date.isoformat() if show.show_date else None,
            "time": show.start_time.strftime("%H:%M") if show.start_time else None,
            "updated_seats": sorted(updated, key=_seat_sort_key),
            "conflicts": {
                "sold": sorted(conflicts["sold"], key=_seat_sort_key),
                "unavailable": sorted(conflicts["unavailable"], key=_seat_sort_key),
                "reserved": sorted(conflicts["reserved"], key=_seat_sort_key),
                "invalid": sorted(conflicts["invalid"], key=_seat_sort_key),
            },
            "message": "Seats reserved.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def release_booking_seats(request: Any) -> tuple[dict[str, Any], int]:
    """Release reserved seats for a booking context."""
    payload = get_payload(request)
    context = _resolve_booking_context(payload)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND

    hall = context.get("hall") or show.hall
    screen, showtime = _get_or_create_showtime_for_context(show, hall)
    _prune_expired_reservations(showtime)

    released = []
    invalid = []
    with transaction.atomic():
        for label in selected_seats:
            row_label, seat_number = _split_seat_label(label)
            if not seat_number:
                invalid.append(label)
                continue
            seat = Seat.objects.filter(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            ).first()
            if not seat:
                continue
            availability = (
                SeatAvailability.objects.select_for_update()
                .filter(seat=seat, showtime=showtime)
                .first()
            )
            if not availability:
                continue
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                continue
            if current_status == SEAT_STATUS_UNAVAILABLE.lower():
                continue
            if availability.locked_until:
                availability.locked_until = None
                availability.save(update_fields=["locked_until", "last_updated"])
                released.append(label)

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "show_id": show.id,
            "hall": hall or layout_payload.get("hall"),
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "date": show.show_date.isoformat() if show.show_date else None,
            "time": show.start_time.strftime("%H:%M") if show.start_time else None,
            "released_seats": sorted(released, key=_seat_sort_key),
            "invalid_seats": sorted(invalid, key=_seat_sort_key),
            "message": "Seats released.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def create_booking_resume_notification(request: Any) -> tuple[dict[str, Any], int]:
    """Create or refresh a customer notification to continue a held booking flow."""
    customer = resolve_customer(request)
    if not customer:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    context = _resolve_booking_context(payload)
    selected_seats = _normalize_seat_labels(
        coalesce(
            context,
            "selected_seats",
            default=coalesce(payload, "selected_seats", "selectedSeats", "seats"),
        )
    )
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    if not context.get("movie_id") or not context.get("cinema_id") or not context.get("show_date") or not context.get("show_time"):
        return {
            "message": "Booking context is incomplete. Provide cinema, movie, date, time, and selected seats.",
        }, status.HTTP_400_BAD_REQUEST

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND
    show_booking_error, show_booking_status = _ensure_show_is_bookable(show)
    if show_booking_error:
        return show_booking_error, int(show_booking_status)

    hall = context.get("hall") or show.hall
    screen, showtime = _get_or_create_showtime_for_context(show, hall)
    _prune_expired_reservations(showtime)

    now = timezone.now()
    active_seats: list[str] = []
    lock_deadlines: list[Any] = []
    for label in selected_seats:
        row_label, seat_number = _split_seat_label(label)
        if not seat_number:
            continue

        seat = Seat.objects.filter(
            screen=screen,
            row_label=row_label or None,
            seat_number=seat_number,
        ).first()
        if not seat:
            continue

        availability = SeatAvailability.objects.filter(seat=seat, showtime=showtime).first()
        if not availability:
            continue

        current_status = str(availability.seat_status or "").strip().lower()
        if current_status in BOOKED_STATUSES:
            continue
        if current_status == SEAT_STATUS_UNAVAILABLE.lower():
            continue
        if availability.locked_until and availability.locked_until > now:
            active_seats.append(label)
            lock_deadlines.append(availability.locked_until)

    if not active_seats:
        return {
            "message": "No active seat hold found to continue.",
        }, status.HTTP_400_BAD_REQUEST

    expires_at = (
        min(lock_deadlines)
        if lock_deadlines
        else now + timedelta(minutes=BOOKING_RESUME_NOTICE_WINDOW_MINUTES)
    )

    show_date_text = (
        show.show_date.isoformat() if show.show_date else str(context.get("show_date") or "")
    )
    show_time_text = (
        show.start_time.strftime("%H:%M") if show.start_time else str(context.get("show_time") or "")
    )

    sorted_seats = sorted(active_seats, key=_seat_sort_key)
    resume_context = {
        "movie_id": show.movie_id,
        "movie_title": show.movie.title if show.movie else None,
        "cinema_id": show.vendor_id,
        "cinema_name": show.vendor.name if show.vendor else None,
        "show_id": show.id,
        "hall": hall or "",
        "date": show_date_text,
        "time": show_time_text,
        "selected_seats": sorted_seats,
    }
    notice_key = (
        f"RESUME_BOOKING:{customer.id}:{show.id}:{showtime.id}:"
        f"{','.join(sorted_seats)}"
    )

    metadata = {
        "notice_key": notice_key,
        "request_status": "PENDING",
        "expires_at": expires_at.isoformat(),
        "hold_minutes": BOOKING_RESUME_NOTICE_WINDOW_MINUTES,
        "resume_path": "/booking",
        "resume_context": resume_context,
        "movie_title": resume_context.get("movie_title"),
        "vendor_name": resume_context.get("cinema_name"),
        "show_date": show_date_text,
        "show_time": show_time_text,
        "seat_count": len(sorted_seats),
        "seats": sorted_seats,
    }

    title = "Continue your booking"
    message = (
        f"{len(sorted_seats)} seat(s) are on hold for "
        f"{resume_context.get('movie_title') or 'your movie'}. Continue within 10 minutes."
    )

    existing = (
        Notification.objects.filter(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=customer.id,
            event_type=Notification.EVENT_BOOKING_RESUME_PENDING,
            metadata__notice_key=notice_key,
            metadata__request_status="PENDING",
        )
        .order_by("-created_at", "-id")
        .first()
    )

    if existing:
        existing.title = title
        existing.message = message
        existing.metadata = metadata
        existing.is_read = False
        existing.read_at = None
        existing.save(update_fields=["title", "message", "metadata", "is_read", "read_at"])
        notification = existing
    else:
        notification = _create_notification(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=customer.id,
            recipient_email=customer.email,
            event_type=Notification.EVENT_BOOKING_RESUME_PENDING,
            title=title,
            message=message,
            metadata=metadata,
            send_email_too=False,
        )

    return {
        "message": "Resume notification created.",
        "notification_id": notification.id,
        "expires_at": metadata["expires_at"],
        "resume_context": resume_context,
    }, status.HTTP_200_OK


def bulk_assign_booking_seats(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Assign bulk corporate seats to an existing booking based on seat category counts."""
    payload = get_payload(request)
    category_payload = coalesce(
        payload,
        "seat_category_counts",
        "seatCategoryCounts",
        "category_counts",
        "categoryCounts",
    )
    if not isinstance(category_payload, dict):
        return {
            "message": "seat_category_counts must be an object with categories and quantities.",
        }, status.HTTP_400_BAD_REQUEST

    requested_categories: dict[str, int] = {}
    for raw_category, raw_quantity in category_payload.items():
        normalized_category = _normalize_seat_category(raw_category)
        if normalized_category not in SEAT_CATEGORY_ORDER:
            return {
                "message": f"Invalid seat category: {raw_category}",
            }, status.HTTP_400_BAD_REQUEST
        category_key = SEAT_CATEGORY_KEYS.get(normalized_category, "normal")
        quantity = _parse_positive_int(raw_quantity, default=0, minimum=0, maximum=10000)
        if quantity > 0:
            requested_categories[category_key] = requested_categories.get(category_key, 0) + quantity

    total_requested = sum(requested_categories.values())
    if total_requested <= 0:
        return {
            "message": "At least one seat category count must be greater than zero.",
        }, status.HTTP_400_BAD_REQUEST

    if booking.booking_status and str(booking.booking_status).strip().lower() == "cancelled":
        return {"message": "Cannot assign seats to a cancelled booking."}, status.HTTP_409_CONFLICT

    showtime = booking.showtime
    screen = getattr(showtime, "screen", None)
    if not showtime or not screen:
        return {
            "message": "Booking showtime or screen context is invalid.",
        }, status.HTTP_400_BAD_REQUEST

    show = Show.objects.filter(
        vendor_id=screen.vendor_id,
        movie_id=showtime.movie_id,
        show_date=showtime.start_time.date(),
        start_time=showtime.start_time.time(),
        hall=screen.screen_number,
    ).first()

    if not show:
        # Use fallback info from showtime when exact Show row is unavailable.
        class _FallbackShow:
            pass

        fallback = _FallbackShow()
        fallback.movie_id = showtime.movie_id
        fallback.show_date = showtime.start_time.date()
        fallback.price = showtime.price
        show = fallback

    available_seats = _available_target_seats_for_showtime(showtime, screen)
    seats_by_category: dict[str, list[Seat]] = {
        "normal": [],
        "executive": [],
        "premium": [],
        "vip": [],
    }
    for seat in available_seats:
        cat_key = _seat_category_key(seat.seat_type)
        seats_by_category.setdefault(cat_key, []).append(seat)

    chosen_seats: list[Seat] = []
    insufficient: dict[str, dict[str, int]] = {}
    for category_key, needed in requested_categories.items():
        available_for_category = seats_by_category.get(category_key, [])
        if len(available_for_category) < needed:
            insufficient[category_key] = {
                "requested": needed,
                "available": len(available_for_category),
            }
        else:
            chosen_seats.extend(available_for_category[:needed])

    if insufficient:
        return {
            "message": "Not enough available seats in one or more requested categories.",
            "insufficient": insufficient,
        }, status.HTTP_409_CONFLICT

    now = timezone.now()
    assigned_labels: list[str] = []
    total_amount = booking.total_amount or Decimal("0.00")
    with transaction.atomic():
        for seat in chosen_seats:
            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            status_value = str(availability.seat_status or "").strip().lower()
            if status_value in BOOKED_STATUSES:
                return {"message": "Some seats are no longer available."}, status.HTTP_409_CONFLICT
            if status_value == SEAT_STATUS_UNAVAILABLE.lower():
                return {"message": "Some seats are unavailable."}, status.HTTP_409_CONFLICT
            if availability.locked_until and availability.locked_until > now:
                return {"message": "Some seats are currently reserved."}, status.HTTP_409_CONFLICT

            availability.seat_status = SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

            seat_price, _ = _resolve_dynamic_seat_price(
                show=show,
                showtime=showtime,
                screen=screen,
                seat_type=seat.seat_type,
                event_name="",
            )
            seat_price = seat_price or Decimal("0.00")
            BookingSeat.objects.create(
                booking=booking,
                showtime=showtime,
                seat=seat,
                seat_price=seat_price,
            )
            assigned_labels.append(_join_seat_label(seat.row_label, seat.seat_number))
            total_amount += seat_price

        booking.total_amount = total_amount
        booking.save(update_fields=["total_amount"])

    return {
        "message": "Corporate seats assigned successfully.",
        "booking_id": booking.id,
        "assigned_seats": sorted(assigned_labels, key=_seat_sort_key),
        "assigned_count": len(assigned_labels),
        "total_amount": float(total_amount),
    }, status.HTTP_200_OK


def _clamp_text(value: Any, limit: int = 44) -> str:
    """Clamp text to a fixed character limit."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _load_font(size: int, bold: bool = False) -> Any:
    """Load the configured font or fall back to a default."""
    candidates = []
    if bold:
        candidates = [
            "arialbd.ttf",
            "Arial Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "arial.ttf",
            "Arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "DejaVuSans.ttf",
        ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    """Normalize ticket line items from incoming payloads."""
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        qty = int(item.get("qty") or 0)
        price = _safe_number(item.get("price"))
        normalized.append({"name": name, "qty": qty, "price": price})
    return normalized


def _build_ticket_payload(order: dict[str, Any], reference: str, request: Any) -> dict[str, Any]:
    """Build the ticket payload that is persisted in the database."""
    if not isinstance(order, dict):
        order = {}
    movie = order.get("movie") if isinstance(order.get("movie"), dict) else {}
    booking_context = _resolve_booking_context(order)
    selected_seats = booking_context.get("selected_seats") or []
    booking_data = order.get("booking") if isinstance(order.get("booking"), dict) else {}
    user_id = (
        booking_context.get("user_id")
        or _coerce_int(coalesce(booking_data, "user_id", "userId"))
    )
    user_payload = None
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            full_name = " ".join(
                [part for part in [user.first_name, user.middle_name, user.last_name] if part]
            ).strip()
            user_payload = {
                "id": user.id,
                "name": full_name or user.email or str(user.id),
                "email": user.email,
                "phone": user.phone_number,
            }

    venue_raw = movie.get("venue") or ""
    venue_parts = [part.strip() for part in str(venue_raw).split(",") if part.strip()]
    venue_name = venue_parts[0] if venue_parts else str(venue_raw)
    venue_location = str(movie.get("cinemaLocation") or movie.get("location") or "").strip()
    explicit_cinema_name = str(movie.get("cinemaName") or "").strip()
    if explicit_cinema_name:
        venue_name = explicit_cinema_name
    show_date = venue_parts[1] if len(venue_parts) > 1 else ""
    show_time = venue_parts[2] if len(venue_parts) > 2 else ""
    if movie.get("showDate"):
        show_date = str(movie.get("showDate"))
    if movie.get("showTime"):
        show_time = str(movie.get("showTime"))
    if booking_context.get("show_date"):
        show_date = booking_context["show_date"].isoformat()
    if booking_context.get("show_time"):
        show_time = booking_context["show_time"].strftime("%I:%M %p")

    seat_label = str(movie.get("seat") or "").strip()
    if selected_seats:
        seat_label = f"Seat No: {', '.join(selected_seats)}"

    theater = (
        booking_context.get("hall")
        or movie.get("theater")
        or movie.get("screen")
        or movie.get("hall")
    )
    if not theater:
        match = re.search(r"\b(\d{1,2})\b", venue_name)
        theater = match.group(1).zfill(2) if match else "03"

    ticket_total = _safe_number(order.get("ticketTotal"))
    food_total = _safe_number(order.get("foodTotal"))
    total = _safe_number(order.get("total") or (ticket_total + food_total))
    payload = {
        "reference": reference,
        "movie": {
            "title": str(movie.get("title") or ""),
            "seat": seat_label,
            "venue": str(venue_raw),
            "venue_name": str(venue_name),
            "venue_location": venue_location,
            "show_date": str(show_date),
            "show_time": str(show_time),
            "theater": str(theater),
            "language": str(movie.get("language") or ""),
            "runtime": str(movie.get("runtime") or ""),
            "movie_id": booking_context.get("movie_id"),
            "cinema_id": booking_context.get("cinema_id"),
            "show_id": booking_context.get("show_id"),
        },
        "selected_seats": selected_seats,
        "ticket_total": ticket_total,
        "food_total": food_total,
        "total": total,
        "items": _normalize_items(order.get("items")),
        "user": user_payload,
        "created_at": timezone.now().isoformat(),
    }
    payload["details_url"] = request.build_absolute_uri(
        f"/api/ticket/{reference}/details/"
    )
    return payload


def _build_qr_image(data: str) -> Optional[Any]:
    """Build a QR image from the supplied data."""
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _image_to_data_url(image: Any) -> str:
    """Convert a PIL image into a data URL string."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _text_size(draw: Any, text: str, font: Any) -> tuple[int, int]:
    """Return text dimensions for the given font."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _draw_perforations(
    draw: Any, rect: tuple[int, int, int, int], bg_color: str, radius: int = 7, step: int = 22
) -> None:
    """Draw perforation holes around a rectangle."""
    left, top, right, bottom = rect
    for x in range(left + radius, right - radius + 1, step):
        draw.ellipse(
            (x - radius, top - radius, x + radius, top + radius), fill=bg_color
        )
        draw.ellipse(
            (x - radius, bottom - radius, x + radius, bottom + radius), fill=bg_color
        )
    for y in range(top + radius, bottom - radius + 1, step):
        draw.ellipse(
            (left - radius, y - radius, left + radius, y + radius), fill=bg_color
        )
        draw.ellipse(
            (right - radius, y - radius, right + radius, y + radius), fill=bg_color
        )


def _draw_barcode(
    draw: Any, box: tuple[int, int, int, int], seed_value: str, color: str = "#1f2933"
) -> None:
    """Draw a fake barcode pattern for styling."""
    rng = random.Random(seed_value)
    x0, y0, x1, y1 = box
    x = x0
    while x < x1:
        bar_width = rng.choice([1, 1, 2, 2, 3])
        gap = rng.choice([1, 1, 2])
        bar_end = min(x + bar_width, x1)
        draw.rectangle((x, y0, bar_end, y1), fill=color)
        x = bar_end + gap


def _render_ticket_image(payload: dict[str, Any], qr_image: Any) -> Any:
    """Render a ticket image for download and QR display."""
    width, height = 1100, 380
    bg_color = "#3f3f44"
    paper_color = "#ffffff"
    border_color = "#d7d7d7"
    text_color = "#1f2937"
    muted_color = "#6b7280"
    accent_color = "#e11d48"

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    margin = 24
    ticket_rect = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(
        ticket_rect, radius=18, fill=paper_color, outline=border_color, width=2
    )
    _draw_perforations(draw, ticket_rect, bg_color, radius=8, step=24)

    ticket_width = ticket_rect[2] - ticket_rect[0]
    separator_x = ticket_rect[0] + int(ticket_width * 0.7)
    dash_y = ticket_rect[1] + 18
    while dash_y < ticket_rect[3] - 18:
        draw.line(
            (separator_x, dash_y, separator_x, dash_y + 10),
            fill=border_color,
            width=2,
        )
        dash_y += 18

    brand_font = _load_font(22, bold=True)
    title_font = _load_font(30, bold=True)
    label_font = _load_font(12, bold=True)
    value_font = _load_font(16, bold=False)
    small_font = _load_font(13, bold=False)

    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    title = str(movie.get("title") or "")
    venue_name = str(movie.get("venue_name") or movie.get("venue") or "")
    seat_raw = str(movie.get("seat") or "")
    seat_value = re.sub(r"(?i)seat\s*no\s*[:#-]?", "", seat_raw).strip() or "-"
    theater = str(movie.get("theater") or "03")
    show_date = str(movie.get("show_date") or "")
    show_time = str(movie.get("show_time") or "")
    reference = str(payload.get("reference") or "")
    ticket_total = payload.get("ticket_total")
    if ticket_total is None:
        ticket_total = payload.get("total")
    food_total = payload.get("food_total")
    total_value = payload.get("total")
    ticket_value = int(_safe_number(ticket_total))
    food_value = int(_safe_number(food_total))
    total_value = int(_safe_number(total_value))

    left_barcode_box = (
        ticket_rect[0] + 12,
        ticket_rect[1] + 18,
        ticket_rect[0] + 48,
        ticket_rect[3] - 18,
    )
    _draw_barcode(draw, left_barcode_box, reference + "left", color=text_color)

    left_x = left_barcode_box[2] + 18
    left_y = ticket_rect[1] + 18

    brand_text = "MERO TICKET"
    brand_w, brand_h = _text_size(draw, brand_text, brand_font)
    brand_rect = (left_x, left_y, left_x + brand_w + 18, left_y + brand_h + 10)
    draw.rounded_rectangle(brand_rect, radius=10, fill=accent_color)
    draw.text((left_x + 9, left_y + 5), brand_text, fill="#ffffff", font=brand_font)

    left_y = brand_rect[3] + 12
    movie_title = _clamp_text(title.upper(), 22)
    draw.text((left_x, left_y), movie_title, fill=accent_color, font=title_font)
    left_y += 36

    def draw_line(label, value, current_y):
        line = f"{label} : {value or '-'}"
        draw.text(
            (left_x, current_y),
            _clamp_text(line, 40),
            fill=text_color,
            font=value_font,
        )
        return current_y + 22

    left_y = draw_line("CINEMA", venue_name, left_y)
    left_y = draw_line("THEATER", theater, left_y)
    left_y = draw_line("SEAT", seat_value, left_y)
    left_y = draw_line("DATE", show_date, left_y)
    left_y = draw_line("TIME", show_time, left_y)
    left_y = draw_line("TICKET", f"NPR {ticket_value}", left_y)
    left_y = draw_line("FOOD", f"NPR {food_value}", left_y)
    left_y = draw_line("TOTAL", f"NPR {total_value}", left_y)

    draw.text(
        (left_x, ticket_rect[3] - 28),
        _clamp_text(f"REF : {reference}", 26),
        fill=muted_color,
        font=small_font,
    )

    right_x = separator_x + 18
    right_y = ticket_rect[1] + 20
    draw.text((right_x, right_y), "ADMIT ONE", fill=text_color, font=label_font)
    right_y += 20
    draw.text((right_x, right_y), "STANDARD 3D", fill=muted_color, font=label_font)
    right_y += 22
    draw.text(
        (right_x, right_y),
        _clamp_text(f"THEATER : {theater}", 22),
        fill=muted_color,
        font=small_font,
    )
    right_y += 18
    draw.text(
        (right_x, right_y),
        _clamp_text(f"SEAT : {seat_value}", 22),
        fill=muted_color,
        font=small_font,
    )
    right_y += 18

    if show_date or show_time:
        show_line = " ".join([value for value in [show_date, show_time] if value]).strip()
        draw.text(
            (right_x, right_y),
            _clamp_text(show_line, 22),
            fill=muted_color,
            font=small_font,
        )
        right_y += 18


def get_vendor_analytics(vendor: Vendor, request: Any) -> dict[str, Any]:
    """Build comprehensive analytics payload for a vendor dashboard."""
    try:
        # Get bookings for this vendor through their shows
        vendor_bookings = Booking.objects.filter(
            showtime__screen__vendor=vendor
        ).select_related('user', 'showtime', 'showtime__movie', 'showtime__screen')
        
        # Get all payments related to vendor bookings
        vendor_payments = Payment.objects.filter(
            booking__in=vendor_bookings
        )
        
        # Get vendor shows
        vendor_shows = Show.objects.filter(vendor=vendor)
        
        # Get vendor food items and their bookings
        vendor_food_items = FoodItem.objects.filter(vendor=vendor)
        vendor_food_bookings = BookingFoodItem.objects.filter(
            booking__in=vendor_bookings
        )
        
        # Get booking seats
        vendor_booking_seats = BookingSeat.objects.filter(booking__in=vendor_bookings)
        
        # Calculate key metrics
        total_bookings = vendor_bookings.count()
        confirmed_bookings = vendor_bookings.filter(booking_status='Confirmed').count()
        completed_bookings = vendor_bookings.filter(booking_status='Completed').count()
        
        total_revenue = float(vendor_payments.filter(
            payment_status='Success'
        ).values_list('amount', flat=True).aggregate(
            total=Sum('amount')
        )['total'] or 0)
        
        total_seats_booked = vendor_booking_seats.count()
        total_shows = vendor_shows.count()
        
        # Revenue breakdown
        successful_payments = vendor_payments.filter(payment_status='Success')
        payment_methods = {}
        for payment in successful_payments:
            method = payment.payment_method or 'Unknown'
            if method not in payment_methods:
                payment_methods[method] = {'count': 0, 'total': 0}
            payment_methods[method]['count'] += 1
            payment_methods[method]['total'] += float(payment.amount or 0)
        
        # Booking status breakdown
        booking_status_breakdown = {
            'Pending': vendor_bookings.filter(booking_status='Pending').count(),
            'Confirmed': confirmed_bookings,
            'Completed': completed_bookings,
            'Cancelled': vendor_bookings.filter(booking_status='Cancelled').count(),
        }
        
        # Top selling food items
        top_food_items = vendor_food_bookings.values(
            'food_item__item_name',
            'food_item__category'
        ).annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-quantity')[:5]
        
        # Convert Decimal to float for JSON serialization
        top_food_list = [
            {
                'name': item['food_item__item_name'],
                'category': item['food_item__category'],
                'quantity': item['quantity'],
                'revenue': float(item['revenue'] or 0)
            }
            for item in top_food_items
        ]
        
        # Get recent bookings
        recent_bookings = vendor_bookings.order_by('-booking_date')[:5]
        recent_bookings_list = [
            {
                'id': booking.id,
                'user': booking.user.first_name + ' ' + booking.user.last_name,
                'status': booking.booking_status,
                'total': float(booking.total_amount or 0),
                'date': booking.booking_date.isoformat(),
                'seats': booking.booking_seats.count()
            }
            for booking in recent_bookings
        ]
        
        # Seat utilization
        total_available_seats = Seat.objects.filter(
            screen__vendor=vendor
        ).count()
        seat_utilization_percentage = (
            (total_seats_booked / total_available_seats * 100) 
            if total_available_seats > 0 else 0
        )
        
        # Monthly booking trend (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        monthly_bookings = vendor_bookings.filter(
            booking_date__gte=thirty_days_ago
        ).extra(
            select={'date': 'DATE(booking_date)'}
        ).values('date').annotate(
            count=Count('id'),
            revenue=Sum('payments__amount')
        ).order_by('date')
        
        monthly_trend = [
            {
                'date': str(item['date']),
                'bookings': item['count'],
                'revenue': float(item['revenue'] or 0)
            }
            for item in monthly_bookings
        ]
        
        # Top shows
        top_shows = vendor_bookings.values(
            'showtime__movie__title'
        ).annotate(
            bookings=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('-bookings')[:5]
        
        top_shows_list = [
            {
                'title': show['showtime__movie__title'],
                'bookings': show['bookings'],
                'revenue': float(show['revenue'] or 0)
            }
            for show in top_shows
        ]
        
        # Food category distribution
        food_by_category = vendor_food_bookings.values(
            'food_item__category'
        ).annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-quantity')
        
        food_category_list = [
            {
                'name': item['food_item__category'] or 'Uncategorized',
                'quantity': item['quantity'],
                'revenue': float(item['revenue'] or 0)
            }
            for item in food_by_category
        ]
        
        # Bookings by day of week
        weekly_distribution = vendor_bookings.extra(
            select={'day_of_week': 'DAYOFWEEK(booking_date)'}
        ).values('day_of_week').annotate(
            count=Count('id')
        ).order_by('day_of_week')
        
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        weekly_bookings = []
        for day_num in range(1, 8):
            day_data = next((item for item in weekly_distribution if item['day_of_week'] == day_num), None)
            weekly_bookings.append({
                'day': days[day_num - 1],
                'bookings': day_data['count'] if day_data else 0
            })
        
        # Average booking value trend
        booking_value_stats = vendor_bookings.aggregate(
            avg_value=Avg('total_amount'),
            max_value=Max('total_amount'),
            min_value=Min('total_amount')
        )
        
        # Revenue per show
        revenue_per_show = vendor_bookings.values(
            'showtime__movie__title'
        ).annotate(
            count=Count('id'),
            total_revenue=Sum('total_amount')
        ).order_by('-total_revenue')[:10]
        
        revenue_per_show_list = [
            {
                'show': item.get('showtime__movie__title', 'Unknown'),
                'bookings': item['count'],
                'revenue': float(item['total_revenue'] or 0)
            }
            for item in revenue_per_show
        ]
        
        return {
            'vendor_id': vendor.id,
            'vendor_name': vendor.name,
            'summary': {
                'total_bookings': total_bookings,
                'confirmed_bookings': confirmed_bookings,
                'completed_bookings': completed_bookings,
                'total_revenue': total_revenue,
                'total_seats_booked': total_seats_booked,
                'total_shows': total_shows,
                'seat_utilization_percentage': round(seat_utilization_percentage, 2),
                'total_food_items_sold': vendor_food_bookings.aggregate(
                    total=Sum('quantity')
                )['total'] or 0,
            },
            'payment_methods': payment_methods,
            'booking_status_breakdown': booking_status_breakdown,
            'top_food_items': top_food_list,
            'top_shows': top_shows_list,
            'recent_bookings': recent_bookings_list,
            'monthly_trend': monthly_trend,
            'food_by_category': food_category_list,
            'weekly_bookings': weekly_bookings,
            'booking_value_stats': booking_value_stats,
            'revenue_per_show': revenue_per_show_list,
            'message': 'Analytics data retrieved successfully'
        }
    except Exception as e:
        logger.error(f"Error building vendor analytics: {str(e)}")
        return {
            'error': str(e),
            'message': 'Failed to retrieve analytics data'
        }

    right_limit = ticket_rect[2] - 18
    if qr_image:
        qr_size = min(130, right_limit - right_x)
        if qr_size >= 90:
            qr_resized = qr_image.resize((qr_size, qr_size))
            img.paste(qr_resized, (right_x, right_y))
            right_y += qr_size + 12

    barcode_width = min(200, right_limit - right_x)
    barcode_box = (
        right_x,
        ticket_rect[3] - 76,
        right_x + barcode_width,
        ticket_rect[3] - 24,
    )
    _draw_barcode(draw, barcode_box, reference + "right", color=text_color)
    draw.text(
        (right_x, ticket_rect[3] - 22),
        _clamp_text(f"NO. {reference}", 20),
        fill=text_color,
        font=small_font,
    )

    return img


def _render_food_slip_image(payload: dict[str, Any]) -> Any:
    """Render a food slip image for download."""
    width = 820
    bg_color = "#3f3f44"
    paper_color = "#ffffff"
    border_color = "#d7d7d7"
    text_color = "#1f2937"
    muted_color = "#6b7280"
    accent_color = "#f59e0b"

    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    title = str(movie.get("title") or "")
    reference = str(payload.get("reference") or "")
    show_date = str(movie.get("show_date") or "")
    show_time = str(movie.get("show_time") or "")
    food_total = int(_safe_number(payload.get("food_total")))
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    item_lines = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        qty = int(item.get("qty") or 0)
        line = f"{_clamp_text(name, 28)} x{qty}" if qty else _clamp_text(name, 28)
        item_lines.append(line)
    if not item_lines:
        item_lines = ["No food items"]

    line_height = 18
    extra_meta = 20 if show_date or show_time else 0
    height = 230 + extra_meta + len(item_lines) * line_height
    height = max(height, 260)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    margin = 22
    slip_rect = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(
        slip_rect, radius=16, fill=paper_color, outline=border_color, width=2
    )
    _draw_perforations(draw, slip_rect, bg_color, radius=7, step=22)

    brand_font = _load_font(16, bold=True)
    title_font = _load_font(24, bold=True)
    body_font = _load_font(16, bold=False)
    small_font = _load_font(12, bold=False)
    label_font = _load_font(12, bold=True)

    x = slip_rect[0] + 18
    y = slip_rect[1] + 16
    draw.text((x, y), "MERO TICKET", fill=text_color, font=brand_font)
    y += 22

    slip_text = "FOOD SLIP"
    slip_w, slip_h = _text_size(draw, slip_text, title_font)
    slip_rect_box = (x, y, x + slip_w + 18, y + slip_h + 10)
    draw.rounded_rectangle(slip_rect_box, radius=8, fill=accent_color)
    draw.text((x + 9, y + 5), slip_text, fill="#1f2937", font=title_font)
    y = slip_rect_box[3] + 12

    if title:
        draw.text((x, y), _clamp_text(title, 34), fill=muted_color, font=body_font)
        y += 20

    if show_date or show_time:
        show_line = " ".join([value for value in [show_date, show_time] if value]).strip()
        draw.text((x, y), _clamp_text(show_line, 34), fill=muted_color, font=body_font)
        y += 20

    draw.text((x, y), "ITEMS", fill=muted_color, font=label_font)
    y += 18
    for line in item_lines:
        draw.text((x, y), line, fill=text_color, font=body_font)
        y += line_height

    y += 8
    amount_text = f"BILL AMOUNT : NPR {food_total}"
    draw.text((x, y), amount_text, fill=text_color, font=title_font)

    draw.text(
        (x, slip_rect[3] - 24),
        _clamp_text(f"REF : {reference}", 28),
        fill=muted_color,
        font=small_font,
    )

    return img


def _render_ticket_bundle_image(payload: dict[str, Any], qr_image: Any) -> Any:
    """Render the combined ticket + food slip bundle image."""
    bg_color = "#3f3f44"
    ticket_image = _render_ticket_image(payload, qr_image)
    food_image = _render_food_slip_image(payload)
    margin = 24
    spacing = 20
    width = max(ticket_image.width, food_image.width) + margin * 2
    height = ticket_image.height + food_image.height + spacing + margin * 2
    img = Image.new("RGB", (width, height), bg_color)
    ticket_x = (width - ticket_image.width) // 2
    food_x = (width - food_image.width) // 2
    img.paste(ticket_image, (ticket_x, margin))
    img.paste(food_image, (food_x, margin + ticket_image.height + spacing))
    return img


def create_payment_qr(request: Any) -> tuple[dict[str, Any], int]:
    """Create a payment QR and store a ticket record."""
    payload = get_payload(request)
    order = payload.get("order", {}) if isinstance(payload, dict) else {}
    if not order:
        return {"message": "Order data is required"}, status.HTTP_400_BAD_REQUEST

    booking_payload, booking_error, booking_status = _create_booking_from_order(order)
    if booking_error:
        return booking_error, booking_status

    reference = uuid.uuid4().hex[:10].upper()
    ticket_payload = _build_ticket_payload(order, reference, request)
    booking_instance: Optional[Booking] = None
    if booking_payload:
        ticket_payload["booking"] = booking_payload
        booking_id = _coerce_int(booking_payload.get("booking_id"))
        if booking_id:
            booking_instance = Booking.objects.select_related(
                "user",
                "showtime__movie",
                "showtime__screen__vendor",
            ).filter(pk=booking_id).first()
    Ticket.objects.create(reference=reference, payload=ticket_payload)

    if booking_instance:
        linked_show = Show.objects.filter(
            vendor_id=booking_instance.showtime.screen.vendor_id,
            movie_id=booking_instance.showtime.movie_id,
            show_date=booking_instance.showtime.start_time.date(),
            start_time=booking_instance.showtime.start_time.time(),
        ).first()
        if linked_show:
            try:
                _notify_payment_success(booking_instance, linked_show)
            except Exception:
                logger.exception("Failed to dispatch payment-success notifications for booking %s", booking_instance.id)

    details_url = ticket_payload.get("details_url", "")
    qr_image = _build_qr_image(details_url)
    if not qr_image:
        return {
            "message": "QR code library not installed. Please install qrcode."
        }, status.HTTP_500_INTERNAL_SERVER_ERROR

    ticket_image = _render_ticket_bundle_image(ticket_payload, qr_image)
    return {
        "message": "Payment ticket created",
        "reference": reference,
        "booking": booking_payload,
        "qr_code": _image_to_data_url(qr_image),
        "ticket_image": _image_to_data_url(ticket_image),
        "download_url": request.build_absolute_uri(f"/api/ticket/{reference}/download/"),
        "details_url": details_url,
    }, status.HTTP_200_OK


def build_ticket_download(reference: str) -> Optional[bytes]:
    """Return a rendered ticket PNG for download."""
    ticket = get_ticket(reference)
    if not ticket:
        return None

    payload = ticket.payload or {}
    qr_image = _build_qr_image(payload.get("details_url", ""))
    ticket_image = _render_ticket_image(payload, qr_image)
    buffer = io.BytesIO()
    ticket_image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


def build_ticket_details_html(reference: str) -> Optional[str]:
    """Return an HTML receipt for a ticket reference."""
    ticket = get_ticket(reference)
    if not ticket:
        return None

    payload = ticket.payload or {}
    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    user = payload.get("user", {}) if isinstance(payload.get("user"), dict) else {}
    venue_name = movie.get("venue_name") or movie.get("venue") or ""
    venue_location = movie.get("venue_location") or ""
    show_date = movie.get("show_date") or ""
    show_time = movie.get("show_time") or ""
    theater = movie.get("theater") or ""
    ticket_total = int(_safe_number(payload.get("ticket_total")))
    food_total = int(_safe_number(payload.get("food_total")))
    grand_total = int(_safe_number(payload.get("total")))

    items_html = ""
    if items:
        rows = []
        for item in items:
            name = escape(str(item.get("name", "")))
            qty_value = int(item.get("qty") or 0)
            unit_price = int(_safe_number(item.get("price")))
            line_total = unit_price * qty_value
            qty_label = f"{qty_value}" if qty_value else "-"
            rows.append(
                f"""
                <div class=\"item-row\">
                  <div>
                    <div class=\"item-name\">{name or '-'}</div>
                    <div class=\"item-meta\">Qty {escape(qty_label)} | NPR {escape(str(unit_price))}</div>
                  </div>
                  <div class=\"item-total\">NPR {escape(str(line_total))}</div>
                </div>
                """
            )
        items_html = "<div class=\"items\">" + "".join(rows) + "</div>"

    location_html = ""
    if venue_location:
        location_html = f"""
            <div class="row">
              <div class="label">Location</div>
              <div class="value">{escape(str(venue_location))}</div>
            </div>
        """

    user_html = ""
    if user:
        name_value = escape(str(user.get("name") or ""))
        email_value = escape(str(user.get("email") or ""))
        phone_value = escape(str(user.get("phone") or ""))
        rows = []
        if name_value:
            rows.append(
                f"""
                <div class="row">
                  <div class="label">Customer</div>
                  <div class="value">{name_value}</div>
                </div>
                """
            )
        if email_value:
            rows.append(
                f"""
                <div class="row">
                  <div class="label">Email</div>
                  <div class="value">{email_value}</div>
                </div>
                """
            )
        if phone_value:
            rows.append(
                f"""
                <div class="row">
                  <div class="label">Phone</div>
                  <div class="value">{phone_value}</div>
                </div>
                """
            )
        if rows:
            user_html = (
                '<div class="section"><div class="section-title">Customer</div>'
                + "".join(rows)
                + "</div>"
            )

    html = f"""
    <html>
      <head>
        <title>Ticket {escape(reference)}</title>
        <style>
          :root {{
            --paper: #fff9f2;
            --ink: #1f2937;
            --muted: #6b7280;
            --accent: #111827;
            --line: #e5e7eb;
          }}
          body {{
            font-family: Arial, sans-serif;
            background: #0f1116;
            color: var(--ink);
            padding: 24px;
          }}
          .receipt {{
            background: var(--paper);
            border-radius: 18px;
            padding: 22px 20px;
            width: min(420px, 100%);
            margin: 0 auto;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
            border: 1px solid #e7e0d6;
          }}
          .receipt-header {{
            text-align: center;
            padding-bottom: 12px;
            border-bottom: 1px dashed #d6d3d1;
            margin-bottom: 14px;
          }}
          .brand {{
            font-size: 13px;
            letter-spacing: 0.28em;
            text-transform: uppercase;
            font-weight: 800;
            color: var(--accent);
          }}
          .title {{
            font-size: 18px;
            font-weight: 800;
            margin: 8px 0 4px;
          }}
          .meta {{
            color: var(--muted);
            font-size: 12px;
          }}
          .section {{
            padding: 10px 0;
            border-bottom: 1px dashed #d6d3d1;
          }}
          .section:last-child {{
            border-bottom: none;
          }}
          .section-title {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: var(--muted);
            margin-bottom: 8px;
          }}
          .row {{
            display: grid;
            gap: 4px;
            padding: 6px 0;
          }}
          .label {{
            color: var(--muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
          }}
          .value {{
            font-size: 15px;
            font-weight: 700;
          }}
          .items {{
            display: grid;
            gap: 10px;
            font-weight: 400;
          }}
          .item-row {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            padding: 8px 0;
            border-top: 1px dotted var(--line);
          }}
          .item-row:first-child {{
            border-top: none;
            padding-top: 0;
          }}
          .item-name {{
            font-weight: 700;
            font-size: 14px;
          }}
          .item-meta {{
            font-size: 12px;
            color: var(--muted);
            margin-top: 2px;
            font-weight: 400;
          }}
          .item-total {{
            font-weight: 800;
            font-size: 14px;
            white-space: nowrap;
          }}
          .total-row {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            font-size: 14px;
            padding: 6px 0;
          }}
          .total-row strong {{
            font-size: 16px;
          }}
        </style>
      </head>
      <body>
        <div class="receipt">
          <div class="receipt-header">
            <div class="brand">Mero Ticket</div>
            <div class="title">Ticket & Food Bill</div>
            <div class="meta">Reference: {escape(reference)}</div>
          </div>

          <div class="section">
            <div class="section-title">Ticket Details</div>
            <div class="row">
              <div class="label">Movie</div>
              <div class="value">{escape(movie.get("title", ""))}</div>
            </div>
            <div class="row">
              <div class="label">Cinema Hall</div>
              <div class="value">{escape(str(venue_name))}</div>
            </div>
            {location_html}
            <div class="row">
              <div class="label">Theater</div>
              <div class="value">{escape(str(theater))}</div>
            </div>
            <div class="row">
              <div class="label">Seat</div>
              <div class="value">{escape(movie.get("seat", ""))}</div>
            </div>
            <div class="row">
              <div class="label">Date</div>
              <div class="value">{escape(str(show_date))}</div>
            </div>
            <div class="row">
              <div class="label">Time</div>
              <div class="value">{escape(str(show_time))}</div>
            </div>
          </div>

          {user_html}

          <div class="section">
            <div class="section-title">Food Items</div>
            <div class="row">
              <div class="label">Food Items</div>
              <div class="value">{items_html or "No food items"}</div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Totals</div>
            <div class="row">
              <div class="label">Ticket Total</div>
              <div class="value">NPR {escape(str(ticket_total))}</div>
            </div>
            <div class="row">
              <div class="label">Food Total</div>
              <div class="value">NPR {escape(str(food_total))}</div>
            </div>
            <div class="row">
              <div class="label">Grand Total</div>
              <div class="value">NPR {escape(str(grand_total))}</div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """
    return html
