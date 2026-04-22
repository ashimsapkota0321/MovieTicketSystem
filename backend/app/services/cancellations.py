"""Cancellation and refund service helpers."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from .. import loyalty, subscription
from ..models import (
    Booking,
    BookingSeat,
    Notification,
    Payment,
    Refund,
    RefundLedger,
    SeatAvailability,
    Vendor,
    VendorCancellationPolicy,
)
from ..utils import coalesce, get_payload
from .notifications import (
    _build_booking_notification_metadata,
    _notify_customer_booking_cancelled,
    _notify_customer_cancel_request_rejected,
    _notify_customer_cancel_request_submitted,
    _notify_customer_refund_result,
    _notify_vendor_cancel_request,
)

DEFAULT_REFUND_PERCENT_2H_PLUS = Decimal("100.00")
DEFAULT_REFUND_PERCENT_1_TO_2H = Decimal("70.00")
DEFAULT_REFUND_PERCENT_LESS_THAN_1H = Decimal("0.00")
BOOKING_STATUS_CANCELLED = Booking.Status.CANCELLED
PAYMENT_STATUS_REFUNDED = Payment.Status.REFUNDED
PAYMENT_STATUS_PARTIALLY_REFUNDED = Payment.Status.PARTIALLY_REFUNDED
REFUND_STATUS_COMPLETED = Refund.Status.COMPLETED


def _quantize_money(value: Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _percent_decimal(value: Any, default: Decimal) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception:
        parsed = default
    return max(Decimal("0"), min(parsed, Decimal("100"))).quantize(Decimal("0.01"))


def _default_cancellation_policy_payload(
    vendor: Optional[Vendor] = None,
    screen: Optional[Any] = None,
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
            _percent_decimal(policy.refund_percent_less_than_1h, DEFAULT_REFUND_PERCENT_LESS_THAN_1H)
        ),
        "note": policy.note,
        "is_default": policy.screen_id is None,
        "source": "VENDOR_POLICY",
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def _resolve_cancellation_policy_for_booking(booking: Booking) -> dict[str, Any]:
    showtime = booking.showtime
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    if not vendor:
        payload = _default_cancellation_policy_payload()
        payload["allow_customer_cancellation"] = False
        payload["is_active"] = False
        payload["source"] = "UNSCOPED"
        return payload

    scoped = VendorCancellationPolicy.objects.filter(vendor_id=vendor.id, is_active=True)
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


def _get_latest_payment_for_booking(booking: Booking) -> Optional[Payment]:
    if not booking:
        return None
    return booking.payments.all().order_by("-payment_date", "-id").first()


def _get_booking_or_none(booking_id: int) -> Optional[Booking]:
    if booking_id <= 0:
        return None
    return Booking.objects.select_related(
        "user",
        "showtime__movie",
        "showtime__screen__vendor",
    ).prefetch_related("booking_seats__seat", "payments__refunds").filter(pk=booking_id).first()


def _booking_amount_for_refund(booking: Booking, latest_payment: Optional[Payment] = None) -> Decimal:
    amount = _quantize_money(booking.total_amount or Decimal("0"))
    if amount <= Decimal("0") and latest_payment:
        amount = _quantize_money(latest_payment.amount or Decimal("0"))
    return amount


def _has_successful_payment(latest_payment: Optional[Payment]) -> bool:
    if not latest_payment:
        return False
    status_value = str(getattr(latest_payment, "payment_status", "") or "").strip().upper()
    return status_value in {
        "SUCCESS",
        "PAID",
        "CONFIRMED",
        "COMPLETED",
        PAYMENT_STATUS_REFUNDED,
        PAYMENT_STATUS_PARTIALLY_REFUNDED,
    }


def _compute_booking_cancellation_quote(
    booking: Booking,
    latest_payment: Optional[Payment] = None,
) -> dict[str, Any]:
    policy = _resolve_cancellation_policy_for_booking(booking)
    showtime = booking.showtime
    payment_status = getattr(latest_payment, "payment_status", None)
    has_successful_payment = _has_successful_payment(latest_payment)
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
            "payment_status": payment_status,
            "has_successful_payment": has_successful_payment,
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
            "payment_status": payment_status,
            "has_successful_payment": has_successful_payment,
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
            "payment_status": payment_status,
            "has_successful_payment": has_successful_payment,
            "policy": policy,
        }

    if hours_until_show < 1:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Cancellation is only allowed at least 1 hour before showtime.",
            "hours_until_show": round(hours_until_show, 2),
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "payment_status": payment_status,
            "has_successful_payment": has_successful_payment,
            "policy": policy,
        }

    if not has_successful_payment:
        return {
            "is_cancellable": True,
            "is_refund_available": False,
            "reason": None,
            "hours_until_show": round(hours_until_show, 2),
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": 0.0,
            "amount_basis": 0.0,
            "payment_status": payment_status,
            "has_successful_payment": False,
            "policy": policy,
        }

    if hours_until_show >= 2:
        percent = _percent_decimal(policy.get("refund_percent_2h_plus"), DEFAULT_REFUND_PERCENT_2H_PLUS)
    elif hours_until_show >= 1:
        percent = _percent_decimal(policy.get("refund_percent_1_to_2h"), DEFAULT_REFUND_PERCENT_1_TO_2H)
    else:
        percent = _percent_decimal(policy.get("refund_percent_less_than_1h"), DEFAULT_REFUND_PERCENT_LESS_THAN_1H)

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
        "payment_status": payment_status,
        "has_successful_payment": True,
        "policy": policy,
    }


def _latest_cancel_request_status(booking: Booking) -> Optional[str]:
    latest = (
        Notification.objects.filter(
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=booking.id,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if not latest:
        return None
    return str((latest.metadata or {}).get("request_status") or "").upper() or None


def _release_booking_seats(booking: Booking) -> None:
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
            seat_status="Available",
            locked_until=None,
        )


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


def _apply_booking_cancellation_with_policy(
    request: Any,
    booking: Booking,
    *,
    actor_label: str,
    require_policy_eligibility: bool,
    require_payment_for_refund: bool = False,
    close_pending_cancel_requests: bool = False,
) -> tuple[dict[str, Any], int]:
    latest_payment = booking.payments.all().order_by("-payment_date", "-id").first()

    from . import build_booking_payload
    from . import _credit_user_wallet_for_booking_refund
    from . import _get_booking_or_none
    from . import _reverse_vendor_booking_earning
    from . import reverse_referral_effects_for_booking

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

    reason_value = str(coalesce(get_payload(request), "reason", "refund_reason", "cancellation_reason") or "").strip()
    reason = reason_value or f"Cancelled by {actor_label}"
    refund_amount = _quantize_money(quote.get("refund_amount") or Decimal("0"))

    with transaction.atomic():
        created_refund: Optional[Refund] = None
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
            if locked_refund and str(locked_refund.refund_status).strip().upper() == REFUND_STATUS_COMPLETED:
                refund_amount = Decimal("0")
            elif refund_amount > Decimal("0"):
                created_refund = Refund.objects.create(
                    payment=locked_payment,
                    refund_amount=refund_amount,
                    refund_reason=reason,
                    refund_status=REFUND_STATUS_COMPLETED,
                )
                refund_vendor = None
                if locked_booking.showtime and locked_booking.showtime.screen:
                    refund_vendor = locked_booking.showtime.screen.vendor
                if refund_vendor:
                    RefundLedger.objects.create(
                        payment=locked_payment,
                        refund=created_refund,
                        booking=locked_booking,
                        vendor=refund_vendor,
                        status=RefundLedger.STATUS_COMPLETED,
                        amount=refund_amount,
                        gross_amount=_quantize_money(locked_payment.amount or Decimal("0")),
                        refund_reason=reason,
                        metadata={"source": "booking_refund"},
                    )
                full_amount = _quantize_money(locked_payment.amount or Decimal("0"))
                if refund_amount >= full_amount:
                    locked_payment.payment_status = PAYMENT_STATUS_REFUNDED
                else:
                    locked_payment.payment_status = PAYMENT_STATUS_PARTIALLY_REFUNDED
                locked_payment.save(update_fields=["payment_status"])

        locked_booking.booking_status = BOOKING_STATUS_CANCELLED
        locked_booking.save(update_fields=["booking_status"])
        _release_booking_seats(locked_booking)
        loyalty.reverse_booking_points(locked_booking, reason=reason)
        subscription.reverse_booking_subscription_effects(locked_booking, reason=reason)
        reverse_referral_effects_for_booking(locked_booking, reason=reason)

        if close_pending_cancel_requests:
            _close_cancel_request_notifications(
                locked_booking,
                resolved_by=actor_label,
                resolved_status="APPROVED",
            )

        if refund_amount > Decimal("0") and created_refund:
            _credit_user_wallet_for_booking_refund(
                booking=locked_booking,
                amount=refund_amount,
                refund=created_refund,
                reason=reason,
                source=f"{actor_label}_booking_refund",
            )
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
    if str(booking.booking_status).lower() == "cancelled":
        from . import build_booking_payload

        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    latest_payment = _get_latest_payment_for_booking(booking)
    quote = _compute_booking_cancellation_quote(booking, latest_payment=latest_payment)
    from . import build_booking_payload

    showtime = booking.showtime
    if not showtime or not showtime.start_time:
        return {
            "message": "Show time is unavailable.",
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST
    if not quote.get("is_cancellable"):
        return {
            "message": str(quote.get("reason") or "Cancellation is not allowed for this booking."),
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    vendor = _get_booking_vendor(booking)
    if not vendor:
        return {"message": "Vendor not found for booking."}, status.HTTP_400_BAD_REQUEST

    payload = get_payload(request)
    reason = str(coalesce(payload, "reason", "refund_reason", "cancellation_reason") or "").strip() or None

    existing = _find_pending_cancel_request_notification(booking, vendor)
    if existing:
        metadata = dict(existing.metadata or {})
        metadata["request_status"] = "PENDING"
        metadata["reminded_at"] = timezone.now().isoformat()
        if reason:
            metadata["requested_reason"] = reason
        existing.metadata = metadata

        update_fields = ["metadata"]
        if bool(existing.is_read):
            existing.is_read = False
            existing.read_at = None
            update_fields.extend(["is_read", "read_at"])
        existing.save(update_fields=update_fields)

        return {
            "message": "Cancellation request is already pending vendor approval.",
            "request_id": existing.id,
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

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
    vendor = _get_booking_vendor(booking)
    if not vendor:
        return {"message": "Vendor not found for booking."}, status.HTTP_400_BAD_REQUEST

    payload = get_payload(request)
    action = str(coalesce(payload, "action", "decision") or "APPROVE").strip().upper()
    reason = str(coalesce(payload, "reason", "refund_reason", "cancellation_reason") or "").strip() or None

    pending_request = _find_pending_cancel_request_notification(booking, vendor)
    if not pending_request:
        from . import build_booking_payload

        return {
            "message": "No pending cancellation request found for this booking.",
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    if action == "REJECT":
        _close_cancel_request_notifications(
            booking,
            resolved_by="vendor",
            resolved_status="REJECTED",
        )
        _notify_customer_cancel_request_rejected(
            booking,
            resolved_by="vendor",
            reason=reason,
        )
        from . import build_booking_payload

        return {
            "message": "Cancellation request rejected.",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    return _apply_booking_cancellation_with_policy(
        request,
        booking,
        actor_label="vendor",
        require_policy_eligibility=False,
        require_payment_for_refund=False,
        close_pending_cancel_requests=True,
    )


def vendor_refund_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    return _apply_booking_cancellation_with_policy(
        request,
        booking,
        actor_label="vendor",
        require_policy_eligibility=False,
        require_payment_for_refund=True,
        close_pending_cancel_requests=True,
    )


def admin_cancel_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    from . import build_booking_payload
    from . import reverse_referral_effects_for_booking

    if str(booking.booking_status).strip().upper() == BOOKING_STATUS_CANCELLED:
        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    payload = get_payload(request)
    reason = str(coalesce(payload, "reason", "cancellation_reason") or "").strip() or "Cancelled by admin"

    with transaction.atomic():
        booking.booking_status = BOOKING_STATUS_CANCELLED
        booking.save(update_fields=["booking_status"])
        _release_booking_seats(booking)
        loyalty.reverse_booking_points(booking, reason=reason)
        subscription.reverse_booking_subscription_effects(booking, reason=reason)
        reverse_referral_effects_for_booking(booking, reason=reason)

    refreshed = _get_booking_or_none(booking.id) or booking
    _notify_customer_booking_cancelled(
        refreshed,
        actor_label="admin",
        reason=reason,
    )

    return {
        "message": "Booking cancelled",
        "booking": build_booking_payload(refreshed),
    }, status.HTTP_200_OK


def admin_refund_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    from . import build_booking_payload
    from . import _credit_user_wallet_for_booking_refund
    from . import _get_booking_or_none
    from . import _reverse_vendor_booking_earning
    from . import reverse_referral_effects_for_booking

    latest_payment = booking.payments.all().order_by("-payment_date", "-id").first()
    if not latest_payment:
        return {"message": "Payment record not found for booking."}, status.HTTP_404_NOT_FOUND

    latest_refund = latest_payment.refunds.all().order_by("-refund_date", "-id").first()
    if latest_refund and str(latest_refund.refund_status).strip().upper() == REFUND_STATUS_COMPLETED:
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
    refund_amount = _quantize_money(Decimal(str(amount)))
    basis_amount = _quantize_money(Decimal(str(latest_payment.amount or 0)))
    actor_reason = reason or "Admin refund"

    with transaction.atomic():
        created_refund = Refund.objects.create(
            payment=latest_payment,
            refund_amount=refund_amount,
            refund_reason=reason,
            refund_status=REFUND_STATUS_COMPLETED,
        )
        refund_vendor = None
        if booking.showtime and booking.showtime.screen:
            refund_vendor = booking.showtime.screen.vendor
        if refund_vendor:
            RefundLedger.objects.create(
                payment=latest_payment,
                refund=created_refund,
                booking=booking,
                vendor=refund_vendor,
                status=RefundLedger.STATUS_COMPLETED,
                amount=refund_amount,
                gross_amount=basis_amount,
                refund_reason=reason,
                metadata={"source": "admin_booking_refund"},
            )
        latest_payment.payment_status = PAYMENT_STATUS_REFUNDED
        latest_payment.save(update_fields=["payment_status"])
        booking.booking_status = BOOKING_STATUS_CANCELLED
        booking.save(update_fields=["booking_status"])
        _release_booking_seats(booking)
        loyalty.reverse_booking_points(booking, reason=actor_reason)
        subscription.reverse_booking_subscription_effects(booking, reason=actor_reason)
        reverse_referral_effects_for_booking(booking, reason=actor_reason)
        if refund_amount > Decimal("0"):
            _credit_user_wallet_for_booking_refund(
                booking=booking,
                amount=refund_amount,
                refund=created_refund,
                reason=actor_reason,
                source="admin_booking_refund",
            )
            _reverse_vendor_booking_earning(booking, reason=actor_reason)

    refreshed = _get_booking_or_none(booking.id) or booking
    _notify_customer_refund_result(
        refreshed,
        quote={
            "amount_basis": float(basis_amount),
            "refund_percent": 0,
            "hours_until_show": None,
            "policy": {"source": "admin_manual_refund"},
        },
        refund_amount=refund_amount,
        actor_label="admin",
        reason=actor_reason,
    )

    return {
        "message": "Booking refunded",
        "booking": build_booking_payload(refreshed),
    }, status.HTTP_200_OK
