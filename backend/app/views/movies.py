"""Movie, trailer, person, and review API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import Person, Review
from ..serializers import ReviewWriteSerializer
from .. import selectors, services, permissions
from ..utils import build_media_url, coalesce


@api_view(["GET", "POST"])
def movies(request: Any):
    """List or create movies."""
    if request.method == "GET":
        include_all = permissions.is_admin_request(request) or permissions.is_vendor_request(
            request
        )
        # Admin/vendor catalogs should not be narrowed by customer city selection.
        city = None if include_all else coalesce(request.query_params, "city", "location")
        payload = selectors.list_movies_payload(
            request,
            include_all=include_all,
            city=city,
        )
        return Response({"movies": payload}, status=status.HTTP_200_OK)

    payload, status_code = services.create_movie(request)
    return Response(payload, status=status_code)


@api_view(["GET"])
def trailers(request: Any):
    """Return trailer payloads."""
    payload = selectors.list_trailers_payload(request=request)
    return Response({"trailers": payload}, status=status.HTTP_200_OK)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def movie_detail(request: Any, movie_id: int):
    """Retrieve, update, or delete a movie by ID."""
    movie = selectors.get_movie(movie_id)
    if not movie:
        return Response({"message": "Movie not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        payload = selectors.build_movie_detail_payload(movie, request=request)
        return Response({"movie": payload}, status=status.HTTP_200_OK)

    if request.method == "DELETE":
        payload, status_code = services.delete_movie(request, movie)
        return Response(payload, status=status_code)

    payload, status_code = services.update_movie(request, movie)
    return Response(payload, status=status_code)


@api_view(["GET"])
def movie_detail_by_slug(request: Any, slug: str):
    """Retrieve a movie by its slug."""
    movie = selectors.get_movie_by_slug(slug)
    if not movie:
        return Response({"message": "Movie not found"}, status=status.HTTP_404_NOT_FOUND)
    payload = selectors.build_movie_detail_payload(movie, request=request)
    return Response({"movie": payload}, status=status.HTTP_200_OK)


@api_view(["POST"])
def movie_reviews(request: Any, movie_id: int):
    """Create a movie review."""
    movie = selectors.get_movie(movie_id)
    if not movie:
        return Response({"message": "Movie not found"}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
    payload["movie"] = movie.id
    if "user" not in payload:
        payload["user"] = payload.get("user_id") or payload.get("userId")
    serializer = ReviewWriteSerializer(data=payload, context={"request": request})
    if not serializer.is_valid():
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = serializer.validated_data.get("user")
        if Review.objects.filter(movie=movie, user=user).exists():
            return Response(
                {"message": "You have already reviewed this movie."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save(movie=movie)
    except Exception as exc:
        return Response(
            {"message": "Unable to save review", "error": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    payload = selectors.build_movie_detail_payload(movie, request=request)
    return Response({"movie": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def person_detail(request: Any, slug: str):
    """Return details for a person by slug."""
    person = Person.objects.prefetch_related(
        "credits__movie",
        "credits__movie__genres",
    ).filter(slug=slug).first()
    if not person:
        return Response({"message": "Person not found"}, status=status.HTTP_404_NOT_FOUND)

    credits = person.credits.select_related("movie").all().order_by("position", "id")
    filmography = []
    for credit in credits:
        movie = credit.movie
        filmography.append(
            {
                "movieId": movie.id,
                "movieSlug": movie.slug,
                "movieTitle": movie.title,
                "posterImage": build_media_url(
                    request, getattr(movie, "poster_image", None)
                ),
                "bannerImage": build_media_url(
                    request, getattr(movie, "banner_image", None)
                ),
                "roleType": credit.role_type,
                "characterName": credit.character_name,
                "jobTitle": credit.job_title,
                "position": credit.position,
                "creditType": credit.role_type,
                "roleName": credit.character_name,
                "department": credit.job_title,
            }
        )

    payload = {
        "id": person.id,
        "fullName": person.full_name,
        "slug": person.slug,
        "photo": build_media_url(request, getattr(person, "photo", None))
        or person.photo_url,
        "bio": person.bio,
        "dateOfBirth": person.date_of_birth.isoformat()
        if person.date_of_birth
        else None,
        "nationality": person.nationality,
        "instagram": person.instagram,
        "imdb": person.imdb,
        "facebook": person.facebook,
        "filmography": filmography,
    }
    return Response({"person": payload}, status=status.HTTP_200_OK)
