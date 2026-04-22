"""Vendor ticket validation and fraud monitoring API views."""

from __future__ import annotations

import csv
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services
from .. import selectors
from ..models import Payment, Show, Ticket, TicketValidationScan, VendorStaff
from ..permissions import resolve_vendor, resolve_vendor_staff, vendor_required
from ..utils import combine_date_time_utc, ensure_utc_datetime, parse_date, parse_time


REFERENCE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{3,19}$")
TICKET_PATH_PATTERN = re.compile(r"/ticket/([^/?#]+)/", re.IGNORECASE)

SCAN_CODE_VALID = "SCAN_VALID"
SCAN_CODE_TICKET_NOT_FOUND = "SCAN_TICKET_NOT_FOUND"
SCAN_CODE_INVALID_TOKEN = "SCAN_INVALID_TOKEN"
SCAN_CODE_EXPIRED_TOKEN = "SCAN_EXPIRED_TOKEN"
SCAN_CODE_ALREADY_USED = "SCAN_ALREADY_USED"
SCAN_CODE_WRONG_VENDOR = "SCAN_WRONG_VENDOR"
SCAN_CODE_OUTSIDE_VALID_TIME_WINDOW = "SCAN_OUTSIDE_VALID_TIME_WINDOW"
SCAN_CODE_PAYMENT_INCOMPLETE = "SCAN_PAYMENT_INCOMPLETE"
SCAN_CODE_LOOKUP_INVALID = "SCAN_LOOKUP_INVALID"
SCAN_CODE_RATE_LIMITED = "SCAN_RATE_LIMITED"
MONITOR_CODE_RATE_LIMITED = "MONITOR_RATE_LIMITED"

RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_SCAN_RATE_LIMIT_STAFF_PER_MINUTE = 60
DEFAULT_SCAN_RATE_LIMIT_IP_PER_MINUTE = 120
DEFAULT_MONITOR_RATE_LIMIT_STAFF_PER_MINUTE = 120
DEFAULT_MONITOR_RATE_LIMIT_IP_PER_MINUTE = 240
VALID_MONITOR_STATUSES = {
    TicketValidationScan.STATUS_VALID,
    TicketValidationScan.STATUS_DUPLICATE,
    TicketValidationScan.STATUS_INVALID,
    TicketValidationScan.STATUS_FRAUD,
}
DEFAULT_INVALID_TOKEN_SPIKE_WINDOW_MINUTES = 10
DEFAULT_INVALID_TOKEN_SPIKE_THRESHOLD = 5
DEFAULT_DUPLICATE_ATTEMPT_WINDOW_MINUTES = 30
DEFAULT_DUPLICATE_ATTEMPT_THRESHOLD = 3
MAX_DUPLICATE_ALERT_OFFENDERS = 5


def _coerce_positive_int(value: Any) -> int | None:
    try:
        number = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _coerce_uuid(value: Any) -> uuid.UUID | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except (TypeError, ValueError, AttributeError):
        return None


def _normalize_reference(value: Any) -> str | None:
    reference = str(value or "").strip().upper()
    if not reference or len(reference) > 20:
        return None
    if not REFERENCE_PATTERN.fullmatch(reference):
        return None
    return reference


def _extract_from_url(scan_data: str) -> tuple[uuid.UUID | None, str | None, str | None, int | None]:
    try:
        parsed = urlparse(scan_data)
    except Exception:
        return None, None, None, None

    path = unquote(str(parsed.path or "")).strip()
    match = TICKET_PATH_PATTERN.search(path)
    if match:
        reference = _normalize_reference(match.group(1))
        if reference:
            return None, None, reference, None

    query = parse_qs(parsed.query or "", keep_blank_values=False)

    token = None
    for key in ("token", "qr_token"):
        values = query.get(key) or []
        if values and str(values[0]).strip():
            token = str(values[0]).strip()
            break

    for key in ("ticket_id", "ticketId", "id"):
        values = query.get(key) or []
        if not values:
            continue
        ticket_uuid = _coerce_uuid(values[0])
        if ticket_uuid:
            return ticket_uuid, token, None, None
        ticket_pk = _coerce_positive_int(values[0])
        if ticket_pk:
            return None, token, None, ticket_pk

    for key in ("reference", "ticket_reference", "ticketRef", "ticket_ref"):
        values = query.get(key) or []
        if not values:
            continue
        reference = _normalize_reference(values[0])
        if reference:
            return None, token, reference, None

    return None, token, None, None


def _extract_lookup_from_scan_data(scan_data: str) -> tuple[uuid.UUID | None, str | None, str | None, int | None]:
    raw = str(scan_data or "").strip()
    if not raw:
        return None, None, None, None

    direct_uuid = _coerce_uuid(raw)
    if direct_uuid:
        return direct_uuid, None, None, None

    direct_reference = _normalize_reference(raw)
    if direct_reference:
        return None, None, direct_reference, None

    direct_pk = _coerce_positive_int(raw)
    if direct_pk:
        return None, None, None, direct_pk

    from_url_uuid, from_url_token, from_url_ref, from_url_pk = _extract_from_url(raw)
    if from_url_uuid or from_url_token or from_url_ref or from_url_pk:
        return from_url_uuid, from_url_token, from_url_ref, from_url_pk

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None

    if isinstance(parsed, dict):
        token = str(parsed.get("token") or parsed.get("qr_token") or "").strip() or None

        for key in ("ticket_id", "ticketId", "id"):
            ticket_uuid = _coerce_uuid(parsed.get(key))
            if ticket_uuid:
                return ticket_uuid, token, None, None
        for key in ("ticket_id", "ticketId", "id"):
            ticket_pk = _coerce_positive_int(parsed.get(key))
            if ticket_pk:
                return None, token, None, ticket_pk

        for key in ("reference", "ticket_reference", "ticketRef", "ticket_ref"):
            reference = _normalize_reference(parsed.get(key))
            if reference:
                return None, token, reference, None

        nested_payload = parsed.get("qr_payload")
        if isinstance(nested_payload, dict):
            nested_uuid = _coerce_uuid(
                nested_payload.get("ticket_id")
                or nested_payload.get("ticketId")
                or nested_payload.get("id")
            )
            nested_token = str(
                nested_payload.get("token")
                or nested_payload.get("qr_token")
                or token
                or ""
            ).strip() or None
            if nested_uuid:
                return nested_uuid, nested_token, None, None
            nested_reference = _normalize_reference(
                nested_payload.get("reference")
                or nested_payload.get("ticket_reference")
            )
            if nested_reference:
                return None, nested_token, nested_reference, None

        details_url = str(parsed.get("details_url") or parsed.get("url") or "").strip()
        if details_url:
            url_uuid, url_token, url_ref, url_pk = _extract_from_url(details_url)
            if url_uuid or url_token or url_ref or url_pk:
                return url_uuid, url_token or token, url_ref, url_pk

    inline_match = TICKET_PATH_PATTERN.search(raw)
    if inline_match:
        reference = _normalize_reference(inline_match.group(1))
        if reference:
            return None, None, reference, None

    return None, None, None, None


