"""Service layer helpers and business logic."""

from __future__ import annotations

import base64
import io
import json
import logging
import random
import re
import uuid
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from typing import Any, Iterable, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.html import escape
from PIL import Image, ImageDraw, ImageFont
from rest_framework import status

from .models import (
    User,
    Admin,
    Vendor,
    Movie,
    Person,
    MovieCredit,
    Show,
    Banner,
    HomeSlide,
    Collaborator,
    OTPVerification,
    Ticket,
    Screen,
    Seat,
    Showtime,
    SeatAvailability,
    Booking,
    BookingSeat,
)
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileUpdateSerializer,
    AdminProfileUpdateSerializer,
    VendorProfileUpdateSerializer,
    generate_unique_username,
    HomeSlideAdminSerializer,
    CollabDetailsAdminSerializer,
    CollaboratorAdminSerializer,
    BannerCreateUpdateSerializer,
)
from .permissions import (
    is_admin_request,
    is_authenticated,
    issue_access_token,
    resolve_admin,
    resolve_vendor,
)
from .selectors import build_movie_payload, build_show_payload, get_ticket
from .utils import (
    coalesce,
    get_payload,
    get_profile_image_url,
    is_phone_like,
    normalize_phone_number,
    parse_date,
    parse_time,
    parse_bool,
    request_data_to_dict,
    short_label,
    slugify_text,
)

logger = logging.getLogger(__name__)

PHONE_REGEX = re.compile(r"^[0-9]{10,13}$")
DEFAULT_VENDOR_STATUS = "Active"
STATUS_BLOCKED = "Blocked"
AUTH_REQUIRED_MESSAGE = "Authentication required"
ADMIN_REQUIRED_MESSAGE = "Admin access required"
INVALID_PHONE_MESSAGE = "Invalid phone number format"
SEAT_STATUS_SOLD = "Sold"
SEAT_STATUS_BOOKED = "Booked"
SEAT_STATUS_AVAILABLE = "Available"
SEAT_STATUS_UNAVAILABLE = "Unavailable"
BOOKING_STATUS_CONFIRMED = "Confirmed"
DEFAULT_GUEST_EMAIL = "guest.booking@meroticket.local"
DEFAULT_GUEST_NAME = "Guest"
SEAT_CATEGORY_NORMAL = "Normal"
SEAT_CATEGORY_EXECUTIVE = "Executive"
SEAT_CATEGORY_PREMIUM = "Premium"
SEAT_CATEGORY_VIP = "VIP"
SEAT_CATEGORY_ORDER = [
    SEAT_CATEGORY_NORMAL,
    SEAT_CATEGORY_EXECUTIVE,
    SEAT_CATEGORY_PREMIUM,
    SEAT_CATEGORY_VIP,
]
SEAT_CATEGORY_KEYS = {
    SEAT_CATEGORY_NORMAL: "normal",
    SEAT_CATEGORY_EXECUTIVE: "executive",
    SEAT_CATEGORY_PREMIUM: "premium",
    SEAT_CATEGORY_VIP: "vip",
}
BOOKED_STATUSES = {SEAT_STATUS_BOOKED.lower(), SEAT_STATUS_SOLD.lower()}


def build_user_payload(user: User, request: Any) -> dict[str, Any]:
    """Build the API payload for a user."""
    full_name = " ".join(
        [part for part in [user.first_name, user.middle_name, user.last_name] if part]
    ).strip()
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "last_name": user.last_name,
        "full_name": full_name,
        "phone_number": user.phone_number,
        "profile_image": get_profile_image_url(request, user),
        "dob": user.dob.isoformat() if user.dob else None,
        "is_active": getattr(user, "is_active", True),
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
    }


def build_admin_payload(admin_user: Admin, request: Any) -> dict[str, Any]:
    """Build the API payload for an admin user."""
    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "username": admin_user.username,
        "full_name": admin_user.full_name,
        "phone_number": admin_user.phone_number,
        "is_active": admin_user.is_active,
        "profile_image": get_profile_image_url(request, admin_user),
        "date_joined": admin_user.date_joined.isoformat()
        if admin_user.date_joined
        else None,
    }


def build_vendor_payload(vendor_user: Vendor, request: Any) -> dict[str, Any]:
    """Build the API payload for a vendor user."""
    return {
        "id": vendor_user.id,
        "name": vendor_user.name,
        "email": vendor_user.email,
        "username": vendor_user.username,
        "phone_number": vendor_user.phone_number,
        "theatre": vendor_user.theatre,
        "city": vendor_user.city,
        "status": vendor_user.status,
        "is_active": vendor_user.is_active,
        "created_at": vendor_user.created_at.isoformat() if vendor_user.created_at else None,
        "profile_image": get_profile_image_url(request, vendor_user),
    }


def _login_identity_query(
    identifier: str,
    phone_candidates: Optional[set[str]] = None,
    include_username: bool = True,
) -> Q:
    """Build a login query for email/phone/username."""
    query = Q(email__iexact=identifier)
    if phone_candidates:
        query |= Q(phone_number__in=phone_candidates)
    else:
        query |= Q(phone_number=identifier)
    if include_username:
        query |= Q(username__iexact=identifier)
    return query


def _admin_lookup_query_from_user(user: User) -> Q:
    """Build a query to find an Admin matching a User identity."""
    query = Q(email__iexact=user.email)
    if user.username:
        query |= Q(username__iexact=user.username)
    if user.phone_number:
        query |= Q(phone_number=user.phone_number)
    return query


def _admin_login_payload(admin: Admin, password: str, request: Any) -> tuple[dict[str, Any], int]:
    """Return the admin login response payload."""
    if not admin.is_active:
        return {"message": "Admin account is inactive"}, status.HTTP_403_FORBIDDEN
    if not admin.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED
    display_name = admin.full_name or admin.username or admin.email
    access_token = issue_access_token("admin", admin.id)
    return {
        "message": f"Admin login successful. Welcome {display_name}!",
        "role": "admin",
        "admin": build_admin_payload(admin, request),
        "access_token": access_token,
    }, status.HTTP_200_OK


def _vendor_login_payload(vendor: Vendor, password: str, request: Any) -> tuple[dict[str, Any], int]:
    """Return the vendor login response payload."""
    if not vendor.is_active or str(vendor.status).lower() == "blocked":
        return {"message": "Vendor account is inactive"}, status.HTTP_403_FORBIDDEN
    if not vendor.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED
    display_name = vendor.name or vendor.username or vendor.email
    access_token = issue_access_token("vendor", vendor.id)
    return {
        "message": f"Vendor login successful. Welcome {display_name}!",
        "role": "vendor",
        "vendor": build_vendor_payload(vendor, request),
        "access_token": access_token,
    }, status.HTTP_200_OK


def _is_truthy_flag(value: Any) -> bool:
    """Normalize common truthy flag values."""
    return str(value or "").lower() in ("1", "true", "yes")


def _update_profile_image(instance: Any, uploaded_image: Any, remove_avatar: bool) -> None:
    """Update or clear profile image based on inputs."""
    if remove_avatar:
        if instance.profile_image:
            instance.profile_image.delete(save=False)
        instance.profile_image = None
        instance.save()
        return
    if uploaded_image:
        if instance.profile_image:
            instance.profile_image.delete(save=False)
        instance.profile_image = uploaded_image
        instance.save()


def register_user(request: Any) -> tuple[dict[str, Any], int]:
    """Register a new user account."""
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        try:
            user = serializer.save()
            return {
                "message": "Registration successful",
                "user": build_user_payload(user, request),
            }, status.HTTP_201_CREATED
        except Exception as exc:
            logger.exception("Error saving user")
            return {
                "message": "Failed to create user",
                "error": str(exc),
            }, status.HTTP_500_INTERNAL_SERVER_ERROR

    return {
        "message": "Registration failed",
        "errors": serializer.errors,
    }, status.HTTP_400_BAD_REQUEST


