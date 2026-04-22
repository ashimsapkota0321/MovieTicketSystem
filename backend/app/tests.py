"""Minimal serializer validation tests."""

from __future__ import annotations

import base64
import json
import tempfile
import zipfile
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from unittest import mock

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.http import QueryDict
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIRequestFactory

from . import group_booking, loyalty, selectors, services, subscription
from .models import (
    Admin,
    Banner,
    BackgroundJob,
    Booking,
    BookingDropoffEvent,
    BookingSeat,
    GroupBookingSession,
    GroupParticipant,
    GroupPayment,
    LoyaltyTransaction,
    Movie,
    MovieCredit,
    Notification,
    OTPVerification,
    Payment,
    Person,
    PrivateScreeningRequest,
    Reward,
    RewardRedemption,
    Referral,
    Refund,
    ReferralWallet,
    ReferralTransaction,
    Review,
    Screen,
    SeatAvailability,
    Seat,
    Show,
    SubscriptionPlan,
    SubscriptionTransaction,
    Ticket,
    TicketValidationScan,
    Transaction,
    User,
    UserWallet,
    UserWalletTransaction,
    UserLoyaltyWallet,
    UserSubscription,
    Vendor,
    VendorStaff,
    Wallet,
)
from .permissions import issue_access_token
from .permissions import resolve_customer
from .serializers import BannerCreateUpdateSerializer, MovieAdminWriteSerializer, UserRegistrationSerializer
from .views.auth import logout, refresh
from .views.ticket_validation import (
    SCAN_CODE_ALREADY_USED,
    SCAN_CODE_EXPIRED_TOKEN,
    SCAN_CODE_INVALID_TOKEN,
    SCAN_CODE_LOOKUP_INVALID,
    SCAN_CODE_PAYMENT_INCOMPLETE,
    SCAN_CODE_RATE_LIMITED,
    SCAN_CODE_OUTSIDE_VALID_TIME_WINDOW,
    SCAN_CODE_VALID,
    SCAN_CODE_WRONG_VENDOR,
    MONITOR_CODE_RATE_LIMITED,
    validate_ticket_scan,
    vendor_ticket_validation_monitor,
    vendor_ticket_validation_monitor_export,
    vendor_ticket_validation_monitor_export_jobs,
    vendor_ticket_validation_monitor_export_job_detail,
    vendor_ticket_validation_monitor_export_job_download,
)
from .views.booking import (
    _build_signature,
    _confirm_booking_after_payment,
    _esewa_product_code,
    _pending_payment_method,
    esewa_verify,
    user_wallet_booking_pay,
    user_wallet_topup_esewa_initiate,
    user_wallet_topup_esewa_verify,
)
from .views.home import home_now_showing_slides
from .views.user_access import user_wallet
from .viewsets import ReviewViewSet


def build_test_image(name: str = "test.png") -> SimpleUploadedFile:
    """Return a valid 1x1 PNG file for upload tests."""
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class StatusNormalizationTests(TestCase):
    """Canonical booking/payment/refund/ticket state normalization."""

    def test_booking_normalization(self) -> None:
        self.assertEqual(
            Booking.normalize_booking_status("Cancelled"),
            Booking.Status.CANCELLED,
        )
        self.assertEqual(
            Booking.normalize_booking_status("pending"),
            Booking.Status.PENDING,
        )


