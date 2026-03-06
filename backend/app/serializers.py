"""DRF serializers for the application API."""

from __future__ import annotations

import logging
import random
import re
from typing import Any, Optional

from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import (
    Admin,
    Banner,
    CollabDetails,
    Collaborator,
    HomeSlide,
    Movie,
    MovieCredit,
    MovieGenre,
    Person,
    Review,
    Show,
    User,
    Vendor,
)
from .utils import build_media_url, normalize_phone_number

logger = logging.getLogger(__name__)

PHONE_REGEX = re.compile(r"^[0-9]{10,13}$")
EMAIL_EXISTS_MESSAGE = "Email already exists"
PHONE_EXISTS_MESSAGE = "Phone number already exists"
PASSWORD_MISMATCH_MESSAGE = "Passwords do not match"
INVALID_PHONE_MESSAGE = "Invalid phone number format"


def generate_unique_username(first_name: str, last_name: str) -> str:
    """Generate a unique username from a first and last name."""
    base = re.sub(r"[^a-zA-Z0-9]", "", f"{first_name}{last_name}").lower()
    if not base:
        base = "user"
    base = base[:47]

    for _ in range(1000):
        suffix = f"{random.randint(0, 999):03d}"
        username = f"{base}{suffix}"
        if not User.objects.filter(username__iexact=username).exists():
            return username

    while True:
        suffix = f"{random.randint(0, 999999):06d}"
        username = f"{base[:44]}{suffix}"
        if not User.objects.filter(username__iexact=username).exists():
            return username


def _resolve_person_payload(
    person_id: Optional[int] = None,
    person_data: Optional[dict[str, Any]] = None,
    id_error_key: str = "person_id",
    data_error_key: str = "person",
) -> Person:
    """Resolve a person from an ID or create one from payload data."""
    if person_id:
        try:
            return Person.objects.get(pk=person_id)
        except Person.DoesNotExist:
            raise ValidationError({id_error_key: "Person not found."})

    person_data = person_data or {}
    if person_data.get("id"):
        try:
            return Person.objects.get(pk=person_data.get("id"))
        except Person.DoesNotExist:
            raise ValidationError({data_error_key: "Person not found."})

    full_name = (person_data.get("full_name") or "").strip()
    if not full_name:
        raise ValidationError(
            {data_error_key: "full_name is required to create a new person."}
        )

    existing = Person.objects.filter(full_name__iexact=full_name).first()
    if existing:
        return existing

    return Person.objects.create(
        full_name=full_name,
        photo=person_data.get("photo"),
        photo_url=person_data.get("photo_url"),
        bio=person_data.get("bio"),
        date_of_birth=person_data.get("date_of_birth"),
        nationality=person_data.get("nationality"),
        instagram=person_data.get("instagram"),
        imdb=person_data.get("imdb"),
        facebook=person_data.get("facebook"),
    )


class UserRegistrationSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(required=True)
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        required=True,
    )
    confirm_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        required=True,
    )

    class Meta:
        model = User
        fields = [
            "phone_number",
            "email",
            "dob",
            "first_name",
            "middle_name",
            "last_name",
            "password",
            "confirm_password",
        ]
        extra_kwargs = {
            "email": {"required": True},
            "phone_number": {"required": True},
            "first_name": {"required": True},
            "last_name": {"required": True},
            "dob": {"required": True},
        }

    def validate_email(self, value):
        """Ensure email is unique and normalized."""
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(EMAIL_EXISTS_MESSAGE)
        return email

    def validate_phone_number(self, value):
        """Ensure phone number has valid format and is unique."""
        phone = normalize_phone_number(value)
        if not PHONE_REGEX.match(phone):
            raise serializers.ValidationError(INVALID_PHONE_MESSAGE)
        if User.objects.filter(phone_number=phone).exists():
            raise serializers.ValidationError(PHONE_EXISTS_MESSAGE)
        return phone

    def validate(self, attrs):
        """Ensure password confirmation matches."""
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": PASSWORD_MISMATCH_MESSAGE}
            )
        return attrs

    def create(self, validated_data):
        """Create a new user with a generated username and hashed password."""
        validated_data.pop("confirm_password")
        logger.info(f"Creating user with data: {validated_data}")

        first_name = validated_data["first_name"].strip()
        last_name = validated_data["last_name"].strip()
        middle_name = validated_data.get("middle_name", "").strip() or None
        username = generate_unique_username(first_name, last_name)

        user = User(
            phone_number=validated_data["phone_number"],
            email=validated_data["email"],
            dob=validated_data["dob"],
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            username=username,
        )
        # Hash password using model helper
        user.set_password(validated_data["password"])
        user.save()
        logger.info(f"User saved to database with ID: {user.id}")
        return user


