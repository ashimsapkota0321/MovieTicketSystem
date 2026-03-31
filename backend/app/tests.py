"""Minimal serializer validation tests."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status

from . import services
from .models import Banner, Booking, Movie, Seat, Show, User, Vendor
from .serializers import BannerCreateUpdateSerializer


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\xdac\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xd9\xfe\x00\x00\x00\x00IEND\xaeB`\x82"
)


def build_test_image(name: str = "test.png") -> SimpleUploadedFile:
    """Return a 1x1 PNG file for upload tests."""
    return SimpleUploadedFile(name, PNG_BYTES, content_type="image/png")


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
