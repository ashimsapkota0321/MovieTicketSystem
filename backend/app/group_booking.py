"""Service functions for group booking and split payment workflows."""

from __future__ import annotations

import random
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from . import services
from .group_booking_serializers import (
    GroupBookingCreateSerializer,
    GroupJoinSessionSerializer,
    GroupManualSplitSerializer,
    GroupParticipantDropSerializer,
    GroupPaymentCompletionSerializer,
    GroupPaymentInitiateSerializer,
    GroupSeatSelectionSerializer,
    GroupSessionCancelSerializer,
)
from .models import (
    Booking,
    BookingSeat,
    GroupBookingSession,
    GroupParticipant,
    GroupPayment,
    Payment,
    Seat,
    SeatAvailability,
    Show,
    Ticket,
)
from .permissions import resolve_customer
from .utils import coalesce, get_payload


GROUP_DEFAULT_EXPIRY_MINUTES = 12
GROUP_MIN_EXPIRY_MINUTES = 10
GROUP_MAX_EXPIRY_MINUTES = 20
GROUP_PAYMENT_PREFIX = "GROUP"


def _frontend_base_url() -> str:
    value = str(getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173") or "").strip()
    return value.rstrip("/") or "http://localhost:5173"


def _decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    parsed = services._parse_price_amount(value)
    if parsed is None:
        return services._quantize_money(default)
    return services._quantize_money(parsed)


def _float_money(value: Any) -> float:
    return float(_decimal(value))


def _normalize_session_seats(value: Any) -> list[str]:
    return sorted(services._normalize_seat_labels(value), key=services._seat_sort_key)


def _build_invite_link(invite_code: str) -> str:
    return f"{_frontend_base_url()}/group-booking/session/{invite_code}"


def _participant_name(participant: GroupParticipant) -> str:
    user = participant.user
    if not user:
        return "Unknown"
    parts = [str(user.first_name or "").strip(), str(user.middle_name or "").strip(), str(user.last_name or "").strip()]
    full = " ".join([part for part in parts if part]).strip()
    return full or str(user.email or user.id)


def _participant_amount_remaining(participant: GroupParticipant) -> Decimal:
    remaining = _decimal(participant.amount_to_pay) - _decimal(participant.amount_paid)
    if remaining < Decimal("0"):
        return Decimal("0.00")
    return services._quantize_money(remaining)


def _session_amount_remaining(session: GroupBookingSession) -> Decimal:
    remaining = _decimal(session.total_amount) - _decimal(session.amount_paid)
    if remaining < Decimal("0"):
        return Decimal("0.00")
    return services._quantize_money(remaining)


def _safe_metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _update_metadata(source: Any, updates: dict[str, Any]) -> dict[str, Any]:
    merged = _safe_metadata(source)
    merged.update(updates)
    return merged


def _generate_invite_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(300):
        code = "".join(random.choice(alphabet) for _ in range(10))
        if not GroupBookingSession.objects.filter(invite_code__iexact=code).exists():
            return code
    return uuid.uuid4().hex[:10].upper()


def _generate_ticket_reference() -> str:
    for _ in range(200):
        reference = uuid.uuid4().hex[:10].upper()
        if not Ticket.objects.filter(reference=reference).exists():
            return reference
    return uuid.uuid4().hex[:14].upper()


def _group_payment_method(session_id: int) -> str:
    return f"{GROUP_PAYMENT_PREFIX}:{session_id}"[:30]


def _active_participants(session: GroupBookingSession, *, lock: bool = False) -> list[GroupParticipant]:
    queryset = session.participants.select_related("user").filter(left_at__isnull=True).order_by("joined_at", "id")
    if lock:
        queryset = queryset.select_for_update()
    return list(queryset)


def _session_query_for_read():
    return GroupBookingSession.objects.select_related(
        "host",
        "show",
        "show__movie",
        "show__vendor",
        "showtime",
        "showtime__screen",
    ).prefetch_related("participants__user")


def _session_query_for_update():
    return GroupBookingSession.objects.select_for_update().select_related(
        "host",
        "show",
        "show__movie",
        "show__vendor",
        "showtime",
        "showtime__screen",
    )


def _load_session_for_update(*, session_id: Optional[int] = None, invite_code: Optional[str] = None) -> Optional[GroupBookingSession]:
    queryset = _session_query_for_update()
    if session_id is not None:
        queryset = queryset.filter(id=session_id)
    elif invite_code is not None:
        queryset = queryset.filter(invite_code__iexact=str(invite_code).strip())
    else:
        return None
    return queryset.first()


def _is_session_open(session: GroupBookingSession) -> bool:
    return session.status in {
        GroupBookingSession.STATUS_ACTIVE,
        GroupBookingSession.STATUS_PARTIALLY_PAID,
    }


def _is_session_expired(session: GroupBookingSession, now: Optional[Any] = None) -> bool:
    now_value = now or timezone.now()
    return bool(session.expires_at and session.expires_at <= now_value)


def _release_session_seat_locks(session: GroupBookingSession, *, lock_rows: bool) -> int:
    showtime = session.showtime
    screen = getattr(showtime, "screen", None)
    if not showtime or not screen:
        return 0

    released = 0
    for label in _normalize_session_seats(session.selected_seats):
        row_label, seat_number = services._split_seat_label(label)
        if not seat_number:
            continue

        seat = Seat.objects.filter(
            screen=screen,
            row_label=row_label or None,
            seat_number=seat_number,
        ).first()
        if not seat:
            continue

        availability_qs = SeatAvailability.objects.filter(seat=seat, showtime=showtime)
        if lock_rows:
            availability_qs = availability_qs.select_for_update()
        availability = availability_qs.first()
        if not availability:
            continue

        status_value = str(availability.seat_status or "").strip().lower()
        if status_value in services.BOOKED_STATUSES:
            continue

        if availability.locked_until is None and status_value == services.SEAT_STATUS_AVAILABLE.lower():
            continue

        availability.seat_status = services.SEAT_STATUS_AVAILABLE
        availability.locked_until = None
        availability.save(update_fields=["seat_status", "locked_until", "last_updated"])
        released += 1

    return released


def _expire_or_cancel_session_locked(
    session: GroupBookingSession,
    *,
    new_status: str,
    reason: str,
) -> dict[str, Any]:
    now = timezone.now()
    released_count = _release_session_seat_locks(session, lock_rows=True)

    GroupPayment.objects.filter(
        session=session,
        status=GroupPayment.STATUS_INITIATED,
    ).update(
        status=GroupPayment.STATUS_FAILED,
        completed_at=now,
    )

    for participant in session.participants.select_for_update().all():
        if participant.left_at:
            participant.payment_status = GroupParticipant.PAYMENT_LEFT
            participant.save(update_fields=["payment_status"])
            continue
        if participant.payment_status in {GroupParticipant.PAYMENT_PENDING, GroupParticipant.PAYMENT_FAILED}:
            participant.payment_status = GroupParticipant.PAYMENT_FAILED
            participant.metadata = _update_metadata(
                participant.metadata,
                {
                    "session_closed_reason": reason,
                    "session_closed_at": now.isoformat(),
                },
            )
            participant.save(update_fields=["payment_status", "metadata"])

    session.status = new_status
    session.cancelled_at = now
    session.metadata = _update_metadata(
        session.metadata,
        {
            "closed_reason": reason,
            "closed_at": now.isoformat(),
            "released_seat_count": released_count,
        },
    )
    session.save(update_fields=["status", "cancelled_at", "metadata", "updated_at"])

    return {
        "session_id": session.id,
        "status": session.status,
        "released_seats": released_count,
    }


def expire_group_booking_sessions(*, session_id: Optional[int] = None) -> dict[str, Any]:
    now = timezone.now()
    queryset = GroupBookingSession.objects.filter(
        status__in=[
            GroupBookingSession.STATUS_ACTIVE,
            GroupBookingSession.STATUS_PARTIALLY_PAID,
        ],
        expires_at__lte=now,
    )
    if session_id is not None:
        queryset = queryset.filter(id=session_id)

    expired_count = 0
    released_seats = 0
    for item_id in queryset.values_list("id", flat=True):
        with transaction.atomic():
            session = _load_session_for_update(session_id=int(item_id))
            if not session:
                continue
            if not _is_session_open(session):
                continue
            if not _is_session_expired(session, now=now):
                continue
            result = _expire_or_cancel_session_locked(
                session,
                new_status=GroupBookingSession.STATUS_EXPIRED,
                reason="SESSION_EXPIRED",
            )
            expired_count += 1
            released_seats += int(result.get("released_seats") or 0)

    return {
        "expired_sessions": expired_count,
        "released_seats": released_seats,
    }


def _sync_session_paid_amount(session: GroupBookingSession) -> Decimal:
    total_paid = Decimal("0.00")
    for participant in _active_participants(session, lock=False):
        total_paid += _decimal(participant.amount_paid)
    session.amount_paid = services._quantize_money(total_paid)
    session.save(update_fields=["amount_paid", "updated_at"])
    return session.amount_paid


def _update_participant_payment_state(participant: GroupParticipant) -> None:
    if participant.left_at:
        participant.payment_status = GroupParticipant.PAYMENT_LEFT
        participant.save(update_fields=["payment_status"])
        return

    amount_to_pay = _decimal(participant.amount_to_pay)
    amount_paid = _decimal(participant.amount_paid)
    fields = []

    if amount_to_pay > Decimal("0") and amount_paid >= amount_to_pay:
        if participant.payment_status != GroupParticipant.PAYMENT_PAID:
            participant.payment_status = GroupParticipant.PAYMENT_PAID
            fields.append("payment_status")
        if participant.paid_at is None:
            participant.paid_at = timezone.now()
            fields.append("paid_at")
    else:
        next_status = GroupParticipant.PAYMENT_PENDING
        if amount_paid > Decimal("0"):
            next_status = GroupParticipant.PAYMENT_PENDING
        if participant.payment_status != next_status:
            participant.payment_status = next_status
            fields.append("payment_status")
        if participant.paid_at is not None and amount_paid < amount_to_pay:
            participant.paid_at = None
            fields.append("paid_at")

    if fields:
        participant.save(update_fields=fields)


def _rebalance_manual_split(session: GroupBookingSession) -> None:
    participants = _active_participants(session, lock=True)
    if not participants:
        return

    host_participant = next((item for item in participants if item.is_host), None)
    non_host_total = Decimal("0.00")
    for participant in participants:
        if participant.is_host:
            continue
        non_host_total += _decimal(participant.amount_to_pay)

    if host_participant:
        host_share = _decimal(session.total_amount) - non_host_total
        if host_share < Decimal("0"):
            host_share = Decimal("0.00")
        if _decimal(host_participant.amount_to_pay) != host_share:
            host_participant.amount_to_pay = host_share
            host_participant.save(update_fields=["amount_to_pay"])

    for participant in participants:
        _update_participant_payment_state(participant)


def _recalculate_equal_split(session: GroupBookingSession) -> None:
    participants = _active_participants(session, lock=True)
    if not participants:
        return

    total = _decimal(session.total_amount)
    total_cents = int((total * 100).to_integral_value())
    count = len(participants)
    base_cents = total_cents // count
    extra = total_cents % count

    for index, participant in enumerate(participants):
        share_cents = base_cents + (1 if index < extra else 0)
        share = services._quantize_money(Decimal(share_cents) / Decimal("100"))
        if _decimal(participant.amount_to_pay) != share:
            participant.amount_to_pay = share
            participant.save(update_fields=["amount_to_pay"])
        _update_participant_payment_state(participant)


def _seat_price_for_label(session: GroupBookingSession, label: str) -> Decimal:
    seat_map = session.seat_price_map if isinstance(session.seat_price_map, dict) else {}
    return _decimal(seat_map.get(label), default=Decimal("0.00"))


def _recalculate_seat_based_split(session: GroupBookingSession) -> None:
    participants = _active_participants(session, lock=True)
    if not participants:
        return

    normalized_session_seats = set(_normalize_session_seats(session.selected_seats))
    used = set()
    for participant in participants:
        next_labels = []
        for label in _normalize_session_seats(participant.selected_seats):
            if label not in normalized_session_seats:
                continue
            if label in used:
                continue
            next_labels.append(label)
            used.add(label)

        if participant.selected_seats != next_labels:
            participant.selected_seats = next_labels
            participant.save(update_fields=["selected_seats"])

        share = Decimal("0.00")
        for label in next_labels:
            share += _seat_price_for_label(session, label)

        share = services._quantize_money(share)
        if _decimal(participant.amount_to_pay) != share:
            participant.amount_to_pay = share
            participant.save(update_fields=["amount_to_pay"])
        _update_participant_payment_state(participant)


def _refresh_split(session: GroupBookingSession) -> None:
    if session.split_mode == GroupBookingSession.SPLIT_EQUAL:
        _recalculate_equal_split(session)
        return
    if session.split_mode == GroupBookingSession.SPLIT_SEAT_BASED:
        _recalculate_seat_based_split(session)
        return
    _rebalance_manual_split(session)


def _session_readiness(session: GroupBookingSession, participants: list[GroupParticipant]) -> dict[str, Any]:
    active = [item for item in participants if not item.left_at]
    if not active:
        return {
            "all_paid": False,
            "all_seats_allocated": False,
            "ready": False,
            "reason": "No active participants.",
        }

    all_paid = True
    for participant in active:
        if _participant_amount_remaining(participant) > Decimal("0"):
            all_paid = False
            break

    session_seats = _normalize_session_seats(session.selected_seats)
    assigned = set()
    for participant in active:
        for label in _normalize_session_seats(participant.selected_seats):
            if label in session_seats:
                assigned.add(label)

    if session.split_mode == GroupBookingSession.SPLIT_SEAT_BASED:
        all_seats_allocated = len(assigned) == len(session_seats)
    else:
        # Equal/manual sessions auto-allocate seats during final confirmation.
        all_seats_allocated = True
    ready = all_paid and all_seats_allocated
    reason = None
    if not all_paid:
        reason = "Waiting for all participants to pay."
    elif not all_seats_allocated:
        reason = "Seat assignment is incomplete."

    return {
        "all_paid": all_paid,
        "all_seats_allocated": all_seats_allocated,
        "ready": ready,
        "reason": reason,
    }


def _serialize_participant(participant: GroupParticipant) -> dict[str, Any]:
    return {
        "id": participant.id,
        "user_id": participant.user_id,
        "name": _participant_name(participant),
        "email": participant.user.email if participant.user else None,
        "is_host": bool(participant.is_host),
        "selected_seats": _normalize_session_seats(participant.selected_seats),
        "amount_to_pay": _float_money(participant.amount_to_pay),
        "amount_paid": _float_money(participant.amount_paid),
        "amount_remaining": _float_money(_participant_amount_remaining(participant)),
        "payment_status": participant.payment_status,
        "joined_at": participant.joined_at.isoformat() if participant.joined_at else None,
        "paid_at": participant.paid_at.isoformat() if participant.paid_at else None,
        "left_at": participant.left_at.isoformat() if participant.left_at else None,
    }


def _serialize_session(session: GroupBookingSession, *, viewer_id: Optional[int]) -> dict[str, Any]:
    participants = list(session.participants.select_related("user").order_by("joined_at", "id"))
    active = [item for item in participants if not item.left_at]
    readiness = _session_readiness(session, participants)

    assigned = set()
    for participant in active:
        assigned.update(_normalize_session_seats(participant.selected_seats))

    all_session_seats = _normalize_session_seats(session.selected_seats)
    unassigned = [label for label in all_session_seats if label not in assigned]

    viewer_participant = next((item for item in participants if item.user_id == viewer_id), None)
    viewer_payload = {
        "is_participant": bool(viewer_participant),
        "is_host": bool(viewer_participant and viewer_participant.is_host),
    }
    if viewer_participant:
        viewer_payload.update(
            {
                "participant_id": viewer_participant.id,
                "payment_status": viewer_participant.payment_status,
                "amount_to_pay": _float_money(viewer_participant.amount_to_pay),
                "amount_paid": _float_money(viewer_participant.amount_paid),
                "amount_remaining": _float_money(_participant_amount_remaining(viewer_participant)),
                "selected_seats": _normalize_session_seats(viewer_participant.selected_seats),
            }
        )

    expires_in_seconds = None
    if session.expires_at:
        expires_in_seconds = max(int((session.expires_at - timezone.now()).total_seconds()), 0)

    show = session.show
    showtime = session.showtime
    show_payload = {
        "id": show.id if show else None,
        "movie_id": show.movie_id if show else None,
        "movie_title": show.movie.title if show and show.movie else None,
        "cinema_id": show.vendor_id if show else None,
        "cinema_name": show.vendor.name if show and show.vendor else None,
        "show_date": show.show_date.isoformat() if show and show.show_date else None,
        "show_time": show.start_time.strftime("%H:%M") if show and show.start_time else None,
        "hall": show.hall if show else None,
        "showtime_id": showtime.id if showtime else None,
    }

    return {
        "id": session.id,
        "invite_code": session.invite_code,
        "invite_link": _build_invite_link(session.invite_code),
        "status": session.status,
        "split_mode": session.split_mode,
        "total_amount": _float_money(session.total_amount),
        "amount_paid": _float_money(session.amount_paid),
        "amount_remaining": _float_money(_session_amount_remaining(session)),
        "selected_seats": all_session_seats,
        "unassigned_seats": unassigned,
        "seat_count": len(all_session_seats),
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        "expires_in_seconds": expires_in_seconds,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "cancelled_at": session.cancelled_at.isoformat() if session.cancelled_at else None,
        "host_id": session.host_id,
        "host_name": _participant_name(active[0]) if active and active[0].is_host else (
            " ".join([part for part in [session.host.first_name, session.host.middle_name, session.host.last_name] if part]).strip() if session.host else None
        ),
        "show": show_payload,
        "participants": [_serialize_participant(item) for item in participants],
        "active_participant_count": len(active),
        "viewer": viewer_payload,
        "all_participants_paid": bool(readiness["all_paid"]),
        "all_seats_allocated": bool(readiness["all_seats_allocated"]),
        "ready_for_confirmation": bool(readiness["ready"]),
        "pending_reason": readiness.get("reason"),
        "bookings": _safe_metadata(session.metadata).get("bookings") or [],
    }


def _can_mutate_open_session(session: GroupBookingSession) -> Optional[tuple[dict[str, Any], int]]:
    if not _is_session_open(session):
        return (
            {"message": f"Session is not open for updates (status: {session.status})."},
            status.HTTP_409_CONFLICT,
        )
    if _is_session_expired(session):
        _expire_or_cancel_session_locked(
            session,
            new_status=GroupBookingSession.STATUS_EXPIRED,
            reason="SESSION_EXPIRED",
        )
        return (
            {"message": "Group booking session has expired."},
            status.HTTP_410_GONE,
        )
    return None


def _resolve_customer_request(request: Any) -> tuple[Optional[Any], Optional[dict[str, Any]], int]:
    customer = resolve_customer(request)
    if not customer:
        return None, {"message": services.AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED
    return customer, None, status.HTTP_200_OK


def create_group_booking_session(request: Any) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupBookingCreateSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid group booking payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    data = serializer.validated_data
    expiry_minutes = int(data.get("expiry_minutes") or GROUP_DEFAULT_EXPIRY_MINUTES)
    expiry_minutes = max(GROUP_MIN_EXPIRY_MINUTES, min(GROUP_MAX_EXPIRY_MINUTES, expiry_minutes))

    context_payload = {
        "show_id": data.get("show_id"),
        "movie_id": data.get("movie_id"),
        "cinema_id": data.get("cinema_id"),
        "date": data.get("date"),
        "time": data.get("time"),
        "hall": data.get("hall"),
    }
    context = services._resolve_booking_context(context_payload)
    show = services._resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND

    show_booking_error, show_booking_status = services._ensure_show_is_bookable(show)
    if show_booking_error:
        return show_booking_error, int(show_booking_status)

    selected_seats = _normalize_session_seats(data.get("selected_seats"))
    split_mode = data.get("split_mode") or GroupBookingSession.SPLIT_EQUAL

    with transaction.atomic():
        services.enqueue_stale_pending_cleanup_job(
            metadata={"source": "group_booking_create", "user_id": customer.id}
        )

        hall = str(data.get("hall") or show.hall or "").strip() or None
        screen, showtime = services._get_or_create_showtime_for_context(show, hall)

        lock_until = timezone.now() + timedelta(minutes=expiry_minutes)
        conflicts = {"sold": [], "unavailable": [], "reserved": [], "invalid": []}
        locked_availabilities = []
        seat_price_map: dict[str, str] = {}
        total_amount = Decimal("0.00")

        for label in selected_seats:
            row_label, seat_number = services._split_seat_label(label)
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
                defaults={"seat_status": services.SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in services.BOOKED_STATUSES:
                conflicts["sold"].append(label)
                continue
            if current_status == services.SEAT_STATUS_UNAVAILABLE.lower():
                conflicts["unavailable"].append(label)
                continue
            if availability.locked_until and availability.locked_until > timezone.now():
                conflicts["reserved"].append(label)
                continue

            seat_price, _ = services._resolve_dynamic_seat_price(
                show=show,
                showtime=showtime,
                screen=screen,
                seat_type=seat.seat_type,
                event_name="",
            )
            normalized_price = _decimal(seat_price)
            seat_price_map[label] = f"{normalized_price}"
            total_amount += normalized_price
            locked_availabilities.append(availability)

        if any(conflicts.values()):
            return {
                "message": "Unable to lock one or more seats for group booking.",
                "conflicts": {
                    "sold": sorted(conflicts["sold"], key=services._seat_sort_key),
                    "unavailable": sorted(conflicts["unavailable"], key=services._seat_sort_key),
                    "reserved": sorted(conflicts["reserved"], key=services._seat_sort_key),
                    "invalid": sorted(conflicts["invalid"], key=services._seat_sort_key),
                },
            }, status.HTTP_409_CONFLICT

        session = GroupBookingSession.objects.create(
            host=customer,
            show=show,
            showtime=showtime,
            invite_code=_generate_invite_code(),
            split_mode=split_mode,
            selected_seats=selected_seats,
            seat_price_map=seat_price_map,
            total_amount=services._quantize_money(total_amount),
            amount_paid=Decimal("0.00"),
            status=GroupBookingSession.STATUS_ACTIVE,
            expires_at=lock_until,
            metadata={
                "created_by": customer.id,
                "expiry_minutes": expiry_minutes,
            },
        )

        host_selected = []
        GroupParticipant.objects.create(
            session=session,
            user=customer,
            is_host=True,
            selected_seats=host_selected,
            amount_to_pay=Decimal("0.00"),
            amount_paid=Decimal("0.00"),
            payment_status=GroupParticipant.PAYMENT_PENDING,
            metadata={"joined_via": "HOST_CREATE"},
        )

        for availability in locked_availabilities:
            availability.seat_status = services.SEAT_STATUS_AVAILABLE
            availability.locked_until = lock_until
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

        _refresh_split(session)
        _sync_session_paid_amount(session)

    session_payload = _serialize_session(session, viewer_id=customer.id)
    return {
        "message": "Group booking session created.",
        "session": session_payload,
    }, status.HTTP_201_CREATED


def list_group_booking_sessions(request: Any) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    services.enqueue_stale_pending_cleanup_job(
        metadata={"source": "group_booking_list", "user_id": customer.id}
    )
    query_params = getattr(request, "query_params", {})
    status_filter = str(query_params.get("status") or "").strip().upper()

    queryset = _session_query_for_read().filter(
        Q(host_id=customer.id) | Q(participants__user_id=customer.id)
    ).distinct()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    sessions = [
        _serialize_session(item, viewer_id=customer.id)
        for item in queryset.order_by("-created_at", "-id")[:50]
    ]
    return {"sessions": sessions}, status.HTTP_200_OK


def get_group_booking_session_by_invite(request: Any, invite_code: str) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    services.enqueue_stale_pending_cleanup_job(
        metadata={"source": "group_booking_by_invite", "user_id": customer.id}
    )
    session = _session_query_for_read().filter(invite_code__iexact=str(invite_code).strip()).first()
    if not session:
        return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

    return {
        "session": _serialize_session(session, viewer_id=customer.id),
    }, status.HTTP_200_OK


def join_group_booking_session(request: Any, invite_code: str) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupJoinSessionSerializer(data=payload)
    serializer.is_valid(raise_exception=False)

    with transaction.atomic():
        session = _load_session_for_update(invite_code=str(invite_code).strip())
        if not session:
            return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

        session_error = _can_mutate_open_session(session)
        if session_error:
            return session_error

        participant = GroupParticipant.objects.select_for_update().filter(
            session=session,
            user=customer,
        ).first()

        payments_started = GroupPayment.objects.filter(
            session=session,
            status=GroupPayment.STATUS_SUCCESS,
        ).exists()
        if not participant and payments_started:
            return {
                "message": "Cannot add new participants after payments are already completed.",
            }, status.HTTP_409_CONFLICT

        max_participants = max(len(_normalize_session_seats(session.selected_seats)), 1)
        active_count = GroupParticipant.objects.filter(session=session, left_at__isnull=True).count()
        if not participant and active_count >= max_participants:
            return {
                "message": "All seats are already associated with active participants.",
            }, status.HTTP_409_CONFLICT

        created = False
        if not participant:
            participant = GroupParticipant.objects.create(
                session=session,
                user=customer,
                is_host=False,
                selected_seats=[],
                amount_to_pay=Decimal("0.00"),
                amount_paid=Decimal("0.00"),
                payment_status=GroupParticipant.PAYMENT_PENDING,
                metadata={"joined_via": "INVITE"},
            )
            created = True
        elif participant.left_at:
            if _decimal(participant.amount_paid) > Decimal("0"):
                return {
                    "message": "You cannot rejoin this session after payment has been processed.",
                }, status.HTTP_409_CONFLICT
            participant.left_at = None
            participant.payment_status = GroupParticipant.PAYMENT_PENDING
            participant.metadata = _update_metadata(participant.metadata, {"rejoined_at": timezone.now().isoformat()})
            participant.save(update_fields=["left_at", "payment_status", "metadata"])

        _refresh_split(session)
        _sync_session_paid_amount(session)

        session_payload = _serialize_session(session, viewer_id=customer.id)

    return {
        "message": "Joined group booking session." if created else "Already joined group booking session.",
        "session": session_payload,
    }, status.HTTP_200_OK


def update_group_participant_seats(request: Any, session_id: int) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupSeatSelectionSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid seat selection payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    with transaction.atomic():
        session = _load_session_for_update(session_id=session_id)
        if not session:
            return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

        if session.split_mode != GroupBookingSession.SPLIT_SEAT_BASED:
            return {
                "message": "Seat assignment is only available for seat-based split mode.",
            }, status.HTTP_400_BAD_REQUEST

        session_error = _can_mutate_open_session(session)
        if session_error:
            return session_error

        participant = GroupParticipant.objects.select_for_update().filter(
            session=session,
            user=customer,
            left_at__isnull=True,
        ).first()
        if not participant:
            return {
                "message": "You are not an active participant of this session.",
            }, status.HTTP_403_FORBIDDEN

        if _decimal(participant.amount_paid) > Decimal("0"):
            return {
                "message": "Seat selection cannot be changed after payment has started.",
            }, status.HTTP_409_CONFLICT

        requested_labels = _normalize_session_seats(serializer.validated_data.get("selected_seats"))
        session_labels = set(_normalize_session_seats(session.selected_seats))

        invalid = [label for label in requested_labels if label not in session_labels]
        if invalid:
            return {
                "message": "Some selected seats are not part of this group session.",
                "invalid_seats": invalid,
            }, status.HTTP_400_BAD_REQUEST

        used_by_others = set()
        others = GroupParticipant.objects.select_for_update().filter(
            session=session,
            left_at__isnull=True,
        ).exclude(id=participant.id)
        for other in others:
            used_by_others.update(_normalize_session_seats(other.selected_seats))

        conflicts = [label for label in requested_labels if label in used_by_others]
        if conflicts:
            return {
                "message": "Some selected seats are already assigned to another participant.",
                "conflicts": conflicts,
            }, status.HTTP_409_CONFLICT

        participant.selected_seats = requested_labels
        participant.save(update_fields=["selected_seats"])

        _refresh_split(session)
        _sync_session_paid_amount(session)

        session_payload = _serialize_session(session, viewer_id=customer.id)

    return {
        "message": "Seat assignment updated.",
        "session": session_payload,
    }, status.HTTP_200_OK


def apply_group_manual_split(request: Any, session_id: int) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupManualSplitSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid manual split payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    with transaction.atomic():
        session = _load_session_for_update(session_id=session_id)
        if not session:
            return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

        if session.host_id != customer.id:
            return {"message": "Only host can override manual split."}, status.HTTP_403_FORBIDDEN

        if session.split_mode != GroupBookingSession.SPLIT_MANUAL:
            return {
                "message": "Manual split override is only available for MANUAL split mode.",
            }, status.HTTP_400_BAD_REQUEST

        session_error = _can_mutate_open_session(session)
        if session_error:
            return session_error

        if GroupPayment.objects.filter(session=session, status=GroupPayment.STATUS_SUCCESS).exists():
            return {
                "message": "Manual split cannot be changed after successful payments.",
            }, status.HTTP_409_CONFLICT

        allocations = serializer.validated_data.get("allocations") or []
        active_participants = _active_participants(session, lock=True)
        active_user_ids = {item.user_id for item in active_participants}

        allocation_map: dict[int, Decimal] = {}
        for item in allocations:
            user_id = int(item["user_id"])
            if user_id not in active_user_ids:
                return {
                    "message": f"User {user_id} is not an active participant.",
                }, status.HTTP_400_BAD_REQUEST
            allocation_map[user_id] = _decimal(item["amount"])

        expected_total = _decimal(session.total_amount)
        provided_total = Decimal("0.00")
        for amount in allocation_map.values():
            provided_total += amount
        provided_total = services._quantize_money(provided_total)

        if provided_total != expected_total:
            return {
                "message": "Manual split must match the full session total amount.",
                "expected_total": _float_money(expected_total),
                "provided_total": _float_money(provided_total),
            }, status.HTTP_400_BAD_REQUEST

        for participant in active_participants:
            participant.amount_to_pay = allocation_map.get(participant.user_id, Decimal("0.00"))
            participant.save(update_fields=["amount_to_pay"])
            _update_participant_payment_state(participant)

        _sync_session_paid_amount(session)
        session_payload = _serialize_session(session, viewer_id=customer.id)

    return {
        "message": "Manual split updated.",
        "session": session_payload,
    }, status.HTTP_200_OK


def _build_assignment_map_for_completion(
    session: GroupBookingSession,
    participants: list[GroupParticipant],
) -> dict[int, list[str]]:
    session_seats = _normalize_session_seats(session.selected_seats)
    seat_set = set(session_seats)
    assigned_to_user: dict[str, int] = {}

    for participant in participants:
        for label in _normalize_session_seats(participant.selected_seats):
            if label not in seat_set:
                continue
            if label in assigned_to_user:
                continue
            assigned_to_user[label] = participant.user_id

    unassigned = [label for label in session_seats if label not in assigned_to_user]

    if unassigned:
        if session.split_mode == GroupBookingSession.SPLIT_SEAT_BASED:
            host = next((item for item in participants if item.is_host), participants[0])
            for label in unassigned:
                assigned_to_user[label] = host.user_id
        else:
            for index, label in enumerate(unassigned):
                owner = participants[index % len(participants)]
                assigned_to_user[label] = owner.user_id

    assignment_map: dict[int, list[str]] = {participant.user_id: [] for participant in participants}
    for label in session_seats:
        owner_user_id = assigned_to_user.get(label)
        if owner_user_id is None:
            continue
        assignment_map.setdefault(owner_user_id, []).append(label)

    for participant in participants:
        normalized = sorted(assignment_map.get(participant.user_id, []), key=services._seat_sort_key)
        if _normalize_session_seats(participant.selected_seats) != normalized:
            participant.selected_seats = normalized
            participant.save(update_fields=["selected_seats"])
        assignment_map[participant.user_id] = normalized

    return assignment_map


def _build_group_ticket_payload(
    *,
    session: GroupBookingSession,
    participant: GroupParticipant,
    booking: Booking,
    seat_labels: list[str],
    reference: str,
) -> dict[str, Any]:
    show = session.show
    movie = show.movie if show else None
    vendor = show.vendor if show else None
    user = participant.user

    user_name_parts = [user.first_name, user.middle_name, user.last_name] if user else []
    user_name = " ".join([part for part in user_name_parts if part]).strip() if user else ""

    ticket_total = Decimal("0.00")
    for label in seat_labels:
        ticket_total += _seat_price_for_label(session, label)
    ticket_total = services._quantize_money(ticket_total)

    show_date_text = show.show_date.isoformat() if show and show.show_date else ""
    show_time_text = show.start_time.strftime("%I:%M %p") if show and show.start_time else ""

    payload = {
        "reference": reference,
        "movie": {
            "title": movie.title if movie else "",
            "seat": f"Seat No: {', '.join(seat_labels)}",
            "venue": vendor.name if vendor else "",
            "venue_name": vendor.name if vendor else "",
            "venue_location": vendor.city if vendor else "",
            "show_date": show_date_text,
            "show_time": show_time_text,
            "theater": show.hall if show else "",
            "language": movie.language if movie else "",
            "runtime": movie.duration if movie else "",
            "movie_id": show.movie_id if show else None,
            "cinema_id": show.vendor_id if show else None,
            "show_id": show.id if show else None,
        },
        "selected_seats": seat_labels,
        "ticket_total": float(ticket_total),
        "food_total": 0.0,
        "total": float(_decimal(participant.amount_paid or participant.amount_to_pay)),
        "items": [],
        "user": {
            "id": user.id if user else None,
            "name": user_name,
            "email": user.email if user else None,
            "phone": user.phone_number if user else None,
        },
        "booking": {
            "booking_id": booking.id,
            "show_id": show.id if show else None,
            "showtime_id": session.showtime_id,
            "screen": show.hall if show else None,
            "sold_seats": seat_labels,
        },
        "group_booking": {
            "session_id": session.id,
            "participant_id": participant.id,
            "invite_code": session.invite_code,
            "split_mode": session.split_mode,
        },
        "created_at": timezone.now().isoformat(),
        "details_url": f"/api/ticket/{reference}/details/",
    }
    return payload


def _confirm_group_session_locked(session: GroupBookingSession) -> dict[str, Any]:
    participants = _active_participants(session, lock=True)
    if not participants:
        raise ValueError("No active participants available to confirm booking.")

    readiness = _session_readiness(session, participants)
    if not readiness.get("ready"):
        raise ValueError(str(readiness.get("reason") or "Group booking is not ready for confirmation."))

    showtime = session.showtime
    screen = getattr(showtime, "screen", None)
    if not showtime or not screen:
        raise ValueError("Session showtime context is invalid.")

    assignment_map = _build_assignment_map_for_completion(session, participants)
    booking_records: list[dict[str, Any]] = []

    for participant in participants:
        seat_labels = assignment_map.get(participant.user_id) or []
        if not seat_labels:
            continue

        booking_total = Decimal("0.00")
        for label in seat_labels:
            booking_total += _seat_price_for_label(session, label)
        booking_total = services._quantize_money(booking_total)

        booking = Booking.objects.create(
            user=participant.user,
            showtime=showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=booking_total,
        )

        for label in seat_labels:
            row_label, seat_number = services._split_seat_label(label)
            if not seat_number:
                raise ValueError(f"Invalid seat label {label} during confirmation.")

            seat = Seat.objects.filter(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            ).first()
            if not seat:
                raise ValueError(f"Seat {label} no longer exists for this show.")

            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": services.SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            already_booked = BookingSeat.objects.filter(
                showtime=showtime,
                seat=seat,
            ).exclude(booking__booking_status__iexact=services.BOOKING_STATUS_CANCELLED).exists()
            if current_status in services.BOOKED_STATUSES or already_booked:
                raise ValueError(f"Seat {label} became unavailable before confirmation.")

            availability.seat_status = services.SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

            BookingSeat.objects.create(
                booking=booking,
                showtime=showtime,
                seat=seat,
                seat_price=_seat_price_for_label(session, label),
            )

        paid_amount = _decimal(participant.amount_paid or participant.amount_to_pay)
        payment = Payment.objects.create(
            booking=booking,
            payment_method=_group_payment_method(session.id),
            payment_status=Payment.Status.SUCCESS,
            amount=paid_amount,
        )

        GroupPayment.objects.filter(
            session=session,
            participant=participant,
            status=GroupPayment.STATUS_SUCCESS,
            booking__isnull=True,
        ).update(booking=booking)

        services._record_vendor_booking_earning(booking, gross_amount=booking_total, payment=payment)
        transaction.on_commit(
            lambda booking_id=booking.id: services._run_post_booking_rewards(booking_id)
        )

        reference = _generate_ticket_reference()
        ticket_payload = _build_group_ticket_payload(
            session=session,
            participant=participant,
            booking=booking,
            seat_labels=seat_labels,
            reference=reference,
        )
        ticket_security = services.build_ticket_security_fields(
            booking=booking,
            show=session.show,
            user=participant.user,
            seats=seat_labels,
            payment_status=Ticket.PaymentStatus.PAID,
        )
        ticket = Ticket.objects.create(
            reference=reference,
            payload=ticket_payload,
            **ticket_security,
        )
        services.persist_ticket_render_artifacts(ticket)

        try:
            services.send_ticket_confirmation_email(ticket)
        except Exception:
            # Do not block group booking completion if email delivery fails.
            pass
        qr_payload = services.build_ticket_qr_payload(ticket)

        participant.metadata = _update_metadata(
            participant.metadata,
            {
                "booking_id": booking.id,
                "ticket_reference": reference,
                "ticket_id": str(ticket.ticket_id),
            },
        )
        participant.payment_status = GroupParticipant.PAYMENT_PAID
        participant.paid_at = participant.paid_at or timezone.now()
        participant.save(update_fields=["metadata", "payment_status", "paid_at"])

        booking_records.append(
            {
                "participant_id": participant.id,
                "user_id": participant.user_id,
                "booking_id": booking.id,
                "ticket_reference": reference,
                "ticket_id": str(ticket.ticket_id),
                "qr_token": qr_payload.get("token"),
                "seats": seat_labels,
                "amount": float(paid_amount),
            }
        )

    session.status = GroupBookingSession.STATUS_COMPLETED
    session.completed_at = timezone.now()
    session.amount_paid = _decimal(session.total_amount)
    session.metadata = _update_metadata(session.metadata, {"bookings": booking_records})
    session.save(update_fields=["status", "completed_at", "amount_paid", "metadata", "updated_at"])

    return {
        "session_id": session.id,
        "status": session.status,
        "bookings": booking_records,
    }


def initiate_group_payment(request: Any, session_id: int) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupPaymentInitiateSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid payment payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    payment_method = str(serializer.validated_data.get("payment_method") or "ESEWA").strip().upper() or "ESEWA"

    with transaction.atomic():
        session = _load_session_for_update(session_id=session_id)
        if not session:
            return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

        session_error = _can_mutate_open_session(session)
        if session_error:
            return session_error

        participant = GroupParticipant.objects.select_for_update().filter(
            session=session,
            user=customer,
            left_at__isnull=True,
        ).first()
        if not participant:
            return {
                "message": "You are not an active participant of this group session.",
            }, status.HTTP_403_FORBIDDEN

        due_amount = _participant_amount_remaining(participant)
        if due_amount <= Decimal("0"):
            return {
                "message": "No pending amount left for this participant.",
                "session": _serialize_session(session, viewer_id=customer.id),
            }, status.HTTP_200_OK

        payment = GroupPayment.objects.create(
            session=session,
            participant=participant,
            user=customer,
            payment_method=payment_method,
            amount=due_amount,
            status=GroupPayment.STATUS_INITIATED,
            metadata={
                "initiated_at": timezone.now().isoformat(),
                "client_reference": f"GRP-{session.id}-{uuid.uuid4().hex[:8].upper()}",
            },
        )

        participant.payment_status = GroupParticipant.PAYMENT_PENDING
        participant.save(update_fields=["payment_status"])

        session_payload = _serialize_session(session, viewer_id=customer.id)

    return {
        "message": "Participant payment initiated.",
        "payment": {
            "id": payment.id,
            "amount": _float_money(payment.amount),
            "status": payment.status,
            "payment_method": payment.payment_method,
            "client_reference": _safe_metadata(payment.metadata).get("client_reference"),
        },
        "session": session_payload,
    }, status.HTTP_201_CREATED


def complete_group_payment(request: Any, session_id: int, payment_id: int) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupPaymentCompletionSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid payment completion payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    completion_status = str(serializer.validated_data.get("status") or "").upper()
    provided_transaction_id = str(serializer.validated_data.get("transaction_id") or "").strip() or None
    provider_reference = str(serializer.validated_data.get("provider_reference") or "").strip() or None
    extra_metadata = serializer.validated_data.get("metadata") if isinstance(serializer.validated_data.get("metadata"), dict) else {}

    with transaction.atomic():
        session = _load_session_for_update(session_id=session_id)
        if not session:
            return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

        session_error = _can_mutate_open_session(session)
        if session_error:
            return session_error

        payment = GroupPayment.objects.select_for_update().select_related("participant").filter(
            id=payment_id,
            session=session,
        ).first()
        if not payment:
            return {"message": "Group payment record not found."}, status.HTTP_404_NOT_FOUND

        if payment.user_id != customer.id and session.host_id != customer.id:
            return {
                "message": "You do not have permission to complete this payment.",
            }, status.HTTP_403_FORBIDDEN

        if payment.status != GroupPayment.STATUS_INITIATED:
            return {
                "message": "This payment is already processed.",
                "payment_status": payment.status,
            }, status.HTTP_409_CONFLICT

        participant = GroupParticipant.objects.select_for_update().filter(id=payment.participant_id).first()
        if not participant or participant.left_at:
            return {
                "message": "Participant is no longer active in this session.",
            }, status.HTTP_409_CONFLICT

        now = timezone.now()
        transaction_id = provided_transaction_id or f"GRP-TXN-{uuid.uuid4().hex[:16].upper()}"

        if completion_status == "FAILED":
            payment.status = GroupPayment.STATUS_FAILED
            payment.completed_at = now
            payment.transaction_id = transaction_id
            payment.provider_reference = provider_reference
            payment.metadata = _update_metadata(
                payment.metadata,
                {
                    "completion_status": "FAILED",
                    "completed_at": now.isoformat(),
                    **extra_metadata,
                },
            )
            payment.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "transaction_id",
                    "provider_reference",
                    "metadata",
                ]
            )

            if _decimal(participant.amount_paid) > Decimal("0") and _participant_amount_remaining(participant) <= Decimal("0"):
                participant.payment_status = GroupParticipant.PAYMENT_PAID
            else:
                participant.payment_status = GroupParticipant.PAYMENT_FAILED
            participant.save(update_fields=["payment_status"])

            total_paid = _sync_session_paid_amount(session)
            if total_paid > Decimal("0"):
                session.status = GroupBookingSession.STATUS_PARTIALLY_PAID
            else:
                session.status = GroupBookingSession.STATUS_ACTIVE
            session.save(update_fields=["status", "updated_at"])

            session_payload = _serialize_session(session, viewer_id=customer.id)
            return {
                "message": "Payment marked as failed.",
                "payment": {
                    "id": payment.id,
                    "status": payment.status,
                    "amount": _float_money(payment.amount),
                    "transaction_id": payment.transaction_id,
                },
                "session": session_payload,
            }, status.HTTP_200_OK

        duplicate_success = GroupPayment.objects.filter(
            transaction_id=transaction_id,
            status=GroupPayment.STATUS_SUCCESS,
        ).exclude(id=payment.id).exists()
        if duplicate_success:
            return {
                "message": "transaction_id already exists for another successful payment.",
            }, status.HTTP_409_CONFLICT

        outstanding = _participant_amount_remaining(participant)
        if outstanding <= Decimal("0"):
            return {
                "message": "Participant has no outstanding balance.",
            }, status.HTTP_409_CONFLICT

        apply_amount = _decimal(payment.amount)
        if apply_amount > outstanding:
            apply_amount = outstanding

        payment.status = GroupPayment.STATUS_SUCCESS
        payment.completed_at = now
        payment.transaction_id = transaction_id
        payment.provider_reference = provider_reference
        payment.metadata = _update_metadata(
            payment.metadata,
            {
                "completion_status": "SUCCESS",
                "completed_at": now.isoformat(),
                "applied_amount": float(apply_amount),
                **extra_metadata,
            },
        )
        payment.save(
            update_fields=[
                "status",
                "completed_at",
                "transaction_id",
                "provider_reference",
                "metadata",
            ]
        )

        participant.amount_paid = services._quantize_money(_decimal(participant.amount_paid) + apply_amount)
        participant.payment_status = GroupParticipant.PAYMENT_PENDING
        participant.save(update_fields=["amount_paid", "payment_status"])
        _update_participant_payment_state(participant)

        _sync_session_paid_amount(session)

        active_participants = _active_participants(session, lock=True)
        readiness = _session_readiness(session, active_participants)

        confirmation_payload = None
        if readiness.get("ready"):
            confirmation_payload = _confirm_group_session_locked(session)
        else:
            session.status = GroupBookingSession.STATUS_PARTIALLY_PAID
            session.save(update_fields=["status", "updated_at"])

        session_payload = _serialize_session(session, viewer_id=customer.id)

    return {
        "message": "Payment processed successfully.",
        "payment": {
            "id": payment.id,
            "status": payment.status,
            "amount": _float_money(payment.amount),
            "transaction_id": payment.transaction_id,
            "provider_reference": payment.provider_reference,
        },
        "session": session_payload,
        "confirmation": confirmation_payload,
    }, status.HTTP_200_OK


