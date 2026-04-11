"""DRF serializers for the application API."""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Optional

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .models import (
    Admin,
    Banner,
    CollabDetails,
    Collaborator,
    LoyaltyPromotion,
    LoyaltyTransaction,
    HomeSlide,
    Movie,
    MovieCredit,
    MovieGenre,
    Person,
    Reward,
    RewardRedemption,
    Review,
    Show,
    User,
    UserLoyaltyWallet,
    VendorLoyaltyRule,
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


def _coerce_credit_list(value: Any, *, field_name: str) -> Optional[list[Any]]:
    """Normalize a credit payload field into a list when provided."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                {field_name: f"Invalid JSON payload: {exc.msg}"}
            ) from exc
        if not isinstance(parsed, list):
            raise ValidationError({field_name: "Expected a list of credit objects."})
        return parsed
    raise ValidationError({field_name: "Expected a list of credit objects."})


def _normalize_credit_role_type(
    value: Any,
    *,
    default_role_type: Optional[str] = None,
) -> Optional[str]:
    """Normalize role type values into MovieCredit choices."""
    raw_value = str(value or default_role_type or "").strip().upper()
    if raw_value in {MovieCredit.ROLE_CAST, "ACTOR", "ACTRESS"}:
        return MovieCredit.ROLE_CAST
    if raw_value in {MovieCredit.ROLE_CREW, "STAFF"}:
        return MovieCredit.ROLE_CREW
    return None


def _normalize_person_credit_input(person_data: Any) -> dict[str, Any]:
    """Normalize person keys accepted by credit payloads."""
    source = person_data if isinstance(person_data, dict) else {}
    normalized: dict[str, Any] = {}

    mappings = {
        "id": source.get("id"),
        "full_name": source.get("full_name") or source.get("fullName") or source.get("name"),
        "photo": source.get("photo"),
        "photo_url": source.get("photo_url") or source.get("photoUrl"),
        "photo_upload_key": source.get("photo_upload_key") or source.get("photoUploadKey"),
        "bio": source.get("bio"),
        "date_of_birth": source.get("date_of_birth") or source.get("dateOfBirth"),
        "nationality": source.get("nationality"),
        "instagram": source.get("instagram"),
        "imdb": source.get("imdb"),
        "facebook": source.get("facebook"),
    }
    for key, value in mappings.items():
        if value is not None:
            normalized[key] = value

    return normalized


def _normalize_credit_input_item(
    item: Any,
    *,
    default_role_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Normalize one credit item into serializer write schema."""
    if not isinstance(item, dict):
        return None

    role_type = _normalize_credit_role_type(
        item.get("role_type")
        or item.get("roleType")
        or item.get("credit_type")
        or item.get("creditType"),
        default_role_type=default_role_type,
    )
    if not role_type:
        return None

    role_value = (
        item.get("role")
        or item.get("role_name")
        or item.get("roleName")
        or item.get("character_name")
        or item.get("characterName")
        or item.get("job_title")
        or item.get("jobTitle")
        or item.get("department")
    )
    character_name = (
        item.get("character_name")
        or item.get("characterName")
        or item.get("role_name")
        or item.get("roleName")
    )
    job_title = item.get("job_title") or item.get("jobTitle") or item.get("department")
    if not character_name and role_type == MovieCredit.ROLE_CAST:
        character_name = role_value
    if not job_title and role_type == MovieCredit.ROLE_CREW:
        job_title = role_value

    person_payload = _normalize_person_credit_input(
        item.get("person") if isinstance(item.get("person"), dict) else item.get("person_data")
    )
    if not person_payload.get("full_name") and not person_payload.get("id"):
        fallback_name = item.get("full_name") or item.get("fullName") or item.get("name")
        if fallback_name:
            person_payload["full_name"] = fallback_name

    normalized: dict[str, Any] = {
        "role_type": role_type,
    }

    credit_id = item.get("id")
    if credit_id is not None:
        normalized["id"] = credit_id

    character_name_value = character_name
    if character_name_value is not None:
        normalized["character_name"] = character_name_value

    job_title_value = job_title
    if job_title_value is not None:
        normalized["job_title"] = job_title_value

    position_value = item.get("position")
    if position_value is None:
        position_value = item.get("order")
    if position_value is not None:
        normalized["position"] = position_value

    person_id = item.get("person_id") or item.get("personId")
    if person_id not in (None, ""):
        normalized["person_id"] = person_id

    if person_payload:
        normalized["person"] = person_payload

    return normalized


def _extract_movie_credits_input(payload: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """Extract and normalize credits from credits/cast/crew payload formats."""
    if "credits" in payload:
        credits_input = _coerce_credit_list(payload.get("credits"), field_name="credits")
        normalized = [
            item
            for item in (
                _normalize_credit_input_item(entry)
                for entry in (credits_input or [])
            )
            if item
        ]
        return normalized

    cast = _coerce_credit_list(payload.get("cast"), field_name="cast") if "cast" in payload else None
    crew = _coerce_credit_list(payload.get("crew"), field_name="crew") if "crew" in payload else None
    if cast is None and crew is None:
        return None

    normalized: list[dict[str, Any]] = []
    for entry in cast or []:
        item = _normalize_credit_input_item(
            entry,
            default_role_type=MovieCredit.ROLE_CAST,
        )
        if item:
            normalized.append(item)
    for entry in crew or []:
        item = _normalize_credit_input_item(
            entry,
            default_role_type=MovieCredit.ROLE_CREW,
        )
        if item:
            normalized.append(item)
    return normalized


def _resolve_person_payload(
    person_id: Optional[int] = None,
    person_data: Optional[dict[str, Any]] = None,
    id_error_key: str = "person_id",
    data_error_key: str = "person",
    request: Optional[Any] = None,
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

    full_name = (
        person_data.get("full_name")
        or person_data.get("fullName")
        or person_data.get("name")
        or ""
    ).strip()
    if not full_name:
        raise ValidationError(
            {data_error_key: "full_name is required to create a new person."}
        )

    existing = Person.objects.filter(full_name__iexact=full_name).first()
    if existing:
        return existing

    upload_key = person_data.get("photo_upload_key") or person_data.get("photoUploadKey")
    uploaded_photo = None
    if request is not None and upload_key and hasattr(request, "FILES"):
        uploaded_photo = request.FILES.get(upload_key)

    return Person.objects.create(
        full_name=full_name,
        photo=uploaded_photo or person_data.get("photo"),
        photo_url=person_data.get("photo_url") or person_data.get("photoUrl"),
        bio=person_data.get("bio"),
        date_of_birth=person_data.get("date_of_birth") or person_data.get("dateOfBirth"),
        nationality=person_data.get("nationality"),
        instagram=person_data.get("instagram"),
        imdb=person_data.get("imdb"),
        facebook=person_data.get("facebook"),
    )


class UserRegistrationSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(required=True)
    referral_code = serializers.CharField(required=False, allow_blank=True, write_only=True)
    referralCode = serializers.CharField(required=False, allow_blank=True, write_only=True)
    device_fingerprint = serializers.CharField(required=False, allow_blank=True, write_only=True)
    deviceFingerprint = serializers.CharField(required=False, allow_blank=True, write_only=True)
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
            "referral_code",
            "referralCode",
            "device_fingerprint",
            "deviceFingerprint",
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
        referral_code = attrs.get("referral_code") or attrs.get("referralCode")
        if referral_code is not None:
            attrs["referral_code"] = str(referral_code).strip().upper()
        attrs.pop("referralCode", None)

        device_fingerprint = attrs.get("device_fingerprint") or attrs.get("deviceFingerprint")
        if device_fingerprint is not None:
            attrs["device_fingerprint"] = str(device_fingerprint).strip()[:128]
        attrs.pop("deviceFingerprint", None)

        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": PASSWORD_MISMATCH_MESSAGE}
            )
        return attrs

    def create(self, validated_data):
        """Create a new user with a generated username and hashed password."""
        validated_data.pop("confirm_password")
        validated_data.pop("referral_code", None)
        validated_data.pop("device_fingerprint", None)
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
            "trailer_urls",
            "status",
            "average_rating",
            "review_count",
            "is_active",
            "is_approved",
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
    fullName = serializers.CharField(required=False, allow_blank=False, write_only=True)
    photo = serializers.ImageField(required=False, allow_null=True)
    photo_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    photoUrl = serializers.URLField(required=False, allow_null=True, allow_blank=True, write_only=True)
    photo_upload_key = serializers.CharField(required=False, allow_blank=True, write_only=True)
    photoUploadKey = serializers.CharField(required=False, allow_blank=True, write_only=True)
    bio = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    dateOfBirth = serializers.DateField(required=False, allow_null=True, write_only=True)
    nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    instagram = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    imdb = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    facebook = serializers.URLField(required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        """Require either a person ID or full name."""
        full_name = attrs.get("full_name") or attrs.get("fullName")
        if full_name:
            attrs["full_name"] = str(full_name).strip()
        attrs.pop("fullName", None)

        photo_url = attrs.get("photo_url") or attrs.get("photoUrl")
        if photo_url is not None:
            attrs["photo_url"] = photo_url
        attrs.pop("photoUrl", None)

        date_of_birth = attrs.get("date_of_birth") or attrs.get("dateOfBirth")
        if date_of_birth is not None:
            attrs["date_of_birth"] = date_of_birth
        attrs.pop("dateOfBirth", None)

        photo_upload_key = attrs.get("photo_upload_key") or attrs.get("photoUploadKey")
        if photo_upload_key:
            attrs["photo_upload_key"] = str(photo_upload_key).strip()
        else:
            attrs.pop("photo_upload_key", None)
        attrs.pop("photoUploadKey", None)

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
        person = _resolve_person_payload(
            person_id,
            person_data,
            request=self.context.get("request"),
        )
        return MovieCredit.objects.create(person=person, **validated_data)

    def update(self, instance, validated_data):
        """Update a credit and optionally replace the person reference."""
        person_id = validated_data.pop("person_id", None)
        person_data = validated_data.pop("person", None)
        if person_id or person_data:
            instance.person = _resolve_person_payload(
                person_id,
                person_data,
                request=self.context.get("request"),
            )
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
            "trailer_urls",
            "status",
            "average_rating",
            "review_count",
            "approval_status",
            "approval_reason",
            "approval_metadata",
            "approved_by",
            "approved_at",
            "is_active",
            "is_approved",
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
            "trailer_urls",
            "status",
            "is_active",
            "is_approved",
            "approval_status",
            "approval_reason",
            "approval_metadata",
            "approved_by",
            "approved_at",
            "credits",
        ]
        read_only_fields = ["approval_metadata"]

    def to_internal_value(self, data):
        """Accept both camelCase and snake_case payload keys from admin clients."""
        mutable = data.copy() if hasattr(data, "copy") else dict(data)
        aliases = {
            "shortDescription": "short_description",
            "longDescription": "long_description",
            "durationMinutes": "duration_minutes",
            "releaseDate": "release_date",
            "posterImage": "poster_image",
            "bannerImage": "banner_image",
            "posterUrl": "poster_url",
            "trailerUrl": "trailer_url",
            "trailerUrls": "trailer_urls",
            "trailers": "trailer_urls",
            "isActive": "is_active",
            "isApproved": "is_approved",
            "approvalStatus": "approval_status",
            "approvalReason": "approval_reason",
            "approvalMetadata": "approval_metadata",
            "synopsis": "description",
        }
        for source_key, target_key in aliases.items():
            if source_key in mutable and target_key not in mutable:
                mutable[target_key] = mutable.get(source_key)

        # Ignore empty image placeholders on PATCH to preserve existing files.
        if self.instance and self.partial:
            for image_field in ("poster_image", "banner_image"):
                if image_field not in mutable:
                    continue
                raw_value = mutable.get(image_field)
                if raw_value is None:
                    del mutable[image_field]
                    continue
                if isinstance(raw_value, str) and raw_value.strip().lower() in {
                    "",
                    "null",
                    "undefined",
                }:
                    del mutable[image_field]

        normalized_credits = _extract_movie_credits_input(mutable)
        if normalized_credits is not None:
            mutable["credits"] = normalized_credits

        # DRF treats QueryDict as HTML form input and ignores direct list values
        # for nested serializers unless indexed keys are used. Flatten to a plain
        # dict so normalized credits lists are validated consistently.
        if hasattr(mutable, "getlist"):
            flattened: dict[str, Any] = {}
            for key in mutable.keys():
                values = mutable.getlist(key)
                if len(values) == 1:
                    flattened[key] = values[0]
                else:
                    flattened[key] = values
            mutable = flattened

        return super().to_internal_value(mutable)

    def _sync_credits(self, movie, credits_data):
        """Synchronize credits for a movie, creating/updating/removing as needed."""
        existing = {credit.id: credit for credit in movie.credits.all()}
        seen_ids = set()
        request = self.context.get("request")
        for idx, credit_payload in enumerate(credits_data):
            credit_id = credit_payload.get("id")
            position = credit_payload.get("position")
            if position is None:
                position = idx + 1
            role_type = _normalize_credit_role_type(credit_payload.get("role_type"))
            if not role_type:
                continue
            person = _resolve_person_payload(
                credit_payload.get("person_id"),
                credit_payload.get("person"),
                request=request,
            )
            if credit_id and credit_id in existing:
                credit = existing[credit_id]
                credit.role_type = role_type
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
                    role_type=role_type,
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
        approval_status = validated_data.pop("approval_status", None)
        approval_reason = validated_data.pop("approval_reason", None)
        approval_metadata = validated_data.pop("approval_metadata", None)
        with transaction.atomic():
            validated_data.setdefault("is_approved", True)
            movie = super().create(validated_data)
            if credits_data:
                self._sync_credits(movie, credits_data)
            request = self.context.get("request")
            if request:
                from .permissions import is_admin_request, resolve_admin

                if is_admin_request(request):
                    now = timezone.now()
                    decision_status = str(approval_status or movie.approval_status or "").strip().upper()
                    if not decision_status:
                        decision_status = movie.ApprovalStatus.APPROVED if movie.is_approved else movie.ApprovalStatus.PENDING
                    movie.approval_status = decision_status
                    movie.approved_by = resolve_admin(request)
                    movie.approved_at = now
                    movie.approval_reason = str(approval_reason or "").strip() or None
                    current_metadata = dict(movie.approval_metadata or {})
                    if isinstance(approval_metadata, dict):
                        current_metadata.update(approval_metadata)
                    current_metadata.update(
                        {
                            "source": "admin_serializer_create",
                            "decision": decision_status,
                            "decision_by": getattr(movie.approved_by, "id", None),
                            "decision_at": now.isoformat(),
                            "reason": movie.approval_reason,
                        }
                    )
                    movie.approval_metadata = current_metadata
                    movie.save(update_fields=["approval_status", "approval_reason", "approval_metadata", "approved_by", "approved_at", "is_approved", "updated_at"])
        return movie

    def update(self, instance, validated_data):
        """Update a movie and optionally sync credits in a transaction."""
        credits_data = validated_data.pop("credits", None)
        approval_status = validated_data.pop("approval_status", None)
        approval_reason = validated_data.pop("approval_reason", None)
        approval_metadata = validated_data.pop("approval_metadata", None)
        with transaction.atomic():
            movie = super().update(instance, validated_data)
            if credits_data is not None:
                self._sync_credits(movie, credits_data)
            request = self.context.get("request")
            if request:
                from .permissions import is_admin_request, resolve_admin

                if is_admin_request(request) and (
                    approval_status is not None
                    or approval_reason is not None
                    or approval_metadata is not None
                    or "is_approved" in validated_data
                ):
                    now = timezone.now()
                    decision_status = str(approval_status or movie.approval_status or "").strip().upper()
                    if decision_status not in Movie.ApprovalStatus.values:
                        decision_status = movie.ApprovalStatus.APPROVED if movie.is_approved else movie.ApprovalStatus.PENDING
                    movie.approval_status = decision_status
                    movie.approved_by = resolve_admin(request)
                    movie.approved_at = now
                    if approval_reason is not None:
                        movie.approval_reason = str(approval_reason or "").strip() or None
                    current_metadata = dict(movie.approval_metadata or {})
                    if isinstance(approval_metadata, dict):
                        current_metadata.update(approval_metadata)
                    current_metadata.update(
                        {
                            "source": "admin_serializer_update",
                            "decision": decision_status,
                            "decision_by": getattr(movie.approved_by, "id", None),
                            "decision_at": now.isoformat(),
                            "reason": movie.approval_reason,
                        }
                    )
                    movie.approval_metadata = current_metadata
                    movie.save(update_fields=["approval_status", "approval_reason", "approval_metadata", "approved_by", "approved_at", "is_approved", "updated_at"])
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


class UserLoyaltyWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserLoyaltyWallet
        fields = [
            "user",
            "total_points",
            "available_points",
            "lifetime_points",
            "tier",
            "created_at",
            "updated_at",
        ]


class LoyaltyTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyTransaction
        fields = [
            "id",
            "user",
            "transaction_type",
            "points",
            "reference_type",
            "reference_id",
            "idempotency_key",
            "expires_at",
            "is_expired",
            "metadata",
            "created_at",
        ]


class RewardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reward
        fields = [
            "id",
            "title",
            "description",
            "points_required",
            "reward_type",
            "discount_amount",
            "discount_percent",
            "max_discount_amount",
            "vendor",
            "stock_limit",
            "redeemed_count",
            "expiry_date",
            "is_active",
            "is_stackable_with_coupon",
            "created_at",
            "updated_at",
        ]


class RewardRedemptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RewardRedemption
        fields = [
            "id",
            "user",
            "reward",
            "points_used",
            "booking",
            "status",
            "redemption_code",
            "expires_at",
            "used_at",
            "metadata",
            "created_at",
        ]


class VendorLoyaltyRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorLoyaltyRule
        fields = [
            "vendor",
            "points_per_currency_unit",
            "first_booking_bonus",
            "bonus_multiplier",
            "is_active",
            "created_at",
            "updated_at",
        ]


class LoyaltyPromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyPromotion
        fields = [
            "id",
            "title",
            "description",
            "promo_type",
            "trigger_code",
            "vendor",
            "bonus_multiplier",
            "bonus_flat_points",
            "stackable",
            "starts_at",
            "ends_at",
            "is_active",
            "created_at",
            "updated_at",
        ]


class LoyaltyCheckoutPreviewSerializer(serializers.Serializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    points_to_redeem = serializers.IntegerField(required=False, min_value=0)
    reward_id = serializers.IntegerField(required=False, min_value=1)
    vendor_id = serializers.IntegerField(required=False, min_value=1)
