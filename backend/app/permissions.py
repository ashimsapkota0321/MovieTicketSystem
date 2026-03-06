"""Custom permission helpers for admin/vendor access."""

from __future__ import annotations

from functools import wraps
from typing import Any, Optional

from django.conf import settings
from django.core import signing
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from .models import Admin, User, Vendor

ADMIN_REQUIRED_MESSAGE = "Admin access required."
SUPER_ADMIN_REQUIRED_MESSAGE = "Super admin access required."
AUTH_REQUIRED_MESSAGE = "Authentication required."
VENDOR_REQUIRED_MESSAGE = "Vendor access required."

ROLE_ADMIN = "admin"
ROLE_VENDOR = "vendor"
ROLE_CUSTOMER = "customer"
ROLE_CHOICES = {ROLE_ADMIN, ROLE_VENDOR, ROLE_CUSTOMER}
AUTH_TOKEN_SALT = "meroticket.auth.token.v1"
DEFAULT_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _token_max_age_seconds() -> int:
    """Return the configured auth token max age in seconds."""
    configured = getattr(
        settings, "APP_AUTH_TOKEN_MAX_AGE_SECONDS", DEFAULT_TOKEN_MAX_AGE_SECONDS
    )
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = DEFAULT_TOKEN_MAX_AGE_SECONDS
    return max(parsed, 60)


def issue_access_token(role: str, user_id: Any) -> str:
    """Issue a signed access token containing role and subject ID."""
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in ROLE_CHOICES:
        raise ValueError("Unsupported role")
    subject_id = int(user_id)
    payload = {"role": normalized_role, "user_id": subject_id}
    return signing.dumps(payload, salt=AUTH_TOKEN_SALT, compress=True)


def _extract_bearer_token(request: Any) -> str:
    """Extract Bearer token from Authorization header."""
    header = ""
    if hasattr(request, "META"):
        header = str(request.META.get("HTTP_AUTHORIZATION") or "").strip()
    if not header and hasattr(request, "headers"):
        header = str(request.headers.get("Authorization") or "").strip()
    if not header:
        return ""

    parts = header.split(None, 1)
    if len(parts) != 2:
        return ""
    if parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def _decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """Decode and validate a signed access token."""
    if not token:
        return None
    try:
        payload = signing.loads(
            token,
            salt=AUTH_TOKEN_SALT,
            max_age=_token_max_age_seconds(),
        )
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None

    if not isinstance(payload, dict):
        return None
    role = str(payload.get("role") or "").strip().lower()
    if role not in ROLE_CHOICES:
        return None
    try:
        user_id = int(payload.get("user_id"))
    except (TypeError, ValueError):
        return None
    if user_id <= 0:
        return None
    return {"role": role, "user_id": user_id}


def _identity_query(user: Any) -> Optional[Q]:
    """Build a lookup query for email/username/phone values on a user-like object."""
    email = getattr(user, "email", None)
    username = getattr(user, "username", None)
    phone = getattr(user, "phone_number", None)

    query = Q()
    if email:
        query |= Q(email__iexact=email)
    if username:
        query |= Q(username__iexact=username)
    if phone:
        query |= Q(phone_number=phone)

    return query if query else None


