"""Query helpers and response payload builders."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from .models import (
    Banner,
    Collaborator,
    HomeSlide,
    Movie,
    MovieCredit,
    Review,
    Show,
    Ticket,
    Vendor,
)
from .permissions import is_admin_request, is_vendor_request, resolve_vendor
from .utils import (
    build_media_url,
    combine_date_time_utc,
    ensure_utc_datetime,
    extract_youtube_id,
)

LISTING_STATUS_NOW = "Now Showing"
LISTING_STATUS_COMING = "Coming Soon"
YOUTUBE_THUMBNAIL_TEMPLATE = "https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg"
SHOW_STATUS_UPCOMING = Show.STATUS_UPCOMING
SHOW_STATUS_RUNNING = Show.STATUS_RUNNING
SHOW_STATUS_COMPLETED = Show.STATUS_COMPLETED
BOOKING_CLOSE_BEFORE_START_MINUTES = Show.BOOKING_CLOSE_BEFORE_START_MINUTES


def _repair_malformed_ticket_uuid_rows() -> None:
    """Repair any malformed ticket UUID values that can break ORM lookups."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, ticket_id FROM tickets")
            rows = cursor.fetchall()
    except Exception:
        return

    for row_id, ticket_uuid in rows:
        try:
            uuid.UUID(str(ticket_uuid))
        except (TypeError, ValueError, AttributeError):
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE tickets SET ticket_id = %s WHERE id = %s",
                        [str(uuid.uuid4()), row_id],
                    )
            except Exception:
                continue


def _hydrate_ticket_from_row(row: tuple[Any, ...]) -> Ticket:
    """Build a Ticket instance from a raw database row."""
    (
        ticket_pk,
        ticket_uuid,
        reference,
        user_id,
        show_id,
        seats,
        show_datetime,
        payment_status,
        token_expires_at,
        is_used,
        payload,
        created_at,
    ) = row

    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except Exception:
            payload = {}

    try:
        parsed_ticket_uuid = uuid.UUID(str(ticket_uuid))
    except (TypeError, ValueError, AttributeError):
        parsed_ticket_uuid = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE tickets SET ticket_id = %s WHERE id = %s",
                [str(parsed_ticket_uuid), ticket_pk],
            )

    ticket = Ticket(
        id=ticket_pk,
        ticket_id=parsed_ticket_uuid,
        reference=str(reference or ""),
        user_id=user_id,
        show_id=show_id,
        seats=seats,
        show_datetime=show_datetime,
        payment_status=payment_status,
        token_expires_at=token_expires_at,
        is_used=bool(is_used),
        payload=payload if isinstance(payload, dict) else {},
        created_at=created_at,
    )
    ticket._state.adding = False
    ticket._state.db = connection.alias
    return ticket


def _get_ticket_by_reference_raw(reference: str) -> Optional[Ticket]:
    """Resolve a ticket by exact or case-insensitive reference without ORM conversion."""
    query = (
        "SELECT id, ticket_id, reference, user_id, show_id, seats, show_datetime, "
        "payment_status, token_expires_at, is_used, payload, created_at "
        "FROM tickets WHERE reference = %s LIMIT 1"
    )
    with connection.cursor() as cursor:
        cursor.execute(query, [reference])
        row = cursor.fetchone()
        if row:
            return _hydrate_ticket_from_row(row)

        cursor.execute(query.replace("reference = %s", "LOWER(reference) = LOWER(%s)"), [reference])
        row = cursor.fetchone()
        if row:
            return _hydrate_ticket_from_row(row)
    return None


def _combine_local_show_datetime(show_date, show_time):
    if not show_date or not show_time:
        return None
    return combine_date_time_utc(show_date, show_time)


def _show_start_before_or_at(moment: datetime) -> Q:
    return Q(show_date__lt=moment.date()) | Q(
        show_date=moment.date(),
        start_time__lte=moment.time(),
    )


def _show_start_after(moment: datetime) -> Q:
    return Q(show_date__gt=moment.date()) | Q(
        show_date=moment.date(),
        start_time__gt=moment.time(),
    )


def _show_end_before_or_at(moment: datetime) -> Q:
    return (
        Q(show_date__lt=moment.date())
        | Q(
            show_date=moment.date(),
            end_time__isnull=False,
            end_time__lte=moment.time(),
        )
        | Q(
            show_date=moment.date(),
            end_time__isnull=True,
            start_time__lte=moment.time(),
        )
    )


