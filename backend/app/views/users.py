"""User administration API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from ..models import User
from ..permissions import admin_required
from .. import services


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def admin_users(request: Any):
    """List or create users for admin management."""
    if request.method == "GET":
        users = services.list_users_payload(request)
        return Response({"users": users}, status=status.HTTP_200_OK)

    payload, status_code = services.create_admin_user(request)
    return Response(payload, status=status_code)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@admin_required
def admin_user_detail(request: Any, user_id: int):
    """Retrieve, update, or delete a user by ID."""
    user = User.objects.filter(pk=user_id).first()
    if not user:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(
            {"user": services.build_user_payload(user, request)},
            status=status.HTTP_200_OK,
        )

    if request.method == "DELETE":
        user.delete()
        return Response({"message": "User deleted"}, status=status.HTTP_200_OK)

    payload, status_code = services.update_admin_user(user, request)
    return Response(payload, status=status_code)
