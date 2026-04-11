"""Custom permission helpers for admin/vendor access."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from functools import wraps
from datetime import timedelta
from typing import Any, Optional

from django.conf import settings
from django.core import signing
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from .models import Admin, AuthSession, User, Vendor, VendorStaff

ADMIN_REQUIRED_MESSAGE = "Admin access required."
SUPER_ADMIN_REQUIRED_MESSAGE = "Super admin access required."
AUTH_REQUIRED_MESSAGE = "Authentication required."
VENDOR_REQUIRED_MESSAGE = "Vendor access required."
CUSTOMER_REQUIRED_MESSAGE = "Customer access required."

ROLE_ADMIN = "admin"
ROLE_VENDOR = "vendor"
ROLE_CUSTOMER = "customer"
ROLE_CHOICES = {ROLE_ADMIN, ROLE_VENDOR, ROLE_CUSTOMER}
AUTH_TOKEN_SALT = "meroticket.auth.token.v1"
DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS = 60 * 15
DEFAULT_REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


def _access_token_max_age_seconds() -> int:
    """Return the configured auth access token max age in seconds."""
    configured = getattr(
        settings,
        "APP_AUTH_ACCESS_TOKEN_MAX_AGE_SECONDS",
        getattr(settings, "APP_AUTH_TOKEN_MAX_AGE_SECONDS", DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS),
    )
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = DEFAULT_ACCESS_TOKEN_MAX_AGE_SECONDS
    return max(parsed, 60)


def _refresh_token_max_age_seconds() -> int:
    """Return the configured auth refresh token max age in seconds."""
    configured = getattr(
        settings,
        "APP_AUTH_REFRESH_TOKEN_MAX_AGE_SECONDS",
        DEFAULT_REFRESH_TOKEN_MAX_AGE_SECONDS,
    )
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = DEFAULT_REFRESH_TOKEN_MAX_AGE_SECONDS
    return max(parsed, 60)


def _token_digest(value: str) -> str:
    """Return a stable hash for persisted token lookup."""
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def issue_access_token(
    role: str,
    user_id: Any,
    extras: Optional[dict[str, Any]] = None,
    *,
    session_id: Any = None,
) -> str:
    """Issue a signed access token containing role and subject ID."""
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in ROLE_CHOICES:
        raise ValueError("Unsupported role")
    subject_id = int(user_id)
    payload = {"role": normalized_role, "user_id": subject_id, "token_type": "access"}
    if session_id is not None:
        payload["session_id"] = str(session_id)
    if isinstance(extras, dict):
        payload.update(extras)
    return signing.dumps(payload, salt=AUTH_TOKEN_SALT, compress=True)


def create_auth_session(
    role: str,
    user_id: Any,
    extras: Optional[dict[str, Any]] = None,
) -> tuple[AuthSession, str]:
    """Create a revocable auth session and return the refresh token."""
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in ROLE_CHOICES:
        raise ValueError("Unsupported role")

    subject_id = int(user_id)
    now = timezone.now()
    session = AuthSession.objects.create(
        role=normalized_role,
        user_id=subject_id,
        staff_id=(int(extras.get("staff_id")) if isinstance(extras, dict) and extras.get("staff_id") is not None else None),
        staff_role=(str(extras.get("staff_role") or "").strip().upper() if isinstance(extras, dict) else None) or None,
        access_expires_at=now + timedelta(seconds=_access_token_max_age_seconds()),
        refresh_expires_at=now + timedelta(seconds=_refresh_token_max_age_seconds()),
    )
    refresh_token = secrets.token_urlsafe(48)
    session.refresh_token_hash = _token_digest(refresh_token)
    session.save(update_fields=["refresh_token_hash"])
    return session, refresh_token


def _get_active_session(session_id: Any) -> Optional[AuthSession]:
    """Return the active auth session for a token payload."""
    token_session_id = str(session_id or "").strip()
    if not token_session_id:
        return None
    try:
        token_session_id = str(uuid.UUID(token_session_id))
    except (TypeError, ValueError, AttributeError):
        return None
    session = AuthSession.objects.filter(session_id=token_session_id).first()
    if not session:
        return None
    now = timezone.now()
    if session.revoked_at or session.refresh_expires_at <= now:
        return None
    return session


def _session_payload_matches(session: AuthSession, token_payload: dict[str, Any]) -> bool:
    """Confirm the decoded token still belongs to the active session."""
    if session.role != str(token_payload.get("role") or "").strip().lower():
        return False
    try:
        if int(token_payload.get("user_id")) != int(session.user_id):
            return False
    except (TypeError, ValueError):
        return False
    token_staff_id = token_payload.get("staff_id")
    if token_staff_id is not None:
        try:
            if int(token_staff_id) != int(session.staff_id or 0):
                return False
        except (TypeError, ValueError):
            return False
    token_staff_role = str(token_payload.get("staff_role") or "").strip().upper() or None
    if token_staff_role and token_staff_role != str(session.staff_role or "").strip().upper():
        return False
    return True


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
            max_age=_access_token_max_age_seconds(),
        )
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None

    if not isinstance(payload, dict):
        return None
    token_type = str(payload.get("token_type") or "access").strip().lower()
    if token_type != "access":
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
    session_id = payload.get("session_id")
    if session_id is not None:
        session = _get_active_session(session_id)
        if not session or not _session_payload_matches(session, payload):
            return None
    decoded = {"role": role, "user_id": user_id}
    if session_id is not None:
        decoded["session_id"] = str(session_id)
    if "staff_id" in payload:
        try:
            decoded["staff_id"] = int(payload.get("staff_id"))
        except (TypeError, ValueError):
            return None
    if "staff_role" in payload:
        decoded["staff_role"] = str(payload.get("staff_role") or "").strip().upper()
    return decoded


def _find_refresh_session(refresh_token: str) -> Optional[AuthSession]:
    """Return the active session associated with a refresh token."""
    token = str(refresh_token or "").strip()
    if not token:
        return None
    token_hash = _token_digest(token)
    session = AuthSession.objects.filter(refresh_token_hash=token_hash).first()
    if not session:
        return None
    now = timezone.now()
    if session.revoked_at or session.refresh_expires_at <= now:
        return None
    return session


def refresh_access_token(refresh_token: str) -> Optional[dict[str, Any]]:
    """Rotate a refresh token and issue a new access token pair."""
    session = _find_refresh_session(refresh_token)
    if not session:
        return None

    extras: dict[str, Any] = {}
    if session.staff_id is not None:
        extras["staff_id"] = session.staff_id
    if session.staff_role:
        extras["staff_role"] = session.staff_role

    new_refresh_token = secrets.token_urlsafe(48)
    now = timezone.now()
    session.refresh_token_hash = _token_digest(new_refresh_token)
    session.access_expires_at = now + timedelta(seconds=_access_token_max_age_seconds())
    session.last_used_at = now
    session.save(update_fields=["refresh_token_hash", "access_expires_at", "last_used_at"])

    access_token = issue_access_token(
        session.role,
        session.user_id,
        extras=extras or None,
        session_id=session.session_id,
    )
    return {
        "session": session,
        "access_token": access_token,
        "refresh_token": new_refresh_token,
    }


def revoke_auth_session(session_id: Any, reason: str = "logout") -> bool:
    """Revoke a session by its identifier."""
    token_session_id = str(session_id or "").strip()
    if not token_session_id:
        return False
    updated = AuthSession.objects.filter(
        session_id=token_session_id,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now(), revoked_reason=reason)
    return bool(updated)


def revoke_refresh_token(refresh_token: str, reason: str = "logout") -> bool:
    """Revoke a session by its refresh token."""
    session = _find_refresh_session(refresh_token)
    if not session:
        return False
    return revoke_auth_session(session.session_id, reason=reason)


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
        "vendor_staff": None,
        "customer": None,
        "session_id": None,
    }
    role = token_payload.get("role")
    user_id = token_payload.get("user_id")
    session_id = token_payload.get("session_id")
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
            staff_id = token_payload.get("staff_id")
            if staff_id:
                staff = VendorStaff.objects.filter(
                    pk=staff_id,
                    vendor_id=vendor.id,
                    is_active=True,
                ).first()
                if staff:
                    identity["vendor_staff"] = staff
    elif role == ROLE_CUSTOMER:
        customer = User.objects.filter(pk=user_id, is_active=True).first()
        if customer:
            identity["role"] = ROLE_CUSTOMER
            identity["customer"] = customer
    if session_id is not None:
        identity["session_id"] = str(session_id)
    return identity


def _resolve_identity_from_request_user(request: Any) -> dict[str, Any]:
    """Resolve role objects from request.user fallbacks."""
    identity = {
        "role": None,
        "admin": None,
        "vendor": None,
        "vendor_staff": None,
        "customer": None,
        "session_id": None,
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
        "vendor_staff": None,
        "customer": None,
        "session_id": None,
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


def get_request_session_id(request: Any) -> Optional[str]:
    """Return the active auth session ID for the current request, if available."""
    session_id = resolve_request_identity(request).get("session_id")
    return str(session_id) if session_id else None


def resolve_vendor_staff(request: Any) -> Optional[VendorStaff]:
    """Resolve the vendor staff actor attached to the request, if any."""
    staff = resolve_request_identity(request).get("vendor_staff")
    return staff if isinstance(staff, VendorStaff) else None


def is_vendor_owner(request: Any) -> bool:
    """Return True when request is vendor account owner (not staff sub-account)."""
    return bool(resolve_vendor(request)) and resolve_vendor_staff(request) is None


def is_vendor_manager(request: Any) -> bool:
    """Return True only for owner vendor account."""
    return is_vendor_owner(request)


def _staff_can_access_path(_staff_role: str, path: str) -> bool:
    """Restrict vendor staff routes to staff-level operations only."""
    normalized_path = str(path or "").lower()

    cashier_allowed_prefixes = [
        "/api/vendor/bookings/",
        "/api/vendor/bookings",
        "/api/vendor/ticket-validation/",
        "/api/vendor/ticket-validation",
        "/api/profile/vendor/",
    ]
    if any(normalized_path.startswith(prefix) for prefix in cashier_allowed_prefixes):
        return True
    return False


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
                if ROLE_CUSTOMER in allowed_roles and ROLE_ADMIN not in allowed_roles and ROLE_VENDOR not in allowed_roles:
                    message = CUSTOMER_REQUIRED_MESSAGE
                return Response(
                    {"message": message},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if role == ROLE_VENDOR:
                staff = resolve_vendor_staff(request)
                if staff and not _staff_can_access_path(staff.role, getattr(request, "path", "")):
                    return Response(
                        {"message": "Vendor staff access denied for this operation."},
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


class IsCustomer(BasePermission):
    """Allow only customers."""

    message = CUSTOMER_REQUIRED_MESSAGE

    def has_permission(self, request: Any, view: Any) -> bool:
        return get_request_role(request) == ROLE_CUSTOMER


class IsAdminOrReadOnly(BasePermission):
    """Allow read-only access for everyone, writes for admins only."""

    message = ADMIN_REQUIRED_MESSAGE

    def has_permission(self, request: Any, view: Any) -> bool:
        if request.method in SAFE_METHODS:
            return True
        return is_admin_request(request)