def get_show_lifecycle_state(show: Show, now: Optional[datetime] = None) -> dict[str, Any]:
    now = ensure_utc_datetime(now or timezone.now())
    start_dt = _combine_local_show_datetime(show.show_date, show.start_time)
    end_dt = _combine_local_show_datetime(show.show_date, show.end_time or show.start_time)
    if not start_dt:
        return {
            "status": SHOW_STATUS_COMPLETED,
            "booking_open": False,
            "start_at": None,
            "end_at": end_dt,
            "booking_close_at": None,
        }

    booking_close_at = start_dt - timedelta(minutes=BOOKING_CLOSE_BEFORE_START_MINUTES)
    if end_dt and now >= end_dt:
        status_value = SHOW_STATUS_COMPLETED
    elif now >= start_dt:
        status_value = SHOW_STATUS_RUNNING
    else:
        status_value = SHOW_STATUS_UPCOMING

    booking_open = status_value == SHOW_STATUS_UPCOMING and now < booking_close_at
    return {
        "status": status_value,
        "booking_open": booking_open,
        "start_at": start_dt,
        "end_at": end_dt,
        "booking_close_at": booking_close_at,
    }


def is_show_booking_open(show: Show, now: Optional[datetime] = None) -> bool:
    return bool(get_show_lifecycle_state(show, now=now).get("booking_open"))


def sync_show_lifecycle_statuses(now: Optional[datetime] = None) -> dict[str, int]:
    now = ensure_utc_datetime(now or timezone.now())
    updated = {
        SHOW_STATUS_UPCOMING: 0,
        SHOW_STATUS_RUNNING: 0,
        SHOW_STATUS_COMPLETED: 0,
    }
    for show in Show.objects.only("id", "show_date", "start_time", "end_time", "status").iterator():
        next_status = get_show_lifecycle_state(show, now=now)["status"]
        current_status = str(show.status or "").strip().lower()
        if current_status == next_status:
            continue
        Show.objects.filter(id=show.id).update(status=next_status)
        updated[next_status] += 1
    return updated


def list_available_shows(now: Optional[datetime] = None):
    now = ensure_utc_datetime(now or timezone.now())
    cutoff = now + timedelta(minutes=BOOKING_CLOSE_BEFORE_START_MINUTES)
    return Show.objects.filter(
        _show_start_after(cutoff),
        movie__is_approved=True,
    ).exclude(status__iexact=SHOW_STATUS_COMPLETED)


def list_booking_closed_shows(now: Optional[datetime] = None):
    now = ensure_utc_datetime(now or timezone.now())
    cutoff = now + timedelta(minutes=BOOKING_CLOSE_BEFORE_START_MINUTES)
    return Show.objects.filter(
        _show_start_before_or_at(cutoff),
        _show_start_after(now),
        movie__is_approved=True,
    ).exclude(status__iexact=SHOW_STATUS_COMPLETED)


def list_running_shows(now: Optional[datetime] = None):
    now = ensure_utc_datetime(now or timezone.now())
    return Show.objects.filter(
        _show_start_before_or_at(now),
        movie__is_approved=True,
    ).exclude(_show_end_before_or_at(now))


def list_completed_shows(now: Optional[datetime] = None):
    now = ensure_utc_datetime(now or timezone.now())
    return Show.objects.filter(_show_end_before_or_at(now), movie__is_approved=True)


def normalize_city(value: Optional[Any]) -> str:
    """Normalize city/location query value."""
    return str(value or "").strip()


def active_slide_filters(now: Optional[timezone.datetime] = None) -> Q:
    """Return the Q filters for active slides based on current time."""
    if now is None:
        now = timezone.now()
    return (
        Q(is_active=True)
        & (Q(start_at__isnull=True) | Q(start_at__lte=now))
        & (Q(end_at__isnull=True) | Q(end_at__gte=now))
    )


def active_banner_filters(now: Optional[timezone.datetime] = None) -> Q:
    """Return the Q filters for active banners."""
    return Q(is_active=True)


def list_active_banners(display_on: Optional[str] = None, now: Optional[timezone.datetime] = None):
    """Return active banners ordered by most recently created."""
    return (
        Banner.objects.select_related("movie")
        .filter(active_banner_filters(now))
        .order_by("-created_at")
    )


def list_banners():
    """Return all banners ordered by most recently created."""
    return Banner.objects.select_related("movie").all().order_by("-created_at")