def drop_group_participant(request: Any, session_id: int) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupParticipantDropSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid drop-out payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    reason = str(serializer.validated_data.get("reason") or "LEFT_SESSION").strip() or "LEFT_SESSION"

    with transaction.atomic():
        session = _load_session_for_update(session_id=session_id)
        if not session:
            return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

        session_error = _can_mutate_open_session(session)
        if session_error:
            return session_error

        participant = GroupParticipant.objects.select_for_update().filter(
            session=session,
            user=customer,
            left_at__isnull=True,
        ).first()
        if not participant:
            return {
                "message": "You are not an active participant of this session.",
            }, status.HTTP_404_NOT_FOUND

        if participant.is_host:
            return {
                "message": "Host cannot drop out. Host should cancel the session instead.",
            }, status.HTTP_400_BAD_REQUEST

        if _decimal(participant.amount_paid) > Decimal("0"):
            return {
                "message": "Cannot drop out after payment has started.",
            }, status.HTTP_409_CONFLICT

        if GroupPayment.objects.filter(session=session, status=GroupPayment.STATUS_SUCCESS).exists():
            return {
                "message": "Cannot drop out after successful payments have started in this session.",
            }, status.HTTP_409_CONFLICT

        participant.left_at = timezone.now()
        participant.payment_status = GroupParticipant.PAYMENT_LEFT
        participant.selected_seats = []
        participant.metadata = _update_metadata(
            participant.metadata,
            {
                "left_reason": reason,
                "left_at": participant.left_at.isoformat(),
            },
        )
        participant.save(update_fields=["left_at", "payment_status", "selected_seats", "metadata"])

        _refresh_split(session)
        _sync_session_paid_amount(session)

        active_count = GroupParticipant.objects.filter(session=session, left_at__isnull=True).count()
        if active_count <= 0:
            _expire_or_cancel_session_locked(
                session,
                new_status=GroupBookingSession.STATUS_CANCELLED,
                reason="ALL_PARTICIPANTS_LEFT",
            )

        session_payload = _serialize_session(session, viewer_id=customer.id)

    return {
        "message": "You left the group booking session.",
        "session": session_payload,
    }, status.HTTP_200_OK


