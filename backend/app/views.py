from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils.html import escape
from .models import (
    User,
    Admin,
    Vendor,
    Movie,
    Show,
    HomeSlide,
    CollabDetails,
    Collaborator,
    OTPVerification,
    Ticket,
)
from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileUpdateSerializer,
    AdminProfileUpdateSerializer,
    VendorProfileUpdateSerializer,
    MovieSerializer,
    ShowSerializer,
    HomeSlideAdminSerializer,
    HomeSlidePublicSerializer,
    CollabDetailsAdminSerializer,
    CollaboratorSerializer,
    CollaboratorAdminSerializer,
)
from .permissions import IsSuperAdmin
import logging
import random
from django.utils import timezone
from datetime import timedelta, datetime, date
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont
import random
import re
import base64
import io
import uuid

logger = logging.getLogger(__name__)


def get_profile_image_url(request, user):
    profile_image = getattr(user, "profile_image", None)
    if not profile_image:
        return None
    try:
        return request.build_absolute_uri(profile_image.url)
    except Exception:
        return None


def _slugify_text(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _short_label(value):
    text = str(value or "").strip()
    if not text:
        return "CIN"
    words = re.findall(r"[A-Za-z0-9]+", text.upper())
    if not words:
        return "CIN"
    if len(words) == 1:
        return words[0][:3]
    return "".join(word[0] for word in words[:3])


@api_view(["GET", "POST"])
def register(request):
    if request.method == "GET":
        return Response(
            {
                "message": "Registration endpoint",
                "method": "POST",
                "required_fields": [
                    "first_name",
                    "last_name",
                    "email",
                    "phone_number",
                    "dob",
                    "password",
                    "confirm_password",
                ],
            },
            status=status.HTTP_200_OK,
        )

    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        try:
            user = serializer.save()
            return Response(
                {
                    "message": "Registration successful",
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                        "first_name": user.first_name,
                        "middle_name": user.middle_name,
                        "last_name": user.last_name,
                        "phone_number": user.phone_number,
                        "profile_image": get_profile_image_url(request, user),
                        "dob": user.dob.isoformat() if user.dob else None,
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("Error saving user")
            return Response(
                {"message": "Failed to create user", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    return Response(
        {"message": "Registration failed", "errors": serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET", "POST"])
def login(request):
    if request.method == "GET":
        return Response(
            {
                "message": "Login endpoint",
                "method": "POST",
                "required_fields": ["email_or_phone", "password"],
            },
            status=status.HTTP_200_OK,
        )

    serializer = UserLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"message": "Invalid input", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email_or_phone = serializer.validated_data["email_or_phone"].strip()
    password = serializer.validated_data["password"]

    try:
        def _admin_response(admin_user):
            display_name = admin_user.full_name or admin_user.username or admin_user.email
            return Response(
                {
                    "message": f"Admin login successful. Welcome {display_name}!",
                    "role": "admin",
                    "admin": {
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
                    },
                },
                status=status.HTTP_200_OK,
            )

        def _vendor_response(vendor_user):
            display_name = vendor_user.name or vendor_user.username or vendor_user.email
            return Response(
                {
                    "message": f"Vendor login successful. Welcome {display_name}!",
                    "role": "vendor",
                    "vendor": {
                        "id": vendor_user.id,
                        "name": vendor_user.name,
                        "email": vendor_user.email,
                        "username": vendor_user.username,
                        "phone_number": vendor_user.phone_number,
                        "theatre": vendor_user.theatre,
                        "city": vendor_user.city,
                        "status": vendor_user.status,
                        "is_active": vendor_user.is_active,
                        "profile_image": get_profile_image_url(request, vendor_user),
                        "created_at": vendor_user.created_at.isoformat()
                        if vendor_user.created_at
                        else None,
                    },
                },
                status=status.HTTP_200_OK,
            )

        admin = Admin.objects.filter(
            Q(email__iexact=email_or_phone)
            | Q(phone_number=email_or_phone)
            | Q(username__iexact=email_or_phone)
        ).first()

        if admin:
            if not admin.is_active:
                return Response(
                    {"message": "Admin account is inactive"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if not admin.check_password(password):
                return Response(
                    {"message": "Incorrect password"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            return _admin_response(admin)

        vendor_query = (
            Q(email__iexact=email_or_phone)
            | Q(phone_number=email_or_phone)
            | Q(username__iexact=email_or_phone)
        )
        if str(email_or_phone).isdigit():
            try:
                vendor_query |= Q(id=int(email_or_phone))
            except ValueError:
                pass

        vendor = Vendor.objects.filter(vendor_query).first()

        if vendor:
            if not vendor.is_active or str(vendor.status).lower() == "blocked":
                return Response(
                    {"message": "Vendor account is inactive"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if not vendor.check_password(password):
                return Response(
                    {"message": "Incorrect password"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            return _vendor_response(vendor)

        user = User.objects.filter(
            Q(email__iexact=email_or_phone) | Q(phone_number=email_or_phone)
        ).first()

        if not user:
            return Response(
                {"message": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        admin_for_user_q = Q(email__iexact=user.email)
        if user.username:
            admin_for_user_q |= Q(username__iexact=user.username)
        if user.phone_number:
            admin_for_user_q |= Q(phone_number=user.phone_number)
        admin_for_user = Admin.objects.filter(admin_for_user_q).first()

        if admin_for_user:
            if not admin_for_user.is_active:
                return Response(
                    {"message": "Admin account is inactive"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not admin_for_user.check_password(password):
                return Response(
                    {"message": "Incorrect password"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            return _admin_response(admin_for_user)

        # Use secure password check (handles hashed passwords)
        if not user.check_password(password):
            return Response(
                {"message": "Incorrect password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "message": f"Login successful. Welcome {user.first_name}!",
                "role": "user",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "first_name": user.first_name,
                    "middle_name": user.middle_name,
                    "last_name": user.last_name,
                    "phone_number": user.phone_number,
                    "profile_image": get_profile_image_url(request, user),
                    "dob": user.dob.isoformat() if user.dob else None,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("Login error")
        return Response(
            {"message": "An error occurred during login", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET", "POST"])
def manage_vendors(request):
    if request.method == "GET":
        vendors = Vendor.objects.all().order_by("-created_at")
        payload = []
        for vendor in vendors:
            payload.append(
                {
                    "id": vendor.id,
                    "name": vendor.name,
                    "email": vendor.email,
                    "phone_number": vendor.phone_number,
                    "username": vendor.username,
                    "theatre": vendor.theatre,
                    "city": vendor.city,
                    "status": vendor.status,
                    "is_active": vendor.is_active,
                    "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
                    "profile_image": get_profile_image_url(request, vendor),
                }
            )
        return Response({"vendors": payload}, status=status.HTTP_200_OK)

    payload = request.data
    if hasattr(payload, "dict"):
        payload = payload.dict()
    elif not isinstance(payload, dict):
        payload = dict(payload)

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    phone_number = str(payload.get("phone_number") or "").strip() or None
    username = str(payload.get("username") or "").strip() or None
    theatre = str(payload.get("theatre") or payload.get("theatre_name") or "").strip() or None
    city = str(payload.get("city") or "").strip() or None
    status_label = str(payload.get("status") or "Active").strip() or "Active"
    status_label = status_label.title()

    if not name or not email or not password:
        return Response(
            {"message": "Name, email, and password are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if Vendor.objects.filter(email__iexact=email).exists():
        return Response(
            {"message": "Email already exists"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if phone_number and Vendor.objects.filter(phone_number=phone_number).exists():
        return Response(
            {"message": "Phone number already exists"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if username and Vendor.objects.filter(username__iexact=username).exists():
        return Response(
            {"message": "Username already exists"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    is_active = status_label.lower() != "blocked"
    vendor = Vendor(
        name=name,
        email=email,
        phone_number=phone_number,
        username=username,
        theatre=theatre,
        city=city,
        status=status_label,
        is_active=is_active,
    )
    vendor.set_password(password)
    vendor.save()

    return Response(
        {
            "message": "Vendor created",
            "vendor": {
                "id": vendor.id,
                "name": vendor.name,
                "email": vendor.email,
                "phone_number": vendor.phone_number,
                "username": vendor.username,
                "theatre": vendor.theatre,
                "city": vendor.city,
                "status": vendor.status,
                "is_active": vendor.is_active,
                "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
                "profile_image": get_profile_image_url(request, vendor),
            },
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def list_cinemas(request):
    vendors = (
        Vendor.objects.filter(is_active=True)
        .exclude(status__iexact="blocked")
        .order_by("name", "id")
    )
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
        slug_base = _slugify_text(display_name)
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
                "short": _short_label(display_name),
                "profile_image": get_profile_image_url(request, vendor),
            }
        )
    return Response({"vendors": payload}, status=status.HTTP_200_OK)


def _get_payload(request):
    payload = request.data
    if hasattr(payload, "dict"):
        payload = payload.dict()
    if isinstance(payload, dict):
        return payload
    return {}


def _coalesce(payload, *keys, default=None):
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return default


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_time(value):
    if not value:
        return None
    if hasattr(value, "hour"):
        return value
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except Exception:
        return None


def _parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return bool(value)


def _movie_payload(movie, listing_status=None, request=None):
    banner_url = None
    if getattr(movie, "banner_image", None):
        try:
            banner_url = movie.banner_image.url
            if request is not None:
                banner_url = request.build_absolute_uri(banner_url)
        except Exception:
            banner_url = None
    return {
        "id": movie.id,
        "title": movie.title,
        "description": movie.description,
        "language": movie.language,
        "genre": movie.genre,
        "duration": movie.duration,
        "durationMinutes": movie.duration_minutes,
        "rating": movie.rating,
        "releaseDate": movie.release_date.isoformat() if movie.release_date else None,
        "bannerImage": banner_url,
        "posterUrl": movie.poster_url,
        "trailerUrl": movie.trailer_url,
        "status": movie.status,
        "listingStatus": listing_status or movie.status,
        "createdAt": movie.created_at.isoformat() if movie.created_at else None,
    }


def _show_payload(show):
    return {
        "id": show.id,
        "movieId": show.movie_id,
        "movie": show.movie.title if show.movie else None,
        "vendorId": show.vendor_id,
        "vendor": show.vendor.name if show.vendor else None,
        "hall": show.hall,
        "slot": show.slot,
        "date": show.show_date.isoformat() if show.show_date else None,
        "start": show.start_time.strftime("%H:%M") if show.start_time else None,
        "end": show.end_time.strftime("%H:%M") if show.end_time else None,
        "screenType": show.screen_type,
        "price": float(show.price) if show.price is not None else None,
        "status": show.status,
        "listingStatus": show.listing_status,
        "city": show.vendor.city if show.vendor else None,
        "theatre": show.vendor.theatre if show.vendor else None,
        "createdAt": show.created_at.isoformat() if show.created_at else None,
    }


def _active_slide_filters(now=None):
    if now is None:
        now = timezone.now()
    return (
        Q(is_active=True)
        & (Q(start_at__isnull=True) | Q(start_at__lte=now))
        & (Q(end_at__isnull=True) | Q(end_at__gte=now))
    )


@api_view(["GET"])
def home_slides(request):
    now = timezone.now()
    slides = (
        HomeSlide.objects.select_related("movie", "collab_details")
        .filter(_active_slide_filters(now))
        .order_by("sort_order", "-created_at")
    )
    serializer = HomeSlidePublicSerializer(slides, many=True, context={"request": request})
    return Response({"slides": serializer.data}, status=status.HTTP_200_OK)


@api_view(["GET"])
def home_collaborators(request):
    collaborators = Collaborator.objects.filter(is_active=True).order_by("sort_order", "name")
    serializer = CollaboratorSerializer(
        collaborators, many=True, context={"request": request}
    )
    return Response({"collaborators": serializer.data}, status=status.HTTP_200_OK)


def _sync_collab_details(slide, payload):
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


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_home_slides(request):
    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, request.data)
    response = HomeSlideAdminSerializer(slide).data
    return Response({"slide": response}, status=status.HTTP_201_CREATED)


@api_view(["PUT", "DELETE"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_home_slide_detail(request, slide_id):
    try:
        slide = HomeSlide.objects.get(pk=slide_id)
    except HomeSlide.DoesNotExist:
        return Response({"message": "Slide not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        slide.delete()
        return Response({"message": "Slide deleted"}, status=status.HTTP_200_OK)

    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(slide, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, request.data)
    response = HomeSlideAdminSerializer(slide).data
    return Response({"slide": response}, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsSuperAdmin])
def admin_home_slide_toggle(request, slide_id):
    try:
        slide = HomeSlide.objects.get(pk=slide_id)
    except HomeSlide.DoesNotExist:
        return Response({"message": "Slide not found"}, status=status.HTTP_404_NOT_FOUND)

    slide.is_active = not slide.is_active
    slide.save(update_fields=["is_active"])
    return Response(
        {"id": slide.id, "is_active": slide.is_active}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_collaborators(request):
    serializer = CollaboratorAdminSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    collaborator = serializer.save()
    return Response(
        {"collaborator": CollaboratorAdminSerializer(collaborator).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["PUT", "DELETE"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_collaborator_detail(request, collaborator_id):
    try:
        collaborator = Collaborator.objects.get(pk=collaborator_id)
    except Collaborator.DoesNotExist:
        return Response(
            {"message": "Collaborator not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "DELETE":
        collaborator.delete()
        return Response({"message": "Collaborator deleted"}, status=status.HTTP_200_OK)

    serializer = CollaboratorAdminSerializer(
        collaborator, data=request.data, partial=True
    )
    serializer.is_valid(raise_exception=True)
    collaborator = serializer.save()
    return Response(
        {"collaborator": CollaboratorAdminSerializer(collaborator).data},
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsSuperAdmin])
def admin_collaborator_toggle(request, collaborator_id):
    try:
        collaborator = Collaborator.objects.get(pk=collaborator_id)
    except Collaborator.DoesNotExist:
        return Response(
            {"message": "Collaborator not found"}, status=status.HTTP_404_NOT_FOUND
        )

    collaborator.is_active = not collaborator.is_active
    collaborator.save(update_fields=["is_active"])
    return Response(
        {"id": collaborator.id, "is_active": collaborator.is_active},
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "POST"])
def movies(request):
    if request.method == "GET":
        movies_qs = Movie.objects.all().order_by("-created_at")
        payload = []
        for movie in movies_qs:
            listing = None
            statuses = list(
                movie.shows.values_list("listing_status", flat=True).order_by("listing_status")
            )
            if any(str(status).lower().startswith("now") for status in statuses):
                listing = "Now Showing"
            elif any(str(status).lower().startswith("coming") for status in statuses):
                listing = "Coming Soon"
            payload.append(_movie_payload(movie, listing, request=request))
        return Response({"movies": payload}, status=status.HTTP_200_OK)

    payload = _get_payload(request)
    title = str(_coalesce(payload, "title", "name", default="") or "").strip()
    if not title:
        return Response({"message": "Title is required"}, status=status.HTTP_400_BAD_REQUEST)

    duration_minutes_value = _coalesce(payload, "durationMinutes", "duration_minutes")
    try:
        duration_minutes_value = (
            int(duration_minutes_value) if duration_minutes_value is not None else None
        )
    except (TypeError, ValueError):
        duration_minutes_value = None

    movie = Movie(
        title=title,
        description=_coalesce(payload, "description", "synopsis"),
        language=_coalesce(payload, "language", "lang"),
        genre=_coalesce(payload, "genre", "category"),
        duration=_coalesce(payload, "duration", "runtime"),
        duration_minutes=duration_minutes_value,
        rating=_coalesce(payload, "rating", "censor"),
        release_date=_parse_date(_coalesce(payload, "releaseDate", "release_date")),
        poster_url=_coalesce(payload, "posterUrl", "poster_url", "poster"),
        trailer_url=_coalesce(payload, "trailerUrl", "trailer_url", "trailer"),
        status=_coalesce(payload, "status", default="Coming Soon"),
    )
    movie.save()
    return Response({"movie": _movie_payload(movie, request=request)}, status=status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def movie_detail(request, movie_id):
    try:
        movie = Movie.objects.get(pk=movie_id)
    except Movie.DoesNotExist:
        return Response({"message": "Movie not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response({"movie": _movie_payload(movie, request=request)}, status=status.HTTP_200_OK)

    if request.method == "DELETE":
        movie.delete()
        return Response({"message": "Movie deleted"}, status=status.HTTP_200_OK)

    payload = _get_payload(request)
    for field, keys in {
        "title": ("title", "name"),
        "description": ("description", "synopsis"),
        "language": ("language", "lang"),
        "genre": ("genre", "category"),
        "duration": ("duration", "runtime"),
        "rating": ("rating", "censor"),
        "poster_url": ("posterUrl", "poster_url", "poster"),
        "trailer_url": ("trailerUrl", "trailer_url", "trailer"),
        "status": ("status",),
    }.items():
        value = _coalesce(payload, *keys)
        if value is not None:
            setattr(movie, field, value)

    duration_minutes_value = _coalesce(payload, "durationMinutes", "duration_minutes")
    if duration_minutes_value is not None:
        try:
            movie.duration_minutes = int(duration_minutes_value)
        except (TypeError, ValueError):
            movie.duration_minutes = None

    release_value = _coalesce(payload, "releaseDate", "release_date")
    if release_value is not None:
        movie.release_date = _parse_date(release_value)

    movie.save()
    return Response({"movie": _movie_payload(movie, request=request)}, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
def shows(request):
    if request.method == "GET":
        shows_qs = Show.objects.select_related("movie", "vendor").order_by("-show_date", "-start_time")
        movie_id = request.query_params.get("movie_id") or request.query_params.get("movieId")
        vendor_id = request.query_params.get("vendor_id") or request.query_params.get("vendorId")

        if movie_id:
            shows_qs = shows_qs.filter(movie_id=movie_id)
        if vendor_id:
            shows_qs = shows_qs.filter(vendor_id=vendor_id)

        payload = [_show_payload(show) for show in shows_qs]
        return Response({"shows": payload}, status=status.HTTP_200_OK)

    payload = _get_payload(request)
    vendor_id = _coalesce(payload, "vendorId", "vendor_id")
    movie_id = _coalesce(payload, "movieId", "movie_id")

    if not vendor_id or not movie_id:
        return Response(
            {"message": "vendorId and movieId are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        vendor = Vendor.objects.get(pk=vendor_id)
    except Vendor.DoesNotExist:
        return Response({"message": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

    try:
        movie = Movie.objects.get(pk=movie_id)
    except Movie.DoesNotExist:
        return Response({"message": "Movie not found"}, status=status.HTTP_404_NOT_FOUND)

    show_date = _parse_date(_coalesce(payload, "date", "show_date", "showDate"))
    start_time = _parse_time(_coalesce(payload, "start", "start_time", "startTime"))
    end_time = _parse_time(_coalesce(payload, "end", "end_time", "endTime"))

    if not show_date or not start_time:
        return Response(
            {"message": "show date and start time are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    show = Show(
        vendor=vendor,
        movie=movie,
        hall=_coalesce(payload, "hall"),
        slot=_coalesce(payload, "slot"),
        screen_type=_coalesce(payload, "screenType", "screen_type"),
        price=_coalesce(payload, "price"),
        status=_coalesce(payload, "status", default="Open"),
        listing_status=_coalesce(payload, "listingStatus", "listing_status", default="Now Showing"),
        show_date=show_date,
        start_time=start_time,
        end_time=end_time,
    )
    show.save()
    return Response({"show": _show_payload(show)}, status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
def show_detail(request, show_id):
    try:
        show = Show.objects.get(pk=show_id)
    except Show.DoesNotExist:
        return Response({"message": "Show not found"}, status=status.HTTP_404_NOT_FOUND)

    show.delete()
    return Response({"message": "Show deleted"}, status=status.HTTP_200_OK)


@api_view(["POST"])
def forgot_password(request):
    """Request an OTP for password reset. Expects { email } in body."""
    email = request.data.get("email", "").strip()
    if not email:
        return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # generate 6-digit OTP
        otp = f"{random.randint(100000, 999999)}"
        # save OTP record
        OTPVerification.objects.create(email=email, otp=otp)

        # In production you would send OTP by email; for now we log it (and return generic message)
        logger.info(f"Generated OTP for {email}: {otp}")
        # Also print to terminal for easy debugging when DEBUG=True
        if getattr(settings, "DEBUG", False):
            print(f"DEBUG OTP for {email}: {otp}")

        return Response({"message": "OTP sent to your email"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("forgot_password error")
        return Response({"message": "Failed to send OTP", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def verify_otp(request):
    """Verify OTP. Expects { email, otp } in body."""
    email = request.data.get("email", "").strip()
    otp = request.data.get("otp", "").strip()
    if not email or not otp:
        return Response({"message": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # only consider OTPs created within last 10 minutes
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(email__iexact=email, otp=otp, created_at__gte=cutoff)
            .order_by("-created_at")
            .first()
        )
        if not record:
            return Response({"message": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

        record.is_verified = True
        record.save()

        return Response({"message": "OTP verified"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("verify_otp error")
        return Response({"message": "Failed to verify OTP", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def reset_password(request):
    """Reset password using verified OTP. Expects { email, otp, new_password }."""
    email = request.data.get("email", "").strip()
    otp = request.data.get("otp", "").strip()
    new_password = request.data.get("new_password", "")

    if not email or not otp or not new_password:
        return Response({"message": "Email, OTP and new_password are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # check verified OTP in last 10 minutes
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(email__iexact=email, otp=otp, created_at__gte=cutoff, is_verified=True)
            .order_by("-created_at")
            .first()
        )
        if not record:
            return Response({"message": "Invalid or unverified OTP"}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        user.set_password(new_password)
        user.save()

        # Invalidate OTP record
        record.is_verified = False
        record.save()

        return Response({"message": "Password reset successful"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("reset_password error")
        return Response({"message": "Failed to reset password", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PATCH"])
def update_profile(request, user_id):
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    # Avoid QueryDict.copy() deep copy (fails on file objects).
    if hasattr(request.data, "dict"):
        data = request.data.dict()
    else:
        data = dict(request.data)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar_raw = data.pop("remove_avatar", "")
    remove_avatar = str(remove_avatar_raw).lower() in ("1", "true", "yes")
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
        return Response(
            {"message": "No profile changes provided"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = UserProfileUpdateSerializer(user, data=data, partial=True)
    if not serializer.is_valid():
        return Response(
            {"message": "Profile update failed", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    updated_user = serializer.save()

    if remove_avatar:
        if updated_user.profile_image:
            updated_user.profile_image.delete(save=False)
        updated_user.profile_image = None
        updated_user.save()
    elif uploaded_image:
        if updated_user.profile_image:
            updated_user.profile_image.delete(save=False)
        updated_user.profile_image = uploaded_image
        updated_user.save()
    return Response(
        {
            "message": "Profile updated",
            "user": {
                "id": updated_user.id,
                "email": updated_user.email,
                "phone_number": updated_user.phone_number,
                "first_name": updated_user.first_name,
                "middle_name": updated_user.middle_name,
                "last_name": updated_user.last_name,
                "username": updated_user.username,
                "profile_image": get_profile_image_url(request, updated_user),
                "dob": updated_user.dob.isoformat() if updated_user.dob else None,
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
def update_admin_profile(request, admin_id):
    try:
        admin_user = Admin.objects.get(pk=admin_id)
    except Admin.DoesNotExist:
        return Response({"message": "Admin not found"}, status=status.HTTP_404_NOT_FOUND)

    if hasattr(request.data, "dict"):
        data = request.data.dict()
    else:
        data = dict(request.data)

    uploaded_image = request.FILES.get("profile_image")
    remove_avatar_raw = data.pop("remove_avatar", "")
    remove_avatar = str(remove_avatar_raw).lower() in ("1", "true", "yes")
    data.pop("username", None)
    data.pop("email", None)
    data.pop("profile_image", None)

    if "full_name" in data and isinstance(data["full_name"], str):
        data["full_name"] = data["full_name"].strip()
        if data["full_name"] == "":
            data["full_name"] = None

    if "phone_number" in data:
        phone = str(data["phone_number"]).strip()
        data["phone_number"] = phone or None
        if phone and Admin.objects.filter(phone_number=phone).exclude(pk=admin_user.id).exists():
            return Response(
                {"message": "Phone number already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if not data and not uploaded_image and not remove_avatar:
        return Response(
            {"message": "No profile changes provided"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = AdminProfileUpdateSerializer(admin_user, data=data, partial=True)
    if not serializer.is_valid():
        return Response(
            {"message": "Profile update failed", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    updated_admin = serializer.save()

    if remove_avatar:
        if updated_admin.profile_image:
            updated_admin.profile_image.delete(save=False)
        updated_admin.profile_image = None
        updated_admin.save()
    elif uploaded_image:
        if updated_admin.profile_image:
            updated_admin.profile_image.delete(save=False)
        updated_admin.profile_image = uploaded_image
        updated_admin.save()

    return Response(
        {
            "message": "Profile updated",
            "admin": {
                "id": updated_admin.id,
                "email": updated_admin.email,
                "username": updated_admin.username,
                "full_name": updated_admin.full_name,
                "phone_number": updated_admin.phone_number,
                "is_active": updated_admin.is_active,
                "profile_image": get_profile_image_url(request, updated_admin),
                "date_joined": updated_admin.date_joined.isoformat()
                if updated_admin.date_joined
                else None,
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
def update_vendor_profile(request, vendor_id):
    try:
        vendor_user = Vendor.objects.get(pk=vendor_id)
    except Vendor.DoesNotExist:
        return Response({"message": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

    if hasattr(request.data, "dict"):
        data = request.data.dict()
    else:
        data = dict(request.data)

    uploaded_image = request.FILES.get("profile_image")
    remove_avatar_raw = data.pop("remove_avatar", "")
    remove_avatar = str(remove_avatar_raw).lower() in ("1", "true", "yes")
    data.pop("username", None)
    data.pop("email", None)
    data.pop("status", None)
    data.pop("is_active", None)
    data.pop("created_at", None)
    data.pop("profile_image", None)

    if "name" in data and isinstance(data["name"], str):
        data["name"] = data["name"].strip()
        if data["name"] == "":
            return Response(
                {"message": "Vendor name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if "phone_number" in data:
        phone = str(data["phone_number"]).strip()
        data["phone_number"] = phone or None
        if phone and Vendor.objects.filter(phone_number=phone).exclude(pk=vendor_user.id).exists():
            return Response(
                {"message": "Phone number already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    for key in ("theatre", "city"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip() or None

    if not data and not uploaded_image and not remove_avatar:
        return Response(
            {"message": "No profile changes provided"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = VendorProfileUpdateSerializer(vendor_user, data=data, partial=True)
    if not serializer.is_valid():
        return Response(
            {"message": "Profile update failed", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    updated_vendor = serializer.save()

    if remove_avatar:
        if updated_vendor.profile_image:
            updated_vendor.profile_image.delete(save=False)
        updated_vendor.profile_image = None
        updated_vendor.save()
    elif uploaded_image:
        if updated_vendor.profile_image:
            updated_vendor.profile_image.delete(save=False)
        updated_vendor.profile_image = uploaded_image
        updated_vendor.save()

    return Response(
        {
            "message": "Profile updated",
            "vendor": {
                "id": updated_vendor.id,
                "name": updated_vendor.name,
                "email": updated_vendor.email,
                "username": updated_vendor.username,
                "phone_number": updated_vendor.phone_number,
                "theatre": updated_vendor.theatre,
                "city": updated_vendor.city,
                "status": updated_vendor.status,
                "is_active": updated_vendor.is_active,
                "created_at": updated_vendor.created_at.isoformat()
                if updated_vendor.created_at
                else None,
                "profile_image": get_profile_image_url(request, updated_vendor),
            },
        },
        status=status.HTTP_200_OK,
    )


def _safe_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_text(value, limit=44):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _load_font(size, bold=False):
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


def _normalize_items(items):
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


def _build_ticket_payload(order, reference, request):
    if not isinstance(order, dict):
        order = {}
    movie = order.get("movie") if isinstance(order.get("movie"), dict) else {}
    venue_raw = movie.get("venue") or ""
    venue_parts = [part.strip() for part in str(venue_raw).split(",") if part.strip()]
    venue_name = venue_parts[0] if venue_parts else str(venue_raw)
    show_date = venue_parts[1] if len(venue_parts) > 1 else ""
    show_time = venue_parts[2] if len(venue_parts) > 2 else ""

    theater = movie.get("theater") or movie.get("screen") or movie.get("hall")
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
            "seat": str(movie.get("seat") or ""),
            "venue": str(venue_raw),
            "venue_name": str(venue_name),
            "show_date": str(show_date),
            "show_time": str(show_time),
            "theater": str(theater),
            "language": str(movie.get("language") or ""),
            "runtime": str(movie.get("runtime") or ""),
        },
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


def _build_qr_image(data):
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


def _image_to_data_url(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _draw_perforations(draw, rect, bg_color, radius=7, step=22):
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


def _draw_barcode(draw, box, seed_value, color="#1f2933"):
    rng = random.Random(seed_value)
    x0, y0, x1, y1 = box
    x = x0
    while x < x1:
        bar_width = rng.choice([1, 1, 2, 2, 3])
        gap = rng.choice([1, 1, 2])
        bar_end = min(x + bar_width, x1)
        draw.rectangle((x, y0, bar_end, y1), fill=color)
        x = bar_end + gap


def _render_ticket_image(payload, qr_image):
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
    draw.rounded_rectangle(ticket_rect, radius=18, fill=paper_color, outline=border_color, width=2)
    _draw_perforations(draw, ticket_rect, bg_color, radius=8, step=24)

    ticket_width = ticket_rect[2] - ticket_rect[0]
    separator_x = ticket_rect[0] + int(ticket_width * 0.7)
    dash_y = ticket_rect[1] + 18
    while dash_y < ticket_rect[3] - 18:
        draw.line((separator_x, dash_y, separator_x, dash_y + 10), fill=border_color, width=2)
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
        draw.text((left_x, current_y), _clamp_text(line, 40), fill=text_color, font=value_font)
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
    barcode_box = (right_x, ticket_rect[3] - 76, right_x + barcode_width, ticket_rect[3] - 24)
    _draw_barcode(draw, barcode_box, reference + "right", color=text_color)
    draw.text(
        (right_x, ticket_rect[3] - 22),
        _clamp_text(f"NO. {reference}", 20),
        fill=text_color,
        font=small_font,
    )

    return img


def _render_food_slip_image(payload):
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
    draw.rounded_rectangle(slip_rect, radius=16, fill=paper_color, outline=border_color, width=2)
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


def _render_ticket_bundle_image(payload, qr_image):
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


def _get_ticket(reference):
    try:
        return Ticket.objects.get(reference=reference)
    except Ticket.DoesNotExist:
        return None


@api_view(["POST"])
def create_payment_qr(request):
    payload = request.data
    if hasattr(payload, "dict"):
        payload = payload.dict()
    elif not isinstance(payload, dict):
        payload = dict(payload)

    order = payload.get("order", {}) if isinstance(payload, dict) else {}
    if not order:
        return Response(
            {"message": "Order data is required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reference = uuid.uuid4().hex[:10].upper()
    ticket_payload = _build_ticket_payload(order, reference, request)
    Ticket.objects.create(reference=reference, payload=ticket_payload)

    details_url = ticket_payload.get("details_url", "")
    qr_image = _build_qr_image(details_url)
    if not qr_image:
        return Response(
            {"message": "QR code library not installed. Please install qrcode."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    ticket_image = _render_ticket_bundle_image(ticket_payload, qr_image)
    return Response(
        {
            "message": "Payment ticket created",
            "reference": reference,
            "qr_code": _image_to_data_url(qr_image),
            "ticket_image": _image_to_data_url(ticket_image),
            "download_url": request.build_absolute_uri(
                f"/api/ticket/{reference}/download/"
            ),
            "details_url": details_url,
        },
        status=status.HTTP_200_OK,
    )


def download_ticket(request, reference):
    ticket = _get_ticket(reference)
    if not ticket:
        return HttpResponse("Ticket not found", status=404)

    payload = ticket.payload or {}
    qr_image = _build_qr_image(payload.get("details_url", ""))
    ticket_image = _render_ticket_image(payload, qr_image)
    buffer = io.BytesIO()
    ticket_image.save(buffer, format="PNG")
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="ticket-{reference}.png"'
    return response


def ticket_details(request, reference):
    ticket = _get_ticket(reference)
    if not ticket:
        return HttpResponse("Ticket not found", status=404)

    payload = ticket.payload or {}
    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    venue_name = movie.get("venue_name") or movie.get("venue") or ""
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
                <div class="item-row">
                  <div>
                    <div class="item-name">{name or '-'}</div>
                    <div class="item-meta">Qty {escape(qty_label)} | NPR {escape(str(unit_price))}</div>
                  </div>
                  <div class="item-total">NPR {escape(str(line_total))}</div>
                </div>
                """
            )
        items_html = "<div class=\"items\">" + "".join(rows) + "</div>"

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
    return HttpResponse(html, content_type="text/html")
