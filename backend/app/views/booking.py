"""Booking flow and ticket generation API views."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import selectors, services
from ..models import Booking, BookingSeat, Payment, Seat, SeatAvailability, Show, Ticket
from ..permissions import ROLE_CUSTOMER, role_required
from ..utils import coalesce, parse_bool, parse_date


ESEWA_SIGNED_FIELD_NAMES = "total_amount,transaction_uuid,product_code"
ESEWA_PENDING_CACHE_PREFIX = "mt:esewa:pending:"
ESEWA_PAYMENT_METHOD_PREFIX = "ESEWA:"


def _esewa_product_code() -> str:
    value = str(getattr(settings, "ESEWA_PRODUCT_CODE", "EPAYTEST") or "").strip()
    return value or "EPAYTEST"


def _esewa_secret_key() -> str:
    value = str(getattr(settings, "ESEWA_SECRET_KEY", "8gBm/:&EnhH.1/q") or "").strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1].strip()
    return value or "8gBm/:&EnhH.1/q"


def _esewa_form_url() -> str:
    value = str(
        getattr(
            settings,
            "ESEWA_FORM_URL",
            "https://rc-epay.esewa.com.np/api/epay/main/v2/form",
        )
        or ""
    ).strip()
    return value or "https://rc-epay.esewa.com.np/api/epay/main/v2/form"


def _esewa_status_check_url() -> str:
    value = str(
        getattr(
            settings,
            "ESEWA_STATUS_CHECK_URL",
            "https://rc.esewa.com.np/api/epay/transaction/status/",
        )
        or ""
    ).strip()
    return value or "https://rc.esewa.com.np/api/epay/transaction/status/"


def _esewa_pending_ttl_seconds() -> int:
    configured = getattr(settings, "ESEWA_PENDING_TTL_SECONDS", 1800)
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = 1800
    return max(parsed, 60)


def _frontend_base_url() -> str:
    value = str(getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173") or "").strip()
    return value or "http://localhost:5173"


def _coerce_int(value: Any) -> Optional[int]:
    """Safely coerce a value into an int or return None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_decimal(value: Any) -> Optional[Decimal]:
    """Safely coerce a value into Decimal or return None."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_amount(value: Decimal) -> str:
    """Format amount string for eSewa signature and form fields."""
    normalized = (
        (value if isinstance(value, Decimal) else Decimal(str(value or 0)))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        .normalize()
    )
    as_text = format(normalized, "f")
    if "." in as_text:
        as_text = as_text.rstrip("0").rstrip(".")
    return as_text or "0"


def _build_transaction_uuid() -> str:
    """Build eSewa-safe transaction UUID (alphanumeric and hyphen only)."""
    now = datetime.utcnow()
    return f"{now.strftime('%y%m%d-%H%M%S')}-{now.microsecond // 1000:03d}"


def _build_signature(message: str) -> str:
    """Build HMAC-SHA256 signature and return Base64 encoded digest."""
    digest = hmac.new(
        _esewa_secret_key().encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _decode_esewa_data(data_value: str) -> dict[str, Any]:
    """Decode Base64 encoded eSewa callback data into JSON payload."""
    cleaned = str(data_value or "").strip().replace(" ", "+")
    if not cleaned:
        return {}
    padding = "=" * (-len(cleaned) % 4)
    encoded = f"{cleaned}{padding}"
    try:
        decoded_bytes = base64.urlsafe_b64decode(encoded)
    except Exception:
        decoded_bytes = base64.b64decode(encoded)
    decoded_text = decoded_bytes.decode("utf-8")
    payload = json.loads(decoded_text)
    return payload if isinstance(payload, dict) else {}


def _verify_esewa_payload(payload: dict[str, Any]) -> tuple[bool, str, str]:
    """Verify callback payload signature using signed_field_names order."""
    signed_fields = str(payload.get("signed_field_names") or "").strip()
    if not signed_fields:
        return False, "", "signed_field_names is missing"

    field_names = [name.strip() for name in signed_fields.split(",") if name.strip()]
    if not field_names:
        return False, "", "signed_field_names is invalid"

    message = ",".join(
        f"{name}={'' if payload.get(name) is None else payload.get(name)}"
        for name in field_names
    )
    expected_signature = _build_signature(message)
    received_signature = str(payload.get("signature") or "")
    is_valid = hmac.compare_digest(expected_signature, received_signature)
    return is_valid, expected_signature, message


def _pending_cache_key(transaction_uuid: str) -> str:
    """Return cache key for one pending eSewa transaction."""
    return f"{ESEWA_PENDING_CACHE_PREFIX}{transaction_uuid}"


def _store_pending_transaction(
    *,
    transaction_uuid: str,
    order: Optional[dict[str, Any]],
    amount_text: str,
    success_url: str,
    failure_url: str,
    booking_id: Optional[int] = None,
) -> None:
    """Store pending checkout payload so booking can be confirmed after callback verify."""
    cache.set(
        _pending_cache_key(transaction_uuid),
        {
            "transaction_uuid": transaction_uuid,
            "order": order if isinstance(order, dict) else None,
            "total_amount": amount_text,
            "success_url": success_url,
            "failure_url": failure_url,
            "booking_id": booking_id,
            "initiated_at": timezone.now().isoformat(),
        },
        timeout=_esewa_pending_ttl_seconds(),
    )


def _get_pending_transaction(transaction_uuid: str) -> Optional[dict[str, Any]]:
    """Load pending checkout payload for a transaction UUID."""
    cached = cache.get(_pending_cache_key(transaction_uuid))
    return cached if isinstance(cached, dict) else None


def _clear_pending_transaction(transaction_uuid: str) -> None:
    """Delete pending checkout payload for a transaction UUID."""
    cache.delete(_pending_cache_key(transaction_uuid))


def _normalize_order_payload(order: Any) -> Optional[dict[str, Any]]:
    """Normalize frontend order payload shape into backend booking context expectations."""
    if not isinstance(order, dict):
        return None

    normalized = dict(order)
    booking_context = normalized.get("booking")
    if not isinstance(booking_context, dict):
        booking_context = normalized.get("bookingContext")
    if isinstance(booking_context, dict):
        normalized["booking"] = dict(booking_context)

    selected_seats = coalesce(
        normalized,
        "selectedSeats",
        "selected_seats",
        default=coalesce(booking_context or {}, "selectedSeats", "selected_seats"),
    )
    if selected_seats is not None:
        normalized["selectedSeats"] = selected_seats
        normalized["selected_seats"] = selected_seats

    movie_payload = normalized.get("movie")
    if isinstance(movie_payload, dict):
        movie_payload = dict(movie_payload)
        if isinstance(booking_context, dict):
            if not movie_payload.get("movieId") and booking_context.get("movieId"):
                movie_payload["movieId"] = booking_context.get("movieId")
            if not movie_payload.get("cinemaId") and booking_context.get("cinemaId"):
                movie_payload["cinemaId"] = booking_context.get("cinemaId")
            if not movie_payload.get("showDate") and booking_context.get("date"):
                movie_payload["showDate"] = booking_context.get("date")
            if not movie_payload.get("showTime") and booking_context.get("time"):
                movie_payload["showTime"] = booking_context.get("time")
            if not movie_payload.get("hall") and booking_context.get("hall"):
                movie_payload["hall"] = booking_context.get("hall")
        normalized["movie"] = movie_payload

    return normalized


def _default_callback_url(path: str) -> str:
    """Build a default frontend callback URL."""
    return f"{_frontend_base_url().rstrip('/')}{path}"


def _backend_base_url(request: Any) -> str:
    """Build absolute backend origin URL from current request."""
    origin = request.build_absolute_uri("/")
    return str(origin or "").rstrip("/")


def _backend_callback_url(request: Any, callback_path: str) -> str:
    """Build absolute API callback URL for eSewa redirect handling."""
    normalized_path = str(callback_path or "").strip() or "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"{_backend_base_url(request)}{normalized_path}"


def _sanitize_callback_url(value: Any, default_path: str) -> str:
    """Allow only absolute HTTP(S) callback URLs and fallback to configured frontend URL."""
    fallback = _default_callback_url(default_path)
    raw = str(value or "").strip()
    if not raw:
        return fallback
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return fallback

    frontend_parsed = urllib.parse.urlparse(_frontend_base_url())
    if frontend_parsed.netloc and parsed.netloc != frontend_parsed.netloc:
        return fallback

    return raw


def _append_query_param(url: str, key: str, value: str) -> str:
    """Append/replace a query parameter in a URL."""
    parsed = urllib.parse.urlparse(url)
    query_items = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query_items[key] = value
    query_text = urllib.parse.urlencode(query_items)
    return urllib.parse.urlunparse(parsed._replace(query=query_text))


def _build_frontend_callback_redirect(
    *,
    transaction_uuid: str,
    data_value: str,
    is_failure: bool,
) -> str:
    """Build frontend redirect URL for success/failure callback forwarding."""
    pending = _get_pending_transaction(transaction_uuid) if transaction_uuid else None
    default_path = "/payment-failure" if is_failure else "/payment-success"
    fallback = _default_callback_url(default_path)
    target = str(
        (pending or {}).get("failure_url" if is_failure else "success_url")
        or fallback
    ).strip() or fallback

    if data_value:
        target = _append_query_param(target, "data", data_value)
    if transaction_uuid:
        target = _append_query_param(target, "transaction_uuid", transaction_uuid)
    return target


def _find_ticket_by_transaction_uuid(transaction_uuid: str) -> Optional[Ticket]:
    """Return a previously created ticket for the given transaction UUID."""
    if not transaction_uuid:
        return None
    try:
        ticket = (
            Ticket.objects.filter(payload__payment__transaction_uuid=transaction_uuid)
            .order_by("-id")
            .first()
        )
        if ticket:
            return ticket

        payment = (
            Payment.objects.filter(
                payment_method=f"{ESEWA_PAYMENT_METHOD_PREFIX}{transaction_uuid}"[:30],
                payment_status="Success",
            )
            .order_by("-id")
            .first()
        )
        if not payment or not payment.booking_id:
            return None

        return (
            Ticket.objects.filter(payload__booking__booking_id=payment.booking_id)
            .order_by("-id")
            .first()
        )
    except Exception:
        return None


def _build_ticket_response(
    request: Any,
    ticket: Ticket,
    booking_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build API response payload for a confirmed ticket."""
    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    details_url = payload.get("details_url") or request.build_absolute_uri(
        f"/api/ticket/{ticket.reference}/details/"
    )
    qr_image = services._build_qr_image(details_url)
    qr_code_data = services._image_to_data_url(qr_image) if qr_image else None
    ticket_image_data = None
    try:
        ticket_image = services._render_ticket_bundle_image(payload, qr_image)
        ticket_image_data = services._image_to_data_url(ticket_image)
    except Exception:
        ticket_image_data = None

    return {
        "reference": ticket.reference,
        "booking": booking_payload or payload.get("booking"),
        "order": payload.get("order"),
        "ticket": {
            "reference": ticket.reference,
            "booking": booking_payload or payload.get("booking"),
            "qr_code": qr_code_data,
            "ticket_image": ticket_image_data,
            "download_url": request.build_absolute_uri(
                f"/api/ticket/{ticket.reference}/download/"
            ),
            "details_url": details_url,
            "payload": payload,
        },
    }