def get_banner(banner_id: int) -> Optional[Banner]:
    """Return a banner by ID or None."""
    try:
        return Banner.objects.get(pk=banner_id)
    except Banner.DoesNotExist:
        return None


def list_active_home_slides(now: Optional[timezone.datetime] = None):
    """Return active home slides ordered by sort and creation date."""
    return (
        HomeSlide.objects.select_related("movie", "collab_details")
        .filter(active_slide_filters(now))
        .order_by("sort_order", "-created_at")
    )


def list_active_collaborators():
    """Return active collaborators ordered by sort and name."""
    return Collaborator.objects.filter(is_active=True).order_by("sort_order", "name")


def get_home_slide(slide_id: int) -> Optional[HomeSlide]:
    """Return a home slide by ID or None."""
    try:
        return HomeSlide.objects.get(pk=slide_id)
    except HomeSlide.DoesNotExist:
        return None


def get_collaborator(collaborator_id: int) -> Optional[Collaborator]:
    """Return a collaborator by ID or None."""
    try:
        return Collaborator.objects.get(pk=collaborator_id)
    except Collaborator.DoesNotExist:
        return None


def list_vendors(request: Optional[Any] = None):
    """Return vendors scoped to the authenticated vendor if present."""
    queryset = Vendor.objects.all().order_by("-created_at")
    vendor = resolve_vendor(request) if request is not None else None
    if vendor:
        queryset = queryset.filter(pk=vendor.pk)
    return queryset


def list_cinema_vendors(city: Optional[str] = None):
    """Return active, non-blocked vendors for cinema listings."""
    queryset = Vendor.objects.filter(is_active=True).exclude(status__iexact="blocked")
    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(city__iexact=normalized_city)
    return queryset.order_by("name", "id")


def list_movies_with_shows(city: Optional[str] = None):
    """Return movies that currently have at least one show."""
    sync_show_lifecycle_statuses()
    show_ids = list_available_shows().values_list("id", flat=True)
    queryset = Movie.objects.filter(shows__id__in=show_ids)
    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(shows__vendor__city__iexact=normalized_city)
    return queryset.distinct().order_by("title", "id")


def list_movies_for_vendor(vendor_id: int, city: Optional[str] = None):
    """Return movies that have shows for a specific vendor, optionally city-scoped."""
    sync_show_lifecycle_statuses()
    show_ids = list_available_shows().filter(vendor_id=vendor_id).values_list("id", flat=True)
    queryset = Movie.objects.filter(shows__id__in=show_ids)
    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(shows__vendor__city__iexact=normalized_city)
    return queryset.distinct().order_by("title", "id")


def list_vendors_for_movie(movie_id: int, city: Optional[str] = None):
    """Return vendors that have shows for a specific movie."""
    sync_show_lifecycle_statuses()
    show_ids = list_available_shows().filter(movie_id=movie_id).values_list("id", flat=True)
    queryset = Vendor.objects.filter(shows__id__in=show_ids)
    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(city__iexact=normalized_city)
    return queryset.distinct().order_by("name", "id")


def list_show_dates_for_vendor_movie(
    vendor_id: int,
    movie_id: int,
    city: Optional[str] = None,
):
    """Return distinct show dates for a vendor + movie pair, optionally city-scoped."""
    sync_show_lifecycle_statuses()
    queryset = list_available_shows().filter(vendor_id=vendor_id, movie_id=movie_id)
    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(vendor__city__iexact=normalized_city)
    return queryset.values_list("show_date", flat=True).distinct().order_by("show_date")


def list_show_times_for_vendor_movie_date(
    vendor_id: int,
    movie_id: int,
    show_date,
    city: Optional[str] = None,
):
    """Return distinct show start times for a vendor + movie + date, optionally city-scoped."""
    sync_show_lifecycle_statuses()
    queryset = list_available_shows().filter(
        vendor_id=vendor_id,
        movie_id=movie_id,
        show_date=show_date,
    )
    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(vendor__city__iexact=normalized_city)
    return queryset.values_list("start_time", flat=True).distinct().order_by("start_time")


def list_movies(include_unapproved: bool = False):
    """Return movies with genres prefetched."""
    queryset = Movie.objects.prefetch_related("genres")
    if not include_unapproved:
        queryset = queryset.filter(is_approved=True)
    return queryset.all().order_by("-created_at")


