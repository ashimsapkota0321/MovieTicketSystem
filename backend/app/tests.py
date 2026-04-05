"""Minimal serializer validation tests."""

from __future__ import annotations

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
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
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
    Reward,
    RewardRedemption,
    Referral,
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
    User,
    UserLoyaltyWallet,
    UserSubscription,
    Vendor,
    VendorStaff,
)
from .permissions import issue_access_token
from .serializers import BannerCreateUpdateSerializer, MovieAdminWriteSerializer
from .views.ticket_validation import (
    SCAN_CODE_ALREADY_USED,
    SCAN_CODE_EXPIRED_TOKEN,
    SCAN_CODE_INVALID_TOKEN,
    SCAN_CODE_LOOKUP_INVALID,
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
from .views.booking import _confirm_booking_after_payment, _pending_payment_method
from .viewsets import ReviewViewSet


def build_test_image(name: str = "test.png") -> SimpleUploadedFile:
    """Return a valid 1x1 PNG file for upload tests."""
    buffer = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


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

    @mock.patch("app.services.send_mail")
    def test_request_password_otp_sends_email(self, mocked_send_mail) -> None:
        mocked_send_mail.return_value = 1

        payload, status_code = services.request_password_otp(self.user.email)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("message"), "OTP sent to your email")
        self.assertTrue(
            OTPVerification.objects.filter(email__iexact=self.user.email).exists()
        )
        self.assertEqual(mocked_send_mail.call_count, 1)

    @mock.patch("app.services.send_mail")
    def test_request_password_otp_returns_error_when_email_fails(self, mocked_send_mail) -> None:
        mocked_send_mail.side_effect = Exception("SMTP unavailable")

        payload, status_code = services.request_password_otp(self.user.email)

        self.assertEqual(status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("Failed to send OTP email", str(payload.get("message") or ""))
        self.assertFalse(
            OTPVerification.objects.filter(email__iexact=self.user.email).exists()
        )

    @override_settings(
        RESEND_API_KEY="re_test_123",
        RESEND_FROM_EMAIL="Mero Ticket <onboarding@resend.dev>",
    )
    @mock.patch("app.services.urllib_request.urlopen")
    def test_request_password_otp_uses_resend_with_html_otp(
        self,
        mocked_resend_open,
    ) -> None:
        mocked_response = mock.Mock()
        mocked_response.status = 200
        mocked_resend_open.return_value.__enter__.return_value = mocked_response

        payload, status_code = services.request_password_otp(self.user.email)

        self.assertEqual(status_code, status.HTTP_200_OK)
        self.assertEqual(payload.get("message"), "OTP sent to your email")
        self.assertEqual(mocked_resend_open.call_count, 1)

        request_obj = mocked_resend_open.call_args.args[0]
        sent_payload = json.loads((request_obj.data or b"{}").decode("utf-8"))
        self.assertEqual(sent_payload.get("to"), [self.user.email])
        self.assertTrue(sent_payload.get("html"))

        otp_record = OTPVerification.objects.filter(email__iexact=self.user.email).order_by("-created_at").first()
        self.assertIsNotNone(otp_record)
        self.assertIn(str(otp_record.otp), str(sent_payload.get("html") or ""))

    @override_settings(
        RESEND_API_KEY="re_test_123",
        RESEND_FROM_EMAIL="Mero Ticket <onboarding@resend.dev>",
    )
    @mock.patch("app.services.urllib_request.urlopen")
    def test_request_password_otp_returns_error_when_resend_fails(
        self,
        mocked_resend_open,
    ) -> None:
        mocked_resend_open.side_effect = Exception("Unauthorized")

        payload, status_code = services.request_password_otp(self.user.email)

        self.assertEqual(status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("Failed to send OTP email", str(payload.get("message") or ""))
        self.assertFalse(
            OTPVerification.objects.filter(email__iexact=self.user.email).exists()
        )

    @mock.patch("app.services._send_password_changed_email")
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

    @mock.patch("app.services._send_password_changed_email")
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
    SHOW_OPERATING_OPEN_TIME="09:00",
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

    def test_booking_closes_when_show_starts_in_ten_minutes(self) -> None:
        fixed_now = timezone.make_aware(
            datetime(2026, 1, 20, 10, 0),
            timezone.get_current_timezone(),
        )
        show = self._create_show(
            hall="Hall A",
            start_at=fixed_now + timedelta(minutes=10),
        )

        with mock.patch("app.selectors.timezone.now", return_value=fixed_now), mock.patch(
            "app.services.timezone.now", return_value=fixed_now
        ):
            payload, status_code = services._ensure_show_is_bookable(show)

        self.assertEqual(status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("10 minutes", str((payload or {}).get("message") or ""))

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
        Payment.objects.create(
            booking=self.pending_booking,
            payment_method=_pending_payment_method(self.transaction_uuid),
            payment_status="Pending",
            amount=Decimal("250.00"),
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

    def test_register_user_with_referral_code_creates_pending_referral(self) -> None:
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
        self.assertEqual(referral.status, Referral.STATUS_PENDING)

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