def _linked_show_for_booking(booking: Optional[Booking]) -> Optional[Show]:
    """Resolve a matching Show row from an existing booking."""
    if not booking or not booking.showtime_id:
        return None
    showtime = booking.showtime
    if not showtime or not showtime.screen_id:
        return None
    return Show.objects.filter(
        vendor_id=showtime.screen.vendor_id,
        movie_id=showtime.movie_id,
        show_date=showtime.start_time.date(),
        start_time=showtime.start_time.time(),
    ).first()


def _release_pending_reserved_seats(order: Optional[dict[str, Any]]) -> None:
    """Release reserved seats for an abandoned checkout attempt."""
    if not isinstance(order, dict):
        return
    context = services._resolve_booking_context(order)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return
    show_date = context.get("show_date")
    show_time = context.get("show_time")
    if (
        not context.get("movie_id")
        or not context.get("cinema_id")
        or not show_date
        or not show_time
    ):
        return

    payload = {
        "movie_id": context["movie_id"],
        "cinema_id": context["cinema_id"],
        "date": show_date.isoformat(),
        "time": show_time.strftime("%H:%M"),
        "selected_seats": selected_seats,
    }
    if context.get("show_id"):
        payload["show_id"] = context["show_id"]
    if context.get("hall"):
        payload["hall"] = context["hall"]

    services.release_booking_seats(SimpleNamespace(data=payload))


