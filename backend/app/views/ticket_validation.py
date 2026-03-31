"""Vendor ticket validation and fraud monitoring API views."""

from __future__ import annotations

from typing import Any

from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import Ticket, TicketValidationScan
from ..permissions import resolve_vendor, vendor_required


def _extract_client_ip(request: Any) -> str | None:
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    remote_addr = str(request.META.get("REMOTE_ADDR") or "").strip()
    return remote_addr or None


def _build_scan_payload(scan: TicketValidationScan) -> dict[str, Any]:
    return {
        "id": scan.id,
        "reference": scan.reference,
        "status": scan.status,
        "reason": scan.reason,
        "fraudScore": int(scan.fraud_score or 0),
        "ticketId": scan.ticket_id,
        "bookingId": scan.booking_id,
        "vendorId": scan.vendor_id,
        "scannedBy": scan.scanned_by_id,
        "sourceIp": scan.source_ip,
        "scannedAt": scan.scanned_at.isoformat() if scan.scanned_at else None,
    }


def _resolve_vendor_from_ticket(ticket: Ticket):
    payload = ticket.payload if isinstance(ticket.payload, dict) else {}

    booking_payload = payload.get("booking") if isinstance(payload.get("booking"), dict) else {}
    movie_payload = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}

    booking_id = booking_payload.get("booking_id")
    vendor_id = (
        booking_payload.get("vendor_id")
        or movie_payload.get("cinema_id")
        or movie_payload.get("vendor_id")
        or movie_payload.get("cinemaId")
        or movie_payload.get("vendorId")
    )
    return vendor_id, booking_id


@api_view(["POST"])
@vendor_required
def validate_ticket_scan(request: Any):
    """Validate one ticket scan and log fraud/duplicate state."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    reference = str(request.data.get("reference") or "").strip().upper()
    if not reference:
        return Response({"message": "reference is required."}, status=status.HTTP_400_BAD_REQUEST)

    ticket = Ticket.objects.filter(reference__iexact=reference).first()
    source_ip = _extract_client_ip(request)
    user_agent = str(request.META.get("HTTP_USER_AGENT") or "").strip()[:255] or None

    if not ticket:
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=None,
            booking=None,
            vendor=vendor,
            scanned_by=vendor,
            status=TicketValidationScan.STATUS_INVALID,
            reason="Ticket reference not found.",
            fraud_score=90,
            source_ip=source_ip,
            user_agent=user_agent,
        )
        return Response(
            {
                "message": "Invalid ticket.",
                "alert": "fraud_suspected",
                "scan": _build_scan_payload(scan),
            },
            status=status.HTTP_200_OK,
        )

    ticket_vendor_id, booking_id = _resolve_vendor_from_ticket(ticket)

    if str(ticket_vendor_id or "") != str(vendor.id):
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=ticket,
            booking_id=booking_id,
            vendor=vendor,
            scanned_by=vendor,
            status=TicketValidationScan.STATUS_FRAUD,
            reason="Ticket does not belong to this vendor.",
            fraud_score=100,
            source_ip=source_ip,
            user_agent=user_agent,
        )
        return Response(
            {
                "message": "Fraud alert: ticket belongs to another vendor.",
                "alert": "fraud_suspected",
                "scan": _build_scan_payload(scan),
            },
            status=status.HTTP_200_OK,
        )

    prior_scans = TicketValidationScan.objects.filter(
        ticket=ticket,
        vendor=vendor,
        status__in=[TicketValidationScan.STATUS_VALID, TicketValidationScan.STATUS_DUPLICATE],
    ).count()

    if prior_scans > 0:
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=ticket,
            booking_id=booking_id,
            vendor=vendor,
            scanned_by=vendor,
            status=TicketValidationScan.STATUS_DUPLICATE,
            reason="Ticket already scanned.",
            fraud_score=min(100, 50 + (prior_scans * 10)),
            source_ip=source_ip,
            user_agent=user_agent,
        )
        return Response(
            {
                "message": "Duplicate ticket scan detected.",
                "alert": "duplicate_ticket",
                "scan": _build_scan_payload(scan),
            },
            status=status.HTTP_200_OK,
        )

    scan = TicketValidationScan.objects.create(
        reference=reference,
        ticket=ticket,
        booking_id=booking_id,
        vendor=vendor,
        scanned_by=vendor,
        status=TicketValidationScan.STATUS_VALID,
        reason="Ticket is valid.",
        fraud_score=0,
        source_ip=source_ip,
        user_agent=user_agent,
    )

    return Response(
        {
            "message": "Ticket validated successfully.",
            "alert": "none",
            "scan": _build_scan_payload(scan),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@vendor_required
def vendor_ticket_validation_monitor(request: Any):
    """Return ticket scan logs + fraud/duplicate metrics for vendor monitoring."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor access required."}, status=status.HTTP_403_FORBIDDEN)

    status_filter = str(request.query_params.get("status") or "").strip().upper()
    reference = str(request.query_params.get("reference") or "").strip().upper()
    try:
        limit = int(request.query_params.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    queryset = TicketValidationScan.objects.filter(vendor=vendor).select_related("ticket", "booking")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if reference:
        queryset = queryset.filter(reference__icontains=reference)

    scans = list(queryset.order_by("-id")[:limit])

    counts = TicketValidationScan.objects.filter(vendor=vendor).values("status").annotate(total=Count("id"))
    summary = {
        "valid": 0,
        "duplicate": 0,
        "invalid": 0,
        "fraud": 0,
        "total": 0,
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

    alerts = [
        {
            "type": "duplicate_ticket",
            "count": summary["duplicate"],
        },
        {
            "type": "fraud_suspected",
            "count": summary["fraud"] + summary["invalid"],
        },
    ]

    return Response(
        {
            "summary": summary,
            "alerts": alerts,
            "scans": [_build_scan_payload(scan) for scan in scans],
        },
        status=status.HTTP_200_OK,
    )
