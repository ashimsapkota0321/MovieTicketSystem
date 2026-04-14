"""Authentication and profile-related API views."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone

from ..models import Admin, User, Vendor
from .. import services
from ..permissions import (
    admin_required,
    get_request_session_id,
    refresh_access_token,
    revoke_auth_session,
    revoke_refresh_token,
    vendor_required,
)


def _auth_cookie_enabled() -> bool:
    """Return True when cookie-based auth is enabled."""
    return bool(getattr(settings, "APP_AUTH_COOKIE_ENABLED", True))


def _cookie_name(kind: str) -> str:
    """Resolve configured cookie names for auth tokens."""
    if kind == "refresh":
        value = getattr(settings, "APP_AUTH_REFRESH_COOKIE_NAME", "mt_refresh_token")
        return str(value or "mt_refresh_token").strip() or "mt_refresh_token"
    value = getattr(settings, "APP_AUTH_ACCESS_COOKIE_NAME", "mt_access_token")
    return str(value or "mt_access_token").strip() or "mt_access_token"


def _cookie_common_options() -> dict[str, Any]:
    """Build shared cookie options from settings."""
    samesite = str(getattr(settings, "APP_AUTH_COOKIE_SAMESITE", "Lax") or "Lax").capitalize()
    if samesite not in {"Lax", "Strict", "None"}:
        samesite = "Lax"
    return {
        "httponly": True,
        "secure": bool(getattr(settings, "APP_AUTH_COOKIE_SECURE", False)),
        "samesite": samesite,
        "path": str(getattr(settings, "APP_AUTH_COOKIE_PATH", "/") or "/"),
        "domain": getattr(settings, "APP_AUTH_COOKIE_DOMAIN", None) or None,
    }


def _set_auth_cookies(response: Response, payload: dict[str, Any]) -> None:
    """Persist access/refresh tokens in HttpOnly cookies."""
    if not _auth_cookie_enabled() or not isinstance(payload, dict):
        return
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        return

    options = _cookie_common_options()
    response.set_cookie(
        _cookie_name("access"),
        access_token,
        max_age=max(int(getattr(settings, "APP_AUTH_ACCESS_TOKEN_MAX_AGE_SECONDS", 60 * 15)), 60),
        **options,
    )
    response.set_cookie(
        _cookie_name("refresh"),
        refresh_token,
        max_age=max(int(getattr(settings, "APP_AUTH_REFRESH_TOKEN_MAX_AGE_SECONDS", 60 * 60 * 24 * 30)), 60),
        **options,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear auth cookies from the client."""
    if not _auth_cookie_enabled():
        return
    options = _cookie_common_options()
    response.delete_cookie(_cookie_name("access"), path=options["path"], domain=options["domain"], samesite=options["samesite"])
    response.delete_cookie(_cookie_name("refresh"), path=options["path"], domain=options["domain"], samesite=options["samesite"])


def _resolve_refresh_token(request: Any) -> str:
    """Resolve refresh token from request body first, then cookie."""
    body_token = request.data.get("refresh_token") or request.data.get("refreshToken")
    if body_token:
        return str(body_token).strip()
    try:
        cookies = getattr(request, "COOKIES", {}) or {}
    except Exception:
        cookies = {}
    return str(cookies.get(_cookie_name("refresh")) or "").strip()


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
                "optional_fields": [
                    "referral_code",
                    "device_fingerprint",
                ],
                "prerequisite": "Verify email via /api/auth/register/request-otp/ and /api/auth/register/verify-otp/ before POST register.",
            },
            status=status.HTTP_200_OK,
        )

    payload, status_code = services.register_user(request)
    return Response(payload, status=status_code)


@api_view(["POST"])
def register_request_otp(request: Any):
    """Send registration OTP to an email address."""
    payload, status_code = services.request_registration_otp(request.data.get("email"))
    return Response(payload, status=status_code)


@api_view(["POST"])
def register_verify_otp(request: Any):
    """Verify registration OTP for an email address."""
    payload, status_code = services.verify_registration_otp(
        request.data.get("email"),
        request.data.get("otp"),
    )
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
                "response_fields": ["access_token", "refresh_token", "session_id", "expires_in", "refresh_expires_in"],
            },
            status=status.HTTP_200_OK,
        )

    payload, status_code = services.login_user(request)
    response = Response(payload, status=status_code)
    if status_code == status.HTTP_200_OK:
        _set_auth_cookies(response, payload if isinstance(payload, dict) else {})
    return response


@api_view(["POST"])
def refresh(request: Any):
    """Refresh an auth session using a refresh token."""
    refresh_token = _resolve_refresh_token(request)
    payload = refresh_access_token(refresh_token)
    if not payload:
        response = Response({"message": "Invalid or expired refresh token"}, status=status.HTTP_401_UNAUTHORIZED)
        _clear_auth_cookies(response)
        return response
    session = payload.pop("session")
    response_payload = {
        **payload,
        "session_id": str(session.session_id),
        "expires_in": max(int((session.access_expires_at - timezone.now()).total_seconds()), 0),
        "refresh_expires_in": max(int((session.refresh_expires_at - timezone.now()).total_seconds()), 0),
    }
    response = Response(response_payload, status=status.HTTP_200_OK)
    _set_auth_cookies(response, response_payload)
    return response


@api_view(["POST"])
def logout(request: Any):
    """Revoke the current auth session."""
    refresh_token = _resolve_refresh_token(request)
    if refresh_token and revoke_refresh_token(refresh_token):
        response = Response({"message": "Logged out successfully"}, status=status.HTTP_200_OK)
        _clear_auth_cookies(response)
        return response

    session_id = get_request_session_id(request)
    if session_id and revoke_auth_session(session_id):
        response = Response({"message": "Logged out successfully"}, status=status.HTTP_200_OK)
        _clear_auth_cookies(response)
        return response

    response = Response({"message": "Session not found or already revoked"}, status=status.HTTP_404_NOT_FOUND)
    _clear_auth_cookies(response)
    return response


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