def _resolve_scan_lookup(data: Any) -> tuple[dict[str, Any] | None, str | None]:
    ticket_uuid = _coerce_uuid(
        data.get("ticket_id")
        or data.get("ticketId")
        or data.get("id")
    )
    ticket_pk = _coerce_positive_int(
        data.get("ticket_pk")
        or data.get("ticketPk")
        or data.get("pk")
    )
    reference = _normalize_reference(
        data.get("reference")
        or data.get("ticket_reference")
        or data.get("ticketRef")
        or data.get("ticket_ref")
    )
    token = str(data.get("token") or data.get("qr_token") or "").strip() or None

    qr_payload = data.get("qr_payload")
    if isinstance(qr_payload, dict):
        ticket_uuid = ticket_uuid or _coerce_uuid(
            qr_payload.get("ticket_id")
            or qr_payload.get("ticketId")
            or qr_payload.get("id")
        )
        reference = reference or _normalize_reference(
            qr_payload.get("reference")
            or qr_payload.get("ticket_reference")
        )
        token = token or str(qr_payload.get("token") or qr_payload.get("qr_token") or "").strip() or None

    scan_data = str(
        data.get("scan_data")
        or data.get("scanData")
        or data.get("qr")
        or data.get("qr_data")
        or ""
    ).strip()

    extracted_uuid, extracted_token, extracted_reference, extracted_pk = _extract_lookup_from_scan_data(scan_data)
    ticket_uuid = ticket_uuid or extracted_uuid
    reference = reference or extracted_reference
    ticket_pk = ticket_pk or extracted_pk
    token = token or extracted_token

    if not ticket_uuid and not reference and not ticket_pk:
        return None, "Provide ticket id, reference, or QR scan data."

    return {
        "ticket_uuid": ticket_uuid,
        "ticket_pk": ticket_pk,
        "reference": reference,
        "token": token,
        "scan_data": scan_data,
    }, None


def _extract_client_ip(request: Any) -> str | None:
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    remote_addr = str(request.META.get("REMOTE_ADDR") or "").strip()
    return remote_addr or None


def _extract_ticket_vendor_id(ticket: Ticket) -> int | None:
    if ticket.show_id and ticket.show:
        return ticket.show.vendor_id

    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    booking_payload = payload.get("booking") if isinstance(payload.get("booking"), dict) else {}
    movie_payload = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}

    vendor_raw = (
        booking_payload.get("vendor_id")
        or movie_payload.get("cinema_id")
        or movie_payload.get("vendor_id")
        or movie_payload.get("cinemaId")
        or movie_payload.get("vendorId")
    )
    return _coerce_positive_int(vendor_raw)


def _resolve_scan_ticket(scan: TicketValidationScan) -> Ticket | None:
    try:
        ticket = scan.ticket
    except Exception:
        ticket = None

    if ticket:
        return ticket

    reference = str(getattr(scan, "reference", "") or "").strip()
    if not reference:
        return None

    try:
        return selectors.get_ticket(reference)
    except Exception:
        return None


def _resolve_ticket_show_datetime(ticket: Ticket) -> datetime | None:
    if ticket.show_datetime:
        return ensure_utc_datetime(ticket.show_datetime)

    if ticket.show and ticket.show.start_datetime:
        return ensure_utc_datetime(ticket.show.start_datetime)

    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    movie = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}
    show_date = parse_date(movie.get("show_date"))
    show_time = parse_time(movie.get("show_time"))
    if not show_date or not show_time:
        return None
    return combine_date_time_utc(show_date, show_time)


def _is_ticket_paid(ticket: Ticket) -> bool:
    status_value = str(ticket.payment_status or "").strip().upper()
    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    payment_payload = payload.get("payment") if isinstance(payload.get("payment"), dict) else {}
    payload_status = str(payment_payload.get("status") or "").strip().upper()

    # Only PAID is accepted directly. Legacy aliases require an actual successful booking payment.
    if status_value == Ticket.PaymentStatus.PAID or payload_status == Ticket.PaymentStatus.PAID:
        return True

    legacy_paid_aliases = {"SUCCESS", "COMPLETED", "CONFIRMED"}
    if status_value not in legacy_paid_aliases and payload_status not in legacy_paid_aliases:
        return False

    booking_payload = payload.get("booking") if isinstance(payload.get("booking"), dict) else {}
    booking_id = _coerce_positive_int(
        booking_payload.get("booking_id")
        or booking_payload.get("bookingId")
        or booking_payload.get("id")
    )
    if not booking_id:
        return False

    return Payment.objects.filter(
        booking_id=booking_id,
        payment_status__iexact=Payment.Status.SUCCESS,
    ).exists()


def _build_show_label(
    movie_title: str | None,
    show_date: str | None,
    show_time: str | None,
    hall: str | None,
) -> str | None:
    title = str(movie_title or "").strip() or "Unknown movie"
    schedule = " ".join(part for part in [show_date, show_time] if part)
    hall_value = str(hall or "").strip()
    details = schedule
    if hall_value:
        details = f"{schedule} | {hall_value}" if schedule else hall_value
    if not details:
        return title
    return f"{title} | {details}"


def _extract_scan_show_context(scan: TicketValidationScan) -> dict[str, Any]:
    ticket = _resolve_scan_ticket(scan)
    show = ticket.show if ticket and ticket.show_id else None
    payload = ticket.payload if ticket and isinstance(ticket.payload, dict) else {}
    movie_payload = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}

    movie_id = show.movie_id if show else None
    movie_title = ""
    if show and show.movie:
        movie_title = str(show.movie.title or "").strip()
    if not movie_title:
        movie_title = str(movie_payload.get("title") or "").strip()

    show_id = show.id if show else None
    hall = str(show.hall or "").strip() if show else ""
    if not hall:
        hall = str(movie_payload.get("theater") or "").strip()

    show_date = show.show_date.isoformat() if show and show.show_date else None
    if not show_date:
        show_date = str(movie_payload.get("show_date") or "").strip() or None

    show_time = show.start_time.strftime("%H:%M") if show and show.start_time else None
    if not show_time:
        show_time = str(movie_payload.get("show_time") or "").strip() or None

    return {
        "movieId": movie_id,
        "movieTitle": movie_title or None,
        "showId": show_id,
        "showDate": show_date,
        "showTime": show_time,
        "hall": hall or None,
        "showLabel": _build_show_label(movie_title or None, show_date, show_time, hall or None),
    }


def _resolve_scan_actor(scan: TicketValidationScan) -> tuple[str, int | None, str]:
    staff = scan.vendor_staff if isinstance(scan.vendor_staff, VendorStaff) else None
    if staff:
        label = str(staff.full_name or staff.username or staff.email or f"Staff #{staff.id}").strip()
        return "staff", staff.id, label

    actor = scan.scanned_by or scan.vendor
    actor_label = str(getattr(actor, "name", "") or getattr(actor, "username", "") or getattr(actor, "email", "")).strip()
    return "vendor", None, actor_label or "Vendor Account"


