from rest_framework import serializers
from .models import (
    User,
    Admin,
    Vendor,
    Movie,
    Show,
    HomeSlide,
    CollabDetails,
    Collaborator,
)
import logging
import random
import re

logger = logging.getLogger(__name__)


def generate_unique_username(first_name, last_name):
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


class UserRegistrationSerializer(serializers.ModelSerializer):
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
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email already exists")
        return email

    def validate_phone_number(self, value):
        phone = value.strip()
        if not re.match(r"^\+?[0-9]{10,13}$", phone):
            raise serializers.ValidationError("Invalid phone number format")
        if User.objects.filter(phone_number=phone).exists():
            raise serializers.ValidationError("Phone number already exists")
        return phone

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match"}
            )
        return attrs

    def create(self, validated_data):
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
            "description",
            "language",
            "genre",
            "duration",
            "duration_minutes",
            "rating",
            "release_date",
            "banner_image",
            "poster_url",
            "trailer_url",
            "status",
            "created_at",
        ]


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

    def _build_url(self, field):
        if not field:
            return None
        try:
            url = field.url
        except Exception:
            return None
        request = self.context.get("request")
        if request is None:
            return url
        return request.build_absolute_uri(url)

    def get_partner_logo(self, obj):
        return self._build_url(obj.partner_logo)

    def get_partner_logo_2(self, obj):
        return self._build_url(obj.partner_logo_2)


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
        return obj.movie_id

    def get_title(self, obj):
        if obj.title_override:
            return obj.title_override
        if obj.movie:
            return obj.movie.title
        return ""

    def get_genre(self, obj):
        return obj.movie.genre if obj.movie else ""

    def get_year(self, obj):
        if not obj.movie or not obj.movie.release_date:
            return ""
        return obj.movie.release_date.year

    def get_duration(self, obj):
        if not obj.movie:
            return ""
        if obj.movie.duration_minutes:
            return f"{obj.movie.duration_minutes} min"
        return obj.movie.duration or ""

    def get_description(self, obj):
        if obj.description_override:
            return obj.description_override
        if obj.movie:
            return obj.movie.description or ""
        return ""

    def get_image(self, obj):
        request = self.context.get("request")

        def build_url(field):
            if not field:
                return None
            try:
                url = field.url
            except Exception:
                return None
            if request is None:
                return url
            return request.build_absolute_uri(url)

        if obj.background_image:
            return build_url(obj.background_image)
        if obj.movie and obj.movie.banner_image:
            return build_url(obj.movie.banner_image)
        if obj.movie and obj.movie.poster_url:
            return obj.movie.poster_url
        return None


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
        if not obj.logo:
            return None
        try:
            url = obj.logo.url
        except Exception:
            return None
        request = self.context.get("request")
        if request is None:
            return url
        return request.build_absolute_uri(url)


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
