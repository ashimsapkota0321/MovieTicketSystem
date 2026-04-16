"""Startup schema guard to keep runtime in sync with migrations."""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import django
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection


_SCHEMA_READY = False
_CRITICAL_SCHEMA_COLUMNS = {
    "bookings": {"user_id", "showtime_id", "booking_status", "total_amount"},
    "booking_seats": {"booking_id", "showtime_id", "seat_id", "seat_price"},
    "seat_availability": {"seat_id", "showtime_id", "seat_status", "locked_until"},
    "tickets": {
        "reference",
        "ticket_id",
        "payload",
        "is_used",
        "payment_status",
        "token_expires_at",
    },
    "pricing_rules": {
        "name",
        "seat_category",
        "day_of_week",
        "is_active",
        "priority",
        "price_multiplier",
        "flat_adjustment",
    },
    "show_base_prices": {"show_id", "seat_category", "base_price", "is_active"},
}


def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean env var values with a safe fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _startup_lock_file() -> Path:
    """Resolve lock file path used to serialize startup migration work."""
    configured = str(os.environ.get("DJANGO_STARTUP_MIGRATION_LOCK_FILE") or "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "meroticket-startup-migrate.lock"


@contextmanager
def _acquire_startup_lock() -> None:
    """Acquire an inter-process file lock for startup migration execution."""
    lock_file = _startup_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_file, "a+") as handle:
        if os.name == "nt":
            import msvcrt

            acquired = False
            while not acquired:
                try:
                    handle.seek(0)
                    handle.write("0")
                    handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                except OSError:
                    time.sleep(0.1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_http_url(value: str) -> bool:
    """Return whether a value is an absolute HTTP(S) URL."""
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _validate_required_env_settings() -> None:
    """Validate startup-critical runtime settings for predictable operation."""
    errors: list[str] = []

    database = settings.DATABASES.get("default") if isinstance(settings.DATABASES, dict) else {}
    engine = str((database or {}).get("ENGINE") or "").strip()
    name = str((database or {}).get("NAME") or "").strip()

    if not engine:
        errors.append("DATABASES.default.ENGINE is required")
    if not name:
        errors.append("DATABASES.default.NAME is required")

    if not str(getattr(settings, "ESEWA_PRODUCT_CODE", "") or "").strip():
        errors.append("ESEWA_PRODUCT_CODE is required")
    if not str(getattr(settings, "ESEWA_SECRET_KEY", "") or "").strip():
        errors.append("ESEWA_SECRET_KEY is required")

    esewa_form_url = str(getattr(settings, "ESEWA_FORM_URL", "") or "").strip()
    if not _is_http_url(esewa_form_url):
        errors.append("ESEWA_FORM_URL must be an absolute http(s) URL")

    esewa_status_url = str(getattr(settings, "ESEWA_STATUS_CHECK_URL", "") or "").strip()
    if not _is_http_url(esewa_status_url):
        errors.append("ESEWA_STATUS_CHECK_URL must be an absolute http(s) URL")

    frontend_base = str(getattr(settings, "FRONTEND_BASE_URL", "") or "").strip()
    if not _is_http_url(frontend_base):
        errors.append("FRONTEND_BASE_URL must be an absolute http(s) URL")

    email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "").strip()
    if not email_backend:
        errors.append("EMAIL_BACKEND is required")
    elif "smtp" in email_backend.lower():
        if not str(getattr(settings, "EMAIL_HOST", "") or "").strip():
            errors.append("EMAIL_HOST is required when SMTP backend is enabled")
        try:
            email_port = int(getattr(settings, "EMAIL_PORT", 0))
        except (TypeError, ValueError):
            email_port = 0
        if email_port <= 0:
            errors.append("EMAIL_PORT must be a positive integer when SMTP backend is enabled")
        if not str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip():
            errors.append("DEFAULT_FROM_EMAIL is required when SMTP backend is enabled")
        if not settings.DEBUG:
            if not str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip():
                errors.append("EMAIL_HOST_USER is required in production when SMTP backend is enabled")
            if not str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip():
                errors.append("EMAIL_HOST_PASSWORD is required in production when SMTP backend is enabled")

    if not settings.DEBUG:
        secret_key = str(getattr(settings, "SECRET_KEY", "") or "").strip()
        if not secret_key or "django-insecure" in secret_key:
            errors.append("SECRET_KEY must be configured with a non-default secure value in production")
        allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        if not any(str(host or "").strip() for host in allowed_hosts):
            errors.append("ALLOWED_HOSTS must contain at least one host in production")

    if errors:
        details = "\n - ".join(errors)
        raise RuntimeError(f"Startup environment validation failed:\n - {details}")


def _validate_critical_database_columns() -> None:
    """Ensure required database tables/columns exist after migrations."""
    errors: list[str] = []

    with connection.cursor() as cursor:
        table_names = set(connection.introspection.table_names(cursor))
        for table_name, expected_columns in _CRITICAL_SCHEMA_COLUMNS.items():
            if table_name not in table_names:
                errors.append(f"missing table: {table_name}")
                continue

            description = connection.introspection.get_table_description(cursor, table_name)
            actual_columns = {str(column.name) for column in description}
            missing_columns = sorted(expected_columns - actual_columns)
            if missing_columns:
                errors.append(
                    f"missing columns in {table_name}: {', '.join(missing_columns)}"
                )

    if errors:
        details = "\n - ".join(errors)
        raise RuntimeError(f"Startup database schema validation failed:\n - {details}")


def _run_startup_validations() -> None:
    """Run configurable startup validations for env and critical schema."""
    if _env_bool("DJANGO_SKIP_STARTUP_VALIDATIONS", default=False):
        return

    should_validate_env = _env_bool("DJANGO_VALIDATE_STARTUP_ENV", default=True)
    should_validate_columns = _env_bool("DJANGO_VALIDATE_STARTUP_DB_COLUMNS", default=True)

    if should_validate_env:
        _validate_required_env_settings()
    if should_validate_columns:
        _validate_critical_database_columns()


def _ensure_django_ready() -> None:
    """Initialize Django app registry before calling management/DB APIs."""
    if not apps.ready:
        django.setup()


def ensure_schema_ready() -> None:
    """Auto-apply and verify migrations so server startup never runs on stale schema."""
    global _SCHEMA_READY

    if _SCHEMA_READY:
        return

    if _env_bool("DJANGO_SKIP_STARTUP_MIGRATIONS", default=False):
        _SCHEMA_READY = True
        return

    should_auto_migrate = _env_bool("DJANGO_AUTO_MIGRATE_ON_STARTUP", default=True)
    should_enforce = _env_bool("DJANGO_ENFORCE_SCHEMA_ON_STARTUP", default=True)

    try:
        with _acquire_startup_lock():
            _ensure_django_ready()

            if should_auto_migrate:
                call_command("migrate", interactive=False, verbosity=1)

            if should_enforce:
                call_command("migrate", check=True, verbosity=0)

            _run_startup_validations()
    except SystemExit as exc:
        raise RuntimeError(
            "Startup aborted because database schema is not up-to-date. "
            "Apply migrations before serving traffic."
        ) from exc
    except RuntimeError:
        # Preserve explicit startup validation errors (env/schema checks) as-is.
        raise
    except Exception as exc:
        raise RuntimeError(
            "Startup aborted while applying/verifying migrations. "
            f"Fix migration/database issues before starting the server. Root cause: {exc}"
        ) from exc

    _SCHEMA_READY = True