class LifecycleTransitionGuardTests(TestCase):
    """Status transitions and gateway idempotency guards."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Lifecycle Vendor",
            email="lifecycle.vendor@meroticket.local",
            phone_number="9810000200",
            username="lifecycle-vendor",
            theatre="Lifecycle Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.user = User.objects.create(
            phone_number="9810000201",
            email="lifecycle.user@meroticket.local",
            username="lifecycle-user",
            dob=date(1995, 5, 5),
            first_name="Lifecycle",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

        self.movie = Movie.objects.create(
            title="Lifecycle Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

        start_at = timezone.now() + timedelta(hours=4)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall L",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("300.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

    def test_booking_status_cannot_regress(self) -> None:
        booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=Booking.Status.PENDING,
            total_amount=Decimal("300.00"),
        )

        booking.booking_status = Booking.Status.CONFIRMED
        booking.save(update_fields=["booking_status"])

        booking.booking_status = Booking.Status.PENDING
        with self.assertRaises(ValidationError):
            booking.save(update_fields=["booking_status"])

    def test_payment_transaction_uuid_is_idempotent(self) -> None:
        booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=Booking.Status.CONFIRMED,
            total_amount=Decimal("300.00"),
        )

        Payment.objects.create(
            booking=booking,
            payment_method="ESEWA",
            transaction_uuid="gateway-123",
            payment_status=Payment.Status.SUCCESS,
            amount=Decimal("300.00"),
        )

        with self.assertRaises(ValidationError):
            Payment.objects.create(
                booking=booking,
                payment_method="ESEWA",
                transaction_uuid="gateway-123",
                payment_status=Payment.Status.SUCCESS,
                amount=Decimal("300.00"),
            )

    def test_refund_status_cannot_regress(self) -> None:
        booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=Booking.Status.CONFIRMED,
            total_amount=Decimal("300.00"),
        )
        payment = Payment.objects.create(
            booking=booking,
            payment_method="ESEWA",
            transaction_uuid="gateway-456",
            payment_status=Payment.Status.SUCCESS,
            amount=Decimal("300.00"),
        )
        refund = Refund.objects.create(
            payment=payment,
            refund_amount=Decimal("300.00"),
            refund_status=Refund.Status.PENDING,
        )

        refund.refund_status = Refund.Status.COMPLETED
        refund.save(update_fields=["refund_status"])

        refund.refund_status = Refund.Status.PENDING
        with self.assertRaises(ValidationError):
            refund.save(update_fields=["refund_status"])

    def test_ticket_payment_status_cannot_regress(self) -> None:
        ticket = Ticket.objects.create(
            reference="LC-0001",
            payment_status=Ticket.PaymentStatus.PENDING,
            payload={"booking_id": 1},
        )

        ticket.payment_status = Ticket.PaymentStatus.PAID
        ticket.save(update_fields=["payment_status"])

        ticket.payment_status = Ticket.PaymentStatus.PENDING
        with self.assertRaises(ValidationError):
            ticket.save(update_fields=["payment_status"])

    def test_withdrawal_transaction_status_cannot_regress(self) -> None:
        wallet = Wallet.objects.create(vendor=self.vendor)
        withdrawal = Transaction.objects.create(
            wallet=wallet,
            vendor=self.vendor,
            transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST,
            amount=Decimal("150.00"),
            status=Transaction.STATUS_PENDING,
        )

        withdrawal.status = Transaction.STATUS_COMPLETED
        withdrawal.save(update_fields=["status"])

        withdrawal.status = Transaction.STATUS_PENDING
        with self.assertRaises(ValidationError):
            withdrawal.save(update_fields=["status"])


class AuthSessionTests(TestCase):
    """Session-backed auth login, refresh, and logout coverage."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = User.objects.create(
            phone_number="9800000099",
            email="auth-user@meroticket.local",
            username="auth-user",
            dob=date(1994, 4, 4),
            first_name="Auth",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

    def _login(self) -> dict[str, Any]:
        request = type(
            "Request",
            (),
            {
                "data": {
                    "email_or_phone": self.user.email,
                    "password": "password",
                },
            },
        )()
        payload, status_code = services.login_user(request)
        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertTrue(payload.get("access_token"))
        self.assertTrue(payload.get("refresh_token"))
        self.assertTrue(payload.get("session_id"))
        return payload

    def test_login_issues_session_backed_tokens(self) -> None:
        payload = self._login()

        request = self.factory.get("/auth/me/")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {payload['access_token']}"

        customer = resolve_customer(request)
        self.assertIsNotNone(customer)
        self.assertEqual(customer.id, self.user.id)

    def test_logout_revokes_access_token(self) -> None:
        payload = self._login()

        request = self.factory.post("/auth/logout/", {}, format="json")
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {payload['access_token']}"
        response = logout(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        revoked_request = self.factory.get("/auth/me/")
        revoked_request.META["HTTP_AUTHORIZATION"] = f"Bearer {payload['access_token']}"
        self.assertIsNone(resolve_customer(revoked_request))

    def test_refresh_rotates_refresh_token(self) -> None:
        payload = self._login()

        request = self.factory.post(
            "/auth/refresh/",
            {"refresh_token": payload["refresh_token"]},
            format="json",
        )
        response = refresh(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotEqual(response.data.get("refresh_token"), payload["refresh_token"])
        self.assertTrue(response.data.get("access_token"))

        stale_request = self.factory.post(
            "/auth/refresh/",
            {"refresh_token": payload["refresh_token"]},
            format="json",
        )
        stale_response = refresh(stale_request)
        self.assertEqual(stale_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_payment_normalization(self) -> None:
        self.assertEqual(
            Payment.normalize_payment_status("Success"),
            Payment.Status.SUCCESS,
        )
        self.assertEqual(
            Payment.normalize_payment_status("PAID"),
            Payment.Status.SUCCESS,
        )
        self.assertEqual(
            Payment.normalize_payment_status("Partially Refunded"),
            Payment.Status.PARTIALLY_REFUNDED,
        )

    def test_refund_normalization(self) -> None:
        self.assertEqual(
            Refund.normalize_refund_status("Refunded"),
            Refund.Status.COMPLETED,
        )
        self.assertEqual(
            Refund.normalize_refund_status("pending"),
            Refund.Status.PENDING,
        )

    def test_ticket_payment_normalization(self) -> None:
        self.assertEqual(
            Ticket.normalize_payment_status("success"),
            Ticket.PaymentStatus.PAID,
        )
        self.assertEqual(
            Ticket.normalize_payment_status("FAILED"),
            Ticket.PaymentStatus.FAILED,
        )


class VendorWalletLedgerIntegrityTests(TestCase):
    """Vendor wallet balances should be derived from ledger entries without zero clamping."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Ledger Vendor",
            email="ledger.vendor@meroticket.local",
            phone_number="9800011111",
            username="ledger-vendor",
            theatre="Ledger Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.user = User.objects.create(
            phone_number="9800011112",
            email="ledger.user@meroticket.local",
            username="ledger-user",
            dob=date(1995, 1, 1),
            first_name="Ledger",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

        self.movie = Movie.objects.create(
            title="Ledger Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        start_at = timezone.now() + timedelta(hours=2)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall L",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("100.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

        self.booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=Booking.Status.CONFIRMED,
            total_amount=Decimal("100.00"),
        )

    def test_vendor_reversal_allows_negative_obligation_after_settlement(self) -> None:
        services._record_vendor_booking_earning(self.booking, gross_amount=Decimal("100.00"))

        wallet = services._wallet_for_vendor(self.vendor)
        Transaction.objects.create(
            wallet=wallet,
            vendor=self.vendor,
            transaction_type=Transaction.TYPE_WITHDRAWAL_APPROVED,
            amount=Decimal("90.00"),
            commission_amount=Decimal("0.00"),
            gross_amount=Decimal("90.00"),
            status=Transaction.STATUS_COMPLETED,
            description="Simulated settlement payout",
        )
        services._recalculate_vendor_wallet_snapshot(wallet)

        services._reverse_vendor_booking_earning(self.booking, reason="Refunded booking")

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("-90.00"))
        self.assertEqual(wallet.total_earnings, Decimal("0.00"))
        self.assertEqual(wallet.total_commission, Decimal("0.00"))
        self.assertEqual(wallet.total_withdrawn, Decimal("90.00"))
        self.assertTrue(
            Transaction.objects.filter(
                booking=self.booking,
                transaction_type=Transaction.TYPE_BOOKING_REVERSAL,
                status=Transaction.STATUS_COMPLETED,
            ).exists()
        )


class RequestIdLoggingMiddlewareTests(TestCase):
    """Request-id middleware behavior for successful and denied API responses."""

    def test_sets_request_id_header_on_successful_response(self) -> None:
        response = self.client.get("/api/movies/")
        self.assertIn("X-Request-ID", response.headers)
        self.assertTrue(str(response.headers.get("X-Request-ID") or "").strip())

    def test_uses_incoming_request_id_header_when_provided(self) -> None:
        custom_request_id = "manual-request-id-123"
        response = self.client.get(
            "/api/movies/",
            HTTP_X_REQUEST_ID=custom_request_id,
        )
        self.assertEqual(response.headers.get("X-Request-ID"), custom_request_id)

    def test_sets_request_id_header_on_role_denied_response(self) -> None:
        response = self.client.get("/api/vendor/analytics/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("X-Request-ID", response.headers)
        self.assertTrue(str(response.headers.get("X-Request-ID") or "").strip())


class BannerValidationTests(TestCase):
    """Banner serializer validation coverage."""

    def setUp(self) -> None:
        self.movie = Movie.objects.create(title="Test Movie")

    def test_movie_banner_requires_movie(self) -> None:
        serializer = BannerCreateUpdateSerializer(
            data={
                "banner_type": Banner.BannerType.MOVIE,
                "image": build_test_image(),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("movie", serializer.errors)


class BookingBulkAssignmentTests(TestCase):
    """Corporate bulk seat assignment behavior tests."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Test Vendor",
            email="vendor@meroticket.local",
            phone_number="9800000000",
            username="vendor-user",
            password="password",
            theatre="Test Theatre",
            city="Kathmandu",
            is_active=True,
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(title="Corporate Movie", status=Movie.STATUS_NOW_SHOWING, is_active=True)

        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="A",
            show_date=date.today(),
            start_time=time(12, 0),
            price=Decimal("200.00"),
            status="Open",
        )

        self.screen, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

        for seat_index in range(1, 6):
            Seat.objects.create(
                screen=self.screen,
                row_label="A",
                seat_number=str(seat_index),
                seat_type="Normal",
            )
        for seat_index in range(1, 6):
            Seat.objects.create(
                screen=self.screen,
                row_label="B",
                seat_number=str(seat_index),
                seat_type="Executive",
            )

        self.user = User.objects.create(
            phone_number="9800000001",
            email="user@meroticket.local",
            username="bulk-user",
            dob=date(1990, 1, 1),
            first_name="Bulk",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

    def test_bulk_assign_booking_seats(self) -> None:
        booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status="Pending",
            total_amount=Decimal("0.00"),
        )

        request = type("Request", (), {"data": {"seat_category_counts": {"normal": 3, "executive": 2}}})

        payload, status_code = services.bulk_assign_booking_seats(request, booking)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("assigned_count"), 5)
        self.assertEqual(payload.get("booking_id"), booking.id)
        self.assertTrue("assigned_seats" in payload)
        booking.refresh_from_db()
        self.assertEqual(booking.total_amount, Decimal("1000.00"))


class CorporateBookingBillingAndAnalyticsTests(TestCase):
    """Corporate billing settlement and vendor analytics coverage."""

    def setUp(self) -> None:
        cache.clear()
        self.vendor = Vendor.objects.create(
            name="Billing Vendor",
            email="billing-vendor@meroticket.local",
            phone_number="9800000999",
            username="billing-vendor",
            password="password",
            theatre="Billing Theatre",
            city="Kathmandu",
            is_active=True,
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(title="Billing Movie", status=Movie.STATUS_NOW_SHOWING, is_active=True)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="C",
            show_date=date.today(),
            start_time=time(18, 0),
            price=Decimal("300.00"),
            status="Open",
        )
        self.screen, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)
        self.seat = Seat.objects.create(
            screen=self.screen,
            row_label="A",
            seat_number="1",
            seat_type="Normal",
        )

        self.user = User.objects.create(
            phone_number="9800000998",
            email="billing-user@meroticket.local",
            username="billing-user",
            dob=date(1991, 1, 1),
            first_name="Billing",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

    def test_private_screening_request_tracks_partial_settlement(self) -> None:
        request_item = PrivateScreeningRequest.objects.create(
            organization_name="Acme Corp",
            contact_person="Ada Manager",
            contact_email="ada@acme.local",
            attendee_count=120,
            vendor=self.vendor,
            estimated_budget=Decimal("1000.00"),
            invoice_total_amount=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
        )

        request = type(
            "Request",
            (),
            {
                "data": {
                    "status": "INVOICED",
                    "invoice_total_amount": "1000",
                    "amount_paid": "250",
                },
                "query_params": {},
            },
        )()

        payload, status_code = services.update_vendor_private_screening_request(request, request_item)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload["request"]["settlement_status"], "PARTIALLY_SETTLED")
        self.assertEqual(payload["request"]["balance_due"], 750.0)

    def test_vendor_revenue_analytics_includes_occupancy_and_rates(self) -> None:
        booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=Booking.Status.CONFIRMED,
            total_amount=Decimal("300.00"),
            vendor_earning=Decimal("270.00"),
            admin_commission=Decimal("30.00"),
        )
        BookingSeat.objects.create(
            booking=booking,
            showtime=self.showtime,
            seat=self.seat,
            seat_price=Decimal("300.00"),
        )
        payment = Payment.objects.create(
            booking=booking,
            payment_method="CARD",
            payment_status=Payment.Status.SUCCESS,
            amount=Decimal("300.00"),
        )
        Refund.objects.create(
            payment=payment,
            refund_amount=Decimal("50.00"),
            refund_reason="Partial refund",
            refund_status=Refund.Status.COMPLETED,
        )

        Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=Booking.Status.CANCELLED,
            total_amount=Decimal("0.00"),
            vendor_earning=Decimal("0.00"),
            admin_commission=Decimal("0.00"),
        )

        request = APIRequestFactory().get("/api/vendor/revenue/analytics/")
        request.user = self.vendor
        request.query_params = {}

        payload, status_code = services.get_vendor_revenue_analytics(request)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertGreater(len(payload.get("occupancy_by_slot") or []), 0)
        summary = payload.get("summary") or {}
        self.assertGreater(float(summary.get("cancellation_rate") or 0), 0)
        self.assertGreater(float(summary.get("refund_rate") or 0), 0)
        self.assertGreaterEqual(float(summary.get("refund_total_amount") or 0), 50.0)

    def test_promo_banner_disallows_movie(self) -> None:
        serializer = BannerCreateUpdateSerializer(
            data={
                "banner_type": Banner.BannerType.PROMO,
                "movie": self.movie.id,
                "image": build_test_image(),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("movie", serializer.errors)

    def test_image_required(self) -> None:
        serializer = BannerCreateUpdateSerializer(
            data={"banner_type": Banner.BannerType.PROMO}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("image", serializer.errors)


class MovieCreditsAndReviewsTests(TestCase):
    """Movie cast/crew persistence and details payload coverage."""

    def _create_user(self, suffix: str) -> User:
        user = User.objects.create(
            phone_number=f"98000000{suffix}",
            email=f"reviewer{suffix}@meroticket.local",
            username=f"reviewer-{suffix}",
            dob=date(1995, 1, 1),
            first_name="Reviewer",
            last_name=suffix,
            password="password",
        )
        user.set_password("password")
        user.save()
        return user

    def test_movie_admin_serializer_accepts_json_credits_payload(self) -> None:
        serializer = MovieAdminWriteSerializer(
            data={
                "title": "Credits JSON Movie",
                "credits": json.dumps(
                    [
                        {
                            "role_type": "CAST",
                            "character_name": "Hero",
                            "position": 1,
                            "person": {"full_name": "Actor One"},
                        },
                        {
                            "role_type": "CREW",
                            "job_title": "Director",
                            "position": 2,
                            "person": {"full_name": "Director One"},
                        },
                    ]
                ),
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        movie = serializer.save()
        self.assertEqual(movie.credits.count(), 2)
        self.assertTrue(MovieCredit.objects.filter(movie=movie, role_type=MovieCredit.ROLE_CAST).exists())
        self.assertTrue(MovieCredit.objects.filter(movie=movie, role_type=MovieCredit.ROLE_CREW).exists())

    def test_movie_admin_serializer_accepts_querydict_credits_payload(self) -> None:
        payload = QueryDict("", mutable=True)
        payload.update({"title": "Credits QueryDict Movie"})
        payload.update(
            {
                "credits": json.dumps(
                    [
                        {
                            "role_type": "CAST",
                            "character_name": "Hero",
                            "position": 1,
                            "person": {"full_name": "Actor Query"},
                        },
                        {
                            "role_type": "CREW",
                            "job_title": "Director",
                            "position": 2,
                            "person": {"full_name": "Director Query"},
                        },
                    ]
                )
            }
        )

        serializer = MovieAdminWriteSerializer(data=payload)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        movie = serializer.save()
        self.assertEqual(movie.credits.count(), 2)
        self.assertTrue(MovieCredit.objects.filter(movie=movie, role_type=MovieCredit.ROLE_CAST).exists())
        self.assertTrue(MovieCredit.objects.filter(movie=movie, role_type=MovieCredit.ROLE_CREW).exists())

    def test_movie_admin_serializer_accepts_cast_and_crew_payload(self) -> None:
        serializer = MovieAdminWriteSerializer(
            data={
                "title": "Cast Crew Payload Movie",
                "cast": json.dumps(
                    [
                        {
                            "name": "Actor Two",
                            "role": "Hero",
                            "position": 1,
                        }
                    ]
                ),
                "crew": [
                    {
                        "roleType": "crew",
                        "jobTitle": "Director",
                        "position": 2,
                        "person": {"fullName": "Director Two"},
                    }
                ],
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        movie = serializer.save()

        self.assertEqual(movie.credits.count(), 2)
        cast_credit = movie.credits.filter(role_type=MovieCredit.ROLE_CAST).select_related("person").first()
        crew_credit = movie.credits.filter(role_type=MovieCredit.ROLE_CREW).select_related("person").first()
        self.assertIsNotNone(cast_credit)
        self.assertIsNotNone(crew_credit)
        self.assertEqual(cast_credit.person.full_name, "Actor Two")
        self.assertEqual(crew_credit.person.full_name, "Director Two")

    def test_services_sync_movie_credits_falls_back_to_cast_crew_payload(self) -> None:
        movie = Movie.objects.create(title="Services Credits Fallback")
        payload = {
            "credits": "invalid-json",
            "cast": json.dumps(
                [
                    {
                        "name": "Actor Three",
                        "role": "Lead",
                    }
                ]
            ),
            "crew": json.dumps(
                [
                    {
                        "name": "Director Three",
                        "role": "Director",
                    }
                ]
            ),
        }
        request = type("Request", (), {"FILES": {}})()

        credits_payload = services._extract_credits_payload(payload)
        services._sync_movie_credits(request, movie, credits_payload)

        self.assertEqual(movie.credits.count(), 2)
        self.assertTrue(
            MovieCredit.objects.filter(movie=movie, role_type=MovieCredit.ROLE_CAST).exists()
        )
        self.assertTrue(
            MovieCredit.objects.filter(movie=movie, role_type=MovieCredit.ROLE_CREW).exists()
        )

    def test_movie_admin_serializer_partial_update_preserves_existing_poster_image(self) -> None:
        movie = Movie.objects.create(
            title="Poster Keep Movie",
            poster_image=build_test_image("existing-poster.png"),
        )
        original_poster_name = movie.poster_image.name

        serializer = MovieAdminWriteSerializer(
            movie,
            data={
                "title": "Poster Keep Movie Updated",
                "poster_image": "",
            },
            partial=True,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated_movie = serializer.save()
        updated_movie.refresh_from_db()

        self.assertTrue(updated_movie.poster_image)
        self.assertEqual(updated_movie.poster_image.name, original_poster_name)

    @mock.patch("app.services.get_payload", return_value={"title": "Vendor Pending Movie"})
    @mock.patch("app.services.resolve_vendor", return_value=object())
    @mock.patch("app.services.resolve_admin", return_value=None)
    def test_vendor_movie_creation_starts_pending(self, mocked_admin, mocked_vendor, mocked_payload) -> None:
        request = type("Request", (), {"FILES": {}})()

        payload, status_code = services.create_movie(request)

        self.assertEqual(status_code, status.HTTP_201_CREATED)
        movie = Movie.objects.get(pk=payload["movie"]["id"])
        self.assertFalse(movie.is_approved)

    def test_vendor_movie_creation_notifies_active_admins(self) -> None:
        admin = Admin.objects.create(
            name="Movie Reviewer",
            email="movie.reviewer@meroticket.local",
            phone_number="9800010101",
            theatre_name="Reviewer Theatre",
            location="Kathmandu",
            is_active=True,
        )
        admin.set_password("password")
        admin.save()

        vendor = Vendor.objects.create(
            name="Notify Vendor",
            email="notify.vendor@meroticket.local",
            phone_number="9800010102",
            username="notify-vendor",
            theatre="Notify Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        vendor.set_password("password")
        vendor.save()

        request = type("Request", (), {"FILES": {}})()
        with mock.patch("app.services.get_payload", return_value={"title": "Vendor Notify Movie"}), mock.patch(
            "app.services.resolve_vendor", return_value=vendor
        ), mock.patch("app.services.resolve_admin", return_value=None):
            payload, status_code = services.create_movie(request)

        self.assertEqual(status_code, status.HTTP_201_CREATED)
        movie_id = payload.get("movie", {}).get("id")
        self.assertIsNotNone(movie_id)

        admin_notification = (
            Notification.objects.filter(
                recipient_role=Notification.ROLE_ADMIN,
                recipient_id=admin.id,
                event_type=Notification.EVENT_SHOW_UPDATE,
                metadata__movie_id=movie_id,
                metadata__action="movie_submission",
            )
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(admin_notification)

    def test_public_movie_lists_hide_unapproved_titles(self) -> None:
        approved_movie = Movie.objects.create(
            title="Approved Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
            is_approved=True,
        )
        pending_movie = Movie.objects.create(
            title="Pending Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
            is_approved=False,
        )

        public_movies = selectors.list_movies()
        admin_movies = selectors.list_movies(include_unapproved=True)

        public_ids = {movie.id for movie in public_movies}
        admin_ids = {movie.id for movie in admin_movies}
        self.assertIn(approved_movie.id, public_ids)
        self.assertNotIn(pending_movie.id, public_ids)
        self.assertIn(pending_movie.id, admin_ids)

    def test_home_now_showing_excludes_unapproved_movies(self) -> None:
        approved_movie = Movie.objects.create(
            title="Homepage Approved",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
            is_approved=True,
        )
        Movie.objects.create(
            title="Homepage Pending",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
            is_approved=False,
        )

        request = APIRequestFactory().get("/home/now-showing/")
        response = home_now_showing_slides(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        slide_ids = {item["id"] for item in response.data["slides"]}
        self.assertIn(approved_movie.id, slide_ids)
        self.assertEqual(len(slide_ids), 1)

    def test_movie_detail_payload_includes_cast_crew_and_approved_reviews(self) -> None:
        movie = Movie.objects.create(title="Movie Detail Data")
        cast_person = Person.objects.create(full_name="Cast Member")
        crew_person = Person.objects.create(full_name="Crew Member")

        MovieCredit.objects.create(
            movie=movie,
            person=cast_person,
            role_type=MovieCredit.ROLE_CAST,
            character_name="Lead",
            position=1,
        )
        MovieCredit.objects.create(
            movie=movie,
            person=crew_person,
            role_type=MovieCredit.ROLE_CREW,
            job_title="Director",
            position=2,
        )

        approved_user = self._create_user("11")
        pending_user = self._create_user("12")
        Review.objects.create(
            movie=movie,
            user=approved_user,
            rating=5,
            comment="Excellent.",
            is_approved=True,
        )
        Review.objects.create(
            movie=movie,
            user=pending_user,
            rating=2,
            comment="Needs improvement.",
            is_approved=False,
        )

        payload = selectors.build_movie_detail_payload(movie)
        self.assertEqual(len(payload.get("cast", [])), 1)
        self.assertEqual(len(payload.get("crew", [])), 1)
        self.assertEqual(len(payload.get("reviews", [])), 1)
        self.assertEqual(payload["reviews"][0]["comment"], "Excellent.")


class ForgotPasswordOtpEmailTests(TestCase):
    """Ensure forgot-password OTP emails are sent and failures are surfaced."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = User.objects.create(
            phone_number="9800000033",
            email="otp-user@meroticket.local",
            username="otp-user",
            dob=date(1993, 1, 1),
            first_name="Otp",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

    @override_settings(
        DEBUG=False,
        RESEND_API_KEY="",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="test@example.com",
        EMAIL_HOST_PASSWORD="test-app-password",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    @mock.patch("app.services.core.send_mail")
    def test_request_password_otp_sends_email(self, mocked_send_mail) -> None:
        mocked_send_mail.return_value = 1

        payload, status_code = services.request_password_otp(self.user.email)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("message"), "OTP sent to your email")
        self.assertTrue(
            OTPVerification.objects.filter(email__iexact=self.user.email).exists()
        )
        self.assertEqual(mocked_send_mail.call_count, 1)

    @override_settings(
        DEBUG=False,
        RESEND_API_KEY="",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="test@example.com",
        EMAIL_HOST_PASSWORD="test-app-password",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    @mock.patch("app.services.core.send_mail")
    def test_request_password_otp_returns_error_when_email_fails(self, mocked_send_mail) -> None:
        mocked_send_mail.side_effect = Exception("SMTP unavailable")

        payload, status_code = services.request_password_otp(self.user.email)

        self.assertEqual(status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("Failed to send OTP email", str(payload.get("message") or ""))
        self.assertFalse(
            OTPVerification.objects.filter(email__iexact=self.user.email).exists()
        )

    @override_settings(
        DEBUG=True,
        RESEND_API_KEY="",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="test@example.com",
        EMAIL_HOST_PASSWORD="test-app-password",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    @mock.patch("app.services.core.send_mail")
    def test_request_password_otp_debug_falls_back_to_console_when_email_fails(
        self,
        mocked_send_mail,
    ) -> None:
        mocked_send_mail.side_effect = Exception("SMTP unavailable")

        payload, status_code = services.request_password_otp(self.user.email)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertIn("OTP printed in backend console", str(payload.get("message") or ""))
        self.assertTrue(
            OTPVerification.objects.filter(email__iexact=self.user.email).exists()
        )

    @mock.patch("app.services.core._send_password_changed_email")
    def test_reset_password_with_otp_sends_password_changed_email(
        self,
        mocked_password_changed_email,
    ) -> None:
        mocked_password_changed_email.return_value = True
        otp = "123456"
        OTPVerification.objects.create(
            email=self.user.email,
            otp=otp,
            is_verified=True,
        )

        payload, status_code = services.reset_password_with_otp(
            self.user.email,
            otp,
            "new-secure-password",
        )

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("message"), "Password reset successful")
        mocked_password_changed_email.assert_called_once_with(
            self.user.email,
            context_label="password reset with OTP",
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("new-secure-password"))

    @mock.patch("app.services.core._send_password_changed_email")
    def test_update_admin_user_sends_password_changed_email(
        self,
        mocked_password_changed_email,
    ) -> None:
        mocked_password_changed_email.return_value = True
        request = type(
            "Request",
            (),
            {"data": {"password": "admin-updated-password"}},
        )()

        payload, status_code = services.update_admin_user(self.user, request)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("message"), "User updated")
        mocked_password_changed_email.assert_called_once_with(
            self.user.email,
            context_label="changed by an administrator",
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("admin-updated-password"))


class RegistrationOtpEmailTests(TestCase):
    """Ensure registration requires verified email OTP and OTP flow works."""

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="test@example.com",
        EMAIL_HOST_PASSWORD="test-app-password",
        DEFAULT_FROM_EMAIL="test@example.com",
    )
    @mock.patch("app.services.core.send_mail")
    def test_request_registration_otp_sends_email(self, mocked_send_mail) -> None:
        mocked_send_mail.return_value = 1

        payload, status_code = services.request_registration_otp("new-user@meroticket.local")

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertIn("OTP", str(payload.get("message") or ""))
        self.assertEqual(mocked_send_mail.call_count, 1)
        self.assertTrue(
            OTPVerification.objects.filter(email__iexact="new-user@meroticket.local").exists()
        )

    def test_register_user_requires_verified_registration_otp(self) -> None:
        request = type(
            "Request",
            (),
            {
                "data": {
                    "phone_number": "9850000199",
                    "email": "otp-required@meroticket.local",
                    "dob": "1998-02-10",
                    "first_name": "Otp",
                    "last_name": "Required",
                    "password": "StrongPass123",
                    "confirm_password": "StrongPass123",
                },
                "META": {},
            },
        )()

        payload, status_code = services.register_user(request)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Email verification required", str(payload.get("message") or ""))


class UserRegistrationSerializerTests(TestCase):
    """Unit tests for user registration serializer email validation."""

    def test_validate_email_accepts_unique_email_and_normalizes(self) -> None:
        data = {
            "phone_number": "9810000001",
            "email": "User@Domain.Com",
            "dob": date(1995, 1, 1),
            "first_name": "Test",
            "last_name": "User",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }

        serializer = UserRegistrationSerializer(data=data)

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["email"], "user@domain.com")

    def test_validate_email_rejects_duplicate_email(self) -> None:
        User.objects.create(
            phone_number="9810000002",
            email="existing@example.com",
            username="existing-user",
            dob=date(1995, 1, 1),
            first_name="Existing",
            last_name="User",
            password="StrongPass123!",
        )

        data = {
            "phone_number": "9810000003",
            "email": "existing@example.com",
            "dob": date(1995, 1, 1),
            "first_name": "New",
            "last_name": "User",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }

        serializer = UserRegistrationSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

    def test_validate_email_rejects_invalid_email_format(self) -> None:
        data = {
            "phone_number": "9810000004",
            "email": "abc@",
            "dob": date(1995, 1, 1),
            "first_name": "Bad",
            "last_name": "Email",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
        }

        serializer = UserRegistrationSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

class NotificationBackgroundQueueTests(TestCase):
    """Ensure notification emails are dispatched through the background queue."""

    def setUp(self) -> None:
        self.user = User.objects.create(
            phone_number="9800012244",
            email="notify-user@meroticket.local",
            username="notify-user",
            dob=date(1992, 1, 1),
            first_name="Notify",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

    @mock.patch("app.services.send_mail")
    def test_create_notification_queues_email_job_and_worker_sends_it(self, mocked_send_mail) -> None:
        mocked_send_mail.return_value = 1

        created_notification = services._create_notification(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=self.user.id,
            recipient_email=self.user.email,
            event_type=Notification.EVENT_NEW_BOOKING,
            title="Queue test",
            message="Queued email test",
            metadata={"source": "unit-test"},
            send_email_too=True,
        )

        self.assertIsNotNone(created_notification.id)
        self.assertEqual(created_notification.channel, Notification.CHANNEL_BOTH)
        self.assertEqual(mocked_send_mail.call_count, 0)

        queued_job = BackgroundJob.objects.filter(
            job_type=BackgroundJob.TYPE_NOTIFICATION_EMAIL,
            status=BackgroundJob.STATUS_PENDING,
        ).order_by("-id").first()
        self.assertIsNotNone(queued_job)

        summary = services.process_background_jobs(
            batch_size=5,
            job_types=[BackgroundJob.TYPE_NOTIFICATION_EMAIL],
        )
        self.assertEqual(summary.get("completed"), 1)

        queued_job.refresh_from_db()
        self.assertEqual(queued_job.status, BackgroundJob.STATUS_COMPLETED)
        self.assertEqual(mocked_send_mail.call_count, 1)


class AdminBookingEmailNotificationTests(TestCase):
    """Ensure admin cancellation/refund actions notify customer through email queue."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Admin Notify Vendor",
            email="admin.notify.vendor@meroticket.local",
            phone_number="9812345100",
            username="admin-notify-vendor",
            theatre="Notify Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.customer = User.objects.create(
            phone_number="9812345101",
            email="admin.notify.customer@meroticket.local",
            username="admin-notify-customer",
            dob=date(1994, 4, 4),
            first_name="Admin",
            last_name="Notify",
            password="password",
        )
        self.customer.set_password("password")
        self.customer.save()

        self.movie = Movie.objects.create(
            title="Admin Notify Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

        start_at = timezone.now() + timedelta(hours=4)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall N",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("500.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

    def _create_confirmed_booking(self) -> Booking:
        return Booking.objects.create(
            user=self.customer,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("500.00"),
        )

    def test_admin_cancel_booking_creates_customer_email_notification(self) -> None:
        booking = self._create_confirmed_booking()
        request = type("Request", (), {"data": {"reason": "Ops cancellation"}})()

        payload, status_code = services.admin_cancel_booking(request, booking)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("message"), "Booking cancelled")

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, services.BOOKING_STATUS_CANCELLED)

        notification = (
            Notification.objects.filter(
                recipient_role=Notification.ROLE_CUSTOMER,
                recipient_id=self.customer.id,
                event_type=Notification.EVENT_BOOKING_CANCELLED,
            )
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(notification)
        self.assertEqual(notification.channel, Notification.CHANNEL_BOTH)

        self.assertTrue(
            BackgroundJob.objects.filter(
                job_type=BackgroundJob.TYPE_NOTIFICATION_EMAIL,
                status=BackgroundJob.STATUS_PENDING,
            ).exists()
        )

    def test_admin_refund_booking_creates_customer_email_notification(self) -> None:
        booking = self._create_confirmed_booking()
        payment = Payment.objects.create(
            booking=booking,
            payment_method="Cash",
            payment_status="Success",
            amount=Decimal("500.00"),
        )
        request = type(
            "Request",
            (),
            {"data": {"amount": "200.00", "reason": "Admin partial refund"}},
        )()

        payload, status_code = services.admin_refund_booking(request, booking)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("message"), "Booking refunded")

        booking.refresh_from_db()
        self.assertEqual(booking.booking_status, services.BOOKING_STATUS_CANCELLED)
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, "Refunded")
        self.assertEqual(payment.refunds.count(), 1)

        wallet = UserWallet.objects.get(user=self.customer)
        self.assertEqual(wallet.balance, Decimal("200.00"))
        self.assertEqual(wallet.total_credited, Decimal("200.00"))

        wallet_tx = UserWalletTransaction.objects.filter(
            user=self.customer,
            booking=booking,
            transaction_type=UserWalletTransaction.TYPE_REFUND,
            status=UserWalletTransaction.STATUS_COMPLETED,
        ).first()
        self.assertIsNotNone(wallet_tx)
        self.assertEqual(wallet_tx.amount, Decimal("200.00"))
        self.assertEqual(wallet_tx.provider, "SYSTEM")

        notification = (
            Notification.objects.filter(
                recipient_role=Notification.ROLE_CUSTOMER,
                recipient_id=self.customer.id,
                event_type=Notification.EVENT_REFUND_PROCESSED,
            )
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(notification)
        self.assertEqual(notification.channel, Notification.CHANNEL_BOTH)

        self.assertTrue(
            BackgroundJob.objects.filter(
                job_type=BackgroundJob.TYPE_NOTIFICATION_EMAIL,
                status=BackgroundJob.STATUS_PENDING,
            ).exists()
        )


class CustomerRefundRequestNotificationTests(TestCase):
    """Ensure customer refund requests create vendor notifications."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Refund Request Vendor",
            email="refund.request.vendor@meroticket.local",
            phone_number="9812345200",
            username="refund-request-vendor",
            theatre="Refund Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.customer = User.objects.create(
            phone_number="9812345201",
            email="refund.request.customer@meroticket.local",
            username="refund-request-customer",
            dob=date(1995, 5, 5),
            first_name="Refund",
            last_name="Customer",
            password="password",
        )
        self.customer.set_password("password")
        self.customer.save()

        self.movie = Movie.objects.create(
            title="Refund Request Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

        start_at = timezone.now() + timedelta(days=2)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall R",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("450.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

        self.booking = Booking.objects.create(
            user=self.customer,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("450.00"),
        )
        Payment.objects.create(
            booking=self.booking,
            payment_method="Cash",
            payment_status="Success",
            amount=Decimal("450.00"),
        )

    def test_customer_cancel_booking_notifies_vendor_for_refund_request(self) -> None:
        request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "Need to cancel due to emergency"},
            },
        )()

        payload, status_code = services.customer_cancel_booking(request, self.booking)

        self.assertEqual(status_code, status.HTTP_202_ACCEPTED, payload)
        self.assertIn("request_id", payload)

        vendor_notification = Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=self.vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=self.booking.id,
        ).order_by("-id").first()
        self.assertIsNotNone(vendor_notification)
        self.assertEqual(vendor_notification.channel, Notification.CHANNEL_BOTH)
        self.assertEqual(
            str((vendor_notification.metadata or {}).get("request_status") or ""),
            "PENDING",
        )

    def test_customer_cancel_booking_reopens_read_pending_vendor_notification(self) -> None:
        first_request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "First refund request"},
            },
        )()
        services.customer_cancel_booking(first_request, self.booking)

        vendor_notification = Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=self.vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=self.booking.id,
        ).order_by("-id").first()
        self.assertIsNotNone(vendor_notification)

        vendor_notification.is_read = True
        vendor_notification.read_at = timezone.now()
        vendor_notification.save(update_fields=["is_read", "read_at"])

        second_request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "Second reminder for refund"},
            },
        )()
        payload, status_code = services.customer_cancel_booking(second_request, self.booking)

        self.assertEqual(status_code, status.HTTP_200_OK, payload)
        self.assertIn("pending vendor approval", str(payload.get("message") or "").lower())

        vendor_notification.refresh_from_db()
        self.assertFalse(vendor_notification.is_read)
        self.assertIsNone(vendor_notification.read_at)
        self.assertEqual(
            str((vendor_notification.metadata or {}).get("requested_reason") or ""),
            "Second reminder for refund",
        )
        self.assertTrue(bool((vendor_notification.metadata or {}).get("reminded_at")))

        self.assertEqual(
            Notification.objects.filter(
                recipient_role=Notification.ROLE_VENDOR,
                recipient_id=self.vendor.id,
                event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
                metadata__booking_id=self.booking.id,
            ).count(),
            1,
        )

    def test_customer_cancel_booking_rejects_within_one_hour(self) -> None:
        start_at = timezone.now() + timedelta(minutes=30)
        short_show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall Short",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("450.00"),
        )
        _, short_showtime = services._get_or_create_showtime_for_context(short_show, short_show.hall)
        short_booking = Booking.objects.create(
            user=self.customer,
            showtime=short_showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("450.00"),
        )

        request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "Too late to travel"},
            },
        )()

        payload, status_code = services.customer_cancel_booking(request, short_booking)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST, payload)
        self.assertIn("1 hour", str(payload.get("message") or ""))
        self.assertFalse(
            Notification.objects.filter(
                recipient_role=Notification.ROLE_VENDOR,
                recipient_id=self.vendor.id,
                event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
                metadata__booking_id=short_booking.id,
            ).exists()
        )

    def test_vendor_cancel_booking_can_reject_pending_request(self) -> None:
        request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "Need to cancel due to emergency"},
            },
        )()
        services.customer_cancel_booking(request, self.booking)

        vendor_request = type(
            "Request",
            (),
            {
                "user": self.vendor,
                "data": {"action": "REJECT", "reason": "Policy does not allow this case"},
            },
        )()

        payload, status_code = services.vendor_cancel_booking(vendor_request, self.booking)

        self.assertEqual(status_code, status.HTTP_200_OK, payload)
        self.assertEqual(payload.get("message"), "Cancellation request rejected.")
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, services.BOOKING_STATUS_CONFIRMED)

        vendor_notification = Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=self.vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=self.booking.id,
        ).order_by("-id").first()
        self.assertIsNotNone(vendor_notification)
        self.assertEqual(
            str((vendor_notification.metadata or {}).get("request_status") or ""),
            "REJECTED",
        )

        customer_notification = Notification.objects.filter(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=self.customer.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=self.booking.id,
        ).order_by("-id").first()
        self.assertIsNotNone(customer_notification)
        self.assertEqual(
            str((customer_notification.metadata or {}).get("request_status") or ""),
            "REJECTED",
        )

    def test_vendor_cancel_booking_can_approve_pending_request_and_process_refund(self) -> None:
        request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "Need to cancel due to emergency"},
            },
        )()
        services.customer_cancel_booking(request, self.booking)

        vendor_request = type(
            "Request",
            (),
            {
                "user": self.vendor,
                "data": {"action": "APPROVE", "reason": "Approved by vendor"},
            },
        )()

        payload, status_code = services.vendor_cancel_booking(vendor_request, self.booking)

        self.assertEqual(status_code, status.HTTP_200_OK, payload)
        self.assertIn("Booking cancelled", str(payload.get("message") or ""))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, services.BOOKING_STATUS_CANCELLED)

        payment = Payment.objects.filter(booking=self.booking).order_by("-id").first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.payment_status, services.PAYMENT_STATUS_REFUNDED)

        vendor_notification = Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=self.vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=self.booking.id,
        ).order_by("-id").first()
        self.assertIsNotNone(vendor_notification)
        self.assertEqual(
            str((vendor_notification.metadata or {}).get("request_status") or ""),
            "APPROVED",
        )

    def test_vendor_can_approve_pending_cancel_request_after_policy_window_changes(self) -> None:
        request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "Need to cancel due to emergency"},
            },
        )()
        request_payload, request_status = services.customer_cancel_booking(request, self.booking)
        self.assertIn(request_status, {status.HTTP_200_OK, status.HTTP_202_ACCEPTED}, request_payload)

        # Simulate vendor delay: request is pending, but show moves into <1h window before approval.
        self.showtime.start_time = timezone.now() + timedelta(minutes=30)
        self.showtime.save(update_fields=["start_time"])

        vendor_request = type(
            "Request",
            (),
            {
                "user": self.vendor,
                "data": {"action": "APPROVE", "reason": "Approved by vendor"},
            },
        )()

        payload, status_code = services.vendor_cancel_booking(vendor_request, self.booking)

        self.assertEqual(status_code, status.HTTP_200_OK, payload)
        self.assertIn("Booking cancelled", str(payload.get("message") or ""))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.booking_status, services.BOOKING_STATUS_CANCELLED)

        vendor_notification = Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=self.vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=self.booking.id,
        ).order_by("-id").first()
        self.assertIsNotNone(vendor_notification)
        self.assertEqual(
            str((vendor_notification.metadata or {}).get("request_status") or ""),
            "APPROVED",
        )

    def test_pending_unpaid_booking_cancellation_is_cancel_only(self) -> None:
        pending_booking = Booking.objects.create(
            user=self.customer,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_PENDING,
            total_amount=Decimal("450.00"),
        )

        request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {"reason": "Change of plan"},
            },
        )()

        payload, status_code = services.customer_cancel_booking(request, pending_booking)

        self.assertEqual(status_code, status.HTTP_202_ACCEPTED, payload)
        self.assertEqual(str((payload.get("cancellation") or {}).get("has_successful_payment") or False), "False")

        vendor_notification = Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=self.vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=pending_booking.id,
        ).order_by("-id").first()
        self.assertIsNotNone(vendor_notification)
        self.assertEqual(
            str((vendor_notification.metadata or {}).get("request_type") or ""),
            "CANCEL_ONLY",
        )
        refund_preview = (vendor_notification.metadata or {}).get("refund_preview") or {}
        self.assertEqual(float(refund_preview.get("refund_amount") or 0), 0.0)
        self.assertEqual(float(refund_preview.get("cancellation_charge_amount") or 0), 0.0)

        vendor_request = type(
            "Request",
            (),
            {
                "user": self.vendor,
                "data": {"action": "APPROVE", "reason": "Approved without refund"},
            },
        )()
        approve_payload, approve_status = services.vendor_cancel_booking(vendor_request, pending_booking)
        self.assertEqual(approve_status, status.HTTP_200_OK, approve_payload)
        pending_booking.refresh_from_db()
        self.assertEqual(pending_booking.booking_status, services.BOOKING_STATUS_CANCELLED)
        self.assertFalse(Payment.objects.filter(booking=pending_booking).exists())


class ReviewOwnershipPermissionsTests(TestCase):
    """Ensure customers can only edit/delete their own reviews."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.movie = Movie.objects.create(title="Review Ownership Movie")

        self.owner = User.objects.create(
            phone_number="9800000021",
            email="owner@meroticket.local",
            username="owner-review",
            dob=date(1994, 1, 1),
            first_name="Owner",
            last_name="User",
            password="password",
        )
        self.owner.set_password("password")
        self.owner.save()

        self.other = User.objects.create(
            phone_number="9800000022",
            email="other@meroticket.local",
            username="other-review",
            dob=date(1994, 1, 1),
            first_name="Other",
            last_name="User",
            password="password",
        )
        self.other.set_password("password")
        self.other.save()

        self.review = Review.objects.create(
            movie=self.movie,
            user=self.owner,
            rating=4,
            comment="Initial review",
            is_approved=True,
        )

    def test_owner_can_update_own_review(self) -> None:
        request = self.factory.patch(
            f"/api/reviews/{self.review.id}/",
            {"rating": 5, "comment": "Updated review"},
            format="json",
        )
        request.user = self.owner

        response = ReviewViewSet.as_view({"patch": "partial_update"})(
            request,
            pk=self.review.id,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 5)
        self.assertEqual(self.review.comment, "Updated review")

    def test_non_owner_cannot_update_review(self) -> None:
        request = self.factory.patch(
            f"/api/reviews/{self.review.id}/",
            {"rating": 1, "comment": "Hacked"},
            format="json",
        )
        request.user = self.other

        response = ReviewViewSet.as_view({"patch": "partial_update"})(
            request,
            pk=self.review.id,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 4)
        self.assertEqual(self.review.comment, "Initial review")

    def test_owner_can_delete_own_review(self) -> None:
        request = self.factory.delete(f"/api/reviews/{self.review.id}/")
        request.user = self.owner

        response = ReviewViewSet.as_view({"delete": "destroy"})(
            request,
            pk=self.review.id,
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Review.objects.filter(id=self.review.id).exists())

    def test_non_owner_cannot_delete_review(self) -> None:
        request = self.factory.delete(f"/api/reviews/{self.review.id}/")
        request.user = self.other

        response = ReviewViewSet.as_view({"delete": "destroy"})(
            request,
            pk=self.review.id,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Review.objects.filter(id=self.review.id).exists())


@override_settings(
    SHOW_BUFFER_MINUTES=20,
    SHOW_MIN_LEAD_HOURS=2,
    SHOW_OPERATING_OPEN_TIME="06:00",
    SHOW_OPERATING_CLOSE_TIME="00:00",
)
class ShowSchedulingRulesTests(TestCase):
    """Show creation scheduling safeguards and computed timing behavior."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Scheduler Vendor",
            email="scheduler.vendor@meroticket.local",
            phone_number="9810000000",
            username="scheduler-vendor",
            theatre="Scheduler Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(
            title="Duration Based Movie",
            duration_minutes=156,
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        self.screen = Screen.objects.create(
            vendor=self.vendor,
            screen_number="Hall A",
            screen_type="Standard",
            status="Active",
        )
        for row_label in ("A", "B"):
            for seat_number in range(1, 5):
                Seat.objects.create(
                    screen=self.screen,
                    row_label=row_label,
                    seat_number=str(seat_number),
                    seat_type="Normal",
                )
        self.future_date = (date.today() + timedelta(days=2)).isoformat()

    def _build_request(self, **overrides):
        payload = {
            "movieId": self.movie.id,
            "vendorId": self.vendor.id,
            "hall": "Hall A",
            "date": self.future_date,
            "start": "18:30",
        }
        payload.update(overrides)
        return type(
            "Request",
            (),
            {
                "user": self.vendor,
                "data": payload,
                "FILES": {},
                "query_params": {},
            },
        )()

    def test_create_show_calculates_end_time_from_movie_duration(self) -> None:
        request = self._build_request(start="18:30", end="22:00")

        payload, status_code = services.create_show(request)

        self.assertEqual(status_code, status.HTTP_201_CREATED, payload)
        show_id = payload.get("show", {}).get("id")
        show = Show.objects.get(id=show_id)
        self.assertEqual(show.end_time.strftime("%H:%M"), "21:06")

    def test_create_show_initializes_seat_availability_for_all_hall_seats(self) -> None:
        request = self._build_request(start="16:00")

        payload, status_code = services.create_show(request)

        self.assertEqual(status_code, status.HTTP_201_CREATED, payload)
        show_id = payload.get("show", {}).get("id")
        show = Show.objects.get(id=show_id)
        showtime = services._find_showtime_for_context(show, show.hall)
        self.assertIsNotNone(showtime)

        expected_seat_count = Seat.objects.filter(screen=self.screen).count()
        self.assertEqual(
            SeatAvailability.objects.filter(showtime=showtime).count(),
            expected_seat_count,
        )
        self.assertFalse(
            SeatAvailability.objects.filter(showtime=showtime)
            .exclude(seat_status=services.SEAT_STATUS_AVAILABLE)
            .exists()
        )

    def test_create_show_rejects_overlap_when_buffer_window_conflicts(self) -> None:
        first_request = self._build_request(start="15:00")
        first_payload, first_status = services.create_show(first_request)
        self.assertEqual(first_status, status.HTTP_201_CREATED, first_payload)

        conflicting_request = self._build_request(start="17:50")
        payload, status_code = services.create_show(conflicting_request)

        self.assertEqual(status_code, status.HTTP_409_CONFLICT, payload)
        self.assertEqual(payload.get("created_count"), 0)
        self.assertTrue(any(item.get("reason") == "overlap" for item in payload.get("conflicts", [])))

    def test_create_show_rejects_timing_outside_operating_hours(self) -> None:
        request = self._build_request(start="22:00")

        payload, status_code = services.create_show(request)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST, payload)
        self.assertTrue(any(item.get("reason") == "outside_operating_hours" for item in payload.get("conflicts", [])))

    def test_create_show_rejects_start_time_less_than_two_hours_ahead(self) -> None:
        fixed_now = timezone.make_aware(
            datetime(2026, 1, 15, 21, 0),
            timezone.get_current_timezone(),
        )

        with mock.patch("app.services.timezone.now", return_value=fixed_now):
            request = self._build_request(date="2026-01-15", start="22:30")
            payload, status_code = services.create_show(request)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST, payload)
        self.assertTrue(any(item.get("reason") == "too_soon" for item in payload.get("conflicts", [])))

    def test_create_show_allows_exact_two_hour_lead_boundary(self) -> None:
        fixed_now = timezone.make_aware(
            datetime(2026, 1, 15, 9, 0),
            timezone.get_current_timezone(),
        )

        with mock.patch("app.services.timezone.now", return_value=fixed_now):
            request = self._build_request(date="2026-01-15", start="11:00")
            payload, status_code = services.create_show(request)

        self.assertEqual(status_code, status.HTTP_201_CREATED, payload)

    def test_create_show_rejects_unknown_hall(self) -> None:
        request = self._build_request(hall="Hall Z")

        payload, status_code = services.create_show(request)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST, payload)
        self.assertIn("does not exist", str(payload.get("message") or "").lower())

    def test_create_show_rejects_hall_without_layout(self) -> None:
        Screen.objects.create(
            vendor=self.vendor,
            screen_number="Hall B",
            screen_type="Standard",
            status="Active",
        )
        request = self._build_request(hall="Hall B")

        payload, status_code = services.create_show(request)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST, payload)
        self.assertIn("seat layout", str(payload.get("message") or "").lower())


class ShowLifecycleVisibilityTests(TestCase):
    """Show lifecycle visibility and booking-close behavior."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Lifecycle Vendor",
            email="lifecycle.vendor@meroticket.local",
            phone_number="9820000000",
            username="lifecycle-vendor",
            theatre="Lifecycle Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.admin = Admin.objects.create(
            email="lifecycle.admin@meroticket.local",
            phone_number="9820000001",
            username="lifecycle-admin",
            full_name="Lifecycle Admin",
            password="password",
            is_active=True,
        )
        self.admin.set_password("password")
        self.admin.save()

        self.movie = Movie.objects.create(
            title="Lifecycle Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

    def _request_for(self, user: Any):
        return type("Request", (), {"user": user, "query_params": {}})()

    def _create_show(
        self,
        *,
        hall: str,
        start_at: datetime,
        end_at: Optional[datetime] = None,
    ) -> Show:
        resolved_end = end_at or (start_at + timedelta(hours=2))
        return Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall=hall,
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=resolved_end.time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )

    def test_booking_closes_when_show_starts_in_thirty_minutes(self) -> None:
        fixed_now = timezone.make_aware(
            datetime(2026, 1, 20, 10, 0),
            timezone.get_current_timezone(),
        )
        show = self._create_show(
            hall="Hall A",
            start_at=fixed_now + timedelta(minutes=30),
        )

        with mock.patch("app.selectors.timezone.now", return_value=fixed_now), mock.patch(
            "app.services.timezone.now", return_value=fixed_now
        ):
            payload, status_code = services._ensure_show_is_bookable(show)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("30 minutes", str((payload or {}).get("message") or ""))

    def test_public_hides_ongoing_while_admin_vendor_can_view_it(self) -> None:
        fixed_now = timezone.make_aware(
            datetime(2026, 1, 20, 14, 0),
            timezone.get_current_timezone(),
        )
        running_show = self._create_show(
            hall="Hall A",
            start_at=fixed_now - timedelta(minutes=15),
            end_at=fixed_now + timedelta(minutes=45),
        )
        upcoming_show = self._create_show(
            hall="Hall B",
            start_at=fixed_now + timedelta(minutes=30),
            end_at=fixed_now + timedelta(hours=2, minutes=30),
        )

        with mock.patch("app.selectors.timezone.now", return_value=fixed_now):
            public_ids = set(selectors.list_shows(request=None).values_list("id", flat=True))
            vendor_ids = set(
                selectors.list_shows(request=self._request_for(self.vendor)).values_list(
                    "id", flat=True
                )
            )
            admin_ids = set(
                selectors.list_shows(request=self._request_for(self.admin)).values_list(
                    "id", flat=True
                )
            )

        self.assertIn(upcoming_show.id, public_ids)
        self.assertNotIn(running_show.id, public_ids)
        self.assertIn(running_show.id, vendor_ids)
        self.assertIn(running_show.id, admin_ids)

        with mock.patch("app.selectors.timezone.now", return_value=fixed_now):
            running_payload = selectors.build_show_payload(
                running_show,
                running_status_label="ongoing",
            )
        self.assertEqual(running_payload.get("status"), "ongoing")


class TimezoneConsistencyTests(TestCase):
    """Regression tests for UTC-only backend datetime handling."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Timezone Vendor",
            email="timezone.vendor@meroticket.local",
            phone_number="9811111111",
            username="timezone-vendor",
            theatre="Timezone Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(
            title="Timezone Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

    def _create_show(self, *, show_date: date, start_time: time, hall: str = "TZ Hall") -> Show:
        return Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall=hall,
            show_date=show_date,
            start_time=start_time,
            end_time=(datetime.combine(show_date, start_time) + timedelta(hours=2)).time(),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
        )

    @override_settings(USE_TZ=True, TIME_ZONE="Asia/Kathmandu")
    def test_show_start_datetime_stays_in_utc_when_active_timezone_differs(self) -> None:
        show = self._create_show(show_date=date(2026, 1, 14), start_time=time(19, 0))

        with timezone.override("Asia/Kathmandu"):
            start_dt = show.start_datetime

        self.assertTrue(timezone.is_aware(start_dt))
        self.assertEqual(start_dt.utcoffset(), timedelta(0))
        self.assertEqual((start_dt.year, start_dt.month, start_dt.day), (2026, 1, 14))
        self.assertEqual((start_dt.hour, start_dt.minute), (19, 0))

    @override_settings(USE_TZ=True, TIME_ZONE="Asia/Kathmandu")
    def test_available_show_query_uses_utc_normalization_for_non_utc_now(self) -> None:
        show = self._create_show(show_date=date(2026, 1, 14), start_time=time(19, 0), hall="Boundary Hall")

        with timezone.override("Asia/Kathmandu"):
            local_now = timezone.make_aware(datetime(2026, 1, 15, 0, 5))
            local_ids = set(selectors.list_available_shows(now=local_now).values_list("id", flat=True))

        utc_now = datetime.fromisoformat("2026-01-14T18:20:00+00:00")
        utc_ids = set(selectors.list_available_shows(now=utc_now).values_list("id", flat=True))

        self.assertIn(show.id, local_ids)
        self.assertSetEqual(local_ids, utc_ids)


class BookingDropoffTrackingTests(TestCase):
    """Drop-off tracking for booking and payment process exits."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Dropoff Vendor",
            email="dropoff.vendor@meroticket.local",
            phone_number="9830000000",
            username="dropoff-vendor",
            theatre="Dropoff Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.user = User.objects.create(
            phone_number="9830000001",
            email="dropoff.user@meroticket.local",
            username="dropoff-user",
            dob=date(1998, 1, 1),
            first_name="Drop",
            last_name="Off",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

        self.movie = Movie.objects.create(
            title="Dropoff Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        start_at = timezone.now() + timedelta(hours=2)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall A",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )
        self.screen, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

        self.seat = Seat.objects.create(
            screen=self.screen,
            row_label="A",
            seat_number="1",
            seat_type="Normal",
        )

    def test_release_booking_seats_logs_booking_dropoff(self) -> None:
        SeatAvailability.objects.create(
            seat=self.seat,
            showtime=self.showtime,
            seat_status=services.SEAT_STATUS_AVAILABLE,
            locked_until=timezone.now() + timedelta(minutes=5),
        )

        payload = {
            "movie_id": self.movie.id,
            "cinema_id": self.vendor.id,
            "date": self.show.show_date.isoformat(),
            "time": self.show.start_time.strftime("%H:%M"),
            "hall": self.show.hall,
            "selected_seats": ["A1"],
            "track_dropoff": True,
            "dropoff_stage": "BOOKING",
            "dropoff_reason": "LEFT_BOOKING_PROCESS",
        }
        request = type("Request", (), {"user": self.user, "data": payload, "query_params": {}})()

        _, status_code = services.release_booking_seats(request)

        self.assertEqual(status_code, status.HTTP_200_OK)
        event = BookingDropoffEvent.objects.order_by("-id").first()
        self.assertIsNotNone(event)
        self.assertEqual(event.stage, BookingDropoffEvent.STAGE_BOOKING)
        self.assertEqual(event.reason, BookingDropoffEvent.REASON_LEFT_BOOKING_PROCESS)
        self.assertEqual(event.vendor_id, self.vendor.id)
        self.assertEqual(event.user_id, self.user.id)
        self.assertEqual(event.seat_count, 1)

    def test_reserve_booking_seats_rejects_seat_not_in_hall_layout(self) -> None:
        payload = {
            "movie_id": self.movie.id,
            "cinema_id": self.vendor.id,
            "date": self.show.show_date.isoformat(),
            "time": self.show.start_time.strftime("%H:%M"),
            "hall": self.show.hall,
            "selected_seats": ["Z99"],
        }
        request = type("Request", (), {"user": self.user, "data": payload, "query_params": {}})()

        response_payload, status_code = services.reserve_booking_seats(request)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST, response_payload)
        self.assertIn("hall layout", str(response_payload.get("message") or "").lower())
        self.assertEqual(response_payload.get("conflicts", {}).get("invalid"), ["Z99"])

    def test_cleanup_expired_pending_bookings_logs_payment_dropoff(self) -> None:
        booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_PENDING,
            total_amount=Decimal("250.00"),
        )
        BookingSeat.objects.create(
            booking=booking,
            showtime=self.showtime,
            seat=self.seat,
            seat_price=Decimal("250.00"),
        )
        SeatAvailability.objects.create(
            seat=self.seat,
            showtime=self.showtime,
            seat_status=services.SEAT_STATUS_AVAILABLE,
            locked_until=timezone.now() + timedelta(minutes=10),
        )
        payment = Payment.objects.create(
            booking=booking,
            payment_method="ESEWA:dropoff-tx-1",
            payment_status="Pending",
            amount=Decimal("250.00"),
        )
        Payment.objects.filter(pk=payment.id).update(
            payment_date=timezone.now() - timedelta(minutes=10)
        )

        expired = services.cleanup_expired_pending_bookings(ttl_seconds=60)

        booking.refresh_from_db()
        self.assertEqual(expired, 1)
        self.assertEqual(booking.booking_status, services.BOOKING_STATUS_CANCELLED)
        self.assertTrue(
            BookingDropoffEvent.objects.filter(
                stage=BookingDropoffEvent.STAGE_PAYMENT,
                reason=BookingDropoffEvent.REASON_PAYMENT_EXPIRED,
                transaction_uuid="dropoff-tx-1",
            ).exists()
        )


class BookingPaymentIdempotencyTests(TestCase):
    """Prevent duplicate booking/ticket creation for repeated payment confirmations."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()

        self.vendor = Vendor.objects.create(
            name="Idempotency Vendor",
            email="idempotency.vendor@meroticket.local",
            phone_number="9812345600",
            username="idempotency-vendor",
            theatre="Idempotency Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.customer = User.objects.create(
            phone_number="9812345601",
            email="idempotency.customer@meroticket.local",
            username="idempotency-customer",
            dob=date(1996, 6, 6),
            first_name="Idempotent",
            last_name="Customer",
            password="password",
        )
        self.customer.set_password("password")
        self.customer.save()

        self.movie = Movie.objects.create(
            title="Idempotency Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

        start_at = timezone.now() + timedelta(hours=3)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall I",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )

        self.screen, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)
        self.seat = Seat.objects.create(
            screen=self.screen,
            row_label="A",
            seat_number="1",
            seat_type="Normal",
        )
        SeatAvailability.objects.create(
            seat=self.seat,
            showtime=self.showtime,
            seat_status=services.SEAT_STATUS_AVAILABLE,
            locked_until=timezone.now() + timedelta(minutes=10),
        )

        self.transaction_uuid = "idem-tx-001"
        self.pending_booking = Booking.objects.create(
            user=self.customer,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_PENDING,
            total_amount=Decimal("250.00"),
        )
        BookingSeat.objects.create(
            booking=self.pending_booking,
            showtime=self.showtime,
            seat=self.seat,
            seat_price=Decimal("250.00"),
        )
        self.order_payload = {
            "ticketTotal": 250,
            "booking": {
                "movie_id": self.movie.id,
                "cinema_id": self.vendor.id,
                "show_id": self.show.id,
                "date": self.show.show_date.isoformat(),
                "time": self.show.start_time.strftime("%H:%M"),
                "hall": self.show.hall,
                "selected_seats": ["A1"],
                "user_id": self.customer.id,
            },
        }
        Payment.objects.create(
            booking=self.pending_booking,
            payment_method=_pending_payment_method(self.transaction_uuid),
            transaction_uuid=self.transaction_uuid,
            metadata={"order": self.order_payload, "transaction_uuid": self.transaction_uuid},
            payment_status="Pending",
            amount=Decimal("250.00"),
        )

    def test_confirm_booking_after_payment_is_idempotent_for_same_transaction(self) -> None:
        request = self.factory.get("/api/payment/esewa/verify/")

        first_payload, first_error, first_status = _confirm_booking_after_payment(
            request,
            transaction_uuid=self.transaction_uuid,
            paid_total_amount="250",
            order=self.order_payload,
            decoded_payload={"status": "COMPLETE"},
            status_check_payload={"status": "COMPLETE"},
        )
        self.assertIsNone(first_error)
        self.assertEqual(first_status, status.HTTP_200_OK)

        second_payload, second_error, second_status = _confirm_booking_after_payment(
            request,
            transaction_uuid=self.transaction_uuid,
            paid_total_amount="250",
            order=self.order_payload,
            decoded_payload={"status": "COMPLETE"},
            status_check_payload={"status": "COMPLETE"},
        )
        self.assertIsNone(second_error)
        self.assertEqual(second_status, status.HTTP_200_OK)
        self.assertEqual(
            (first_payload or {}).get("reference"),
            (second_payload or {}).get("reference"),
        )

        self.pending_booking.refresh_from_db()
        self.assertEqual(self.pending_booking.booking_status, services.BOOKING_STATUS_CANCELLED)

        self.assertEqual(
            Booking.objects.filter(
                user=self.customer,
                showtime=self.showtime,
                booking_status=services.BOOKING_STATUS_CONFIRMED,
            ).count(),
            1,
        )
        self.assertEqual(
            Ticket.objects.filter(payload__payment__transaction_uuid=self.transaction_uuid).count(),
            1,
        )
        self.assertEqual(
            Payment.objects.filter(
                payment_method=_pending_payment_method(self.transaction_uuid),
                payment_status="Success",
            ).count(),
            1,
        )

    def test_confirm_booking_leaves_manual_review_bookings_pending(self) -> None:
        request = self.factory.get("/api/payment/esewa/verify/")

        with mock.patch(
            "app.services.assess_booking_fraud_risk",
            return_value={
                "score": 95,
                "level": Booking.FRAUD_LEVEL_CRITICAL,
                "signals": [{"code": "manual_review", "title": "Manual review required", "weight": 95}],
                "requires_manual_review": True,
            },
        ):
            payload, error, status_code = _confirm_booking_after_payment(
                request,
                transaction_uuid=self.transaction_uuid,
                paid_total_amount="250",
                order=self.order_payload,
                decoded_payload={"status": "COMPLETE"},
                status_check_payload={"status": "COMPLETE"},
            )

        self.assertIsNone(payload)
        self.assertIsNotNone(error)
        self.assertEqual(status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(bool((error or {}).get("requires_manual_review")))

        reviewed_booking_id = int((error or {}).get("booking_id") or 0)
        self.assertGreater(reviewed_booking_id, 0)
        reviewed_booking = Booking.objects.get(pk=reviewed_booking_id)
        self.assertEqual(reviewed_booking.booking_status, services.BOOKING_STATUS_PENDING)
        self.assertEqual(Ticket.objects.filter(payload__payment__transaction_uuid=self.transaction_uuid).count(), 0)

    def test_esewa_initiate_accepts_show_date_time_aliases(self) -> None:
        request = self.factory.post(
            "/api/payment/esewa/initiate/",
            {
                "amount": "250",
                "order": {
                    "ticketTotal": 250,
                    "selectedSeats": ["A1"],
                    "bookingContext": {
                        "movieId": self.movie.id,
                        "cinemaId": self.vendor.id,
                        "showDate": self.show.show_date.isoformat(),
                        "showTime": self.show.start_time.strftime("%H:%M:%S"),
                        "hall": self.show.hall,
                        "selectedSeats": ["A1"],
                        "user_id": self.customer.id,
                    },
                },
                "success_url": "http://localhost:5173/payment-success",
                "failure_url": "http://localhost:5173/payment-failure",
            },
            format="json",
        )

        response = esewa_initiate(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(str(response.data.get("transaction_uuid") or "").strip())

    def test_esewa_verify_recovers_booking_context_without_cache(self) -> None:
        cache.clear()

        callback_payload = {
            "status": "COMPLETE",
            "total_amount": "250",
            "transaction_uuid": self.transaction_uuid,
            "product_code": _esewa_product_code(),
            "signed_field_names": "total_amount,transaction_uuid,product_code",
        }
        callback_payload["signature"] = _build_signature(
            "total_amount=250,transaction_uuid=idem-tx-001,product_code=" + _esewa_product_code()
        )
        encoded_data = base64.b64encode(
            json.dumps(callback_payload).encode("utf-8")
        ).decode("utf-8")

        with mock.patch(
            "app.views.booking._esewa_status_check",
            return_value={"status": "COMPLETE", "total_amount": "250", "product_code": _esewa_product_code()},
        ):
            request = self.factory.post(
                "/api/payment/esewa/verify/",
                {"data": encoded_data},
                format="json",
            )
            response = esewa_verify(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data.get("confirmed"))
        self.assertEqual(
            Ticket.objects.filter(payload__payment__transaction_uuid=self.transaction_uuid).count(),
            1,
        )


class PaymentQrInitiationSafetyTests(TestCase):
    """Ensure QR initiation does not persist paid-looking ticket records."""

    def test_create_payment_qr_does_not_create_ticket_before_payment_verification(self) -> None:
        order = {
            "movie": {
                "title": "Initiation Safety Movie",
                "seat": "Seat No: A1",
                "venue": "Safety Hall, 2026-05-01, 07:30 PM",
            },
            "ticketTotal": 450,
            "foodTotal": 0,
            "total": 450,
            "items": [],
        }

        request = type(
            "Request",
            (),
            {
                "data": {"order": order},
                "build_absolute_uri": staticmethod(lambda path="": f"http://testserver{path}"),
            },
        )()

        payload, status_code = services.create_payment_qr(request)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(payload.get("payment_status"), "PENDING")
        self.assertIsNone(payload.get("ticket_id"))
        self.assertIsNone(payload.get("token"))
        self.assertIsNone(payload.get("download_url"))
        self.assertIsNone(payload.get("details_url"))
        self.assertTrue(str(payload.get("reference") or "").strip())
        self.assertTrue(str(payload.get("message") or "").lower().startswith("payment initiated"))


class UserWalletTopupEsewaTests(TestCase):
    """Customer wallet top-up eSewa initiate and verify behavior."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.customer = User.objects.create(
            phone_number="9815555501",
            email="wallet.topup@meroticket.local",
            username="wallet-topup-user",
            dob=date(1997, 3, 3),
            first_name="Wallet",
            last_name="Topup",
            password="password",
        )
        self.customer.set_password("password")
        self.customer.save()

    def _auth_headers(self, user: User) -> dict[str, str]:
        token = issue_access_token("customer", user.id)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_esewa_verify_credits_user_wallet_once(self) -> None:
        initiate_request = self.factory.post(
            "/api/user/wallet/topup/esewa/initiate/",
            {"amount": "500"},
            format="json",
            **self._auth_headers(self.customer),
        )
        initiate_response = user_wallet_topup_esewa_initiate(initiate_request)

        self.assertEqual(initiate_response.status_code, status.HTTP_200_OK)
        initiate_payload = dict(initiate_response.data)
        transaction_uuid = str(initiate_payload.get("transaction_uuid") or "")
        total_amount = str(initiate_payload.get("total_amount") or "")
        product_code = str(initiate_payload.get("product_code") or _esewa_product_code())
        signed_field_names = str(initiate_payload.get("signed_field_names") or "")

        signature_message = (
            f"total_amount={total_amount},"
            f"transaction_uuid={transaction_uuid},"
            f"product_code={product_code}"
        )
        callback_payload = {
            "status": "COMPLETE",
            "total_amount": total_amount,
            "transaction_uuid": transaction_uuid,
            "product_code": product_code,
            "signed_field_names": signed_field_names,
            "signature": _build_signature(signature_message),
        }
        encoded_data = base64.b64encode(
            json.dumps(callback_payload).encode("utf-8")
        ).decode("utf-8")

        status_check_payload = {
            "status": "COMPLETE",
            "total_amount": total_amount,
            "product_code": product_code,
        }
        with mock.patch("app.views.booking._esewa_status_check", return_value=status_check_payload):
            verify_request = self.factory.post(
                "/api/user/wallet/topup/esewa/verify/",
                {"data": encoded_data},
                format="json",
                **self._auth_headers(self.customer),
            )
            first_verify = user_wallet_topup_esewa_verify(verify_request)

        self.assertEqual(first_verify.status_code, status.HTTP_200_OK, first_verify.data)
        self.assertTrue(first_verify.data.get("credited"))
        self.assertFalse(first_verify.data.get("already_processed"))

        wallet = UserWallet.objects.get(user=self.customer)
        self.assertEqual(wallet.balance, Decimal("500.00"))
        self.assertEqual(wallet.total_credited, Decimal("500.00"))

        with mock.patch("app.views.booking._esewa_status_check", return_value=status_check_payload):
            verify_request = self.factory.post(
                "/api/user/wallet/topup/esewa/verify/",
                {"data": encoded_data},
                format="json",
                **self._auth_headers(self.customer),
            )
            second_verify = user_wallet_topup_esewa_verify(verify_request)

        self.assertEqual(second_verify.status_code, status.HTTP_200_OK, second_verify.data)
        self.assertTrue(second_verify.data.get("credited"))
        self.assertTrue(second_verify.data.get("already_processed"))

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("500.00"))
        self.assertEqual(
            UserWalletTransaction.objects.filter(
                user=self.customer,
                transaction_type=UserWalletTransaction.TYPE_TOPUP,
                status=UserWalletTransaction.STATUS_COMPLETED,
                reference_id=transaction_uuid,
            ).count(),
            1,
        )

    def test_esewa_verify_recovers_wallet_topup_without_cache(self) -> None:
        initiate_request = self.factory.post(
            "/api/user/wallet/topup/esewa/initiate/",
            {"amount": "500"},
            format="json",
            **self._auth_headers(self.customer),
        )
        initiate_response = user_wallet_topup_esewa_initiate(initiate_request)

        initiate_payload = dict(initiate_response.data)
        transaction_uuid = str(initiate_payload.get("transaction_uuid") or "")
        total_amount = str(initiate_payload.get("total_amount") or "")
        product_code = str(initiate_payload.get("product_code") or _esewa_product_code())
        signed_field_names = str(initiate_payload.get("signed_field_names") or "")

        callback_payload = {
            "status": "COMPLETE",
            "total_amount": total_amount,
            "transaction_uuid": transaction_uuid,
            "product_code": product_code,
            "signed_field_names": signed_field_names,
        }
        callback_payload["signature"] = _build_signature(
            f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
        )
        encoded_data = base64.b64encode(
            json.dumps(callback_payload).encode("utf-8")
        ).decode("utf-8")

        cache.clear()
        status_check_payload = {
            "status": "COMPLETE",
            "total_amount": total_amount,
            "product_code": product_code,
        }
        with mock.patch("app.views.booking._esewa_status_check", return_value=status_check_payload):
            verify_request = self.factory.post(
                "/api/user/wallet/topup/esewa/verify/",
                {"data": encoded_data},
                format="json",
                **self._auth_headers(self.customer),
            )
            verify_response = user_wallet_topup_esewa_verify(verify_request)

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK, verify_response.data)
        self.assertTrue(verify_response.data.get("credited"))
        self.assertTrue(verify_response.data.get("confirmed", True))

        wallet = UserWallet.objects.get(user=self.customer)
        self.assertEqual(wallet.balance, Decimal("500.00"))
        self.assertEqual(
            UserWalletTransaction.objects.filter(
                user=self.customer,
                transaction_type=UserWalletTransaction.TYPE_TOPUP,
                status=UserWalletTransaction.STATUS_COMPLETED,
                reference_id=transaction_uuid,
            ).count(),
            1,
        )

    def test_user_wallet_alias_returns_cash_wallet_payload(self) -> None:
        wallet = UserWallet.objects.create(
            user=self.customer,
            balance=Decimal("220.00"),
            total_credited=Decimal("300.00"),
            total_debited=Decimal("80.00"),
        )
        UserWalletTransaction.objects.create(
            wallet=wallet,
            user=self.customer,
            transaction_type=UserWalletTransaction.TYPE_TOPUP,
            status=UserWalletTransaction.STATUS_COMPLETED,
            amount=Decimal("300.00"),
            reference_id="wallet-topup-001",
            provider="ESEWA",
            processed_at=timezone.now(),
        )

        request = self.factory.get(
            "/api/user/wallet/",
            **self._auth_headers(self.customer),
        )
        response = user_wallet(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("cash_wallet", response.data)
        self.assertIn("cash_wallet_recent_transactions", response.data)
        self.assertEqual(response.data.get("cash_wallet", {}).get("balance"), 220.0)
        self.assertEqual(len(response.data.get("cash_wallet_recent_transactions") or []), 1)


class UserWalletBookingPaymentTests(TestCase):
    """Customer booking payment with project cash wallet."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()

        self.customer = User.objects.create(
            phone_number="9815555601",
            email="wallet.booking@meroticket.local",
            username="wallet-booking-user",
            dob=date(1995, 5, 5),
            first_name="Wallet",
            last_name="Booking",
            password="password",
        )
        self.customer.set_password("password")
        self.customer.save()

        self.other_user = User.objects.create(
            phone_number="9815555602",
            email="wallet.booking.other@meroticket.local",
            username="wallet-booking-other",
            dob=date(1994, 4, 4),
            first_name="Other",
            last_name="User",
            password="password",
        )
        self.other_user.set_password("password")
        self.other_user.save()

        self.vendor = Vendor.objects.create(
            name="Wallet Booking Vendor",
            email="wallet.booking.vendor@meroticket.local",
            phone_number="9815555603",
            username="wallet-booking-vendor",
            theatre="Wallet Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(
            title="Wallet Booking Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        start_at = timezone.now() + timedelta(hours=4)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall W",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )

        self.screen, self.showtime = services._get_or_create_showtime_for_context(
            self.show,
            self.show.hall,
        )
        self.seat = Seat.objects.create(
            screen=self.screen,
            row_label="A",
            seat_number="1",
            seat_type="Normal",
        )
        SeatAvailability.objects.create(
            seat=self.seat,
            showtime=self.showtime,
            seat_status=services.SEAT_STATUS_AVAILABLE,
            locked_until=timezone.now() + timedelta(minutes=10),
        )

    def _auth_headers(self, user: User) -> dict[str, str]:
        token = issue_access_token("customer", user.id)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _build_order_payload(self, *, user_id: int, total_amount: str = "250") -> dict[str, Any]:
        return {
            "ticketTotal": 250,
            "total": float(total_amount),
            "movie": {
                "title": self.movie.title,
                "language": "Nepali",
                "runtime": "2h",
            },
            "booking": {
                "movie_id": self.movie.id,
                "cinema_id": self.vendor.id,
                "show_id": self.show.id,
                "date": self.show.show_date.isoformat(),
                "time": self.show.start_time.strftime("%H:%M"),
                "hall": self.show.hall,
                "selected_seats": ["A1"],
                "user_id": user_id,
            },
        }

    def test_wallet_payment_confirms_booking_and_debits_cash_wallet(self) -> None:
        wallet = UserWallet.objects.create(
            user=self.customer,
            balance=Decimal("600.00"),
            total_credited=Decimal("600.00"),
            total_debited=Decimal("0.00"),
        )

        request = self.factory.post(
            "/api/user/wallet/booking/pay/",
            {"order": self._build_order_payload(user_id=self.customer.id)},
            format="json",
            **self._auth_headers(self.customer),
        )
        response = user_wallet_booking_pay(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data.get("payment_method"), "USER_WALLET")
        self.assertTrue(response.data.get("ticket"))

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("350.00"))
        self.assertEqual(wallet.total_debited, Decimal("250.00"))

        booking = Booking.objects.get(user=self.customer, showtime=self.showtime)
        self.assertEqual(booking.booking_status, services.BOOKING_STATUS_CONFIRMED)

        payment = Payment.objects.get(booking=booking)
        self.assertEqual(payment.payment_method, "USER_WALLET")
        self.assertEqual(payment.payment_status, "Success")
        self.assertEqual(payment.amount, Decimal("250.00"))

        wallet_tx = UserWalletTransaction.objects.get(booking=booking)
        self.assertEqual(wallet_tx.transaction_type, UserWalletTransaction.TYPE_DEBIT)
        self.assertEqual(wallet_tx.status, UserWalletTransaction.STATUS_COMPLETED)
        self.assertEqual(wallet_tx.amount, Decimal("250.00"))

        self.assertEqual(Ticket.objects.count(), 1)

    def test_wallet_payment_uses_authenticated_customer_not_payload_user(self) -> None:
        UserWallet.objects.create(
            user=self.customer,
            balance=Decimal("600.00"),
            total_credited=Decimal("600.00"),
            total_debited=Decimal("0.00"),
        )

        request = self.factory.post(
            "/api/user/wallet/booking/pay/",
            {"order": self._build_order_payload(user_id=self.other_user.id)},
            format="json",
            **self._auth_headers(self.customer),
        )
        response = user_wallet_booking_pay(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        booking = Booking.objects.get(showtime=self.showtime)
        self.assertEqual(booking.user_id, self.customer.id)

    def test_wallet_payment_rejects_when_balance_is_insufficient_without_creating_booking(self) -> None:
        wallet = UserWallet.objects.create(
            user=self.customer,
            balance=Decimal("100.00"),
            total_credited=Decimal("100.00"),
            total_debited=Decimal("0.00"),
        )

        request = self.factory.post(
            "/api/user/wallet/booking/pay/",
            {"order": self._build_order_payload(user_id=self.customer.id)},
            format="json",
            **self._auth_headers(self.customer),
        )
        response = user_wallet_booking_pay(request)

        self.assertEqual(response.status_code, status.HTTP_402_PAYMENT_REQUIRED, response.data)
        self.assertIn("Insufficient wallet balance", str(response.data.get("message") or ""))

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))
        self.assertEqual(wallet.total_debited, Decimal("0.00"))

        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(UserWalletTransaction.objects.count(), 0)


class VendorHallManagementTests(TestCase):
    """Auto-generated vendor hall naming behavior."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Hall Vendor",
            email="hall.vendor@meroticket.local",
            phone_number="9811111111",
            username="hall-vendor",
            theatre="Hall Theatre",
            city="Pokhara",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

    def _build_request(self, payload: Optional[dict[str, Any]] = None):
        return type(
            "Request",
            (),
            {
                "user": self.vendor,
                "data": payload or {},
                "query_params": {},
            },
        )()

    def test_create_vendor_hall_generates_alphabetical_sequence(self) -> None:
        request_one = self._build_request()
        payload_one, status_one = services.create_vendor_hall(request_one)

        request_two = self._build_request()
        payload_two, status_two = services.create_vendor_hall(request_two)

        self.assertEqual(status_one, status.HTTP_201_CREATED, payload_one)
        self.assertEqual(status_two, status.HTTP_201_CREATED, payload_two)
        self.assertEqual(payload_one.get("hall", {}).get("hall"), "Hall A")
        self.assertEqual(payload_two.get("hall", {}).get("hall"), "Hall B")

    def test_create_vendor_hall_seeds_layout_from_requested_dimensions(self) -> None:
        request = self._build_request(
            {
                "rows": 6,
                "columns": 8,
                "category_rows": {
                    "normal": 2,
                    "executive": 2,
                    "premium": 1,
                    "vip": 1,
                },
            }
        )

        payload, status_code = services.create_vendor_hall(request)

        self.assertEqual(status_code, status.HTTP_201_CREATED, payload)
        hall_name = payload.get("hall", {}).get("hall")
        self.assertEqual(payload.get("hall", {}).get("total_rows"), 6)
        self.assertEqual(payload.get("hall", {}).get("total_columns"), 8)
        self.assertEqual(payload.get("hall", {}).get("seat_count"), 48)

        screen = Screen.objects.get(vendor=self.vendor, screen_number=hall_name)
        self.assertEqual(Seat.objects.filter(screen=screen).count(), 48)

    def test_update_vendor_seat_layout_keeps_existing_grid_when_only_prices_change(self) -> None:
        create_payload, create_status = services.create_vendor_hall(
            self._build_request({"rows": 4, "columns": 6})
        )
        self.assertEqual(create_status, status.HTTP_201_CREATED, create_payload)
        hall_name = create_payload.get("hall", {}).get("hall")

        update_payload, update_status = services.create_or_update_vendor_seat_layout(
            self._build_request(
                {
                    "hall": hall_name,
                    "category_prices": {
                        "normal": 300,
                        "executive": 450,
                        "premium": 600,
                        "vip": 800,
                    },
                }
            )
        )

        self.assertEqual(update_status, status.HTTP_200_OK, update_payload)
        self.assertEqual(update_payload.get("total_rows"), 4)
        self.assertEqual(update_payload.get("total_columns"), 6)

        screen = Screen.objects.get(vendor=self.vendor, screen_number=hall_name)
        self.assertEqual(Seat.objects.filter(screen=screen).count(), 24)


class LoyaltyLifecycleTests(TestCase):
    """Loyalty earn/redeem/reverse/expiry behavior coverage."""

    def setUp(self) -> None:
        self.user = User.objects.create(
            phone_number="9840000001",
            email="loyalty.user@meroticket.local",
            username="loyalty-user",
            dob=date(1996, 1, 1),
            first_name="Loyalty",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

        self.vendor = Vendor.objects.create(
            name="Loyalty Vendor",
            email="loyalty.vendor@meroticket.local",
            phone_number="9840000002",
            username="loyalty-vendor",
            theatre="Loyalty Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(
            title="Loyalty Feature Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        start_at = timezone.now() + timedelta(hours=3)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall L",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)
        self.booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status="Pending",
            total_amount=Decimal("250.00"),
        )

    def test_preview_checkout_redemption_rejects_insufficient_points(self) -> None:
        UserLoyaltyWallet.objects.create(
            user=self.user,
            available_points=40,
            total_points=40,
            lifetime_points=40,
            tier=UserLoyaltyWallet.TIER_SILVER,
        )
        reward = Reward.objects.create(
            vendor=self.vendor,
            title="Rs 100 Reward",
            reward_type=Reward.TYPE_DISCOUNT,
            points_required=100,
            discount_amount=Decimal("100.00"),
            is_active=True,
        )

        preview, error, status_code = loyalty.preview_checkout_redemption(
            self.user,
            {
                "subtotal": "500.00",
                "reward_id": reward.id,
                "vendor_id": self.vendor.id,
                "points": 0,
            },
        )

        self.assertIsNone(preview)
        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error.get("required_points"), 100)
        self.assertEqual(error.get("available_points"), 40)

    def test_apply_referral_bonus_rejects_own_referral_code(self) -> None:
        services.ensure_user_referral_code(self.user)

        request = type(
            "Request",
            (),
            {
                "user": self.user,
                "data": {"referral_code": self.user.referral_code},
            },
        )()

        payload, status_code = loyalty.apply_referral_bonus(request)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST, payload)
        self.assertEqual(payload.get("message"), "You cannot use your own referral code.")
        self.assertFalse(
            LoyaltyTransaction.objects.filter(
                user=self.user,
                reference_type=LoyaltyTransaction.REFERENCE_REFERRAL,
                reference_id=self.user.referral_code,
            ).exists()
        )

    def test_consume_checkout_redemption_updates_wallet_booking_and_reward(self) -> None:
        wallet = UserLoyaltyWallet.objects.create(
            user=self.user,
            available_points=500,
            total_points=500,
            lifetime_points=500,
            tier=UserLoyaltyWallet.TIER_SILVER,
        )
        reward = Reward.objects.create(
            vendor=self.vendor,
            title="Rs 50 Reward",
            reward_type=Reward.TYPE_DISCOUNT,
            points_required=100,
            discount_amount=Decimal("50.00"),
            is_active=True,
        )

        preview, error, status_code = loyalty.preview_checkout_redemption(
            self.user,
            {
                "subtotal": "300.00",
                "reward_id": reward.id,
                "vendor_id": self.vendor.id,
                "points": 25,
            },
        )
        self.assertIsNone(error)
        self.assertEqual(status_code, status.HTTP_200_OK)

        consume_payload, consume_status = loyalty.consume_checkout_redemption(
            user=self.user,
            booking=self.booking,
            preview=preview or {},
        )

        self.assertEqual(consume_status, status.HTTP_200_OK)
        self.assertEqual(consume_payload.get("points_used"), 125)
        self.assertEqual(Decimal(str(consume_payload.get("discount_amount"))), Decimal("75.00"))

        wallet.refresh_from_db()
        self.booking.refresh_from_db()
        reward.refresh_from_db()

        self.assertEqual(wallet.available_points, 375)
        self.assertEqual(wallet.total_points, 375)
        self.assertEqual(self.booking.loyalty_points_redeemed, 125)
        self.assertEqual(self.booking.loyalty_discount_amount, Decimal("75.00"))
        self.assertIsNotNone(self.booking.reward_redemption)
        self.assertEqual(reward.redeemed_count, 1)
        self.assertTrue(
            LoyaltyTransaction.objects.filter(
                user=self.user,
                transaction_type=LoyaltyTransaction.TYPE_REDEEM,
                reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
                reference_id=str(self.booking.id),
            ).exists()
        )

    def test_award_booking_points_applies_first_booking_bonus_and_is_idempotent(self) -> None:
        first_award = loyalty.award_booking_points(self.booking)
        second_award = loyalty.award_booking_points(self.booking)

        config = loyalty.get_program_config()
        expected_points = int(Decimal("250.00") / Decimal(str(config.points_per_currency_unit or 1))) + int(
            config.first_booking_bonus or 0
        )

        self.assertEqual(first_award, expected_points)
        self.assertEqual(second_award, 0)

        wallet = UserLoyaltyWallet.objects.get(user=self.user)
        self.assertEqual(wallet.available_points, expected_points)
        self.assertEqual(wallet.lifetime_points, expected_points)
        self.assertEqual(
            LoyaltyTransaction.objects.filter(
                user=self.user,
                transaction_type=LoyaltyTransaction.TYPE_EARN,
                reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
                reference_id=str(self.booking.id),
            ).count(),
            1,
        )

    def test_reverse_booking_points_reverses_earn_and_restores_redeemed_points(self) -> None:
        earned_points = loyalty.award_booking_points(self.booking)
        reward = Reward.objects.create(
            vendor=self.vendor,
            title="Used Reward",
            reward_type=Reward.TYPE_DISCOUNT,
            points_required=30,
            discount_amount=Decimal("30.00"),
            redeemed_count=1,
            is_active=True,
        )
        redemption = RewardRedemption.objects.create(
            user=self.user,
            reward=reward,
            points_used=30,
            booking=self.booking,
            status=RewardRedemption.STATUS_USED,
            used_at=timezone.now(),
        )
        self.booking.loyalty_points_redeemed = 30
        self.booking.reward_redemption = redemption
        self.booking.save(update_fields=["loyalty_points_redeemed", "reward_redemption"])

        result = loyalty.reverse_booking_points(self.booking, reason="test-cancel")

        self.assertEqual(result.get("reversed_points"), earned_points)
        self.assertEqual(result.get("restored_points"), 30)

        wallet = UserLoyaltyWallet.objects.get(user=self.user)
        self.assertEqual(wallet.available_points, 30)
        self.assertEqual(wallet.lifetime_points, earned_points)

        redemption.refresh_from_db()
        reward.refresh_from_db()
        self.assertEqual(redemption.status, RewardRedemption.STATUS_CANCELLED)
        self.assertEqual(reward.redeemed_count, 0)

        second = loyalty.reverse_booking_points(self.booking, reason="repeat")
        self.assertEqual(second.get("reversed_points"), 0)
        self.assertEqual(second.get("restored_points"), 0)

    def test_expire_points_marks_earn_transaction_and_deducts_wallet(self) -> None:
        wallet = UserLoyaltyWallet.objects.create(
            user=self.user,
            available_points=100,
            total_points=100,
            lifetime_points=100,
            tier=UserLoyaltyWallet.TIER_SILVER,
        )
        earn_tx = LoyaltyTransaction.objects.create(
            wallet=wallet,
            user=self.user,
            transaction_type=LoyaltyTransaction.TYPE_EARN,
            points=40,
            reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
            reference_id=str(self.booking.id),
            expires_at=timezone.now() - timedelta(days=1),
            is_expired=False,
        )

        result = loyalty.expire_points(now=timezone.now())

        wallet.refresh_from_db()
        earn_tx.refresh_from_db()
        self.assertEqual(result.get("expired_transactions"), 1)
        self.assertEqual(result.get("expired_points"), 40)
        self.assertEqual(wallet.available_points, 60)
        self.assertEqual(wallet.total_points, 60)
        self.assertTrue(earn_tx.is_expired)
        self.assertTrue(
            LoyaltyTransaction.objects.filter(
                user=self.user,
                transaction_type=LoyaltyTransaction.TYPE_EXPIRE,
                reference_type=LoyaltyTransaction.REFERENCE_SYSTEM,
                reference_id=str(earn_tx.id),
            ).exists()
        )

    def test_wallet_snapshot_downgrades_tier_when_points_window_expires(self) -> None:
        config = loyalty.get_program_config()
        config.tier_gold_threshold = 100
        config.tier_points_window_months = 1
        config.save(update_fields=["tier_gold_threshold", "tier_points_window_months", "updated_at"])

        wallet = UserLoyaltyWallet.objects.create(
            user=self.user,
            available_points=300,
            total_points=300,
            lifetime_points=300,
            tier=UserLoyaltyWallet.TIER_GOLD,
        )
        old_tx = LoyaltyTransaction.objects.create(
            wallet=wallet,
            user=self.user,
            transaction_type=LoyaltyTransaction.TYPE_EARN,
            points=250,
            reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
            reference_id=str(self.booking.id),
        )
        LoyaltyTransaction.objects.filter(id=old_tx.id).update(created_at=timezone.now() - timedelta(days=45))

        snapshot = loyalty.get_wallet_snapshot(self.user, use_cache=False)
        wallet.refresh_from_db()
        self.assertEqual(snapshot.get("tier"), UserLoyaltyWallet.TIER_SILVER)
        self.assertEqual(wallet.tier, UserLoyaltyWallet.TIER_SILVER)

    def test_preview_checkout_redemption_blocks_when_daily_points_cap_exceeded(self) -> None:
        config = loyalty.get_program_config()
        config.daily_redemption_points_cap = 100
        config.save(update_fields=["daily_redemption_points_cap", "updated_at"])

        wallet = UserLoyaltyWallet.objects.create(
            user=self.user,
            available_points=500,
            total_points=500,
            lifetime_points=500,
            tier=UserLoyaltyWallet.TIER_SILVER,
        )
        LoyaltyTransaction.objects.create(
            wallet=wallet,
            user=self.user,
            transaction_type=LoyaltyTransaction.TYPE_REDEEM,
            points=90,
            reference_type=LoyaltyTransaction.REFERENCE_SYSTEM,
            reference_id="seed",
        )

        preview, error, status_code = loyalty.preview_checkout_redemption(
            self.user,
            {
                "subtotal": "300.00",
                "points": 20,
            },
        )

        self.assertIsNone(preview)
        self.assertEqual(status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("cap", str((error or {}).get("message") or "").lower())

    def test_redeem_reward_blocks_on_reward_cooldown(self) -> None:
        config = loyalty.get_program_config()
        config.reward_redeem_cooldown_minutes = 60
        config.save(update_fields=["reward_redeem_cooldown_minutes", "updated_at"])

        wallet = UserLoyaltyWallet.objects.create(
            user=self.user,
            available_points=500,
            total_points=500,
            lifetime_points=500,
            tier=UserLoyaltyWallet.TIER_SILVER,
        )
        reward = Reward.objects.create(
            vendor=self.vendor,
            title="Cooldown Reward",
            reward_type=Reward.TYPE_DISCOUNT,
            points_required=100,
            discount_amount=Decimal("40.00"),
            is_active=True,
        )
        RewardRedemption.objects.create(
            user=self.user,
            reward=reward,
            points_used=100,
            status=RewardRedemption.STATUS_UNUSED,
            expires_at=timezone.now() + timedelta(days=7),
        )

        request = type(
            "Request",
            (),
            {
                "user": self.user,
                "data": {"reward_id": reward.id},
            },
        )()
        payload, status_code = loyalty.redeem_reward_for_customer(request)

        self.assertEqual(status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("cooldown", str(payload.get("message") or "").lower())


class ReferralWalletLifecycleTests(TestCase):
    """Referral signup, reward trigger, and wallet credit/debit coverage."""

    def setUp(self) -> None:
        self.referrer = User.objects.create(
            phone_number="9850000101",
            email="referrer@meroticket.local",
            username="referrer-user",
            dob=date(1992, 1, 1),
            first_name="Ref",
            last_name="Errer",
            password="password",
        )
        self.referrer.set_password("password")
        self.referrer.save()
        services.ensure_user_referral_code(self.referrer)

        self.customer = User.objects.create(
            phone_number="9850000102",
            email="customer@meroticket.local",
            username="customer-user",
            dob=date(1995, 1, 1),
            first_name="Cus",
            last_name="Tomer",
            password="password",
        )
        self.customer.set_password("password")
        self.customer.save()
        services.ensure_user_referral_code(self.customer)

        self.vendor = Vendor.objects.create(
            name="Referral Vendor",
            email="ref.vendor@meroticket.local",
            phone_number="9850000103",
            username="ref-vendor",
            theatre="Referral Theatre",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(
            title="Referral Wallet Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        start_at = timezone.now() + timedelta(hours=4)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall R",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

    def test_referral_anti_fraud_blocks_same_ip_and_device(self) -> None:
        self.referrer.signup_ip_address = "10.20.30.40"
        self.referrer.signup_device_fingerprint = "device-referrer"
        self.referrer.save(update_fields=["signup_ip_address", "signup_device_fingerprint"])

        blocked_ip_reason = services._referral_anti_fraud_reason(
            referrer=self.referrer,
            signup_email="new-user@meroticket.local",
            signup_phone="9850000999",
            signup_ip="10.20.30.40",
            signup_device_fingerprint="device-new",
        )
        blocked_device_reason = services._referral_anti_fraud_reason(
            referrer=self.referrer,
            signup_email="new-user@meroticket.local",
            signup_phone="9850000999",
            signup_ip="10.20.30.41",
            signup_device_fingerprint="device-referrer",
        )

        self.assertIn("same IP", blocked_ip_reason or "")
        self.assertIn("same device", blocked_device_reason or "")

    def test_referral_reward_is_held_before_spendable(self) -> None:
        ReferralPolicy.objects.update_or_create(
            key="default",
            defaults={
                "referrer_reward_amount": Decimal("120.00"),
                "referred_reward_amount": Decimal("60.00"),
                "reward_hold_period_days": 5,
                "reward_expiry_days": 30,
                "wallet_cap_percent": Decimal("20.00"),
                "max_signups_per_ip_per_day": 3,
                "max_signups_per_device_per_day": 2,
                "auto_approve_rewards": True,
                "is_active": True,
            },
        )

        referral = Referral.objects.create(
            referrer=self.referrer,
            referred_user=self.customer,
            referral_code=self.referrer.referral_code,
            status=Referral.STATUS_PENDING,
            expires_at=timezone.now() + timedelta(days=30),
        )
        booking = Booking.objects.create(
            user=self.customer,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("250.00"),
        )

        result = services.process_referral_reward_for_booking(booking)
        self.assertTrue(result.get("awarded"), result)

        transaction_row = ReferralTransaction.objects.get(
            referral=referral,
            user=self.referrer,
            reason=ReferralTransaction.REASON_REFERRER_REWARD,
        )
        self.assertIsNotNone(transaction_row.available_at)
        self.assertGreater(transaction_row.available_at, timezone.now())

        wallet_snapshot = services.get_referral_wallet_snapshot(self.referrer, use_cache=False)
        self.assertGreater(wallet_snapshot.get("balance", 0), 0)
        self.assertEqual(wallet_snapshot.get("spendable_balance"), 0.0)
        self.assertGreater(wallet_snapshot.get("locked_balance", 0), 0)

    def test_register_user_with_referral_code_rewards_referrer_immediately(self) -> None:
        OTPVerification.objects.create(
            email="new.referral@meroticket.local",
            otp="123456",
            is_verified=True,
        )

        request = type(
            "Request",
            (),
            {
                "data": {
                    "phone_number": "9850000104",
                    "email": "new.referral@meroticket.local",
                    "dob": "1998-02-10",
                    "first_name": "New",
                    "last_name": "User",
                    "password": "StrongPass123",
                    "confirm_password": "StrongPass123",
                    "referral_code": self.referrer.referral_code,
                },
                "META": {
                    "REMOTE_ADDR": "10.10.10.10",
                    "HTTP_USER_AGENT": "pytest-referral",
                    "HTTP_X_DEVICE_FINGERPRINT": "device-a",
                },
            },
        )()

        payload, status_code = services.register_user(request)

        self.assertEqual(status_code, status.HTTP_201_CREATED, payload)
        self.assertTrue(payload.get("referral", {}).get("applied"))
        created_user = User.objects.get(email="new.referral@meroticket.local")
        self.assertTrue(created_user.referral_code)

        referral = Referral.objects.get(referred_user=created_user)
        self.assertEqual(referral.referrer_id, self.referrer.id)
        self.assertEqual(referral.status, Referral.STATUS_REWARDED)

        signup_reward = services._referral_signup_reward_amount()
        referrer_wallet = ReferralWallet.objects.get(user=self.referrer)
        self.assertEqual(referrer_wallet.balance, signup_reward)
        self.assertTrue(
            ReferralTransaction.objects.filter(
                referral=referral,
                user=self.referrer,
                reason=ReferralTransaction.REASON_REFERRER_REWARD,
                transaction_type=ReferralTransaction.TYPE_CREDIT,
                status=ReferralTransaction.STATUS_COMPLETED,
            ).exists()
        )

    def test_process_referral_reward_for_first_successful_booking(self) -> None:
        referral = Referral.objects.create(
            referrer=self.referrer,
            referred_user=self.customer,
            referral_code=self.referrer.referral_code,
            status=Referral.STATUS_PENDING,
            expires_at=timezone.now() + timedelta(days=30),
        )
        booking = Booking.objects.create(
            user=self.customer,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("250.00"),
        )

        first = services.process_referral_reward_for_booking(booking)
        second = services.process_referral_reward_for_booking(booking)

        referrer_amount, referred_amount = services._referral_reward_amounts()
        self.assertTrue(first.get("awarded"), first)
        self.assertFalse(second.get("awarded"), second)

        referral.refresh_from_db()
        self.assertEqual(referral.status, Referral.STATUS_REWARDED)
        self.assertEqual(referral.reward_trigger_booking_id, booking.id)

        referrer_wallet = ReferralWallet.objects.get(user=self.referrer)
        referred_wallet = ReferralWallet.objects.get(user=self.customer)
        self.assertEqual(referrer_wallet.balance, referrer_amount)
        self.assertEqual(referred_wallet.balance, referred_amount)

        self.assertEqual(
            ReferralTransaction.objects.filter(
                referral=referral,
                reason=ReferralTransaction.REASON_REFERRER_REWARD,
                transaction_type=ReferralTransaction.TYPE_CREDIT,
            ).count(),
            1,
        )
        self.assertEqual(
            ReferralTransaction.objects.filter(
                referral=referral,
                reason=ReferralTransaction.REASON_REFERRED_REWARD,
                transaction_type=ReferralTransaction.TYPE_CREDIT,
            ).count(),
            1,
        )

    def test_preview_referral_wallet_checkout_applies_cap(self) -> None:
        ReferralWallet.objects.create(
            user=self.customer,
            balance=Decimal("500.00"),
            total_credited=Decimal("500.00"),
        )
        request = type(
            "Request",
            (),
            {
                "user": self.customer,
                "data": {
                    "subtotal": "400",
                    "requested_amount": "300",
                    "use_referral_wallet": True,
                },
                "query_params": {},
                "META": {},
            },
        )()

        payload, status_code = services.preview_customer_referral_wallet_checkout(request)

        self.assertEqual(status_code, status.HTTP_200_OK, payload)
        self.assertEqual(payload.get("preview", {}).get("applied_amount"), 80.0)
        self.assertEqual(payload.get("preview", {}).get("cap_percent"), 20.0)

    def test_booking_flow_debits_and_refunds_referral_wallet(self) -> None:
        ReferralWallet.objects.create(
            user=self.customer,
            balance=Decimal("500.00"),
            total_credited=Decimal("500.00"),
        )

        order_payload = {
            "ticketTotal": 250,
            "use_referral_wallet": True,
            "referral_wallet_amount": 120,
            "booking": {
                "movie_id": self.movie.id,
                "cinema_id": self.vendor.id,
                "show_id": self.show.id,
                "date": self.show.show_date.isoformat(),
                "time": self.show.start_time.strftime("%H:%M"),
                "hall": self.show.hall,
                "selected_seats": ["A1"],
                "user_id": self.customer.id,
            },
        }

        booking_payload, booking_error, booking_status = services._create_booking_from_order(order_payload)

        self.assertIsNone(booking_error)
        self.assertEqual(booking_status, status.HTTP_201_CREATED)
        booking = Booking.objects.get(pk=booking_payload.get("booking_id"))
        self.assertEqual(booking.referral_wallet_used_amount, Decimal("50.00"))

        wallet = ReferralWallet.objects.get(user=self.customer)
        self.assertEqual(wallet.balance, Decimal("450.00"))
        self.assertTrue(
            ReferralTransaction.objects.filter(
                booking=booking,
                user=self.customer,
                reason=ReferralTransaction.REASON_BOOKING_WALLET_USE,
                transaction_type=ReferralTransaction.TYPE_DEBIT,
            ).exists()
        )

        reversal_result = services.reverse_referral_effects_for_booking(booking, reason="test-cancel")
        booking.refresh_from_db()
        wallet.refresh_from_db()

        self.assertEqual(reversal_result.get("wallet_refund_amount"), 50.0)
        self.assertEqual(booking.referral_wallet_refunded_amount, Decimal("50.00"))
        self.assertEqual(wallet.balance, Decimal("500.00"))
        self.assertTrue(
            ReferralTransaction.objects.filter(
                booking=booking,
                user=self.customer,
                reason=ReferralTransaction.REASON_BOOKING_WALLET_REFUND,
                transaction_type=ReferralTransaction.TYPE_CREDIT,
            ).exists()
        )


class SubscriptionLifecycleTests(TestCase):
    """Subscription purchase, upgrade, booking usage, and reversal coverage."""

    def setUp(self) -> None:
        self.user = User.objects.create(
            phone_number="9860000001",
            email="subscription.user@meroticket.local",
            username="subscription-user",
            dob=date(1994, 2, 2),
            first_name="Subscription",
            last_name="User",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

        self.vendor = Vendor.objects.create(
            name="Subscription Vendor",
            email="subscription.vendor@meroticket.local",
            phone_number="9860000002",
            username="subscription-vendor",
            theatre="Subscription Hall",
            city="Kathmandu",
            is_active=True,
            status="Active",
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.movie = Movie.objects.create(
            title="Subscription Feature",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        start_at = timezone.now() + timedelta(hours=5)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall S",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

    def _request(self, user: User, payload: Optional[dict[str, Any]] = None, query_params: Optional[dict[str, Any]] = None) -> Any:
        return type(
            "Request",
            (),
            {
                "user": user,
                "data": payload or {},
                "query_params": query_params or {},
                "META": {},
            },
        )()

    def _create_plan(
        self,
        *,
        code: str,
        name: str,
        price: Decimal,
        discount_type: str = SubscriptionPlan.DISCOUNT_TYPE_NONE,
        discount_value: Decimal = Decimal("0.00"),
        free_tickets_total: int = 0,
        allow_multiple_active: bool = False,
    ) -> SubscriptionPlan:
        return SubscriptionPlan.objects.create(
            code=code,
            name=name,
            tier=SubscriptionPlan.TIER_SILVER,
            vendor=self.vendor,
            duration_days=30,
            price=price,
            discount_type=discount_type,
            discount_value=discount_value,
            free_tickets_total=free_tickets_total,
            allow_multiple_active=allow_multiple_active,
            is_public=True,
            is_active=True,
        )

    def test_subscribe_customer_creates_active_subscription_and_transaction(self) -> None:
        plan = self._create_plan(
            code="SUB-BASIC-001",
            name="Basic Silver",
            price=Decimal("199.00"),
        )

        payload, status_code = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": plan.id, "payment_method": "ESEWA"})
        )

        self.assertEqual(status_code, status.HTTP_201_CREATED, payload)
        self.assertEqual(
            UserSubscription.objects.filter(
                user=self.user,
                status=UserSubscription.STATUS_ACTIVE,
            ).count(),
            1,
        )
        self.assertTrue(
            SubscriptionTransaction.objects.filter(
                user=self.user,
                transaction_type=SubscriptionTransaction.TYPE_PURCHASE,
                status=SubscriptionTransaction.STATUS_SUCCESS,
            ).exists()
        )

    def test_subscribe_blocks_second_active_subscription_when_multiple_not_allowed(self) -> None:
        first_plan = self._create_plan(
            code="SUB-BASIC-002",
            name="Basic Plus",
            price=Decimal("250.00"),
        )
        second_plan = self._create_plan(
            code="SUB-BASIC-003",
            name="Basic Prime",
            price=Decimal("399.00"),
        )

        first_payload, first_status = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": first_plan.id})
        )
        self.assertEqual(first_status, status.HTTP_201_CREATED, first_payload)

        second_payload, second_status = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": second_plan.id})
        )
        self.assertEqual(second_status, status.HTTP_409_CONFLICT, second_payload)
        self.assertIn("active subscription", str(second_payload.get("message", "")).lower())

    def test_upgrade_customer_applies_prorated_credit(self) -> None:
        base_plan = self._create_plan(
            code="SUB-UPGRADE-001",
            name="Silver Base",
            price=Decimal("100.00"),
        )
        premium_plan = self._create_plan(
            code="SUB-UPGRADE-002",
            name="Gold Premium",
            price=Decimal("300.00"),
            discount_type=SubscriptionPlan.DISCOUNT_TYPE_PERCENTAGE,
            discount_value=Decimal("10.00"),
        )

        subscribe_payload, subscribe_status = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": base_plan.id})
        )
        self.assertEqual(subscribe_status, status.HTTP_201_CREATED, subscribe_payload)

        current = UserSubscription.objects.get(user=self.user, plan=base_plan)
        current.start_at = timezone.now() - timedelta(days=15)
        current.end_at = timezone.now() + timedelta(days=15)
        current.save(update_fields=["start_at", "end_at", "updated_at"])

        upgrade_payload, upgrade_status = subscription.upgrade_customer(
            self._request(self.user, {"plan_id": premium_plan.id, "payment_method": "ESEWA"})
        )
        self.assertEqual(upgrade_status, status.HTTP_200_OK, upgrade_payload)

        current.refresh_from_db()
        self.assertEqual(current.status, UserSubscription.STATUS_CANCELLED)

        upgraded = UserSubscription.objects.filter(
            user=self.user,
            status=UserSubscription.STATUS_ACTIVE,
        ).exclude(id=current.id).first()
        self.assertIsNotNone(upgraded)
        self.assertEqual(getattr(upgraded, "plan_id", None), premium_plan.id)

        self.assertAlmostEqual(float(upgrade_payload.get("prorated_credit") or 0), 50.0, delta=2.0)
        self.assertAlmostEqual(float(upgrade_payload.get("upgrade_charge") or 0), 250.0, delta=2.0)

    def test_booking_flow_applies_and_reverses_subscription_benefits(self) -> None:
        plan = self._create_plan(
            code="SUB-BOOKING-001",
            name="Booking Saver",
            price=Decimal("299.00"),
            discount_type=SubscriptionPlan.DISCOUNT_TYPE_PERCENTAGE,
            discount_value=Decimal("10.00"),
            free_tickets_total=2,
        )

        subscribe_payload, subscribe_status = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": plan.id})
        )
        self.assertEqual(subscribe_status, status.HTTP_201_CREATED, subscribe_payload)

        active_subscription = UserSubscription.objects.get(
            user=self.user,
            status=UserSubscription.STATUS_ACTIVE,
        )

        order_payload = {
            "ticketTotal": 500,
            "use_subscription": True,
            "user_subscription_id": active_subscription.id,
            "use_subscription_free_ticket": True,
            "subscription_free_tickets": 1,
            "booking": {
                "movie_id": self.movie.id,
                "cinema_id": self.vendor.id,
                "show_id": self.show.id,
                "date": self.show.show_date.isoformat(),
                "time": self.show.start_time.strftime("%H:%M"),
                "hall": self.show.hall,
                "selected_seats": ["A1", "A2"],
                "user_id": self.user.id,
            },
        }

        booking_payload, booking_error, booking_status = services._create_booking_from_order(order_payload)
        self.assertIsNone(booking_error)
        self.assertEqual(booking_status, status.HTTP_201_CREATED)

        booking = Booking.objects.get(id=booking_payload.get("booking_id"))
        booking.refresh_from_db()

        self.assertEqual(booking.user_subscription_id, active_subscription.id)
        self.assertEqual(booking.subscription_free_tickets_used, 1)
        self.assertEqual(booking.subscription_discount_amount, Decimal("300.00"))
        self.assertEqual(booking.total_amount, Decimal("200.00"))

        active_subscription.refresh_from_db()
        self.assertEqual(active_subscription.remaining_free_tickets, 1)
        self.assertEqual(active_subscription.used_free_tickets, 1)
        self.assertEqual(active_subscription.total_discount_used, Decimal("300.00"))

        reversal = subscription.reverse_booking_subscription_effects(booking, reason="test-cancel")
        self.assertEqual(reversal.get("free_tickets_restored"), 1)
        self.assertEqual(Decimal(str(reversal.get("discount_refund_amount") or 0)), Decimal("300.00"))

        active_subscription.refresh_from_db()
        self.assertEqual(active_subscription.remaining_free_tickets, 2)
        self.assertEqual(active_subscription.used_free_tickets, 0)
        self.assertEqual(active_subscription.total_discount_used, Decimal("0.00"))

        second_reversal = subscription.reverse_booking_subscription_effects(booking, reason="repeat")
        self.assertEqual(second_reversal.get("free_tickets_restored"), 0)
        self.assertEqual(Decimal(str(second_reversal.get("discount_refund_amount") or 0)), Decimal("0.00"))

    def test_renew_customer_extends_active_subscription(self) -> None:
        plan = self._create_plan(
            code="SUB-RENEW-001",
            name="Renew Plan",
            price=Decimal("180.00"),
        )
        subscribe_payload, subscribe_status = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": plan.id})
        )
        self.assertEqual(subscribe_status, status.HTTP_201_CREATED, subscribe_payload)

        active = UserSubscription.objects.get(user=self.user, status=UserSubscription.STATUS_ACTIVE)
        previous_end = active.end_at

        renew_payload, renew_status = subscription.renew_customer_subscription(
            self._request(self.user, {"payment_method": "ESEWA"})
        )
        self.assertEqual(renew_status, status.HTTP_200_OK, renew_payload)

        active.refresh_from_db()
        self.assertGreater(active.end_at, previous_end)
        self.assertTrue(
            SubscriptionTransaction.objects.filter(
                user=self.user,
                subscription=active,
                transaction_type=SubscriptionTransaction.TYPE_RENEWAL,
                status=SubscriptionTransaction.STATUS_SUCCESS,
            ).exists()
        )

    def test_pause_and_resume_subscription_restores_remaining_time(self) -> None:
        plan = self._create_plan(
            code="SUB-PAUSE-001",
            name="Pause Plan",
            price=Decimal("210.00"),
        )
        subscribe_payload, subscribe_status = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": plan.id})
        )
        self.assertEqual(subscribe_status, status.HTTP_201_CREATED, subscribe_payload)

        active = UserSubscription.objects.get(user=self.user, status=UserSubscription.STATUS_ACTIVE)
        active.start_at = timezone.now() - timedelta(days=10)
        active.end_at = timezone.now() + timedelta(days=5)
        active.save(update_fields=["start_at", "end_at", "updated_at"])

        pause_payload, pause_status = subscription.pause_customer_subscription(
            self._request(self.user, {"reason": "Travel"})
        )
        self.assertEqual(pause_status, status.HTTP_200_OK, pause_payload)
        active.refresh_from_db()
        self.assertEqual(active.status, UserSubscription.STATUS_PAUSED)
        paused_seconds = int(active.paused_remaining_seconds or 0)
        self.assertGreater(paused_seconds, 0)

        resume_payload, resume_status = subscription.resume_customer_subscription(
            self._request(self.user, {"reason": "Back"})
        )
        self.assertEqual(resume_status, status.HTTP_200_OK, resume_payload)
        active.refresh_from_db()
        self.assertEqual(active.status, UserSubscription.STATUS_ACTIVE)
        self.assertGreater(active.end_at, timezone.now())
        self.assertEqual(int(active.paused_remaining_seconds or 0), 0)
        self.assertTrue(
            SubscriptionTransaction.objects.filter(
                user=self.user,
                subscription=active,
                transaction_type=SubscriptionTransaction.TYPE_PAUSE,
                status=SubscriptionTransaction.STATUS_SUCCESS,
            ).exists()
        )
        self.assertTrue(
            SubscriptionTransaction.objects.filter(
                user=self.user,
                subscription=active,
                transaction_type=SubscriptionTransaction.TYPE_RESUME,
                status=SubscriptionTransaction.STATUS_SUCCESS,
            ).exists()
        )

    def test_preview_checkout_uses_coupon_and_referral_signals_for_compatibility(self) -> None:
        plan = self._create_plan(
            code="SUB-COMPAT-001",
            name="Compatibility Plan",
            price=Decimal("300.00"),
        )
        plan.is_stackable_with_coupon = False
        plan.is_stackable_with_referral_wallet = False
        plan.save(update_fields=["is_stackable_with_coupon", "is_stackable_with_referral_wallet", "updated_at"])

        subscribe_payload, subscribe_status = subscription.subscribe_customer(
            self._request(self.user, {"plan_id": plan.id})
        )
        self.assertEqual(subscribe_status, status.HTTP_201_CREATED, subscribe_payload)

        preview, error, status_code = subscription.preview_checkout_subscription(
            self.user.id,
            {
                "subtotal": "500",
                "vendor_id": self.vendor.id,
                "seat_count": 2,
                "coupon_code": "SPRING50",
                "referral_wallet_amount": "20",
            },
        )
        self.assertIsNone(preview)
        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("combined", str((error or {}).get("message") or "").lower())


class GroupBookingSplitPaymentTests(TestCase):
    """Group booking split payment lifecycle and seat-locking tests."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Group Vendor",
            email="group.vendor@meroticket.local",
            phone_number="9855000101",
            username="group-vendor",
            password="password",
            theatre="Group Cineplex",
            city="Kathmandu",
            is_active=True,
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.host = User.objects.create(
            phone_number="9855000102",
            email="group.host@meroticket.local",
            username="group-host",
            dob=date(1992, 5, 5),
            first_name="Group",
            last_name="Host",
            password="password",
        )
        self.host.set_password("password")
        self.host.save()

        self.friend = User.objects.create(
            phone_number="9855000103",
            email="group.friend@meroticket.local",
            username="group-friend",
            dob=date(1993, 7, 7),
            first_name="Group",
            last_name="Friend",
            password="password",
        )
        self.friend.set_password("password")
        self.friend.save()

        self.movie = Movie.objects.create(
            title="Group Payment Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

        start_at = timezone.now() + timedelta(hours=4)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall G",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            end_time=(start_at + timedelta(hours=2)).time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("250.00"),
        )
        self.screen, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

    def _request(self, user: User, data: Optional[dict[str, Any]] = None) -> Any:
        return type(
            "Request",
            (),
            {
                "user": user,
                "data": data or {},
                "query_params": {},
                "META": {},
            },
        )()

    def _create_group_session(
        self,
        *,
        split_mode: str = GroupBookingSession.SPLIT_EQUAL,
        selected_seats: Optional[list[str]] = None,
    ) -> GroupBookingSession:
        payload = {
            "show_id": self.show.id,
            "hall": self.show.hall,
            "selected_seats": selected_seats or ["A1", "A2"],
            "split_mode": split_mode,
            "expiry_minutes": 12,
        }
        response_payload, response_status = group_booking.create_group_booking_session(
            self._request(self.host, payload)
        )
        self.assertEqual(response_status, status.HTTP_201_CREATED, response_payload)
        session_id = response_payload.get("session", {}).get("id")
        self.assertIsNotNone(session_id)
        return GroupBookingSession.objects.get(id=session_id)

    def test_create_group_booking_locks_seats(self) -> None:
        session = self._create_group_session(split_mode=GroupBookingSession.SPLIT_EQUAL)

        host_participant = GroupParticipant.objects.get(session=session, user=self.host)
        self.assertTrue(host_participant.is_host)
        self.assertEqual(host_participant.payment_status, GroupParticipant.PAYMENT_PENDING)

        for label in session.selected_seats:
            row_label, seat_number = services._split_seat_label(label)
            seat = Seat.objects.get(
                screen=self.screen,
                row_label=row_label or None,
                seat_number=seat_number,
            )
            availability = SeatAvailability.objects.get(seat=seat, showtime=session.showtime)
            self.assertIsNotNone(availability.locked_until)
            self.assertGreater(availability.locked_until, timezone.now())

    def test_equal_split_group_session_completes_after_all_payments(self) -> None:
        session = self._create_group_session(split_mode=GroupBookingSession.SPLIT_EQUAL, selected_seats=["A1", "A2"])

        join_payload, join_status = group_booking.join_group_booking_session(
            self._request(self.friend, {}),
            session.invite_code,
        )
        self.assertEqual(join_status, status.HTTP_200_OK, join_payload)

        session.refresh_from_db()
        host_participant = GroupParticipant.objects.get(session=session, user=self.host)
        friend_participant = GroupParticipant.objects.get(session=session, user=self.friend)
        self.assertEqual(host_participant.amount_to_pay, Decimal("250.00"))
        self.assertEqual(friend_participant.amount_to_pay, Decimal("250.00"))

        host_init_payload, host_init_status = group_booking.initiate_group_payment(
            self._request(self.host, {"payment_method": "ESEWA"}),
            session.id,
        )
        self.assertEqual(host_init_status, status.HTTP_201_CREATED, host_init_payload)
        host_payment_id = host_init_payload.get("payment", {}).get("id")
        self.assertIsNotNone(host_payment_id)

        host_complete_payload, host_complete_status = group_booking.complete_group_payment(
            self._request(
                self.host,
                {
                    "status": "SUCCESS",
                    "transaction_id": "GROUP-HOST-TXN-001",
                },
            ),
            session.id,
            int(host_payment_id),
        )
        self.assertEqual(host_complete_status, status.HTTP_200_OK, host_complete_payload)
        session.refresh_from_db()
        self.assertEqual(session.status, GroupBookingSession.STATUS_PARTIALLY_PAID)

        friend_init_payload, friend_init_status = group_booking.initiate_group_payment(
            self._request(self.friend, {"payment_method": "ESEWA"}),
            session.id,
        )
        self.assertEqual(friend_init_status, status.HTTP_201_CREATED, friend_init_payload)
        friend_payment_id = friend_init_payload.get("payment", {}).get("id")
        self.assertIsNotNone(friend_payment_id)

        friend_complete_payload, friend_complete_status = group_booking.complete_group_payment(
            self._request(
                self.friend,
                {
                    "status": "SUCCESS",
                    "transaction_id": "GROUP-FRIEND-TXN-001",
                },
            ),
            session.id,
            int(friend_payment_id),
        )
        self.assertEqual(friend_complete_status, status.HTTP_200_OK, friend_complete_payload)

        session.refresh_from_db()
        self.assertEqual(session.status, GroupBookingSession.STATUS_COMPLETED)
        self.assertEqual(Booking.objects.filter(showtime=self.showtime).count(), 2)
        self.assertEqual(BookingSeat.objects.filter(showtime=self.showtime).count(), 2)
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertEqual(
            GroupPayment.objects.filter(session=session, status=GroupPayment.STATUS_SUCCESS).count(),
            2,
        )


class BookingFraudRiskScoringTests(TestCase):
    """Booking fraud scoring persistence and analytics coverage."""

    def setUp(self) -> None:
        self.vendor = Vendor.objects.create(
            name="Fraud Vendor",
            email="fraud-vendor@meroticket.local",
            phone_number="9800001777",
            username="fraud-vendor",
            password="password",
            theatre="Fraud Hall",
            city="Kathmandu",
            is_active=True,
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.user = User.objects.create(
            phone_number="9800001778",
            email="fraud-user@meroticket.local",
            username="fraud-user",
            dob=date(1994, 1, 1),
            first_name="Fraud",
            last_name="Tester",
            password="password",
        )
        self.user.set_password("password")
        self.user.save()

        self.movie = Movie.objects.create(
            title="Fraud Score Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )

        start_at = timezone.now() + timedelta(hours=3)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall F",
            show_date=start_at.date(),
            start_time=start_at.time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("700.00"),
        )
        _, self.showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)

    @override_settings(
        BOOKING_FRAUD_REVIEW_SCORE_THRESHOLD=60,
        BOOKING_FRAUD_VELOCITY_THRESHOLD=2,
        BOOKING_FRAUD_IP_VELOCITY_THRESHOLD=2,
        BOOKING_FRAUD_HIGH_SEAT_COUNT=5,
    )
    def test_create_booking_persists_fraud_score_level_and_signals(self) -> None:
        for _ in range(3):
            prior_booking = Booking.objects.create(
                user=self.user,
                showtime=self.showtime,
                booking_status=services.BOOKING_STATUS_CONFIRMED,
                total_amount=Decimal("350.00"),
                source_ip="203.0.113.40",
                user_agent="fraud-risk-tests",
            )
            Booking.objects.filter(pk=prior_booking.id).update(
                booking_date=timezone.now() - timedelta(minutes=5)
            )

        order_payload = {
            "ticketTotal": 5600,
            "source_ip": "203.0.113.40",
            "user_agent": "fraud-risk-tests",
            "booking": {
                "movie_id": self.movie.id,
                "cinema_id": self.vendor.id,
                "show_id": self.show.id,
                "date": self.show.show_date.isoformat(),
                "time": self.show.start_time.strftime("%H:%M"),
                "hall": self.show.hall,
                "selected_seats": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"],
                "user_id": self.user.id,
            },
        }

        booking_payload, booking_error, booking_status = services._create_booking_from_order(order_payload)

        self.assertIsNone(booking_error)
        self.assertEqual(booking_status, status.HTTP_201_CREATED)

        booking = Booking.objects.get(pk=booking_payload.get("booking_id"))
        self.assertGreaterEqual(booking.fraud_score, services.booking_fraud_review_threshold())
        self.assertIn(
            booking.fraud_level,
            {Booking.FRAUD_LEVEL_HIGH, Booking.FRAUD_LEVEL_CRITICAL},
        )
        self.assertTrue(isinstance(booking.fraud_signals, list))
        self.assertGreater(len(booking.fraud_signals), 0)
        self.assertEqual(booking.source_ip, "203.0.113.40")

    def test_build_booking_payload_contains_fraud_risk_fields(self) -> None:
        booking = Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("1200.00"),
            fraud_score=82,
            fraud_level=Booking.FRAUD_LEVEL_HIGH,
            fraud_signals=[
                {
                    "code": "risk_test",
                    "title": "Risk test signal",
                    "weight": 82,
                }
            ],
            source_ip="198.51.100.200",
            user_agent="fraud-payload-tests",
        )

        payload = services.build_booking_payload(booking)

        self.assertEqual(payload.get("fraudScore"), 82)
        self.assertEqual(payload.get("fraudLevel"), Booking.FRAUD_LEVEL_HIGH)
        self.assertTrue(bool(payload.get("requiresManualReview")))
        self.assertTrue(isinstance(payload.get("fraudSignals"), list))
        self.assertEqual(payload.get("sourceIp"), "198.51.100.200")

        fraud_block = payload.get("fraudRisk") or {}
        self.assertEqual(fraud_block.get("score"), 82)
        self.assertEqual(fraud_block.get("level"), Booking.FRAUD_LEVEL_HIGH)
        self.assertTrue(bool(fraud_block.get("requiresManualReview")))

    def test_vendor_analytics_contains_fraud_summary(self) -> None:
        Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("900.00"),
            fraud_score=88,
            fraud_level=Booking.FRAUD_LEVEL_HIGH,
            fraud_signals=[{"code": "test_high", "title": "High risk", "weight": 88}],
        )
        Booking.objects.create(
            user=self.user,
            showtime=self.showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("500.00"),
            fraud_score=18,
            fraud_level=Booking.FRAUD_LEVEL_LOW,
            fraud_signals=[{"code": "test_low", "title": "Low risk", "weight": 18}],
        )

        payload = services.get_vendor_analytics(self.vendor, request=None)

        fraud_summary = payload.get("fraud_summary") or {}
        self.assertIn("levels", fraud_summary)
        self.assertGreaterEqual(int(fraud_summary.get("high_risk_bookings") or 0), 1)
        self.assertGreaterEqual(int((fraud_summary.get("levels") or {}).get("high") or 0), 1)
        self.assertTrue(isinstance(payload.get("risky_bookings"), list))


class TicketValidationRaceSafetyTests(TestCase):
    """Ensure ticket scan validation is race-safe and duplicate-aware."""

    def setUp(self) -> None:
        cache.clear()
        self.factory = APIRequestFactory()
        self.vendor = Vendor.objects.create(
            name="Scan Vendor",
            email="scan-vendor@meroticket.local",
            phone_number="9800000777",
            username="scan-vendor",
            password="password",
            theatre="Validation Hall",
            city="Kathmandu",
            is_active=True,
        )
        self.vendor.set_password("password")
        self.vendor.save()

        self.vendor_staff = VendorStaff.objects.create(
            vendor=self.vendor,
            full_name="Scan Staff",
            email="scan-staff@meroticket.local",
            phone_number="9800000881",
            username="scan-staff",
            role=VendorStaff.ROLE_CASHIER,
            password="password",
            is_active=True,
        )

        self.customer = User.objects.create(
            phone_number="9800000778",
            email="scan-customer@meroticket.local",
            username="scan-customer",
            dob=date(1994, 1, 1),
            first_name="Scan",
            last_name="Customer",
            password="password",
        )
        self.customer.set_password("password")
        self.customer.save()

        self.movie = Movie.objects.create(
            title="Validation Movie",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        now = timezone.now() + timedelta(minutes=10)
        self.show = Show.objects.create(
            vendor=self.vendor,
            movie=self.movie,
            hall="Hall V",
            show_date=now.date(),
            start_time=now.time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("300.00"),
        )

        self.ticket = Ticket.objects.create(
            reference="RACE1234",
            user=self.customer,
            show=self.show,
            show_datetime=now,
            payment_status="PAID",
            is_used=False,
            payload={
                "movie": {
                    "title": self.movie.title,
                    "theater": self.show.hall,
                    "show_time": now.strftime("%H:%M"),
                    "show_date": now.date().isoformat(),
                    "seat": "A1",
                },
                "user": {"name": "Scan Customer"},
            },
        )

    def _scan_request(
        self,
        payload: dict[str, Any],
        *,
        vendor: Vendor | None = None,
        staff: VendorStaff | None = None,
        remote_addr: str = "127.0.0.1",
    ) -> Any:
        actor_vendor = vendor or self.vendor
        extras = None
        if staff is not None:
            extras = {"staff_id": staff.id, "staff_role": staff.role}
        token = issue_access_token("vendor", actor_vendor.id, extras=extras)
        return self.factory.post(
            "/api/vendor/ticket-validation/scan/",
            payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
            REMOTE_ADDR=remote_addr,
        )

    def _monitor_request(
        self,
        *,
        vendor: Vendor | None = None,
        staff: VendorStaff | None = None,
        params: dict[str, Any] | None = None,
        endpoint: str = "monitor",
        method: str = "GET",
        remote_addr: str = "127.0.0.1",
    ) -> Any:
        actor_vendor = vendor or self.vendor
        extras = None
        if staff is not None:
            extras = {"staff_id": staff.id, "staff_role": staff.role}
        token = issue_access_token("vendor", actor_vendor.id, extras=extras)
        query = ""
        if params:
            encoded = urlencode(
                {
                    key: value
                    for key, value in params.items()
                    if value not in (None, "")
                }
            )
            query = f"?{encoded}" if encoded else ""
        path = f"/api/vendor/ticket-validation/{endpoint}/{query}"
        if str(method or "GET").strip().upper() == "POST":
            return self.factory.post(
                path,
                {},
                format="json",
                HTTP_AUTHORIZATION=f"Bearer {token}",
                REMOTE_ADDR=remote_addr,
            )

        return self.factory.get(
            path,
            HTTP_AUTHORIZATION=f"Bearer {token}",
            REMOTE_ADDR=remote_addr,
        )

    def _create_monitor_scan(
        self,
        *,
        reference: str,
        status_value: str,
        scanned_at: datetime | None = None,
        reason: str | None = None,
        ticket: Ticket | None = None,
    ) -> TicketValidationScan:
        scan = TicketValidationScan.objects.create(
            reference=reference,
            ticket=ticket,
            booking=None,
            vendor=self.vendor,
            scanned_by=self.vendor,
            vendor_staff=self.vendor_staff,
            status=status_value,
            reason=reason,
            fraud_score=45 if status_value != TicketValidationScan.STATUS_VALID else 0,
            source_ip="198.51.100.60",
            user_agent="monitor-alert-tests",
        )
        if scanned_at is not None:
            TicketValidationScan.objects.filter(pk=scan.id).update(scanned_at=scanned_at)
            scan.scanned_at = scanned_at
        return scan

    def test_second_scan_is_duplicate_after_first_success(self) -> None:
        first_response = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data.get("code"), SCAN_CODE_VALID)
        self.assertEqual(first_response.data.get("alert"), "none")
        self.assertEqual(first_response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_VALID)

        first_scan_payload = first_response.data.get("scan") or {}
        self.assertEqual(first_scan_payload.get("riskLevel"), Booking.FRAUD_LEVEL_LOW)
        self.assertFalse(bool(first_scan_payload.get("requiresManualReview")))

        second_response = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.data.get("code"), SCAN_CODE_ALREADY_USED)
        self.assertEqual(second_response.data.get("alert"), "duplicate_ticket")
        self.assertEqual(second_response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_DUPLICATE)

        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.is_used)
        self.assertEqual(
            TicketValidationScan.objects.filter(
                ticket=self.ticket,
                vendor=self.vendor,
                status=TicketValidationScan.STATUS_VALID,
            ).count(),
            1,
        )
        self.assertEqual(
            TicketValidationScan.objects.filter(
                ticket=self.ticket,
                vendor=self.vendor,
                status=TicketValidationScan.STATUS_DUPLICATE,
            ).count(),
            1,
        )

    def test_duplicate_scan_counter_increases_on_repeated_attempts(self) -> None:
        first = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))
        second = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))
        third = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(third.status_code, status.HTTP_200_OK)

        self.assertEqual(second.data.get("code"), SCAN_CODE_ALREADY_USED)
        self.assertEqual(second.data.get("scan", {}).get("duplicateCount"), 1)
        self.assertEqual(second.data.get("scan", {}).get("totalScansForTicket"), 2)

        self.assertEqual(third.data.get("code"), SCAN_CODE_ALREADY_USED)
        self.assertEqual(third.data.get("scan", {}).get("duplicateCount"), 2)
        self.assertEqual(third.data.get("scan", {}).get("totalScansForTicket"), 3)

    def test_scan_requires_token_when_ticket_uuid_is_provided(self) -> None:
        response = validate_ticket_scan(
            self._scan_request(
                {
                    "ticket_id": str(self.ticket.ticket_id),
                }
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_INVALID_TOKEN)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_INVALID)

    def test_scan_rejects_token_for_different_ticket(self) -> None:
        other_ticket = Ticket.objects.create(
            reference="RACE5678",
            user=self.customer,
            show=self.show,
            show_datetime=self.ticket.show_datetime,
            payment_status="PAID",
            is_used=False,
            payload=self.ticket.payload,
        )
        mismatched_token = services.generate_ticket_qr_token(other_ticket)

        response = validate_ticket_scan(
            self._scan_request(
                {
                    "ticket_id": str(self.ticket.ticket_id),
                    "token": mismatched_token,
                }
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_INVALID_TOKEN)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_INVALID)

    def test_scan_accepts_nested_qr_payload_with_valid_token(self) -> None:
        token = services.generate_ticket_qr_token(self.ticket)
        scan_blob = json.dumps(
            {
                "qr_payload": {
                    "ticket_id": str(self.ticket.ticket_id),
                    "token": token,
                }
            }
        )

        response = validate_ticket_scan(self._scan_request({"scan_data": scan_blob}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_VALID)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_VALID)

        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.is_used)

    def test_second_secure_qr_scan_is_duplicate(self) -> None:
        token = services.generate_ticket_qr_token(self.ticket)

        first = validate_ticket_scan(
            self._scan_request(
                {
                    "ticket_id": str(self.ticket.ticket_id),
                    "token": token,
                }
            )
        )
        second = validate_ticket_scan(
            self._scan_request(
                {
                    "ticket_id": str(self.ticket.ticket_id),
                    "token": token,
                }
            )
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data.get("code"), SCAN_CODE_VALID)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data.get("code"), SCAN_CODE_ALREADY_USED)
        self.assertEqual(second.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_DUPLICATE)

    def test_scan_returns_invalid_token_code(self) -> None:
        response = validate_ticket_scan(
            self._scan_request(
                {
                    "ticket_id": str(self.ticket.ticket_id),
                    "token": "invalid-ticket-token",
                }
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_INVALID_TOKEN)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_INVALID)

    def test_scan_returns_expired_token_code(self) -> None:
        self.ticket.token_expires_at = timezone.now() - timedelta(minutes=1)
        self.ticket.save(update_fields=["token_expires_at"])
        expired_token = services.generate_ticket_qr_token(self.ticket)

        response = validate_ticket_scan(
            self._scan_request(
                {
                    "ticket_id": str(self.ticket.ticket_id),
                    "token": expired_token,
                }
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_EXPIRED_TOKEN)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_INVALID)

    def test_scan_returns_wrong_vendor_code(self) -> None:
        other_vendor = Vendor.objects.create(
            name="Other Vendor",
            email="other-vendor@meroticket.local",
            phone_number="9800000991",
            username="other-vendor",
            password="password",
            theatre="Other Hall",
            city="Pokhara",
            is_active=True,
        )
        other_vendor.set_password("password")
        other_vendor.save()

        response = validate_ticket_scan(
            self._scan_request(
                {"reference": self.ticket.reference},
                vendor=other_vendor,
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_WRONG_VENDOR)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_FRAUD)

    def test_scan_returns_outside_window_code(self) -> None:
        self.ticket.show_datetime = timezone.now() + timedelta(hours=3)
        self.ticket.save(update_fields=["show_datetime"])

        response = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_OUTSIDE_VALID_TIME_WINDOW)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_INVALID)

    def test_scan_within_earlier_validation_window_is_accepted(self) -> None:
        self.ticket.show_datetime = timezone.now() + timedelta(hours=1, minutes=30)
        self.ticket.save(update_fields=["show_datetime"])

        response = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_VALID)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_VALID)

    def test_scan_rejects_legacy_paid_alias_without_successful_payment_record(self) -> None:
        legacy_ticket = Ticket.objects.create(
            reference="LEGACY001",
            user=self.customer,
            show=self.show,
            show_datetime=self.ticket.show_datetime,
            payment_status=Ticket.PaymentStatus.PENDING,
            is_used=False,
            payload={
                "movie": {
                    "title": self.movie.title,
                    "theater": self.show.hall,
                    "show_time": self.show.start_time.strftime("%H:%M"),
                    "show_date": self.show.show_date.isoformat(),
                    "seat": "A2",
                },
                "payment": {"status": "SUCCESS"},
                "booking": {"booking_id": 999999},
            },
        )

        response = validate_ticket_scan(self._scan_request({"reference": legacy_ticket.reference}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_PAYMENT_INCOMPLETE)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_INVALID)

    def test_scan_accepts_legacy_paid_alias_with_successful_payment_record(self) -> None:
        _, showtime = services._get_or_create_showtime_for_context(self.show, self.show.hall)
        booking = Booking.objects.create(
            user=self.customer,
            showtime=showtime,
            booking_status=services.BOOKING_STATUS_CONFIRMED,
            total_amount=Decimal("300.00"),
        )
        Payment.objects.create(
            booking=booking,
            payment_method="ESEWA:legacy-paid-ok",
            payment_status="Success",
            amount=Decimal("300.00"),
        )

        legacy_ticket = Ticket.objects.create(
            reference="LEGACY002",
            user=self.customer,
            show=self.show,
            show_datetime=self.ticket.show_datetime,
            payment_status=Ticket.PaymentStatus.PENDING,
            is_used=False,
            payload={
                "movie": {
                    "title": self.movie.title,
                    "theater": self.show.hall,
                    "show_time": self.show.start_time.strftime("%H:%M"),
                    "show_date": self.show.show_date.isoformat(),
                    "seat": "A3",
                },
                "payment": {"status": "SUCCESS"},
                "booking": {"booking_id": booking.id},
            },
        )

        response = validate_ticket_scan(self._scan_request({"reference": legacy_ticket.reference}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_VALID)
        self.assertEqual(response.data.get("scan", {}).get("status"), TicketValidationScan.STATUS_VALID)

    def test_invalid_scan_request_is_audited_with_failure_reason(self) -> None:
        response = validate_ticket_scan(self._scan_request({}))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get("code"), SCAN_CODE_LOOKUP_INVALID)
        self.assertEqual(response.data.get("alert"), "invalid_request")

        scan_payload = response.data.get("scan") or {}
        self.assertIsNotNone(scan_payload.get("id"))
        self.assertEqual(scan_payload.get("status"), TicketValidationScan.STATUS_INVALID)

        logged_scan = TicketValidationScan.objects.filter(pk=scan_payload.get("id")).first()
        self.assertIsNotNone(logged_scan)
        self.assertIn("Invalid scan request", str(logged_scan.reason))

    @override_settings(
        TICKET_VALIDATION_SCAN_RATE_LIMIT_STAFF_PER_MINUTE=1,
        TICKET_VALIDATION_SCAN_RATE_LIMIT_IP_PER_MINUTE=100,
    )
    def test_scan_rate_limit_blocks_per_vendor_staff(self) -> None:
        payload = {"reference": "MISS1234"}

        first = validate_ticket_scan(
            self._scan_request(
                payload,
                staff=self.vendor_staff,
                remote_addr="198.51.100.20",
            )
        )
        second = validate_ticket_scan(
            self._scan_request(
                payload,
                staff=self.vendor_staff,
                remote_addr="198.51.100.20",
            )
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(second.data.get("code"), SCAN_CODE_RATE_LIMITED)
        self.assertEqual(second.data.get("scope"), "vendor_staff")

        rate_limited_scan_payload = second.data.get("scan") or {}
        self.assertEqual(rate_limited_scan_payload.get("status"), TicketValidationScan.STATUS_INVALID)
        self.assertIn("Rate limit exceeded", str(rate_limited_scan_payload.get("reason") or ""))

    @override_settings(
        TICKET_VALIDATION_SCAN_RATE_LIMIT_STAFF_PER_MINUTE=100,
        TICKET_VALIDATION_SCAN_RATE_LIMIT_IP_PER_MINUTE=1,
    )
    def test_scan_rate_limit_blocks_per_ip(self) -> None:
        payload = {"reference": "MISS2234"}

        first = validate_ticket_scan(self._scan_request(payload, remote_addr="198.51.100.21"))
        second = validate_ticket_scan(self._scan_request(payload, remote_addr="198.51.100.21"))

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(second.data.get("code"), SCAN_CODE_RATE_LIMITED)
        self.assertEqual(second.data.get("scope"), "vendor_ip")

    @override_settings(
        TICKET_VALIDATION_MONITOR_RATE_LIMIT_STAFF_PER_MINUTE=1,
        TICKET_VALIDATION_MONITOR_RATE_LIMIT_IP_PER_MINUTE=100,
    )
    def test_monitor_rate_limit_blocks_per_vendor_staff(self) -> None:
        first = vendor_ticket_validation_monitor(
            self._monitor_request(
                staff=self.vendor_staff,
                remote_addr="203.0.113.45",
            )
        )
        second = vendor_ticket_validation_monitor(
            self._monitor_request(
                staff=self.vendor_staff,
                remote_addr="203.0.113.45",
            )
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(second.data.get("code"), MONITOR_CODE_RATE_LIMITED)
        self.assertEqual(second.data.get("scope"), "vendor_staff")

    def test_monitor_filters_by_date_staff_status_movie_show(self) -> None:
        first_scan_response = validate_ticket_scan(
            self._scan_request(
                {"reference": self.ticket.reference},
                staff=self.vendor_staff,
            )
        )
        self.assertEqual(first_scan_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_scan_response.data.get("code"), SCAN_CODE_VALID)

        first_scan_id = first_scan_response.data.get("scan", {}).get("id")
        first_scan = TicketValidationScan.objects.filter(pk=first_scan_id).first()
        self.assertIsNotNone(first_scan)

        next_show_time = timezone.now() + timedelta(days=1)
        second_movie = Movie.objects.create(
            title="Validation Movie 2",
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
        )
        second_show = Show.objects.create(
            vendor=self.vendor,
            movie=second_movie,
            hall="Hall X",
            show_date=next_show_time.date(),
            start_time=next_show_time.time().replace(second=0, microsecond=0),
            status=Show.STATUS_UPCOMING,
            listing_status="Now Showing",
            price=Decimal("320.00"),
        )
        second_ticket = Ticket.objects.create(
            reference="RACE9933",
            user=self.customer,
            show=second_show,
            show_datetime=next_show_time,
            payment_status="PAID",
            is_used=False,
            payload={
                "movie": {
                    "title": second_movie.title,
                    "theater": second_show.hall,
                    "show_time": next_show_time.strftime("%H:%M"),
                    "show_date": next_show_time.date().isoformat(),
                    "seat": "B1",
                },
                "user": {"name": "Scan Customer"},
            },
        )
        second_scan_response = validate_ticket_scan(self._scan_request({"reference": second_ticket.reference}))
        self.assertEqual(second_scan_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_scan_response.data.get("code"), SCAN_CODE_VALID)

        monitor_response = vendor_ticket_validation_monitor(
            self._monitor_request(
                params={
                    "date": first_scan.scanned_at.date().isoformat(),
                    "staff": str(self.vendor_staff.id),
                    "status": TicketValidationScan.STATUS_VALID,
                    "movie": str(self.movie.id),
                    "show": str(self.show.id),
                }
            )
        )

        self.assertEqual(monitor_response.status_code, status.HTTP_200_OK)
        self.assertEqual(monitor_response.data.get("summary", {}).get("total"), 1)
        scans = monitor_response.data.get("scans") or []
        self.assertEqual(len(scans), 1)

        scan_payload = scans[0]
        self.assertEqual(scan_payload.get("reference"), self.ticket.reference)
        self.assertEqual(scan_payload.get("scannedByStaffId"), self.vendor_staff.id)
        self.assertEqual(scan_payload.get("movieId"), self.movie.id)
        self.assertEqual(scan_payload.get("showId"), self.show.id)
        self.assertEqual(scan_payload.get("status"), TicketValidationScan.STATUS_VALID)

    @override_settings(
        TICKET_VALIDATION_ALERT_INVALID_TOKEN_WINDOW_MINUTES=10,
        TICKET_VALIDATION_ALERT_INVALID_TOKEN_SPIKE_THRESHOLD=4,
    )
    def test_monitor_alerts_detect_invalid_token_spike(self) -> None:
        now = timezone.now()
        self._create_monitor_scan(
            reference="SPKPREV1",
            status_value=TicketValidationScan.STATUS_INVALID,
            reason="Invalid QR code.",
            scanned_at=now - timedelta(minutes=15),
            ticket=self.ticket,
        )

        for idx in range(5):
            self._create_monitor_scan(
                reference=f"SPKNOW{idx:02d}",
                status_value=TicketValidationScan.STATUS_INVALID,
                reason="Invalid QR code.",
                scanned_at=now - timedelta(minutes=2, seconds=idx),
                ticket=self.ticket,
            )

        monitor_response = vendor_ticket_validation_monitor(self._monitor_request())

        self.assertEqual(monitor_response.status_code, status.HTTP_200_OK)
        alerts = monitor_response.data.get("alerts") or []
        alert_by_type = {item.get("type"): item for item in alerts}
        spike_alert = alert_by_type.get("invalid_token_spike")

        self.assertIsNotNone(spike_alert)
        self.assertTrue(bool(spike_alert.get("isTriggered")))
        self.assertEqual(int(spike_alert.get("count") or 0), 5)
        self.assertEqual(int(spike_alert.get("previousWindowCount") or 0), 1)

    @override_settings(
        TICKET_VALIDATION_ALERT_DUPLICATE_WINDOW_MINUTES=30,
        TICKET_VALIDATION_ALERT_DUPLICATE_ATTEMPT_THRESHOLD=3,
    )
    def test_monitor_alerts_detect_repeated_duplicate_attempts(self) -> None:
        now = timezone.now()

        for idx in range(4):
            self._create_monitor_scan(
                reference=self.ticket.reference,
                status_value=TicketValidationScan.STATUS_DUPLICATE,
                reason="Ticket already used.",
                scanned_at=now - timedelta(minutes=4, seconds=idx),
                ticket=self.ticket,
            )

        monitor_response = vendor_ticket_validation_monitor(self._monitor_request())

        self.assertEqual(monitor_response.status_code, status.HTTP_200_OK)
        alerts = monitor_response.data.get("alerts") or []
        alert_by_type = {item.get("type"): item for item in alerts}
        duplicate_alert = alert_by_type.get("repeated_duplicate_attempts")

        self.assertIsNotNone(duplicate_alert)
        self.assertTrue(bool(duplicate_alert.get("isTriggered")))
        self.assertGreaterEqual(int(duplicate_alert.get("count") or 0), 4)

        offenders = duplicate_alert.get("offenders") or []
        self.assertTrue(
            any(
                item.get("reference") == self.ticket.reference
                and int(item.get("duplicateAttempts") or 0) >= 4
                for item in offenders
            )
        )

    def test_monitor_export_returns_filtered_csv(self) -> None:
        first_scan = validate_ticket_scan(
            self._scan_request(
                {"reference": self.ticket.reference},
                staff=self.vendor_staff,
            )
        )
        self.assertEqual(first_scan.status_code, status.HTTP_200_OK)
        self.assertEqual(first_scan.data.get("code"), SCAN_CODE_VALID)

        invalid_scan = validate_ticket_scan(self._scan_request({"reference": "MISS2235"}))
        self.assertEqual(invalid_scan.status_code, status.HTTP_200_OK)

        export_response = vendor_ticket_validation_monitor_export(
            self._monitor_request(
                endpoint="monitor/export",
                params={
                    "status": TicketValidationScan.STATUS_VALID,
                    "staff": str(self.vendor_staff.id),
                },
            )
        )

        self.assertEqual(export_response.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", export_response.get("Content-Type", ""))
        self.assertIn(
            "ticket_validation_monitor_",
            str(export_response.get("Content-Disposition", "")),
        )

        csv_body = export_response.content.decode("utf-8")
        self.assertIn("scan_id,reference,ticket_id,status", csv_body)
        self.assertIn(self.ticket.reference, csv_body)
        self.assertNotIn("MISS2235", csv_body)

        non_empty_lines = [line for line in csv_body.splitlines() if line.strip()]
        self.assertEqual(len(non_empty_lines), 2)

    def test_monitor_export_job_queue_flow(self) -> None:
        valid_scan = validate_ticket_scan(
            self._scan_request(
                {"reference": self.ticket.reference},
                staff=self.vendor_staff,
            )
        )
        self.assertEqual(valid_scan.status_code, status.HTTP_200_OK)

        _ = validate_ticket_scan(self._scan_request({"reference": "MISS3344"}))

        queue_response = vendor_ticket_validation_monitor_export_jobs(
            self._monitor_request(
                endpoint="monitor/export/jobs",
                method="POST",
                params={
                    "status": TicketValidationScan.STATUS_VALID,
                    "staff": str(self.vendor_staff.id),
                },
            )
        )
        self.assertEqual(queue_response.status_code, status.HTTP_202_ACCEPTED)

        queued_job_payload = queue_response.data.get("job") or {}
        queued_job_id = int(queued_job_payload.get("id") or 0)
        self.assertGreater(queued_job_id, 0)

        summary = services.process_background_jobs(
            batch_size=10,
            job_types=[BackgroundJob.TYPE_ANALYTICS_MONITOR_EXPORT],
        )
        self.assertEqual(summary.get("completed"), 1)

        detail_response = vendor_ticket_validation_monitor_export_job_detail(
            self._monitor_request(endpoint=f"monitor/export/jobs/{queued_job_id}")
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            str(detail_response.data.get("job", {}).get("status") or "").upper(),
            BackgroundJob.STATUS_COMPLETED,
        )

        download_response = vendor_ticket_validation_monitor_export_job_download(
            self._monitor_request(endpoint=f"monitor/export/jobs/{queued_job_id}/download")
        )
        self.assertEqual(download_response.status_code, status.HTTP_200_OK)
        self.assertIn("text/csv", str(download_response.get("Content-Type", "")))

        csv_body = download_response.content.decode("utf-8")
        self.assertIn("scan_id,reference,ticket_id,status", csv_body)
        self.assertIn(self.ticket.reference, csv_body)
        self.assertNotIn("MISS3344", csv_body)

    def test_scan_validation_uses_select_for_update_lock(self) -> None:
        with mock.patch("app.views.ticket_validation.Ticket.objects.select_for_update") as mocked_lock:
            mocked_lock.return_value = Ticket.objects.all()
            response = validate_ticket_scan(self._scan_request({"reference": self.ticket.reference}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(mocked_lock.called)

    def test_download_ticket_repairs_corrupted_ticket_uuid(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE tickets SET ticket_id = %s WHERE id = %s",
                ["not-a-valid-uuid", self.ticket.id],
            )

        content = services.build_ticket_download(self.ticket.reference)

        self.assertIsInstance(content, (bytes, bytearray))
        self.ticket.refresh_from_db()
        self.assertTrue(str(self.ticket.ticket_id).strip())

    def test_download_ticket_accepts_case_insensitive_reference(self) -> None:
        content = services.build_ticket_download(self.ticket.reference.lower())

        self.assertIsInstance(content, (bytes, bytearray))

    def test_scan_recovers_ticket_from_qr_token_when_uuid_row_is_corrupted(self) -> None:
        token = services.generate_ticket_qr_token(self.ticket)
        scan_blob = json.dumps(
            {
                "qr_payload": {
                    "ticket_id": str(self.ticket.ticket_id),
                    "token": token,
                }
            }
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE tickets SET ticket_id = %s WHERE id = %s",
                ["not-a-valid-uuid", self.ticket.id],
            )

        response = validate_ticket_scan(self._scan_request({"scan_data": scan_blob}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data.get("code"), SCAN_CODE_VALID)

        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.is_used)


class BackupRestoreCommandTests(TransactionTestCase):
    """Validate automated backup and restore management command routines."""

    def _create_backup_fixture(self, *, media_root: Path) -> tuple[User, Path]:
        user = User.objects.create(
            phone_number="9800099991",
            email="backup-user@meroticket.local",
            username="backup-user",
            dob=date(1991, 1, 1),
            first_name="Backup",
            last_name="User",
            password="password",
        )
        user.set_password("password")
        user.save()

        media_file = media_root / "backup-tests" / "sample.txt"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_text("backup-fixture", encoding="utf-8")
        return user, media_file

    def _single_bundle_dir(self, output_dir: Path) -> Path:
        bundle_dirs = sorted(item for item in output_dir.iterdir() if item.is_dir())
        self.assertEqual(len(bundle_dirs), 1)
        return bundle_dirs[0]

    def test_backup_data_creates_database_media_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as media_tmp, tempfile.TemporaryDirectory() as backup_tmp:
            media_root = Path(media_tmp)
            output_dir = Path(backup_tmp)

            with self.settings(MEDIA_ROOT=str(media_root)):
                self._create_backup_fixture(media_root=media_root)

                call_command("backup_data", output_dir=str(output_dir), verbosity=0)

                bundle_dir = self._single_bundle_dir(output_dir)
                database_fixture = bundle_dir / "database.json"
                media_archive = bundle_dir / "media.zip"
                manifest_file = bundle_dir / "manifest.json"

                self.assertTrue(database_fixture.exists())
                self.assertTrue(media_archive.exists())
                self.assertTrue(manifest_file.exists())

                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                self.assertEqual(manifest.get("database_file"), "database.json")
                self.assertEqual(manifest.get("media_file"), "media.zip")

                with zipfile.ZipFile(media_archive, mode="r") as archive:
                    self.assertIn("backup-tests/sample.txt", archive.namelist())

    def test_restore_data_recovers_database_and_media(self) -> None:
        with tempfile.TemporaryDirectory() as media_tmp, tempfile.TemporaryDirectory() as backup_tmp:
            media_root = Path(media_tmp)
            output_dir = Path(backup_tmp)

            with self.settings(MEDIA_ROOT=str(media_root)):
                original_user, media_file = self._create_backup_fixture(media_root=media_root)

                call_command("backup_data", output_dir=str(output_dir), verbosity=0)
                bundle_dir = self._single_bundle_dir(output_dir)

                User.objects.filter(id=original_user.id).delete()
                self.assertFalse(User.objects.filter(id=original_user.id).exists())

                media_file.write_text("changed-after-backup", encoding="utf-8")
                stale_file = media_root / "stale.tmp"
                stale_file.write_text("stale", encoding="utf-8")

                call_command("restore_data", str(bundle_dir), force=True, verbosity=0)

                self.assertTrue(User.objects.filter(email="backup-user@meroticket.local").exists())
                self.assertEqual(media_file.read_text(encoding="utf-8"), "backup-fixture")
                self.assertFalse(stale_file.exists())