def _build_scan_payload(scan: TicketValidationScan) -> dict[str, Any]:
    actor_type, actor_staff_id, actor_name = _resolve_scan_actor(scan)
    show_context = _extract_scan_show_context(scan)
    risk_payload = services.build_fraud_risk_payload(score=int(scan.fraud_score or 0), signals=[])
    ticket = _resolve_scan_ticket(scan)

    return {
        "id": scan.id,
        "reference": scan.reference,
        "ticketReference": ticket.reference if ticket else None,
        "ticketId": str(ticket.ticket_id) if ticket and ticket.ticket_id else None,
        "status": scan.status,
        "reason": scan.reason,
        "fraudScore": int(scan.fraud_score or 0),
        "riskLevel": risk_payload.get("level"),
        "requiresManualReview": bool(risk_payload.get("requires_manual_review")),
        "vendorId": scan.vendor_id,
        "scannedBy": scan.scanned_by_id,
        "scannedByType": actor_type,
        "scannedByStaffId": actor_staff_id,
        "scannedByName": actor_name,
        "movieId": show_context.get("movieId"),
        "movieTitle": show_context.get("movieTitle"),
        "showId": show_context.get("showId"),
        "showDate": show_context.get("showDate"),
        "showTime": show_context.get("showTime"),
        "hall": show_context.get("hall"),
        "showLabel": show_context.get("showLabel"),
        "sourceIp": scan.source_ip,
        "scannedAt": scan.scanned_at.isoformat() if scan.scanned_at else None,
    }


def _build_ticket_success_payload(ticket: Ticket) -> dict[str, Any]:
    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    movie = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}

    return {
        "ticketId": str(ticket.ticket_id),
        "movie": str(movie.get("title") or "").strip() or None,
        "hall": str(movie.get("theater") or "").strip() or None,
        "showTime": str(movie.get("show_time") or "").strip() or None,
        "showDate": str(movie.get("show_date") or "").strip() or None,
        "seat": str(movie.get("seat") or "").strip() or None,
        "customer": str(user.get("name") or "").strip() or None,
    }


def _build_scan_response(
    *,
    message: str,
    code: str,
    alert: str,
    scan_payload: dict[str, Any],
    ticket_payload: dict[str, Any] | None = None,
) -> Response:
    body: dict[str, Any] = {
        "message": message,
        "code": code,
        "alert": alert,
        "scan": scan_payload,
    }
    if ticket_payload is not None:
        body["ticket"] = ticket_payload
    return Response(body, status=status.HTTP_200_OK)


def _scan_assessment(
    event: str,
    *,
    duplicate_attempts: int = 0,
    rate_limit_scope: str = "",
) -> dict[str, Any]:
    return services.assess_scan_fraud_risk(
        event,
        duplicate_attempts=duplicate_attempts,
        rate_limit_scope=rate_limit_scope,
    )


def _extract_scan_reference_hint(data: Any) -> str:
    if not hasattr(data, "get"):
        return "UNKNOWN"

    direct_reference = _normalize_reference(
        data.get("reference")
        or data.get("ticket_reference")
        or data.get("ticketRef")
        or data.get("ticket_ref")
    )
    if direct_reference:
        return direct_reference

    scan_data = str(
        data.get("scan_data")
        or data.get("scanData")
        or data.get("qr")
        or data.get("qr_data")
        or ""
    ).strip()
    if scan_data:
        _, _, extracted_reference, _ = _extract_lookup_from_scan_data(scan_data)
        if extracted_reference:
            return extracted_reference

    return "UNKNOWN"


def _best_effort_log_scan_attempt(
    *,
    vendor: Any,
    vendor_staff: Any,
    reference: str,
    status_value: str,
    reason: str,
    fraud_score: int,
    source_ip: str | None,
    user_agent: str | None,
    ticket: Ticket | None = None,
) -> TicketValidationScan | None:
    try:
        return TicketValidationScan.objects.create(
            reference=str(reference or "UNKNOWN")[:20],
            ticket=ticket,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
            status=status_value,
            reason=str(reason or "")[:255] or None,
            fraud_score=max(0, min(int(fraud_score), 100)),
            source_ip=source_ip,
            user_agent=user_agent,
        )
    except Exception:
        return None


def _read_non_negative_int_setting(name: str, default: int) -> int:
    raw = getattr(settings, name, default)
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(parsed, 0)


def _rate_limit_increment(key: str, *, timeout_seconds: int) -> int:
    if cache.add(key, 1, timeout=timeout_seconds):
        return 1
    try:
        return int(cache.incr(key))
    except (ValueError, TypeError):
        cache.set(key, 1, timeout=timeout_seconds)
        return 1


