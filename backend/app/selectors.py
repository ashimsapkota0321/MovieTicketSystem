"""Query helpers and response payload builders."""

from __future__ import annotations

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


def list_cinema_vendors():
    """Return active, non-blocked vendors for cinema listings."""
    return (
        Vendor.objects.filter(is_active=True)
        .exclude(status__iexact="blocked")
        .order_by("name", "id")
    )


def list_movies_with_shows():
    """Return movies that currently have at least one show."""
    return Movie.objects.filter(shows__isnull=False).distinct().order_by("title", "id")


def list_movies_for_vendor(vendor_id: int):
    """Return movies that have shows for a specific vendor."""
    return (
        Movie.objects.filter(shows__vendor_id=vendor_id).distinct().order_by("title", "id")
    )


def list_vendors_for_movie(movie_id: int):
    """Return vendors that have shows for a specific movie."""
    return (
        Vendor.objects.filter(shows__movie_id=movie_id).distinct().order_by("name", "id")
    )


def list_show_dates_for_vendor_movie(vendor_id: int, movie_id: int):
    """Return distinct show dates for a vendor + movie pair."""
    return (
        Show.objects.filter(vendor_id=vendor_id, movie_id=movie_id)
        .values_list("show_date", flat=True)
        .distinct()
        .order_by("show_date")
    )


def list_show_times_for_vendor_movie_date(vendor_id: int, movie_id: int, show_date):
    """Return distinct show start times for a vendor + movie + date."""
    return (
        Show.objects.filter(vendor_id=vendor_id, movie_id=movie_id, show_date=show_date)
        .values_list("start_time", flat=True)
        .distinct()
        .order_by("start_time")
    )


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
        if not youtube_id:
            continue

        thumbnail_url = build_media_url(request, getattr(movie, "banner_image", None))
        if not thumbnail_url and movie.poster_url:
            thumbnail_url = movie.poster_url
        if not thumbnail_url:
            thumbnail_url = YOUTUBE_THUMBNAIL_TEMPLATE.format(youtube_id=youtube_id)

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


def list_movies_payload(request: Optional[Any] = None) -> list[dict[str, Any]]:
    """Return movie payloads with listing status for each movie."""
    payload: list[dict[str, Any]] = []
    for movie in list_movies():
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


def list_shows(request: Optional[Any] = None, movie_id: Optional[int] = None, vendor_id: Optional[int] = None):
    """Return shows scoped by vendor and/or movie filters."""
    queryset = Show.objects.select_related("movie", "vendor").order_by(
        "-show_date", "-start_time"
    )

    vendor = resolve_vendor(request) if request is not None else None
    if vendor:
        queryset = queryset.filter(vendor_id=vendor.id)
    elif vendor_id:
        queryset = queryset.filter(vendor_id=vendor_id)

    if movie_id:
        queryset = queryset.filter(movie_id=movie_id)

    return queryset


def get_show(show_id: int) -> Optional[Show]:
    """Return a show by ID or None."""
    try:
        return Show.objects.get(pk=show_id)
    except Show.DoesNotExist:
        return None


def build_show_payload(show: Show) -> dict[str, Any]:
    """Build the payload for a show listing."""
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


def get_ticket(reference: str) -> Optional[Ticket]:
    """Return a ticket by reference or None."""
    try:
        return Ticket.objects.get(reference=reference)
    except Ticket.DoesNotExist:
        return None