class UserLoginSerializer(serializers.Serializer):
    email_or_phone = serializers.CharField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "dob",
        ]
        extra_kwargs = {
            "first_name": {"required": False},
            "middle_name": {"required": False, "allow_null": True},
            "last_name": {"required": False},
            "dob": {"required": False},
        }


class AdminProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Admin
        fields = [
            "full_name",
            "phone_number",
        ]
        extra_kwargs = {
            "full_name": {"required": False, "allow_null": True},
            "phone_number": {"required": False, "allow_null": True},
        }


class VendorProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = [
            "name",
            "phone_number",
            "theatre",
            "city",
        ]
        extra_kwargs = {
            "name": {"required": False},
            "phone_number": {"required": False, "allow_null": True},
            "theatre": {"required": False, "allow_null": True},
            "city": {"required": False, "allow_null": True},
        }


class MovieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movie
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "description",
            "long_description",
            "language",
            "genre",
            "genres",
            "duration",
            "duration_minutes",
            "rating",
            "release_date",
            "poster_image",
            "banner_image",
            "poster_url",
            "trailer_url",
            "status",
            "average_rating",
            "review_count",
            "is_active",
            "created_at",
            "updated_at",
        ]


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovieGenre
        fields = ["id", "name", "slug"]


class PersonSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = [
            "id",
            "full_name",
            "slug",
            "photo",
            "photo_url",
            "bio",
            "date_of_birth",
            "nationality",
            "instagram",
            "imdb",
            "facebook",
        ]

    def get_photo(self, obj):
        """Return the absolute photo URL or fallback to the stored URL."""
        request = self.context.get("request")
        return build_media_url(request, obj.photo) or obj.photo_url


class PersonWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = [
            "id",
            "full_name",
            "slug",
            "photo",
            "photo_url",
            "bio",
            "date_of_birth",
            "nationality",
            "instagram",
            "imdb",
            "facebook",
        ]


class PersonInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    full_name = serializers.CharField(required=False, allow_blank=False)
    photo = serializers.ImageField(required=False, allow_null=True)
    photo_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    bio = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    instagram = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    imdb = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    facebook = serializers.URLField(required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        """Require either a person ID or full name."""
        if not attrs.get("id") and not attrs.get("full_name"):
            raise ValidationError("Person id or full_name is required.")
        return attrs


class MovieCreditSerializer(serializers.ModelSerializer):
    person = PersonSerializer(read_only=True)

    class Meta:
        model = MovieCredit
        fields = [
            "id",
            "movie",
            "role_type",
            "character_name",
            "job_title",
            "position",
            "person",
        ]


class MovieCreditWriteSerializer(serializers.ModelSerializer):
    person_id = serializers.IntegerField(required=False, write_only=True)
    person = PersonInputSerializer(required=False, write_only=True)

    class Meta:
        model = MovieCredit
        fields = [
            "id",
            "movie",
            "role_type",
            "character_name",
            "job_title",
            "position",
            "person_id",
            "person",
        ]
        extra_kwargs = {
            "movie": {"required": False},
        }

    def validate(self, attrs):
        """Ensure person reference data exists for a credit."""
        if not attrs.get("person_id") and not attrs.get("person"):
            raise ValidationError("person_id or person data is required.")
        return attrs

    def create(self, validated_data):
        """Create a credit and resolve the referenced person."""
        person_id = validated_data.pop("person_id", None)
        person_data = validated_data.pop("person", None)
        person = _resolve_person_payload(person_id, person_data)
        return MovieCredit.objects.create(person=person, **validated_data)

    def update(self, instance, validated_data):
        """Update a credit and optionally replace the person reference."""
        person_id = validated_data.pop("person_id", None)
        person_data = validated_data.pop("person", None)
        if person_id or person_data:
            instance.person = _resolve_person_payload(person_id, person_data)
        return super().update(instance, validated_data)


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "user",
            "user_name",
            "movie",
            "rating",
            "comment",
            "is_approved",
            "created_at",
            "updated_at",
        ]

    def get_user_name(self, obj):
        """Return a friendly display name for the review author."""
        if not obj.user:
            return ""
        return obj.user.first_name or obj.user.email or str(obj.user_id)


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["movie", "user", "rating", "comment", "is_approved"]


class ReviewWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "movie", "user", "rating", "comment", "is_approved"]

    def validate(self, attrs):
        """Drop approval flag for non-admin requests."""
        request = self.context.get("request")
        from .permissions import is_admin_request

        if not request or not is_admin_request(request):
            attrs.pop("is_approved", None)
        return attrs


class MovieAdminReadSerializer(serializers.ModelSerializer):
    credits = MovieCreditSerializer(many=True, read_only=True)

    class Meta:
        model = Movie
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "description",
            "long_description",
            "language",
            "genre",
            "genres",
            "duration",
            "duration_minutes",
            "rating",
            "release_date",
            "poster_image",
            "banner_image",
            "poster_url",
            "trailer_url",
            "status",
            "average_rating",
            "review_count",
            "is_active",
            "created_at",
            "updated_at",
            "credits",
        ]


class MovieAdminWriteSerializer(serializers.ModelSerializer):
    credits = MovieCreditWriteSerializer(many=True, required=False)

    class Meta:
        model = Movie
        fields = [
            "id",
            "title",
            "slug",
            "short_description",
            "description",
            "long_description",
            "language",
            "genre",
            "genres",
            "duration",
            "duration_minutes",
            "rating",
            "release_date",
            "poster_image",
            "banner_image",
            "poster_url",
            "trailer_url",
            "status",
            "is_active",
            "credits",
        ]

    def _sync_credits(self, movie, credits_data):
        """Synchronize credits for a movie, creating/updating/removing as needed."""
        existing = {credit.id: credit for credit in movie.credits.all()}
        seen_ids = set()
        for idx, credit_payload in enumerate(credits_data):
            credit_id = credit_payload.get("id")
            position = credit_payload.get("position")
            if position is None:
                position = idx + 1
            person = _resolve_person_payload(
                credit_payload.get("person_id"),
                credit_payload.get("person"),
            )
            if credit_id and credit_id in existing:
                credit = existing[credit_id]
                credit.role_type = credit_payload.get("role_type")
                credit.character_name = credit_payload.get("character_name")
                credit.job_title = credit_payload.get("job_title")
                credit.position = position
                credit.person = person
                credit.save()
                seen_ids.add(credit.id)
            else:
                credit = MovieCredit.objects.create(
                    movie=movie,
                    person=person,
                    role_type=credit_payload.get("role_type"),
                    character_name=credit_payload.get("character_name"),
                    job_title=credit_payload.get("job_title"),
                    position=position,
                )
                seen_ids.add(credit.id)
        for credit_id, credit in existing.items():
            if credit_id not in seen_ids:
                credit.delete()

    def create(self, validated_data):
        """Create a movie and optionally sync credits in a transaction."""
        credits_data = validated_data.pop("credits", [])
        with transaction.atomic():
            movie = super().create(validated_data)
            if credits_data:
                self._sync_credits(movie, credits_data)
        return movie

    def update(self, instance, validated_data):
        """Update a movie and optionally sync credits in a transaction."""
        credits_data = validated_data.pop("credits", None)
        with transaction.atomic():
            movie = super().update(instance, validated_data)
            if credits_data is not None:
                self._sync_credits(movie, credits_data)
        return movie



class ShowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Show
        fields = [
            "id",
            "vendor",
            "movie",
            "hall",
            "slot",
            "screen_type",
            "price",
            "status",
            "listing_status",
            "show_date",
            "start_time",
            "end_time",
            "created_at",
        ]


class CollabDetailsSerializer(serializers.ModelSerializer):
    partner_logo = serializers.SerializerMethodField()
    partner_logo_2 = serializers.SerializerMethodField()

    class Meta:
        model = CollabDetails
        fields = [
            "partner_name",
            "partner_logo",
            "partner_logo_2",
            "headline",
            "offer_text",
            "promo_code_label",
            "promo_code",
            "terms_text",
            "primary_color",
            "secondary_color",
            "right_badge_text",
        ]

    def get_partner_logo(self, obj):
        """Return absolute URL for the primary partner logo."""
        request = self.context.get("request")
        return build_media_url(request, obj.partner_logo)

    def get_partner_logo_2(self, obj):
        """Return absolute URL for the secondary partner logo."""
        request = self.context.get("request")
        return build_media_url(request, obj.partner_logo_2)


class CollabDetailsAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollabDetails
        fields = [
            "partner_name",
            "partner_logo",
            "partner_logo_2",
            "headline",
            "offer_text",
            "promo_code_label",
            "promo_code",
            "terms_text",
            "primary_color",
            "secondary_color",
            "right_badge_text",
        ]


class HomeSlideAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeSlide
        fields = [
            "id",
            "slide_type",
            "movie",
            "title_override",
            "badge_text",
            "subtitle",
            "description_override",
            "background_image",
            "cta_text",
            "cta_type",
            "external_url",
            "sort_order",
            "is_active",
            "start_at",
            "end_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        """Validate slide type and CTA requirements."""
        instance = self.instance
        slide_type = attrs.get("slide_type", instance.slide_type if instance else None)
        movie = attrs.get("movie", instance.movie if instance else None)
        cta_type = attrs.get("cta_type", instance.cta_type if instance else None)
        external_url = attrs.get("external_url", instance.external_url if instance else None)

        if slide_type == HomeSlide.SLIDE_MOVIE and not movie:
            raise serializers.ValidationError("Movie is required for MOVIE slides.")
        if slide_type == HomeSlide.SLIDE_COLLAB and movie:
            raise serializers.ValidationError("Movie must be empty for COLLAB slides.")

        if cta_type == HomeSlide.CTA_EXTERNAL and not external_url:
            raise serializers.ValidationError("External URL is required for EXTERNAL_LINK CTA.")
        if cta_type in (HomeSlide.CTA_MOVIE_DETAIL, HomeSlide.CTA_BOOK_NOW) and not movie:
            raise serializers.ValidationError("Movie is required for MOVIE_DETAIL or BOOK_NOW CTA.")
        if slide_type == HomeSlide.SLIDE_COLLAB and cta_type in (
            HomeSlide.CTA_MOVIE_DETAIL,
            HomeSlide.CTA_BOOK_NOW,
        ):
            raise serializers.ValidationError("COLLAB slides must use EXTERNAL_LINK CTA.")

        return attrs


class HomeSlidePublicSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    genre = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    movie_id = serializers.SerializerMethodField()
    collab_details = CollabDetailsSerializer(read_only=True)

    class Meta:
        model = HomeSlide
        fields = [
            "id",
            "slide_type",
            "badge_text",
            "subtitle",
            "cta_text",
            "cta_type",
            "external_url",
            "sort_order",
            "movie_id",
            "title",
            "genre",
            "year",
            "duration",
            "description",
            "image",
            "collab_details",
        ]

    def get_movie_id(self, obj):
        """Expose movie ID for client usage."""
        return obj.movie_id

    def get_title(self, obj):
        """Return title override or movie title."""
        if obj.title_override:
            return obj.title_override
        if obj.movie:
            return obj.movie.title
        return ""

    def get_genre(self, obj):
        """Return movie genre if available."""
        return obj.movie.genre if obj.movie else ""

    def get_year(self, obj):
        """Return release year if available."""
        if not obj.movie or not obj.movie.release_date:
            return ""
        return obj.movie.release_date.year

    def get_duration(self, obj):
        """Return duration label for the movie if available."""
        if not obj.movie:
            return ""
        if obj.movie.duration_minutes:
            return f"{obj.movie.duration_minutes} min"
        return obj.movie.duration or ""

    def get_description(self, obj):
        """Return description override or movie description."""
        if obj.description_override:
            return obj.description_override
        if obj.movie:
            return obj.movie.description or ""
        return ""

    def get_image(self, obj):
        """Return the best available background image URL."""
        request = self.context.get("request")

        if obj.background_image:
            return build_media_url(request, obj.background_image)
        if obj.movie and obj.movie.banner_image:
            return build_media_url(request, obj.movie.banner_image)
        if obj.movie and obj.movie.poster_url:
            return obj.movie.poster_url
        return None


class NowShowingHeroMovieSerializer(serializers.ModelSerializer):
    movie_id = serializers.IntegerField(source="id", read_only=True)
    slide_type = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    year = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    poster_image = serializers.SerializerMethodField()
    trailer_url = serializers.CharField(read_only=True)
    badge_text = serializers.SerializerMethodField()
    cta_type = serializers.SerializerMethodField()
    cta_text = serializers.SerializerMethodField()

    class Meta:
        model = Movie
        fields = [
            "id",
            "movie_id",
            "slide_type",
            "title",
            "description",
            "genre",
            "year",
            "duration",
            "image",
            "poster_image",
            "trailer_url",
            "badge_text",
            "cta_type",
            "cta_text",
        ]

    def get_slide_type(self, obj):
        """Return slide type expected by hero slider."""
        return "MOVIE"

    def get_description(self, obj):
        """Return short description with fallback."""
        return obj.short_description or obj.description or ""

    def get_year(self, obj):
        """Return release year when available."""
        if not obj.release_date:
            return ""
        return obj.release_date.year

    def get_duration(self, obj):
        """Return duration label with minutes fallback."""
        if obj.duration:
            return obj.duration
        if obj.duration_minutes:
            return f"{obj.duration_minutes} min"
        return ""

    def get_image(self, obj):
        """Return the preferred hero background image."""
        request = self.context.get("request")
        if obj.banner_image:
            return build_media_url(request, obj.banner_image)
        if obj.poster_image:
            return build_media_url(request, obj.poster_image)
        return obj.poster_url

    def get_poster_image(self, obj):
        """Return the movie poster image URL."""
        request = self.context.get("request")
        poster = build_media_url(request, getattr(obj, "poster_image", None))
        return poster or obj.poster_url

    def get_badge_text(self, obj):
        """Return the static hero badge for this list."""
        return "Now Showing"

    def get_cta_type(self, obj):
        """Return CTA type used by existing hero slider."""
        return "BOOK_NOW"

    def get_cta_text(self, obj):
        """Return CTA label used by existing hero slider."""
        return "Buy Ticket"


class CollaboratorSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Collaborator
        fields = [
            "id",
            "name",
            "logo",
            "website_url",
            "sort_order",
            "is_active",
        ]

    def get_logo(self, obj):
        """Return absolute URL for collaborator logo."""
        request = self.context.get("request")
        return build_media_url(request, obj.logo)


class CollaboratorAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collaborator
        fields = [
            "id",
            "name",
            "logo",
            "website_url",
            "sort_order",
            "is_active",
        ]

class BannerCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = [
            "id",
            "banner_type",
            "movie",
            "image",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        """Enforce banner validation rules based on banner type."""
        instance = self.instance
        banner_type = attrs.get(
            "banner_type", instance.banner_type if instance else None
        )
        if banner_type == Banner.BannerType.PROMO and "movie" not in attrs:
            movie = None
        else:
            movie = attrs.get("movie", instance.movie if instance else None)
        image = attrs.get("image", instance.image if instance else None)

        errors = {}
        if not banner_type:
            errors["banner_type"] = "Banner type is required."
        if not image:
            errors["image"] = "Image is required."
        if banner_type == Banner.BannerType.MOVIE:
            if not movie:
                errors["movie"] = "Movie is required for movie banners."
        if banner_type == Banner.BannerType.PROMO and movie:
            errors["movie"] = "Movie must be empty for promo banners."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def update(self, instance, validated_data):
        """Ensure promo banners clear movie when omitted in payload."""
        banner_type = validated_data.get("banner_type", instance.banner_type)
        if banner_type == Banner.BannerType.PROMO and "movie" not in validated_data:
            validated_data["movie"] = None
        return super().update(instance, validated_data)


class BannerListSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    movie = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = [
            "id",
            "banner_type",
            "movie",
            "image",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_image(self, obj):
        """Return absolute URL for banner image."""
        request = self.context.get("request")
        return build_media_url(request, obj.image)

    def get_movie(self, obj):
        """Return a simplified movie payload for banner lists."""
        movie = obj.movie
        if not movie:
            return None
        request = self.context.get("request")
        poster_image = build_media_url(request, getattr(movie, "poster_image", None))
        banner_image = build_media_url(request, getattr(movie, "banner_image", None))
        poster_image = poster_image or movie.poster_url
        genre_value = movie.genre
        if not genre_value and hasattr(movie, "genres"):
            genres = list(movie.genres.all())
            if genres:
                genre_value = ", ".join(
                    [item.name for item in genres if item and item.name]
                )
        return {
            "id": movie.id,
            "slug": movie.slug,
            "title": movie.title,
            "shortDescription": movie.short_description or movie.description or "",
            "language": movie.language,
            "genre": genre_value,
            "duration": movie.duration,
            "durationMinutes": movie.duration_minutes,
            "rating": movie.rating,
            "releaseDate": movie.release_date.isoformat()
            if movie.release_date
            else None,
            "posterImage": poster_image,
            "bannerImage": banner_image,
            "status": movie.status,
        }
