"""ViewSets for admin and public APIs."""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny

from .models import Movie, MovieCredit, Person, Review
from .permissions import (
    IsAdmin,
    IsAdminOrReadOnly,
    is_admin_request,
    resolve_customer,
)
from .serializers import (
    MovieAdminReadSerializer,
    MovieAdminWriteSerializer,
    MovieCreditSerializer,
    MovieCreditWriteSerializer,
    PersonSerializer,
    PersonWriteSerializer,
    ReviewSerializer,
    ReviewWriteSerializer,
)


class MovieAdminViewSet(viewsets.ModelViewSet):
    """Admin CRUD for movies."""

    queryset = Movie.objects.prefetch_related("genres", "credits__person").all()
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAdmin]

    def get_serializer_class(self):
        """Return the write serializer for mutations, read serializer otherwise."""
        if self.action in ("create", "update", "partial_update"):
            return MovieAdminWriteSerializer
        return MovieAdminReadSerializer


class PersonViewSet(viewsets.ModelViewSet):
    """Admin CRUD for people with read-only access for non-admins."""

    queryset = Person.objects.all().order_by("full_name")
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        """Return the write serializer for mutations, read serializer otherwise."""
        if self.action in ("create", "update", "partial_update"):
            return PersonWriteSerializer
        return PersonSerializer


class MovieCreditViewSet(viewsets.ModelViewSet):
    """Admin CRUD for movie credits."""

    queryset = MovieCredit.objects.select_related("movie", "person").all().order_by(
        "position", "id"
    )
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        """Return the write serializer for mutations, read serializer otherwise."""
        if self.action in ("create", "update", "partial_update"):
            return MovieCreditWriteSerializer
        return MovieCreditSerializer

    def get_queryset(self):
        """Optionally filter credits by movie and role type."""
        qs = super().get_queryset()
        movie_id = self.request.query_params.get("movie") or self.request.query_params.get(
            "movie_id"
        )
        role_type = self.request.query_params.get("role_type")
        if movie_id:
            qs = qs.filter(movie_id=movie_id)
        if role_type:
            qs = qs.filter(role_type=role_type)
        return qs


class ReviewViewSet(viewsets.ModelViewSet):
    """Review CRUD; public read/create with admin-only updates/deletes."""

    queryset = Review.objects.select_related("movie", "user").all().order_by("-created_at")
    parser_classes = [FormParser, JSONParser]

    def get_serializer_class(self):
        """Return the write serializer for mutations, read serializer otherwise."""
        if self.action in ("create", "update", "partial_update"):
            return ReviewWriteSerializer
        return ReviewSerializer

    def get_permissions(self):
        """Allow public reads and controlled writes based on actor identity."""
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [AllowAny()]

    def get_queryset(self):
        """Filter reviews by movie/user and respect approval status for non-admins."""
        qs = super().get_queryset()
        movie_id = self.request.query_params.get("movie") or self.request.query_params.get(
            "movie_id"
        )
        user_id = self.request.query_params.get("user") or self.request.query_params.get(
            "user_id"
        )
        if movie_id:
            qs = qs.filter(movie_id=movie_id)
        if user_id:
            qs = qs.filter(user_id=user_id)
        customer = resolve_customer(self.request)
        if not is_admin_request(self.request):
            visible_filter = Q(is_approved=True)
            if customer:
                visible_filter |= Q(user_id=customer.id)
            qs = qs.filter(visible_filter)
        return qs

    def _assert_owner_or_admin(self, review: Review) -> None:
        """Ensure only review owner (customer) or admin can mutate review."""
        if is_admin_request(self.request):
            return
        customer = resolve_customer(self.request)
        if not customer:
            raise PermissionDenied("Authentication required.")
        if review.user_id != customer.id:
            raise PermissionDenied("You can only modify your own review.")

    def perform_create(self, serializer):
        """Enforce unique user/movie reviews and customer ownership on create."""
        customer = resolve_customer(self.request)
        if not is_admin_request(self.request) and not customer:
            raise PermissionDenied("Authentication required.")

        movie = serializer.validated_data.get("movie")
        user = serializer.validated_data.get("user")
        if not is_admin_request(self.request):
            user = customer

        if movie and user and Review.objects.filter(movie=movie, user=user).exists():
            raise ValidationError("You have already reviewed this movie.")

        if is_admin_request(self.request):
            serializer.save()
            return
        serializer.save(user=user)

    def perform_update(self, serializer):
        """Allow updates only for review owner or admin."""
        review = serializer.instance
        self._assert_owner_or_admin(review)

        if is_admin_request(self.request):
            serializer.save()
            return

        serializer.save(
            user=review.user,
            movie=review.movie,
            is_approved=review.is_approved,
        )

    def perform_destroy(self, instance):
        """Allow deletion only for review owner or admin."""
        self._assert_owner_or_admin(instance)
        instance.delete()
