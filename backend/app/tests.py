"""Minimal serializer validation tests."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from .models import Banner, Movie
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
