"""Service helpers for vendor offer management."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from .models import VendorOffer
from .permissions import resolve_customer, resolve_vendor
from .utils import coalesce, get_payload, parse_bool, parse_datetime_utc

MONEY_QUANTIZER = Decimal("0.01")


def _quantize_money(value: Decimal | int | float | str | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(MONEY_QUANTIZER)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _parse_money(value: Any, *, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value)).quantize(MONEY_QUANTIZER)
    except (InvalidOperation, TypeError, ValueError):
        return default


def _serialize_offer(offer: VendorOffer, *, now: Optional[Any] = None) -> dict[str, Any]:
    current = now or timezone.now()
    is_live_window = True
    if offer.starts_at and offer.starts_at > current:
        is_live_window = False
    if offer.ends_at and offer.ends_at < current:
        is_live_window = False

    return {
        "id": offer.id,
        "vendor_id": offer.vendor_id,
        "vendor_name": getattr(offer.vendor, "name", None),
        "title": offer.title,
        "code": offer.code,
        "description": offer.description,
        "offer_type": offer.offer_type,
        "discount_type": offer.discount_type,
        "discount_value": float(_quantize_money(offer.discount_value)),
        "min_booking_amount": float(_quantize_money(offer.min_booking_amount)),
        "allow_loyalty_redemption": bool(offer.allow_loyalty_redemption),
        "subscriber_perk_text": offer.subscriber_perk_text,
        "starts_at": offer.starts_at.isoformat() if offer.starts_at else None,
        "ends_at": offer.ends_at.isoformat() if offer.ends_at else None,
        "is_active": bool(offer.is_active),
        "is_live": bool(offer.is_active and is_live_window),
        "metadata": offer.metadata if isinstance(offer.metadata, dict) else {},
        "created_at": offer.created_at.isoformat() if offer.created_at else None,
        "updated_at": offer.updated_at.isoformat() if offer.updated_at else None,
    }


def _normalize_offer_payload(payload: dict[str, Any], *, partial: bool) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    normalized: dict[str, Any] = {}

    if not partial or "title" in payload:
        title = str(payload.get("title") or "").strip()
        if not title:
            return None, "title is required."
        normalized["title"] = title[:140]

    if "code" in payload:
        code_raw = payload.get("code")
        if code_raw in (None, ""):
            normalized["code"] = None
        else:
            normalized["code"] = str(code_raw).strip().upper()[:50]

    if "description" in payload:
        description = payload.get("description")
        normalized["description"] = str(description).strip() if description not in (None, "") else None

    if "offer_type" in payload:
        offer_type = str(payload.get("offer_type") or "").strip().upper()
        allowed = {choice[0] for choice in VendorOffer.OFFER_TYPE_CHOICES}
        if offer_type not in allowed:
            return None, f"offer_type must be one of: {', '.join(sorted(allowed))}."
        normalized["offer_type"] = offer_type

    if "discount_type" in payload:
        discount_type = str(payload.get("discount_type") or "").strip().upper()
        allowed = {choice[0] for choice in VendorOffer.DISCOUNT_TYPE_CHOICES}
        if discount_type not in allowed:
            return None, f"discount_type must be one of: {', '.join(sorted(allowed))}."
        normalized["discount_type"] = discount_type

    if "discount_value" in payload:
        discount_value = _parse_money(payload.get("discount_value"))
        if discount_value is None or discount_value < Decimal("0"):
            return None, "discount_value must be a non-negative number."
        normalized["discount_value"] = discount_value

    if "min_booking_amount" in payload:
        min_booking_amount = _parse_money(payload.get("min_booking_amount"))
        if min_booking_amount is None or min_booking_amount < Decimal("0"):
            return None, "min_booking_amount must be a non-negative number."
        normalized["min_booking_amount"] = min_booking_amount

    if "allow_loyalty_redemption" in payload:
        normalized["allow_loyalty_redemption"] = parse_bool(
            payload.get("allow_loyalty_redemption"),
            default=True,
        )

    if "subscriber_perk_text" in payload:
        text = payload.get("subscriber_perk_text")
        normalized["subscriber_perk_text"] = str(text).strip()[:200] if text not in (None, "") else None

    starts_key = "starts_at" in payload
    ends_key = "ends_at" in payload
    starts_at = parse_datetime_utc(payload.get("starts_at")) if starts_key else None
    ends_at = parse_datetime_utc(payload.get("ends_at")) if ends_key else None
    if starts_key and payload.get("starts_at") not in (None, "") and starts_at is None:
        return None, "starts_at must be a valid ISO datetime."
    if ends_key and payload.get("ends_at") not in (None, "") and ends_at is None:
        return None, "ends_at must be a valid ISO datetime."
    if starts_key:
        normalized["starts_at"] = starts_at
    if ends_key:
        normalized["ends_at"] = ends_at

    if "is_active" in payload:
        normalized["is_active"] = parse_bool(payload.get("is_active"), default=True)

    if "metadata" in payload:
        metadata = payload.get("metadata")
        if metadata in (None, ""):
            normalized["metadata"] = {}
        elif isinstance(metadata, dict):
            normalized["metadata"] = metadata
        else:
            return None, "metadata must be a JSON object."

    return normalized, None


def list_vendor_offers(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    include_inactive = parse_bool(
        coalesce(request.query_params, "include_inactive", "includeInactive"),
        default=False,
    )
    queryset = VendorOffer.objects.select_related("vendor").filter(vendor_id=vendor.id)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)

    offers = queryset.order_by("-created_at", "-id")
    return {
        "offers": [_serialize_offer(item) for item in offers],
        "count": len(offers),
    }, status.HTTP_200_OK


def create_vendor_offer(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    normalized, error = _normalize_offer_payload(payload, partial=False)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    try:
        offer = VendorOffer.objects.create(vendor=vendor, **(normalized or {}))
    except ValidationError as exc:
        return {
            "message": "Invalid offer payload.",
            "errors": exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)},
        }, status.HTTP_400_BAD_REQUEST

    return {
        "message": "Offer created.",
        "offer": _serialize_offer(offer),
    }, status.HTTP_201_CREATED


def update_vendor_offer(request: Any, offer: VendorOffer) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    normalized, error = _normalize_offer_payload(payload, partial=True)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    for key, value in (normalized or {}).items():
        setattr(offer, key, value)

    try:
        offer.save()
    except ValidationError as exc:
        return {
            "message": "Invalid offer payload.",
            "errors": exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)},
        }, status.HTTP_400_BAD_REQUEST

    return {
        "message": "Offer updated.",
        "offer": _serialize_offer(offer),
    }, status.HTTP_200_OK


def delete_vendor_offer(offer: VendorOffer) -> tuple[dict[str, Any], int]:
    offer.is_active = False
    offer.save(update_fields=["is_active", "updated_at"])
    return {"message": "Offer disabled."}, status.HTTP_200_OK


def list_offers_for_customer(request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    if not user:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    vendor_id_raw = coalesce(request.query_params, "vendor_id", "vendorId")
    vendor_id = None
    if vendor_id_raw not in (None, ""):
        try:
            vendor_id = int(vendor_id_raw)
        except (TypeError, ValueError):
            return {"message": "vendor_id must be a valid integer."}, status.HTTP_400_BAD_REQUEST

    now = timezone.now()
    queryset = VendorOffer.objects.select_related("vendor").filter(
        is_active=True,
    ).filter(
        (Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        & (Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )
    if vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

    offers = queryset.order_by("-created_at", "-id")
    return {
        "offers": [_serialize_offer(item, now=now) for item in offers],
        "count": len(offers),
    }, status.HTTP_200_OK