class _PendingBookingError(Exception):
    """Internal exception carrying an API payload and status code."""

    def __init__(self, payload: dict[str, Any], status_code: int):
        super().__init__(payload.get("message") or "Pending booking error")
        self.payload = payload
        self.status_code = status_code


def _pending_payment_method(transaction_uuid: str) -> str:
    return f"{ESEWA_PAYMENT_METHOD_PREFIX}{transaction_uuid}"[:30]


def _cancel_pending_booking_for_transaction(
    transaction_uuid: str,
    *,
    keep_booking: bool,
) -> None:
    """Cancel stale pending booking for transaction and release held seats."""
    if not transaction_uuid:
        return

    payment_method = _pending_payment_method(transaction_uuid)
    pending_payments = list(
        Payment.objects.select_related("booking")
        .filter(payment_method=payment_method)
        .order_by("-id")
    )
    seen_booking_ids: set[int] = set()
    for payment in pending_payments:
        booking = payment.booking
        if not booking or booking.id in seen_booking_ids:
            continue
        seen_booking_ids.add(booking.id)

        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().filter(pk=booking.id).first()
            if not locked_booking:
                continue
            if str(locked_booking.booking_status or "").strip().lower() == "cancelled":
                continue

            services._release_booking_seats(locked_booking)
            BookingSeat.objects.filter(booking=locked_booking).delete()

            if keep_booking:
                locked_booking.booking_status = services.BOOKING_STATUS_CANCELLED
                locked_booking.save(update_fields=["booking_status"])
                Payment.objects.filter(booking=locked_booking).update(payment_status="Failed")
            else:
                locked_booking.delete()