def get_movie(movie_id: int, include_unapproved: bool = False) -> Optional[Movie]:
    """Return a movie by ID or None."""
    try:
        queryset = Movie.objects.all()
        if not include_unapproved:
            queryset = queryset.filter(is_approved=True)
        return queryset.get(pk=movie_id)
    except Movie.DoesNotExist:
        return None


def get_movie_by_slug(slug: str, include_unapproved: bool = False) -> Optional[Movie]:
    """Return a movie by slug or None."""
    try:
        queryset = Movie.objects.all()
        if not include_unapproved:
            queryset = queryset.filter(is_approved=True)
        return queryset.get(slug=slug)
    except Movie.DoesNotExist:
        return None


def list_trailers_payload(request: Optional[Any] = None) -> list[dict[str, Any]]:
    """Build payload data for movies that have trailers."""
    payload: list[dict[str, Any]] = []
    for movie in list_movies():
        trailer_urls = [
            str(item or "").strip()
            for item in (movie.trailer_urls or [])
            if str(item or "").strip()
        ]
        if movie.trailer_url and movie.trailer_url not in trailer_urls:
            trailer_urls.insert(0, movie.trailer_url)
        if not trailer_urls:
            continue

        for index, trailer_url in enumerate(trailer_urls):
            youtube_id = extract_youtube_id(trailer_url)

            thumbnail_url = None
            if youtube_id:
                thumbnail_url = YOUTUBE_THUMBNAIL_TEMPLATE.format(youtube_id=youtube_id)
            if not thumbnail_url:
                thumbnail_url = build_media_url(request, getattr(movie, "banner_image", None))
            if not thumbnail_url:
                thumbnail_url = build_media_url(request, getattr(movie, "poster_image", None))
            if not thumbnail_url and movie.poster_url:
                thumbnail_url = movie.poster_url

            payload.append(
                {
                    "id": f"{movie.id}-{index + 1}",
                    "movie_id": movie.id,
                    "title": movie.title,
                    "youtube_url": trailer_url,
                    "youtube_id": youtube_id,
                    "thumbnail_url": thumbnail_url,
                    "duration_label": movie.duration or "",
                    "trailer_index": index + 1,
                    "trailer_count": len(trailer_urls),
                }
            )
    return payload


def compute_listing_status(movie: Movie) -> Optional[str]:
    """Compute listing status for a movie based on show statuses."""
    statuses = list(
        movie.shows.values_list("listing_status", flat=True).order_by("listing_status")
    )
    if any(str(status).lower().startswith("now") for status in statuses):
        return LISTING_STATUS_NOW
    if any(str(status).lower().startswith("coming") for status in statuses):
        return LISTING_STATUS_COMING
    return None


def _build_movie_audit_payload(movie: Movie) -> dict[str, Any]:
    """Build moderation metadata for backoffice movie responses."""
    return {
        "approvalStatus": getattr(movie, "approval_status", None),
        "approvalReason": getattr(movie, "approval_reason", None),
        "approvalMetadata": getattr(movie, "approval_metadata", {}) or {},
        "approvedAt": movie.approved_at.isoformat() if getattr(movie, "approved_at", None) else None,
        "approvedBy": getattr(movie.approved_by, "id", None) if getattr(movie, "approved_by", None) else None,
    }


def build_movie_payload(movie: Movie, listing_status: Optional[str] = None, request: Optional[Any] = None) -> dict[str, Any]:
    """Build the public payload for a movie."""
    banner_url = build_media_url(request, getattr(movie, "banner_image", None))
    poster_image_url = build_media_url(request, getattr(movie, "poster_image", None))

    genre_list = list(movie.genres.all()) if hasattr(movie, "genres") else []
    genres_payload = [
        {"id": genre.id, "name": genre.name, "slug": genre.slug}
        for genre in genre_list
    ]

    genre_text = movie.genre
    if not genre_text and genres_payload:
        genre_text = ", ".join(item["name"] for item in genres_payload if item.get("name"))

    short_desc = movie.short_description or movie.description or ""
    long_desc = movie.long_description or movie.description or ""
    trailer_urls = [
        str(item or "").strip()
        for item in (movie.trailer_urls or [])
        if str(item or "").strip()
    ]
    if movie.trailer_url and movie.trailer_url not in trailer_urls:
        trailer_urls.insert(0, movie.trailer_url)

    return {
        "id": movie.id,
        "slug": movie.slug,
        "title": movie.title,
        "shortDescription": short_desc,
        "description": long_desc,
        "language": movie.language,
        "genre": genre_text,
        "genres": genres_payload,
        "duration": movie.duration,
        "durationMinutes": movie.duration_minutes,
        "rating": movie.rating,
        "releaseDate": movie.release_date.isoformat() if movie.release_date else None,
        "posterImage": poster_image_url,
        "bannerImage": banner_url,
        "posterUrl": movie.poster_url,
        "trailerUrl": trailer_urls[0] if trailer_urls else movie.trailer_url,
        "trailerUrls": trailer_urls,
        "status": movie.status,
        "listingStatus": listing_status or movie.status,
        "averageRating": float(movie.average_rating or 0),
        "reviewCount": movie.review_count or 0,
        "isActive": movie.is_active,
        "isApproved": movie.is_approved,
        "createdAt": movie.created_at.isoformat() if movie.created_at else None,
        "updatedAt": movie.updated_at.isoformat() if movie.updated_at else None,
    }