def login_user(request: Any) -> tuple[dict[str, Any], int]:
    """Authenticate a user, vendor, or admin."""
    serializer = UserLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return {
            "message": "Invalid input",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    raw_identifier = serializer.validated_data["email_or_phone"].strip()
    password = serializer.validated_data["password"]
    phone_candidates: Optional[set[str]] = None
    if is_phone_like(raw_identifier):
        normalized_phone = normalize_phone_number(raw_identifier)
        if normalized_phone:
            phone_candidates = {normalized_phone, raw_identifier}

    try:
        admin = Admin.objects.filter(
            _login_identity_query(raw_identifier, phone_candidates)
        ).first()
        if admin:
            return _admin_login_payload(admin, password, request)

        vendor_query = _login_identity_query(raw_identifier, phone_candidates)
        if str(raw_identifier).isdigit():
            try:
                vendor_query |= Q(id=int(raw_identifier))
            except ValueError:
                pass

        vendor = Vendor.objects.filter(vendor_query).first()

        if vendor:
            return _vendor_login_payload(vendor, password, request)

        user_phone_query = (
            Q(phone_number__in=phone_candidates)
            if phone_candidates
            else Q(phone_number=raw_identifier)
        )
        user = User.objects.filter(
            Q(email__iexact=raw_identifier) | user_phone_query
        ).first()

        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        admin_for_user = Admin.objects.filter(_admin_lookup_query_from_user(user)).first()
        if admin_for_user:
            return _admin_login_payload(admin_for_user, password, request)

        if hasattr(user, "is_active") and not user.is_active:
            return {"message": "User account is inactive"}, status.HTTP_403_FORBIDDEN

        if not user.check_password(password):
            return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED

        access_token = issue_access_token("customer", user.id)
        return {
            "message": f"Login successful. Welcome {user.first_name}!",
            "role": "user",
            "user": build_user_payload(user, request),
            "access_token": access_token,
        }, status.HTTP_200_OK

    except Exception as exc:
        logger.exception("Login error")
        return {
            "message": "An error occurred during login",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def list_vendors_payload(request: Any) -> list[dict[str, Any]]:
    """Return vendor payloads for admin/vendor views."""
    vendors = Vendor.objects.all().order_by("-created_at")
    vendor = resolve_vendor(request)
    if vendor:
        vendors = vendors.filter(pk=vendor.pk)
    return [build_vendor_payload(vendor, request) for vendor in vendors]


def list_users_payload(request: Any) -> list[dict[str, Any]]:
    """Return user payloads for admin views."""
    users = User.objects.all().order_by("-date_joined")
    return [build_user_payload(user, request) for user in users]


def create_admin_user(request: Any) -> tuple[dict[str, Any], int]:
    """Create a user account from the admin panel."""
    payload = get_payload(request)

    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    middle_name = str(payload.get("middle_name") or "").strip() or None
    email = str(payload.get("email") or "").strip().lower()
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    password = str(payload.get("password") or "")
    dob_value = payload.get("dob")
    dob = parse_date(dob_value)
    is_active = parse_bool(payload.get("is_active"), default=True)

    if not first_name or not last_name or not email or not raw_phone or not password:
        return {
            "message": "First name, last name, email, phone number, and password are required"
        }, status.HTTP_400_BAD_REQUEST

    if dob is None:
        return {"message": "Date of birth is required"}, status.HTTP_400_BAD_REQUEST

    if not phone_number or not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if User.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST

    if User.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST

    if username and User.objects.filter(username__iexact=username).exists():
        return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST

    if not username:
        username = generate_unique_username(first_name, last_name)

    user = User(
        phone_number=phone_number,
        email=email,
        dob=dob,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        username=username,
        is_active=is_active,
    )
    user.set_password(password)
    user.save()

    return {
        "message": "User created",
        "user": build_user_payload(user, request),
    }, status.HTTP_201_CREATED


def update_admin_user(user: User, request: Any) -> tuple[dict[str, Any], int]:
    """Update a user account from the admin panel."""
    payload = get_payload(request)

    if "first_name" in payload:
        first_name = str(payload.get("first_name") or "").strip()
        if not first_name:
            return {"message": "First name is required"}, status.HTTP_400_BAD_REQUEST
        user.first_name = first_name

    if "last_name" in payload:
        last_name = str(payload.get("last_name") or "").strip()
        if not last_name:
            return {"message": "Last name is required"}, status.HTTP_400_BAD_REQUEST
        user.last_name = last_name

    if "middle_name" in payload:
        middle_name = str(payload.get("middle_name") or "").strip() or None
        user.middle_name = middle_name

    if "email" in payload:
        email = str(payload.get("email") or "").strip().lower()
        if not email:
            return {"message": "Email is required"}, status.HTTP_400_BAD_REQUEST
        if User.objects.filter(email__iexact=email).exclude(pk=user.id).exists():
            return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST
        user.email = email

    if "phone_number" in payload:
        raw_phone = str(payload.get("phone_number") or "").strip()
        phone_number = normalize_phone_number(raw_phone)
        if not raw_phone:
            return {"message": "Phone number is required"}, status.HTTP_400_BAD_REQUEST
        if not phone_number or not PHONE_REGEX.match(phone_number):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if (
            User.objects.filter(phone_number=phone_number)
            .exclude(pk=user.id)
            .exists()
        ):
            return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST
        user.phone_number = phone_number

    if "username" in payload:
        username = str(payload.get("username") or "").strip() or None
        if username and User.objects.filter(username__iexact=username).exclude(pk=user.id).exists():
            return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST
        user.username = username

    if "dob" in payload:
        dob_value = payload.get("dob")
        dob = parse_date(dob_value)
        if dob is None:
            return {"message": "Invalid date of birth"}, status.HTTP_400_BAD_REQUEST
        user.dob = dob

    if "is_active" in payload:
        user.is_active = parse_bool(payload.get("is_active"), default=True)

    if "password" in payload:
        password = str(payload.get("password") or "")
        if password:
            user.set_password(password)

    user.save()
    return {
        "message": "User updated",
        "user": build_user_payload(user, request),
    }, status.HTTP_200_OK


def create_vendor(request: Any) -> tuple[dict[str, Any], int]:
    """Create a vendor account."""
    payload = get_payload(request)

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    theatre = (
        str(payload.get("theatre") or payload.get("theatre_name") or "").strip()
        or None
    )
    city = str(payload.get("city") or "").strip() or None
    status_label = str(payload.get("status") or DEFAULT_VENDOR_STATUS).strip() or DEFAULT_VENDOR_STATUS
    status_label = status_label.title()

    if not name or not email or not password:
        return {
            "message": "Name, email, and password are required"
        }, status.HTTP_400_BAD_REQUEST

    if Vendor.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST

    if raw_phone and not phone_number:
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and Vendor.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST

    if username and Vendor.objects.filter(username__iexact=username).exists():
        return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST

    is_active = status_label.lower() != STATUS_BLOCKED.lower()
    vendor = Vendor(
        name=name,
        email=email,
        phone_number=phone_number or None,
        username=username,
        theatre=theatre,
        city=city,
        status=status_label,
        is_active=is_active,
    )
    vendor.set_password(password)
    vendor.save()

    return {
        "message": "Vendor created",
        "vendor": build_vendor_payload(vendor, request),
    }, status.HTTP_201_CREATED


def list_cinemas_payload(request: Any) -> list[dict[str, Any]]:
    """Return cinema vendor payloads for public views."""
    vendors = (
        Vendor.objects.filter(is_active=True)
        .exclude(status__iexact=STATUS_BLOCKED)
        .order_by("name", "id")
    )
    return build_cinemas_payload(vendors, request)


def build_cinemas_payload(
    vendors: Iterable[Vendor], request: Optional[Any] = None
) -> list[dict[str, Any]]:
    """Build cinema payloads for dropdowns and listings."""
    payload = []
    used_slugs = set()
    for vendor in vendors:
        display_name = (
            vendor.name
            or vendor.theatre
            or vendor.username
            or vendor.email
            or f"Vendor {vendor.id}"
        )
        slug_base = slugify_text(display_name)
        slug = slug_base or f"vendor-{vendor.id}"
        if slug in used_slugs:
            slug = f"{slug}-{vendor.id}"
        used_slugs.add(slug)
        payload.append(
            {
                "id": vendor.id,
                "name": display_name,
                "theatre": vendor.theatre,
                "city": vendor.city,
                "slug": slug,
                "short": short_label(display_name),
                "profile_image": get_profile_image_url(request, vendor),
            }
        )
    return payload


def _sync_collab_details(slide: HomeSlide, payload: dict[str, Any]) -> Optional[Any]:
    """Sync collaboration details for a slide."""
    if slide.slide_type != HomeSlide.SLIDE_COLLAB:
        if hasattr(slide, "collab_details"):
            slide.collab_details.delete()
        return None

    instance = getattr(slide, "collab_details", None)
    serializer = CollabDetailsAdminSerializer(
        instance=instance,
        data=payload,
        partial=instance is not None,
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(slide=slide)


def create_home_slide(data: dict[str, Any]) -> HomeSlide:
    """Create a home slide with optional collaboration details."""
    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, data)
    return slide


def update_home_slide(slide: HomeSlide, data: dict[str, Any]) -> HomeSlide:
    """Update a home slide with optional collaboration details."""
    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(slide, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, data)
    return slide


def toggle_home_slide(slide: HomeSlide) -> HomeSlide:
    """Toggle the active state for a home slide."""
    slide.is_active = not slide.is_active
    slide.save(update_fields=["is_active"])
    return slide


def create_collaborator(data: dict[str, Any]) -> Collaborator:
    """Create a collaborator."""
    serializer = CollaboratorAdminSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def update_collaborator(collaborator: Collaborator, data: dict[str, Any]) -> Collaborator:
    """Update a collaborator."""
    serializer = CollaboratorAdminSerializer(collaborator, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def toggle_collaborator(collaborator: Collaborator) -> Collaborator:
    """Toggle collaborator active state."""
    collaborator.is_active = not collaborator.is_active
    collaborator.save(update_fields=["is_active"])
    return collaborator


def create_banner(data: dict[str, Any]) -> Banner:
    """Create a banner."""
    serializer = BannerCreateUpdateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def update_banner(banner: Banner, data: dict[str, Any]) -> Banner:
    """Update a banner."""
    serializer = BannerCreateUpdateSerializer(banner, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def _coerce_list(value: Any) -> Optional[list[Any]]:
    """Normalize a payload field into a list if possible."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return None
    return None


def _normalize_credit_item(
    item: Any, default_role_type: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Normalize a credit payload into the canonical schema."""
    if not isinstance(item, dict):
        return None
    role_type = (
        item.get("role_type")
        or item.get("roleType")
        or item.get("credit_type")
        or item.get("creditType")
        or default_role_type
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
    person_payload = item.get("person") or item.get("person_data") or {}
    if not person_payload:
        name_value = item.get("full_name") or item.get("fullName") or item.get("name")
        if name_value:
            person_payload = {"full_name": name_value}
    return {
        "id": item.get("id"),
        "role_type": role_type,
        "character_name": character_name,
        "job_title": job_title,
        "position": item.get("position") or item.get("order"),
        "person_id": item.get("person_id") or item.get("personId"),
        "person": person_payload,
    }


def _extract_credits_payload(payload: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """Extract normalized credits payload from request data."""
    if "credits" in payload:
        return _coerce_list(payload.get("credits")) or []
    cast = _coerce_list(payload.get("cast"))
    crew = _coerce_list(payload.get("crew"))
    if cast is None and crew is None:
        return None
    credits = []
    if cast:
        credits.extend(
            filter(
                None,
                [
                    _normalize_credit_item(item, default_role_type=MovieCredit.ROLE_CAST)
                    for item in cast
                ],
            )
        )
    if crew:
        credits.extend(
            filter(
                None,
                [
                    _normalize_credit_item(item, default_role_type=MovieCredit.ROLE_CREW)
                    for item in crew
                ],
            )
        )
    return credits


def _resolve_person_from_credit(credit: dict[str, Any]) -> Optional[Person]:
    """Resolve or create a person from a credit payload."""
    person_id = credit.get("person_id")
    if person_id:
        return Person.objects.filter(pk=person_id).first()
    person_data = credit.get("person") if isinstance(credit.get("person"), dict) else {}
    if person_data.get("id"):
        return Person.objects.filter(pk=person_data.get("id")).first()
    full_name = (person_data.get("full_name") or person_data.get("fullName") or "").strip()
    if not full_name:
        return None
    existing = Person.objects.filter(full_name__iexact=full_name).first()
    if existing:
        return existing
    return Person.objects.create(
        full_name=full_name,
        photo=person_data.get("photo"),
        photo_url=person_data.get("photo_url") or person_data.get("photoUrl"),
        bio=person_data.get("bio"),
        date_of_birth=parse_date(person_data.get("date_of_birth") or person_data.get("dateOfBirth")),
        nationality=person_data.get("nationality"),
        instagram=person_data.get("instagram"),
        imdb=person_data.get("imdb"),
        facebook=person_data.get("facebook"),
    )


def _sync_movie_credits(movie: Movie, credits_payload: Optional[list[dict[str, Any]]]) -> None:
    """Synchronize movie credits with the provided payload."""
    if credits_payload is None:
        return
    existing = {credit.id: credit for credit in movie.credits.all()}
    seen_ids = set()
    for idx, item in enumerate(credits_payload):
        credit = _normalize_credit_item(item, default_role_type=item.get("role_type"))
        if not credit:
            continue
        person = _resolve_person_from_credit(credit)
        if not person:
            continue
        position = credit.get("position")
        if position is None:
            position = idx + 1
        credit_id = credit.get("id")
        if credit_id and credit_id in existing:
            instance = existing[credit_id]
            instance.role_type = credit.get("role_type")
            instance.character_name = credit.get("character_name")
            instance.job_title = credit.get("job_title")
            instance.position = position
            instance.person = person
            instance.save()
            seen_ids.add(instance.id)
        else:
            instance = MovieCredit.objects.create(
                movie=movie,
                person=person,
                role_type=credit.get("role_type"),
                character_name=credit.get("character_name"),
                job_title=credit.get("job_title"),
                position=position,
            )
            seen_ids.add(instance.id)
    for credit_id, instance in existing.items():
        if credit_id not in seen_ids:
            instance.delete()


def create_movie(request: Any) -> tuple[dict[str, Any], int]:
    """Create a movie (admin only)."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    title = str(coalesce(payload, "title", "name", default="") or "").strip()
    if not title:
        return {"message": "Title is required"}, status.HTTP_400_BAD_REQUEST

    duration_minutes_value = coalesce(payload, "durationMinutes", "duration_minutes")
    try:
        duration_minutes_value = (
            int(duration_minutes_value) if duration_minutes_value is not None else None
        )
    except (TypeError, ValueError):
        duration_minutes_value = None

    movie = Movie(
        title=title,
        short_description=coalesce(payload, "shortDescription", "short_description"),
        description=coalesce(payload, "description", "synopsis"),
        long_description=coalesce(payload, "longDescription", "long_description"),
        language=coalesce(payload, "language", "lang"),
        genre=coalesce(payload, "genre", "category"),
        duration=coalesce(payload, "duration", "runtime"),
        duration_minutes=duration_minutes_value,
        rating=coalesce(payload, "rating", "censor"),
        release_date=parse_date(coalesce(payload, "releaseDate", "release_date")),
        poster_url=coalesce(payload, "posterUrl", "poster_url", "poster"),
        trailer_url=coalesce(payload, "trailerUrl", "trailer_url", "trailer"),
        status=coalesce(payload, "status", default=Movie.STATUS_COMING_SOON),
        is_active=coalesce(payload, "isActive", "is_active", default=True),
    )
    movie.save()
    genre_ids = coalesce(payload, "genreIds", "genres")
    if genre_ids:
        try:
            movie.genres.set(genre_ids)
        except Exception:
            pass
    _sync_movie_credits(movie, _extract_credits_payload(payload))
    return {"movie": build_movie_payload(movie, request=request)}, status.HTTP_201_CREATED


def update_movie(request: Any, movie: Movie) -> tuple[dict[str, Any], int]:
    """Update a movie (admin only)."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    for field, keys in {
        "title": ("title", "name"),
        "short_description": ("shortDescription", "short_description"),
        "description": ("description", "synopsis"),
        "long_description": ("longDescription", "long_description"),
        "language": ("language", "lang"),
        "genre": ("genre", "category"),
        "duration": ("duration", "runtime"),
        "rating": ("rating", "censor"),
        "poster_url": ("posterUrl", "poster_url", "poster"),
        "trailer_url": ("trailerUrl", "trailer_url", "trailer"),
        "status": ("status",),
        "is_active": ("isActive", "is_active"),
    }.items():
        value = coalesce(payload, *keys)
        if value is not None:
            setattr(movie, field, value)

    duration_minutes_value = coalesce(payload, "durationMinutes", "duration_minutes")
    if duration_minutes_value is not None:
        try:
            movie.duration_minutes = int(duration_minutes_value)
        except (TypeError, ValueError):
            movie.duration_minutes = None

    release_value = coalesce(payload, "releaseDate", "release_date")
    if release_value is not None:
        movie.release_date = parse_date(release_value)

    movie.save()
    genre_ids = coalesce(payload, "genreIds", "genres")
    if genre_ids is not None:
        try:
            movie.genres.set(genre_ids)
        except Exception:
            pass
    _sync_movie_credits(movie, _extract_credits_payload(payload))
    return {"movie": build_movie_payload(movie, request=request)}, status.HTTP_200_OK


def delete_movie(request: Any, movie: Movie) -> tuple[dict[str, Any], int]:
    """Delete a movie (admin only)."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    movie.delete()
    return {"message": "Movie deleted"}, status.HTTP_200_OK


def create_show(request: Any) -> tuple[dict[str, Any], int]:
    """Create a show entry (admin/vendor only)."""
    if not is_authenticated(request):
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    vendor_id = coalesce(payload, "vendorId", "vendor_id")
    movie_id = coalesce(payload, "movieId", "movie_id")

    if not vendor_id or not movie_id:
        return {
            "message": "vendorId and movieId are required"
        }, status.HTTP_400_BAD_REQUEST

    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    if vendor_actor and str(vendor_id) != str(vendor_actor.id):
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN
    if not vendor_actor and not admin_actor:
        return {"message": "Vendor access required"}, status.HTTP_403_FORBIDDEN

    if vendor_actor:
        vendor_id = vendor_actor.id

    try:
        vendor = Vendor.objects.get(pk=vendor_id)
    except Vendor.DoesNotExist:
        return {"message": "Vendor not found"}, status.HTTP_404_NOT_FOUND

    try:
        movie = Movie.objects.get(pk=movie_id)
    except Movie.DoesNotExist:
        return {"message": "Movie not found"}, status.HTTP_404_NOT_FOUND

    show_date = parse_date(coalesce(payload, "date", "show_date", "showDate"))
    start_time = parse_time(coalesce(payload, "start", "start_time", "startTime"))
    end_time = parse_time(coalesce(payload, "end", "end_time", "endTime"))

    if not show_date or not start_time:
        return {
            "message": "show date and start time are required"
        }, status.HTTP_400_BAD_REQUEST

    show = Show(
        vendor=vendor,
        movie=movie,
        hall=coalesce(payload, "hall"),
        slot=coalesce(payload, "slot"),
        screen_type=coalesce(payload, "screenType", "screen_type"),
        price=coalesce(payload, "price"),
        status=coalesce(payload, "status", default="Open"),
        listing_status=coalesce(
            payload, "listingStatus", "listing_status", default="Now Showing"
        ),
        show_date=show_date,
        start_time=start_time,
        end_time=end_time,
    )
    show.save()
    return {"show": build_show_payload(show)}, status.HTTP_201_CREATED


def delete_show(request: Any, show: Show) -> tuple[dict[str, Any], int]:
    """Delete a show entry (admin/vendor only)."""
    if not is_authenticated(request):
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    if vendor_actor and show.vendor_id != vendor_actor.id:
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN
    if not vendor_actor and not admin_actor:
        return {"message": "Vendor access required"}, status.HTTP_403_FORBIDDEN

    show.delete()
    return {"message": "Show deleted"}, status.HTTP_200_OK


def request_password_otp(email: Optional[str]) -> tuple[dict[str, Any], int]:
    """Create or refresh an OTP for password reset."""
    email = str(email or "").strip()
    if not email:
        return {"message": "Email is required"}, status.HTTP_400_BAD_REQUEST

    try:
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        otp = f"{random.randint(100000, 999999)}"
        OTPVerification.objects.create(email=email, otp=otp)

        logger.info("Generated OTP for %s: %s", email, otp)
        if getattr(settings, "DEBUG", False):
            print(f"DEBUG OTP for {email}: {otp}")

        return {"message": "OTP sent to your email"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("forgot_password error")
        return {
            "message": "Failed to send OTP",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def verify_password_otp(email: Optional[str], otp: Optional[str]) -> tuple[dict[str, Any], int]:
    """Verify a password reset OTP."""
    email = str(email or "").strip()
    otp = str(otp or "").strip()
    if not email or not otp:
        return {
            "message": "Email and OTP are required"
        }, status.HTTP_400_BAD_REQUEST

    try:
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(
                email__iexact=email, otp=otp, created_at__gte=cutoff
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return {
                "message": "Invalid or expired OTP"
            }, status.HTTP_400_BAD_REQUEST

        record.is_verified = True
        record.save()
        return {"message": "OTP verified"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("verify_otp error")
        return {
            "message": "Failed to verify OTP",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def reset_password_with_otp(
    email: Optional[str], otp: Optional[str], new_password: Optional[str]
) -> tuple[dict[str, Any], int]:
    """Reset a user's password using a verified OTP."""
    email = str(email or "").strip()
    otp = str(otp or "").strip()
    if not email or not otp or not new_password:
        return {
            "message": "Email, OTP and new_password are required"
        }, status.HTTP_400_BAD_REQUEST

    try:
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(
                email__iexact=email,
                otp=otp,
                created_at__gte=cutoff,
                is_verified=True,
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return {
                "message": "Invalid or unverified OTP"
            }, status.HTTP_400_BAD_REQUEST

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        user.set_password(new_password)
        user.save()

        record.is_verified = False
        record.save()

        return {"message": "Password reset successful"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("reset_password error")
        return {
            "message": "Failed to reset password",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def update_user_profile(request: Any, user: User) -> tuple[dict[str, Any], int]:
    """Update a user's profile information."""
    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("profile_image", None)

    for key in ("first_name", "middle_name", "last_name"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()
            if key == "middle_name" and data[key] == "":
                data[key] = None

    if "dob" in data and not str(data["dob"]).strip():
        data.pop("dob")

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = UserProfileUpdateSerializer(user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_user = serializer.save()

    _update_profile_image(updated_user, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "user": build_user_payload(updated_user, request),
    }, status.HTTP_200_OK


def update_admin_profile(request: Any, admin_user: Admin) -> tuple[dict[str, Any], int]:
    """Update an admin's profile information."""
    actor_admin = resolve_admin(request)
    actor_id = getattr(actor_admin, "id", None)
    if actor_admin and actor_id and int(actor_id) != int(admin_user.id):
        if not getattr(actor_admin, "is_superuser", False):
            return {"message": "Admin access denied"}, status.HTTP_403_FORBIDDEN

    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("email", None)
    data.pop("profile_image", None)

    if "full_name" in data and isinstance(data["full_name"], str):
        data["full_name"] = data["full_name"].strip()
        if data["full_name"] == "":
            data["full_name"] = None

    if "phone_number" in data:
        raw_phone = str(data["phone_number"]).strip()
        phone = normalize_phone_number(raw_phone)
        data["phone_number"] = phone or None
        if raw_phone and not phone:
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and not PHONE_REGEX.match(phone):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and Admin.objects.filter(phone_number=phone).exclude(pk=admin_user.id).exists():
            return {
                "message": "Phone number already exists"
            }, status.HTTP_400_BAD_REQUEST

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = AdminProfileUpdateSerializer(admin_user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_admin = serializer.save()

    _update_profile_image(updated_admin, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "admin": build_admin_payload(updated_admin, request),
    }, status.HTTP_200_OK


def update_vendor_profile(request: Any, vendor_user: Vendor) -> tuple[dict[str, Any], int]:
    """Update a vendor's profile information."""
    actor_vendor = resolve_vendor(request)
    if actor_vendor and actor_vendor.id != vendor_user.id:
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN

    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("email", None)
    data.pop("status", None)
    data.pop("is_active", None)
    data.pop("created_at", None)
    data.pop("profile_image", None)

    if "name" in data and isinstance(data["name"], str):
        data["name"] = data["name"].strip()
        if data["name"] == "":
            return {"message": "Vendor name is required"}, status.HTTP_400_BAD_REQUEST

    if "phone_number" in data:
        raw_phone = str(data["phone_number"]).strip()
        phone = normalize_phone_number(raw_phone)
        data["phone_number"] = phone or None
        if raw_phone and not phone:
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and not PHONE_REGEX.match(phone):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and Vendor.objects.filter(phone_number=phone).exclude(pk=vendor_user.id).exists():
            return {
                "message": "Phone number already exists"
            }, status.HTTP_400_BAD_REQUEST

    for key in ("theatre", "city"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip() or None

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = VendorProfileUpdateSerializer(vendor_user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_vendor = serializer.save()

    _update_profile_image(updated_vendor, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "vendor": build_vendor_payload(updated_vendor, request),
    }, status.HTTP_200_OK


def _safe_number(value: Any) -> float:
    """Coerce a value to a float, returning 0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_int(value: Any) -> Optional[int]:
    """Coerce a value to int if possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_flexible_time(value: Any) -> Optional[time_cls]:
    """Parse a time value from common 24h and 12h formats."""
    if not value:
        return None
    if isinstance(value, time_cls):
        return value

    parsed = parse_time(value)
    if parsed:
        return parsed

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%I:%M %p", "%I %p", "%H:%M:%S"):
        try:
            return datetime.strptime(text.upper(), fmt).time()
        except ValueError:
            continue
    return None


def _normalize_seat_labels(value: Any) -> list[str]:
    """Normalize seat labels into uppercase tokens like A10."""
    raw_labels: list[str] = []
    if isinstance(value, str):
        matches = re.findall(r"[A-Za-z]+\s*\d+[A-Za-z]?", value)
        if matches:
            raw_labels.extend(matches)
        elif value.strip():
            raw_labels.append(value.strip())
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            raw_labels.extend(_normalize_seat_labels(item))

    labels: list[str] = []
    seen = set()
    for label in raw_labels:
        normalized = re.sub(r"\s+", "", str(label)).upper()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        labels.append(normalized)
    return labels


def _split_seat_label(value: str) -> tuple[str, str]:
    """Split a seat label into row and seat number parts."""
    label = re.sub(r"\s+", "", str(value or "")).upper()
    if not label:
        return "", ""

    match = re.match(r"^([A-Z]+)(\d+[A-Z]?)$", label)
    if match:
        return match.group(1), match.group(2)

    match = re.match(r"^(\d+[A-Z]?)$", label)
    if match:
        return "", match.group(1)

    row = label[:1] if label and label[0].isalpha() else ""
    seat_number = label[len(row):] if row else label
    return row, seat_number


def _join_seat_label(row_label: Any, seat_number: Any) -> str:
    """Build a canonical seat label from row and seat number."""
    row = str(row_label or "").strip().upper()
    number = str(seat_number or "").strip().upper()
    return f"{row}{number}".strip()


def _seat_sort_key(label: str) -> tuple[str, int, str]:
    """Sort seat labels by row then seat number."""
    cleaned = re.sub(r"\s+", "", str(label or "")).upper()
    match = re.match(r"^([A-Z]+)?(\d+)?([A-Z]*)$", cleaned)
    if not match:
        return cleaned, 0, ""
    row = match.group(1) or ""
    number = int(match.group(2) or 0)
    suffix = match.group(3) or ""
    return row, number, suffix


def _combine_show_datetime(show_date: date_cls, show_time: time_cls) -> datetime:
    """Combine date and time into a timezone-aware datetime when needed."""
    combined = datetime.combine(show_date, show_time)
    if getattr(settings, "USE_TZ", False) and timezone.is_naive(combined):
        return timezone.make_aware(combined, timezone.get_current_timezone())
    return combined


def _resolve_booking_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract booking context fields from request/order payloads."""
    booking_data = payload.get("booking") if isinstance(payload.get("booking"), dict) else {}
    movie_data = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}

    cinema_id = _coerce_int(
        coalesce(
            booking_data,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
            default=coalesce(
                payload,
                "cinema_id",
                "cinemaId",
                "vendor_id",
                "vendorId",
                default=coalesce(movie_data, "cinemaId", "vendorId"),
            ),
        )
    )
    movie_id = _coerce_int(
        coalesce(
            booking_data,
            "movie_id",
            "movieId",
            "movie",
            default=coalesce(
                payload,
                "movie_id",
                "movieId",
                "movie",
                default=coalesce(movie_data, "movieId", "movie_id", "id"),
            ),
        )
    )
    show_id = _coerce_int(
        coalesce(
            booking_data,
            "show_id",
            "showId",
            default=coalesce(payload, "show_id", "showId"),
        )
    )
    show_date = parse_date(
        coalesce(
            booking_data,
            "date",
            "show_date",
            "showDate",
            default=coalesce(payload, "date", "show_date", "showDate"),
        )
    )
    show_time = _parse_flexible_time(
        coalesce(
            booking_data,
            "time",
            "start",
            "start_time",
            "startTime",
            default=coalesce(payload, "time", "start", "start_time", "startTime"),
        )
    )
    hall = str(
        coalesce(
            booking_data,
            "hall",
            "cinema_hall",
            "cinemaHall",
            default=coalesce(payload, "hall", "cinema_hall", "cinemaHall"),
        )
        or ""
    ).strip()
    selected_seats = _normalize_seat_labels(
        coalesce(
            booking_data,
            "selected_seats",
            "selectedSeats",
            "seats",
            default=coalesce(payload, "selected_seats", "selectedSeats", "seats"),
        )
    )
    user_id = _coerce_int(
        coalesce(booking_data, "user_id", "userId", default=coalesce(payload, "user_id", "userId"))
    )

    return {
        "show_id": show_id,
        "movie_id": movie_id,
        "cinema_id": cinema_id,
        "show_date": show_date,
        "show_time": show_time,
        "hall": hall or None,
        "selected_seats": selected_seats,
        "user_id": user_id,
    }


def _resolve_show_for_context(context: dict[str, Any]) -> Optional[Show]:
    """Resolve a Show row from booking context fields."""
    show_id = context.get("show_id")
    if show_id:
        return Show.objects.filter(pk=show_id).first()

    cinema_id = context.get("cinema_id")
    movie_id = context.get("movie_id")
    show_date = context.get("show_date")
    show_time = context.get("show_time")
    if not cinema_id or not movie_id or not show_date or not show_time:
        return None

    queryset = Show.objects.filter(
        vendor_id=cinema_id,
        movie_id=movie_id,
        show_date=show_date,
        start_time=show_time,
    )
    hall = context.get("hall")
    if hall:
        queryset = queryset.filter(hall__iexact=hall)
    return queryset.order_by("id").first()


def _resolve_screen_number(show: Show, hall_override: Optional[str] = None) -> str:
    """Resolve the screen number identifier for a show."""
    hall = str(hall_override or show.hall or "").strip()
    if hall:
        return hall
    return f"Hall-{show.id}"


def _find_showtime_for_context(show: Show, hall_override: Optional[str] = None) -> Optional[Showtime]:
    """Find an existing showtime row that maps to the selected show context."""
    screen_number = _resolve_screen_number(show, hall_override)
    screen = Screen.objects.filter(
        vendor_id=show.vendor_id, screen_number=screen_number
    ).first()
    if not screen:
        return None
    start_at = _combine_show_datetime(show.show_date, show.start_time)
    return Showtime.objects.filter(
        movie_id=show.movie_id,
        screen_id=screen.id,
        start_time=start_at,
    ).first()


def _get_or_create_showtime_for_context(
    show: Show, hall_override: Optional[str] = None
) -> tuple[Screen, Showtime]:
    """Get or create the Screen/Showtime records for a selected show."""
    screen_number = _resolve_screen_number(show, hall_override)
    screen, _ = Screen.objects.get_or_create(
        vendor_id=show.vendor_id,
        screen_number=screen_number,
        defaults={
            "screen_type": show.screen_type,
            "status": "Active",
        },
    )
    if show.screen_type and not screen.screen_type:
        screen.screen_type = show.screen_type
        screen.save(update_fields=["screen_type"])

    start_at = _combine_show_datetime(show.show_date, show.start_time)
    end_at = (
        _combine_show_datetime(show.show_date, show.end_time)
        if show.end_time
        else None
    )
    showtime, created = Showtime.objects.get_or_create(
        movie_id=show.movie_id,
        screen=screen,
        start_time=start_at,
        defaults={
            "end_time": end_at,
            "price": show.price,
        },
    )
    if not created:
        updated_fields: list[str] = []
        if end_at and not showtime.end_time:
            showtime.end_time = end_at
            updated_fields.append("end_time")
        if show.price is not None and showtime.price is None:
            showtime.price = show.price
            updated_fields.append("price")
        if updated_fields:
            showtime.save(update_fields=updated_fields)

    return screen, showtime


def _collect_sold_labels_for_showtime(showtime: Showtime, lock: bool = False) -> list[str]:
    """Collect sold seat labels from availability + confirmed bookings."""
    sold_labels = set()

    availability_qs = SeatAvailability.objects.filter(showtime=showtime).select_related(
        "seat"
    )
    if lock:
        availability_qs = availability_qs.select_for_update()
    for availability in availability_qs:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value not in BOOKED_STATUSES:
            continue
        sold_labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )

    booking_seat_qs = BookingSeat.objects.filter(
        booking__showtime=showtime,
    ).exclude(
        booking__booking_status__iexact="Cancelled"
    ).select_related("seat")
    if lock:
        booking_seat_qs = booking_seat_qs.select_for_update()
    for booking_seat in booking_seat_qs:
        sold_labels.add(
            _join_seat_label(booking_seat.seat.row_label, booking_seat.seat.seat_number)
        )

    return sorted(sold_labels, key=_seat_sort_key)


def _collect_unavailable_labels_for_showtime(
    showtime: Showtime, lock: bool = False
) -> list[str]:
    """Collect unavailable seat labels for a showtime."""
    labels = set()
    queryset = SeatAvailability.objects.filter(showtime=showtime).select_related("seat")
    if lock:
        queryset = queryset.select_for_update()
    for availability in queryset:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value != SEAT_STATUS_UNAVAILABLE.lower():
            continue
        labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )
    return sorted(labels, key=_seat_sort_key)


def _next_guest_phone_number() -> str:
    """Generate a unique phone number for fallback guest users."""
    for suffix in range(1000):
        candidate = str(9800000000 + suffix)
        if not User.objects.filter(phone_number=candidate).exists():
            return candidate
    while True:
        candidate = str(random.randint(9000000000, 9999999999))
        if not User.objects.filter(phone_number=candidate).exists():
            return candidate


def _resolve_booking_user(context: dict[str, Any]) -> User:
    """Resolve booking user from payload or fallback guest account."""
    user_id = context.get("user_id")
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            return user

    guest = User.objects.filter(email__iexact=DEFAULT_GUEST_EMAIL).first()
    if guest:
        return guest

    guest_user = User(
        email=DEFAULT_GUEST_EMAIL,
        phone_number=_next_guest_phone_number(),
        dob=date_cls(2000, 1, 1),
        first_name=DEFAULT_GUEST_NAME,
        last_name="User",
        username=f"guest-{uuid.uuid4().hex[:8]}",
    )
    guest_user.set_password(uuid.uuid4().hex)
    guest_user.save()
    return guest_user


def _create_booking_from_order(order: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    """Create booking + sold seat records from order context."""
    context = _resolve_booking_context(order)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return None, None, status.HTTP_200_OK

    if not context.get("movie_id") or not context.get("cinema_id") or not context.get("show_date") or not context.get("show_time"):
        return (
            None,
            {
                "message": "Booking context is incomplete. Provide cinema, movie, date, time, and selected seats.",
            },
            status.HTTP_400_BAD_REQUEST,
        )

    show = _resolve_show_for_context(context)
    if not show:
        return (
            None,
            {"message": "Selected show was not found."},
            status.HTTP_404_NOT_FOUND,
        )

    normalized_labels = _normalize_seat_labels(selected_seats)
    parsed_labels: list[tuple[str, str, str]] = []
    invalid_labels: list[str] = []
    for label in normalized_labels:
        row_label, seat_number = _split_seat_label(label)
        if not seat_number:
            invalid_labels.append(label)
            continue
        parsed_labels.append((label, row_label, seat_number))

    if invalid_labels:
        return (
            None,
            {"message": "Invalid seat labels in request.", "invalid_seats": invalid_labels},
            status.HTTP_400_BAD_REQUEST,
        )

    user = _resolve_booking_user(context)
    ticket_total = _safe_number(order.get("ticketTotal"))
    total_amount = _safe_number(order.get("total"))
    seat_price = (ticket_total / len(parsed_labels)) if parsed_labels and ticket_total else None

    with transaction.atomic():
        screen, showtime = _get_or_create_showtime_for_context(show, context.get("hall"))
        existing_sold = set(_collect_sold_labels_for_showtime(showtime, lock=True))
        conflicts = [label for label, _, _ in parsed_labels if label in existing_sold]
        if conflicts:
            return (
                None,
                {
                    "message": "Some selected seats are already sold.",
                    "sold_seats": sorted(conflicts, key=_seat_sort_key),
                },
                status.HTTP_409_CONFLICT,
            )

        seat_records: list[tuple[str, str, str, Seat, SeatAvailability]] = []
        persisted_seats: list[str] = []
        for label, row_label, seat_number in parsed_labels:
            seat, _ = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            )
            availability, created = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if not created and current_status in BOOKED_STATUSES:
                return (
                    None,
                    {
                        "message": "Some selected seats are already sold.",
                        "sold_seats": [label],
                    },
                    status.HTTP_409_CONFLICT,
                )
            if not created and current_status == SEAT_STATUS_UNAVAILABLE.lower():
                return (
                    None,
                    {
                        "message": "Some selected seats are unavailable.",
                        "unavailable_seats": [label],
                    },
                    status.HTTP_409_CONFLICT,
                )
            seat_records.append((label, row_label, seat_number, seat, availability))

        booking = Booking.objects.create(
            user=user,
            showtime=showtime,
            booking_status=BOOKING_STATUS_CONFIRMED,
            total_amount=total_amount if total_amount else None,
        )

        for _, row_label, seat_number, seat, availability in seat_records:
            availability.seat_status = SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

            BookingSeat.objects.create(
                booking=booking,
                seat=seat,
                seat_price=seat_price if seat_price is not None else None,
            )
            persisted_seats.append(_join_seat_label(row_label, seat_number))

    return (
        {
            "booking_id": booking.id,
            "show_id": show.id,
            "showtime_id": showtime.id,
            "screen": screen.screen_number,
            "sold_seats": sorted(persisted_seats, key=_seat_sort_key),
        },
        None,
        status.HTTP_201_CREATED,
    )


def list_sold_seats_for_context(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return sold seat labels for a selected movie/cinema/date/time context."""
    layout_payload, status_code = list_booking_seat_layout(payload)
    sold_labels = list(layout_payload.get("sold_seats") or [])
    unavailable_labels = list(layout_payload.get("unavailable_seats") or [])
    return {
        "sold_seats": sold_labels,
        "soldSeats": sold_labels,
        "unavailable_seats": unavailable_labels,
        "unavailableSeats": unavailable_labels,
        "show_id": layout_payload.get("show_id"),
        "showtime_id": layout_payload.get("showtime_id"),
    }, status_code


def _row_label_from_index(index: int) -> str:
    """Convert a zero-based row index into a label (A..Z, AA..)."""
    label = ""
    current = int(index)
    while True:
        current, remainder = divmod(current, 26)
        label = chr(65 + remainder) + label
        if current == 0:
            break
        current -= 1
    return label


def _row_label_sort_key(value: Any) -> int:
    """Sort row labels lexicographically in base-26 order."""
    label = str(value or "").strip().upper()
    score = 0
    for char in label:
        if not ("A" <= char <= "Z"):
            continue
        score = (score * 26) + (ord(char) - 64)
    return score


def _parse_positive_int(
    value: Any, default: int, minimum: int = 1, maximum: int = 100
) -> int:
    """Parse an int with bounds and fallback."""
    parsed = _coerce_int(value)
    if parsed is None:
        return default
    return max(minimum, min(maximum, parsed))


def _normalize_seat_category(value: Any) -> str:
    """Normalize free-text seat category labels."""
    text = str(value or "").strip().lower()
    if text.startswith("vip"):
        return SEAT_CATEGORY_VIP
    if text.startswith("prem"):
        return SEAT_CATEGORY_PREMIUM
    if text.startswith("exec"):
        return SEAT_CATEGORY_EXECUTIVE
    return SEAT_CATEGORY_NORMAL


def _default_category_counts(total_rows: int) -> dict[str, int]:
    """Build default row distribution for seat categories."""
    rows = max(1, int(total_rows))
    normal = max(1, round(rows * 0.3))
    executive = max(1, round(rows * 0.3))
    premium = max(1, round(rows * 0.2))
    vip = max(1, rows - (normal + executive + premium))
    diff = rows - (normal + executive + premium + vip)
    normal += diff
    return {
        "normal": normal,
        "executive": executive,
        "premium": premium,
        "vip": vip,
    }


def _normalize_category_counts(total_rows: int, payload: dict[str, Any]) -> dict[str, int]:
    """Normalize category row counts from payload into a complete distribution."""
    category_rows = (
        payload.get("category_rows")
        if isinstance(payload.get("category_rows"), dict)
        else {}
    )
    counts = {
        "normal": _parse_positive_int(
            coalesce(
                category_rows,
                "normal",
                default=coalesce(payload, "normal_rows", "normalRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "executive": _parse_positive_int(
            coalesce(
                category_rows,
                "executive",
                default=coalesce(
                    payload, "executive_rows", "executiveRows", default=0
                ),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "premium": _parse_positive_int(
            coalesce(
                category_rows,
                "premium",
                default=coalesce(payload, "premium_rows", "premiumRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "vip": _parse_positive_int(
            coalesce(
                category_rows,
                "vip",
                default=coalesce(payload, "vip_rows", "vipRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
    }

    provided_total = sum(counts.values())
    if provided_total <= 0:
        return _default_category_counts(total_rows)

    if provided_total < total_rows:
        counts["normal"] += total_rows - provided_total
    elif provided_total > total_rows:
        overflow = provided_total - total_rows
        for key in ("vip", "premium", "executive", "normal"):
            if overflow <= 0:
                break
            reducible = min(counts[key], overflow)
            counts[key] -= reducible
            overflow -= reducible
        if overflow > 0:
            defaults = _default_category_counts(total_rows)
            return defaults
    return counts


def _build_row_category_map(
    row_labels: list[str], category_counts: dict[str, int]
) -> dict[str, str]:
    """Map each row label to its seat category in front-to-back order."""
    ordered_categories = [
        ("normal", SEAT_CATEGORY_NORMAL),
        ("executive", SEAT_CATEGORY_EXECUTIVE),
        ("premium", SEAT_CATEGORY_PREMIUM),
        ("vip", SEAT_CATEGORY_VIP),
    ]
    mapping: dict[str, str] = {}
    index = 0
    for key, label in ordered_categories:
        count = max(0, int(category_counts.get(key, 0)))
        for _ in range(count):
            if index >= len(row_labels):
                break
            mapping[row_labels[index]] = label
            index += 1
    while index < len(row_labels):
        mapping[row_labels[index]] = SEAT_CATEGORY_VIP
        index += 1
    return mapping


def _build_default_layout_payload() -> dict[str, Any]:
    """Return fallback seat layout payload compatible with existing frontend grid."""
    return {
        "seat_groups": [
            {"key": "normal", "label": SEAT_CATEGORY_NORMAL, "rows": ["A", "B", "C"]},
            {
                "key": "executive",
                "label": SEAT_CATEGORY_EXECUTIVE,
                "rows": ["D", "E", "F"],
            },
            {"key": "premium", "label": SEAT_CATEGORY_PREMIUM, "rows": ["G", "H"]},
            {"key": "vip", "label": SEAT_CATEGORY_VIP, "rows": ["I", "J"]},
        ],
        "seat_columns": list(range(1, 16)),
        "sold_seats": [],
        "unavailable_seats": [],
        "seats": [],
        "total_rows": 10,
        "total_columns": 15,
    }


def _resolve_vendor_for_payload(
    request: Any, payload: dict[str, Any]
) -> tuple[Optional[Vendor], Optional[dict[str, Any]], int]:
    """Resolve vendor identity from request or explicit payload values."""
    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    vendor_id = _coerce_int(
        coalesce(payload, "vendor_id", "vendorId", "cinema_id", "cinemaId")
    )

    if vendor_actor:
        if vendor_id and int(vendor_id) != int(vendor_actor.id):
            return None, {"message": "Vendor access denied."}, status.HTTP_403_FORBIDDEN
        return vendor_actor, None, status.HTTP_200_OK

    if admin_actor:
        if not vendor_id:
            return (
                None,
                {"message": "vendor_id is required for admin requests."},
                status.HTTP_400_BAD_REQUEST,
            )
        vendor = Vendor.objects.filter(pk=vendor_id).first()
        if not vendor:
            return None, {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
        return vendor, None, status.HTTP_200_OK

    if not vendor_id:
        return (
            None,
            {"message": "vendor_id is required."},
            status.HTTP_400_BAD_REQUEST,
        )

    vendor = Vendor.objects.filter(pk=vendor_id).first()
    if not vendor:
        return None, {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
    return vendor, None, status.HTTP_200_OK


def _resolve_show_for_vendor(vendor: Vendor, payload: dict[str, Any]) -> Optional[Show]:
    """Resolve a vendor-owned show from payload context."""
    show_id = _coerce_int(coalesce(payload, "show_id", "showId"))
    if show_id:
        return Show.objects.filter(pk=show_id, vendor_id=vendor.id).first()

    movie_id = _coerce_int(coalesce(payload, "movie_id", "movieId", "movie"))
    show_date = parse_date(coalesce(payload, "date", "show_date", "showDate"))
    show_time = _parse_flexible_time(
        coalesce(payload, "time", "start", "start_time", "startTime")
    )
    if not movie_id or not show_date or not show_time:
        return None

    queryset = Show.objects.filter(
        vendor_id=vendor.id,
        movie_id=movie_id,
        show_date=show_date,
        start_time=show_time,
    )
    hall = str(coalesce(payload, "hall", "cinema_hall", "cinemaHall") or "").strip()
    if hall:
        queryset = queryset.filter(hall__iexact=hall)
    return queryset.order_by("id").first()


def _build_screen_layout_payload(
    screen: Optional[Screen], showtime: Optional[Showtime] = None, show: Optional[Show] = None
) -> dict[str, Any]:
    """Build seat layout payload from screen seats and optional showtime statuses."""
    if not screen:
        return _build_default_layout_payload()

    seats = list(
        Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
    )
    if not seats:
        payload = _build_default_layout_payload()
        payload.update(
            {
                "screen_id": screen.id,
                "hall": screen.screen_number,
                "vendor_id": screen.vendor_id,
                "show_id": show.id if show else None,
                "showtime_id": showtime.id if showtime else None,
            }
        )
        return payload

    row_labels = sorted(
        {str(seat.row_label or "").strip().upper() for seat in seats if seat.row_label},
        key=_row_label_sort_key,
    )
    parsed_columns = []
    for seat in seats:
        number_text = str(seat.seat_number or "").strip()
        match = re.search(r"\d+", number_text)
        if not match:
            continue
        parsed_columns.append(int(match.group(0)))
    seat_columns = sorted(set(parsed_columns)) or list(range(1, 16))

    sold_labels = set(_collect_sold_labels_for_showtime(showtime, lock=False)) if showtime else set()
    unavailable_labels = (
        set(_collect_unavailable_labels_for_showtime(showtime, lock=False)) if showtime else set()
    )

    category_rows: dict[str, set[str]] = {
        category: set() for category in SEAT_CATEGORY_ORDER
    }
    seat_items = []
    for seat in seats:
        category_label = _normalize_seat_category(seat.seat_type)
        row_label = str(seat.row_label or "").strip().upper()
        seat_label = _join_seat_label(row_label, seat.seat_number)
        category_rows[category_label].add(row_label)

        seat_status = "available"
        if seat_label in sold_labels:
            seat_status = "booked"
        elif seat_label in unavailable_labels:
            seat_status = "unavailable"

        seat_items.append(
            {
                "id": seat.id,
                "row_label": row_label,
                "seat_number": str(seat.seat_number or ""),
                "label": seat_label,
                "seat_type": category_label,
                "status": seat_status,
            }
        )

    seat_groups = []
    for category_label in SEAT_CATEGORY_ORDER:
        rows = sorted(category_rows[category_label], key=_row_label_sort_key)
        seat_groups.append(
            {
                "key": SEAT_CATEGORY_KEYS[category_label],
                "label": category_label,
                "rows": rows,
            }
        )

    return {
        "screen_id": screen.id,
        "hall": screen.screen_number,
        "vendor_id": screen.vendor_id,
        "show_id": show.id if show else None,
        "showtime_id": showtime.id if showtime else None,
        "seat_groups": seat_groups,
        "seat_columns": seat_columns,
        "row_labels": row_labels,
        "seats": seat_items,
        "sold_seats": sorted(sold_labels, key=_seat_sort_key),
        "unavailable_seats": sorted(unavailable_labels, key=_seat_sort_key),
        "total_rows": len(row_labels),
        "total_columns": len(seat_columns),
        "total_seats": len(seat_items),
    }


def list_vendor_seat_layout(request: Any) -> tuple[dict[str, Any], int]:
    """Return vendor seat layout for hall/show management."""
    query_payload = {
        key: request.query_params.get(key) for key in request.query_params.keys()
    }
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, query_payload)
    if error_payload:
        return error_payload, status_code

    show = _resolve_show_for_vendor(vendor, query_payload)
    hall = str(
        coalesce(query_payload, "hall", "cinema_hall", "cinemaHall", default=show.hall if show else "")
        or ""
    ).strip()

    screen = None
    if hall:
        screen = Screen.objects.filter(vendor_id=vendor.id, screen_number=hall).first()
    if not screen:
        screen = Screen.objects.filter(vendor_id=vendor.id).order_by("id").first()

    showtime = None
    if show:
        showtime = _find_showtime_for_context(show, hall or None)

    payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "hall": hall or payload.get("hall"),
        }
    )
    return payload, status.HTTP_200_OK


def create_or_update_vendor_seat_layout(request: Any) -> tuple[dict[str, Any], int]:
    """Create or update seat layout rows/columns/categories for a vendor hall."""
    payload = get_payload(request)
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, payload)
    if error_payload:
        return error_payload, status_code

    hall = str(coalesce(payload, "hall", "cinema_hall", "cinemaHall") or "").strip()
    if not hall:
        return {"message": "hall is required."}, status.HTTP_400_BAD_REQUEST

    total_rows = _parse_positive_int(
        coalesce(payload, "rows", "row_count", "rowCount"), default=10, minimum=1, maximum=52
    )
    total_columns = _parse_positive_int(
        coalesce(payload, "columns", "cols", "column_count", "columnCount"),
        default=15,
        minimum=1,
        maximum=40,
    )
    category_counts = _normalize_category_counts(total_rows, payload)

    screen, _ = Screen.objects.get_or_create(
        vendor_id=vendor.id,
        screen_number=hall,
        defaults={
            "screen_type": coalesce(payload, "screen_type", "screenType"),
            "status": "Active",
        },
    )
    screen.capacity = total_rows * total_columns
    provided_screen_type = coalesce(payload, "screen_type", "screenType")
    if provided_screen_type:
        screen.screen_type = provided_screen_type
    screen.status = "Active"
    screen.save(update_fields=["capacity", "screen_type", "status"])

    row_labels = [_row_label_from_index(index) for index in range(total_rows)]
    row_category_map = _build_row_category_map(row_labels, category_counts)

    desired_pairs = set()
    for row_label in row_labels:
        seat_category = row_category_map.get(row_label, SEAT_CATEGORY_NORMAL)
        for col in range(1, total_columns + 1):
            seat_number = str(col)
            desired_pairs.add((row_label, seat_number))
            seat, created = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label,
                seat_number=seat_number,
                defaults={"seat_type": seat_category},
            )
            if not created and _normalize_seat_category(seat.seat_type) != seat_category:
                seat.seat_type = seat_category
                seat.save(update_fields=["seat_type"])

    existing_seats = Seat.objects.filter(screen=screen)
    for seat in existing_seats:
        pair = (str(seat.row_label or "").upper(), str(seat.seat_number or ""))
        if pair in desired_pairs:
            continue
        if seat.booking_seats.exists() or seat.availabilities.exists():
            continue
        seat.delete()

    show = _resolve_show_for_vendor(vendor, payload)
    showtime = _find_showtime_for_context(show, hall) if show else None
    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "category_rows": category_counts,
            "message": "Seat layout saved.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def update_vendor_seat_status(request: Any) -> tuple[dict[str, Any], int]:
    """Update per-show seat status for vendor seats."""
    payload = get_payload(request)
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, payload)
    if error_payload:
        return error_payload, status_code

    show = _resolve_show_for_vendor(vendor, payload)
    if not show:
        return {"message": "show_id or valid show context is required."}, status.HTTP_400_BAD_REQUEST

    target_status = str(coalesce(payload, "status", "seat_status") or "").strip().lower()
    if target_status not in (
        SEAT_STATUS_AVAILABLE.lower(),
        SEAT_STATUS_UNAVAILABLE.lower(),
    ):
        return {"message": "status must be Available or Unavailable."}, status.HTTP_400_BAD_REQUEST

    status_label = (
        SEAT_STATUS_UNAVAILABLE
        if target_status == SEAT_STATUS_UNAVAILABLE.lower()
        else SEAT_STATUS_AVAILABLE
    )
    seat_labels = _normalize_seat_labels(
        coalesce(payload, "seat_labels", "seatLabels", "selected_seats", "selectedSeats", "seats")
    )
    if not seat_labels:
        return {"message": "seat_labels are required."}, status.HTTP_400_BAD_REQUEST

    hall = str(
        coalesce(payload, "hall", "cinema_hall", "cinemaHall", default=show.hall) or ""
    ).strip()
    screen, showtime = _get_or_create_showtime_for_context(show, hall or None)

    conflicts = {"booked": [], "invalid": []}
    updated = []
    with transaction.atomic():
        for label in seat_labels:
            row_label, seat_number = _split_seat_label(label)
            if not seat_number:
                conflicts["invalid"].append(label)
                continue

            seat, _ = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
                defaults={"seat_type": SEAT_CATEGORY_NORMAL},
            )
            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                conflicts["booked"].append(label)
                continue

            availability.seat_status = status_label
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])
            updated.append(label)

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "updated_seats": sorted(updated, key=_seat_sort_key),
            "conflicts": {
                "booked": sorted(conflicts["booked"], key=_seat_sort_key),
                "invalid": sorted(conflicts["invalid"], key=_seat_sort_key),
            },
            "message": "Seat status updated.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def list_booking_seat_layout(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return booking seat layout with category rows and seat statuses."""
    context = _resolve_booking_context(payload)
    show = _resolve_show_for_context(context)
    if not show:
        fallback = _build_default_layout_payload()
        fallback.update({"show_id": None, "showtime_id": None})
        return fallback, status.HTTP_200_OK

    hall = str(context.get("hall") or show.hall or "").strip()
    screen = None
    if hall:
        screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number=hall).first()
    if not screen:
        screen = Screen.objects.filter(vendor_id=show.vendor_id).order_by("id").first()

    showtime = _find_showtime_for_context(show, hall or None)
    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "show_id": show.id,
            "hall": hall or layout_payload.get("hall"),
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "date": show.show_date.isoformat() if show.show_date else None,
            "time": show.start_time.strftime("%H:%M") if show.start_time else None,
        }
    )
    return layout_payload, status.HTTP_200_OK


def _clamp_text(value: Any, limit: int = 44) -> str:
    """Clamp text to a fixed character limit."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _load_font(size: int, bold: bool = False) -> Any:
    """Load the configured font or fall back to a default."""
    candidates = []
    if bold:
        candidates = [
            "arialbd.ttf",
            "Arial Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "arial.ttf",
            "Arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "DejaVuSans.ttf",
        ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    """Normalize ticket line items from incoming payloads."""
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        qty = int(item.get("qty") or 0)
        price = _safe_number(item.get("price"))
        normalized.append({"name": name, "qty": qty, "price": price})
    return normalized


def _build_ticket_payload(order: dict[str, Any], reference: str, request: Any) -> dict[str, Any]:
    """Build the ticket payload that is persisted in the database."""
    if not isinstance(order, dict):
        order = {}
    movie = order.get("movie") if isinstance(order.get("movie"), dict) else {}
    booking_context = _resolve_booking_context(order)
    selected_seats = booking_context.get("selected_seats") or []

    venue_raw = movie.get("venue") or ""
    venue_parts = [part.strip() for part in str(venue_raw).split(",") if part.strip()]
    venue_name = venue_parts[0] if venue_parts else str(venue_raw)
    venue_location = str(movie.get("cinemaLocation") or movie.get("location") or "").strip()
    explicit_cinema_name = str(movie.get("cinemaName") or "").strip()
    if explicit_cinema_name:
        venue_name = explicit_cinema_name
    show_date = venue_parts[1] if len(venue_parts) > 1 else ""
    show_time = venue_parts[2] if len(venue_parts) > 2 else ""
    if movie.get("showDate"):
        show_date = str(movie.get("showDate"))
    if movie.get("showTime"):
        show_time = str(movie.get("showTime"))
    if booking_context.get("show_date"):
        show_date = booking_context["show_date"].isoformat()
    if booking_context.get("show_time"):
        show_time = booking_context["show_time"].strftime("%I:%M %p")

    seat_label = str(movie.get("seat") or "").strip()
    if selected_seats:
        seat_label = f"Seat No: {', '.join(selected_seats)}"

    theater = (
        booking_context.get("hall")
        or movie.get("theater")
        or movie.get("screen")
        or movie.get("hall")
    )
    if not theater:
        match = re.search(r"\b(\d{1,2})\b", venue_name)
        theater = match.group(1).zfill(2) if match else "03"

    ticket_total = _safe_number(order.get("ticketTotal"))
    food_total = _safe_number(order.get("foodTotal"))
    total = _safe_number(order.get("total") or (ticket_total + food_total))
    payload = {
        "reference": reference,
        "movie": {
            "title": str(movie.get("title") or ""),
            "seat": seat_label,
            "venue": str(venue_raw),
            "venue_name": str(venue_name),
            "venue_location": venue_location,
            "show_date": str(show_date),
            "show_time": str(show_time),
            "theater": str(theater),
            "language": str(movie.get("language") or ""),
            "runtime": str(movie.get("runtime") or ""),
            "movie_id": booking_context.get("movie_id"),
            "cinema_id": booking_context.get("cinema_id"),
            "show_id": booking_context.get("show_id"),
        },
        "selected_seats": selected_seats,
        "ticket_total": ticket_total,
        "food_total": food_total,
        "total": total,
        "items": _normalize_items(order.get("items")),
        "created_at": timezone.now().isoformat(),
    }
    payload["details_url"] = request.build_absolute_uri(
        f"/api/ticket/{reference}/details/"
    )
    return payload


def _build_qr_image(data: str) -> Optional[Any]:
    """Build a QR image from the supplied data."""
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _image_to_data_url(image: Any) -> str:
    """Convert a PIL image into a data URL string."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _text_size(draw: Any, text: str, font: Any) -> tuple[int, int]:
    """Return text dimensions for the given font."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _draw_perforations(
    draw: Any, rect: tuple[int, int, int, int], bg_color: str, radius: int = 7, step: int = 22
) -> None:
    """Draw perforation holes around a rectangle."""
    left, top, right, bottom = rect
    for x in range(left + radius, right - radius + 1, step):
        draw.ellipse(
            (x - radius, top - radius, x + radius, top + radius), fill=bg_color
        )
        draw.ellipse(
            (x - radius, bottom - radius, x + radius, bottom + radius), fill=bg_color
        )
    for y in range(top + radius, bottom - radius + 1, step):
        draw.ellipse(
            (left - radius, y - radius, left + radius, y + radius), fill=bg_color
        )
        draw.ellipse(
            (right - radius, y - radius, right + radius, y + radius), fill=bg_color
        )


def _draw_barcode(
    draw: Any, box: tuple[int, int, int, int], seed_value: str, color: str = "#1f2933"
) -> None:
    """Draw a fake barcode pattern for styling."""
    rng = random.Random(seed_value)
    x0, y0, x1, y1 = box
    x = x0
    while x < x1:
        bar_width = rng.choice([1, 1, 2, 2, 3])
        gap = rng.choice([1, 1, 2])
        bar_end = min(x + bar_width, x1)
        draw.rectangle((x, y0, bar_end, y1), fill=color)
        x = bar_end + gap


def _render_ticket_image(payload: dict[str, Any], qr_image: Any) -> Any:
    """Render a ticket image for download and QR display."""
    width, height = 1100, 380
    bg_color = "#3f3f44"
    paper_color = "#ffffff"
    border_color = "#d7d7d7"
    text_color = "#1f2937"
    muted_color = "#6b7280"
    accent_color = "#e11d48"

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    margin = 24
    ticket_rect = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(
        ticket_rect, radius=18, fill=paper_color, outline=border_color, width=2
    )
    _draw_perforations(draw, ticket_rect, bg_color, radius=8, step=24)

    ticket_width = ticket_rect[2] - ticket_rect[0]
    separator_x = ticket_rect[0] + int(ticket_width * 0.7)
    dash_y = ticket_rect[1] + 18
    while dash_y < ticket_rect[3] - 18:
        draw.line(
            (separator_x, dash_y, separator_x, dash_y + 10),
            fill=border_color,
            width=2,
        )
        dash_y += 18

    brand_font = _load_font(22, bold=True)
    title_font = _load_font(30, bold=True)
    label_font = _load_font(12, bold=True)
    value_font = _load_font(16, bold=False)
    small_font = _load_font(13, bold=False)

    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    title = str(movie.get("title") or "")
    venue_name = str(movie.get("venue_name") or movie.get("venue") or "")
    seat_raw = str(movie.get("seat") or "")
    seat_value = re.sub(r"(?i)seat\s*no\s*[:#-]?", "", seat_raw).strip() or "-"
    theater = str(movie.get("theater") or "03")
    show_date = str(movie.get("show_date") or "")
    show_time = str(movie.get("show_time") or "")
    reference = str(payload.get("reference") or "")
    ticket_total = payload.get("ticket_total")
    if ticket_total is None:
        ticket_total = payload.get("total")
    food_total = payload.get("food_total")
    total_value = payload.get("total")
    ticket_value = int(_safe_number(ticket_total))
    food_value = int(_safe_number(food_total))
    total_value = int(_safe_number(total_value))

    left_barcode_box = (
        ticket_rect[0] + 12,
        ticket_rect[1] + 18,
        ticket_rect[0] + 48,
        ticket_rect[3] - 18,
    )
    _draw_barcode(draw, left_barcode_box, reference + "left", color=text_color)

    left_x = left_barcode_box[2] + 18
    left_y = ticket_rect[1] + 18

    brand_text = "MERO TICKET"
    brand_w, brand_h = _text_size(draw, brand_text, brand_font)
    brand_rect = (left_x, left_y, left_x + brand_w + 18, left_y + brand_h + 10)
    draw.rounded_rectangle(brand_rect, radius=10, fill=accent_color)
    draw.text((left_x + 9, left_y + 5), brand_text, fill="#ffffff", font=brand_font)

    left_y = brand_rect[3] + 12
    movie_title = _clamp_text(title.upper(), 22)
    draw.text((left_x, left_y), movie_title, fill=accent_color, font=title_font)
    left_y += 36

    def draw_line(label, value, current_y):
        line = f"{label} : {value or '-'}"
        draw.text(
            (left_x, current_y),
            _clamp_text(line, 40),
            fill=text_color,
            font=value_font,
        )
        return current_y + 22

    left_y = draw_line("CINEMA", venue_name, left_y)
    left_y = draw_line("THEATER", theater, left_y)
    left_y = draw_line("SEAT", seat_value, left_y)
    left_y = draw_line("DATE", show_date, left_y)
    left_y = draw_line("TIME", show_time, left_y)
    left_y = draw_line("TICKET", f"NPR {ticket_value}", left_y)
    left_y = draw_line("FOOD", f"NPR {food_value}", left_y)
    left_y = draw_line("TOTAL", f"NPR {total_value}", left_y)

    draw.text(
        (left_x, ticket_rect[3] - 28),
        _clamp_text(f"REF : {reference}", 26),
        fill=muted_color,
        font=small_font,
    )

    right_x = separator_x + 18
    right_y = ticket_rect[1] + 20
    draw.text((right_x, right_y), "ADMIT ONE", fill=text_color, font=label_font)
    right_y += 20
    draw.text((right_x, right_y), "STANDARD 3D", fill=muted_color, font=label_font)
    right_y += 22
    draw.text(
        (right_x, right_y),
        _clamp_text(f"THEATER : {theater}", 22),
        fill=muted_color,
        font=small_font,
    )
    right_y += 18
    draw.text(
        (right_x, right_y),
        _clamp_text(f"SEAT : {seat_value}", 22),
        fill=muted_color,
        font=small_font,
    )
    right_y += 18

    if show_date or show_time:
        show_line = " ".join([value for value in [show_date, show_time] if value]).strip()
        draw.text(
            (right_x, right_y),
            _clamp_text(show_line, 22),
            fill=muted_color,
            font=small_font,
        )
        right_y += 18

    right_limit = ticket_rect[2] - 18
    if qr_image:
        qr_size = min(130, right_limit - right_x)
        if qr_size >= 90:
            qr_resized = qr_image.resize((qr_size, qr_size))
            img.paste(qr_resized, (right_x, right_y))
            right_y += qr_size + 12

    barcode_width = min(200, right_limit - right_x)
    barcode_box = (
        right_x,
        ticket_rect[3] - 76,
        right_x + barcode_width,
        ticket_rect[3] - 24,
    )
    _draw_barcode(draw, barcode_box, reference + "right", color=text_color)
    draw.text(
        (right_x, ticket_rect[3] - 22),
        _clamp_text(f"NO. {reference}", 20),
        fill=text_color,
        font=small_font,
    )

    return img


def _render_food_slip_image(payload: dict[str, Any]) -> Any:
    """Render a food slip image for download."""
    width = 820
    bg_color = "#3f3f44"
    paper_color = "#ffffff"
    border_color = "#d7d7d7"
    text_color = "#1f2937"
    muted_color = "#6b7280"
    accent_color = "#f59e0b"

    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    title = str(movie.get("title") or "")
    reference = str(payload.get("reference") or "")
    show_date = str(movie.get("show_date") or "")
    show_time = str(movie.get("show_time") or "")
    food_total = int(_safe_number(payload.get("food_total")))
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    item_lines = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        qty = int(item.get("qty") or 0)
        line = f"{_clamp_text(name, 28)} x{qty}" if qty else _clamp_text(name, 28)
        item_lines.append(line)
    if not item_lines:
        item_lines = ["No food items"]

    line_height = 18
    extra_meta = 20 if show_date or show_time else 0
    height = 230 + extra_meta + len(item_lines) * line_height
    height = max(height, 260)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    margin = 22
    slip_rect = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(
        slip_rect, radius=16, fill=paper_color, outline=border_color, width=2
    )
    _draw_perforations(draw, slip_rect, bg_color, radius=7, step=22)

    brand_font = _load_font(16, bold=True)
    title_font = _load_font(24, bold=True)
    body_font = _load_font(16, bold=False)
    small_font = _load_font(12, bold=False)
    label_font = _load_font(12, bold=True)

    x = slip_rect[0] + 18
    y = slip_rect[1] + 16
    draw.text((x, y), "MERO TICKET", fill=text_color, font=brand_font)
    y += 22

    slip_text = "FOOD SLIP"
    slip_w, slip_h = _text_size(draw, slip_text, title_font)
    slip_rect_box = (x, y, x + slip_w + 18, y + slip_h + 10)
    draw.rounded_rectangle(slip_rect_box, radius=8, fill=accent_color)
    draw.text((x + 9, y + 5), slip_text, fill="#1f2937", font=title_font)
    y = slip_rect_box[3] + 12

    if title:
        draw.text((x, y), _clamp_text(title, 34), fill=muted_color, font=body_font)
        y += 20

    if show_date or show_time:
        show_line = " ".join([value for value in [show_date, show_time] if value]).strip()
        draw.text((x, y), _clamp_text(show_line, 34), fill=muted_color, font=body_font)
        y += 20

    draw.text((x, y), "ITEMS", fill=muted_color, font=label_font)
    y += 18
    for line in item_lines:
        draw.text((x, y), line, fill=text_color, font=body_font)
        y += line_height

    y += 8
    amount_text = f"BILL AMOUNT : NPR {food_total}"
    draw.text((x, y), amount_text, fill=text_color, font=title_font)

    draw.text(
        (x, slip_rect[3] - 24),
        _clamp_text(f"REF : {reference}", 28),
        fill=muted_color,
        font=small_font,
    )

    return img


def _render_ticket_bundle_image(payload: dict[str, Any], qr_image: Any) -> Any:
    """Render the combined ticket + food slip bundle image."""
    bg_color = "#3f3f44"
    ticket_image = _render_ticket_image(payload, qr_image)
    food_image = _render_food_slip_image(payload)
    margin = 24
    spacing = 20
    width = max(ticket_image.width, food_image.width) + margin * 2
    height = ticket_image.height + food_image.height + spacing + margin * 2
    img = Image.new("RGB", (width, height), bg_color)
    ticket_x = (width - ticket_image.width) // 2
    food_x = (width - food_image.width) // 2
    img.paste(ticket_image, (ticket_x, margin))
    img.paste(food_image, (food_x, margin + ticket_image.height + spacing))
    return img


def create_payment_qr(request: Any) -> tuple[dict[str, Any], int]:
    """Create a payment QR and store a ticket record."""
    payload = get_payload(request)
    order = payload.get("order", {}) if isinstance(payload, dict) else {}
    if not order:
        return {"message": "Order data is required"}, status.HTTP_400_BAD_REQUEST

    booking_payload, booking_error, booking_status = _create_booking_from_order(order)
    if booking_error:
        return booking_error, booking_status

    reference = uuid.uuid4().hex[:10].upper()
    ticket_payload = _build_ticket_payload(order, reference, request)
    if booking_payload:
        ticket_payload["booking"] = booking_payload
    Ticket.objects.create(reference=reference, payload=ticket_payload)

    details_url = ticket_payload.get("details_url", "")
    qr_image = _build_qr_image(details_url)
    if not qr_image:
        return {
            "message": "QR code library not installed. Please install qrcode."
        }, status.HTTP_500_INTERNAL_SERVER_ERROR

    ticket_image = _render_ticket_bundle_image(ticket_payload, qr_image)
    return {
        "message": "Payment ticket created",
        "reference": reference,
        "booking": booking_payload,
        "qr_code": _image_to_data_url(qr_image),
        "ticket_image": _image_to_data_url(ticket_image),
        "download_url": request.build_absolute_uri(f"/api/ticket/{reference}/download/"),
        "details_url": details_url,
    }, status.HTTP_200_OK


def build_ticket_download(reference: str) -> Optional[bytes]:
    """Return a rendered ticket PNG for download."""
    ticket = get_ticket(reference)
    if not ticket:
        return None

    payload = ticket.payload or {}
    qr_image = _build_qr_image(payload.get("details_url", ""))
    ticket_image = _render_ticket_image(payload, qr_image)
    buffer = io.BytesIO()
    ticket_image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


def build_ticket_details_html(reference: str) -> Optional[str]:
    """Return an HTML receipt for a ticket reference."""
    ticket = get_ticket(reference)
    if not ticket:
        return None

    payload = ticket.payload or {}
    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    venue_name = movie.get("venue_name") or movie.get("venue") or ""
    venue_location = movie.get("venue_location") or ""
    show_date = movie.get("show_date") or ""
    show_time = movie.get("show_time") or ""
    theater = movie.get("theater") or ""
    ticket_total = int(_safe_number(payload.get("ticket_total")))
    food_total = int(_safe_number(payload.get("food_total")))
    grand_total = int(_safe_number(payload.get("total")))

    items_html = ""
    if items:
        rows = []
        for item in items:
            name = escape(str(item.get("name", "")))
            qty_value = int(item.get("qty") or 0)
            unit_price = int(_safe_number(item.get("price")))
            line_total = unit_price * qty_value
            qty_label = f"{qty_value}" if qty_value else "-"
            rows.append(
                f"""
                <div class=\"item-row\">
                  <div>
                    <div class=\"item-name\">{name or '-'}</div>
                    <div class=\"item-meta\">Qty {escape(qty_label)} | NPR {escape(str(unit_price))}</div>
                  </div>
                  <div class=\"item-total\">NPR {escape(str(line_total))}</div>
                </div>
                """
            )
        items_html = "<div class=\"items\">" + "".join(rows) + "</div>"

    location_html = ""
    if venue_location:
        location_html = f"""
            <div class="row">
              <div class="label">Location</div>
              <div class="value">{escape(str(venue_location))}</div>
            </div>
        """

    html = f"""
    <html>
      <head>
        <title>Ticket {escape(reference)}</title>
        <style>
          :root {{
            --paper: #fff9f2;
            --ink: #1f2937;
            --muted: #6b7280;
            --accent: #111827;
            --line: #e5e7eb;
          }}
          body {{
            font-family: Arial, sans-serif;
            background: #0f1116;
            color: var(--ink);
            padding: 24px;
          }}
          .receipt {{
            background: var(--paper);
            border-radius: 18px;
            padding: 22px 20px;
            width: min(420px, 100%);
            margin: 0 auto;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
            border: 1px solid #e7e0d6;
          }}
          .receipt-header {{
            text-align: center;
            padding-bottom: 12px;
            border-bottom: 1px dashed #d6d3d1;
            margin-bottom: 14px;
          }}
          .brand {{
            font-size: 13px;
            letter-spacing: 0.28em;
            text-transform: uppercase;
            font-weight: 800;
            color: var(--accent);
          }}
          .title {{
            font-size: 18px;
            font-weight: 800;
            margin: 8px 0 4px;
          }}
          .meta {{
            color: var(--muted);
            font-size: 12px;
          }}
          .section {{
            padding: 10px 0;
            border-bottom: 1px dashed #d6d3d1;
          }}
          .section:last-child {{
            border-bottom: none;
          }}
          .section-title {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: var(--muted);
            margin-bottom: 8px;
          }}
          .row {{
            display: grid;
            gap: 4px;
            padding: 6px 0;
          }}
          .label {{
            color: var(--muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
          }}
          .value {{
            font-size: 15px;
            font-weight: 700;
          }}
          .items {{
            display: grid;
            gap: 10px;
            font-weight: 400;
          }}
          .item-row {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            padding: 8px 0;
            border-top: 1px dotted var(--line);
          }}
          .item-row:first-child {{
            border-top: none;
            padding-top: 0;
          }}
          .item-name {{
            font-weight: 700;
            font-size: 14px;
          }}
          .item-meta {{
            font-size: 12px;
            color: var(--muted);
            margin-top: 2px;
            font-weight: 400;
          }}
          .item-total {{
            font-weight: 800;
            font-size: 14px;
            white-space: nowrap;
          }}
          .total-row {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            font-size: 14px;
            padding: 6px 0;
          }}
          .total-row strong {{
            font-size: 16px;
          }}
        </style>
      </head>
      <body>
        <div class="receipt">
          <div class="receipt-header">
            <div class="brand">Mero Ticket</div>
            <div class="title">Ticket & Food Bill</div>
            <div class="meta">Reference: {escape(reference)}</div>
          </div>

          <div class="section">
            <div class="section-title">Ticket Details</div>
            <div class="row">
              <div class="label">Movie</div>
              <div class="value">{escape(movie.get("title", ""))}</div>
            </div>
            <div class="row">
              <div class="label">Cinema Hall</div>
              <div class="value">{escape(str(venue_name))}</div>
            </div>
            {location_html}
            <div class="row">
              <div class="label">Theater</div>
              <div class="value">{escape(str(theater))}</div>
            </div>
            <div class="row">
              <div class="label">Seat</div>
              <div class="value">{escape(movie.get("seat", ""))}</div>
            </div>
            <div class="row">
              <div class="label">Date</div>
              <div class="value">{escape(str(show_date))}</div>
            </div>
            <div class="row">
              <div class="label">Time</div>
              <div class="value">{escape(str(show_time))}</div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Food Items</div>
            <div class="row">
              <div class="label">Food Items</div>
              <div class="value">{items_html or "No food items"}</div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Totals</div>
            <div class="row">
              <div class="label">Ticket Total</div>
              <div class="value">NPR {escape(str(ticket_total))}</div>
            </div>
            <div class="row">
              <div class="label">Food Total</div>
              <div class="value">NPR {escape(str(food_total))}</div>
            </div>
            <div class="row">
              <div class="label">Grand Total</div>
              <div class="value">NPR {escape(str(grand_total))}</div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """
    return html
