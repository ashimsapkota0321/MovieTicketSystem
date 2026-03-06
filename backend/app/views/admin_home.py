"""Admin views for banners, home slides, and collaborators."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from ..permissions import IsSuperAdmin, admin_required
from ..serializers import (
    BannerListSerializer,
    CollaboratorAdminSerializer,
    HomeSlideAdminSerializer,
)
from .. import selectors, services


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def admin_banners(request: Any):
    """List or create banners for admin management."""
    if request.method == "GET":
        banners_qs = selectors.list_banners()
        serializer = BannerListSerializer(banners_qs, many=True, context={"request": request})
        return Response({"banners": serializer.data}, status=status.HTTP_200_OK)

    banner = services.create_banner(request.data)
    response = BannerListSerializer(banner, context={"request": request}).data
    return Response({"banner": response}, status=status.HTTP_201_CREATED)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def admin_banner_detail(request: Any, banner_id: int):
    """Retrieve, update, or delete a banner by ID."""
    banner = selectors.get_banner(banner_id)
    if not banner:
        return Response({"message": "Banner not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        response = BannerListSerializer(banner, context={"request": request}).data
        return Response({"banner": response}, status=status.HTTP_200_OK)

    if request.method == "DELETE":
        banner.delete()
        return Response({"message": "Banner deleted"}, status=status.HTTP_200_OK)

    banner = services.update_banner(banner, request.data)
    response = BannerListSerializer(banner, context={"request": request}).data
    return Response({"banner": response}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_home_slides(request: Any):
    """Create a home slide (super admin only)."""
    slide = services.create_home_slide(request.data)
    response = HomeSlideAdminSerializer(slide).data
    return Response({"slide": response}, status=status.HTTP_201_CREATED)


@api_view(["PUT", "DELETE"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_home_slide_detail(request: Any, slide_id: int):
    """Update or delete a home slide (super admin only)."""
    slide = selectors.get_home_slide(slide_id)
    if not slide:
        return Response({"message": "Slide not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        slide.delete()
        return Response({"message": "Slide deleted"}, status=status.HTTP_200_OK)

    slide = services.update_home_slide(slide, request.data)
    response = HomeSlideAdminSerializer(slide).data
    return Response({"slide": response}, status=status.HTTP_200_OK)


@api_view(["PATCH"])
@permission_classes([IsSuperAdmin])
def admin_home_slide_toggle(request: Any, slide_id: int):
    """Toggle the active state for a home slide."""
    slide = selectors.get_home_slide(slide_id)
    if not slide:
        return Response({"message": "Slide not found"}, status=status.HTTP_404_NOT_FOUND)

    slide = services.toggle_home_slide(slide)
    return Response(
        {"id": slide.id, "is_active": slide.is_active}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_collaborators(request: Any):
    """Create a collaborator (super admin only)."""
    collaborator = services.create_collaborator(request.data)
    return Response(
        {"collaborator": CollaboratorAdminSerializer(collaborator).data},
        status=status.HTTP_201_CREATED,
    )


@api_view(["PUT", "DELETE"])
@permission_classes([IsSuperAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def admin_collaborator_detail(request: Any, collaborator_id: int):
    """Update or delete a collaborator (super admin only)."""
    collaborator = selectors.get_collaborator(collaborator_id)
    if not collaborator:
        return Response(
            {"message": "Collaborator not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "DELETE":
        collaborator.delete()
        return Response({"message": "Collaborator deleted"}, status=status.HTTP_200_OK)

    collaborator = services.update_collaborator(collaborator, request.data)
    return Response(
        {"collaborator": CollaboratorAdminSerializer(collaborator).data},
        status=status.HTTP_200_OK,
    )


@api_view(["PATCH"])
@permission_classes([IsSuperAdmin])
def admin_collaborator_toggle(request: Any, collaborator_id: int):
    """Toggle the active state for a collaborator."""
    collaborator = selectors.get_collaborator(collaborator_id)
    if not collaborator:
        return Response(
            {"message": "Collaborator not found"}, status=status.HTTP_404_NOT_FOUND
        )

    collaborator = services.toggle_collaborator(collaborator)
    return Response(
        {"id": collaborator.id, "is_active": collaborator.is_active},
        status=status.HTTP_200_OK,
    )