def _build_rate_limited_response(*, endpoint: str, scope: str) -> Response:
    is_scan = endpoint == "scan"
    return Response(
        {
            "message": (
                "Too many ticket scan requests. Please retry shortly."
                if is_scan
                else "Too many ticket validation monitor requests. Please retry shortly."
            ),
            "code": SCAN_CODE_RATE_LIMITED if is_scan else MONITOR_CODE_RATE_LIMITED,
            "alert": "rate_limited",
            "scope": scope,
            "retryAfterSeconds": RATE_LIMIT_WINDOW_SECONDS,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )


def _resolve_actor_rate_limit_key(vendor_id: int, vendor_staff: Any) -> tuple[str, str]:
    if vendor_staff and getattr(vendor_staff, "id", None):
        return f"staff:{vendor_staff.id}", "vendor_staff"
    return f"vendor:{vendor_id}", "vendor_account"


def _enforce_ticket_validation_rate_limits(
    *,
    request: Any,
    vendor: Any,
    vendor_staff: Any,
    endpoint: str,
) -> Response | None:
    actor_identity, actor_scope = _resolve_actor_rate_limit_key(vendor.id, vendor_staff)
    source_ip = _extract_client_ip(request) or "unknown"
    bucket = int(time.time() // RATE_LIMIT_WINDOW_SECONDS)

    if endpoint == "scan":
        actor_limit = _read_non_negative_int_setting(
            "TICKET_VALIDATION_SCAN_RATE_LIMIT_STAFF_PER_MINUTE",
            DEFAULT_SCAN_RATE_LIMIT_STAFF_PER_MINUTE,
        )
        ip_limit = _read_non_negative_int_setting(
            "TICKET_VALIDATION_SCAN_RATE_LIMIT_IP_PER_MINUTE",
            DEFAULT_SCAN_RATE_LIMIT_IP_PER_MINUTE,
        )
    else:
        actor_limit = _read_non_negative_int_setting(
            "TICKET_VALIDATION_MONITOR_RATE_LIMIT_STAFF_PER_MINUTE",
            DEFAULT_MONITOR_RATE_LIMIT_STAFF_PER_MINUTE,
        )
        ip_limit = _read_non_negative_int_setting(
            "TICKET_VALIDATION_MONITOR_RATE_LIMIT_IP_PER_MINUTE",
            DEFAULT_MONITOR_RATE_LIMIT_IP_PER_MINUTE,
        )

    if actor_limit > 0:
        actor_key = f"rate-limit:ticket-validation:{endpoint}:actor:{actor_identity}:{bucket}"
        actor_count = _rate_limit_increment(actor_key, timeout_seconds=RATE_LIMIT_WINDOW_SECONDS)
        if actor_count > actor_limit:
            return _build_rate_limited_response(endpoint=endpoint, scope=actor_scope)

    if ip_limit > 0:
        ip_key = f"rate-limit:ticket-validation:{endpoint}:ip:{source_ip}:{bucket}"
        ip_count = _rate_limit_increment(ip_key, timeout_seconds=RATE_LIMIT_WINDOW_SECONDS)
        if ip_count > ip_limit:
            return _build_rate_limited_response(endpoint=endpoint, scope="vendor_ip")

    return None


def _ticket_lookup_query(lookup: dict[str, Any]) -> Ticket | None:
    ticket_uuid = lookup.get("ticket_uuid")
    ticket_pk = lookup.get("ticket_pk")
    reference = lookup.get("reference")
    token = str(lookup.get("token") or "").strip()

    if ticket_uuid:
        try:
            ticket = Ticket.objects.select_related("show").filter(ticket_id=ticket_uuid).first()
        except (TypeError, ValueError, ValidationError):
            ticket = None
        if ticket:
            return ticket

    if ticket_pk:
        ticket = Ticket.objects.select_related("show").filter(pk=ticket_pk).first()
        if ticket:
            return ticket

    if reference:
        return selectors.get_ticket(reference)

    if token:
        try:
            decoded_token = signing.loads(token, salt=services.TICKET_QR_SIGNING_SALT)
        except Exception:
            decoded_token = None
        if isinstance(decoded_token, dict):
            decoded_reference = _normalize_reference(decoded_token.get("reference"))
            if decoded_reference:
                return selectors.get_ticket(decoded_reference)

    return None


@api_view(["POST"])
@vendor_required
def validate_ticket_scan(request: Any):
    """Validate one ticket scan and log fraud/duplicate state."""
    vendor = resolve_vendor(request)
    vendor_staff = resolve_vendor_staff(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    source_ip = _extract_client_ip(request)
    user_agent = str(request.META.get("HTTP_USER_AGENT") or "").strip()[:255] or None
    attempt_reference = _extract_scan_reference_hint(request.data)

    rate_limited = _enforce_ticket_validation_rate_limits(
        request=request,
        vendor=vendor,
        vendor_staff=vendor_staff,
        endpoint="scan",
    )
    if rate_limited is not None:
        scope = "vendor_rate_limit"
        if isinstance(rate_limited.data, dict):
            scope = str(rate_limited.data.get("scope") or scope)
        rate_limit_assessment = _scan_assessment(
            services.SCAN_FRAUD_EVENT_RATE_LIMITED,
            rate_limit_scope=scope,
        )
        rate_limited_scan = _best_effort_log_scan_attempt(
            vendor=vendor,
            vendor_staff=vendor_staff,
            reference=attempt_reference,
            status_value=TicketValidationScan.STATUS_INVALID,
            reason=f"Rate limit exceeded ({scope}).",
            fraud_score=int(rate_limit_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        if rate_limited_scan and isinstance(rate_limited.data, dict):
            rate_limited.data = {
                **rate_limited.data,
                "scan": _build_scan_payload(rate_limited_scan),
            }
        return rate_limited

    lookup, lookup_error = _resolve_scan_lookup(request.data)
    if lookup_error:
        invalid_request_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_INVALID_REQUEST)
        invalid_request_scan = _best_effort_log_scan_attempt(
            vendor=vendor,
            vendor_staff=vendor_staff,
            reference=attempt_reference,
            status_value=TicketValidationScan.STATUS_INVALID,
            reason=f"Invalid scan request: {lookup_error}",
            fraud_score=int(invalid_request_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        response_payload: dict[str, Any] = {
            "message": lookup_error,
            "code": SCAN_CODE_LOOKUP_INVALID,
            "alert": "invalid_request",
        }
        if invalid_request_scan:
            response_payload["scan"] = _build_scan_payload(invalid_request_scan)
        return Response(response_payload, status=status.HTTP_400_BAD_REQUEST)

    ticket = _ticket_lookup_query(lookup)
    reference = lookup.get("reference") or (str(ticket.reference or "").strip().upper() if ticket else "")
    actor_type = "staff" if vendor_staff else "vendor"
    actor_staff_id = vendor_staff.id if vendor_staff else None

    if not ticket:
        not_found_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_TICKET_NOT_FOUND)
        scan = TicketValidationScan.objects.create(
            reference=reference or "UNKNOWN",
            ticket=None,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
            status=TicketValidationScan.STATUS_INVALID,
            reason="Ticket not found.",
            fraud_score=int(not_found_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        scan_payload = _build_scan_payload(scan)
        scan_payload.update(
            {
                "duplicateCount": 0,
                "totalScansForTicket": 0,
                "scannedByType": actor_type,
                "scannedByStaffId": actor_staff_id,
            }
        )
        return _build_scan_response(
            message="Ticket not found.",
            code=SCAN_CODE_TICKET_NOT_FOUND,
            alert="fraud_suspected",
            scan_payload=scan_payload,
        )

    if not reference:
        reference = str(ticket.reference or "").strip().upper() or str(ticket.ticket_id)

    ticket_vendor_id = _extract_ticket_vendor_id(ticket)
    if str(ticket_vendor_id or "") != str(vendor.id):
        wrong_vendor_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_WRONG_VENDOR)
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=ticket,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
            status=TicketValidationScan.STATUS_FRAUD,
            reason="Ticket does not belong to this vendor.",
            fraud_score=int(wrong_vendor_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        prior_total_scans = TicketValidationScan.objects.filter(ticket=ticket, vendor=vendor).count()
        scan_payload = _build_scan_payload(scan)
        scan_payload.update(
            {
                "duplicateCount": 0,
                "totalScansForTicket": prior_total_scans,
                "scannedByType": actor_type,
                "scannedByStaffId": actor_staff_id,
            }
        )
        return _build_scan_response(
            message="Fraud alert: ticket belongs to another vendor.",
            code=SCAN_CODE_WRONG_VENDOR,
            alert="fraud_suspected",
            scan_payload=scan_payload,
        )

    now = timezone.now()
    token = lookup.get("token")
    if lookup.get("ticket_uuid") and not token:
        missing_token_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_MISSING_QR_TOKEN)
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=ticket,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
            status=TicketValidationScan.STATUS_INVALID,
            reason="Missing QR token.",
            fraud_score=int(missing_token_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        prior_total_scans = TicketValidationScan.objects.filter(ticket=ticket, vendor=vendor).count()
        scan_payload = _build_scan_payload(scan)
        scan_payload.update(
            {
                "duplicateCount": 0,
                "totalScansForTicket": prior_total_scans,
                "scannedByType": actor_type,
                "scannedByStaffId": actor_staff_id,
            }
        )
        return _build_scan_response(
            message="Invalid QR code.",
            code=SCAN_CODE_INVALID_TOKEN,
            alert="fraud_suspected",
            scan_payload=scan_payload,
        )

    if token:
        token_ok, token_error = services.verify_ticket_qr_token(ticket, token, now=now)
        if not token_ok:
            reason = "Invalid QR code." if token_error in {"invalid", "missing"} else "QR token expired."
            outcome_code = (
                SCAN_CODE_INVALID_TOKEN
                if token_error in {"invalid", "missing"}
                else SCAN_CODE_EXPIRED_TOKEN
            )
            token_assessment = _scan_assessment(
                services.SCAN_FRAUD_EVENT_INVALID_QR_TOKEN
                if token_error in {"invalid", "missing"}
                else services.SCAN_FRAUD_EVENT_EXPIRED_QR_TOKEN
            )
            scan = TicketValidationScan.objects.create(
                reference=reference,
                ticket=ticket,
                booking=None,
                vendor=vendor,
                scanned_by=vendor,
                vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
                status=TicketValidationScan.STATUS_INVALID,
                reason=reason,
                fraud_score=int(token_assessment.get("score") or 0),
                source_ip=source_ip,
                user_agent=user_agent,
            )
            prior_total_scans = TicketValidationScan.objects.filter(ticket=ticket, vendor=vendor).count()
            scan_payload = _build_scan_payload(scan)
            scan_payload.update(
                {
                    "duplicateCount": 0,
                    "totalScansForTicket": prior_total_scans,
                    "scannedByType": actor_type,
                    "scannedByStaffId": actor_staff_id,
                }
            )
            return _build_scan_response(
                message=reason,
                code=outcome_code,
                alert="fraud_suspected",
                scan_payload=scan_payload,
            )

    if not _is_ticket_paid(ticket):
        payment_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_PAYMENT_INCOMPLETE)
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=ticket,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
            status=TicketValidationScan.STATUS_INVALID,
            reason="Payment incomplete.",
            fraud_score=int(payment_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        prior_total_scans = TicketValidationScan.objects.filter(ticket=ticket, vendor=vendor).count()
        scan_payload = _build_scan_payload(scan)
        scan_payload.update(
            {
                "duplicateCount": 0,
                "totalScansForTicket": prior_total_scans,
                "scannedByType": actor_type,
                "scannedByStaffId": actor_staff_id,
            }
        )
        return _build_scan_response(
            message="Payment incomplete.",
            code=SCAN_CODE_PAYMENT_INCOMPLETE,
            alert="fraud_suspected",
            scan_payload=scan_payload,
        )

    show_datetime = _resolve_ticket_show_datetime(ticket)
    window_start, window_end = services.compute_ticket_validation_window(show_datetime)
    if window_start and window_end and not (window_start <= now <= window_end):
        reason = "Ticket expired." if now > window_end else "Ticket is not valid yet."
        outside_window_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_OUTSIDE_VALID_TIME_WINDOW)
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=ticket,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
            status=TicketValidationScan.STATUS_INVALID,
            reason=reason,
            fraud_score=int(outside_window_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        prior_total_scans = TicketValidationScan.objects.filter(ticket=ticket, vendor=vendor).count()
        scan_payload = _build_scan_payload(scan)
        scan_payload.update(
            {
                "duplicateCount": 0,
                "totalScansForTicket": prior_total_scans,
                "scannedByType": actor_type,
                "scannedByStaffId": actor_staff_id,
            }
        )
        return _build_scan_response(
            message=reason,
            code=SCAN_CODE_OUTSIDE_VALID_TIME_WINDOW,
            alert="fraud_suspected",
            scan_payload=scan_payload,
        )

    with transaction.atomic():
        # Lock ticket row so concurrent scans cannot both mark one ticket as valid.
        locked_ticket = (
            Ticket.objects.select_for_update()
            .select_related("show")
            .filter(pk=ticket.pk)
            .first()
        )

        if not locked_ticket:
            missing_locked_ticket_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_TICKET_NOT_FOUND)
            scan = TicketValidationScan.objects.create(
                reference=reference or "UNKNOWN",
                ticket=None,
                booking=None,
                vendor=vendor,
                scanned_by=vendor,
                vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
                status=TicketValidationScan.STATUS_INVALID,
                reason="Ticket not found.",
                fraud_score=int(missing_locked_ticket_assessment.get("score") or 0),
                source_ip=source_ip,
                user_agent=user_agent,
            )
            scan_payload = _build_scan_payload(scan)
            scan_payload.update(
                {
                    "duplicateCount": 0,
                    "totalScansForTicket": 0,
                    "scannedByType": actor_type,
                    "scannedByStaffId": actor_staff_id,
                }
            )
            return _build_scan_response(
                message="Ticket not found.",
                code=SCAN_CODE_TICKET_NOT_FOUND,
                alert="fraud_suspected",
                scan_payload=scan_payload,
            )

        prior_scans = TicketValidationScan.objects.filter(
            ticket=locked_ticket,
            vendor=vendor,
            status__in=[TicketValidationScan.STATUS_VALID, TicketValidationScan.STATUS_DUPLICATE],
        ).count()
        prior_total_scans = TicketValidationScan.objects.filter(ticket=locked_ticket, vendor=vendor).count()
        total_scans_for_ticket = prior_total_scans + 1

        if locked_ticket.is_used or prior_scans > 0:
            duplicate_assessment = _scan_assessment(
                services.SCAN_FRAUD_EVENT_DUPLICATE_TICKET,
                duplicate_attempts=prior_scans,
            )
            scan = TicketValidationScan.objects.create(
                reference=reference,
                ticket=locked_ticket,
                booking=None,
                vendor=vendor,
                scanned_by=vendor,
                vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
                status=TicketValidationScan.STATUS_DUPLICATE,
                reason="Ticket already used.",
                fraud_score=int(duplicate_assessment.get("score") or 0),
                source_ip=source_ip,
                user_agent=user_agent,
            )
            scan_payload = _build_scan_payload(scan)
            scan_payload.update(
                {
                    "duplicateCount": prior_scans,
                    "totalScansForTicket": total_scans_for_ticket,
                    "scannedByType": actor_type,
                    "scannedByStaffId": actor_staff_id,
                }
            )
            return _build_scan_response(
                message="Ticket already used.",
                code=SCAN_CODE_ALREADY_USED,
                alert="duplicate_ticket",
                scan_payload=scan_payload,
            )

        locked_ticket.is_used = True
        locked_ticket.save(update_fields=["is_used"])

        valid_assessment = _scan_assessment(services.SCAN_FRAUD_EVENT_VALID)
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=locked_ticket,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            vendor_staff=vendor_staff if isinstance(vendor_staff, VendorStaff) else None,
            status=TicketValidationScan.STATUS_VALID,
            reason="Ticket is valid.",
            fraud_score=int(valid_assessment.get("score") or 0),
            source_ip=source_ip,
            user_agent=user_agent,
        )

        scan_payload = _build_scan_payload(scan)
        scan_payload.update(
            {
                "duplicateCount": 0,
                "totalScansForTicket": total_scans_for_ticket,
                "scannedByType": actor_type,
                "scannedByStaffId": actor_staff_id,
            }
        )

        ticket_payload = _build_ticket_success_payload(locked_ticket)

    return _build_scan_response(
        message="Ticket validated successfully.",
        code=SCAN_CODE_VALID,
        alert="none",
        scan_payload=scan_payload,
        ticket_payload=ticket_payload,
    )


def _normalize_monitor_status(value: Any) -> str:
    candidate = str(value or "").strip().upper()
    return candidate if candidate in VALID_MONITOR_STATUSES else ""


def _parse_staff_filter(value: Any) -> tuple[str, int | None, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", None, ""

    lowered = raw.lower()
    if lowered in {"owner", "vendor", "vendor_account"}:
        return "owner", None, "owner"

    staff_id = _coerce_positive_int(raw)
    if staff_id:
        return "staff", staff_id, str(staff_id)

    return "", None, ""


def _parse_monitor_filters(request: Any) -> dict[str, Any]:
    query = request.query_params
    status_filter = _normalize_monitor_status(query.get("status"))
    reference = str(query.get("reference") or "").strip().upper()
    scan_date = parse_date(query.get("date"))
    staff_mode, staff_id, staff_value = _parse_staff_filter(query.get("staff") or query.get("staff_id"))
    movie_id = _coerce_positive_int(query.get("movie") or query.get("movie_id"))
    show_id = _coerce_positive_int(query.get("show") or query.get("show_id"))

    try:
        limit = int(query.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    return {
        "status": status_filter,
        "reference": reference,
        "date": scan_date,
        "staffMode": staff_mode,
        "staffId": staff_id,
        "staff": staff_value,
        "movieId": movie_id,
        "showId": show_id,
        "limit": limit,
    }


def _base_monitor_queryset(vendor: Any):
    return TicketValidationScan.objects.filter(vendor=vendor).select_related(
        "vendor_staff",
        "vendor",
        "scanned_by",
    )


def _apply_monitor_filters(queryset: Any, *, filters: dict[str, Any]):
    if filters.get("status"):
        queryset = queryset.filter(status=filters["status"])
    if filters.get("reference"):
        queryset = queryset.filter(reference__icontains=filters["reference"])
    if filters.get("date"):
        queryset = queryset.filter(scanned_at__date=filters["date"])

    if filters.get("staffMode") == "owner":
        queryset = queryset.filter(vendor_staff__isnull=True)
    elif filters.get("staffMode") == "staff" and filters.get("staffId"):
        queryset = queryset.filter(vendor_staff_id=filters["staffId"])

    if filters.get("movieId"):
        queryset = queryset.filter(ticket__show__movie_id=filters["movieId"])
    if filters.get("showId"):
        queryset = queryset.filter(ticket__show_id=filters["showId"])

    return queryset


def _build_monitor_summary(queryset: Any) -> dict[str, Any]:
    counts = queryset.values("status").annotate(total=Count("id"))
    score_stats = queryset.aggregate(avg_score=Avg("fraud_score"), max_score=Max("fraud_score"))
    review_threshold = services.scan_fraud_review_threshold()
    summary = {
        "valid": 0,
        "duplicate": 0,
        "invalid": 0,
        "fraud": 0,
        "total": 0,
        "uniqueTickets": 0,
        "duplicateRate": 0.0,
        "riskRate": 0.0,
        "averageFraudScore": round(float(score_stats.get("avg_score") or 0), 2),
        "maxFraudScore": int(score_stats.get("max_score") or 0),
        "highRiskScans": queryset.filter(fraud_score__gte=review_threshold).count(),
        "criticalRiskScans": queryset.filter(fraud_score__gte=90).count(),
        "reviewThreshold": review_threshold,
    }

    for row in counts:
        status_value = str(row.get("status") or "")
        total = int(row.get("total") or 0)
        summary["total"] += total
        if status_value == TicketValidationScan.STATUS_VALID:
            summary["valid"] = total
        elif status_value == TicketValidationScan.STATUS_DUPLICATE:
            summary["duplicate"] = total
        elif status_value == TicketValidationScan.STATUS_INVALID:
            summary["invalid"] = total
        elif status_value == TicketValidationScan.STATUS_FRAUD:
            summary["fraud"] = total

    summary["uniqueTickets"] = queryset.filter(ticket__isnull=False).values("ticket_id").distinct().count()
    if summary["total"] > 0:
        summary["duplicateRate"] = round((summary["duplicate"] / summary["total"]) * 100, 2)
        summary["riskRate"] = round(((summary["fraud"] + summary["invalid"]) / summary["total"]) * 100, 2)

    return summary


def _build_monitor_realtime_metrics(base_queryset: Any) -> dict[str, Any]:
    now_local = timezone.localtime(timezone.now())
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    today_queryset = base_queryset.filter(scanned_at__gte=day_start, scanned_at__lt=day_end)
    today_total = today_queryset.count()
    today_valid = today_queryset.filter(status=TicketValidationScan.STATUS_VALID).count()
    today_duplicate = today_queryset.filter(status=TicketValidationScan.STATUS_DUPLICATE).count()
    today_failed = today_queryset.filter(
        status__in=[
            TicketValidationScan.STATUS_INVALID,
            TicketValidationScan.STATUS_FRAUD,
        ]
    ).count()

    hourly_trend = [
        {
            "hour": f"{hour:02d}:00",
            "total": 0,
            "failed": 0,
        }
        for hour in range(24)
    ]

    for scanned_at, status_value in today_queryset.values_list("scanned_at", "status"):
        if not scanned_at:
            continue

        try:
            local_scanned_at = timezone.localtime(scanned_at)
            hour_index = int(local_scanned_at.hour)
        except Exception:
            hour_index = int(getattr(scanned_at, "hour", 0) or 0)

        if hour_index < 0 or hour_index > 23:
            continue

        hourly_trend[hour_index]["total"] += 1
        if status_value in {TicketValidationScan.STATUS_INVALID, TicketValidationScan.STATUS_FRAUD}:
            hourly_trend[hour_index]["failed"] += 1

    failed_rate = 0.0
    if today_total > 0:
        failed_rate = round((today_failed / today_total) * 100, 2)

    return {
        "todayScans": today_total,
        "todayFailedScans": today_failed,
        "todayValidScans": today_valid,
        "todayDuplicateScans": today_duplicate,
        "todayFailedRate": failed_rate,
        "hourlyScanTrend": hourly_trend,
        "updatedAt": timezone.now().isoformat(),
    }


def _read_positive_int_setting(name: str, default: int, *, minimum: int = 1) -> int:
    value = _read_non_negative_int_setting(name, default)
    return max(minimum, value)


def _build_monitor_suspicious_alerts(base_queryset: Any) -> list[dict[str, Any]]:
    now = timezone.now()

    invalid_window_minutes = _read_positive_int_setting(
        "TICKET_VALIDATION_ALERT_INVALID_TOKEN_WINDOW_MINUTES",
        DEFAULT_INVALID_TOKEN_SPIKE_WINDOW_MINUTES,
    )
    invalid_threshold = _read_positive_int_setting(
        "TICKET_VALIDATION_ALERT_INVALID_TOKEN_SPIKE_THRESHOLD",
        DEFAULT_INVALID_TOKEN_SPIKE_THRESHOLD,
    )
    invalid_window_start = now - timedelta(minutes=invalid_window_minutes)
    invalid_prev_window_start = invalid_window_start - timedelta(minutes=invalid_window_minutes)

    invalid_token_queryset = base_queryset.filter(
        status=TicketValidationScan.STATUS_INVALID,
    ).filter(
        Q(reason__icontains="invalid qr")
        | Q(reason__icontains="missing qr token")
        | Q(reason__icontains="qr token expired")
    )
    invalid_recent_count = invalid_token_queryset.filter(
        scanned_at__gte=invalid_window_start,
        scanned_at__lt=now,
    ).count()
    invalid_previous_count = invalid_token_queryset.filter(
        scanned_at__gte=invalid_prev_window_start,
        scanned_at__lt=invalid_window_start,
    ).count()
    invalid_delta = invalid_recent_count - invalid_previous_count
    invalid_spike_delta_threshold = max(2, invalid_threshold // 2)
    invalid_spike_triggered = (
        invalid_recent_count >= invalid_threshold
        and invalid_delta >= invalid_spike_delta_threshold
    )
    invalid_severity = "danger" if invalid_spike_triggered else ("warning" if invalid_recent_count > 0 else "info")
    if invalid_spike_triggered:
        invalid_message = (
            f"Invalid-token scans spiked to {invalid_recent_count} in the last "
            f"{invalid_window_minutes} minutes (previous window: {invalid_previous_count})."
        )
    elif invalid_recent_count > 0:
        invalid_message = (
            f"{invalid_recent_count} invalid-token scans were recorded in the last "
            f"{invalid_window_minutes} minutes."
        )
    else:
        invalid_message = f"No invalid-token activity detected in the last {invalid_window_minutes} minutes."

    duplicate_window_minutes = _read_positive_int_setting(
        "TICKET_VALIDATION_ALERT_DUPLICATE_WINDOW_MINUTES",
        DEFAULT_DUPLICATE_ATTEMPT_WINDOW_MINUTES,
    )
    duplicate_threshold = _read_positive_int_setting(
        "TICKET_VALIDATION_ALERT_DUPLICATE_ATTEMPT_THRESHOLD",
        DEFAULT_DUPLICATE_ATTEMPT_THRESHOLD,
        minimum=2,
    )
    duplicate_window_start = now - timedelta(minutes=duplicate_window_minutes)
    duplicate_recent_queryset = base_queryset.filter(
        status=TicketValidationScan.STATUS_DUPLICATE,
        scanned_at__gte=duplicate_window_start,
        scanned_at__lt=now,
    )
    duplicate_total_in_window = duplicate_recent_queryset.count()
    duplicate_offender_rows = list(
        duplicate_recent_queryset.values("ticket_id", "reference")
        .annotate(duplicateAttempts=Count("id"))
        .filter(duplicateAttempts__gte=duplicate_threshold)
        .order_by("-duplicateAttempts", "reference")[:MAX_DUPLICATE_ALERT_OFFENDERS]
    )
    duplicate_offenders = [
        {
            "ticketId": row.get("ticket_id"),
            "reference": str(row.get("reference") or "").strip() or "UNKNOWN",
            "duplicateAttempts": int(row.get("duplicateAttempts") or 0),
        }
        for row in duplicate_offender_rows
    ]
    repeated_duplicate_attempts = sum(item["duplicateAttempts"] for item in duplicate_offenders)
    repeated_duplicate_triggered = bool(duplicate_offenders)
    duplicate_severity = "danger" if repeated_duplicate_triggered else ("warning" if duplicate_total_in_window > 0 else "info")
    if repeated_duplicate_triggered:
        duplicate_message = (
            f"{len(duplicate_offenders)} tickets crossed the repeated duplicate threshold "
            f"in the last {duplicate_window_minutes} minutes."
        )
    elif duplicate_total_in_window > 0:
        duplicate_message = (
            f"{duplicate_total_in_window} duplicate scans detected in the last {duplicate_window_minutes} minutes, "
            "but none crossed the repeated-attempt threshold."
        )
    else:
        duplicate_message = f"No duplicate scan activity detected in the last {duplicate_window_minutes} minutes."

    return [
        {
            "type": "invalid_token_spike",
            "title": "Invalid Token Spike",
            "count": invalid_recent_count,
            "windowMinutes": invalid_window_minutes,
            "threshold": invalid_threshold,
            "previousWindowCount": invalid_previous_count,
            "delta": invalid_delta,
            "isTriggered": invalid_spike_triggered,
            "severity": invalid_severity,
            "message": invalid_message,
        },
        {
            "type": "repeated_duplicate_attempts",
            "title": "Repeated Duplicate Attempts",
            "count": repeated_duplicate_attempts if repeated_duplicate_triggered else duplicate_total_in_window,
            "totalInWindow": duplicate_total_in_window,
            "repeatedTicketCount": len(duplicate_offenders),
            "windowMinutes": duplicate_window_minutes,
            "threshold": duplicate_threshold,
            "isTriggered": repeated_duplicate_triggered,
            "severity": duplicate_severity,
            "message": duplicate_message,
            "offenders": duplicate_offenders,
        },
    ]


def _build_monitor_filter_options(vendor: Any) -> dict[str, Any]:
    staff_options = [{"value": "owner", "label": "Vendor Account"}]
    for staff in VendorStaff.objects.filter(vendor_id=vendor.id).order_by("full_name", "id"):
        suffix = "" if staff.is_active else " (inactive)"
        staff_options.append(
            {
                "value": str(staff.id),
                "label": f"{str(staff.full_name or staff.email or f'Staff #{staff.id}').strip()}{suffix}",
            }
        )

    movie_options_by_id: dict[int, dict[str, Any]] = {}
    show_options: list[dict[str, Any]] = []
    shows = (
        Show.objects.filter(vendor_id=vendor.id)
        .select_related("movie")
        .order_by("-show_date", "-start_time", "-id")[:300]
    )
    for show in shows:
        movie_title = str(show.movie.title if show.movie else "").strip() or f"Movie #{show.movie_id}"
        movie_options_by_id[show.movie_id] = {
            "value": str(show.movie_id),
            "label": movie_title,
        }
        show_date = show.show_date.isoformat() if show.show_date else None
        show_time = show.start_time.strftime("%H:%M") if show.start_time else None
        show_label = _build_show_label(movie_title, show_date, show_time, show.hall)
        show_options.append(
            {
                "value": str(show.id),
                "label": show_label or f"Show #{show.id}",
            }
        )

    movie_options = sorted(movie_options_by_id.values(), key=lambda item: str(item.get("label") or "").lower())
    status_options = [
        {"value": TicketValidationScan.STATUS_VALID, "label": "VALID"},
        {"value": TicketValidationScan.STATUS_DUPLICATE, "label": "DUPLICATE"},
        {"value": TicketValidationScan.STATUS_INVALID, "label": "INVALID"},
        {"value": TicketValidationScan.STATUS_FRAUD, "label": "FRAUD"},
    ]
    return {
        "staff": staff_options,
        "movies": movie_options,
        "shows": show_options,
        "statuses": status_options,
    }


def _build_monitor_applied_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": filters["date"].isoformat() if filters.get("date") else "",
        "staff": filters.get("staff") or "",
        "status": filters.get("status") or "",
        "movie": str(filters.get("movieId") or ""),
        "show": str(filters.get("showId") or ""),
        "reference": filters.get("reference") or "",
    }


def _build_monitor_csv_response(scans: list[TicketValidationScan]) -> HttpResponse:
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="ticket_validation_monitor_{timestamp}.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "scan_id",
            "reference",
            "ticket_id",
            "status",
            "fraud_score",
            "reason",
            "scanned_at",
            "source_ip",
            "scanned_by_type",
            "scanned_by_staff_id",
            "scanned_by_name",
            "movie_id",
            "movie_title",
            "show_id",
            "show_date",
            "show_time",
            "hall",
        ]
    )

    for scan in scans:
        payload = _build_scan_payload(scan)
        writer.writerow(
            [
                payload.get("id"),
                payload.get("reference"),
                payload.get("ticketId"),
                payload.get("status"),
                payload.get("fraudScore"),
                payload.get("reason") or "",
                payload.get("scannedAt") or "",
                payload.get("sourceIp") or "",
                payload.get("scannedByType") or "",
                payload.get("scannedByStaffId") or "",
                payload.get("scannedByName") or "",
                payload.get("movieId") or "",
                payload.get("movieTitle") or "",
                payload.get("showId") or "",
                payload.get("showDate") or "",
                payload.get("showTime") or "",
                payload.get("hall") or "",
            ]
        )

    return response


def _serialize_monitor_export_job(job: Any) -> dict[str, Any]:
    result = job.result if isinstance(getattr(job, "result", None), dict) else {}
    return {
        "id": job.id,
        "jobType": getattr(job, "job_type", ""),
        "status": getattr(job, "status", ""),
        "attempts": int(getattr(job, "attempts", 0) or 0),
        "maxAttempts": int(getattr(job, "max_attempts", 0) or 0),
        "availableAt": job.available_at.isoformat() if getattr(job, "available_at", None) else None,
        "queuedAt": job.created_at.isoformat() if getattr(job, "created_at", None) else None,
        "startedAt": job.started_at.isoformat() if getattr(job, "started_at", None) else None,
        "finishedAt": job.finished_at.isoformat() if getattr(job, "finished_at", None) else None,
        "filename": result.get("filename"),
        "rowCount": int(result.get("row_count") or 0),
        "errorMessage": getattr(job, "error_message", None),
    }


@api_view(["GET"])
@vendor_required
def vendor_ticket_validation_monitor(request: Any):
    """Return filtered ticket scan logs + metrics for vendor monitoring."""
    vendor = resolve_vendor(request)
    vendor_staff = resolve_vendor_staff(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    rate_limited = _enforce_ticket_validation_rate_limits(
        request=request,
        vendor=vendor,
        vendor_staff=vendor_staff,
        endpoint="monitor",
    )
    if rate_limited is not None:
        return rate_limited

    filters = _parse_monitor_filters(request)
    base_queryset = _base_monitor_queryset(vendor)
    filtered_queryset = _apply_monitor_filters(base_queryset, filters=filters)
    scans = list(filtered_queryset.order_by("-scanned_at", "-id")[: filters["limit"]])
    summary = _build_monitor_summary(filtered_queryset)
    realtime = _build_monitor_realtime_metrics(base_queryset)

    alerts = [
        {
            "type": "duplicate_ticket",
            "count": summary["duplicate"],
            "title": "Duplicate Ticket Alerts",
            "severity": "warning" if summary["duplicate"] > 0 else "info",
            "message": "Duplicate outcomes in the current filtered results.",
        },
        {
            "type": "fraud_suspected",
            "count": summary["fraud"] + summary["invalid"],
            "title": "Fraud/Invalid Alerts",
            "severity": "danger" if (summary["fraud"] + summary["invalid"]) > 0 else "info",
            "message": "Fraud and invalid outcomes in the current filtered results.",
        },
    ]
    alerts.extend(_build_monitor_suspicious_alerts(base_queryset))

    return Response(
        {
            "summary": summary,
            "realtime": realtime,
            "alerts": alerts,
            "scans": [_build_scan_payload(scan) for scan in scans],
            "filters": _build_monitor_filter_options(vendor),
            "appliedFilters": _build_monitor_applied_filters(filters),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@vendor_required
def vendor_ticket_validation_monitor_export(request: Any):
    """Export filtered ticket validation monitor logs as CSV."""
    vendor = resolve_vendor(request)
    vendor_staff = resolve_vendor_staff(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    rate_limited = _enforce_ticket_validation_rate_limits(
        request=request,
        vendor=vendor,
        vendor_staff=vendor_staff,
        endpoint="monitor",
    )
    if rate_limited is not None:
        return rate_limited

    filters = _parse_monitor_filters(request)
    filtered_queryset = _apply_monitor_filters(_base_monitor_queryset(vendor), filters=filters)
    scans = list(filtered_queryset.order_by("-scanned_at", "-id"))
    return _build_monitor_csv_response(scans)


@api_view(["POST"])
@vendor_required
def vendor_ticket_validation_monitor_export_jobs(request: Any):
    """Queue a monitor CSV export job for background processing."""
    vendor = resolve_vendor(request)
    vendor_staff = resolve_vendor_staff(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    rate_limited = _enforce_ticket_validation_rate_limits(
        request=request,
        vendor=vendor,
        vendor_staff=vendor_staff,
        endpoint="monitor",
    )
    if rate_limited is not None:
        return rate_limited

    filters = _parse_monitor_filters(request)
    export_filters = {
        "status": filters.get("status") or "",
        "reference": filters.get("reference") or "",
        "date": filters["date"].isoformat() if filters.get("date") else "",
        "staffMode": filters.get("staffMode") or "",
        "staffId": filters.get("staffId"),
        "movieId": filters.get("movieId"),
        "showId": filters.get("showId"),
    }
    queued_job = services.enqueue_vendor_monitor_export_job(
        vendor_id=vendor.id,
        filters=export_filters,
        requested_by_staff_id=vendor_staff.id if isinstance(vendor_staff, VendorStaff) else None,
    )
    if not queued_job:
        return Response(
            {"message": "Failed to queue monitor export job."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "message": "Monitor CSV export queued.",
            "job": _serialize_monitor_export_job(queued_job),
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["GET"])
@vendor_required
def vendor_ticket_validation_monitor_export_job_detail(request: Any, job_id: int):
    """Return current status for one queued monitor CSV export job."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    queued_job = services.get_vendor_monitor_export_job(vendor.id, job_id)
    if not queued_job:
        return Response({"message": "Export job not found."}, status=status.HTTP_404_NOT_FOUND)

    response_payload = {
        "job": _serialize_monitor_export_job(queued_job),
    }
    normalized_status = str(queued_job.status or "").strip().upper()
    if normalized_status == "FAILED":
        response_payload["message"] = queued_job.error_message or "Monitor CSV export failed."
        return Response(response_payload, status=status.HTTP_200_OK)
    if normalized_status != "COMPLETED":
        response_payload["message"] = "Monitor CSV export is still processing."
        return Response(response_payload, status=status.HTTP_202_ACCEPTED)

    response_payload["message"] = "Monitor CSV export is ready."
    return Response(response_payload, status=status.HTTP_200_OK)


@api_view(["GET"])
@vendor_required
def vendor_ticket_validation_monitor_export_job_download(request: Any, job_id: int):
    """Download a completed queued monitor CSV export job."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    queued_job = services.get_vendor_monitor_export_job(vendor.id, job_id)
    if not queued_job:
        return Response({"message": "Export job not found."}, status=status.HTTP_404_NOT_FOUND)

    normalized_status = str(queued_job.status or "").strip().upper()
    if normalized_status != "COMPLETED":
        return Response(
            {
                "message": "Export file is not ready yet.",
                "status": normalized_status or "PENDING",
            },
            status=status.HTTP_409_CONFLICT,
        )

    csv_content, filename, error_message = services.get_vendor_monitor_export_job_file(queued_job)
    if error_message or csv_content is None:
        return Response(
            {"message": error_message or "Failed to prepare export file."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename or "ticket_validation_monitor.csv"}"'
    return response