def build_movie_backoffice_payload(
    movie: Movie,
    listing_status: Optional[str] = None,
    request: Optional[Any] = None,
) -> dict[str, Any]:
    """Build the vendor/admin payload for a movie with moderation metadata."""
    payload = build_movie_payload(movie, listing_status=listing_status, request=request)
    payload.update(_build_movie_audit_payload(movie))
    return payload


def build_movie_vendor_payload(
    movie: Movie,
    listing_status: Optional[str] = None,
    request: Optional[Any] = None,
) -> dict[str, Any]:
    """Build the vendor-facing payload for a movie."""
    return build_movie_backoffice_payload(movie, listing_status=listing_status, request=request)


def build_movie_admin_payload(
    movie: Movie,
    listing_status: Optional[str] = None,
    request: Optional[Any] = None,
) -> dict[str, Any]:
    """Build the admin-facing payload for a movie."""
    return build_movie_backoffice_payload(movie, listing_status=listing_status, request=request)


def build_movie_select_payload(movie: Movie) -> dict[str, Any]:
    """Build a minimal movie payload for selection lists."""
    return {"id": movie.id, "title": movie.title}


def list_movies_payload(
    request: Optional[Any] = None,
    *,
    include_all: bool = False,
    city: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return movie payloads with listing status for each movie."""
    queryset = list_movies(include_unapproved=include_all)
    if not include_all:
        # Customer catalog should include any movie that has at least one show,
        # even if the movie-level active flag is off.
        queryset = queryset.filter(shows__isnull=False).distinct()

    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(shows__vendor__city__iexact=normalized_city).distinct()

    if include_all and request is not None and is_admin_request(request):
        payload_builder = build_movie_admin_payload
    elif include_all and request is not None and is_vendor_request(request):
        payload_builder = build_movie_vendor_payload
    else:
        payload_builder = build_movie_payload
    payload: list[dict[str, Any]] = []
    for movie in queryset:
        listing = compute_listing_status(movie)
        payload.append(payload_builder(movie, listing, request=request))
    return payload


def list_movie_credits(movie: Movie):
    """Return movie credits with related person data."""
    return MovieCredit.objects.select_related("person").filter(movie=movie).order_by(
        "position", "id"
    )


def list_movie_reviews(movie: Movie):
    """Return approved reviews for a movie."""
    return Review.objects.select_related("user").filter(
        movie=movie, is_approved=True
    ).order_by("-created_at")


def build_movie_detail_payload(
    movie: Movie,
    request: Optional[Any] = None,
    *,
    include_audit: bool = False,
) -> dict[str, Any]:
    """Build the movie detail payload including credits and reviews."""
    base = build_movie_payload(movie, listing_status=None, request=request)
    if include_audit:
        base.update(_build_movie_audit_payload(movie))
    credits = list_movie_credits(movie)

    cast: list[dict[str, Any]] = []
    crew: list[dict[str, Any]] = []
    for credit in credits:
        person = credit.person
        person_photo = build_media_url(request, getattr(person, "photo", None))
        payload = {
            "id": credit.id,
            "roleType": credit.role_type,
            "characterName": credit.character_name,
            "jobTitle": credit.job_title,
            "position": credit.position,
            # Backwards-compatible keys
            "creditType": credit.role_type,
            "roleName": credit.character_name,
            "department": credit.job_title,
            "order": credit.position,
            "person": {
                "id": person.id,
                "fullName": person.full_name,
                "slug": person.slug,
                "photo": person_photo or person.photo_url,
                "nationality": person.nationality,
            },
        }
        if credit.role_type == MovieCredit.ROLE_CAST:
            cast.append(payload)
        else:
            crew.append(payload)

    reviews_payload: list[dict[str, Any]] = []
    for review in list_movie_reviews(movie):
        user = review.user
        user_name = ""
        if user:
            user_name = user.first_name or user.email or str(user.id)
        reviews_payload.append(
            {
                "id": review.id,
                "userId": review.user_id,
                "userName": user_name,
                "rating": review.rating,
                "comment": review.comment,
                "createdAt": review.created_at.isoformat() if review.created_at else None,
            }
        )

    base.update({"cast": cast, "crew": crew, "reviews": reviews_payload})
    return base


def list_shows(
    request: Optional[Any] = None,
    movie_id: Optional[int] = None,
    vendor_id: Optional[int] = None,
    city: Optional[str] = None,
):
    """Return shows scoped by vendor and/or movie filters."""
    sync_show_lifecycle_statuses()
    queryset = Show.objects.select_related("movie", "vendor").order_by(
        "-show_date", "-start_time"
    )
    queryset = queryset.exclude(status__iexact=SHOW_STATUS_COMPLETED)
    dashboard_scope = bool(
        request is not None and (is_admin_request(request) or is_vendor_request(request))
    )

    vendor = resolve_vendor(request) if request is not None else None
    if vendor:
        queryset = queryset.filter(vendor_id=vendor.id)
    elif vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

    if not dashboard_scope:
        queryset = queryset.exclude(status__iexact=SHOW_STATUS_RUNNING)

    if movie_id:
        queryset = queryset.filter(movie_id=movie_id)

    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(vendor__city__iexact=normalized_city)

    return queryset


def get_show(show_id: int) -> Optional[Show]:
    """Return a show by ID or None."""
    try:
        return Show.objects.get(pk=show_id)
    except Show.DoesNotExist:
        return None


def build_show_payload(
    show: Show,
    *,
    running_status_label: Optional[str] = None,
) -> dict[str, Any]:
    """Build the payload for a show listing."""
    lifecycle = get_show_lifecycle_state(show)
    status_value = lifecycle["status"]
    if status_value == SHOW_STATUS_RUNNING and running_status_label:
        status_value = str(running_status_label).strip() or status_value
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
        "status": status_value,
        "listingStatus": show.listing_status,
        "bookingOpen": bool(lifecycle["booking_open"]),
        "bookingCloseAt": lifecycle["booking_close_at"].isoformat()
        if lifecycle.get("booking_close_at")
        else None,
        "startAt": lifecycle["start_at"].isoformat() if lifecycle.get("start_at") else None,
        "endAt": lifecycle["end_at"].isoformat() if lifecycle.get("end_at") else None,
        "city": show.vendor.city if show.vendor else None,
        "theatre": show.vendor.theatre if show.vendor else None,
        "createdAt": show.created_at.isoformat() if show.created_at else None,
    }


def get_ticket(reference: str) -> Optional[Ticket]:
    """Return a ticket by reference or None."""
    raw_reference = str(reference or "").strip()
    if not raw_reference:
        return None

    _repair_malformed_ticket_uuid_rows()

    ticket = _get_ticket_by_reference_raw(raw_reference)
    if ticket:
        return ticket

    try:
        ticket = Ticket.objects.get(reference=raw_reference)
        return ticket
    except Ticket.DoesNotExist:
        pass
    except (TypeError, ValueError, ValidationError):
        Ticket.objects.filter(reference__iexact=raw_reference).update(ticket_id=uuid.uuid4())

    ticket = Ticket.objects.filter(reference__iexact=raw_reference).first()
    if ticket:
        return ticket

    ticket = (
        Ticket.objects.filter(payload__reference__iexact=raw_reference)
        .order_by("-id")
        .first()
    )
    if ticket:
        return ticket

    ticket = (
        Ticket.objects.filter(payload__payment__transaction_uuid=raw_reference)
        .order_by("-id")
        .first()
    )
    if ticket:
        return ticket

    try:
        ticket_uuid = uuid.UUID(raw_reference)
    except (TypeError, ValueError, AttributeError):
        return None

    return Ticket.objects.filter(ticket_id=ticket_uuid).first()