def _create_pending_booking_record(
    *,
    order: Optional[dict[str, Any]],
    transaction_uuid: str,
    total_amount: Decimal,
) -> tuple[Optional[Booking], Optional[dict[str, Any]], int]:
    """Create a temporary pending booking so user can see pending payment in history."""
    if not isinstance(order, dict):
        return None, None, status.HTTP_200_OK

    context = services._resolve_booking_context(order)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return None, None, status.HTTP_200_OK

    if not (
        context.get("movie_id")
        and context.get("cinema_id")
        and context.get("show_date")
        and context.get("show_time")
    ):
        return (
            None,
            {
                "message": "Booking context is incomplete. Provide cinema, movie, date, time, and selected seats.",
            },
            status.HTTP_400_BAD_REQUEST,
        )

    show = services._resolve_show_for_context(context)
    if not show:
        return None, {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND

    user = services._resolve_booking_user(context)
    hall = context.get("hall") or show.hall
    now = timezone.now()
    lock_until = now + timedelta(minutes=services.RESERVE_HOLD_MINUTES)

    # If same transaction was retried, drop previous pending copy first.
    _cancel_pending_booking_for_transaction(transaction_uuid, keep_booking=False)

    try:
        with transaction.atomic():
            screen, showtime = services._get_or_create_showtime_for_context(show, hall)
            services._prune_expired_reservations(showtime)

            booking = Booking.objects.create(
                user=user,
                showtime=showtime,
                booking_status=services.BOOKING_STATUS_PENDING,
                total_amount=total_amount,
            )

            for label in selected_seats:
                row_label, seat_number = services._split_seat_label(label)
                if not seat_number:
                    raise _PendingBookingError(
                        {"message": "Invalid seat labels in request.", "invalid_seats": [label]},
                        status.HTTP_400_BAD_REQUEST,
                    )

                seat, _ = Seat.objects.get_or_create(
                    screen=screen,
                    row_label=row_label or None,
                    seat_number=seat_number,
                )
                availability, created = SeatAvailability.objects.select_for_update().get_or_create(
                    seat=seat,
                    showtime=showtime,
                    defaults={"seat_status": services.SEAT_STATUS_AVAILABLE},
                )

                current_status = str(availability.seat_status or "").strip().lower()
                if not created and current_status in services.BOOKED_STATUSES:
                    raise _PendingBookingError(
                        {
                            "message": "Some selected seats are already sold.",
                            "sold_seats": [label],
                        },
                        status.HTTP_409_CONFLICT,
                    )
                if not created and current_status == services.SEAT_STATUS_UNAVAILABLE.lower():
                    raise _PendingBookingError(
                        {
                            "message": "Some selected seats are unavailable.",
                            "unavailable_seats": [label],
                        },
                        status.HTTP_409_CONFLICT,
                    )

                # Keep a short payment hold while checkout is pending.
                availability.seat_status = services.SEAT_STATUS_AVAILABLE
                availability.locked_until = lock_until
                availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

                seat_price, _ = services._resolve_dynamic_seat_price(
                    show=show,
                    showtime=showtime,
                    screen=screen,
                    seat_type=seat.seat_type,
                    event_name=str(
                        coalesce(order, "event", "event_name", "festival", "festival_name") or ""
                    ).strip(),
                )
                BookingSeat.objects.create(
                    booking=booking,
                    showtime=showtime,
                    seat=seat,
                    seat_price=seat_price,
                )

            Payment.objects.create(
                booking=booking,
                payment_method=_pending_payment_method(transaction_uuid),
                payment_status="Pending",
                amount=total_amount,
            )
        return booking, None, status.HTTP_200_OK
    except _PendingBookingError as exc:
        return None, exc.payload, exc.status_code


def _confirm_booking_after_payment(
    request: Any,
    *,
    transaction_uuid: str,
    paid_total_amount: str,
    order: dict[str, Any],
    decoded_payload: dict[str, Any],
    status_check_payload: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    """Create booking/payment/ticket once payment is verified successful."""
    _cancel_pending_booking_for_transaction(transaction_uuid, keep_booking=False)

    booking_payload, booking_error, booking_status = services._create_booking_from_order(order)
    if booking_error:
        return None, booking_error, booking_status

    reference = uuid.uuid4().hex[:10].upper()
    ticket_payload = services._build_ticket_payload(order, reference, request)
    ticket_payload["order"] = order
    if booking_payload:
        ticket_payload["booking"] = booking_payload
    ticket_payload["payment"] = {
        "provider": "ESEWA",
        "transaction_uuid": transaction_uuid,
        "total_amount": paid_total_amount,
        "status": str(
            decoded_payload.get("status") or status_check_payload.get("status") or ""
        ).upper(),
        "status_check": status_check_payload,
        "verified_at": timezone.now().isoformat(),
    }
    ticket = Ticket.objects.create(reference=reference, payload=ticket_payload)

    booking_instance = None
    booking_id = _coerce_int((booking_payload or {}).get("booking_id"))
    if booking_id:
        booking_instance = (
            Booking.objects.select_related("showtime__screen", "showtime__movie")
            .filter(pk=booking_id)
            .first()
        )
    if booking_instance:
        payment_amount = _coerce_decimal(paid_total_amount) or _coerce_decimal(
            booking_instance.total_amount
        ) or Decimal("0")
        payment_method = f"{ESEWA_PAYMENT_METHOD_PREFIX}{transaction_uuid}"[:30]
        if not Payment.objects.filter(
            booking=booking_instance,
            payment_method=payment_method,
            payment_status="Success",
        ).exists():
            Payment.objects.create(
                booking=booking_instance,
                payment_method=payment_method,
                payment_status="Success",
                amount=payment_amount,
            )

        linked_show = _linked_show_for_booking(booking_instance)
        if linked_show:
            try:
                services._notify_payment_success(booking_instance, linked_show)
            except Exception:
                # Keep booking/ticket success response even if notification fails.
                pass

    return _build_ticket_response(request, ticket, booking_payload=booking_payload), None, status.HTTP_200_OK


@api_view(["GET"])
def booking_cinemas(request: Any):
    """Return cinemas for booking dropdowns, optionally filtered by movie."""
    movie_id = _coerce_int(
        coalesce(request.query_params, "movie_id", "movieId", "movie")
    )
    city = coalesce(request.query_params, "city", "location")
    if movie_id:
        vendors = selectors.list_vendors_for_movie(movie_id, city=city)
    else:
        vendors = selectors.list_cinema_vendors(city=city)
    payload = services.build_cinemas_payload(vendors, request)
    return Response({"cinemas": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_movies(request: Any):
    """Return movies for booking dropdowns, optionally filtered by cinema."""
    cinema_id = _coerce_int(
        coalesce(
            request.query_params,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
        )
    )
    city = coalesce(request.query_params, "city", "location")
    if cinema_id:
        movies = selectors.list_movies_for_vendor(cinema_id, city=city)
    else:
        movies = selectors.list_movies_with_shows(city=city)
    payload = [selectors.build_movie_select_payload(movie) for movie in movies]
    return Response({"movies": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_dates(request: Any):
    """Return available show dates for a cinema + movie selection."""
    cinema_id = _coerce_int(
        coalesce(
            request.query_params,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
        )
    )
    movie_id = _coerce_int(
        coalesce(request.query_params, "movie_id", "movieId", "movie")
    )
    city = coalesce(request.query_params, "city", "location")
    if not cinema_id or not movie_id:
        return Response({"dates": []}, status=status.HTTP_200_OK)

    dates = selectors.list_show_dates_for_vendor_movie(cinema_id, movie_id, city=city)
    payload = [date.isoformat() for date in dates if date]
    return Response({"dates": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_times(request: Any):
    """Return available show times for a cinema + movie + date selection."""
    cinema_id = _coerce_int(
        coalesce(
            request.query_params,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
        )
    )
    movie_id = _coerce_int(
        coalesce(request.query_params, "movie_id", "movieId", "movie")
    )
    show_date = parse_date(
        coalesce(request.query_params, "date", "show_date", "showDate")
    )
    city = coalesce(request.query_params, "city", "location")
    if not cinema_id or not movie_id or not show_date:
        return Response({"times": []}, status=status.HTTP_200_OK)

    times = selectors.list_show_times_for_vendor_movie_date(
        cinema_id,
        movie_id,
        show_date,
        city=city,
    )
    payload = [time.strftime("%H:%M") for time in times if time]
    return Response({"times": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_sold_seats(request: Any):
    """Return sold seat labels for a selected show context."""
    query_payload = {
        key: request.query_params.get(key)
        for key in request.query_params.keys()
    }
    payload, status_code = services.list_sold_seats_for_context(query_payload)
    return Response(payload, status=status_code)


@api_view(["GET"])
def booking_available_seats(request: Any):
    """Return available seat entries for a selected show context."""
    query_payload = {
        key: request.query_params.get(key)
        for key in request.query_params.keys()
    }
    payload, status_code = services.list_available_seats_for_context(query_payload)
    return Response(payload, status=status_code)


@api_view(["POST"])
def booking_ticket_price(request: Any):
    """Calculate dynamic ticket prices for selected seats."""
    payload, status_code = services.calculate_dynamic_ticket_price(
        request.data if isinstance(request.data, dict) else {}
    )
    return Response(payload, status=status_code)


@api_view(["POST"])
def booking_apply_coupon(request: Any):
    """Validate and apply a coupon for booking subtotal calculation."""
    payload, status_code = services.apply_coupon_for_booking(
        request.data if isinstance(request.data, dict) else {}
    )
    return Response(payload, status=status_code)


@api_view(["GET"])
def booking_seat_layout(request: Any):
    """Return seat layout + statuses for customer booking page."""
    query_payload = {
        key: request.query_params.get(key)
        for key in request.query_params.keys()
    }
    payload, status_code = services.list_booking_seat_layout(query_payload)
    return Response(payload, status=status_code)


@api_view(["POST"])
def booking_seat_reserve(request: Any):
    """Reserve seats for a short hold during booking."""
    payload, status_code = services.reserve_booking_seats(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
def booking_seat_release(request: Any):
    """Release reserved seats for a booking."""
    payload, status_code = services.release_booking_seats(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@role_required(ROLE_CUSTOMER)
def booking_resume_notification(request: Any):
    """Create/refresh a customer notification to continue a pending booking flow."""
    payload, status_code = services.create_booking_resume_notification(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
def create_payment_qr(request: Any):
    """Create a payment QR code and ticket details."""
    payload, status_code = services.create_payment_qr(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
def esewa_initiate(request: Any):
    """Create eSewa ePay V2 signed payload and store pending order context."""
    payload = request.data if isinstance(request.data, dict) else {}
    order = _normalize_order_payload(payload.get("order")) if payload.get("order") else None

    amount_value = coalesce(payload, "amount")
    if amount_value in (None, "") and isinstance(order, dict):
        amount_value = coalesce(order, "total", "grandTotal", "orderTotal")
    amount = _coerce_decimal(amount_value)
    if amount is None or amount <= 0:
        return Response(
            {"message": "Valid amount is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    tax_amount = Decimal("0")
    product_service_charge = Decimal("0")
    product_delivery_charge = Decimal("0")
    total_amount = amount + tax_amount + product_service_charge + product_delivery_charge
    services.cleanup_expired_pending_bookings()

    transaction_uuid = _build_transaction_uuid()
    total_amount_text = _format_amount(total_amount)
    tax_amount_text = _format_amount(tax_amount)
    service_charge_text = _format_amount(product_service_charge)
    delivery_charge_text = _format_amount(product_delivery_charge)

    # Message format must stay strictly comma-separated with this exact order.
    message = (
        f"total_amount={total_amount_text},"
        f"transaction_uuid={transaction_uuid},"
        f"product_code={_esewa_product_code()}"
    )
    signature = _build_signature(message)

    frontend_success_url = _sanitize_callback_url(payload.get("success_url"), "/payment-success")
    frontend_failure_url = _sanitize_callback_url(payload.get("failure_url"), "/payment-failure")
    frontend_failure_url = _append_query_param(
        frontend_failure_url,
        "transaction_uuid",
        transaction_uuid,
    )

    success_url = _backend_callback_url(request, "/api/payment/esewa/callback/success/")
    failure_url = _backend_callback_url(request, "/api/payment/esewa/callback/failure/")
    failure_url = _append_query_param(failure_url, "transaction_uuid", transaction_uuid)

    pending_booking, pending_error, pending_status = _create_pending_booking_record(
        order=order,
        transaction_uuid=transaction_uuid,
        total_amount=total_amount,
    )
    if pending_error:
        return Response(pending_error, status=pending_status)

    _store_pending_transaction(
        transaction_uuid=transaction_uuid,
        order=order,
        amount_text=total_amount_text,
        success_url=frontend_success_url,
        failure_url=frontend_failure_url,
        booking_id=pending_booking.id if pending_booking else None,
    )

    return Response(
        {
            "amount": _format_amount(amount),
            "tax_amount": tax_amount_text,
            "total_amount": total_amount_text,
            "transaction_uuid": transaction_uuid,
            "product_code": _esewa_product_code(),
            "product_service_charge": service_charge_text,
            "product_delivery_charge": delivery_charge_text,
            "signed_field_names": ESEWA_SIGNED_FIELD_NAMES,
            "signature": signature,
            "message": message,
            "form_url": _esewa_form_url(),
            "success_url": success_url,
            "failure_url": failure_url,
            "frontend_success_url": frontend_success_url,
            "frontend_failure_url": frontend_failure_url,
            "expires_in_seconds": _esewa_pending_ttl_seconds(),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
def esewa_callback_success(request: Any):
    """Receive eSewa success redirect on backend and forward to frontend route."""
    data_value = str(coalesce(request.query_params, "data", default="") or "").strip()
    transaction_uuid = str(
        coalesce(request.query_params, "transaction_uuid", "transactionUuid", default="") or ""
    ).strip()

    if data_value:
        try:
            decoded = _decode_esewa_data(data_value)
            transaction_uuid = str(decoded.get("transaction_uuid") or transaction_uuid).strip()
        except Exception:
            pass

    return redirect(
        _build_frontend_callback_redirect(
            transaction_uuid=transaction_uuid,
            data_value=data_value,
            is_failure=False,
        )
    )


@api_view(["GET"])
def esewa_callback_failure(request: Any):
    """Receive eSewa failure redirect on backend and forward to frontend route."""
    data_value = str(coalesce(request.query_params, "data", default="") or "").strip()
    transaction_uuid = str(
        coalesce(request.query_params, "transaction_uuid", "transactionUuid", default="") or ""
    ).strip()

    if data_value and not transaction_uuid:
        try:
            decoded = _decode_esewa_data(data_value)
            transaction_uuid = str(decoded.get("transaction_uuid") or transaction_uuid).strip()
        except Exception:
            pass

    return redirect(
        _build_frontend_callback_redirect(
            transaction_uuid=transaction_uuid,
            data_value=data_value,
            is_failure=True,
        )
    )


def _esewa_status_check(transaction_uuid: str, total_amount: str) -> dict[str, Any]:
    """Call eSewa transaction status API for post-payment verification."""
    if not transaction_uuid or not total_amount:
        return {}
    query = urllib.parse.urlencode(
        {
            "product_code": _esewa_product_code(),
            "total_amount": total_amount,
            "transaction_uuid": transaction_uuid,
        }
    )
    base_url = _esewa_status_check_url().rstrip("?")
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{query}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@api_view(["POST"])
def esewa_verify(request: Any):
    """Decode + verify eSewa callback and confirm booking only on successful payment."""
    services.cleanup_expired_pending_bookings()

    payload = request.data if isinstance(request.data, dict) else {}
    data_value = str(payload.get("data") or "").strip()
    release_requested = parse_bool(payload.get("release"), default=False)
    transaction_uuid = str(
        coalesce(payload, "transaction_uuid", "transactionUuid", default="")
    ).strip()
    decoded: dict[str, Any] = {}

    if data_value:
        try:
            decoded = _decode_esewa_data(data_value)
        except Exception:
            return Response(
                {"message": "Unable to decode eSewa data."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        transaction_uuid = str(decoded.get("transaction_uuid") or transaction_uuid).strip()

    if not transaction_uuid:
        return Response(
            {"message": "transaction_uuid is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    pending = _get_pending_transaction(transaction_uuid)
    expected_total = str((pending or {}).get("total_amount") or "").strip()

    verified = False
    expected_signature = ""
    signature_message = ""
    if decoded:
        verified, expected_signature, signature_message = _verify_esewa_payload(decoded)

    decoded_status = str(decoded.get("status") or "").upper()
    decoded_total = str(decoded.get("total_amount") or "").strip()
    decoded_product = str(decoded.get("product_code") or "").strip()
    product_code_match = not decoded_product or decoded_product == _esewa_product_code()

    total_amount_for_status = decoded_total or expected_total
    status_check = _esewa_status_check(transaction_uuid, total_amount_for_status)
    status_check_value = str(status_check.get("status") or "").upper()
    status_check_total = str(status_check.get("total_amount") or "").strip()
    status_check_product = str(status_check.get("product_code") or "").strip()
    status_product_match = (
        not status_check_product or status_check_product == _esewa_product_code()
    )
    status_amount_match = True
    if expected_total and status_check_total:
        expected_decimal = _coerce_decimal(expected_total)
        status_decimal = _coerce_decimal(status_check_total)
        status_amount_match = (
            expected_decimal is not None
            and status_decimal is not None
            and expected_decimal == status_decimal
        )

    amount_match = True
    if expected_total and decoded_total:
        expected_decimal = _coerce_decimal(expected_total)
        decoded_decimal = _coerce_decimal(decoded_total)
        amount_match = (
            expected_decimal is not None
            and decoded_decimal is not None
            and expected_decimal == decoded_decimal
        )

    callback_complete = decoded_status == "COMPLETE"
    status_api_complete = (
        status_check_value == "COMPLETE"
        and status_product_match
        and status_amount_match
    )
    is_complete = (
        (callback_complete and verified and product_code_match and amount_match)
        or status_api_complete
    )

    existing_ticket = _find_ticket_by_transaction_uuid(transaction_uuid)
    if existing_ticket:
        ticket_response = _build_ticket_response(request, existing_ticket)
        return Response(
            {
                "verified": bool(verified or status_api_complete),
                "status": decoded_status or status_check_value,
                "is_complete": True,
                "status_check": status_check,
                "status_check_complete": status_api_complete,
                "status_check_product_match": status_product_match,
                "status_check_amount_match": status_amount_match,
                "decoded": decoded,
                "expected_signature": expected_signature,
                "message": "Payment already confirmed.",
                "confirmed": True,
                **ticket_response,
            },
            status=status.HTTP_200_OK,
        )

    if is_complete:
        if not pending or not isinstance(pending.get("order"), dict):
            return Response(
                {
                    "verified": bool(verified or status_api_complete),
                    "status": decoded_status or status_check_value,
                    "is_complete": True,
                    "status_check": status_check,
                    "status_check_complete": status_api_complete,
                    "status_check_product_match": status_product_match,
                    "status_check_amount_match": status_amount_match,
                    "decoded": decoded,
                    "message": "Payment verified but booking context is missing or expired.",
                    "confirmed": False,
                },
                status=status.HTTP_409_CONFLICT,
            )

        paid_total = decoded_total or expected_total
        ticket_response, booking_error, booking_status = _confirm_booking_after_payment(
            request,
            transaction_uuid=transaction_uuid,
            paid_total_amount=paid_total,
            order=pending["order"],
            decoded_payload=decoded,
            status_check_payload=status_check,
        )
        if booking_error:
            return Response(
                {
                    "verified": bool(verified or status_api_complete),
                    "status": decoded_status or status_check_value,
                    "is_complete": True,
                    "status_check": status_check,
                    "status_check_complete": status_api_complete,
                    "status_check_product_match": status_product_match,
                    "status_check_amount_match": status_amount_match,
                    "decoded": decoded,
                    "message": booking_error.get("message")
                    or "Unable to confirm booking after payment.",
                    "confirmed": False,
                    "booking_error": booking_error,
                },
                status=booking_status,
            )

        _clear_pending_transaction(transaction_uuid)
        return Response(
            {
                "verified": bool(verified or status_api_complete),
                "status": decoded_status or status_check_value,
                "is_complete": True,
                "status_check": status_check,
                "status_check_complete": status_api_complete,
                "status_check_product_match": status_product_match,
                "status_check_amount_match": status_amount_match,
                "decoded": decoded,
                "expected_signature": expected_signature,
                "message": "Payment verified and booking confirmed.",
                "confirmed": True,
                **(ticket_response or {}),
            },
            status=status.HTTP_200_OK,
        )

    if release_requested and pending and isinstance(pending.get("order"), dict):
        _cancel_pending_booking_for_transaction(transaction_uuid, keep_booking=True)
        _release_pending_reserved_seats(pending.get("order"))
        _clear_pending_transaction(transaction_uuid)

    response_status = decoded_status or status_check_value or "PENDING"
    return Response(
        {
            "verified": bool(verified),
            "status": response_status,
            "is_complete": False,
            "status_check": status_check,
            "status_check_complete": status_api_complete,
            "status_check_product_match": status_product_match,
            "status_check_amount_match": status_amount_match,
            "decoded": decoded,
            "expected_signature": expected_signature,
            "message": (
                "Payment not completed."
                if not release_requested
                else "Payment not completed. Reserved seats were released."
            ),
            "confirmed": False,
            "pending_order_available": bool(pending and pending.get("order")),
            "signature_message": signature_message,
            "order": pending.get("order") if pending else None,
        },
        status=status.HTTP_200_OK,
    )


def download_ticket(request: Any, reference: str):
    """Download a ticket image by reference."""
    content = services.build_ticket_download(reference)
    if content is None:
        return HttpResponse("Ticket not found", status=404)

    response = HttpResponse(content, content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="ticket-{reference}.png"'
    return response


def ticket_details(request: Any, reference: str):
    """Render ticket details HTML by reference."""
    html = services.build_ticket_details_html(reference)
    if html is None:
        return HttpResponse("Ticket not found", status=404)
    return HttpResponse(html, content_type="text/html")
