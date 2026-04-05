"""Request logging and role-based access middleware."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from django.http import JsonResponse

from .logging_utils import reset_request_id, set_request_id

from .permissions import (
    ADMIN_REQUIRED_MESSAGE,
    AUTH_REQUIRED_MESSAGE,
    VENDOR_REQUIRED_MESSAGE,
    is_admin_request,
    is_authenticated,
    is_vendor_request,
)

REQUEST_ID_META_KEY = "HTTP_X_REQUEST_ID"
REQUEST_ID_HEADER = "X-Request-ID"

request_logger = logging.getLogger("app.request")


class RequestIDLoggingMiddleware:
    """Attach request IDs and emit centralized access logs for API debugging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: Any):
        request_id = self._resolve_request_id(request)
        request.request_id = request_id
        started_at = time.perf_counter()
        context_token = set_request_id(request_id)

        response = None
        try:
            response = self.get_response(request)
            return response
        except Exception:
            request_logger.exception(
                "Unhandled exception while processing request",
                extra=self._build_log_context(
                    request=request,
                    started_at=started_at,
                    status_code=500,
                    request_id=request_id,
                ),
            )
            raise
        finally:
            if response is not None:
                response[REQUEST_ID_HEADER] = request_id
                request_logger.info(
                    "Request completed",
                    extra=self._build_log_context(
                        request=request,
                        started_at=started_at,
                        status_code=getattr(response, "status_code", "-"),
                        request_id=request_id,
                    ),
                )
            reset_request_id(context_token)

    def _resolve_request_id(self, request: Any) -> str:
        incoming = str(getattr(request, "META", {}).get(REQUEST_ID_META_KEY, "") or "").strip()
        if incoming:
            return incoming[:128]
        return uuid.uuid4().hex

    def _resolve_user_id(self, request: Any) -> str:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            return str(getattr(user, "id", "-"))
        return "-"

    def _resolve_client_ip(self, request: Any) -> str:
        meta = getattr(request, "META", {}) or {}
        forwarded_for = str(meta.get("HTTP_X_FORWARDED_FOR", "") or "").strip()
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip() or "-"
        return str(meta.get("REMOTE_ADDR", "") or "-")

    def _build_log_context(
        self,
        *,
        request: Any,
        started_at: float,
        status_code: int | str,
        request_id: str,
    ) -> dict[str, Any]:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "request_id": request_id,
            "method": str(getattr(request, "method", "-") or "-"),
            "path": str(getattr(request, "path", "-") or "-"),
            "status_code": status_code,
            "duration_ms": duration_ms,
            "user_id": self._resolve_user_id(request),
            "client_ip": self._resolve_client_ip(request),
        }


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
