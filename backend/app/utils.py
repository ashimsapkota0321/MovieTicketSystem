"""Utility helpers shared across the backend."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timezone as datetime_timezone
from typing import Any, Iterable, Optional

from django.utils import timezone as django_timezone

DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M"
DEFAULT_SHORT_LABEL = "CIN"
UTC = datetime_timezone.utc

YOUTUBE_ID_PATTERNS: tuple[str, ...] = (
    r"(?:v=|vi=)([0-9A-Za-z_-]{11})",
    r"youtu\.be/([0-9A-Za-z_-]{11})",
    r"youtube\.com/embed/([0-9A-Za-z_-]{11})",
)


def build_media_url(request: Any, field: Any) -> Optional[str]:
    """Return an absolute URL for a Django File/ImageField or None."""
    if not field:
        return None
    try:
        url = field.url
    except Exception:
        return None
    if request is None:
        return url
    return request.build_absolute_uri(url)


def get_profile_image_url(request: Any, user: Any) -> Optional[str]:
    """Return the absolute URL for a user's profile image if available."""
    return build_media_url(request, getattr(user, "profile_image", None))


def slugify_text(value: Any) -> str:
    """Slugify a value into lowercase dash-separated text."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def short_label(value: Any) -> str:
    """Create a short label for a venue or name."""
    text = str(value or "").strip()
    if not text:
        return DEFAULT_SHORT_LABEL
    words = re.findall(r"[A-Za-z0-9]+", text.upper())
    if not words:
        return DEFAULT_SHORT_LABEL
    if len(words) == 1:
        return words[0][:3]
    return "".join(word[0] for word in words[:3])


def get_payload(request: Any) -> dict[str, Any]:
    """Safely coerce request.data into a plain dict."""
    payload = getattr(request, "data", None)
    if payload is None:
        return {}
    if hasattr(payload, "dict"):
        payload = payload.dict()
    if isinstance(payload, dict):
        return payload
    try:
        return dict(payload)
    except Exception:
        return {}


def request_data_to_dict(request: Any) -> dict[str, Any]:
    """Convert request.data into a dictionary without validation."""
    if hasattr(request.data, "dict"):
        return request.data.dict()
    return dict(request.data)


def coalesce(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first non-empty value for the given keys from payload."""
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return default


def parse_date(value: Any) -> Optional[date]:
    """Parse a date string in YYYY-MM-DD format or return None."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), DATE_FORMAT).date()
    except Exception:
        return None


def parse_time(value: Any) -> Optional[time]:
    """Parse a time string in HH:MM format or return None."""
    if not value:
        return None
    if hasattr(value, "hour"):
        return value
    try:
        return datetime.strptime(str(value), TIME_FORMAT).time()
    except Exception:
        return None


def ensure_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    """Return a timezone-aware UTC datetime for consistent storage/comparisons."""
    if value is None:
        return None
    if django_timezone.is_naive(value):
        return django_timezone.make_aware(value, UTC)
    return value.astimezone(UTC)


def combine_date_time_utc(day_value: Optional[date], time_value: Optional[time]) -> Optional[datetime]:
    """Combine date/time and normalize result into aware UTC datetime."""
    if not day_value or not time_value:
        return None
    return ensure_utc_datetime(datetime.combine(day_value, time_value))


def parse_datetime_utc(value: Any) -> Optional[datetime]:
    """Parse ISO datetime input and normalize it into aware UTC datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return ensure_utc_datetime(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return ensure_utc_datetime(parsed)


def extract_youtube_id(url: Any) -> Optional[str]:
    """Extract a YouTube video ID from a URL."""
    if not url:
        return None
    for pattern in YOUTUBE_ID_PATTERNS:
        match = re.search(pattern, str(url))
        if match:
            return match.group(1)
    return None


def parse_bool(value: Any, default: bool = False) -> bool:
    """Coerce common truthy/falsey string values into booleans."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return bool(value)


def normalize_phone_number(value: Any) -> str:
    """Normalize a phone number by stripping non-digit characters."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return re.sub(r"\D", "", text)


def is_phone_like(value: Any) -> bool:
    """Return True if the value looks like a phone number input."""
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    return bool(re.fullmatch(r"[0-9+()\s-]+", text))
