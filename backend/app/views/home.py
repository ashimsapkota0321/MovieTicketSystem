"""Homepage and public display API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import Movie
from ..serializers import (
    BannerListSerializer,
    CollaboratorSerializer,
    HomeSlidePublicSerializer,
    NowShowingHeroMovieSerializer,
)
from .. import selectors


@api_view(["GET"])
def home_slides(request: Any):
    """Return active home slides."""
    slides = selectors.list_active_home_slides()
    serializer = HomeSlidePublicSerializer(slides, many=True, context={"request": request})
    return Response({"slides": serializer.data}, status=status.HTTP_200_OK)


@api_view(["GET"])
def home_now_showing_slides(request: Any):
    """Return now showing movie slides for the homepage hero."""
    movies = (
        Movie.objects.filter(
            status=Movie.STATUS_NOW_SHOWING,
            is_active=True,
            is_approved=True,
        )
        .order_by("-updated_at", "-created_at")
    )
    serializer = NowShowingHeroMovieSerializer(
        movies, many=True, context={"request": request}
    )
    return Response({"slides": serializer.data}, status=status.HTTP_200_OK)


@api_view(["GET"])
def home_collaborators(request: Any):
    """Return active collaborator logos."""
    collaborators = selectors.list_active_collaborators()
    serializer = CollaboratorSerializer(
        collaborators, many=True, context={"request": request}
    )
    return Response({"collaborators": serializer.data}, status=status.HTTP_200_OK)


@api_view(["GET"])
def banners(request: Any):
    """Return active banners for public display."""
    page = request.query_params.get("page") or request.query_params.get("display_on")
    banners_qs = selectors.list_active_banners(page)
    serializer = BannerListSerializer(banners_qs, many=True, context={"request": request})
    return Response({"banners": serializer.data}, status=status.HTTP_200_OK)


@api_view(["GET"])
def active_banners(request: Any):
    """Return active banners for public display."""
    page = request.query_params.get("page") or request.query_params.get("display_on")
    banners_qs = selectors.list_active_banners(page)
    serializer = BannerListSerializer(banners_qs, many=True, context={"request": request})
    return Response({"banners": serializer.data}, status=status.HTTP_200_OK)
