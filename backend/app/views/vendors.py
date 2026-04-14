"""Vendor and cinema listing API views."""

from __future__ import annotations

from typing import Any

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import services
from ..models import (
    BulkTicketBatch,
    PricingRule,
    PrivateScreeningRequest,
    Transaction,
    VendorCampaign,
    VendorPromoCode,
    VendorStaff,
)
from ..permissions import admin_required, vendor_required, resolve_vendor, is_vendor_owner
from ..revenue_serializers import RevenueConfigUpdateSerializer
from ..utils import coalesce


@api_view(["GET", "POST"])
@admin_required
def manage_vendors(request: Any):
    """List vendors or create a vendor account."""
    if request.method == "GET":
        vendors = services.list_vendors_payload(request)
        return Response({"vendors": vendors}, status=status.HTTP_200_OK)

    payload, status_code = services.create_vendor(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
def list_cinemas(request: Any):
    """Return cinema vendors for public listings."""
    city = coalesce(request.query_params, "city", "location")
    payload = services.list_cinemas_payload(request, city=city)
    return Response({"vendors": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
@vendor_required
def vendor_analytics(request: Any):
    """Get vendor analytics dashboard data."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response(
            {"error": "Vendor not found", "message": "Unable to identify vendor"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    analytics_data = services.get_vendor_analytics(vendor, request)
    return Response(analytics_data, status=status.HTTP_200_OK)


@api_view(["GET"])
@vendor_required
def vendor_revenue_analytics(request: Any):
    """Get vendor revenue analytics (daily/weekly/monthly + chart-ready)."""
    payload, status_code = services.get_vendor_revenue_analytics(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@vendor_required
def vendor_revenue_transactions(request: Any):
    """Get vendor revenue transaction history."""
    payload, status_code = services.list_vendor_revenue_transactions(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@vendor_required
def vendor_revenue_report(request: Any):
    """Get vendor revenue report grouped per show with date-range filter."""
    payload, status_code = services.get_vendor_revenue_report(request)
    return Response(payload, status=status_code)


@api_view(["GET", "PATCH"])
@admin_required
def admin_revenue_config(request: Any):
    """Get or update platform commission configuration."""
    if request.method == "GET":
        payload, status_code = services.get_admin_revenue_config(request)
        return Response(payload, status=status_code)

    serializer = RevenueConfigUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({"message": "Invalid payload.", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    payload, status_code = services.update_admin_revenue_config(request, payload_override=serializer.validated_data)
    return Response(payload, status=status_code)


@api_view(["GET"])
@admin_required
def admin_revenue_analytics(request: Any):
    """Get admin revenue analytics (overall platform + top vendors + charts)."""
    payload, status_code = services.get_admin_revenue_analytics(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@admin_required
def admin_revenue_transactions(request: Any):
    """Get admin commission transaction history."""
    payload, status_code = services.list_admin_revenue_transactions(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@admin_required
def admin_revenue_report(request: Any):
    """Get admin report grouped by vendor and show with date-range filter."""
    payload, status_code = services.get_admin_revenue_report(request)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_pricing_rules(request: Any):
    """List or create vendor pricing rules for dynamic ticket pricing."""
    if request.method == "GET":
        rules = services.list_vendor_pricing_rules(request)
        return Response({"rules": rules}, status=status.HTTP_200_OK)

    payload, status_code = services.create_vendor_pricing_rule(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_pricing_rule_detail(request: Any, rule_id: int):
    """Update or delete a single vendor pricing rule."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response(
            {"error": "Vendor not found", "message": "Unable to identify vendor"},
            status=status.HTTP_404_NOT_FOUND,
        )

    rule = PricingRule.objects.filter(id=rule_id, vendor_id=vendor.id).first()
    if not rule:
        return Response({"message": "Pricing rule not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = services.update_vendor_pricing_rule(request, rule)
        return Response(payload, status=status_code)

    payload, status_code = services.delete_vendor_pricing_rule(rule)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@admin_required
def admin_pricing_rules(request: Any):
    """List or create pricing rules (global and vendor-scoped) for admin."""
    if request.method == "GET":
        payload, status_code = services.list_admin_pricing_rules(request)
        return Response(payload, status=status_code)

    payload, status_code = services.create_admin_pricing_rule(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@admin_required
def admin_pricing_rule_detail(request: Any, rule_id: int):
    """Update or delete one pricing rule as admin."""
    rule = PricingRule.objects.filter(id=rule_id).first()
    if not rule:
        return Response({"message": "Pricing rule not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = services.update_admin_pricing_rule(request, rule)
        return Response(payload, status=status_code)

    payload, status_code = services.delete_admin_pricing_rule(rule)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_show_base_prices(request: Any):
    """List or upsert per-show base prices for vendor dynamic pricing engine."""
    if request.method == "GET":
        payload, status_code = services.list_vendor_show_base_prices(request)
        return Response(payload, status=status_code)

    payload, status_code = services.upsert_vendor_show_base_prices(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@vendor_required
def vendor_wallet_balance(request: Any):
    """Get authenticated vendor wallet summary and balance."""
    payload, status_code = services.get_vendor_wallet_balance(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@vendor_required
def vendor_wallet_withdraw(request: Any):
    """Create a vendor withdrawal request."""
    payload, status_code = services.create_vendor_withdrawal_request(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@vendor_required
def vendor_payout_profile(request: Any):
    """Create or update the vendor payout destination and payout policy."""
    payload, status_code = services.update_vendor_payout_profile(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@vendor_required
def vendor_payout_profile_request_verification(request: Any):
    """Request an OTP to verify the vendor payout destination."""
    payload, status_code = services.request_vendor_payout_destination_verification(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@vendor_required
def vendor_payout_profile_verify(request: Any):
    """Verify the vendor payout destination using an OTP."""
    payload, status_code = services.verify_vendor_payout_destination(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@vendor_required
def vendor_wallet_transactions(request: Any):
    """List vendor wallet transactions."""
    payload, status_code = services.list_vendor_wallet_transactions(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@admin_required
def admin_withdrawal_requests(request: Any):
    """List withdrawal requests for admin review."""
    payload, status_code = services.list_admin_withdrawal_requests(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
@admin_required
def admin_withdrawal_approve(request: Any, transaction_id: int):
    """Approve one pending withdrawal request."""
    withdrawal_txn = Transaction.objects.filter(id=transaction_id).first()
    if not withdrawal_txn:
        return Response({"message": "Withdrawal request not found."}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.approve_admin_withdrawal_request(request, withdrawal_txn)
    return Response(payload, status=status_code)


@api_view(["POST"])
@admin_required
def admin_withdrawal_reject(request: Any, transaction_id: int):
    """Reject one pending withdrawal request."""
    withdrawal_txn = Transaction.objects.filter(id=transaction_id).first()
    if not withdrawal_txn:
        return Response({"message": "Withdrawal request not found."}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.reject_admin_withdrawal_request(request, withdrawal_txn)
    return Response(payload, status=status_code)


@api_view(["POST"])
@admin_required
def admin_withdrawal_retry(request: Any, transaction_id: int):
    """Retry a failed withdrawal settlement."""
    withdrawal_txn = Transaction.objects.filter(id=transaction_id).first()
    if not withdrawal_txn:
        return Response({"message": "Withdrawal request not found."}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.retry_failed_withdrawal_settlement(request, withdrawal_txn)
    return Response(payload, status=status_code)


@api_view(["GET", "PATCH"])
@vendor_required
def vendor_cancellation_policy(request: Any):
    """Get or update vendor cancellation policy (default or per screen/hall)."""
    if request.method == "GET":
        payload, status_code = services.get_vendor_cancellation_policy(request)
        return Response(payload, status=status_code)

    payload, status_code = services.update_vendor_cancellation_policy(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
def private_screening_request_submit(request: Any):
    """Submit a private screening quote request."""
    payload, status_code = services.create_private_screening_request(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@vendor_required
def vendor_private_screening_requests(request: Any):
    """List private screening requests assigned to vendor."""
    payload, status_code = services.list_vendor_private_screening_requests(request)
    return Response(payload, status=status_code)


@api_view(["PATCH"])
@vendor_required
def vendor_private_screening_request_detail(request: Any, request_id: int):
    """Update vendor actions for one private screening request."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    screening_request = PrivateScreeningRequest.objects.filter(
        id=request_id,
        vendor_id=vendor.id,
    ).first()
    if not screening_request:
        return Response({"message": "Private screening request not found."}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.update_vendor_private_screening_request(request, screening_request)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_bulk_ticket_batches(request: Any):
    """List or generate bulk ticket batches for vendor."""
    if request.method == "GET":
        payload, status_code = services.list_vendor_bulk_ticket_batches(request)
        return Response(payload, status=status_code)

    payload, status_code = services.create_vendor_bulk_ticket_batch(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
@vendor_required
def vendor_bulk_ticket_batch_export(request: Any, batch_id: int):
    """Export one vendor bulk ticket batch as a downloadable CSV."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    batch = BulkTicketBatch.objects.filter(id=batch_id, vendor_id=vendor.id).first()
    if not batch:
        return Response({"message": "Bulk ticket batch not found."}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.export_vendor_bulk_ticket_batch(request, batch)
    if status_code != status.HTTP_200_OK:
        return Response(payload, status=status_code)

    csv_base64 = payload.get("csv_base64") or ""
    if not csv_base64:
        return Response({"message": "CSV export is empty."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    try:
        import base64

        csv_content = base64.b64decode(csv_base64)
    except Exception:
        return Response({"message": "Failed to decode export file."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    filename = str(payload.get("filename") or f"bulk_tickets_batch_{batch.id}.csv")
    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@api_view(["GET", "POST"])
@vendor_required
def vendor_staff_accounts(request: Any):
    """List or create vendor staff sub-accounts."""
    if not is_vendor_owner(request):
        return Response(
            {"message": "Only vendor admin can manage staff accounts."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        payload, status_code = services.list_vendor_staff_accounts(request)
        return Response(payload, status=status_code)

    payload, status_code = services.create_vendor_staff_account(request)
    return Response(payload, status=status_code)


@api_view(["PATCH"])
@vendor_required
def vendor_staff_account_detail(request: Any, staff_id: int):
    """Update a vendor staff account."""
    if not is_vendor_owner(request):
        return Response(
            {"message": "Only vendor admin can manage staff accounts."},
            status=status.HTTP_403_FORBIDDEN,
        )

    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    staff = VendorStaff.objects.filter(id=staff_id, vendor_id=vendor.id).first()
    if not staff:
        return Response({"message": "Vendor staff account not found."}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.update_vendor_staff_account(request, staff)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_promo_codes(request: Any):
    """List or create vendor-specific promo codes."""
    if request.method == "GET":
        payload, status_code = services.list_vendor_promo_codes(request)
        return Response(payload, status=status_code)

    payload, status_code = services.create_vendor_promo_code(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "DELETE"])
@vendor_required
def vendor_promo_code_detail(request: Any, promo_id: int):
    """Update or delete one vendor promo code."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    promo = VendorPromoCode.objects.filter(id=promo_id, vendor_id=vendor.id).first()
    if not promo:
        return Response({"message": "Vendor promo code not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = services.update_vendor_promo_code(request, promo)
        return Response(payload, status=status_code)

    payload, status_code = services.delete_vendor_promo_code(promo)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
@vendor_required
def vendor_campaigns(request: Any):
    """List or create targeted vendor marketing campaigns."""
    if request.method == "GET":
        payload, status_code = services.list_vendor_campaigns(request)
        return Response(payload, status=status_code)

    payload, status_code = services.create_vendor_campaign(request)
    return Response(payload, status=status_code)


@api_view(["PATCH", "POST"])
@vendor_required
def vendor_campaign_detail(request: Any, campaign_id: int):
    """Update campaign settings or run campaign immediately."""
    vendor = resolve_vendor(request)
    if not vendor:
        return Response({"message": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    campaign = VendorCampaign.objects.filter(id=campaign_id, vendor_id=vendor.id).select_related(
        "vendor", "promo_code", "target_movie", "recommended_movie"
    ).first()
    if not campaign:
        return Response({"message": "Campaign not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "PATCH":
        payload, status_code = services.update_vendor_campaign(request, campaign)
        return Response(payload, status=status_code)

    payload, status_code = services.run_vendor_campaign(campaign)
    return Response(payload, status=status_code)