def cancel_group_booking_session(request: Any, session_id: int) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    payload = get_payload(request)
    serializer = GroupSessionCancelSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid cancel payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    reason = str(serializer.validated_data.get("reason") or "HOST_CANCELLED").strip() or "HOST_CANCELLED"

    with transaction.atomic():
        session = _load_session_for_update(session_id=session_id)
        if not session:
            return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

        if session.host_id != customer.id:
            return {
                "message": "Only host can cancel this session.",
            }, status.HTTP_403_FORBIDDEN

        if session.status in {
            GroupBookingSession.STATUS_CANCELLED,
            GroupBookingSession.STATUS_EXPIRED,
            GroupBookingSession.STATUS_COMPLETED,
        }:
            return {
                "message": f"Session is already closed with status {session.status}.",
                "session": _serialize_session(session, viewer_id=customer.id),
            }, status.HTTP_200_OK

        _expire_or_cancel_session_locked(
            session,
            new_status=GroupBookingSession.STATUS_CANCELLED,
            reason=reason,
        )

        session_payload = _serialize_session(session, viewer_id=customer.id)

    return {
        "message": "Group booking session cancelled.",
        "session": session_payload,
    }, status.HTTP_200_OK


def get_group_booking_session_by_id(request: Any, session_id: int) -> tuple[dict[str, Any], int]:
    customer, error_payload, status_code = _resolve_customer_request(request)
    if error_payload:
        return error_payload, status_code

    services.enqueue_stale_pending_cleanup_job(
        metadata={
            "source": "group_booking_by_id",
            "user_id": customer.id,
            "session_id": session_id,
        }
    )
    session = _session_query_for_read().filter(id=session_id).first()
    if not session:
        return {"message": "Group booking session not found."}, status.HTTP_404_NOT_FOUND

    if session.host_id != customer.id and not session.participants.filter(user_id=customer.id).exists():
        return {
            "message": "You do not have access to this group booking session.",
        }, status.HTTP_403_FORBIDDEN

    return {
        "session": _serialize_session(session, viewer_id=customer.id),
    }, status.HTTP_200_OK
