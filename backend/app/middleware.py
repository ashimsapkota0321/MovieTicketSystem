"""Role-based access middleware for admin and vendor API namespaces."""

from __future__ import annotations

from typing import Any, Optional

from django.http import JsonResponse

from .permissions import (
    ADMIN_REQUIRED_MESSAGE,
    AUTH_REQUIRED_MESSAGE,
    VENDOR_REQUIRED_MESSAGE,
    is_admin_request,
    is_authenticated,
    is_vendor_request,
)


class RoleBasedAccessMiddleware:
    """Enforce role checks on `/api/admin/*` and `/api/vendor/*` routes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: Any):
        if request.method == "OPTIONS":
            return self.get_response(request)

        path = str(getattr(request, "path", "") or "")
        denied_response = self._enforce_path_role(request, path)
        if denied_response is not None:
            return denied_response

        return self.get_response(request)

    def _enforce_path_role(self, request: Any, path: str) -> Optional[JsonResponse]:
        if path.startswith("/api/admin/"):
            return self._require_admin(request)
        if path.startswith("/api/vendor/"):
            return self._require_vendor(request)
        return None

    def _require_admin(self, request: Any) -> Optional[JsonResponse]:
        if not is_authenticated(request):
            return JsonResponse(
                {"message": AUTH_REQUIRED_MESSAGE},
                status=401,
            )
        if not is_admin_request(request):
            return JsonResponse(
                {"message": ADMIN_REQUIRED_MESSAGE},
                status=403,
            )
        return None

    def _require_vendor(self, request: Any) -> Optional[JsonResponse]:
        if not is_authenticated(request):
            return JsonResponse(
                {"message": AUTH_REQUIRED_MESSAGE},
                status=401,
            )
        if not is_vendor_request(request):
            return JsonResponse(
                {"message": VENDOR_REQUIRED_MESSAGE},
                status=403,
            )
        return None