def _resolve_identity_from_token(token_payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve role objects using decoded token payload."""
    identity = {
        "role": None,
        "admin": None,
        "vendor": None,
        "customer": None,
    }
    role = token_payload.get("role")
    user_id = token_payload.get("user_id")
    if role == ROLE_ADMIN:
        admin = Admin.objects.filter(pk=user_id, is_active=True).first()
        if admin:
            identity["role"] = ROLE_ADMIN
            identity["admin"] = admin
    elif role == ROLE_VENDOR:
        vendor = (
            Vendor.objects.filter(pk=user_id, is_active=True)
            .exclude(status__iexact="blocked")
            .first()
        )
        if vendor:
            identity["role"] = ROLE_VENDOR
            identity["vendor"] = vendor
    elif role == ROLE_CUSTOMER:
        customer = User.objects.filter(pk=user_id, is_active=True).first()
        if customer:
            identity["role"] = ROLE_CUSTOMER
            identity["customer"] = customer
    return identity


def _resolve_identity_from_request_user(request: Any) -> dict[str, Any]:
    """Resolve role objects from request.user fallbacks."""
    identity = {
        "role": None,
        "admin": None,
        "vendor": None,
        "customer": None,
    }
    user = getattr(request, "user", None)
    if not user:
        return identity

    if isinstance(user, Admin):
        identity["role"] = ROLE_ADMIN
        identity["admin"] = user
        return identity
    if isinstance(user, Vendor):
        identity["role"] = ROLE_VENDOR
        identity["vendor"] = user
        return identity
    if isinstance(user, User):
        identity["role"] = ROLE_CUSTOMER
        identity["customer"] = user
        return identity

    if not getattr(user, "is_authenticated", False):
        return identity

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        identity["role"] = ROLE_ADMIN
        identity["admin"] = user
        return identity

    query = _identity_query(user)
    if not query:
        return identity

    admin = Admin.objects.filter(query, is_active=True).first()
    if admin:
        identity["role"] = ROLE_ADMIN
        identity["admin"] = admin
        return identity

    vendor = (
        Vendor.objects.filter(query, is_active=True)
        .exclude(status__iexact="blocked")
        .first()
    )
    if vendor:
        identity["role"] = ROLE_VENDOR
        identity["vendor"] = vendor
        return identity

    customer = User.objects.filter(query, is_active=True).first()
    if customer:
        identity["role"] = ROLE_CUSTOMER
        identity["customer"] = customer
        return identity

    return identity


def resolve_request_identity(request: Any) -> dict[str, Any]:
    """Resolve authenticated role identity from token or request.user."""
    cached = getattr(request, "_mt_identity_cache", None)
    if isinstance(cached, dict):
        return cached

    identity = {
        "role": None,
        "admin": None,
        "vendor": None,
        "customer": None,
    }
    token = _extract_bearer_token(request)
    token_payload = _decode_access_token(token)
    if token_payload:
        identity = _resolve_identity_from_token(token_payload)
    if not identity.get("role"):
        identity = _resolve_identity_from_request_user(request)

    setattr(request, "_mt_identity_cache", identity)
    return identity


def get_request_role(request: Any) -> Optional[str]:
    """Return normalized role for the current request identity."""
    return resolve_request_identity(request).get("role")


def is_authenticated(request: Any) -> bool:
    """Return True if request resolves to a known authenticated role."""
    return bool(get_request_role(request))


def resolve_admin(request: Any) -> Optional[Any]:
    """Resolve the admin actor attached to the request, if any."""
    return resolve_request_identity(request).get("admin")


def resolve_vendor(request: Any) -> Optional[Any]:
    """Resolve the vendor actor attached to the request, if any."""
    return resolve_request_identity(request).get("vendor")


def resolve_customer(request: Any) -> Optional[Any]:
    """Resolve the customer actor attached to the request, if any."""
    return resolve_request_identity(request).get("customer")


def is_admin_request(request: Any) -> bool:
    """Return True if the request is authenticated as an admin."""
    return get_request_role(request) == ROLE_ADMIN


def is_vendor_request(request: Any) -> bool:
    """Return True if the request is authenticated as a vendor."""
    return get_request_role(request) == ROLE_VENDOR


def role_required(*roles: str):
    """Return a decorator that restricts a view to one or more roles."""
    allowed_roles = {str(role or "").strip().lower() for role in roles if role}

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request: Any, *args, **kwargs):
            role = get_request_role(request)
            if not role:
                return Response(
                    {"message": AUTH_REQUIRED_MESSAGE},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if role not in allowed_roles:
                message = ADMIN_REQUIRED_MESSAGE
                if ROLE_VENDOR in allowed_roles and ROLE_ADMIN not in allowed_roles:
                    message = VENDOR_REQUIRED_MESSAGE
                return Response(
                    {"message": message},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def admin_required(view_func):
    """Restrict a view to authenticated admin role only."""
    return role_required(ROLE_ADMIN)(view_func)


def vendor_required(view_func):
    """Restrict a view to authenticated vendor role only."""
    return role_required(ROLE_VENDOR)(view_func)


class IsSuperAdmin(BasePermission):
    """Allow only super admins (or authenticated app admins)."""

    message = SUPER_ADMIN_REQUIRED_MESSAGE

    def has_permission(self, request: Any, view: Any) -> bool:
        if is_admin_request(request):
            return True
        user = getattr(request, "user", None)
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and getattr(user, "is_staff", False)
            and getattr(user, "is_superuser", False)
        )


class IsAdmin(BasePermission):
    """Allow only admins (including staff/superuser)."""

    message = ADMIN_REQUIRED_MESSAGE

    def has_permission(self, request: Any, view: Any) -> bool:
        return is_admin_request(request)


class IsVendor(BasePermission):
    """Allow only vendors."""

    message = VENDOR_REQUIRED_MESSAGE

    def has_permission(self, request: Any, view: Any) -> bool:
        return is_vendor_request(request)


class IsAdminOrReadOnly(BasePermission):
    """Allow read-only access for everyone, writes for admins only."""

    message = ADMIN_REQUIRED_MESSAGE

    def has_permission(self, request: Any, view: Any) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return is_admin_request(request)
