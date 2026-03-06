"""Authentication and profile-related API views."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..models import Admin, User, Vendor
from .. import services
from ..permissions import admin_required, vendor_required


@api_view(["GET", "POST"])
def register(request: Any):
    """Register a new user or describe required fields."""
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

    payload, status_code = services.register_user(request)
    return Response(payload, status=status_code)


@api_view(["GET", "POST"])
def login(request: Any):
    """Authenticate a user, vendor, or admin."""
    if request.method == "GET":
        return Response(
            {
                "message": "Login endpoint",
                "method": "POST",
                "required_fields": ["email_or_phone", "password"],
            },
            status=status.HTTP_200_OK,
        )

    payload, status_code = services.login_user(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
def forgot_password(request: Any):
    """Send a password reset OTP."""
    payload, status_code = services.request_password_otp(request.data.get("email"))
    return Response(payload, status=status_code)


@api_view(["POST"])
def verify_otp(request: Any):
    """Verify a password reset OTP."""
    payload, status_code = services.verify_password_otp(
        request.data.get("email"), request.data.get("otp")
    )
    return Response(payload, status=status_code)


@api_view(["POST"])
def reset_password(request: Any):
    """Reset password using OTP verification."""
    payload, status_code = services.reset_password_with_otp(
        request.data.get("email"),
        request.data.get("otp"),
        request.data.get("new_password"),
    )
    return Response(payload, status=status_code)


@api_view(["PATCH"])
def update_profile(request: Any, user_id: int):
    """Update a user's profile by ID."""
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.update_user_profile(request, user)
    return Response(payload, status=status_code)


@api_view(["PATCH"])
@admin_required
def update_admin_profile(request: Any, admin_id: int):
    """Update an admin's profile by ID."""
    try:
        admin_user = Admin.objects.get(pk=admin_id)
    except Admin.DoesNotExist:
        return Response({"message": "Admin not found"}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.update_admin_profile(request, admin_user)
    return Response(payload, status=status_code)


@api_view(["PATCH"])
@vendor_required
def update_vendor_profile(request: Any, vendor_id: int):
    """Update a vendor's profile by ID."""
    try:
        vendor_user = Vendor.objects.get(pk=vendor_id)
    except Vendor.DoesNotExist:
        return Response({"message": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

    payload, status_code = services.update_vendor_profile(request, vendor_user)
    return Response(payload, status=status_code)
