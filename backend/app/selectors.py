"""Query helpers and response payload builders."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

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
from .permissions import resolve_vendor
from .utils import build_media_url, extract_youtube_id

LISTING_STATUS_NOW = "Now Showing"
LISTING_STATUS_COMING = "Coming Soon"
YOUTUBE_THUMBNAIL_TEMPLATE = "https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg"
SHOW_STATUS_UPCOMING = Show.STATUS_UPCOMING
SHOW_STATUS_RUNNING = Show.STATUS_RUNNING
SHOW_STATUS_COMPLETED = Show.STATUS_COMPLETED
BOOKING_CLOSE_BEFORE_START_MINUTES = Show.BOOKING_CLOSE_BEFORE_START_MINUTES


def _combine_local_show_datetime(show_date, show_time):
    if not show_date or not show_time:
        return None
    combined = datetime.combine(show_date, show_time)
    now = timezone.now()
    if timezone.is_aware(now):
        return timezone.make_aware(combined, timezone.get_current_timezone())
    return combined


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
    now = now or timezone.now()
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
    now = now or timezone.now()
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
    now = now or timezone.now()
    cutoff = now + timedelta(minutes=BOOKING_CLOSE_BEFORE_START_MINUTES)
    return Show.objects.filter(_show_start_after(cutoff)).exclude(status__iexact=SHOW_STATUS_COMPLETED)


def list_booking_closed_shows(now: Optional[datetime] = None):
    now = now or timezone.now()
    cutoff = now + timedelta(minutes=BOOKING_CLOSE_BEFORE_START_MINUTES)
    return Show.objects.filter(_show_start_before_or_at(cutoff)).filter(_show_start_after(now)).exclude(
        status__iexact=SHOW_STATUS_COMPLETED
    )


def list_running_shows(now: Optional[datetime] = None):
    now = now or timezone.now()
    return Show.objects.filter(_show_start_before_or_at(now)).exclude(_show_end_before_or_at(now))


def list_completed_shows(now: Optional[datetime] = None):
    now = now or timezone.now()
    return Show.objects.filter(_show_end_before_or_at(now))


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


def list_movies():
    """Return all movies with genres prefetched."""
    return Movie.objects.prefetch_related("genres").all().order_by("-created_at")


def get_movie(movie_id: int) -> Optional[Movie]:
    """Return a movie by ID or None."""
    try:
        return Movie.objects.get(pk=movie_id)
    except Movie.DoesNotExist:
        return None


def get_movie_by_slug(slug: str) -> Optional[Movie]:
    """Return a movie by slug or None."""
    try:
        return Movie.objects.get(slug=slug)
    except Movie.DoesNotExist:
        return None


def list_trailers_payload(request: Optional[Any] = None) -> list[dict[str, Any]]:
    """Build payload data for movies that have trailers."""
    payload: list[dict[str, Any]] = []
    for movie in list_movies():
        if not movie.trailer_url:
            continue
        youtube_id = extract_youtube_id(movie.trailer_url)

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
                "id": movie.id,
                "title": movie.title,
                "youtube_url": movie.trailer_url,
                "youtube_id": youtube_id,
                "thumbnail_url": thumbnail_url,
                "duration_label": movie.duration or "",
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
        "trailerUrl": movie.trailer_url,
        "status": movie.status,
        "listingStatus": listing_status or movie.status,
        "averageRating": float(movie.average_rating or 0),
        "reviewCount": movie.review_count or 0,
        "isActive": movie.is_active,
        "createdAt": movie.created_at.isoformat() if movie.created_at else None,
        "updatedAt": movie.updated_at.isoformat() if movie.updated_at else None,
    }


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
    queryset = list_movies()
    if not include_all:
        # Customer catalog should include any movie that has at least one show,
        # even if the movie-level active flag is off.
        queryset = queryset.filter(shows__isnull=False).distinct()

    normalized_city = normalize_city(city)
    if normalized_city:
        queryset = queryset.filter(shows__vendor__city__iexact=normalized_city).distinct()

    payload: list[dict[str, Any]] = []
    for movie in queryset:
        listing = compute_listing_status(movie)
        payload.append(build_movie_payload(movie, listing, request=request))
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


def build_movie_detail_payload(movie: Movie, request: Optional[Any] = None) -> dict[str, Any]:
    """Build the movie detail payload including credits and reviews."""
    base = build_movie_payload(movie, listing_status=None, request=request)
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

    vendor = resolve_vendor(request) if request is not None else None
    if vendor:
        queryset = queryset.filter(vendor_id=vendor.id)
    elif vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

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


def build_show_payload(show: Show) -> dict[str, Any]:
    """Build the payload for a show listing."""
    lifecycle = get_show_lifecycle_state(show)
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
        "status": lifecycle["status"],
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
    try:
        return Ticket.objects.get(reference=reference)
    except Ticket.DoesNotExist:
        return None
