"""Service layer helpers and business logic."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import random
import re
import uuid
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from django.conf import settings
from django.core.cache import cache
from django.core import signing
from django.core.mail import EmailMessage, send_mail
from django.db import transaction
from django.db import IntegrityError
from django.db.models import Q, Count, Sum, F, DecimalField, Avg, Max, Min
from django.db.models.functions import ExtractWeekDay, TruncDate, TruncMonth
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.utils.html import escape
from PIL import Image, ImageDraw, ImageFont
from rest_framework import status

from ..models import (
    User,
    Admin,
    Vendor,
    VendorStaff,
    Movie,
    Person,
    MovieCredit,
    Show,
    ShowBasePrice,
    Banner,
    HomeSlide,
    Collaborator,
    OTPVerification,
    Ticket,
    TicketValidationScan,
    Screen,
    Seat,
    Showtime,
    PricingRule,
    SeatAvailability,
    Coupon,
    Booking,
    BookingSeat,
    BulkTicketBatch,
    BulkTicketItem,
    Payment,
    PrivateScreeningRequest,
    Refund,
    PlatformRevenueConfig,
    AdminWallet,
    AdminWalletTransaction,
    Referral,
    ReferralPolicy,
    ReferralWallet,
    ReferralTransaction,
    Wallet,
    Transaction,
    VendorCommissionLedger,
    RefundLedger,
    ReversalLedger,
    WithdrawalLedger,
    UserWallet,
    UserWalletTransaction,
    LoyaltyProgramConfig,
    UserLoyaltyWallet,
    LoyaltyTransaction,
    LoyaltyPromotion,
    VendorLoyaltyRule,
    Reward,
    RewardRedemption,
    FoodItem,
    BookingFoodItem,
    BookingDropoffEvent,
    Notification,
    BackgroundJob,
    VendorPromoCode,
    VendorCampaign,
    VendorCampaignDispatch,
    VendorCancellationPolicy,
    VendorPayoutProfile,
)
from ..serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer,
    UserProfileUpdateSerializer,
    AdminProfileUpdateSerializer,
    VendorProfileUpdateSerializer,
    generate_unique_username,
    HomeSlideAdminSerializer,
    CollabDetailsAdminSerializer,
    CollaboratorAdminSerializer,
    BannerCreateUpdateSerializer,
)
from ..permissions import (
    is_admin_request,
    is_authenticated,
    create_auth_session,
    issue_access_token,
    resolve_admin,
    resolve_customer,
    resolve_vendor,
)
from .. import loyalty, selectors, subscription
from ..selectors import build_movie_admin_payload, build_movie_payload, build_movie_vendor_payload, build_show_payload, get_ticket
from ..utils import (
    combine_date_time_utc,
    coalesce,
    ensure_utc_datetime,
    get_payload,
    get_profile_image_url,
    is_phone_like,
    normalize_phone_number,
    parse_date,
    parse_datetime_utc,
    parse_time,
    parse_bool,
    request_data_to_dict,
    short_label,
    slugify_text,
)

logger = logging.getLogger(__name__)


def _build_auth_token_payload(session: Any, access_token: str, refresh_token: str) -> dict[str, Any]:
    """Build the token response payload for authenticated sessions."""
    now = timezone.now()
    access_expires_in = max(int((session.access_expires_at - now).total_seconds()), 0)
    refresh_expires_in = max(int((session.refresh_expires_at - now).total_seconds()), 0)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "session_id": str(session.session_id),
        "expires_in": access_expires_in,
        "refresh_expires_in": refresh_expires_in,
    }


def _issue_session_tokens(role: str, user_id: int, extras: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Create a revocable session and issue access/refresh tokens."""
    session, refresh_token = create_auth_session(role, user_id, extras=extras)
    access_token = issue_access_token(
        role,
        user_id,
        extras=extras,
        session_id=session.session_id,
    )
    return _build_auth_token_payload(session, access_token, refresh_token)


PHONE_REGEX = re.compile(r"^[0-9]{10,13}$")
DEFAULT_VENDOR_STATUS = "Active"
STATUS_BLOCKED = "Blocked"
AUTH_REQUIRED_MESSAGE = "Authentication required"
ADMIN_REQUIRED_MESSAGE = "Admin access required"
INVALID_PHONE_MESSAGE = "Invalid phone number format"
PHONE_EXISTS_MESSAGE = "Phone number already exists"
SEAT_STATUS_SOLD = "Sold"
SEAT_STATUS_BOOKED = "Booked"
SEAT_STATUS_AVAILABLE = "Available"
SEAT_STATUS_UNAVAILABLE = "Unavailable"
SEAT_STATUS_RESERVED = "Reserved"
BOOKING_STATUS_PENDING = Booking.Status.PENDING
BOOKING_STATUS_CONFIRMED = Booking.Status.CONFIRMED
BOOKING_STATUS_CANCELLED = Booking.Status.CANCELLED
PAYMENT_STATUS_PENDING = Payment.Status.PENDING
PAYMENT_STATUS_SUCCESS = Payment.Status.SUCCESS
PAYMENT_STATUS_FAILED = Payment.Status.FAILED
PAYMENT_STATUS_REFUNDED = Payment.Status.REFUNDED
PAYMENT_STATUS_PARTIALLY_REFUNDED = Payment.Status.PARTIALLY_REFUNDED
REFUND_STATUS_PENDING = Refund.Status.PENDING
REFUND_STATUS_COMPLETED = Refund.Status.COMPLETED
TICKET_PAYMENT_STATUS_PENDING = Ticket.PaymentStatus.PENDING
TICKET_PAYMENT_STATUS_PAID = Ticket.PaymentStatus.PAID
ESEWA_PAYMENT_METHOD_PREFIX = "ESEWA:"
DEFAULT_GUEST_EMAIL = "guest.booking@meroticket.local"
DEFAULT_GUEST_NAME = "Guest"
SEAT_CATEGORY_NORMAL = "Normal"
SEAT_CATEGORY_EXECUTIVE = "Executive"
SEAT_CATEGORY_PREMIUM = "Premium"
SEAT_CATEGORY_VIP = "VIP"
SEAT_CATEGORY_ORDER = [
    SEAT_CATEGORY_NORMAL,
    SEAT_CATEGORY_EXECUTIVE,
    SEAT_CATEGORY_PREMIUM,
    SEAT_CATEGORY_VIP,
]
SEAT_CATEGORY_KEYS = {
    SEAT_CATEGORY_NORMAL: "normal",
    SEAT_CATEGORY_EXECUTIVE: "executive",
    SEAT_CATEGORY_PREMIUM: "premium",
    SEAT_CATEGORY_VIP: "vip",
}
SEAT_CATEGORY_RULE_VALUES = {
    SEAT_CATEGORY_NORMAL: PricingRule.SEAT_CATEGORY_NORMAL,
    SEAT_CATEGORY_EXECUTIVE: PricingRule.SEAT_CATEGORY_EXECUTIVE,
    SEAT_CATEGORY_PREMIUM: PricingRule.SEAT_CATEGORY_PREMIUM,
    SEAT_CATEGORY_VIP: PricingRule.SEAT_CATEGORY_VIP,
}
SEAT_CATEGORY_RULE_ALIASES = {
    SEAT_CATEGORY_NORMAL: {
        PricingRule.SEAT_CATEGORY_NORMAL,
        PricingRule.SEAT_CATEGORY_SILVER,
    },
    SEAT_CATEGORY_EXECUTIVE: {
        PricingRule.SEAT_CATEGORY_EXECUTIVE,
        PricingRule.SEAT_CATEGORY_GOLD,
    },
    SEAT_CATEGORY_PREMIUM: {
        PricingRule.SEAT_CATEGORY_PREMIUM,
        PricingRule.SEAT_CATEGORY_PLATINUM,
    },
    SEAT_CATEGORY_VIP: {
        PricingRule.SEAT_CATEGORY_VIP,
        PricingRule.SEAT_CATEGORY_PLATINUM,
    },
}
SEAT_CATEGORY_SCREEN_FIELDS = {
    "normal": "normal_price",
    "executive": "executive_price",
    "premium": "premium_price",
    "vip": "vip_price",
}
BOOKED_STATUSES = {SEAT_STATUS_BOOKED.lower(), SEAT_STATUS_SOLD.lower()}
RESERVE_HOLD_MINUTES = 10
BOOKING_RESUME_NOTICE_WINDOW_MINUTES = RESERVE_HOLD_MINUTES
EMAIL_OTP_TTL_MINUTES = 10
PLATFORM_COMMISSION_PERCENT = Decimal("10.00")
WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DEFAULT_REFUND_PERCENT_2H_PLUS = Decimal("100.00")
DEFAULT_REFUND_PERCENT_1_TO_2H = Decimal("70.00")
DEFAULT_REFUND_PERCENT_LESS_THAN_1H = Decimal("0.00")
SHOW_BUFFER_MINUTES_DEFAULT = 20
SHOW_MIN_LEAD_HOURS_DEFAULT = 2
SHOW_OPERATING_OPEN_TIME_DEFAULT = time_cls(hour=6, minute=0)
SHOW_OPERATING_CLOSE_TIME_DEFAULT = time_cls(hour=0, minute=0)
SHOW_BUFFER_MINUTES_MAX = 180
TICKET_QR_SIGNING_SALT = "app.ticket.qr.v1"
TICKET_VALIDATION_OPEN_WINDOW_HOURS = 1
TICKET_VALIDATION_GRACE_MINUTES = 15
TICKET_QR_FALLBACK_VALIDITY_HOURS = 4
LOYALTY_CACHE_KEY_PREFIX = "mt:loyalty:wallet:"
LOYALTY_CACHE_TTL_SECONDS = 60 * 5
LOYALTY_REWARD_REDEMPTION_HOLD_DAYS = 30
REFERRAL_CODE_LENGTH = 8
REFERRAL_REWARD_REFERRER_DEFAULT = Decimal("100.00")
REFERRAL_REWARD_REFERRED_DEFAULT = Decimal("50.00")
REFERRAL_SIGNUP_REWARD_DEFAULT = Decimal("20.00")
REFERRAL_REWARD_HOLD_PERIOD_DAYS_DEFAULT = 7
REFERRAL_REWARD_EXPIRY_DAYS_DEFAULT = 90
REFERRAL_WALLET_CAP_PERCENT_DEFAULT = Decimal("20.00")
ANALYTICS_CACHE_TTL_SECONDS = 120
ANALYTICS_VENDOR_CACHE_TTL_SECONDS = 90
VENDOR_PAYOUT_DEFAULT_MINIMUM_WITHDRAWAL = Decimal("500.00")
VENDOR_PAYOUT_DEFAULT_SCHEDULE = "WEEKLY"
VENDOR_PAYOUT_DEFAULT_SCHEDULE_DAY = 0
VENDOR_PAYOUT_DEFAULT_SCHEDULE_TIME = time_cls(hour=10, minute=0)


def _dashboard_cache_key(prefix: str, *parts: Any) -> str:
    """Build a stable cache key for analytics payloads."""
    serialized_parts = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(serialized_parts.encode("utf-8")).hexdigest()
    return f"mt:dashboard:{prefix}:{digest}"
REFERRAL_MAX_IP_SIGNUPS_PER_DAY_DEFAULT = 3
REFERRAL_MAX_DEVICE_SIGNUPS_PER_DAY_DEFAULT = 2
REFERRAL_CACHE_KEY_PREFIX = "mt:referral:wallet:"
REFERRAL_CACHE_TTL_SECONDS = 60 * 5
PRICING_PREVIEW_CACHE_PREFIX = "mt:pricing:preview:"
PRICING_LOCK_CACHE_PREFIX = "mt:pricing:lock:"
PRICING_OCCUPANCY_CACHE_PREFIX = "mt:pricing:occupancy:"
PRICING_CATEGORY_CACHE_PREFIX = "mt:pricing:category:"
PRICING_PREVIEW_CACHE_TTL_SECONDS = 30
PRICING_OCCUPANCY_CACHE_TTL_SECONDS = 20
PRICING_CATEGORY_CACHE_TTL_SECONDS = 45
PRICING_LOCK_TTL_SECONDS = 60 * 10
PRICING_OCCUPANCY_LOW_MAX = Decimal("30.00")
PRICING_OCCUPANCY_HIGH_MIN = Decimal("70.00")
PRICING_OCCUPANCY_LOW_MULTIPLIER = Decimal("0.90")
PRICING_OCCUPANCY_NORMAL_MULTIPLIER = Decimal("1.00")
PRICING_OCCUPANCY_HIGH_MULTIPLIER = Decimal("1.20")
PRICING_MIN_PRICE_FACTOR = Decimal("0.50")
PRICING_MAX_PRICE_FACTOR = Decimal("3.00")
BACKGROUND_JOB_DEFAULT_MAX_ATTEMPTS = 3
BACKGROUND_JOB_RETRY_BACKOFF_SECONDS = 30
BACKGROUND_JOB_TYPE_GATEWAY_STATUS_CHECK = BackgroundJob.TYPE_GATEWAY_STATUS_CHECK
BACKGROUND_JOB_TYPE_FINANCIAL_SUMMARY_ROLLUP = BackgroundJob.TYPE_FINANCIAL_SUMMARY_ROLLUP
BACKGROUND_JOB_TYPE_WITHDRAWAL_SETTLEMENT = BackgroundJob.TYPE_WITHDRAWAL_SETTLEMENT
BACKGROUND_JOB_TYPE_NOTIFICATION_EMAIL_RETRY = BackgroundJob.TYPE_NOTIFICATION_EMAIL_RETRY
BACKGROUND_JOB_TYPE_STALE_PENDING_CLEANUP = BackgroundJob.TYPE_STALE_PENDING_CLEANUP
BACKGROUND_JOB_TYPE_DATA_RECONCILIATION = BackgroundJob.TYPE_DATA_RECONCILIATION
BACKGROUND_JOB_TYPE_ANALYTICS_ROLLUP = BackgroundJob.TYPE_ANALYTICS_ROLLUP
PRECOMPUTED_SUMMARY_CACHE_KEY = "mt:summary:precomputed:v1"
PRECOMPUTED_SUMMARY_CACHE_TTL_SECONDS = 60
WEEKDAY_TO_DAY_CODE = {
    0: PricingRule.DAY_OF_WEEK_MON,
    1: PricingRule.DAY_OF_WEEK_TUE,
    2: PricingRule.DAY_OF_WEEK_WED,
    3: PricingRule.DAY_OF_WEEK_THU,
    4: PricingRule.DAY_OF_WEEK_FRI,
    5: PricingRule.DAY_OF_WEEK_SAT,
    6: PricingRule.DAY_OF_WEEK_SUN,
}

BOOKING_FRAUD_REVIEW_SCORE_THRESHOLD_DEFAULT = 70
BOOKING_FRAUD_VELOCITY_WINDOW_MINUTES_DEFAULT = 20
BOOKING_FRAUD_VELOCITY_THRESHOLD_DEFAULT = 3
BOOKING_FRAUD_IP_VELOCITY_THRESHOLD_DEFAULT = 5
BOOKING_FRAUD_SAME_SHOW_WINDOW_HOURS_DEFAULT = 6
BOOKING_FRAUD_SAME_SHOW_THRESHOLD_DEFAULT = 2
BOOKING_FRAUD_HIGH_SEAT_COUNT_DEFAULT = 6
BOOKING_FRAUD_HIGH_AMOUNT_THRESHOLD_DEFAULT = Decimal("5000.00")
BOOKING_FRAUD_LARGE_DISCOUNT_PERCENT_DEFAULT = Decimal("50.00")
BOOKING_FRAUD_NEW_ACCOUNT_DAYS_DEFAULT = 3

SCAN_FRAUD_REVIEW_SCORE_THRESHOLD_DEFAULT = 70
SCAN_FRAUD_EVENT_VALID = "valid"
SCAN_FRAUD_EVENT_TICKET_NOT_FOUND = "ticket_not_found"
SCAN_FRAUD_EVENT_WRONG_VENDOR = "wrong_vendor"
SCAN_FRAUD_EVENT_MISSING_QR_TOKEN = "missing_qr_token"
SCAN_FRAUD_EVENT_INVALID_QR_TOKEN = "invalid_qr_token"
SCAN_FRAUD_EVENT_EXPIRED_QR_TOKEN = "expired_qr_token"
SCAN_FRAUD_EVENT_PAYMENT_INCOMPLETE = "payment_incomplete"
SCAN_FRAUD_EVENT_OUTSIDE_VALID_TIME_WINDOW = "outside_valid_time_window"
SCAN_FRAUD_EVENT_INVALID_REQUEST = "invalid_request"
SCAN_FRAUD_EVENT_RATE_LIMITED = "rate_limited"
SCAN_FRAUD_EVENT_DUPLICATE_TICKET = "duplicate_ticket"


def _clamp_fraud_score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(parsed, 100))


def _booking_fraud_review_threshold() -> int:
    value = _settings_int(
        "BOOKING_FRAUD_REVIEW_SCORE_THRESHOLD",
        BOOKING_FRAUD_REVIEW_SCORE_THRESHOLD_DEFAULT,
    )
    return max(1, min(value, 100))


def booking_fraud_review_threshold() -> int:
    """Return booking fraud score threshold used for manual-review flags."""
    return _booking_fraud_review_threshold()


def _scan_fraud_review_threshold() -> int:
    value = _settings_int(
        "TICKET_VALIDATION_FRAUD_REVIEW_SCORE_THRESHOLD",
        SCAN_FRAUD_REVIEW_SCORE_THRESHOLD_DEFAULT,
    )
    return max(1, min(value, 100))


def scan_fraud_review_threshold() -> int:
    """Return scan fraud score threshold used for manual-review flags."""
    return _scan_fraud_review_threshold()


def _fraud_level_from_score(score: Any) -> str:
    safe_score = _clamp_fraud_score(score)
    if safe_score >= 90:
        return Booking.FRAUD_LEVEL_CRITICAL
    if safe_score >= 70:
        return Booking.FRAUD_LEVEL_HIGH
    if safe_score >= 40:
        return Booking.FRAUD_LEVEL_MEDIUM
    return Booking.FRAUD_LEVEL_LOW


def build_fraud_risk_payload(
    *,
    score: Any,
    signals: Any = None,
    review_threshold: Optional[int] = None,
) -> dict[str, Any]:
    """Build a normalized fraud payload with score, level, and review hint."""
    safe_score = _clamp_fraud_score(score)
    safe_signals = signals if isinstance(signals, list) else []
    threshold = int(review_threshold or 0)
    if threshold <= 0:
        threshold = _booking_fraud_review_threshold()

    return {
        "score": safe_score,
        "level": _fraud_level_from_score(safe_score),
        "signals": safe_signals,
        "requires_manual_review": safe_score >= threshold,
    }


def _build_fraud_signal(
    *,
    code: str,
    title: str,
    weight: int,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    signal = {
        "code": str(code or "").strip()[:64],
        "title": str(title or "").strip()[:120],
        "weight": max(int(weight or 0), 0),
    }
    if isinstance(details, dict) and details:
        signal["details"] = details
    return signal


def _normalize_booking_source_ip(value: Any) -> Optional[str]:
    ip = str(value or "").strip()
    if not ip:
        return None
    return ip[:45]


def _normalize_booking_user_agent(value: Any) -> Optional[str]:
    user_agent = str(value or "").strip()
    if not user_agent:
        return None
    return user_agent[:255]


def assess_scan_fraud_risk(
    event: str,
    *,
    duplicate_attempts: int = 0,
    rate_limit_scope: str = "",
) -> dict[str, Any]:
    """Compute a scan fraud score and normalized risk payload for one scan outcome."""
    normalized_event = str(event or "").strip().lower()
    safe_duplicate_attempts = max(int(duplicate_attempts or 0), 0)

    event_scores = {
        SCAN_FRAUD_EVENT_VALID: 0,
        SCAN_FRAUD_EVENT_TICKET_NOT_FOUND: 90,
        SCAN_FRAUD_EVENT_WRONG_VENDOR: 100,
        SCAN_FRAUD_EVENT_MISSING_QR_TOKEN: 85,
        SCAN_FRAUD_EVENT_INVALID_QR_TOKEN: 80,
        SCAN_FRAUD_EVENT_EXPIRED_QR_TOKEN: 80,
        SCAN_FRAUD_EVENT_PAYMENT_INCOMPLETE: 70,
        SCAN_FRAUD_EVENT_OUTSIDE_VALID_TIME_WINDOW: 65,
        SCAN_FRAUD_EVENT_INVALID_REQUEST: 75,
        SCAN_FRAUD_EVENT_RATE_LIMITED: 40,
    }

    if normalized_event == SCAN_FRAUD_EVENT_DUPLICATE_TICKET:
        base_score = 50
        score = min(100, base_score + (safe_duplicate_attempts * 10))
        signals = [
            _build_fraud_signal(
                code="duplicate_attempt",
                title="Duplicate ticket scan detected",
                weight=score,
                details={"duplicate_attempts": safe_duplicate_attempts},
            )
        ]
    else:
        score = event_scores.get(normalized_event, 50)
        details: dict[str, Any] = {}
        if normalized_event == SCAN_FRAUD_EVENT_RATE_LIMITED and rate_limit_scope:
            details["scope"] = str(rate_limit_scope)
        if normalized_event == SCAN_FRAUD_EVENT_VALID:
            details["outcome"] = "successful_scan"
        signal_code = normalized_event or "scan_outcome"
        signals = [
            _build_fraud_signal(
                code=signal_code,
                title="Ticket scan risk outcome",
                weight=score,
                details=details or None,
            )
        ]

    return build_fraud_risk_payload(
        score=score,
        signals=signals,
        review_threshold=_scan_fraud_review_threshold(),
    )


def assess_booking_fraud_risk(
    *,
    user: User,
    show: Show,
    seat_count: int,
    subtotal_amount: Decimal,
    total_amount: Decimal,
    discount_amount: Decimal,
    loyalty_discount_amount: Decimal,
    subscription_discount_amount: Decimal,
    referral_wallet_used_amount: Decimal,
    source_ip: Optional[str],
    user_agent: Optional[str],
) -> dict[str, Any]:
    """Compute booking fraud score based on velocity, discount stacking, and ticket profile."""
    now = timezone.now()
    safe_seat_count = max(int(seat_count or 0), 0)
    safe_subtotal = _quantize_money(subtotal_amount or Decimal("0"))
    safe_total = _quantize_money(total_amount or Decimal("0"))
    safe_discount = _quantize_money(discount_amount or Decimal("0"))
    safe_loyalty_discount = _quantize_money(loyalty_discount_amount or Decimal("0"))
    safe_subscription_discount = _quantize_money(subscription_discount_amount or Decimal("0"))
    safe_referral_wallet = _quantize_money(referral_wallet_used_amount or Decimal("0"))
    safe_ip = _normalize_booking_source_ip(source_ip)
    safe_user_agent = _normalize_booking_user_agent(user_agent)

    high_seat_threshold = max(
        2,
        _settings_int("BOOKING_FRAUD_HIGH_SEAT_COUNT", BOOKING_FRAUD_HIGH_SEAT_COUNT_DEFAULT),
    )
    high_amount_threshold = _quantize_money(
        _settings_decimal(
            "BOOKING_FRAUD_HIGH_AMOUNT_THRESHOLD",
            BOOKING_FRAUD_HIGH_AMOUNT_THRESHOLD_DEFAULT,
        )
    )
    large_discount_threshold = _settings_decimal(
        "BOOKING_FRAUD_LARGE_DISCOUNT_PERCENT",
        BOOKING_FRAUD_LARGE_DISCOUNT_PERCENT_DEFAULT,
    )
    if large_discount_threshold < Decimal("1"):
        large_discount_threshold = Decimal("1")
    if large_discount_threshold > Decimal("100"):
        large_discount_threshold = Decimal("100")

    velocity_window_minutes = max(
        5,
        _settings_int(
            "BOOKING_FRAUD_VELOCITY_WINDOW_MINUTES",
            BOOKING_FRAUD_VELOCITY_WINDOW_MINUTES_DEFAULT,
        ),
    )
    velocity_threshold = max(
        2,
        _settings_int("BOOKING_FRAUD_VELOCITY_THRESHOLD", BOOKING_FRAUD_VELOCITY_THRESHOLD_DEFAULT),
    )
    ip_velocity_threshold = max(
        3,
        _settings_int(
            "BOOKING_FRAUD_IP_VELOCITY_THRESHOLD",
            BOOKING_FRAUD_IP_VELOCITY_THRESHOLD_DEFAULT,
        ),
    )
    same_show_window_hours = max(
        1,
        _settings_int(
            "BOOKING_FRAUD_SAME_SHOW_WINDOW_HOURS",
            BOOKING_FRAUD_SAME_SHOW_WINDOW_HOURS_DEFAULT,
        ),
    )
    same_show_threshold = max(
        2,
        _settings_int(
            "BOOKING_FRAUD_SAME_SHOW_THRESHOLD",
            BOOKING_FRAUD_SAME_SHOW_THRESHOLD_DEFAULT,
        ),
    )
    new_account_days = max(
        1,
        _settings_int("BOOKING_FRAUD_NEW_ACCOUNT_DAYS", BOOKING_FRAUD_NEW_ACCOUNT_DAYS_DEFAULT),
    )

    velocity_since = now - timedelta(minutes=velocity_window_minutes)
    recent_user_bookings = Booking.objects.filter(
        user_id=user.id,
        booking_date__gte=velocity_since,
    ).exclude(
        booking_status__iexact=BOOKING_STATUS_CANCELLED,
    )
    recent_user_count = recent_user_bookings.count()

    recent_ip_count = 0
    if safe_ip:
        recent_ip_count = Booking.objects.filter(
            source_ip=safe_ip,
            booking_date__gte=velocity_since,
        ).exclude(
            booking_status__iexact=BOOKING_STATUS_CANCELLED,
        ).count()

    same_show_since = now - timedelta(hours=same_show_window_hours)
    same_show_count = Booking.objects.filter(
        user_id=user.id,
        showtime__movie_id=show.movie_id,
        showtime__screen__vendor_id=show.vendor_id,
        booking_date__gte=same_show_since,
    ).exclude(
        booking_status__iexact=BOOKING_STATUS_CANCELLED,
    ).count()

    aggregate_discount = _quantize_money(
        safe_discount + safe_loyalty_discount + safe_subscription_discount + safe_referral_wallet
    )
    discount_percent = Decimal("0")
    if safe_subtotal > Decimal("0"):
        discount_percent = (aggregate_discount / safe_subtotal) * Decimal("100")

    score = 0
    signals: list[dict[str, Any]] = []

    if safe_seat_count >= high_seat_threshold:
        seat_delta = safe_seat_count - high_seat_threshold
        weight = min(25, 12 + (seat_delta * 2))
        score += weight
        signals.append(
            _build_fraud_signal(
                code="high_seat_count",
                title="Large seat count in one booking",
                weight=weight,
                details={"seat_count": safe_seat_count, "threshold": high_seat_threshold},
            )
        )

    if high_amount_threshold > Decimal("0") and safe_total >= high_amount_threshold:
        weight = 10
        score += weight
        signals.append(
            _build_fraud_signal(
                code="high_booking_value",
                title="High-value booking",
                weight=weight,
                details={
                    "booking_total": float(safe_total),
                    "threshold": float(high_amount_threshold),
                },
            )
        )

    if discount_percent >= large_discount_threshold:
        weight = 20
        score += weight
        signals.append(
            _build_fraud_signal(
                code="large_discount_stack",
                title="Large stacked discount detected",
                weight=weight,
                details={
                    "discount_percent": round(float(discount_percent), 2),
                    "threshold": float(large_discount_threshold),
                },
            )
        )
    elif discount_percent >= (large_discount_threshold * Decimal("0.70")):
        weight = 12
        score += weight
        signals.append(
            _build_fraud_signal(
                code="moderate_discount_stack",
                title="Moderate stacked discount detected",
                weight=weight,
                details={
                    "discount_percent": round(float(discount_percent), 2),
                    "threshold": round(float(large_discount_threshold * Decimal("0.70")), 2),
                },
            )
        )

    if recent_user_count >= velocity_threshold:
        repeat_count = (recent_user_count - velocity_threshold) + 1
        weight = min(35, 18 + (repeat_count * 5))
        score += weight
        signals.append(
            _build_fraud_signal(
                code="user_velocity_spike",
                title="Rapid repeat bookings by account",
                weight=weight,
                details={
                    "recent_booking_count": recent_user_count,
                    "threshold": velocity_threshold,
                    "window_minutes": velocity_window_minutes,
                },
            )
        )

    if safe_ip and recent_ip_count >= ip_velocity_threshold:
        repeat_ip_count = (recent_ip_count - ip_velocity_threshold) + 1
        weight = min(30, 15 + (repeat_ip_count * 4))
        score += weight
        signals.append(
            _build_fraud_signal(
                code="ip_velocity_spike",
                title="Rapid repeat bookings from same IP",
                weight=weight,
                details={
                    "source_ip": safe_ip,
                    "recent_booking_count": recent_ip_count,
                    "threshold": ip_velocity_threshold,
                    "window_minutes": velocity_window_minutes,
                },
            )
        )

    if same_show_count >= same_show_threshold:
        repeat_show_count = (same_show_count - same_show_threshold) + 1
        weight = min(20, 10 + (repeat_show_count * 3))
        score += weight
        signals.append(
            _build_fraud_signal(
                code="same_show_repeat",
                title="Repeated bookings for same vendor show",
                weight=weight,
                details={
                    "recent_booking_count": same_show_count,
                    "threshold": same_show_threshold,
                    "window_hours": same_show_window_hours,
                },
            )
        )

    user_created_at = getattr(user, "created_at", None)
    if user_created_at:
        account_age = now - ensure_utc_datetime(user_created_at)
        if account_age <= timedelta(days=new_account_days):
            weight = 8
            score += weight
            signals.append(
                _build_fraud_signal(
                    code="new_account_booking",
                    title="Booking made from a newly created account",
                    weight=weight,
                    details={"account_age_days": round(account_age.total_seconds() / 86400, 2)},
                )
            )

    if not safe_ip or not safe_user_agent:
        weight = 5
        score += weight
        signals.append(
            _build_fraud_signal(
                code="missing_client_fingerprint",
                title="Missing client fingerprint data",
                weight=weight,
                details={
                    "has_ip": bool(safe_ip),
                    "has_user_agent": bool(safe_user_agent),
                },
            )
        )

    return build_fraud_risk_payload(
        score=score,
        signals=signals,
        review_threshold=_booking_fraud_review_threshold(),
    )


def _transaction_uuid_from_payment_method(payment_method: Any) -> Optional[str]:
    """Extract eSewa transaction UUID from payment_method text."""
    raw = str(payment_method or "").strip()
    if not raw:
        return None
    upper_prefix = ESEWA_PAYMENT_METHOD_PREFIX.upper()
    if raw.upper().startswith(upper_prefix):
        extracted = raw[len(ESEWA_PAYMENT_METHOD_PREFIX):].strip()
        return extracted or None
    return None


def _referral_wallet_cache_key(user_id: int) -> str:
    return f"{REFERRAL_CACHE_KEY_PREFIX}{int(user_id)}"


def _clear_referral_wallet_cache(user_id: int) -> None:
    cache.delete(_referral_wallet_cache_key(user_id))


def _settings_decimal(name: str, default: Decimal) -> Decimal:
    try:
        return Decimal(str(getattr(settings, name, default)))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal(default)


def _settings_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):
        return int(default)


def _get_referral_policy() -> ReferralPolicy:
    defaults = {
        "referrer_reward_amount": REFERRAL_REWARD_REFERRER_DEFAULT,
        "referred_reward_amount": REFERRAL_REWARD_REFERRED_DEFAULT,
        "reward_hold_period_days": REFERRAL_REWARD_HOLD_PERIOD_DAYS_DEFAULT,
        "reward_expiry_days": REFERRAL_REWARD_EXPIRY_DAYS_DEFAULT,
        "wallet_cap_percent": REFERRAL_WALLET_CAP_PERCENT_DEFAULT,
        "max_signups_per_ip_per_day": REFERRAL_MAX_IP_SIGNUPS_PER_DAY_DEFAULT,
        "max_signups_per_device_per_day": REFERRAL_MAX_DEVICE_SIGNUPS_PER_DAY_DEFAULT,
        "auto_approve_rewards": True,
        "is_active": True,
    }
    policy, _ = ReferralPolicy.objects.get_or_create(key="default", defaults=defaults)
    return policy


def _referral_reward_amounts() -> tuple[Decimal, Decimal]:
    policy = _get_referral_policy()
    if policy and bool(policy.is_active):
        referrer_amount = _quantize_money(policy.referrer_reward_amount)
        referred_amount = _quantize_money(policy.referred_reward_amount)
    else:
        referrer_amount = _quantize_money(
            _settings_decimal("REFERRAL_REWARD_REFERRER_AMOUNT", REFERRAL_REWARD_REFERRER_DEFAULT)
        )
        referred_amount = _quantize_money(
            _settings_decimal("REFERRAL_REWARD_REFERRED_AMOUNT", REFERRAL_REWARD_REFERRED_DEFAULT)
        )
    if referrer_amount < Decimal("0"):
        referrer_amount = Decimal("0.00")
    if referred_amount < Decimal("0"):
        referred_amount = Decimal("0.00")
    return referrer_amount, referred_amount


def _referral_signup_reward_amount() -> Decimal:
    amount = _quantize_money(
        _settings_decimal("REFERRAL_SIGNUP_REWARD_AMOUNT", REFERRAL_SIGNUP_REWARD_DEFAULT)
    )
    if amount < Decimal("0"):
        return Decimal("0.00")
    return amount


def _referral_reward_expiry_days() -> int:
    policy = _get_referral_policy()
    if policy and bool(policy.is_active):
        value = int(policy.reward_expiry_days or REFERRAL_REWARD_EXPIRY_DAYS_DEFAULT)
    else:
        value = _settings_int("REFERRAL_REWARD_EXPIRY_DAYS", REFERRAL_REWARD_EXPIRY_DAYS_DEFAULT)
    return max(1, value)


def _referral_reward_hold_period_days() -> int:
    policy = _get_referral_policy()
    if policy and bool(policy.is_active):
        value = int(policy.reward_hold_period_days or REFERRAL_REWARD_HOLD_PERIOD_DAYS_DEFAULT)
    else:
        value = _settings_int("REFERRAL_REWARD_HOLD_PERIOD_DAYS", REFERRAL_REWARD_HOLD_PERIOD_DAYS_DEFAULT)
    return max(0, value)


def _referral_wallet_cap_percent() -> Decimal:
    policy = _get_referral_policy()
    if policy and bool(policy.is_active):
        value = _quantize_money(policy.wallet_cap_percent)
    else:
        value = _quantize_money(
            _settings_decimal("REFERRAL_WALLET_MAX_BOOKING_PERCENT", REFERRAL_WALLET_CAP_PERCENT_DEFAULT)
        )
    if value < Decimal("0"):
        return Decimal("0.00")
    if value > Decimal("100"):
        return Decimal("100.00")
    return value


def _extract_client_ip(request: Any) -> Optional[str]:
    if not request:
        return None
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        return first_ip or None
    remote_addr = str(request.META.get("REMOTE_ADDR") or "").strip()
    return remote_addr or None


def _extract_client_user_agent(request: Any) -> Optional[str]:
    if not request:
        return None
    value = str(request.META.get("HTTP_USER_AGENT") or "").strip()
    return value[:255] or None


def _extract_device_fingerprint(request: Any, payload: Optional[dict[str, Any]] = None) -> Optional[str]:
    source = payload or {}
    value = str(
        coalesce(
            source,
            "device_fingerprint",
            "deviceFingerprint",
            default=request.META.get("HTTP_X_DEVICE_FINGERPRINT") if request else None,
        )
        or ""
    ).strip()
    return value[:128] or None


def ensure_user_referral_code(user: User) -> str:
    """Ensure every user has a unique referral code."""
    existing = str(getattr(user, "referral_code", "") or "").strip().upper()
    if existing:
        return existing

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(200):
        candidate = "".join(random.choice(alphabet) for _ in range(REFERRAL_CODE_LENGTH))
        if not candidate:
            continue
        if User.objects.filter(referral_code__iexact=candidate).exists():
            continue
        user.referral_code = candidate
        user.save(update_fields=["referral_code"])
        return candidate

    # Fallback with UUID suffix when random generation repeatedly collides.
    fallback = uuid.uuid4().hex[:REFERRAL_CODE_LENGTH].upper()
    user.referral_code = fallback
    user.save(update_fields=["referral_code"])
    return fallback


def _update_signup_metadata(
    user: User,
    *,
    signup_ip: Optional[str],
    signup_user_agent: Optional[str],
    signup_device_fingerprint: Optional[str],
) -> None:
    changed_fields: list[str] = []
    if signup_ip and user.signup_ip_address != signup_ip:
        user.signup_ip_address = signup_ip
        changed_fields.append("signup_ip_address")
    if signup_user_agent and user.signup_user_agent != signup_user_agent:
        user.signup_user_agent = signup_user_agent
        changed_fields.append("signup_user_agent")
    if signup_device_fingerprint and user.signup_device_fingerprint != signup_device_fingerprint:
        user.signup_device_fingerprint = signup_device_fingerprint
        changed_fields.append("signup_device_fingerprint")
    if changed_fields:
        user.save(update_fields=changed_fields)


def _referral_anti_fraud_reason(
    *,
    referrer: User,
    signup_email: str,
    signup_phone: str,
    signup_ip: Optional[str],
    signup_device_fingerprint: Optional[str],
) -> Optional[str]:
    """Return a reason string when referral should be blocked by policy."""
    if not referrer:
        return "Referrer account was not found."

    if str(referrer.email or "").strip().lower() == str(signup_email or "").strip().lower():
        return "Self-referral is not allowed."

    normalized_referrer_phone = str(referrer.phone_number or "").strip()
    normalized_signup_phone = str(signup_phone or "").strip()
    if normalized_referrer_phone and normalized_referrer_phone == normalized_signup_phone:
        return "Self-referral is not allowed."

    referrer_signup_ip = str(referrer.signup_ip_address or "").strip()
    if signup_ip and referrer_signup_ip and signup_ip == referrer_signup_ip:
        return "Referral from the same IP is blocked by anti-fraud policy."

    referrer_device = str(referrer.signup_device_fingerprint or "").strip()
    if signup_device_fingerprint and referrer_device and signup_device_fingerprint == referrer_device:
        return "Referral from the same device is blocked by anti-fraud policy."

    lookback_since = timezone.now() - timedelta(days=1)
    policy = _get_referral_policy()
    if policy and bool(policy.is_active):
        ip_limit = max(1, int(policy.max_signups_per_ip_per_day or REFERRAL_MAX_IP_SIGNUPS_PER_DAY_DEFAULT))
        device_limit = max(
            1,
            int(policy.max_signups_per_device_per_day or REFERRAL_MAX_DEVICE_SIGNUPS_PER_DAY_DEFAULT),
        )
    else:
        ip_limit = max(
            1,
            _settings_int(
                "REFERRAL_MAX_SIGNUPS_PER_IP_PER_DAY",
                REFERRAL_MAX_IP_SIGNUPS_PER_DAY_DEFAULT,
            ),
        )
        device_limit = max(
            1,
            _settings_int(
                "REFERRAL_MAX_SIGNUPS_PER_DEVICE_PER_DAY",
                REFERRAL_MAX_DEVICE_SIGNUPS_PER_DAY_DEFAULT,
            ),
        )

    if signup_ip:
        ip_count = (
            Referral.objects.filter(
                signup_ip_address=signup_ip,
                created_at__gte=lookback_since,
            )
            .exclude(status=Referral.STATUS_REJECTED)
            .count()
        )
        if ip_count >= ip_limit:
            return "Too many referral signups detected from this IP."

    if signup_device_fingerprint:
        device_count = (
            Referral.objects.filter(
                signup_device_fingerprint=signup_device_fingerprint,
                created_at__gte=lookback_since,
            )
            .exclude(status=Referral.STATUS_REJECTED)
            .count()
        )
        if device_count >= device_limit:
            return "Too many referral signups detected from this device."

    return None


def _referral_wallet_for_user(user: User, *, lock_for_update: bool = False) -> ReferralWallet:
    wallet, _ = ReferralWallet.objects.get_or_create(user=user)
    if lock_for_update:
        wallet = ReferralWallet.objects.select_for_update().get(pk=wallet.pk)
    return wallet


def get_referral_wallet_snapshot(user: User, *, use_cache: bool = True) -> dict[str, Any]:
    if not user or not user.id:
        return {
            "user_id": None,
            "balance": 0.0,
            "spendable_balance": 0.0,
            "total_credited": 0.0,
            "total_debited": 0.0,
            "total_expired": 0.0,
            "updated_at": None,
        }

    cache_key = _referral_wallet_cache_key(user.id)
    if use_cache:
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    wallet = _referral_wallet_for_user(user)
    wallet = _recalculate_referral_wallet_snapshot(wallet)
    balance = _quantize_money(wallet.balance)
    now_value = timezone.now()
    spendable = _quantize_money(
        wallet.transactions.filter(
            transaction_type=ReferralTransaction.TYPE_CREDIT,
            status=ReferralTransaction.STATUS_COMPLETED,
        )
        .filter(Q(available_at__isnull=True) | Q(available_at__lte=now_value))
        .aggregate(total=Sum("remaining_amount"))
        .get("total")
        or Decimal("0")
    )
    if spendable < Decimal("0"):
        spendable = Decimal("0.00")
    payload = {
        "user_id": user.id,
        "balance": float(balance),
        "spendable_balance": float(spendable),
        "locked_balance": float(_quantize_money(balance - spendable)) if balance > spendable else 0.0,
        "total_credited": float(_quantize_money(wallet.total_credited)),
        "total_debited": float(_quantize_money(wallet.total_debited)),
        "total_expired": float(_quantize_money(wallet.total_expired)),
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
    }
    cache.set(cache_key, payload, timeout=REFERRAL_CACHE_TTL_SECONDS)
    return payload


def _create_referral_transaction(
    *,
    wallet: ReferralWallet,
    user: User,
    amount: Decimal,
    transaction_type: str,
    reason: str,
    status_value: str = ReferralTransaction.STATUS_COMPLETED,
    referral: Optional[Referral] = None,
    booking: Optional[Booking] = None,
    available_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    remaining_amount: Optional[Decimal] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> ReferralTransaction:
    return ReferralTransaction.objects.create(
        wallet=wallet,
        user=user,
        referral=referral,
        booking=booking,
        transaction_type=transaction_type,
        status=status_value,
        reason=reason,
        amount=_quantize_money(amount),
        remaining_amount=_quantize_money(remaining_amount if remaining_amount is not None else Decimal("0")),
        available_at=available_at,
        expires_at=expires_at,
        processed_at=timezone.now(),
        metadata=metadata or {},
    )


def _referral_transaction_is_spendable(tx: ReferralTransaction, now_value: Optional[datetime] = None) -> bool:
    if not tx or tx.transaction_type != ReferralTransaction.TYPE_CREDIT:
        return False
    if tx.status != ReferralTransaction.STATUS_COMPLETED:
        return False
    available_at = tx.available_at
    if not available_at:
        return True
    current_time = now_value or timezone.now()
    return available_at <= current_time


def _consume_referral_credit_buckets(user_id: int, amount: Decimal) -> None:
    """Reduce remaining credit buckets in FIFO order to support accurate expiry."""
    pending = _quantize_money(amount)
    if pending <= Decimal("0"):
        return

    credit_rows = (
        ReferralTransaction.objects.select_for_update()
        .filter(
            user_id=user_id,
            transaction_type=ReferralTransaction.TYPE_CREDIT,
            status=ReferralTransaction.STATUS_COMPLETED,
            remaining_amount__gt=Decimal("0"),
        )
        .filter(Q(available_at__isnull=True) | Q(available_at__lte=timezone.now()))
        .order_by("expires_at", "created_at", "id")
    )
    for row in credit_rows:
        if pending <= Decimal("0"):
            break
        available = _quantize_money(row.remaining_amount)
        if available <= Decimal("0"):
            continue
        consumed = available if available <= pending else pending
        row.remaining_amount = _quantize_money(available - consumed)
        row.save(update_fields=["remaining_amount", "updated_at"])
        pending = _quantize_money(pending - consumed)


def _credit_referral_wallet(
    *,
    user: User,
    amount: Decimal,
    reason: str,
    referral: Optional[Referral] = None,
    booking: Optional[Booking] = None,
    expires_at: Optional[datetime] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[ReferralTransaction]:
    credit_amount = _quantize_money(amount)
    if credit_amount <= Decimal("0"):
        return None

    with transaction.atomic():
        wallet = _referral_wallet_for_user(user, lock_for_update=True)
        tx = _create_referral_transaction(
            wallet=wallet,
            user=user,
            amount=credit_amount,
            transaction_type=ReferralTransaction.TYPE_CREDIT,
            reason=reason,
            status_value=ReferralTransaction.STATUS_COMPLETED,
            referral=referral,
            booking=booking,
            available_at=timezone.now() + timedelta(days=_referral_reward_hold_period_days()),
            expires_at=expires_at,
            remaining_amount=credit_amount,
            metadata=metadata,
        )
        _recalculate_referral_wallet_snapshot(wallet)

    _clear_referral_wallet_cache(user.id)
    return tx


def _debit_referral_wallet(
    *,
    user: User,
    amount: Decimal,
    reason: str,
    referral: Optional[Referral] = None,
    booking: Optional[Booking] = None,
    metadata: Optional[dict[str, Any]] = None,
    require_available_balance: bool = True,
    allow_negative_balance: bool = False,
    transaction_type: str = ReferralTransaction.TYPE_DEBIT,
) -> tuple[Optional[ReferralTransaction], Optional[dict[str, Any]], int]:
    debit_amount = _quantize_money(amount)
    if debit_amount <= Decimal("0"):
        return None, None, status.HTTP_200_OK

    with transaction.atomic():
        wallet = _referral_wallet_for_user(user, lock_for_update=True)
        wallet = _recalculate_referral_wallet_snapshot(wallet)
        current_balance = _quantize_money(wallet.balance)
        spendable_balance = _quantize_money(
            wallet.transactions.filter(
                transaction_type=ReferralTransaction.TYPE_CREDIT,
                status=ReferralTransaction.STATUS_COMPLETED,
            )
            .filter(Q(available_at__isnull=True) | Q(available_at__lte=timezone.now()))
            .aggregate(total=Sum("remaining_amount"))
            .get("total")
            or Decimal("0")
        )
        if require_available_balance and spendable_balance < debit_amount:
            return (
                None,
                {
                    "message": "Insufficient referral wallet balance.",
                    "available_balance": float(spendable_balance),
                    "requested_amount": float(debit_amount),
                },
                status.HTTP_400_BAD_REQUEST,
            )

        if not allow_negative_balance and spendable_balance < debit_amount:
            return (
                None,
                {
                    "message": "Referral wallet cannot go negative.",
                    "available_balance": float(spendable_balance),
                    "requested_amount": float(debit_amount),
                },
                status.HTTP_400_BAD_REQUEST,
            )
        _consume_referral_credit_buckets(user.id, debit_amount)

        tx = _create_referral_transaction(
            wallet=wallet,
            user=user,
            amount=debit_amount,
            transaction_type=transaction_type,
            reason=reason,
            status_value=ReferralTransaction.STATUS_COMPLETED,
            referral=referral,
            booking=booking,
            remaining_amount=Decimal("0"),
            metadata=metadata,
        )
        _recalculate_referral_wallet_snapshot(wallet)

    _clear_referral_wallet_cache(user.id)
    return tx, None, status.HTTP_200_OK


def preview_referral_wallet_usage_for_user(
    user: User,
    *,
    subtotal: Decimal,
    requested_amount: Optional[Decimal] = None,
) -> dict[str, Any]:
    subtotal_amount = _quantize_money(subtotal)
    if subtotal_amount < Decimal("0"):
        subtotal_amount = Decimal("0.00")

    wallet_snapshot = get_referral_wallet_snapshot(user)
    wallet_balance = _quantize_money(wallet_snapshot.get("balance") or Decimal("0"))
    spendable_balance = _quantize_money(wallet_snapshot.get("spendable_balance") or Decimal("0"))

    cap_percent = _referral_wallet_cap_percent()
    cap_amount = _quantize_money((subtotal_amount * cap_percent) / Decimal("100"))
    max_usable_amount = min(subtotal_amount, cap_amount, spendable_balance)

    normalized_requested = (
        _quantize_money(requested_amount)
        if requested_amount is not None
        else max_usable_amount
    )
    if normalized_requested < Decimal("0"):
        normalized_requested = Decimal("0.00")

    applied_amount = min(max_usable_amount, normalized_requested)
    remaining_after_wallet = _quantize_money(subtotal_amount - applied_amount)
    if remaining_after_wallet < Decimal("0"):
        remaining_after_wallet = Decimal("0.00")

    return {
        "subtotal": float(subtotal_amount),
        "wallet_balance": float(wallet_balance),
        "spendable_balance": float(spendable_balance),
        "cap_percent": float(cap_percent),
        "cap_amount": float(cap_amount),
        "max_usable_amount": float(max_usable_amount),
        "requested_amount": float(normalized_requested),
        "applied_amount": float(applied_amount),
        "remaining_total": float(remaining_after_wallet),
    }


def _mark_referral_expired(referral: Referral) -> None:
    if not referral:
        return
    if referral.status in {Referral.STATUS_REJECTED, Referral.STATUS_REVERSED, Referral.STATUS_EXPIRED}:
        return
    referral.status = Referral.STATUS_EXPIRED
    referral.rejection_reason = referral.rejection_reason or "Referral expired before reward trigger."
    referral.save(update_fields=["status", "rejection_reason", "updated_at"])


def expire_referral_wallet_credits(
    *,
    now: Optional[datetime] = None,
    user_id: Optional[int] = None,
) -> dict[str, Any]:
    """Expire unused referral credits and mark pending referrals past expiry."""
    current_time = now or timezone.now()
    expired_transactions = 0
    expired_amount = Decimal("0.00")
    expired_referrals = 0

    credits = ReferralTransaction.objects.filter(
        transaction_type=ReferralTransaction.TYPE_CREDIT,
        status=ReferralTransaction.STATUS_COMPLETED,
        expires_at__isnull=False,
        expires_at__lte=current_time,
        remaining_amount__gt=Decimal("0"),
    )
    if user_id:
        credits = credits.filter(user_id=user_id)

    for tx in credits.order_by("expires_at", "id"):
        with transaction.atomic():
            locked_tx = ReferralTransaction.objects.select_for_update().filter(pk=tx.id).first()
            if not locked_tx:
                continue
            if locked_tx.status != ReferralTransaction.STATUS_COMPLETED:
                continue
            if not locked_tx.expires_at or locked_tx.expires_at > current_time:
                continue

            remaining = _quantize_money(locked_tx.remaining_amount)
            if remaining <= Decimal("0"):
                continue

            wallet = ReferralWallet.objects.select_for_update().filter(pk=locked_tx.wallet_id).first()
            if not wallet:
                locked_tx.remaining_amount = Decimal("0.00")
                locked_tx.status = ReferralTransaction.STATUS_EXPIRED
                locked_tx.processed_at = current_time
                locked_tx.save(update_fields=["remaining_amount", "status", "processed_at", "updated_at"])
                expired_transactions += 1
                expired_amount = _quantize_money(expired_amount + remaining)
                continue

            _create_referral_transaction(
                wallet=wallet,
                user=wallet.user,
                amount=remaining,
                transaction_type=ReferralTransaction.TYPE_EXPIRE,
                reason=ReferralTransaction.REASON_EXPIRY,
                status_value=ReferralTransaction.STATUS_EXPIRED,
                referral=locked_tx.referral,
                booking=locked_tx.booking,
                remaining_amount=Decimal("0.00"),
                metadata={"source_transaction_id": locked_tx.id},
            )
            _recalculate_referral_wallet_snapshot(wallet)

            locked_tx.remaining_amount = Decimal("0.00")
            locked_tx.status = ReferralTransaction.STATUS_EXPIRED
            locked_tx.processed_at = current_time
            locked_tx.save(update_fields=["remaining_amount", "status", "processed_at", "updated_at"])

            _clear_referral_wallet_cache(wallet.user_id)
            expired_transactions += 1
            expired_amount = _quantize_money(expired_amount + remaining)

    pending_referrals = Referral.objects.filter(
        status=Referral.STATUS_PENDING,
        expires_at__isnull=False,
        expires_at__lte=current_time,
    )
    if user_id:
        pending_referrals = pending_referrals.filter(Q(referrer_id=user_id) | Q(referred_user_id=user_id))

    for referral in pending_referrals:
        _mark_referral_expired(referral)
        expired_referrals += 1

    return {
        "expired_transactions": expired_transactions,
        "expired_amount": float(expired_amount),
        "expired_referrals": expired_referrals,
    }


def _link_referral_on_signup(
    *,
    user: User,
    referral_code: str,
    signup_ip: Optional[str],
    signup_user_agent: Optional[str],
    signup_device_fingerprint: Optional[str],
) -> dict[str, Any]:
    normalized_code = str(referral_code or "").strip().upper()
    if not normalized_code:
        return {"applied": False, "message": "Referral code was not provided."}

    referrer = User.objects.filter(referral_code__iexact=normalized_code).first()
    if not referrer:
        return {"applied": False, "message": "Referral code is invalid."}

    anti_fraud_reason = _referral_anti_fraud_reason(
        referrer=referrer,
        signup_email=user.email,
        signup_phone=user.phone_number,
        signup_ip=signup_ip,
        signup_device_fingerprint=signup_device_fingerprint,
    )
    expires_at = timezone.now() + timedelta(days=_referral_reward_expiry_days())

    referral = Referral.objects.create(
        referrer=referrer,
        referred_user=user,
        referral_code=normalized_code,
        status=Referral.STATUS_PENDING if not anti_fraud_reason else Referral.STATUS_REJECTED,
        rejection_reason=anti_fraud_reason,
        signup_ip_address=signup_ip,
        signup_user_agent=signup_user_agent,
        signup_device_fingerprint=signup_device_fingerprint,
        expires_at=expires_at,
        metadata={
            "signup_email": user.email,
            "signup_phone": user.phone_number,
        },
    )

    if anti_fraud_reason:
        return {
            "applied": False,
            "status": referral.status,
            "message": anti_fraud_reason,
            "referral_id": referral.id,
        }

    now_value = timezone.now()
    signup_reward_amount = _referral_signup_reward_amount()

    referrer_tx = None
    if signup_reward_amount > Decimal("0"):
        referrer_tx = _credit_referral_wallet(
            user=referrer,
            amount=signup_reward_amount,
            reason=ReferralTransaction.REASON_REFERRER_REWARD,
            referral=referral,
            expires_at=expires_at,
            metadata={
                "source": "signup_referral",
                "reward_mode": "SIGNUP_IMMEDIATE",
                "referred_user_id": user.id,
            },
        )

    referral.status = Referral.STATUS_REWARDED
    referral.rewarded_at = now_value
    referral.metadata = {
        **(referral.metadata or {}),
        "reward_mode": "SIGNUP_IMMEDIATE",
        "referrer_reward_amount": float(signup_reward_amount),
        "referrer_transaction_id": referrer_tx.id if referrer_tx else None,
    }
    referral.save(update_fields=["status", "rewarded_at", "metadata", "updated_at"])

    reward_points = (
        int(signup_reward_amount)
        if signup_reward_amount == signup_reward_amount.to_integral_value()
        else float(signup_reward_amount)
    )

    return {
        "applied": True,
        "status": referral.status,
        "message": f"Referral linked. Referrer received {reward_points} points instantly.",
        "referral_id": referral.id,
        "referrer_id": referrer.id,
        "referrer_reward_points": reward_points,
    }


def process_referral_reward_for_booking(booking: Optional[Booking]) -> dict[str, Any]:
    """Credit referrer + referred wallets when referred user completes first booking."""
    if not booking or not booking.id or not booking.user_id:
        return {"awarded": False, "message": "Booking context unavailable."}

    booking_status = str(booking.booking_status or "").strip().lower()
    if booking_status != BOOKING_STATUS_CONFIRMED.lower():
        return {"awarded": False, "message": "Booking is not confirmed."}

    with transaction.atomic():
        referral = (
            Referral.objects.select_for_update()
            .select_related("referrer", "referred_user")
            .filter(referred_user_id=booking.user_id)
            .order_by("-created_at", "-id")
            .first()
        )
        if not referral:
            return {"awarded": False, "message": "Referral not found for user."}
        if referral.status != Referral.STATUS_PENDING:
            return {"awarded": False, "message": f"Referral status is {referral.status}."}

        policy = _get_referral_policy()
        if policy and bool(policy.is_active) and not bool(policy.auto_approve_rewards):
            metadata = referral.metadata if isinstance(referral.metadata, dict) else {}
            approved = bool(metadata.get("admin_approved")) or bool(metadata.get("admin_approved_at"))
            if not approved:
                return {"awarded": False, "message": "Referral is pending admin approval."}

        now_value = timezone.now()
        if referral.expires_at and referral.expires_at <= now_value:
            _mark_referral_expired(referral)
            return {"awarded": False, "message": "Referral reward eligibility has expired."}

        successful_bookings = Booking.objects.filter(
            user_id=booking.user_id,
            booking_status__iexact=BOOKING_STATUS_CONFIRMED,
        ).count()
        if successful_bookings != 1:
            return {"awarded": False, "message": "Not the first successful booking."}

        referrer_amount, referred_amount = _referral_reward_amounts()
        credit_expiry = now_value + timedelta(days=_referral_reward_expiry_days())

        referrer_tx = _credit_referral_wallet(
            user=referral.referrer,
            amount=referrer_amount,
            reason=ReferralTransaction.REASON_REFERRER_REWARD,
            referral=referral,
            booking=booking,
            expires_at=credit_expiry,
            metadata={
                "booking_id": booking.id,
                "recipient_role": "referrer",
                "referred_user_id": booking.user_id,
            },
        )
        referred_tx = _credit_referral_wallet(
            user=referral.referred_user,
            amount=referred_amount,
            reason=ReferralTransaction.REASON_REFERRED_REWARD,
            referral=referral,
            booking=booking,
            expires_at=credit_expiry,
            metadata={
                "booking_id": booking.id,
                "recipient_role": "referred",
                "referrer_id": referral.referrer_id,
            },
        )

        referral.status = Referral.STATUS_REWARDED
        referral.reward_trigger_booking = booking
        referral.rewarded_at = now_value
        referral.metadata = {
            **(referral.metadata or {}),
            "referrer_reward_amount": float(referrer_amount),
            "referred_reward_amount": float(referred_amount),
            "reward_credit_expiry": credit_expiry.isoformat(),
            "referrer_transaction_id": referrer_tx.id if referrer_tx else None,
            "referred_transaction_id": referred_tx.id if referred_tx else None,
        }
        referral.save(
            update_fields=[
                "status",
                "reward_trigger_booking",
                "rewarded_at",
                "metadata",
                "updated_at",
            ]
        )

    return {
        "awarded": True,
        "referral_id": referral.id,
        "referrer_reward": float(referrer_amount),
        "referred_reward": float(referred_amount),
    }


def reverse_referral_effects_for_booking(
    booking: Optional[Booking],
    *,
    reason: str,
) -> dict[str, Any]:
    """Reverse booking wallet usage and awarded referral rewards on cancellation/refund."""
    if not booking or not booking.id:
        return {"wallet_refund_amount": 0.0, "reversed_reward_amount": 0.0}

    wallet_refund_amount = Decimal("0.00")
    reversed_reward_amount = Decimal("0.00")

    with transaction.atomic():
        locked_booking = Booking.objects.select_for_update().filter(pk=booking.id).first()
        if not locked_booking:
            return {"wallet_refund_amount": 0.0, "reversed_reward_amount": 0.0}

        wallet_used = _quantize_money(locked_booking.referral_wallet_used_amount or Decimal("0"))
        already_refunded = _quantize_money(locked_booking.referral_wallet_refunded_amount or Decimal("0"))
        pending_refund = _quantize_money(wallet_used - already_refunded)
        if pending_refund < Decimal("0"):
            pending_refund = Decimal("0.00")

        if pending_refund > Decimal("0") and locked_booking.user_id:
            existing_refund_tx = ReferralTransaction.objects.filter(
                booking_id=locked_booking.id,
                user_id=locked_booking.user_id,
                reason=ReferralTransaction.REASON_BOOKING_WALLET_REFUND,
                transaction_type=ReferralTransaction.TYPE_CREDIT,
                status=ReferralTransaction.STATUS_COMPLETED,
            ).first()
            if not existing_refund_tx:
                _credit_referral_wallet(
                    user=locked_booking.user,
                    amount=pending_refund,
                    reason=ReferralTransaction.REASON_BOOKING_WALLET_REFUND,
                    booking=locked_booking,
                    metadata={"reason": reason or "Booking cancellation refund"},
                )
            wallet_refund_amount = pending_refund
            locked_booking.referral_wallet_refunded_amount = _quantize_money(already_refunded + pending_refund)
            locked_booking.save(update_fields=["referral_wallet_refunded_amount"])

        referral = (
            Referral.objects.select_for_update()
            .filter(reward_trigger_booking_id=locked_booking.id)
            .order_by("-id")
            .first()
        )
        if not referral or referral.status != Referral.STATUS_REWARDED:
            return {
                "wallet_refund_amount": float(wallet_refund_amount),
                "reversed_reward_amount": float(reversed_reward_amount),
            }

        reward_credit_rows = list(
            ReferralTransaction.objects.select_for_update().filter(
                referral_id=referral.id,
                booking_id=locked_booking.id,
                transaction_type=ReferralTransaction.TYPE_CREDIT,
                reason__in=[
                    ReferralTransaction.REASON_REFERRER_REWARD,
                    ReferralTransaction.REASON_REFERRED_REWARD,
                ],
                status=ReferralTransaction.STATUS_COMPLETED,
            )
        )

        for credit_tx in reward_credit_rows:
            debit_tx, _, _ = _debit_referral_wallet(
                user=credit_tx.user,
                amount=_quantize_money(credit_tx.amount),
                reason=ReferralTransaction.REASON_REFERRAL_CANCELLATION_REVERSAL,
                referral=referral,
                booking=locked_booking,
                metadata={
                    "source_transaction_id": credit_tx.id,
                    "reason": reason,
                },
                require_available_balance=False,
                allow_negative_balance=True,
                transaction_type=ReferralTransaction.TYPE_REVERSAL,
            )
            if debit_tx:
                reversed_reward_amount = _quantize_money(
                    reversed_reward_amount + _quantize_money(credit_tx.amount)
                )
            credit_tx.status = ReferralTransaction.STATUS_REVERSED
            credit_tx.remaining_amount = Decimal("0.00")
            credit_tx.processed_at = timezone.now()
            credit_tx.save(update_fields=["status", "remaining_amount", "processed_at", "updated_at"])

        referral.status = Referral.STATUS_REVERSED
        referral.reversed_at = timezone.now()
        referral.reversal_reason = str(reason or "Booking cancelled")[:255]
        referral.save(update_fields=["status", "reversed_at", "reversal_reason", "updated_at"])

    return {
        "wallet_refund_amount": float(wallet_refund_amount),
        "reversed_reward_amount": float(reversed_reward_amount),
    }


def _dropoff_vendor_from_booking(booking: Optional[Booking]) -> Optional[Vendor]:
    """Resolve vendor from booking showtime screen context."""
    if not booking or not booking.showtime_id:
        return None
    showtime = booking.showtime
    screen = getattr(showtime, "screen", None) if showtime else None
    return getattr(screen, "vendor", None) if screen else None


def _dropoff_show_from_booking(booking: Optional[Booking]) -> Optional[Show]:
    """Resolve Show row that matches a booking showtime context."""
    if not booking or not booking.showtime_id:
        return None
    showtime = booking.showtime
    screen = getattr(showtime, "screen", None) if showtime else None
    if not showtime or not screen or not showtime.start_time:
        return None
    return (
        Show.objects.filter(
            vendor_id=screen.vendor_id,
            movie_id=showtime.movie_id,
            show_date=showtime.start_time.date(),
            start_time=showtime.start_time.time(),
            hall=screen.screen_number,
        )
        .order_by("-id")
        .first()
    )


def _record_booking_dropoff_event(
    *,
    stage: str,
    reason: str,
    seat_count: int = 0,
    booking: Optional[Booking] = None,
    payment: Optional[Payment] = None,
    user: Optional[User] = None,
    vendor: Optional[Vendor] = None,
    show: Optional[Show] = None,
    transaction_uuid: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    dedupe_by_transaction: bool = False,
) -> Optional[BookingDropoffEvent]:
    """Persist one drop-off event for booking/payment funnel analytics."""
    normalized_stage = str(stage or "").strip().upper()
    normalized_reason = str(reason or "").strip().upper()
    if normalized_stage not in {
        BookingDropoffEvent.STAGE_BOOKING,
        BookingDropoffEvent.STAGE_PAYMENT,
    }:
        return None
    if normalized_reason not in {
        BookingDropoffEvent.REASON_LEFT_BOOKING_PROCESS,
        BookingDropoffEvent.REASON_PAYMENT_NOT_COMPLETED,
        BookingDropoffEvent.REASON_PAYMENT_EXPIRED,
    }:
        return None

    resolved_tx_uuid = str(transaction_uuid or "").strip() or None
    if not resolved_tx_uuid and payment:
        resolved_tx_uuid = _transaction_uuid_from_payment_method(payment.payment_method)

    if dedupe_by_transaction and resolved_tx_uuid:
        already_logged = BookingDropoffEvent.objects.filter(
            stage=normalized_stage,
            transaction_uuid=resolved_tx_uuid,
        ).exists()
        if already_logged:
            return None

    resolved_booking = booking
    resolved_payment = payment
    if resolved_booking is None and resolved_payment is not None:
        resolved_booking = resolved_payment.booking

    resolved_user = user or (resolved_booking.user if resolved_booking else None)
    resolved_vendor = vendor or _dropoff_vendor_from_booking(resolved_booking)
    resolved_show = show or _dropoff_show_from_booking(resolved_booking)

    try:
        safe_seat_count = max(int(seat_count or 0), 0)
    except (TypeError, ValueError):
        safe_seat_count = 0

    return BookingDropoffEvent.objects.create(
        user=resolved_user,
        vendor=resolved_vendor,
        show=resolved_show,
        booking=resolved_booking,
        payment=resolved_payment,
        stage=normalized_stage,
        reason=normalized_reason,
        seat_count=safe_seat_count,
        transaction_uuid=resolved_tx_uuid,
        metadata=metadata or {},
    )


def _build_dropoff_analytics_payload(
    events_qs,
    *,
    days: int = 7,
) -> dict[str, Any]:
    """Build summary + daily trend payload for drop-off analytics graphs."""
    horizon_days = max(int(days or 7), 1)
    today = timezone.localdate()
    start_date = today - timedelta(days=horizon_days - 1)

    booking_dropoffs = events_qs.filter(
        stage=BookingDropoffEvent.STAGE_BOOKING,
    ).count()
    payment_dropoffs = events_qs.filter(
        stage=BookingDropoffEvent.STAGE_PAYMENT,
    ).count()

    daily_rows = (
        events_qs.filter(created_at__date__gte=start_date)
        .values("created_at", "stage")
        .order_by("created_at")
    )

    trend_map: dict[date_cls, dict[str, int]] = {}
    for offset in range(horizon_days):
        day = start_date + timedelta(days=offset)
        trend_map[day] = {
            "booking_process_left": 0,
            "payment_process_left": 0,
            "total_left": 0,
        }

    for row in daily_rows:
        created_at = row.get("created_at")
        stage = str(row.get("stage") or "").strip().upper()
        if not created_at:
            continue
        local_day = ensure_utc_datetime(created_at).date()
        if local_day not in trend_map:
            continue
        if stage == BookingDropoffEvent.STAGE_BOOKING:
            trend_map[local_day]["booking_process_left"] += 1
        elif stage == BookingDropoffEvent.STAGE_PAYMENT:
            trend_map[local_day]["payment_process_left"] += 1
        trend_map[local_day]["total_left"] += 1

    trend = [
        {
            "date": day.isoformat(),
            **trend_map[day],
        }
        for day in sorted(trend_map.keys())
    ]

    return {
        "summary": {
            "booking_process_left": booking_dropoffs,
            "payment_process_left": payment_dropoffs,
            "total_left": booking_dropoffs + payment_dropoffs,
        },
        "trend": trend,
    }


def get_admin_dropoff_analytics(days: int = 7) -> dict[str, Any]:
    """Return platform-wide booking/payment drop-off analytics for admin graphs."""
    cache_key = _dashboard_cache_key("admin-dropoff", days)
    cached_payload = cache.get(cache_key)
    if cached_payload is not None:
        return cached_payload
    base_qs = BookingDropoffEvent.objects.all()
    payload = _build_dropoff_analytics_payload(base_qs, days=days)
    response = {
        "scope": "admin",
        "dropoff_summary": payload["summary"],
        "dropoff_trend": payload["trend"],
        "message": "Drop-off analytics retrieved successfully",
    }
    cache.set(cache_key, response, ANALYTICS_CACHE_TTL_SECONDS)
    return response


def _normalize_ticket_monitor_export_filters(raw_filters: Optional[dict[str, Any]]) -> dict[str, Any]:
    filters = raw_filters if isinstance(raw_filters, dict) else {}

    valid_statuses = {
        TicketValidationScan.STATUS_VALID,
        TicketValidationScan.STATUS_DUPLICATE,
        TicketValidationScan.STATUS_INVALID,
        TicketValidationScan.STATUS_FRAUD,
    }
    status_value = str(filters.get("status") or "").strip().upper()
    if status_value not in valid_statuses:
        status_value = ""

    reference = str(filters.get("reference") or "").strip().upper()
    parsed_date = parse_date(filters.get("date"))

    staff_mode = str(filters.get("staffMode") or filters.get("staff_mode") or "").strip().lower()
    staff_id = _coerce_int(filters.get("staffId") or filters.get("staff_id"))
    if staff_mode not in {"owner", "staff"}:
        raw_staff = str(filters.get("staff") or "").strip().lower()
        if raw_staff in {"owner", "vendor", "vendor_account"}:
            staff_mode = "owner"
            staff_id = None
        else:
            parsed_staff_id = _coerce_int(raw_staff)
            if parsed_staff_id:
                staff_mode = "staff"
                staff_id = parsed_staff_id
            else:
                staff_mode = ""
                staff_id = None
    elif staff_mode != "staff":
        staff_id = None

    movie_id = _coerce_int(filters.get("movieId") or filters.get("movie_id") or filters.get("movie"))
    show_id = _coerce_int(filters.get("showId") or filters.get("show_id") or filters.get("show"))

    return {
        "status": status_value,
        "reference": reference,
        "date": parsed_date.isoformat() if parsed_date else "",
        "staffMode": staff_mode,
        "staffId": staff_id,
        "movieId": movie_id,
        "showId": show_id,
    }


def _query_ticket_monitor_scans_for_export(vendor_id: int, filters: Optional[dict[str, Any]] = None):
    normalized_filters = _normalize_ticket_monitor_export_filters(filters)
    queryset = TicketValidationScan.objects.filter(vendor_id=vendor_id).select_related(
        "ticket__show__movie",
        "vendor_staff",
        "vendor",
        "scanned_by",
    )

    if normalized_filters.get("status"):
        queryset = queryset.filter(status=normalized_filters["status"])
    if normalized_filters.get("reference"):
        queryset = queryset.filter(reference__icontains=normalized_filters["reference"])

    parsed_date = parse_date(normalized_filters.get("date"))
    if parsed_date:
        queryset = queryset.filter(scanned_at__date=parsed_date)

    if normalized_filters.get("staffMode") == "owner":
        queryset = queryset.filter(vendor_staff__isnull=True)
    elif normalized_filters.get("staffMode") == "staff" and normalized_filters.get("staffId"):
        queryset = queryset.filter(vendor_staff_id=normalized_filters["staffId"])

    if normalized_filters.get("movieId"):
        queryset = queryset.filter(ticket__show__movie_id=normalized_filters["movieId"])
    if normalized_filters.get("showId"):
        queryset = queryset.filter(ticket__show_id=normalized_filters["showId"])

    return queryset.order_by("-scanned_at", "-id")


def _resolve_ticket_monitor_scan_actor(scan: TicketValidationScan) -> tuple[str, Optional[int], str]:
    staff = scan.vendor_staff if isinstance(scan.vendor_staff, VendorStaff) else None
    if staff:
        label = str(staff.full_name or staff.username or staff.email or f"Staff #{staff.id}").strip()
        return "staff", staff.id, label

    actor = scan.scanned_by or scan.vendor
    actor_label = str(
        getattr(actor, "name", "")
        or getattr(actor, "username", "")
        or getattr(actor, "email", "")
    ).strip()
    return "vendor", None, actor_label or "Vendor Account"


def _extract_ticket_monitor_show_context(scan: TicketValidationScan) -> dict[str, Any]:
    show = scan.ticket.show if scan.ticket and scan.ticket.show else None
    payload = scan.ticket.payload if scan.ticket and isinstance(scan.ticket.payload, dict) else {}
    movie_payload = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}

    movie_id = show.movie_id if show else None
    movie_title = str(show.movie.title if show and show.movie else "").strip()
    if not movie_title:
        movie_title = str(movie_payload.get("title") or "").strip()

    show_id = show.id if show else None
    hall = str(show.hall if show else "").strip()
    if not hall:
        hall = str(movie_payload.get("theater") or "").strip()

    show_date = show.show_date.isoformat() if show and show.show_date else None
    if not show_date:
        show_date = str(movie_payload.get("show_date") or "").strip() or None

    show_time = show.start_time.strftime("%H:%M") if show and show.start_time else None
    if not show_time:
        show_time = str(movie_payload.get("show_time") or "").strip() or None

    return {
        "movie_id": movie_id,
        "movie_title": movie_title or None,
        "show_id": show_id,
        "show_date": show_date,
        "show_time": show_time,
        "hall": hall or None,
    }


def _build_ticket_monitor_csv_content(
    *,
    vendor_id: int,
    filters: Optional[dict[str, Any]] = None,
) -> tuple[str, str, int]:
    scans = _query_ticket_monitor_scans_for_export(vendor_id, filters=filters)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "scan_id",
            "reference",
            "ticket_id",
            "status",
            "fraud_score",
            "reason",
            "scanned_at",
            "source_ip",
            "scanned_by_type",
            "scanned_by_staff_id",
            "scanned_by_name",
            "movie_id",
            "movie_title",
            "show_id",
            "show_date",
            "show_time",
            "hall",
        ]
    )

    row_count = 0
    for scan in scans:
        actor_type, actor_staff_id, actor_name = _resolve_ticket_monitor_scan_actor(scan)
        show_context = _extract_ticket_monitor_show_context(scan)
        writer.writerow(
            [
                scan.id,
                scan.reference,
                str(scan.ticket.ticket_id) if scan.ticket and scan.ticket.ticket_id else "",
                scan.status,
                int(scan.fraud_score or 0),
                scan.reason or "",
                scan.scanned_at.isoformat() if scan.scanned_at else "",
                scan.source_ip or "",
                actor_type,
                actor_staff_id or "",
                actor_name,
                show_context.get("movie_id") or "",
                show_context.get("movie_title") or "",
                show_context.get("show_id") or "",
                show_context.get("show_date") or "",
                show_context.get("show_time") or "",
                show_context.get("hall") or "",
            ]
        )
        row_count += 1

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ticket_validation_monitor_{timestamp}.csv"
    return filename, output.getvalue(), row_count


def _enqueue_background_job(
    *,
    job_type: str,
    payload: Optional[dict[str, Any]] = None,
    max_attempts: int = BACKGROUND_JOB_DEFAULT_MAX_ATTEMPTS,
) -> Optional[BackgroundJob]:
    safe_attempts = max(int(max_attempts or BACKGROUND_JOB_DEFAULT_MAX_ATTEMPTS), 1)
    try:
        return BackgroundJob.objects.create(
            job_type=job_type,
            status=BackgroundJob.STATUS_PENDING,
            payload=payload or {},
            max_attempts=safe_attempts,
        )
    except Exception:
        logger.exception("Failed to enqueue background job %s", job_type)
        return None


def enqueue_vendor_monitor_export_job(
    *,
    vendor_id: int,
    filters: Optional[dict[str, Any]] = None,
    requested_by_staff_id: Optional[int] = None,
) -> Optional[BackgroundJob]:
    safe_vendor_id = _coerce_int(vendor_id)
    if not safe_vendor_id:
        return None

    payload: dict[str, Any] = {
        "vendor_id": safe_vendor_id,
        "filters": _normalize_ticket_monitor_export_filters(filters),
    }

    safe_staff_id = _coerce_int(requested_by_staff_id)
    if safe_staff_id:
        payload["requested_by_staff_id"] = safe_staff_id

    return _enqueue_background_job(
        job_type=BackgroundJob.TYPE_ANALYTICS_MONITOR_EXPORT,
        payload=payload,
        max_attempts=2,
    )


def enqueue_gateway_status_check_job(
    *,
    transaction_uuid: str,
    total_amount: str,
    provider: str = "ESEWA",
    context: str = "BOOKING_PAYMENT",
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[BackgroundJob]:
    """Queue async gateway status validation for pending callback flows."""
    safe_transaction_uuid = str(transaction_uuid or "").strip()
    safe_total_amount = str(total_amount or "").strip()
    if not safe_transaction_uuid or not safe_total_amount:
        return None

    payload = {
        "transaction_uuid": safe_transaction_uuid,
        "total_amount": safe_total_amount,
        "provider": str(provider or "ESEWA").strip().upper()[:20],
        "context": str(context or "BOOKING_PAYMENT").strip().upper()[:40],
        "metadata": metadata or {},
    }
    return _enqueue_background_job(
        job_type=BACKGROUND_JOB_TYPE_GATEWAY_STATUS_CHECK,
        payload=payload,
        max_attempts=2,
    )


def enqueue_financial_summary_rollup_job(
    *,
    scope: str = "ALL",
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[BackgroundJob]:
    """Queue async financial snapshot rollups from immutable ledgers."""
    payload = {
        "scope": str(scope or "ALL").strip().upper()[:20] or "ALL",
        "metadata": metadata or {},
    }
    return _enqueue_background_job(
        job_type=BACKGROUND_JOB_TYPE_FINANCIAL_SUMMARY_ROLLUP,
        payload=payload,
        max_attempts=2,
    )


def enqueue_withdrawal_settlement_job(
    *,
    withdrawal_transaction_id: int,
    payout_reference: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[BackgroundJob]:
    """Queue async settlement for an approved withdrawal request."""
    safe_withdrawal_id = _coerce_int(withdrawal_transaction_id)
    if not safe_withdrawal_id:
        return None

    payload = {
        "withdrawal_transaction_id": safe_withdrawal_id,
        "payout_reference": str(payout_reference or "").strip() or None,
        "metadata": metadata or {},
    }
    return _enqueue_background_job(
        job_type=BACKGROUND_JOB_TYPE_WITHDRAWAL_SETTLEMENT,
        payload=payload,
        max_attempts=3,
    )


def enqueue_notification_email_retry_job(
    *,
    subject: str,
    message: str,
    recipient_email: Optional[str],
    html_message: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[BackgroundJob]:
    """Queue dedicated email retry job type for degraded delivery windows."""
    email = str(recipient_email or "").strip()
    if not email:
        return None

    return _enqueue_background_job(
        job_type=BACKGROUND_JOB_TYPE_NOTIFICATION_EMAIL_RETRY,
        payload={
            "subject": str(subject or "").strip(),
            "message": str(message or "").strip(),
            "recipient_email": email,
            "html_message": html_message,
            "metadata": metadata or {},
        },
        max_attempts=max(BACKGROUND_JOB_DEFAULT_MAX_ATTEMPTS, 5),
    )


def enqueue_stale_pending_cleanup_job(
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[BackgroundJob]:
    """Queue cleanup for expired pending bookings, seat locks, and group sessions."""
    return _enqueue_background_job(
        job_type=BACKGROUND_JOB_TYPE_STALE_PENDING_CLEANUP,
        payload={"metadata": metadata or {}},
        max_attempts=2,
    )


def enqueue_data_reconciliation_job(
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[BackgroundJob]:
    """Queue background reconciliation checks and wallet rollups."""
    return _enqueue_background_job(
        job_type=BACKGROUND_JOB_TYPE_DATA_RECONCILIATION,
        payload={"metadata": metadata or {}},
        max_attempts=2,
    )


def enqueue_analytics_rollup_job(
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[BackgroundJob]:
    """Queue precomputation of cache-heavy analytics summary counters."""
    return _enqueue_background_job(
        job_type=BACKGROUND_JOB_TYPE_ANALYTICS_ROLLUP,
        payload={"metadata": metadata or {}},
        max_attempts=2,
    )


def _schedule_background_job_once(
    *,
    cache_key: str,
    interval_seconds: int,
    enqueue_fn: Any,
) -> bool:
    safe_interval = max(int(interval_seconds or 0), 10)
    if not cache.add(cache_key, timezone.now().isoformat(), timeout=safe_interval):
        return False
    job = enqueue_fn()
    if job is not None:
        return True
    cache.delete(cache_key)
    return False


def enqueue_scheduled_maintenance_jobs() -> dict[str, int]:
    """Enqueue periodic maintenance jobs with cache-backed throttling."""
    stale_interval = max(_settings_int("BACKGROUND_STALE_PENDING_CLEANUP_INTERVAL_SECONDS", 30), 10)
    reconcile_interval = max(_settings_int("BACKGROUND_RECONCILIATION_INTERVAL_SECONDS", 120), 30)
    analytics_interval = max(_settings_int("BACKGROUND_ANALYTICS_ROLLUP_INTERVAL_SECONDS", 60), 30)

    stale_enqueued = _schedule_background_job_once(
        cache_key="mt:bg:schedule:stale-pending-cleanup",
        interval_seconds=stale_interval,
        enqueue_fn=lambda: enqueue_stale_pending_cleanup_job(metadata={"scheduled": True}),
    )
    reconciliation_enqueued = _schedule_background_job_once(
        cache_key="mt:bg:schedule:data-reconciliation",
        interval_seconds=reconcile_interval,
        enqueue_fn=lambda: enqueue_data_reconciliation_job(metadata={"scheduled": True}),
    )
    analytics_enqueued = _schedule_background_job_once(
        cache_key="mt:bg:schedule:analytics-rollup",
        interval_seconds=analytics_interval,
        enqueue_fn=lambda: enqueue_analytics_rollup_job(metadata={"scheduled": True}),
    )

    return {
        "stale_cleanup_enqueued": 1 if stale_enqueued else 0,
        "reconciliation_enqueued": 1 if reconciliation_enqueued else 0,
        "analytics_rollup_enqueued": 1 if analytics_enqueued else 0,
    }


def get_vendor_monitor_export_job(vendor_id: int, job_id: int) -> Optional[BackgroundJob]:
    safe_job_id = _coerce_int(job_id)
    safe_vendor_id = _coerce_int(vendor_id)
    if not safe_job_id or not safe_vendor_id:
        return None

    job = BackgroundJob.objects.filter(
        id=safe_job_id,
        job_type=BackgroundJob.TYPE_ANALYTICS_MONITOR_EXPORT,
    ).first()
    if not job:
        return None

    payload = job.payload if isinstance(job.payload, dict) else {}
    job_vendor_id = _coerce_int(payload.get("vendor_id"))
    if job_vendor_id != safe_vendor_id:
        return None

    return job


def get_vendor_monitor_export_job_file(job: BackgroundJob) -> tuple[Optional[bytes], Optional[str], Optional[str]]:
    result = job.result if isinstance(job.result, dict) else {}
    encoded_csv = str(result.get("csv_base64") or "").strip()
    if not encoded_csv:
        return None, None, "CSV export is empty."

    try:
        csv_content = base64.b64decode(encoded_csv)
    except Exception:
        return None, None, "Failed to decode export file."

    filename = str(result.get("filename") or f"ticket_validation_monitor_{job.id}.csv").strip()
    return csv_content, filename or f"ticket_validation_monitor_{job.id}.csv", None


def _queue_notification_email(
    *,
    subject: str,
    message: str,
    recipient_email: Optional[str],
    html_message: Optional[str] = None,
) -> bool:
    email = str(recipient_email or "").strip()
    if not email:
        return False

    # Try immediate delivery first so critical customer notifications are not blocked
    # by a missing background worker.
    if _send_notification_email(
        subject=subject,
        message=message,
        recipient_email=email,
        html_message=html_message,
    ):
        return True

    queued_job = _enqueue_background_job(
        job_type=BackgroundJob.TYPE_NOTIFICATION_EMAIL,
        payload={
            "subject": str(subject or "").strip(),
            "message": str(message or "").strip(),
            "recipient_email": email,
            "html_message": html_message,
        },
        max_attempts=BACKGROUND_JOB_DEFAULT_MAX_ATTEMPTS,
    )
    if queued_job:
        return True

    retry_job = enqueue_notification_email_retry_job(
        subject=subject,
        message=message,
        recipient_email=email,
        html_message=html_message,
        metadata={"fallback": "primary_enqueue_failed"},
    )
    if retry_job:
        return True
    return False


def _process_notification_email_background_job(job: BackgroundJob) -> dict[str, Any]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    subject = str(payload.get("subject") or "").strip()
    message = str(payload.get("message") or "").strip()
    recipient_email = str(payload.get("recipient_email") or "").strip()
    html_message = payload.get("html_message")
    html_message = str(html_message).strip() if html_message is not None else None

    sent = _send_notification_email(
        subject=subject,
        message=message,
        recipient_email=recipient_email,
        html_message=html_message,
    )
    if not sent:
        raise ValueError("Notification email delivery failed.")

    return {
        "sent": True,
        "recipient_email": recipient_email,
    }


def _process_monitor_export_background_job(job: BackgroundJob) -> dict[str, Any]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    vendor_id = _coerce_int(payload.get("vendor_id"))
    if not vendor_id:
        raise ValueError("Missing vendor_id for analytics export job.")

    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    filename, csv_content, row_count = _build_ticket_monitor_csv_content(
        vendor_id=vendor_id,
        filters=filters,
    )

    encoded_csv = base64.b64encode(csv_content.encode("utf-8")).decode("ascii")
    return {
        "filename": filename,
        "content_type": "text/csv",
        "csv_base64": encoded_csv,
        "row_count": row_count,
        "generated_at": timezone.now().isoformat(),
    }


def _esewa_status_check_background_payload(*, transaction_uuid: str, total_amount: str) -> dict[str, Any]:
    """Call eSewa transaction status endpoint for asynchronous validation."""
    if not transaction_uuid or not total_amount:
        return {}

    query = urllib_parse.urlencode(
        {
            "product_code": str(getattr(settings, "ESEWA_PRODUCT_CODE", "EPAYTEST") or "EPAYTEST").strip() or "EPAYTEST",
            "total_amount": total_amount,
            "transaction_uuid": transaction_uuid,
        }
    )
    base_url = str(
        getattr(
            settings,
            "ESEWA_STATUS_CHECK_URL",
            "https://rc.esewa.com.np/api/epay/transaction/status/",
        )
        or "https://rc.esewa.com.np/api/epay/transaction/status/"
    ).strip()
    base_url = base_url.rstrip("?")
    separator = "&" if "?" in base_url else "?"
    url = f"{base_url}{separator}{query}"

    with urllib_request.urlopen(url, timeout=10) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _process_gateway_status_check_background_job(job: BackgroundJob) -> dict[str, Any]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    provider = str(payload.get("provider") or "ESEWA").strip().upper()
    transaction_uuid = str(payload.get("transaction_uuid") or "").strip()
    total_amount = str(payload.get("total_amount") or "").strip()
    if not transaction_uuid or not total_amount:
        raise ValueError("Missing transaction_uuid or total_amount for gateway status check.")

    if provider != "ESEWA":
        raise ValueError(f"Unsupported provider for status check: {provider}")

    status_payload = _esewa_status_check_background_payload(
        transaction_uuid=transaction_uuid,
        total_amount=total_amount,
    )
    normalized_status = str(status_payload.get("status") or "").strip().upper()
    return {
        "provider": provider,
        "transaction_uuid": transaction_uuid,
        "total_amount": total_amount,
        "status": normalized_status,
        "status_payload": status_payload,
        "is_complete": normalized_status == "COMPLETE",
        "checked_at": timezone.now().isoformat(),
    }


def _process_financial_summary_rollup_background_job(job: BackgroundJob) -> dict[str, Any]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    scope = str(payload.get("scope") or "ALL").strip().upper()

    vendor_wallets = Wallet.objects.all()
    if scope == "VENDOR" and payload.get("vendor_id"):
        vendor_id = _coerce_int(payload.get("vendor_id"))
        if vendor_id:
            vendor_wallets = vendor_wallets.filter(vendor_id=vendor_id)

    vendor_count = 0
    for wallet in vendor_wallets.iterator(chunk_size=100):
        _recalculate_vendor_wallet_snapshot(wallet)
        vendor_count += 1

    admin_count = 0
    for admin_wallet in AdminWallet.objects.all().iterator(chunk_size=10):
        _recalculate_admin_wallet_snapshot(admin_wallet)
        admin_count += 1

    user_count = 0
    for user_wallet in UserWallet.objects.all().iterator(chunk_size=200):
        _recalculate_user_wallet_snapshot(user_wallet)
        user_count += 1

    referral_count = 0
    for referral_wallet in ReferralWallet.objects.all().iterator(chunk_size=200):
        _recalculate_referral_wallet_snapshot(referral_wallet)
        referral_count += 1

    return {
        "scope": scope,
        "vendor_wallets_rebuilt": vendor_count,
        "admin_wallets_rebuilt": admin_count,
        "user_wallets_rebuilt": user_count,
        "referral_wallets_rebuilt": referral_count,
        "rolled_up_at": timezone.now().isoformat(),
    }


def _build_precomputed_summary_counts() -> dict[str, Any]:
    """Build small, hot-path counters to be served from Redis cache."""
    booking_stats = Booking.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(booking_status__iexact=BOOKING_STATUS_PENDING)),
        confirmed=Count("id", filter=Q(booking_status__iexact=BOOKING_STATUS_CONFIRMED)),
        cancelled=Count("id", filter=Q(booking_status__iexact=BOOKING_STATUS_CANCELLED)),
        gross=Sum("total_amount"),
    )
    payment_stats = Payment.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(payment_status__iexact=PAYMENT_STATUS_PENDING)),
        success=Count("id", filter=Q(payment_status__iexact=PAYMENT_STATUS_SUCCESS)),
        failed=Count("id", filter=Q(payment_status__iexact=PAYMENT_STATUS_FAILED)),
        collected=Sum("amount", filter=Q(payment_status__iexact=PAYMENT_STATUS_SUCCESS)),
    )

    return {
        "bookings": {
            "total": int(booking_stats.get("total") or 0),
            "pending": int(booking_stats.get("pending") or 0),
            "confirmed": int(booking_stats.get("confirmed") or 0),
            "cancelled": int(booking_stats.get("cancelled") or 0),
            "gross": float(_quantize_money(booking_stats.get("gross") or Decimal("0"))),
        },
        "payments": {
            "total": int(payment_stats.get("total") or 0),
            "pending": int(payment_stats.get("pending") or 0),
            "success": int(payment_stats.get("success") or 0),
            "failed": int(payment_stats.get("failed") or 0),
            "collected": float(_quantize_money(payment_stats.get("collected") or Decimal("0"))),
        },
        "users": {
            "customers": User.objects.count(),
            "vendors": Vendor.objects.count(),
            "admins": Admin.objects.count(),
        },
        "notifications": {
            "unread": Notification.objects.filter(is_read=False).count(),
            "total": Notification.objects.count(),
        },
        "generated_at": timezone.now().isoformat(),
    }


def _process_analytics_rollup_background_job(job: BackgroundJob) -> dict[str, Any]:
    summary = _build_precomputed_summary_counts()
    cache.set(PRECOMPUTED_SUMMARY_CACHE_KEY, summary, PRECOMPUTED_SUMMARY_CACHE_TTL_SECONDS)
    return {
        "summary_cached": True,
        "cache_key": PRECOMPUTED_SUMMARY_CACHE_KEY,
        "generated_at": summary.get("generated_at"),
    }


def _process_stale_pending_cleanup_background_job(job: BackgroundJob) -> dict[str, Any]:
    """Process stale pending cleanup in worker context, not request context."""
    expired_bookings = cleanup_expired_pending_bookings()
    stale_locks = cleanup_stale_seat_locks()

    from .. import group_booking as group_booking_module

    group_result = group_booking_module.expire_group_booking_sessions()
    return {
        "expired_pending_bookings": int(expired_bookings or 0),
        "stale_seat_locks_cleared": int(stale_locks or 0),
        "expired_group_sessions": int(group_result.get("expired_sessions") or 0),
        "processed_at": timezone.now().isoformat(),
    }


def _process_data_reconciliation_background_job(job: BackgroundJob) -> dict[str, Any]:
    rollup = _process_financial_summary_rollup_background_job(job)

    pending_without_pending_payment = Booking.objects.filter(
        booking_status__iexact=BOOKING_STATUS_PENDING,
    ).exclude(
        payments__payment_status__iexact=PAYMENT_STATUS_PENDING,
    ).distinct().count()

    settled_without_success_payment = Booking.objects.filter(
        Q(booking_status__iexact=BOOKING_STATUS_CONFIRMED)
        | Q(booking_status__iexact=Booking.Status.COMPLETED),
    ).exclude(
        payments__payment_status__iexact=PAYMENT_STATUS_SUCCESS,
    ).distinct().count()

    cache.set(
        "mt:summary:reconciliation:v1",
        {
            "pending_without_pending_payment": int(pending_without_pending_payment),
            "settled_without_success_payment": int(settled_without_success_payment),
            "checked_at": timezone.now().isoformat(),
        },
        timeout=60,
    )

    return {
        "wallet_rollup": rollup,
        "pending_without_pending_payment": int(pending_without_pending_payment),
        "settled_without_success_payment": int(settled_without_success_payment),
        "checked_at": timezone.now().isoformat(),
    }


def _process_withdrawal_settlement_background_job(job: BackgroundJob) -> dict[str, Any]:
    payload = job.payload if isinstance(job.payload, dict) else {}
    withdrawal_id = _coerce_int(payload.get("withdrawal_transaction_id"))
    if not withdrawal_id:
        raise ValueError("Missing withdrawal_transaction_id for settlement.")

    payout_reference = str(payload.get("payout_reference") or "").strip() or None
    settled_vendor: Optional[Vendor] = None
    settled_amount: Decimal = Decimal("0")
    settled_reference: Optional[str] = payout_reference

    with transaction.atomic():
        withdrawal_txn = (
            Transaction.objects.select_for_update()
            .select_related("wallet", "vendor")
            .filter(id=withdrawal_id, transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST)
            .first()
        )
        if not withdrawal_txn:
            raise ValueError("Withdrawal request transaction not found.")
        if withdrawal_txn.status != Transaction.STATUS_COMPLETED:
            raise ValueError("Withdrawal request must be approved before settlement.")

        ledger = (
            WithdrawalLedger.objects.select_for_update()
            .filter(withdrawal_transaction=withdrawal_txn)
            .order_by("-created_at", "-id")
            .first()
        )
        if not ledger:
            raise ValueError("Withdrawal ledger entry not found for settlement.")

        if ledger.status not in {WithdrawalLedger.STATUS_APPROVED, WithdrawalLedger.STATUS_PROCESSING}:
            raise ValueError("Withdrawal ledger is not in an approvable state for settlement.")

        ledger.decision_metadata = {
            **(ledger.decision_metadata if isinstance(ledger.decision_metadata, dict) else {}),
            "action": "SETTLEMENT_PROCESSING",
            "processing_started_at": timezone.now().isoformat(),
            "job_id": job.id,
        }
        ledger.status = WithdrawalLedger.STATUS_PROCESSING
        if payout_reference:
            ledger.payout_reference = payout_reference
        ledger.save(update_fields=["status", "payout_reference", "decision_metadata", "updated_at"])

    try:
        with transaction.atomic():
            withdrawal_txn = (
                Transaction.objects.select_for_update()
                .select_related("wallet", "vendor")
                .filter(id=withdrawal_id, transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST)
                .first()
            )
            if not withdrawal_txn:
                raise ValueError("Withdrawal request transaction not found.")

            ledger = (
                WithdrawalLedger.objects.select_for_update()
                .filter(withdrawal_transaction=withdrawal_txn)
                .order_by("-created_at", "-id")
                .first()
            )
            if not ledger:
                raise ValueError("Withdrawal ledger entry not found for settlement.")

            ledger.status = WithdrawalLedger.STATUS_PAID
            if payout_reference:
                ledger.payout_reference = payout_reference
            ledger.decision_metadata = {
                **(ledger.decision_metadata if isinstance(ledger.decision_metadata, dict) else {}),
                "action": "SETTLED",
                "settled_at": timezone.now().isoformat(),
                "job_id": job.id,
            }
            ledger.save(update_fields=["status", "payout_reference", "decision_metadata", "updated_at"])

            _recalculate_vendor_wallet_snapshot(withdrawal_txn.wallet)
            settled_vendor = withdrawal_txn.vendor
            settled_amount = _quantize_money(ledger.amount or withdrawal_txn.amount or Decimal("0"))
            settled_reference = ledger.payout_reference or payout_reference
    except Exception:
        with transaction.atomic():
            withdrawal_txn = (
                Transaction.objects.select_for_update()
                .select_related("wallet", "vendor")
                .filter(id=withdrawal_id, transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST)
                .first()
            )
            if withdrawal_txn:
                ledger = (
                    WithdrawalLedger.objects.select_for_update()
                    .filter(withdrawal_transaction=withdrawal_txn)
                    .order_by("-created_at", "-id")
                    .first()
                )
                if ledger and ledger.status == WithdrawalLedger.STATUS_PROCESSING:
                    ledger.status = WithdrawalLedger.STATUS_FAILED
                    ledger.decision_metadata = {
                        **(ledger.decision_metadata if isinstance(ledger.decision_metadata, dict) else {}),
                        "action": "SETTLEMENT_FAILED",
                        "failed_at": timezone.now().isoformat(),
                        "job_id": job.id,
                    }
                    ledger.save(update_fields=["status", "decision_metadata", "updated_at"])
        raise

    if settled_vendor:
        try:
            readable_reference = settled_reference or f"WSET-{withdrawal_id}"
            _create_notification(
                recipient_role=Notification.ROLE_VENDOR,
                recipient_id=settled_vendor.id,
                recipient_email=settled_vendor.email,
                event_type=Notification.EVENT_CUSTOM_MESSAGE,
                title="Withdrawal Transaction Complete",
                message=(
                    f"Your withdrawal of NPR {float(settled_amount):,.2f} has been completed. "
                    f"Reference: {readable_reference}."
                ),
                metadata={
                    "source": "withdrawal_settlement",
                    "withdrawal_transaction_id": withdrawal_id,
                    "payout_reference": readable_reference,
                    "amount": float(settled_amount),
                },
                send_email_too=True,
            )
        except Exception:
            logger.exception(
                "Failed to send vendor withdrawal completion notification for transaction %s",
                withdrawal_id,
            )

    return {
        "withdrawal_transaction_id": withdrawal_id,
        "payout_reference": payout_reference,
        "settled": True,
        "settled_at": timezone.now().isoformat(),
    }


def _process_notification_email_retry_background_job(job: BackgroundJob) -> dict[str, Any]:
    """Dedicated processor for retry-oriented email jobs."""
    return _process_notification_email_background_job(job)


def _process_background_job(job: BackgroundJob) -> dict[str, Any]:
    if job.job_type == BackgroundJob.TYPE_NOTIFICATION_EMAIL:
        return _process_notification_email_background_job(job)
    if job.job_type == BACKGROUND_JOB_TYPE_NOTIFICATION_EMAIL_RETRY:
        return _process_notification_email_retry_background_job(job)
    if job.job_type == BackgroundJob.TYPE_ANALYTICS_MONITOR_EXPORT:
        return _process_monitor_export_background_job(job)
    if job.job_type == BACKGROUND_JOB_TYPE_GATEWAY_STATUS_CHECK:
        return _process_gateway_status_check_background_job(job)
    if job.job_type == BACKGROUND_JOB_TYPE_FINANCIAL_SUMMARY_ROLLUP:
        return _process_financial_summary_rollup_background_job(job)
    if job.job_type == BACKGROUND_JOB_TYPE_WITHDRAWAL_SETTLEMENT:
        return _process_withdrawal_settlement_background_job(job)
    if job.job_type == BACKGROUND_JOB_TYPE_STALE_PENDING_CLEANUP:
        return _process_stale_pending_cleanup_background_job(job)
    if job.job_type == BACKGROUND_JOB_TYPE_DATA_RECONCILIATION:
        return _process_data_reconciliation_background_job(job)
    if job.job_type == BACKGROUND_JOB_TYPE_ANALYTICS_ROLLUP:
        return _process_analytics_rollup_background_job(job)
    raise ValueError(f"Unsupported background job type: {job.job_type}")


def _claim_background_jobs(
    *,
    batch_size: int = 20,
    job_types: Optional[Iterable[str]] = None,
) -> list[BackgroundJob]:
    safe_batch_size = max(min(int(batch_size or 20), 200), 1)
    normalized_types = [
        str(item or "").strip().upper()
        for item in (job_types or [])
        if str(item or "").strip()
    ]

    now = timezone.now()
    with transaction.atomic():
        queryset = BackgroundJob.objects.filter(
            status=BackgroundJob.STATUS_PENDING,
            available_at__lte=now,
        ).order_by("available_at", "id")
        if normalized_types:
            queryset = queryset.filter(job_type__in=normalized_types)

        try:
            jobs = list(queryset.select_for_update(skip_locked=True)[:safe_batch_size])
        except Exception:
            jobs = list(queryset.select_for_update()[:safe_batch_size])

        if not jobs:
            return []

        for job in jobs:
            job.status = BackgroundJob.STATUS_PROCESSING
            job.started_at = now
            job.error_message = None
            job.attempts = int(job.attempts or 0) + 1
            job.updated_at = now
            job.save(
                update_fields=[
                    "status",
                    "started_at",
                    "error_message",
                    "attempts",
                    "updated_at",
                ]
            )

        return jobs


def _mark_background_job_completed(job: BackgroundJob, *, result: Optional[dict[str, Any]] = None) -> None:
    now = timezone.now()
    job.status = BackgroundJob.STATUS_COMPLETED
    job.result = result or {}
    job.error_message = None
    job.finished_at = now
    job.updated_at = now
    job.save(
        update_fields=[
            "status",
            "result",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )


def _mark_background_job_failed_or_requeued(job: BackgroundJob, *, error_message: str) -> str:
    now = timezone.now()
    max_attempts = max(int(job.max_attempts or BACKGROUND_JOB_DEFAULT_MAX_ATTEMPTS), 1)
    attempts = int(job.attempts or 0)

    job.error_message = str(error_message or "Job failed")[:255]
    job.updated_at = now
    if attempts >= max_attempts:
        job.status = BackgroundJob.STATUS_FAILED
        job.finished_at = now
        job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        return "failed"

    retry_seconds = BACKGROUND_JOB_RETRY_BACKOFF_SECONDS * attempts
    job.status = BackgroundJob.STATUS_PENDING
    job.available_at = now + timedelta(seconds=retry_seconds)
    job.started_at = None
    job.save(
        update_fields=[
            "status",
            "available_at",
            "started_at",
            "error_message",
            "updated_at",
        ]
    )
    return "requeued"


def process_background_jobs(
    *,
    batch_size: int = 20,
    job_types: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    jobs = _claim_background_jobs(batch_size=batch_size, job_types=job_types)
    summary = {
        "claimed": len(jobs),
        "processed": 0,
        "completed": 0,
        "failed": 0,
        "requeued": 0,
    }
    if not jobs:
        return summary

    for job in jobs:
        summary["processed"] += 1
        try:
            result = _process_background_job(job)
            _mark_background_job_completed(job, result=result)
            summary["completed"] += 1
        except Exception as exc:
            logger.exception("Background job %s failed", job.id)
            outcome = _mark_background_job_failed_or_requeued(job, error_message=str(exc))
            if outcome == "failed":
                summary["failed"] += 1
            else:
                summary["requeued"] += 1

    return summary


def _normalize_show_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"", "open", "booking_open", "upcoming"}:
        return Show.STATUS_UPCOMING
    if raw in {"running", "live", "ongoing"}:
        return Show.STATUS_RUNNING
    if raw in {"completed", "closed", "ended"}:
        return Show.STATUS_COMPLETED
    return Show.STATUS_UPCOMING


def _ensure_show_is_bookable(show: Show) -> tuple[Optional[dict[str, Any]], Optional[int]]:
    """Return an error payload when booking is closed for the show lifecycle window."""
    selectors.sync_show_lifecycle_statuses()
    show.refresh_from_db(fields=["status", "show_date", "start_time", "end_time"])
    lifecycle = selectors.get_show_lifecycle_state(show)
    if lifecycle["status"] == selectors.SHOW_STATUS_COMPLETED:
        return {"message": "This show is completed. Booking is no longer available."}, status.HTTP_400_BAD_REQUEST
    if lifecycle["status"] == selectors.SHOW_STATUS_RUNNING:
        return {"message": "This show is already running. Booking is closed."}, status.HTTP_400_BAD_REQUEST
    if not lifecycle.get("booking_open"):
        return {
            "message": (
                f"Booking closes {selectors.BOOKING_CLOSE_BEFORE_START_MINUTES} minutes "
                "before show start time."
            ),
            "booking_close_at": lifecycle["booking_close_at"].isoformat()
            if lifecycle.get("booking_close_at")
            else None,
        }, status.HTTP_400_BAD_REQUEST
    return None, None


def _send_notification_email(
    subject: str,
    message: str,
    recipient_email: Optional[str],
    html_message: Optional[str] = None,
) -> bool:
    """Send a notification email using Django's configured email backend."""
    email = str(recipient_email or "").strip()
    if not email:
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@meroticket.local"
    try:
        sent_count = send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=[email],
            html_message=html_message,
            fail_silently=False,
        )
        return bool(sent_count)
    except Exception:
        logger.exception("Failed to send notification email to %s", email)
        return False


def _build_password_reset_otp_html(otp: str) -> str:
    """Render the HTML template for password reset OTP emails."""
    safe_otp = escape(str(otp or "").strip())
    return (
        "<div style=\"font-family:Arial,sans-serif;max-width:560px;margin:0 auto;"
        "border:1px solid #e5e7eb;border-radius:12px;overflow:hidden\">"
        "<div style=\"background:#111827;color:#ffffff;padding:18px 20px;font-size:18px;"
        "font-weight:700\">Mero Ticket - Password Reset</div>"
        "<div style=\"padding:20px;color:#111827\">"
        "<p style=\"margin:0 0 12px 0;font-size:14px\">Use the OTP below to reset your password:</p>"
        f"<div style=\"font-size:32px;letter-spacing:8px;font-weight:800;color:#0f172a;"
        f"margin:8px 0 16px 0\">{safe_otp}</div>"
        "<p style=\"margin:0 0 8px 0;font-size:13px;color:#4b5563\">This OTP is valid for 10 minutes.</p>"
        "<p style=\"margin:0;font-size:13px;color:#4b5563\">If you did not request this, please ignore this email.</p>"
        "</div>"
        "</div>"
    )


def _send_password_reset_otp_email(email: str, otp: str) -> bool:
    """Send password-reset OTP to a user email address."""
    subject = "Mero Ticket password reset OTP"
    message = (
        "Your Mero Ticket password reset OTP is: "
        f"{otp}\n\n"
        "This OTP is valid for 10 minutes.\n"
        "If you did not request this, please ignore this email."
    )
    return _send_notification_email(
        subject,
        message,
        email,
        html_message=_build_password_reset_otp_html(otp),
    )


def _build_password_changed_html(context_label: str) -> str:
    """Render the HTML template for password changed confirmation emails."""
    safe_context = escape(str(context_label or "").strip() or "security update")
    return (
        "<div style=\"font-family:Arial,sans-serif;max-width:560px;margin:0 auto;"
        "border:1px solid #e5e7eb;border-radius:12px;overflow:hidden\">"
        "<div style=\"background:#0f172a;color:#ffffff;padding:18px 20px;font-size:18px;"
        "font-weight:700\">Mero Ticket - Password Updated</div>"
        "<div style=\"padding:20px;color:#111827\">"
        "<p style=\"margin:0 0 12px 0;font-size:14px\">Your account password was changed successfully.</p>"
        f"<p style=\"margin:0 0 12px 0;font-size:13px;color:#334155\">Context: {safe_context}</p>"
        "<p style=\"margin:0 0 8px 0;font-size:13px;color:#4b5563\">"
        "If this was not you, please reset your password immediately and contact support."
        "</p>"
        "</div>"
        "</div>"
    )


def _send_password_changed_email(
    recipient_email: Optional[str],
    *,
    context_label: str,
) -> bool:
    """Send a password changed confirmation email via the configured email backend."""
    email = str(recipient_email or "").strip()
    if not email:
        return False

    context_text = str(context_label or "").strip() or "security update"
    subject = "Mero Ticket password changed"
    message = (
        "Your Mero Ticket account password was changed successfully.\n"
        f"Context: {context_text}\n\n"
        "If this was not you, please reset your password immediately and contact support."
    )
    return _send_notification_email(
        subject,
        message,
        email,
        html_message=_build_password_changed_html(context_text),
    )


def _create_notification(
    *,
    recipient_role: str,
    recipient_id: int,
    recipient_email: Optional[str],
    event_type: str,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
    send_email_too: bool = False,
) -> Notification:
    """Persist in-app notification and optionally send matching email."""
    channel = Notification.CHANNEL_BOTH if send_email_too else Notification.CHANNEL_IN_APP
    notification = Notification.objects.create(
        recipient_role=recipient_role,
        recipient_id=recipient_id,
        recipient_email=(str(recipient_email).strip() if recipient_email else None),
        event_type=event_type,
        channel=channel,
        title=title,
        message=message,
        metadata=metadata or {},
    )

    if send_email_too:
        _queue_notification_email(
            subject=title,
            message=message,
            recipient_email=recipient_email,
        )

    return notification


def _build_notification_payload(notification: Notification) -> dict[str, Any]:
    """Serialize a notification for API responses."""
    return {
        "id": notification.id,
        "recipient_role": notification.recipient_role,
        "recipient_id": notification.recipient_id,
        "recipient_email": notification.recipient_email,
        "event_type": notification.event_type,
        "channel": notification.channel,
        "title": notification.title,
        "message": notification.message,
        "metadata": notification.metadata or {},
        "is_read": bool(notification.is_read),
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def _notify_show_update(
    *,
    vendor: Vendor,
    movie: Movie,
    title: str,
    message: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Send show update notifications to the owner vendor and active admins."""
    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=vendor.id,
        recipient_email=vendor.email,
        event_type=Notification.EVENT_SHOW_UPDATE,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )

    for admin in Admin.objects.filter(is_active=True).only("id", "email"):
        _create_notification(
            recipient_role=Notification.ROLE_ADMIN,
            recipient_id=admin.id,
            recipient_email=admin.email,
            event_type=Notification.EVENT_SHOW_UPDATE,
            title=title,
            message=message,
            metadata=metadata,
            send_email_too=True,
        )


def _notify_booking_created(booking: Booking, show: Show) -> None:
    """Send booking-created notifications to customer, vendor, and admins."""
    title = "New booking confirmed"
    seat_count = booking.booking_seats.count()
    message = (
        f"Your booking #{booking.id} for {show.movie.title} is confirmed with {seat_count} seat(s)."
    )
    metadata = _build_booking_notification_metadata(
        booking,
        include_booking_detail=True,
    )
    metadata.update(
        {
            "show_id": show.id,
            "showtime_id": booking.showtime_id,
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "seat_count": seat_count,
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=booking.user_id,
        recipient_email=booking.user.email,
        event_type=Notification.EVENT_NEW_BOOKING,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )

    vendor_message = (
        f"New booking #{booking.id} received for {show.movie.title} ({seat_count} seat(s))."
    )
    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=show.vendor_id,
        recipient_email=show.vendor.email,
        event_type=Notification.EVENT_NEW_BOOKING,
        title=title,
        message=vendor_message,
        metadata=metadata,
        send_email_too=True,
    )

    for admin in Admin.objects.filter(is_active=True).only("id", "email"):
        _create_notification(
            recipient_role=Notification.ROLE_ADMIN,
            recipient_id=admin.id,
            recipient_email=admin.email,
            event_type=Notification.EVENT_NEW_BOOKING,
            title=title,
            message=vendor_message,
            metadata=metadata,
            send_email_too=True,
        )


def _find_ticket_reference_for_booking(booking_id: int) -> Optional[str]:
    """Return the latest ticket reference linked to the given booking id."""
    if booking_id <= 0:
        return None

    # Use JSON lookup first; if unsupported by the DB backend, scan recent rows.
    try:
        ticket = (
            Ticket.objects.filter(payload__booking__booking_id=booking_id)
            .only("reference")
            .order_by("-id")
            .first()
        )
        if ticket:
            return str(ticket.reference)
    except Exception:
        ticket = None

    recent_tickets = Ticket.objects.only("reference", "payload").order_by("-id")[:500]
    for item in recent_tickets:
        payload = item.payload if isinstance(item.payload, dict) else {}
        booking_payload = payload.get("booking") if isinstance(payload, dict) else {}
        if not isinstance(booking_payload, dict):
            continue
        payload_booking_id = _coerce_int(coalesce(booking_payload, "booking_id", "id"))
        if payload_booking_id == booking_id:
            return str(item.reference)
    return None


def _get_latest_payment_for_booking(booking: Booking) -> Optional[Payment]:
    if not booking:
        return None
    return booking.payments.all().order_by("-payment_date", "-id").first()


def _get_latest_refund_for_booking(payment: Optional[Payment]) -> Optional[Refund]:
    if not payment:
        return None
    return payment.refunds.all().order_by("-refund_date", "-id").first()


def _build_booking_notification_metadata(
    booking: Booking,
    *,
    include_booking_detail: bool = False,
) -> dict[str, Any]:
    """Build rich booking/payment metadata for in-app notification payloads."""
    showtime = booking.showtime if booking else None
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    movie = getattr(showtime, "movie", None) if showtime else None
    latest_payment = _get_latest_payment_for_booking(booking)
    latest_refund = _get_latest_refund_for_booking(latest_payment)
    amount_basis = _booking_amount_for_refund(booking, latest_payment=latest_payment)
    seat_labels = [
        _seat_label(item.seat)
        for item in booking.booking_seats.select_related("seat").all()
        if item.seat
    ]

    ticket_reference = _find_ticket_reference_for_booking(booking.id)
    ticket_qr_code = None
    if ticket_reference:
        ticket = Ticket.objects.filter(reference=ticket_reference).only("id", "payload", "ticket_id").first()
        if ticket:
            try:
                ticket_payload = persist_ticket_render_artifacts(ticket)
                ticket_qr_code = str(ticket_payload.get("qr_code") or "").strip() or None
            except Exception:
                ticket_qr_code = None

    metadata: dict[str, Any] = {
        "booking_id": booking.id,
        "booking_status": booking.booking_status,
        "booking_date": booking.booking_date.isoformat() if booking.booking_date else None,
        "user_id": booking.user_id,
        "user_email": booking.user.email if booking.user else None,
        "showtime_id": booking.showtime_id,
        "show_start_time": showtime.start_time.isoformat()
        if showtime and showtime.start_time
        else None,
        "show_end_time": showtime.end_time.isoformat()
        if showtime and showtime.end_time
        else None,
        "movie_id": movie.id if movie else None,
        "movie_title": movie.title if movie else None,
        "vendor_id": vendor.id if vendor else None,
        "vendor_name": vendor.name if vendor else None,
        "screen_id": screen.id if screen else None,
        "screen_number": screen.screen_number if screen else None,
        "seats": seat_labels,
        "seat_count": len(seat_labels),
        "amount_basis": float(_quantize_money(amount_basis)),
        "payment": {
            "id": latest_payment.id if latest_payment else None,
            "status": latest_payment.payment_status if latest_payment else None,
            "method": latest_payment.payment_method if latest_payment else None,
            "amount": float(_quantize_money(latest_payment.amount or Decimal("0")))
            if latest_payment
            else 0.0,
            "paid_at": latest_payment.payment_date.isoformat()
            if latest_payment and latest_payment.payment_date
            else None,
        },
        "refund": {
            "id": latest_refund.id if latest_refund else None,
            "status": latest_refund.refund_status if latest_refund else None,
            "amount": float(_quantize_money(latest_refund.refund_amount or Decimal("0")))
            if latest_refund
            else 0.0,
            "reason": latest_refund.refund_reason if latest_refund else None,
            "refunded_at": latest_refund.refund_date.isoformat()
            if latest_refund and latest_refund.refund_date
            else None,
        },
        "ticket_reference": ticket_reference,
        "ticket_qr_code": ticket_qr_code,
    }

    if include_booking_detail:
        metadata["booking_detail"] = build_booking_detail_payload(booking)

    return metadata


def _notify_payment_success(booking: Booking, show: Show) -> None:
    """Send payment success notifications for a booking."""
    title = "Payment successful"
    message = (
        f"Payment for booking #{booking.id} for {show.movie.title} was completed successfully."
    )
    metadata = _build_booking_notification_metadata(
        booking,
        include_booking_detail=True,
    )
    metadata.update(
        {
            "show_id": show.id,
            "showtime_id": booking.showtime_id,
            "amount": float(_quantize_money(booking.total_amount or Decimal("0"))),
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=booking.user_id,
        recipient_email=booking.user.email,
        event_type=Notification.EVENT_PAYMENT_SUCCESS,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )

    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=show.vendor_id,
        recipient_email=show.vendor.email,
        event_type=Notification.EVENT_PAYMENT_SUCCESS,
        title=title,
        message=f"Payment received for booking #{booking.id} ({show.movie.title}).",
        metadata=metadata,
        send_email_too=True,
    )


def _notify_vendor_when_show_fully_booked(
    *, show: Show, showtime: Showtime, screen: Screen
) -> None:
    """Notify vendor once when a show reaches full seat capacity."""
    capacity = int(screen.capacity or 0) if screen and screen.capacity else 0
    if capacity <= 0:
        return

    sold_count = len(_collect_sold_labels_for_showtime(showtime, lock=False))
    if sold_count < capacity:
        return

    updated_rows = (
        Show.objects.filter(pk=show.id)
        .exclude(status__iexact="Sold Out")
        .update(status="Sold Out")
    )
    if updated_rows == 0:
        return
    show.status = "Sold Out"

    hall = str(screen.screen_number or show.hall or "").strip() or "Hall"
    show_date_text = show.show_date.isoformat() if show.show_date else "-"
    show_time_text = show.start_time.strftime("%H:%M") if show.start_time else "-"
    title = "Show fully booked"
    message = (
        f"{show.movie.title} on {show_date_text} at {show_time_text} in {hall} "
        f"is fully booked ({sold_count}/{capacity} seats)."
    )
    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=show.vendor_id,
        recipient_email=show.vendor.email,
        event_type=Notification.EVENT_SHOW_UPDATE,
        title=title,
        message=message,
        metadata={
            "show_id": show.id,
            "showtime_id": showtime.id,
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "hall": hall,
            "sold_seat_count": sold_count,
            "capacity": capacity,
            "is_fully_booked": True,
        },
        send_email_too=True,
    )


def _resolve_notification_actor(request: Any) -> tuple[Optional[str], Optional[int]]:
    """Resolve notification actor role and ID from authenticated request."""
    if not is_authenticated(request):
        return None, None

    admin = resolve_admin(request)
    if admin:
        return Notification.ROLE_ADMIN, admin.id

    vendor = resolve_vendor(request)
    if vendor:
        return Notification.ROLE_VENDOR, vendor.id

    customer = resolve_customer(request)
    if customer:
        return Notification.ROLE_CUSTOMER, customer.id

    return None, None


def _ensure_customer_login_offer_notification(user: User) -> None:
    """Create one daily in-app offer notice for a customer after successful login."""
    if not user or not getattr(user, "id", None):
        return

    now = timezone.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    exists = Notification.objects.filter(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=user.id,
        event_type=Notification.EVENT_MARKETING_CAMPAIGN,
        metadata__notice_key="LOGIN_OFFER",
        created_at__gte=start_of_day,
    ).exists()
    if exists:
        return

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=user.id,
        recipient_email=user.email,
        event_type=Notification.EVENT_MARKETING_CAMPAIGN,
        title="New offers available",
        message="Check the latest movie offers and promo campaigns near you.",
        metadata={
            "notice_key": "LOGIN_OFFER",
            "source": "customer_login",
            "date": now.date().isoformat(),
        },
        send_email_too=False,
    )


def list_notifications(request: Any) -> tuple[dict[str, Any], int]:
    """List notifications scoped to the authenticated actor."""
    actor_role, actor_id = _resolve_notification_actor(request)
    if not actor_role or not actor_id:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    unread_only = parse_bool(request.query_params.get("unread"), default=False)
    raw_event_types = coalesce(request.query_params, "event_type", "eventType", default="")
    event_types = [
        str(item).strip().upper()
        for item in str(raw_event_types or "").split(",")
        if str(item).strip()
    ]
    base_queryset = Notification.objects.filter(
        recipient_role=actor_role,
        recipient_id=actor_id,
    )
    if event_types:
        base_queryset = base_queryset.filter(event_type__in=event_types)
    queryset = base_queryset.filter(is_read=False) if unread_only else base_queryset

    try:
        limit = int(request.query_params.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 100))

    notifications = list(queryset[:limit])
    unread_count = base_queryset.filter(is_read=False).count()
    total_count = base_queryset.count()
    event_unread_counts = {
        str(item.get("event_type") or ""): int(item.get("total") or 0)
        for item in base_queryset.filter(is_read=False)
        .values("event_type")
        .annotate(total=Count("id"))
    }
    event_total_counts = {
        str(item.get("event_type") or ""): int(item.get("total") or 0)
        for item in base_queryset.values("event_type").annotate(total=Count("id"))
    }
    return {
        "notifications": [_build_notification_payload(item) for item in notifications],
        "count": len(notifications),
        "total_count": total_count,
        "unread_count": unread_count,
        "event_total_counts": event_total_counts,
        "event_unread_counts": event_unread_counts,
    }, status.HTTP_200_OK


def mark_notifications_read(request: Any) -> tuple[dict[str, Any], int]:
    """Mark one, many, or all scoped notifications as read."""
    actor_role, actor_id = _resolve_notification_actor(request)
    if not actor_role or not actor_id:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    mark_all = parse_bool(coalesce(payload, "all", "mark_all", "markAll"), default=False)
    queryset = Notification.objects.filter(
        recipient_role=actor_role,
        recipient_id=actor_id,
    )

    if not mark_all:
        raw_ids = coalesce(payload, "ids", "notification_ids", "notificationIds")
        if not isinstance(raw_ids, list):
            return {
                "message": "Provide ids as a list or set all=true to mark all notifications.",
            }, status.HTTP_400_BAD_REQUEST

        ids: list[int] = []
        for item in raw_ids:
            parsed = _coerce_int(item)
            if parsed and parsed > 0:
                ids.append(parsed)
        if not ids:
            return {"message": "At least one valid notification id is required."}, status.HTTP_400_BAD_REQUEST
        queryset = queryset.filter(id__in=ids)

    now = timezone.now()
    updated = queryset.filter(is_read=False).update(is_read=True, read_at=now)
    unread_count = Notification.objects.filter(
        recipient_role=actor_role,
        recipient_id=actor_id,
        is_read=False,
    ).count()

    return {
        "message": "Notifications updated.",
        "updated": int(updated),
        "unread_count": int(unread_count),
    }, status.HTTP_200_OK


def send_admin_custom_email_to_vendor(request: Any) -> tuple[dict[str, Any], int]:
    """Send a custom admin message/email to a vendor and create notification records."""
    admin = resolve_admin(request)
    if not admin:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    vendor_id = _coerce_int(coalesce(payload, "vendor_id", "vendorId"))
    vendor_email = str(
        coalesce(payload, "vendor_email", "vendorEmail", "email", "recipient_email", "recipientEmail") or ""
    ).strip()

    vendor = None
    if vendor_id:
        vendor = Vendor.objects.filter(id=vendor_id, is_active=True).first()
    elif vendor_email:
        vendor = Vendor.objects.filter(email__iexact=vendor_email, is_active=True).first()
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    subject = str(coalesce(payload, "subject", "title") or "").strip()
    message = str(coalesce(payload, "message", "body") or "").strip()
    if not subject:
        return {"message": "subject is required."}, status.HTTP_400_BAD_REQUEST
    if not message:
        return {"message": "message is required."}, status.HTTP_400_BAD_REQUEST

    send_email_too = parse_bool(coalesce(payload, "send_email", "sendEmail"), default=True)
    metadata = coalesce(payload, "metadata", default={})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "source": "admin_custom_email",
            "sender_role": Notification.ROLE_ADMIN,
            "sender_id": admin.id,
            "sender_email": getattr(admin, "email", None),
            "target_vendor_id": vendor.id,
        }
    )

    notification = _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=vendor.id,
        recipient_email=vendor.email,
        event_type=Notification.EVENT_CUSTOM_MESSAGE,
        title=subject,
        message=message,
        metadata=metadata,
        send_email_too=send_email_too,
    )

    _create_notification(
        recipient_role=Notification.ROLE_ADMIN,
        recipient_id=admin.id,
        recipient_email=getattr(admin, "email", None),
        event_type=Notification.EVENT_CUSTOM_MESSAGE,
        title=f"Message sent to vendor {vendor.name or vendor.email}",
        message=subject,
        metadata={
            "source": "admin_custom_email",
            "vendor_id": vendor.id,
            "vendor_email": vendor.email,
            "target_notification_id": notification.id,
        },
        send_email_too=False,
    )

    return {
        "message": "Custom message sent to vendor.",
        "notification": _build_notification_payload(notification),
    }, status.HTTP_200_OK


def send_vendor_custom_email_to_customer(request: Any) -> tuple[dict[str, Any], int]:
    """Send a custom vendor message/email to a customer tied to vendor activity."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    user_id = _coerce_int(coalesce(payload, "user_id", "userId", "customer_id", "customerId"))
    user_email = str(
        coalesce(payload, "user_email", "userEmail", "email", "recipient_email", "recipientEmail") or ""
    ).strip()
    booking_id = _coerce_int(coalesce(payload, "booking_id", "bookingId"))

    customer = None
    if booking_id:
        booking = (
            Booking.objects.select_related("user", "showtime__screen")
            .filter(id=booking_id, showtime__screen__vendor_id=vendor.id)
            .first()
        )
        if booking:
            customer = booking.user
    if not customer and user_id:
        customer = User.objects.filter(id=user_id, is_active=True).first()
    if not customer and user_email:
        customer = User.objects.filter(email__iexact=user_email, is_active=True).first()
    if not customer:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    has_relationship = Booking.objects.filter(
        user_id=customer.id,
        showtime__screen__vendor_id=vendor.id,
    ).exists()
    if not has_relationship:
        return {
            "message": "You can only message customers who booked with your cinema.",
        }, status.HTTP_403_FORBIDDEN

    subject = str(coalesce(payload, "subject", "title") or "").strip()
    message = str(coalesce(payload, "message", "body") or "").strip()
    if not subject:
        return {"message": "subject is required."}, status.HTTP_400_BAD_REQUEST
    if not message:
        return {"message": "message is required."}, status.HTTP_400_BAD_REQUEST

    send_email_too = parse_bool(coalesce(payload, "send_email", "sendEmail"), default=True)
    metadata = coalesce(payload, "metadata", default={})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "source": "vendor_custom_email",
            "sender_role": Notification.ROLE_VENDOR,
            "sender_id": vendor.id,
            "sender_email": getattr(vendor, "email", None),
            "target_user_id": customer.id,
        }
    )

    notification = _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=Notification.EVENT_CUSTOM_MESSAGE,
        title=subject,
        message=message,
        metadata=metadata,
        send_email_too=send_email_too,
    )

    _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=vendor.id,
        recipient_email=vendor.email,
        event_type=Notification.EVENT_CUSTOM_MESSAGE,
        title=f"Message sent to customer {customer.email}",
        message=subject,
        metadata={
            "source": "vendor_custom_email",
            "customer_id": customer.id,
            "customer_email": customer.email,
            "target_notification_id": notification.id,
        },
        send_email_too=False,
    )

    return {
        "message": "Custom message sent to customer.",
        "notification": _build_notification_payload(notification),
    }, status.HTTP_200_OK


def notify_user_feedback_submission(review: Any) -> None:
    """Notify vendors/admin when a customer submits movie feedback/review."""
    if not review or not getattr(review, "movie_id", None) or not getattr(review, "user_id", None):
        return

    movie = getattr(review, "movie", None)
    customer = getattr(review, "user", None)
    movie_title = str(getattr(movie, "title", None) or f"Movie #{review.movie_id}")
    customer_label = "Customer"
    if customer:
        customer_label = str(customer.full_name or customer.username or customer.email or f"User #{customer.id}")

    comment_text = str(getattr(review, "comment", "") or "").strip()
    metadata = {
        "source": "user_feedback",
        "review_id": review.id,
        "movie_id": review.movie_id,
        "movie_title": movie_title,
        "user_id": review.user_id,
        "rating": int(getattr(review, "rating", 0) or 0),
        "comment_preview": comment_text[:240],
    }
    title = "New user feedback received"
    message = f"{customer_label} rated {movie_title} {int(getattr(review, 'rating', 0) or 0)}/5."

    vendor_ids = list(
        Show.objects.filter(movie_id=review.movie_id)
        .values_list("vendor_id", flat=True)
        .distinct()
    )
    if vendor_ids:
        vendors = Vendor.objects.filter(id__in=vendor_ids, is_active=True).only("id", "email")
        for vendor in vendors:
            _create_notification(
                recipient_role=Notification.ROLE_VENDOR,
                recipient_id=vendor.id,
                recipient_email=vendor.email,
                event_type=Notification.EVENT_USER_FEEDBACK,
                title=title,
                message=message,
                metadata=metadata,
                send_email_too=False,
            )

    admins = Admin.objects.filter(is_active=True).only("id", "email")
    for admin in admins:
        _create_notification(
            recipient_role=Notification.ROLE_ADMIN,
            recipient_id=admin.id,
            recipient_email=admin.email,
            event_type=Notification.EVENT_USER_FEEDBACK,
            title=title,
            message=message,
            metadata=metadata,
            send_email_too=False,
        )


def _quantize_money(value: Decimal) -> Decimal:
    """Normalize decimal amounts to 2 decimal places."""
    return (value if isinstance(value, Decimal) else Decimal(str(value or 0))).quantize(Decimal("0.01"))


def _credit_user_wallet_for_booking_refund(
    *,
    booking: Booking,
    amount: Decimal,
    refund: Optional[Refund] = None,
    reason: Optional[str] = None,
    source: str = "booking_refund",
) -> Optional[UserWalletTransaction]:
    """Credit customer cash wallet for a successful booking refund once."""
    if not booking or not booking.user_id:
        return None

    credit_amount = _quantize_money(amount or Decimal("0"))
    if credit_amount <= Decimal("0"):
        return None

    wallet, _ = UserWallet.objects.get_or_create(user_id=booking.user_id)
    wallet = UserWallet.objects.select_for_update().get(pk=wallet.pk)

    reference_suffix = str(refund.id) if refund and refund.id else str(booking.id)
    reference_id = f"BOOKING-REFUND-{booking.id}-{reference_suffix}"
    existing_tx = (
        UserWalletTransaction.objects.select_for_update()
        .filter(
            user_id=booking.user_id,
            booking_id=booking.id,
            transaction_type=UserWalletTransaction.TYPE_REFUND,
            status=UserWalletTransaction.STATUS_COMPLETED,
            reference_id=reference_id,
        )
        .order_by("-id")
        .first()
    )
    if existing_tx:
        return existing_tx

    credit_tx = UserWalletTransaction.objects.create(
        wallet=wallet,
        user_id=booking.user_id,
        booking=booking,
        transaction_type=UserWalletTransaction.TYPE_REFUND,
        status=UserWalletTransaction.STATUS_COMPLETED,
        amount=credit_amount,
        reference_id=reference_id,
        provider="SYSTEM",
        processed_at=timezone.now(),
        metadata={
            "source": str(source or "booking_refund").strip()[:64],
            "reason": str(reason or "").strip()[:255] or None,
            "refund_id": refund.id if refund and refund.id else None,
            "booking_id": booking.id,
        },
    )
    _recalculate_user_wallet_snapshot(wallet)
    return credit_tx


def _get_platform_revenue_config() -> PlatformRevenueConfig:
    """Return singleton platform revenue config."""
    config, _ = PlatformRevenueConfig.objects.get_or_create(key="default")
    return config


def _resolve_default_commission_percent() -> Decimal:
    """Resolve default commission percent from DB config with settings fallback."""
    config = _get_platform_revenue_config()
    config_value = getattr(config, "commission_percent", None)
    if config_value is not None:
        try:
            parsed = Decimal(str(config_value))
            return _quantize_money(max(Decimal("0"), min(parsed, Decimal("100"))))
        except (TypeError, ValueError, InvalidOperation):
            pass

    default_raw = getattr(settings, "PLATFORM_COMMISSION_PERCENT", PLATFORM_COMMISSION_PERCENT)
    try:
        default_percent = Decimal(str(default_raw))
    except (TypeError, ValueError, InvalidOperation):
        default_percent = PLATFORM_COMMISSION_PERCENT
    return _quantize_money(max(Decimal("0"), min(default_percent, Decimal("100"))))


def _resolve_vendor_commission_percent(vendor: Optional[Vendor]) -> Decimal:
    """Resolve effective commission percent from vendor override or configured default."""
    default_percent = _resolve_default_commission_percent()

    vendor_percent = getattr(vendor, "commission_percent", None) if vendor else None
    try:
        effective = Decimal(str(vendor_percent)) if vendor_percent is not None else default_percent
    except (TypeError, ValueError, InvalidOperation):
        effective = default_percent

    if effective < Decimal("0"):
        effective = Decimal("0")
    if effective > Decimal("100"):
        effective = Decimal("100")
    return _quantize_money(effective)


def _wallet_for_vendor(vendor: Vendor) -> Wallet:
    """Get or create vendor wallet."""
    wallet, _ = Wallet.objects.get_or_create(vendor=vendor)
    return wallet


def _admin_wallet() -> AdminWallet:
    """Get or create singleton admin wallet."""
    wallet, _ = AdminWallet.objects.get_or_create(key="primary")
    return wallet


def _recalculate_user_wallet_snapshot(wallet: UserWallet) -> UserWallet:
    """Rebuild user cash wallet totals from immutable completed transactions."""
    completed = wallet.transactions.filter(status=UserWalletTransaction.STATUS_COMPLETED)

    credits = _quantize_money(
        completed.filter(
            transaction_type__in=[
                UserWalletTransaction.TYPE_TOPUP,
                UserWalletTransaction.TYPE_REFUND,
                UserWalletTransaction.TYPE_ADJUSTMENT,
            ]
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )
    debits = _quantize_money(
        completed.filter(transaction_type=UserWalletTransaction.TYPE_DEBIT)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )

    wallet.balance = _quantize_money(credits - debits)
    wallet.total_credited = credits
    wallet.total_debited = debits
    wallet.save(update_fields=["balance", "total_credited", "total_debited", "updated_at"])
    return wallet


def recalculate_user_wallet_snapshot(wallet: UserWallet) -> UserWallet:
    """Public wrapper for user wallet snapshot recalculation."""
    return _recalculate_user_wallet_snapshot(wallet)


def _recalculate_referral_wallet_snapshot(wallet: ReferralWallet) -> ReferralWallet:
    """Rebuild referral wallet totals from immutable referral transactions."""
    transactions = wallet.transactions.all()

    total_credited = _quantize_money(
        transactions.filter(
            transaction_type=ReferralTransaction.TYPE_CREDIT,
            status=ReferralTransaction.STATUS_COMPLETED,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )
    total_debited = _quantize_money(
        transactions.filter(
            transaction_type__in=[
                ReferralTransaction.TYPE_DEBIT,
                ReferralTransaction.TYPE_REVERSAL,
            ],
            status=ReferralTransaction.STATUS_COMPLETED,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )
    total_expired = _quantize_money(
        transactions.filter(
            transaction_type=ReferralTransaction.TYPE_EXPIRE,
            status=ReferralTransaction.STATUS_EXPIRED,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )

    wallet.balance = _quantize_money(total_credited - total_debited - total_expired)
    wallet.total_credited = total_credited
    wallet.total_debited = total_debited
    wallet.total_expired = total_expired
    wallet.save(update_fields=["balance", "total_credited", "total_debited", "total_expired", "updated_at"])
    return wallet


def _recalculate_vendor_wallet_snapshot(wallet: Wallet) -> Wallet:
    """Rebuild vendor wallet balances from immutable completed transactions."""
    completed = wallet.transactions.filter(status=Transaction.STATUS_COMPLETED)

    earning_amount = _quantize_money(
        completed.filter(transaction_type=Transaction.TYPE_BOOKING_EARNING).aggregate(total=Sum("amount")).get("total")
        or Decimal("0")
    )
    reversal_amount = _quantize_money(
        completed.filter(transaction_type=Transaction.TYPE_BOOKING_REVERSAL).aggregate(total=Sum("amount")).get("total")
        or Decimal("0")
    )
    withdrawn_amount = _quantize_money(
        completed.filter(transaction_type=Transaction.TYPE_WITHDRAWAL_APPROVED)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )

    gross_earned = _quantize_money(
        completed.filter(transaction_type=Transaction.TYPE_BOOKING_EARNING)
        .aggregate(total=Sum("gross_amount"))
        .get("total")
        or Decimal("0")
    )
    gross_reversed = _quantize_money(
        completed.filter(transaction_type=Transaction.TYPE_BOOKING_REVERSAL)
        .aggregate(total=Sum("gross_amount"))
        .get("total")
        or Decimal("0")
    )
    commission_earned = _quantize_money(
        completed.filter(transaction_type=Transaction.TYPE_BOOKING_EARNING)
        .aggregate(total=Sum("commission_amount"))
        .get("total")
        or Decimal("0")
    )
    commission_reversed = _quantize_money(
        completed.filter(transaction_type=Transaction.TYPE_BOOKING_REVERSAL)
        .aggregate(total=Sum("commission_amount"))
        .get("total")
        or Decimal("0")
    )

    wallet.balance = _quantize_money(earning_amount - reversal_amount - withdrawn_amount)
    wallet.total_earnings = _quantize_money(gross_earned - gross_reversed)
    wallet.total_commission = _quantize_money(commission_earned - commission_reversed)
    wallet.total_withdrawn = withdrawn_amount
    wallet.save(update_fields=["balance", "total_earnings", "total_commission", "total_withdrawn", "updated_at"])
    return wallet


def _recalculate_admin_wallet_snapshot(wallet: AdminWallet) -> AdminWallet:
    """Rebuild admin wallet balances from immutable completed admin transactions."""
    completed = wallet.transactions.filter(status=AdminWalletTransaction.STATUS_COMPLETED)

    commission_credits = _quantize_money(
        completed.filter(transaction_type=AdminWalletTransaction.TYPE_COMMISSION_CREDIT)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )
    commission_reversals = _quantize_money(
        completed.filter(transaction_type=AdminWalletTransaction.TYPE_COMMISSION_REVERSAL)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )
    adjustments = _quantize_money(
        completed.filter(transaction_type=AdminWalletTransaction.TYPE_ADJUSTMENT)
        .aggregate(total=Sum("amount"))
        .get("total")
        or Decimal("0")
    )

    wallet.balance = _quantize_money(commission_credits + adjustments - commission_reversals)
    wallet.total_commission_earned = commission_credits
    wallet.total_commission_reversed = commission_reversals
    wallet.save(update_fields=["balance", "total_commission_earned", "total_commission_reversed", "updated_at"])
    return wallet


def _pending_withdrawal_total(wallet: Wallet) -> Decimal:
    """Calculate pending withdrawal requests total for a wallet."""
    pending = wallet.transactions.filter(
        transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST,
        status=Transaction.STATUS_PENDING,
    ).aggregate(total=Sum("amount"))
    return _quantize_money(pending.get("total") or Decimal("0"))


def _get_or_create_vendor_payout_profile(vendor: Vendor) -> VendorPayoutProfile:
    """Return a persisted payout profile for the vendor with safe defaults."""
    profile, created = VendorPayoutProfile.objects.get_or_create(
        vendor=vendor,
        defaults={
            "destination_type": VendorPayoutProfile.DESTINATION_BANK,
            "minimum_withdrawal_amount": VENDOR_PAYOUT_DEFAULT_MINIMUM_WITHDRAWAL,
            "payout_schedule": VENDOR_PAYOUT_DEFAULT_SCHEDULE,
            "payout_schedule_days": [VENDOR_PAYOUT_DEFAULT_SCHEDULE_DAY],
            "payout_schedule_time": VENDOR_PAYOUT_DEFAULT_SCHEDULE_TIME,
        },
    )
    if created:
        return profile

    changed_fields: list[str] = []
    if not profile.minimum_withdrawal_amount:
        profile.minimum_withdrawal_amount = VENDOR_PAYOUT_DEFAULT_MINIMUM_WITHDRAWAL
        changed_fields.append("minimum_withdrawal_amount")
    if not profile.payout_schedule:
        profile.payout_schedule = VENDOR_PAYOUT_DEFAULT_SCHEDULE
        changed_fields.append("payout_schedule")
    if not isinstance(profile.payout_schedule_days, list) or not profile.payout_schedule_days:
        profile.payout_schedule_days = [VENDOR_PAYOUT_DEFAULT_SCHEDULE_DAY]
        changed_fields.append("payout_schedule_days")
    if not profile.payout_schedule_time:
        profile.payout_schedule_time = VENDOR_PAYOUT_DEFAULT_SCHEDULE_TIME
        changed_fields.append("payout_schedule_time")
    if changed_fields:
        profile.save(update_fields=changed_fields + ["updated_at"])
    return profile


def _normalize_schedule_day_values(values: Any) -> list[int]:
    if not isinstance(values, list):
        values = [values]
    normalized: list[int] = []
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        parsed = max(0, min(parsed, 31))
        if parsed not in normalized:
            normalized.append(parsed)
    return normalized


def _payout_schedule_time_value(profile: VendorPayoutProfile) -> time_cls:
    return profile.payout_schedule_time or VENDOR_PAYOUT_DEFAULT_SCHEDULE_TIME


def _vendor_payout_window_matches(profile: VendorPayoutProfile, current_dt: datetime) -> bool:
    schedule = str(profile.payout_schedule or VENDOR_PAYOUT_DEFAULT_SCHEDULE).strip().upper()
    current_date = current_dt.date()
    current_time = current_dt.time()
    schedule_time = _payout_schedule_time_value(profile)
    if current_time < schedule_time:
        return False

    if schedule == VendorPayoutProfile.SCHEDULE_DAILY:
        return True

    if schedule == VendorPayoutProfile.SCHEDULE_MONTHLY:
        day_values = _normalize_schedule_day_values(profile.payout_schedule_days or [1])
        return current_date.day in day_values

    day_values = _normalize_schedule_day_values(profile.payout_schedule_days or [VENDOR_PAYOUT_DEFAULT_SCHEDULE_DAY])
    return current_date.weekday() in day_values


def _next_vendor_payout_window(profile: VendorPayoutProfile, now: Optional[datetime] = None) -> Optional[datetime]:
    current_dt = _ensure_timezone_aware(now or timezone.now()) or timezone.now()
    schedule = str(profile.payout_schedule or VENDOR_PAYOUT_DEFAULT_SCHEDULE).strip().upper()
    schedule_time = _payout_schedule_time_value(profile)
    day_values = _normalize_schedule_day_values(profile.payout_schedule_days or [VENDOR_PAYOUT_DEFAULT_SCHEDULE_DAY])
    search_days = 45 if schedule == VendorPayoutProfile.SCHEDULE_MONTHLY else 14
    for offset in range(search_days):
        candidate_date = (current_dt + timedelta(days=offset)).date()
        if schedule == VendorPayoutProfile.SCHEDULE_MONTHLY:
            if candidate_date.day not in day_values:
                continue
        elif schedule == VendorPayoutProfile.SCHEDULE_WEEKLY:
            if candidate_date.weekday() not in day_values:
                continue
        candidate_dt = _ensure_timezone_aware(datetime.combine(candidate_date, schedule_time))
        if candidate_dt and candidate_dt > current_dt:
            return candidate_dt
        if candidate_dt and offset == 0 and candidate_dt >= current_dt:
            return candidate_dt
    return None


def _serialize_vendor_payout_profile(profile: VendorPayoutProfile) -> dict[str, Any]:
    schedule_time = profile.payout_schedule_time.isoformat(timespec="minutes") if profile.payout_schedule_time else None
    reference = str(profile.destination_reference or "").strip()
    masked_reference = None
    if reference:
        masked_reference = reference[:2] + ("*" * max(len(reference) - 4, 4)) + reference[-2:]
    return {
        "vendor_id": profile.vendor_id,
        "destination_type": profile.destination_type,
        "destination_name": profile.destination_name,
        "destination_reference": masked_reference,
        "account_holder_name": profile.account_holder_name,
        "bank_name": profile.bank_name,
        "branch_name": profile.branch_name,
        "minimum_withdrawal_amount": float(_quantize_money(profile.minimum_withdrawal_amount or VENDOR_PAYOUT_DEFAULT_MINIMUM_WITHDRAWAL)),
        "payout_schedule": profile.payout_schedule,
        "payout_schedule_days": profile.payout_schedule_days or [],
        "payout_schedule_time": schedule_time,
        "failed_retry_limit": int(profile.failed_retry_limit or 0),
        "retry_backoff_minutes": int(profile.retry_backoff_minutes or 0),
        "is_destination_verified": bool(profile.is_destination_verified),
        "destination_verified_at": profile.destination_verified_at.isoformat() if profile.destination_verified_at else None,
        "verification_requested_at": profile.verification_requested_at.isoformat() if profile.verification_requested_at else None,
    }


def _vendor_payout_policy_payload(profile: VendorPayoutProfile, now: Optional[datetime] = None) -> dict[str, Any]:
    current_dt = _ensure_timezone_aware(now or timezone.now()) or timezone.now()
    next_window = _next_vendor_payout_window(profile, now=current_dt)
    return {
        "minimum_withdrawal_amount": float(_quantize_money(profile.minimum_withdrawal_amount or VENDOR_PAYOUT_DEFAULT_MINIMUM_WITHDRAWAL)),
        "payout_schedule": profile.payout_schedule,
        "payout_schedule_days": profile.payout_schedule_days or [],
        "payout_schedule_time": profile.payout_schedule_time.isoformat(timespec="minutes") if profile.payout_schedule_time else None,
        "next_payout_window": next_window.isoformat() if next_window else None,
        "payout_window_open": _vendor_payout_window_matches(profile, current_dt),
        "failed_retry_limit": int(profile.failed_retry_limit or 0),
        "retry_backoff_minutes": int(profile.retry_backoff_minutes or 0),
    }


def _record_vendor_booking_earning(
    booking: Booking,
    gross_amount: Optional[Decimal] = None,
    payment: Optional[Payment] = None,
) -> None:
    """Credit vendor wallet + admin wallet for a successful booking payment."""
    showtime = booking.showtime
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    if not vendor:
        return

    existing = Transaction.objects.filter(
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_EARNING,
    ).exists()
    if existing:
        return

    gross = _quantize_money(gross_amount if gross_amount is not None else booking.total_amount or Decimal("0"))
    commission_percent = _resolve_vendor_commission_percent(vendor)
    commission = _quantize_money((gross * commission_percent) / Decimal("100"))
    net = _quantize_money(gross - commission)

    booking.total_amount = gross
    booking.admin_commission = commission
    booking.vendor_earning = net
    booking.commission_percent_applied = commission_percent
    booking.save(
        update_fields=[
            "total_amount",
            "admin_commission",
            "vendor_earning",
            "commission_percent_applied",
        ]
    )

    wallet = _wallet_for_vendor(vendor)

    Transaction.objects.create(
        wallet=wallet,
        vendor=vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_EARNING,
        amount=net,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Booking #{booking.id} earning",
    )
    VendorCommissionLedger.objects.create(
        vendor=vendor,
        wallet=wallet,
        booking=booking,
        payment=payment,
        entry_type=VendorCommissionLedger.ENTRY_EARNED,
        status=VendorCommissionLedger.STATUS_COMPLETED,
        amount=net,
        gross_amount=gross,
        commission_amount=commission,
        commission_percent=commission_percent,
        metadata={"source": "booking_success"},
    )
    Transaction.objects.create(
        wallet=wallet,
        vendor=vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_PLATFORM_COMMISSION,
        amount=commission,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Platform commission for booking #{booking.id}",
    )

    _recalculate_vendor_wallet_snapshot(wallet)

    admin_wallet = _admin_wallet()
    AdminWalletTransaction.objects.create(
        wallet=admin_wallet,
        booking=booking,
        payment=payment,
        vendor=vendor,
        transaction_type=AdminWalletTransaction.TYPE_COMMISSION_CREDIT,
        status=AdminWalletTransaction.STATUS_COMPLETED,
        amount=commission,
        gross_amount=gross,
        commission_percent=commission_percent,
        description=f"Commission credited for booking #{booking.id}",
        metadata={"source": "booking_success"},
    )
    _recalculate_admin_wallet_snapshot(admin_wallet)
    enqueue_financial_summary_rollup_job(scope="ALL", metadata={"source": "booking_earning"})


def _reverse_vendor_booking_earning(booking: Booking, *, reason: Optional[str] = None) -> None:
    """Reverse wallet earning + commission for a refunded/cancelled booking once."""
    earning_txn = (
        Transaction.objects.select_for_update()
        .filter(
            booking=booking,
            transaction_type=Transaction.TYPE_BOOKING_EARNING,
            status=Transaction.STATUS_COMPLETED,
        )
        .order_by("-id")
        .first()
    )
    if not earning_txn:
        return

    already_reversed = Transaction.objects.filter(
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_REVERSAL,
        status=Transaction.STATUS_COMPLETED,
    ).exists()
    if already_reversed:
        return

    wallet = Wallet.objects.select_for_update().filter(id=earning_txn.wallet_id).first()
    if not wallet:
        return

    net = _quantize_money(earning_txn.amount or Decimal("0"))
    gross = _quantize_money(earning_txn.gross_amount or Decimal("0"))
    commission = _quantize_money(earning_txn.commission_amount or Decimal("0"))

    description_suffix = f" ({reason})" if reason else ""
    Transaction.objects.create(
        wallet=wallet,
        vendor=earning_txn.vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_BOOKING_REVERSAL,
        amount=net,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Booking #{booking.id} earning reversed{description_suffix}",
    )
    ReversalLedger.objects.create(
        vendor=earning_txn.vendor,
        wallet=wallet,
        booking=booking,
        reversal_type=ReversalLedger.TYPE_BOOKING_EARNING,
        status=ReversalLedger.STATUS_COMPLETED,
        amount=net,
        gross_amount=gross,
        commission_amount=commission,
        metadata={"reason": reason or "", "source": "booking_reversal"},
        decision_metadata={"reason": reason or ""},
    )
    Transaction.objects.create(
        wallet=wallet,
        vendor=earning_txn.vendor,
        booking=booking,
        transaction_type=Transaction.TYPE_PLATFORM_COMMISSION_REVERSAL,
        amount=commission,
        commission_amount=commission,
        gross_amount=gross,
        status=Transaction.STATUS_COMPLETED,
        description=f"Platform commission reversed for booking #{booking.id}{description_suffix}",
    )
    ReversalLedger.objects.create(
        vendor=earning_txn.vendor,
        wallet=wallet,
        booking=booking,
        reversal_type=ReversalLedger.TYPE_PLATFORM_COMMISSION,
        status=ReversalLedger.STATUS_COMPLETED,
        amount=commission,
        gross_amount=gross,
        commission_amount=commission,
        metadata={"reason": reason or "", "source": "commission_reversal"},
        decision_metadata={"reason": reason or ""},
    )
    _recalculate_vendor_wallet_snapshot(wallet)

    admin_wallet = _admin_wallet()

    refund_obj = None
    latest_payment = booking.payments.order_by("-payment_date", "-id").first()
    if latest_payment:
        refund_obj = latest_payment.refunds.order_by("-refund_date", "-id").first()

    AdminWalletTransaction.objects.create(
        wallet=admin_wallet,
        booking=booking,
        payment=latest_payment,
        refund=refund_obj,
        vendor=earning_txn.vendor,
        transaction_type=AdminWalletTransaction.TYPE_COMMISSION_REVERSAL,
        status=AdminWalletTransaction.STATUS_COMPLETED,
        amount=commission,
        gross_amount=gross,
        commission_percent=_quantize_money(booking.commission_percent_applied or Decimal("0")),
        description=f"Commission reversed for booking #{booking.id}{description_suffix}",
        metadata={"reason": reason or ""},
    )
    _recalculate_admin_wallet_snapshot(admin_wallet)

    booking.admin_commission = Decimal("0.00")
    booking.vendor_earning = Decimal("0.00")
    booking.save(update_fields=["admin_commission", "vendor_earning"])
    enqueue_financial_summary_rollup_job(scope="ALL", metadata={"source": "booking_reversal"})


def get_vendor_wallet_balance(request: Any) -> tuple[dict[str, Any], int]:
    """Return wallet balance and summary for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    wallet = _wallet_for_vendor(vendor)
    payout_profile = _get_or_create_vendor_payout_profile(vendor)
    _recalculate_vendor_wallet_snapshot(wallet)
    pending_withdrawal = _pending_withdrawal_total(wallet)
    available = _quantize_money((wallet.balance or Decimal("0")) - pending_withdrawal)
    if available < Decimal("0"):
        available = Decimal("0")
    commission_percent = _resolve_vendor_commission_percent(vendor)
    withdrawal_history = list(
        WithdrawalLedger.objects.filter(vendor=vendor).select_related("withdrawal_transaction").order_by("-created_at", "-id")[:50]
    )

    return {
        "vendor_id": vendor.id,
        "wallet": {
            "balance": float(_quantize_money(wallet.balance or Decimal("0"))),
            "available_balance": float(available),
            "pending_withdrawals": float(pending_withdrawal),
            "total_earnings": float(_quantize_money(wallet.total_earnings or Decimal("0"))),
            "total_commission": float(_quantize_money(wallet.total_commission or Decimal("0"))),
            "total_withdrawn": float(_quantize_money(wallet.total_withdrawn or Decimal("0"))),
            "platform_commission_percent": float(commission_percent),
        },
        "payout_profile": _serialize_vendor_payout_profile(payout_profile),
        "payout_policy": _vendor_payout_policy_payload(payout_profile),
        "withdrawal_history": [
            {
                "id": entry.id,
                "status": entry.status,
                "amount": float(_quantize_money(entry.amount or Decimal("0"))),
                "gross_amount": float(_quantize_money(entry.gross_amount or Decimal("0"))),
                "payout_reference": entry.payout_reference,
                "decision_reason": entry.decision_reason,
                "decision_at": entry.decision_at.isoformat() if entry.decision_at else None,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "retry_count": int((entry.decision_metadata or {}).get("retry_count") or 0),
                "transaction_id": entry.withdrawal_transaction_id,
                "transaction_status": entry.withdrawal_transaction.status if entry.withdrawal_transaction else None,
            }
            for entry in withdrawal_history
        ],
    }, status.HTTP_200_OK


def create_vendor_withdrawal_request(request: Any) -> tuple[dict[str, Any], int]:
    """Create OTP-gated withdrawal request for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    wallet = _wallet_for_vendor(vendor)
    payout_profile = _get_or_create_vendor_payout_profile(vendor)
    verification_metadata = dict(payout_profile.verification_metadata or {})
    pending_request = verification_metadata.get("pending_withdrawal_request") if isinstance(verification_metadata, dict) else None
    otp = str(coalesce(payload, "otp", "verification_otp", "verificationOtp") or "").strip()

    if otp:
        if not isinstance(pending_request, dict):
            return {"message": "No pending OTP withdrawal request found. Start withdrawal first."}, status.HTTP_400_BAD_REQUEST

        cutoff = timezone.now() - timedelta(minutes=EMAIL_OTP_TTL_MINUTES)
        record = OTPVerification.objects.filter(
            email__iexact=vendor.email,
            otp=otp,
            is_verified=False,
            created_at__gte=cutoff,
        ).order_by("-created_at").first()
        if not record:
            return {"message": "Invalid or expired OTP."}, status.HTTP_400_BAD_REQUEST

        amount = _parse_price_amount(pending_request.get("amount"))
        if amount is None or amount <= Decimal("0"):
            return {"message": "Pending withdrawal amount is invalid. Please retry withdrawal."}, status.HTTP_400_BAD_REQUEST

        phone_digits = "".join(ch for ch in str(pending_request.get("phone") or "") if ch.isdigit())
        if len(phone_digits) > 10 and phone_digits.startswith("977"):
            phone_digits = phone_digits[-10:]
        note = str(pending_request.get("note") or "").strip() or None

        with transaction.atomic():
            locked_wallet = Wallet.objects.select_for_update().filter(id=wallet.id).first()
            if not locked_wallet:
                return {"message": "Wallet not found for withdrawal request."}, status.HTTP_404_NOT_FOUND

            _recalculate_vendor_wallet_snapshot(locked_wallet)
            pending_withdrawal = _pending_withdrawal_total(locked_wallet)
            available = _quantize_money((locked_wallet.balance or Decimal("0")) - pending_withdrawal)
            if amount > available:
                return {
                    "message": "Insufficient withdrawable balance.",
                    "available_balance": float(max(available, Decimal("0"))),
                }, status.HTTP_400_BAD_REQUEST

            payout_profile.destination_type = VendorPayoutProfile.DESTINATION_MOBILE
            payout_profile.destination_name = "eSewa"
            if phone_digits:
                payout_profile.destination_reference = phone_digits
            payout_profile.is_destination_verified = True
            payout_profile.destination_verified_at = timezone.now()
            verification_metadata = dict(payout_profile.verification_metadata or {})
            verification_metadata["auto_verified_by"] = "vendor_withdrawal_otp"
            verification_metadata["auto_verified_at"] = timezone.now().isoformat()
            verification_metadata["last_withdrawal_otp_verified_at"] = timezone.now().isoformat()
            verification_metadata.pop("pending_withdrawal_request", None)
            payout_profile.verification_metadata = verification_metadata
            payout_profile.save(
                update_fields=[
                    "destination_type",
                    "destination_name",
                    "destination_reference",
                    "is_destination_verified",
                    "destination_verified_at",
                    "verification_metadata",
                    "updated_at",
                ]
            )

            withdrawal_txn = Transaction.objects.create(
                wallet=locked_wallet,
                vendor=vendor,
                transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST,
                amount=_quantize_money(amount),
                commission_amount=Decimal("0.00"),
                gross_amount=_quantize_money(amount),
                status=Transaction.STATUS_COMPLETED,
                description=note or "Withdrawal request (OTP verified)",
                decision_metadata={
                    "action": "OTP_VERIFY_AND_APPROVE",
                    "approved_by": vendor.id,
                    "approved_at": timezone.now().isoformat(),
                    "reason": note,
                    "destination_phone": phone_digits or None,
                },
                decision_reason=note,
                decision_at=timezone.now(),
            )

            Transaction.objects.create(
                wallet=locked_wallet,
                vendor=vendor,
                transaction_type=Transaction.TYPE_WITHDRAWAL_APPROVED,
                amount=_quantize_money(amount),
                commission_amount=Decimal("0.00"),
                gross_amount=_quantize_money(amount),
                status=Transaction.STATUS_COMPLETED,
                description=f"Withdrawal approved via OTP for request #{withdrawal_txn.id}",
            )

            WithdrawalLedger.objects.create(
                vendor=vendor,
                wallet=locked_wallet,
                withdrawal_transaction=withdrawal_txn,
                status=WithdrawalLedger.STATUS_APPROVED,
                amount=_quantize_money(amount),
                gross_amount=_quantize_money(amount),
                metadata={"source": "vendor_withdrawal_otp"},
                decision_metadata={"action": "OTP_VERIFY_AND_APPROVE", "reason": note},
                decision_reason=note,
                decision_at=timezone.now(),
            )

            _recalculate_vendor_wallet_snapshot(locked_wallet)

        record.is_verified = True
        record.save(update_fields=["is_verified"])

        enqueue_withdrawal_settlement_job(
            withdrawal_transaction_id=withdrawal_txn.id,
            payout_reference=f"WSET-{withdrawal_txn.transaction_uuid or withdrawal_txn.id}",
            metadata={"source": "vendor_otp_approval"},
        )

        return {
            "message": "OTP verified. Payment successful.",
            "payment_success": True,
            "transaction": {
                "id": withdrawal_txn.id,
                "transaction_uuid": withdrawal_txn.transaction_uuid,
                "type": withdrawal_txn.transaction_type,
                "status": withdrawal_txn.status,
                "amount": float(withdrawal_txn.amount),
                "created_at": withdrawal_txn.created_at.isoformat() if withdrawal_txn.created_at else None,
                "description": withdrawal_txn.description,
            },
        }, status.HTTP_200_OK

    amount = _parse_price_amount(coalesce(payload, "amount", "withdraw_amount", "withdrawAmount"))
    if amount is None or amount <= Decimal("0"):
        return {"message": "Valid amount is required."}, status.HTTP_400_BAD_REQUEST

    pending_withdrawal = _pending_withdrawal_total(wallet)
    available = _quantize_money((wallet.balance or Decimal("0")) - pending_withdrawal)
    if amount > available:
        return {
            "message": "Insufficient withdrawable balance.",
            "available_balance": float(max(available, Decimal("0"))),
        }, status.HTTP_400_BAD_REQUEST

    phone_raw = str(coalesce(payload, "phone_number", "phoneNumber", "mobile_number", "mobileNumber") or "").strip()
    phone_digits = "".join(ch for ch in phone_raw if ch.isdigit())
    if len(phone_digits) > 10 and phone_digits.startswith("977"):
        phone_digits = phone_digits[-10:]

    if not phone_digits:
        return {"message": "Phone number is required."}, status.HTTP_400_BAD_REQUEST
    if len(phone_digits) != 10 or not phone_digits.startswith("9"):
        return {"message": "Enter a valid Nepali phone number."}, status.HTTP_400_BAD_REQUEST

    note = str(coalesce(payload, "note", "description", "remark") or "").strip() or None
    otp_value = f"{random.randint(100000, 999999)}"
    otp_record = OTPVerification.objects.create(email=vendor.email, otp=otp_value)

    verification_metadata = dict(payout_profile.verification_metadata or {})
    verification_metadata["pending_withdrawal_request"] = {
        "amount": str(_quantize_money(amount)),
        "phone": phone_digits,
        "note": note,
        "requested_at": timezone.now().isoformat(),
    }
    payout_profile.verification_metadata = verification_metadata
    payout_profile.save(update_fields=["verification_metadata", "updated_at"])

    sent = _send_notification_email(
        subject="Vendor withdrawal OTP",
        message=(
            "Use this OTP to complete your withdrawal request.\n\n"
            f"OTP: {otp_value}\n"
            f"Amount: NPR {float(_quantize_money(amount)):.2f}\n"
            f"Phone: {phone_digits}\n\n"
            f"This OTP is valid for {EMAIL_OTP_TTL_MINUTES} minutes."
        ),
        recipient_email=vendor.email,
    )
    if not sent:
        otp_record.delete()
        verification_metadata.pop("pending_withdrawal_request", None)
        payout_profile.verification_metadata = verification_metadata
        payout_profile.save(update_fields=["verification_metadata", "updated_at"])
        return {"message": "Failed to send withdrawal OTP."}, status.HTTP_500_INTERNAL_SERVER_ERROR

    if bool(getattr(settings, "DEBUG", False)):
        print(f"DEBUG WITHDRAW OTP for {vendor.email}: {otp_value}")

    return {
        "message": "OTP sent to your email. Enter OTP to complete payment.",
        "requires_otp": True,
        "otp_ttl_minutes": EMAIL_OTP_TTL_MINUTES,
    }, status.HTTP_200_OK


def update_vendor_payout_profile(request: Any) -> tuple[dict[str, Any], int]:
    """Create or update a vendor payout destination and schedule policy."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    profile = _get_or_create_vendor_payout_profile(vendor)
    destination_type = str(coalesce(payload, "destination_type", "destinationType") or profile.destination_type or "").strip().upper()
    if destination_type not in dict(VendorPayoutProfile.DESTINATION_CHOICES):
        destination_type = profile.destination_type or VendorPayoutProfile.DESTINATION_BANK

    schedule = str(coalesce(payload, "payout_schedule", "payoutSchedule") or profile.payout_schedule or "").strip().upper()
    if schedule not in dict(VendorPayoutProfile.SCHEDULE_CHOICES):
        schedule = profile.payout_schedule or VENDOR_PAYOUT_DEFAULT_SCHEDULE

    payout_schedule_days = coalesce(payload, "payout_schedule_days", "payoutScheduleDays")
    if payout_schedule_days is None:
        payout_schedule_days = profile.payout_schedule_days or [VENDOR_PAYOUT_DEFAULT_SCHEDULE_DAY]
    payout_schedule_days = _normalize_schedule_day_values(payout_schedule_days)
    if not payout_schedule_days:
        payout_schedule_days = [VENDOR_PAYOUT_DEFAULT_SCHEDULE_DAY]

    minimum_amount = _parse_price_amount(coalesce(payload, "minimum_withdrawal_amount", "minimumWithdrawalAmount"))
    if minimum_amount is None or minimum_amount <= Decimal("0"):
        minimum_amount = profile.minimum_withdrawal_amount or VENDOR_PAYOUT_DEFAULT_MINIMUM_WITHDRAWAL

    payout_time_raw = coalesce(payload, "payout_schedule_time", "payoutScheduleTime")
    payout_time = parse_time(payout_time_raw) if payout_time_raw else profile.payout_schedule_time

    profile.destination_type = destination_type
    profile.destination_name = str(coalesce(payload, "destination_name", "destinationName") or "").strip() or None
    profile.destination_reference = str(coalesce(payload, "destination_reference", "destinationReference", "account_number", "accountNumber", "upi_id", "upiId", "mobile_number", "mobileNumber") or "").strip() or None
    profile.account_holder_name = str(coalesce(payload, "account_holder_name", "accountHolderName") or "").strip() or None
    profile.bank_name = str(coalesce(payload, "bank_name", "bankName") or "").strip() or None
    profile.branch_name = str(coalesce(payload, "branch_name", "branchName") or "").strip() or None
    profile.minimum_withdrawal_amount = _quantize_money(minimum_amount)
    profile.payout_schedule = schedule
    profile.payout_schedule_days = payout_schedule_days
    profile.payout_schedule_time = payout_time or profile.payout_schedule_time or VENDOR_PAYOUT_DEFAULT_SCHEDULE_TIME
    profile.failed_retry_limit = max(int(coalesce(payload, "failed_retry_limit", "failedRetryLimit") or profile.failed_retry_limit or 3), 1)
    profile.retry_backoff_minutes = max(int(coalesce(payload, "retry_backoff_minutes", "retryBackoffMinutes") or profile.retry_backoff_minutes or 60), 1)
    profile.is_destination_verified = False
    profile.destination_verified_at = None
    profile.verification_metadata = {
        **(profile.verification_metadata if isinstance(profile.verification_metadata, dict) else {}),
        "updated_at": timezone.now().isoformat(),
        "updated_by_vendor_id": vendor.id,
    }
    profile.save()

    return {
        "message": "Payout destination saved. Verify the destination using the OTP sent to your email.",
        "payout_profile": _serialize_vendor_payout_profile(profile),
        "payout_policy": _vendor_payout_policy_payload(profile),
    }, status.HTTP_200_OK


def request_vendor_payout_destination_verification(request: Any) -> tuple[dict[str, Any], int]:
    """Send an OTP to verify the vendor payout destination."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    profile = _get_or_create_vendor_payout_profile(vendor)
    if not profile.destination_reference:
        return {"message": "Save your payout destination before requesting verification."}, status.HTTP_400_BAD_REQUEST

    otp = f"{random.randint(100000, 999999)}"
    record = OTPVerification.objects.create(email=vendor.email, otp=otp)
    subject = "Verify your payout destination"
    message = (
        "Use this OTP to verify your vendor payout destination:\n\n"
        f"{otp}\n\n"
        "If you did not request this, ignore this email."
    )
    sent = _send_notification_email(
        subject=subject,
        message=message,
        recipient_email=vendor.email,
    )
    if not sent:
        record.delete()
        return {"message": "Failed to send verification OTP."}, status.HTTP_500_INTERNAL_SERVER_ERROR

    profile.verification_requested_at = timezone.now()
    profile.save(update_fields=["verification_requested_at", "updated_at"])
    if bool(getattr(settings, "DEBUG", False)):
        print(f"DEBUG PAYOUT OTP for {vendor.email}: {otp}")

    return {
        "message": "Verification OTP sent to vendor email.",
        "payout_profile": _serialize_vendor_payout_profile(profile),
    }, status.HTTP_200_OK


def verify_vendor_payout_destination(request: Any) -> tuple[dict[str, Any], int]:
    """Verify the payout destination OTP and enable withdrawals."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    profile = _get_or_create_vendor_payout_profile(vendor)
    otp = str(coalesce(get_payload(request), "otp") or "").strip()
    if not otp:
        return {"message": "OTP is required."}, status.HTTP_400_BAD_REQUEST

    cutoff = timezone.now() - timedelta(minutes=10)
    record = OTPVerification.objects.filter(
        email__iexact=vendor.email,
        otp=otp,
        created_at__gte=cutoff,
    ).order_by("-created_at").first()
    if not record:
        return {"message": "Invalid or expired OTP."}, status.HTTP_400_BAD_REQUEST

    record.is_verified = True
    record.save(update_fields=["is_verified"])
    profile.is_destination_verified = True
    profile.destination_verified_at = timezone.now()
    profile.verification_metadata = {
        **(profile.verification_metadata if isinstance(profile.verification_metadata, dict) else {}),
        "verified_at": timezone.now().isoformat(),
        "verified_by_email": vendor.email,
    }
    profile.save(update_fields=["is_destination_verified", "destination_verified_at", "verification_metadata", "updated_at"])

    return {
        "message": "Payout destination verified successfully.",
        "payout_profile": _serialize_vendor_payout_profile(profile),
    }, status.HTTP_200_OK


def retry_failed_withdrawal_settlement(request: Any, withdrawal_txn: Transaction) -> tuple[dict[str, Any], int]:
    """Retry a failed withdrawal settlement by requeueing the background job."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN
    if withdrawal_txn.transaction_type != Transaction.TYPE_WITHDRAWAL_REQUEST:
        return {"message": "Transaction is not a withdrawal request."}, status.HTTP_400_BAD_REQUEST

    ledger = (
        WithdrawalLedger.objects.select_for_update()
        .filter(withdrawal_transaction=withdrawal_txn)
        .order_by("-created_at", "-id")
        .first()
    )
    if not ledger:
        return {"message": "Withdrawal ledger not found."}, status.HTTP_404_NOT_FOUND
    if ledger.status == WithdrawalLedger.STATUS_PAID:
        return {"message": "Withdrawal already settled."}, status.HTTP_400_BAD_REQUEST

    retry_count = int((ledger.decision_metadata or {}).get("retry_count") or 0) + 1
    ledger.status = WithdrawalLedger.STATUS_APPROVED
    ledger.decision_metadata = {
        **(ledger.decision_metadata if isinstance(ledger.decision_metadata, dict) else {}),
        "action": "RETRY",
        "retry_count": retry_count,
        "retry_requested_at": timezone.now().isoformat(),
        "retry_requested_by": getattr(resolve_admin(request), "id", None),
    }
    ledger.save(update_fields=["status", "decision_metadata", "updated_at"])

    enqueue_withdrawal_settlement_job(
        withdrawal_transaction_id=withdrawal_txn.id,
        payout_reference=ledger.payout_reference or f"WSET-{withdrawal_txn.transaction_uuid or withdrawal_txn.id}",
        metadata={"source": "admin_retry", "retry_count": retry_count},
    )

    return {
        "message": "Withdrawal settlement retry queued.",
        "transaction_id": withdrawal_txn.id,
        "retry_count": retry_count,
        "status": ledger.status,
    }, status.HTTP_200_OK


def list_vendor_wallet_transactions(request: Any) -> tuple[dict[str, Any], int]:
    """List authenticated vendor wallet transactions."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    wallet = _wallet_for_vendor(vendor)
    transactions = wallet.transactions.all().order_by("-created_at", "-id")
    tx_type = str(coalesce(request.query_params, "type", "transaction_type") or "").strip().upper()
    tx_status = str(coalesce(request.query_params, "status") or "").strip().upper()
    if tx_type:
        transactions = transactions.filter(transaction_type=tx_type)
    if tx_status:
        transactions = transactions.filter(status=tx_status)

    payload = []
    for txn in transactions[:200]:
        ledger = (
            WithdrawalLedger.objects.filter(withdrawal_transaction=txn).order_by("-created_at", "-id").first()
            if txn.transaction_type == Transaction.TYPE_WITHDRAWAL_REQUEST
            else None
        )
        payload.append(
            {
                "id": txn.id,
                "type": txn.transaction_type,
                "status": txn.status,
                "amount": float(_quantize_money(txn.amount or Decimal("0"))),
                "gross_amount": float(_quantize_money(txn.gross_amount or Decimal("0"))),
                "commission_amount": float(_quantize_money(txn.commission_amount or Decimal("0"))),
                "booking_id": txn.booking_id,
                "vendor_id": txn.vendor_id,
                "description": txn.description,
                "payout_status": ledger.status if ledger else None,
                "payout_reference": ledger.payout_reference if ledger else None,
                "retry_count": int((ledger.decision_metadata or {}).get("retry_count") or 0) if ledger else 0,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
            }
        )

    withdrawal_history = [
        {
            "id": entry.id,
            "transaction_id": entry.withdrawal_transaction_id,
            "status": entry.status,
            "amount": float(_quantize_money(entry.amount or Decimal("0"))),
            "payout_reference": entry.payout_reference,
            "decision_reason": entry.decision_reason,
            "retry_count": int((entry.decision_metadata or {}).get("retry_count") or 0),
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
        for entry in WithdrawalLedger.objects.filter(vendor=vendor).order_by("-created_at", "-id")[:100]
    ]

    return {"transactions": payload, "withdrawal_history": withdrawal_history}, status.HTTP_200_OK


def _parse_date_range_from_request(request: Any) -> tuple[Optional[datetime], Optional[datetime], str]:
    """Resolve date range using preset or explicit start/end query params."""
    params = request.query_params
    preset = str(coalesce(params, "range", "preset", "period") or "").strip().lower()
    now = timezone.now()

    if preset in {"last_7_days", "7d", "weekly", "week"}:
        return now - timedelta(days=7), now, "last_7_days"
    if preset in {"last_30_days", "30d", "monthly", "month"}:
        return now - timedelta(days=30), now, "last_30_days"
    if preset in {"yearly", "year", "1y", "last_365_days"}:
        return now - timedelta(days=365), now, "yearly"

    start_raw = coalesce(params, "start_date", "startDate", "from")
    end_raw = coalesce(params, "end_date", "endDate", "to")

    start_date = parse_date(start_raw) if start_raw else None
    end_date = parse_date(end_raw) if end_raw else None

    start_dt = ensure_utc_datetime(datetime.combine(start_date, time_cls.min)) if start_date else None
    end_dt = ensure_utc_datetime(datetime.combine(end_date, time_cls.max)) if end_date else None
    return start_dt, end_dt, "custom"


def _apply_datetime_window(queryset: Any, field_name: str, start_dt: Optional[datetime], end_dt: Optional[datetime]) -> Any:
    if start_dt:
        queryset = queryset.filter(**{f"{field_name}__gte": start_dt})
    if end_dt:
        queryset = queryset.filter(**{f"{field_name}__lte": end_dt})
    return queryset


def _chart_points_from_rows(rows: Iterable[dict[str, Any]], *, key_name: str, value_name: str = "value") -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        label = str(row.get(key_name) or "")
        value = float(_quantize_money(row.get(value_name) or Decimal("0")))
        points.append({"label": label, "value": value})
    return points


def _vendor_successful_booking_queryset(vendor: Vendor) -> Any:
    """Bookings that have at least one successful payment for a vendor."""
    return (
        Booking.objects.filter(
            showtime__screen__vendor=vendor,
            payments__payment_status__iexact=PAYMENT_STATUS_SUCCESS,
        )
        .distinct()
        .select_related("showtime", "showtime__movie", "showtime__screen")
    )


def get_vendor_revenue_analytics(request: Any) -> tuple[dict[str, Any], int]:
    """Return vendor earnings analytics with chart-ready aggregates."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    period = str(coalesce(request.query_params, "group", "group_by", "interval") or "daily").strip().lower()
    if period not in {"daily", "weekly", "monthly"}:
        period = "daily"

    start_dt, end_dt, range_key = _parse_date_range_from_request(request)
    cache_key = _dashboard_cache_key("vendor-revenue", vendor.id, period, range_key, start_dt, end_dt)
    cached_response = cache.get(cache_key)
    if cached_response is not None:
        return cached_response
    bookings = _apply_datetime_window(_vendor_successful_booking_queryset(vendor), "booking_date", start_dt, end_dt)
    all_bookings = _apply_datetime_window(
        Booking.objects.filter(showtime__screen__vendor=vendor)
        .select_related("showtime", "showtime__movie", "showtime__screen")
        .distinct(),
        "booking_date",
        start_dt,
        end_dt,
    )

    totals = bookings.aggregate(
        total_earnings=Sum("vendor_earning"),
        total_commission=Sum("admin_commission"),
        total_revenue=Sum("total_amount"),
    )
    total_earnings = _quantize_money(totals.get("total_earnings") or Decimal("0"))
    total_commission = _quantize_money(totals.get("total_commission") or Decimal("0"))
    total_revenue = _quantize_money(totals.get("total_revenue") or Decimal("0"))
    tickets_sold = BookingSeat.objects.filter(booking__in=bookings).count()
    total_booking_rows = all_bookings.count()
    cancelled_booking_rows = all_bookings.filter(booking_status__iexact=BOOKING_STATUS_CANCELLED).count()
    refund_booking_rows = all_bookings.filter(
        Q(payments__refunds__refund_status__iexact=Refund.Status.COMPLETED)
        | Q(payments__payment_status__iexact=PAYMENT_STATUS_REFUNDED)
        | Q(payments__payment_status__iexact=PAYMENT_STATUS_PARTIALLY_REFUNDED)
    ).distinct().count()
    refund_total_amount = _quantize_money(
        all_bookings.filter(payments__refunds__refund_status__iexact=Refund.Status.COMPLETED).aggregate(
            total=Sum("payments__refunds__refund_amount")
        ).get("total") or Decimal("0")
    )
    wallet = _wallet_for_vendor(vendor)
    pending_payout_amount = _pending_withdrawal_total(wallet)

    by_show_rows = (
        bookings.values("showtime__movie__title", "showtime__id")
        .annotate(
            bookings_count=Count("id"),
            tickets=Count("booking_seats__id"),
            gross=Sum("total_amount"),
            vendor_earnings=Sum("vendor_earning"),
            admin_commission=Sum("admin_commission"),
        )
        .order_by("-vendor_earnings", "-bookings_count")
    )
    earnings_per_show = [
        {
            "showtime_id": row.get("showtime__id"),
            "show_title": row.get("showtime__movie__title") or "Unknown",
            "bookings": int(row.get("bookings_count") or 0),
            "tickets_sold": int(row.get("tickets") or 0),
            "gross_revenue": float(_quantize_money(row.get("gross") or Decimal("0"))),
            "vendor_earning": float(_quantize_money(row.get("vendor_earnings") or Decimal("0"))),
            "admin_commission": float(_quantize_money(row.get("admin_commission") or Decimal("0"))),
        }
        for row in by_show_rows
    ]

    if period == "monthly":
        trend_rows = (
            bookings.annotate(period_key=TruncMonth("booking_date"))
            .values("period_key")
            .annotate(value=Sum("vendor_earning"))
            .order_by("period_key")
        )
        trend_points = [
            {
                "label": row["period_key"].strftime("%Y-%m") if row.get("period_key") else "",
                "value": float(_quantize_money(row.get("value") or Decimal("0"))),
            }
            for row in trend_rows
        ]
    elif period == "weekly":
        weekly_raw = (
            bookings.annotate(period_key=TruncDate("booking_date"))
            .values("period_key")
            .annotate(value=Sum("vendor_earning"))
            .order_by("period_key")
        )
        buckets: dict[str, Decimal] = {}
        for row in weekly_raw:
            day_value = row.get("period_key")
            if not day_value:
                continue
            year, week, _ = day_value.isocalendar()
            label = f"{year}-W{week:02d}"
            buckets[label] = _quantize_money(buckets.get(label, Decimal("0")) + (row.get("value") or Decimal("0")))
        trend_points = [{"label": label, "value": float(amount)} for label, amount in sorted(buckets.items())]
    else:
        trend_rows = (
            bookings.annotate(period_key=TruncDate("booking_date"))
            .values("period_key")
            .annotate(value=Sum("vendor_earning"))
            .order_by("period_key")
        )
        trend_points = [
            {
                "label": row["period_key"].isoformat() if row.get("period_key") else "",
                "value": float(_quantize_money(row.get("value") or Decimal("0"))),
            }
            for row in trend_rows
        ]

    occupancy_rows = list(
        bookings.values(
            "showtime__id",
            "showtime__start_time",
            "showtime__movie__title",
            "showtime__screen__screen_number",
            "showtime__screen_id",
        ).annotate(
            tickets_sold=Count("booking_seats__id"),
        ).order_by("showtime__start_time")
    )
    screen_ids = [row.get("showtime__screen_id") for row in occupancy_rows if row.get("showtime__screen_id")]
    capacity_rows = Seat.objects.filter(screen_id__in=screen_ids).values("screen_id").annotate(total=Count("id"))
    screen_capacity_map = {row["screen_id"]: int(row["total"] or 0) for row in capacity_rows}
    occupancy_by_slot = []
    for row in occupancy_rows:
        screen_id = row.get("showtime__screen_id")
        capacity = int(screen_capacity_map.get(screen_id) or 0)
        sold = int(row.get("tickets_sold") or 0)
        occupancy_percent = (sold / capacity * 100) if capacity > 0 else 0
        start_time = row.get("showtime__start_time")
        occupancy_by_slot.append(
            {
                "showtime_id": row.get("showtime__id"),
                "movie_title": row.get("showtime__movie__title") or "Unknown",
                "slot_label": start_time.strftime("%Y-%m-%d %H:%M") if start_time else "",
                "hall": row.get("showtime__screen__screen_number") or "-",
                "capacity": capacity,
                "tickets_sold": sold,
                "occupancy_percent": round(occupancy_percent, 2),
            }
        )

    cancellation_rate = (cancelled_booking_rows / total_booking_rows * 100) if total_booking_rows > 0 else 0
    refund_rate = (refund_booking_rows / total_booking_rows * 100) if total_booking_rows > 0 else 0

    response = {
        "vendor_id": vendor.id,
        "range": range_key,
        "period": period,
        "summary": {
            "total_earnings": float(total_earnings),
            "total_commission": float(total_commission),
            "total_revenue": float(total_revenue),
            "total_tickets_sold": int(tickets_sold),
            "cancellation_rate": round(cancellation_rate, 2),
            "refund_rate": round(refund_rate, 2),
            "payout_pending": float(pending_payout_amount),
            "refund_total_amount": float(refund_total_amount),
        },
        "earnings_per_show": earnings_per_show,
        "occupancy_by_slot": occupancy_by_slot,
        "trend": trend_points,
        "chart": {
            "series": [{"name": "Vendor Earnings", "data": trend_points}],
            "xKey": "label",
            "yKey": "value",
        },
    }, status.HTTP_200_OK
    cache.set(cache_key, response, ANALYTICS_VENDOR_CACHE_TTL_SECONDS)
    return response


def list_vendor_revenue_transactions(request: Any) -> tuple[dict[str, Any], int]:
    """Return vendor-side earning and reversal transaction ledger."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    wallet = _wallet_for_vendor(vendor)
    start_dt, end_dt, _ = _parse_date_range_from_request(request)
    queryset = wallet.transactions.select_related("booking").all().order_by("-created_at", "-id")
    queryset = _apply_datetime_window(queryset, "created_at", start_dt, end_dt)

    items = []
    for tx in queryset[:500]:
        items.append(
            {
                "id": tx.id,
                "transaction_type": tx.transaction_type,
                "status": tx.status,
                "amount": float(_quantize_money(tx.amount or Decimal("0"))),
                "gross_amount": float(_quantize_money(tx.gross_amount or Decimal("0"))),
                "commission_amount": float(_quantize_money(tx.commission_amount or Decimal("0"))),
                "booking_id": tx.booking_id,
                "description": tx.description,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
        )
    return {"transactions": items}, status.HTTP_200_OK


def get_admin_revenue_config(request: Any) -> tuple[dict[str, Any], int]:
    """Return current platform commission config."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN
    config = _get_platform_revenue_config()
    return {
        "commission_percent": float(_quantize_money(config.commission_percent or Decimal("0"))),
        "is_active": bool(config.is_active),
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }, status.HTTP_200_OK


def update_admin_revenue_config(
    request: Any,
    payload_override: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], int]:
    """Update platform commission config from admin panel."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = payload_override or get_payload(request)
    commission_raw = coalesce(payload, "commission_percent", "commissionPercent", "platform_commission_percent")
    if commission_raw in (None, ""):
        return {"message": "commission_percent is required."}, status.HTTP_400_BAD_REQUEST

    try:
        commission = Decimal(str(commission_raw))
    except (TypeError, ValueError, InvalidOperation):
        return {"message": "commission_percent must be numeric."}, status.HTTP_400_BAD_REQUEST
    if commission < Decimal("0") or commission > Decimal("100"):
        return {"message": "commission_percent must be between 0 and 100."}, status.HTTP_400_BAD_REQUEST

    config = _get_platform_revenue_config()
    config.commission_percent = _quantize_money(commission)
    config.is_active = parse_bool(coalesce(payload, "is_active", "isActive"), default=True)
    config.updated_by = resolve_admin(request)
    config.save(update_fields=["commission_percent", "is_active", "updated_by", "updated_at"])

    return {
        "message": "Revenue configuration updated.",
        "commission_percent": float(config.commission_percent),
        "is_active": bool(config.is_active),
    }, status.HTTP_200_OK


def get_admin_revenue_analytics(request: Any) -> tuple[dict[str, Any], int]:
    """Return platform commission and revenue analytics for admin dashboard."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    period = str(coalesce(request.query_params, "group", "group_by", "interval") or "daily").strip().lower()
    if period not in {"daily", "weekly", "monthly"}:
        period = "daily"

    start_dt, end_dt, range_key = _parse_date_range_from_request(request)
    cache_key = _dashboard_cache_key("admin-revenue", period, range_key, start_dt, end_dt)
    cached_response = cache.get(cache_key)
    if cached_response is not None:
        return cached_response
    bookings = Booking.objects.filter(payments__payment_status__iexact=PAYMENT_STATUS_SUCCESS).distinct()
    bookings = _apply_datetime_window(bookings, "booking_date", start_dt, end_dt)

    admin_wallet = _admin_wallet()
    _recalculate_admin_wallet_snapshot(admin_wallet)
    top_vendors_rows = (
        bookings.values("showtime__screen__vendor_id", "showtime__screen__vendor__name")
        .annotate(
            vendor_revenue=Sum("total_amount"),
            vendor_earning=Sum("vendor_earning"),
            commission=Sum("admin_commission"),
            bookings_count=Count("id"),
        )
        .order_by("-vendor_revenue", "-bookings_count")[:10]
    )

    top_vendors = [
        {
            "vendor_id": row.get("showtime__screen__vendor_id"),
            "vendor_name": row.get("showtime__screen__vendor__name") or "Unknown",
            "platform_revenue": float(_quantize_money(row.get("vendor_revenue") or Decimal("0"))),
            "vendor_earning": float(_quantize_money(row.get("vendor_earning") or Decimal("0"))),
            "admin_commission": float(_quantize_money(row.get("commission") or Decimal("0"))),
            "bookings": int(row.get("bookings_count") or 0),
        }
        for row in top_vendors_rows
    ]

    if period == "monthly":
        trend_rows = (
            bookings.annotate(period_key=TruncMonth("booking_date"))
            .values("period_key")
            .annotate(
                revenue=Sum("total_amount"),
                commission=Sum("admin_commission"),
            )
            .order_by("period_key")
        )
        trend = [
            {
                "label": row["period_key"].strftime("%Y-%m") if row.get("period_key") else "",
                "platform_revenue": float(_quantize_money(row.get("revenue") or Decimal("0"))),
                "admin_commission": float(_quantize_money(row.get("commission") or Decimal("0"))),
            }
            for row in trend_rows
        ]
    else:
        trend_rows = (
            bookings.annotate(period_key=TruncDate("booking_date"))
            .values("period_key")
            .annotate(
                revenue=Sum("total_amount"),
                commission=Sum("admin_commission"),
            )
            .order_by("period_key")
        )
        if period == "weekly":
            weekly_buckets: dict[str, dict[str, Decimal]] = {}
            for row in trend_rows:
                day_value = row.get("period_key")
                if not day_value:
                    continue
                year, week, _ = day_value.isocalendar()
                label = f"{year}-W{week:02d}"
                bucket = weekly_buckets.setdefault(label, {"revenue": Decimal("0"), "commission": Decimal("0")})
                bucket["revenue"] = _quantize_money(bucket["revenue"] + (row.get("revenue") or Decimal("0")))
                bucket["commission"] = _quantize_money(bucket["commission"] + (row.get("commission") or Decimal("0")))
            trend = [
                {
                    "label": label,
                    "platform_revenue": float(values["revenue"]),
                    "admin_commission": float(values["commission"]),
                }
                for label, values in sorted(weekly_buckets.items())
            ]
        else:
            trend = [
                {
                    "label": row["period_key"].isoformat() if row.get("period_key") else "",
                    "platform_revenue": float(_quantize_money(row.get("revenue") or Decimal("0"))),
                    "admin_commission": float(_quantize_money(row.get("commission") or Decimal("0"))),
                }
                for row in trend_rows
            ]

    totals = bookings.aggregate(
        total_platform_revenue=Sum("total_amount"),
        total_commission=Sum("admin_commission"),
    )
    total_platform_revenue = _quantize_money(totals.get("total_platform_revenue") or Decimal("0"))
    total_commission = _quantize_money(totals.get("total_commission") or Decimal("0"))

    response = {
        "range": range_key,
        "period": period,
        "summary": {
            "total_commission_earned": float(total_commission),
            "platform_total_revenue": float(total_platform_revenue),
            "admin_wallet_balance": float(_quantize_money(admin_wallet.balance or Decimal("0"))),
            "total_commission_reversed": float(_quantize_money(admin_wallet.total_commission_reversed or Decimal("0"))),
        },
        "revenue_per_vendor": top_vendors,
        "top_performing_vendors": top_vendors,
        "trend": trend,
        "chart": {
            "series": [
                {"name": "Platform Revenue", "data": [{"label": p["label"], "value": p["platform_revenue"]} for p in trend]},
                {"name": "Admin Commission", "data": [{"label": p["label"], "value": p["admin_commission"]} for p in trend]},
            ],
            "xKey": "label",
            "yKey": "value",
        },
    }, status.HTTP_200_OK
    cache.set(cache_key, response, ANALYTICS_CACHE_TTL_SECONDS)
    return response


def list_admin_revenue_transactions(request: Any) -> tuple[dict[str, Any], int]:
    """Return admin commission transaction ledger."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    start_dt, end_dt, _ = _parse_date_range_from_request(request)
    queryset = AdminWalletTransaction.objects.select_related("vendor", "booking", "payment", "refund").all()
    queryset = _apply_datetime_window(queryset, "created_at", start_dt, end_dt).order_by("-created_at", "-id")

    tx_type = str(coalesce(request.query_params, "type", "transaction_type") or "").strip().upper()
    if tx_type:
        queryset = queryset.filter(transaction_type=tx_type)

    items = []
    for tx in queryset[:500]:
        items.append(
            {
                "id": tx.id,
                "transaction_type": tx.transaction_type,
                "status": tx.status,
                "amount": float(_quantize_money(tx.amount or Decimal("0"))),
                "gross_amount": float(_quantize_money(tx.gross_amount or Decimal("0"))),
                "commission_percent": float(_quantize_money(tx.commission_percent or Decimal("0"))),
                "vendor_id": tx.vendor_id,
                "vendor_name": tx.vendor.name if tx.vendor else None,
                "booking_id": tx.booking_id,
                "payment_id": tx.payment_id,
                "refund_id": tx.refund_id,
                "description": tx.description,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
        )
    return {"transactions": items}, status.HTTP_200_OK


def get_vendor_revenue_report(request: Any) -> tuple[dict[str, Any], int]:
    """Return report-oriented vendor revenue data by show and date range."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    start_dt, end_dt, range_key = _parse_date_range_from_request(request)
    bookings = _apply_datetime_window(_vendor_successful_booking_queryset(vendor), "booking_date", start_dt, end_dt)

    show_report = (
        bookings.values("showtime__id", "showtime__movie__title", "showtime__show_date")
        .annotate(
            bookings_count=Count("id"),
            tickets=Count("booking_seats__id"),
            gross=Sum("total_amount"),
            vendor_earning=Sum("vendor_earning"),
            admin_commission=Sum("admin_commission"),
        )
        .order_by("-showtime__show_date", "-gross")
    )

    report = [
        {
            "showtime_id": row.get("showtime__id"),
            "show_title": row.get("showtime__movie__title") or "Unknown",
            "show_date": row.get("showtime__show_date").isoformat() if row.get("showtime__show_date") else None,
            "bookings": int(row.get("bookings_count") or 0),
            "tickets_sold": int(row.get("tickets") or 0),
            "gross_revenue": float(_quantize_money(row.get("gross") or Decimal("0"))),
            "vendor_earning": float(_quantize_money(row.get("vendor_earning") or Decimal("0"))),
            "admin_commission": float(_quantize_money(row.get("admin_commission") or Decimal("0"))),
        }
        for row in show_report
    ]

    return {"range": range_key, "show_report": report}, status.HTTP_200_OK


def get_admin_revenue_report(request: Any) -> tuple[dict[str, Any], int]:
    """Return admin report grouped by vendor and show with date-range filter."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    start_dt, end_dt, range_key = _parse_date_range_from_request(request)
    bookings = Booking.objects.filter(payments__payment_status__iexact=PAYMENT_STATUS_SUCCESS).distinct()
    bookings = _apply_datetime_window(bookings, "booking_date", start_dt, end_dt)

    vendor_report_rows = (
        bookings.values("showtime__screen__vendor_id", "showtime__screen__vendor__name")
        .annotate(
            bookings_count=Count("id"),
            gross=Sum("total_amount"),
            vendor_earning=Sum("vendor_earning"),
            admin_commission=Sum("admin_commission"),
        )
        .order_by("-gross", "-bookings_count")
    )
    vendor_report = [
        {
            "vendor_id": row.get("showtime__screen__vendor_id"),
            "vendor_name": row.get("showtime__screen__vendor__name") or "Unknown",
            "bookings": int(row.get("bookings_count") or 0),
            "platform_revenue": float(_quantize_money(row.get("gross") or Decimal("0"))),
            "vendor_earning": float(_quantize_money(row.get("vendor_earning") or Decimal("0"))),
            "admin_commission": float(_quantize_money(row.get("admin_commission") or Decimal("0"))),
        }
        for row in vendor_report_rows
    ]

    show_report_rows = (
        bookings.values("showtime__id", "showtime__movie__title")
        .annotate(
            bookings_count=Count("id"),
            gross=Sum("total_amount"),
            vendor_earning=Sum("vendor_earning"),
            admin_commission=Sum("admin_commission"),
        )
        .order_by("-gross", "-bookings_count")
    )
    show_report = [
        {
            "showtime_id": row.get("showtime__id"),
            "show_title": row.get("showtime__movie__title") or "Unknown",
            "bookings": int(row.get("bookings_count") or 0),
            "platform_revenue": float(_quantize_money(row.get("gross") or Decimal("0"))),
            "vendor_earning": float(_quantize_money(row.get("vendor_earning") or Decimal("0"))),
            "admin_commission": float(_quantize_money(row.get("admin_commission") or Decimal("0"))),
        }
        for row in show_report_rows
    ]

    return {
        "range": range_key,
        "vendor_report": vendor_report,
        "show_report": show_report,
    }, status.HTTP_200_OK


def list_admin_withdrawal_requests(request: Any) -> tuple[dict[str, Any], int]:
    """List withdrawal request transactions for admin review."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    queryset = Transaction.objects.filter(
        transaction_type=Transaction.TYPE_WITHDRAWAL_REQUEST,
    ).select_related("vendor", "wallet").order_by("-created_at", "-id")

    status_filter = str(coalesce(request.query_params, "status") or "").strip().upper()
    if status_filter in {Transaction.STATUS_PENDING, Transaction.STATUS_COMPLETED, Transaction.STATUS_REJECTED}:
        queryset = queryset.filter(status=status_filter)

    items = []
    for txn in queryset[:500]:
        items.append(
            {
                "id": txn.id,
                "vendor_id": txn.vendor_id,
                "vendor_name": txn.vendor.name if txn.vendor else None,
                "status": txn.status,
                "amount": float(_quantize_money(txn.amount or Decimal("0"))),
                "description": txn.description,
                "created_at": txn.created_at.isoformat() if txn.created_at else None,
            }
        )
    return {"withdrawals": items}, status.HTTP_200_OK


def _process_admin_withdrawal(
    request: Any,
    withdrawal_txn: Transaction,
    *,
    approve: bool,
) -> tuple[dict[str, Any], int]:
    """Approve or reject a pending vendor withdrawal request."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN
    if withdrawal_txn.transaction_type != Transaction.TYPE_WITHDRAWAL_REQUEST:
        return {"message": "Transaction is not a withdrawal request."}, status.HTTP_400_BAD_REQUEST

    with transaction.atomic():
        locked = (
            Transaction.objects.select_for_update()
            .select_related("wallet", "vendor")
            .filter(id=withdrawal_txn.id)
            .first()
        )
        if not locked:
            return {"message": "Withdrawal request not found."}, status.HTTP_404_NOT_FOUND
        if locked.status != Transaction.STATUS_PENDING:
            return {
                "message": "Withdrawal request already processed.",
                "status": locked.status,
            }, status.HTTP_400_BAD_REQUEST

        wallet = Wallet.objects.select_for_update().filter(id=locked.wallet_id).first()
        if not wallet:
            return {"message": "Wallet not found for withdrawal request."}, status.HTTP_404_NOT_FOUND

        _recalculate_vendor_wallet_snapshot(wallet)

        payload = get_payload(request)
        note = str(coalesce(payload, "reason", "note", "description") or "").strip()
        amount = _quantize_money(locked.amount or Decimal("0"))

        if approve:
            pending_total = _pending_withdrawal_total(wallet)
            available = _quantize_money((wallet.balance or Decimal("0")) - pending_total + amount)
            if amount > available:
                return {"message": "Insufficient balance to approve this withdrawal."}, status.HTTP_400_BAD_REQUEST

            locked.status = Transaction.STATUS_COMPLETED
            if note:
                locked.description = f"{locked.description or 'Withdrawal request'} | Approved: {note}"
            admin_actor = resolve_admin(request)
            locked.decision_metadata = {
                "action": "APPROVE",
                "approved_by": getattr(admin_actor, "id", None),
                "approved_at": timezone.now().isoformat(),
                "reason": note,
            }
            locked.decision_reason = note or None
            locked.decision_by = admin_actor
            locked.decision_at = timezone.now()
            locked.save(
                update_fields=[
                    "status",
                    "description",
                    "decision_metadata",
                    "decision_reason",
                    "decision_by",
                    "decision_at",
                ]
            )

            Transaction.objects.create(
                wallet=wallet,
                vendor=locked.vendor,
                transaction_type=Transaction.TYPE_WITHDRAWAL_APPROVED,
                amount=amount,
                commission_amount=Decimal("0.00"),
                gross_amount=amount,
                status=Transaction.STATUS_COMPLETED,
                description=f"Withdrawal approved for request #{locked.id}",
            )
            WithdrawalLedger.objects.create(
                vendor=locked.vendor,
                wallet=wallet,
                withdrawal_transaction=locked,
                status=WithdrawalLedger.STATUS_APPROVED,
                amount=amount,
                gross_amount=amount,
                metadata={"source": "admin_withdrawal_approval"},
                decision_metadata={"action": "APPROVE", "reason": note},
                decision_reason=note or None,
                decision_by=admin_actor,
                decision_at=timezone.now(),
            )
            _recalculate_vendor_wallet_snapshot(wallet)
            enqueue_withdrawal_settlement_job(
                withdrawal_transaction_id=locked.id,
                payout_reference=f"WSET-{locked.transaction_uuid or locked.id}",
                metadata={"source": "admin_approval"},
            )

            return {
                "message": "Withdrawal approved.",
                "transaction_id": locked.id,
                "status": locked.status,
                "amount": float(amount),
            }, status.HTTP_200_OK

        locked.status = Transaction.STATUS_REJECTED
        if note:
            locked.description = f"{locked.description or 'Withdrawal request'} | Rejected: {note}"
        admin_actor = resolve_admin(request)
        locked.decision_metadata = {
            "action": "REJECT",
            "rejected_by": getattr(admin_actor, "id", None),
            "rejected_at": timezone.now().isoformat(),
            "reason": note,
        }
        locked.decision_reason = note or None
        locked.decision_by = admin_actor
        locked.decision_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "description",
                "decision_metadata",
                "decision_reason",
                "decision_by",
                "decision_at",
            ]
        )
        Transaction.objects.create(
            wallet=wallet,
            vendor=locked.vendor,
            transaction_type=Transaction.TYPE_WITHDRAWAL_REJECTED,
            amount=amount,
            commission_amount=Decimal("0.00"),
            gross_amount=amount,
            status=Transaction.STATUS_REJECTED,
            description=f"Withdrawal rejected for request #{locked.id}",
        )
        WithdrawalLedger.objects.create(
            vendor=locked.vendor,
            wallet=wallet,
            withdrawal_transaction=locked,
            status=WithdrawalLedger.STATUS_REJECTED,
            amount=amount,
            gross_amount=amount,
            metadata={"source": "admin_withdrawal_rejection"},
            decision_metadata={"action": "REJECT", "reason": note},
            decision_reason=note or None,
            decision_by=admin_actor,
            decision_at=timezone.now(),
        )
        return {
            "message": "Withdrawal rejected.",
            "transaction_id": locked.id,
            "status": locked.status,
            "amount": float(amount),
        }, status.HTTP_200_OK


def approve_admin_withdrawal_request(request: Any, withdrawal_txn: Transaction) -> tuple[dict[str, Any], int]:
    return _process_admin_withdrawal(request, withdrawal_txn, approve=True)


def reject_admin_withdrawal_request(request: Any, withdrawal_txn: Transaction) -> tuple[dict[str, Any], int]:
    return _process_admin_withdrawal(request, withdrawal_txn, approve=False)


def _normalize_coupon_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _serialize_coupon(coupon: Coupon) -> dict[str, Any]:
    return {
        "id": coupon.id,
        "code": coupon.code,
        "discount_type": coupon.discount_type,
        "discount_value": float(_quantize_money(coupon.discount_value or Decimal("0"))),
        "min_booking_amount": float(
            _quantize_money(coupon.min_booking_amount or Decimal("0"))
        ),
        "expiry_date": coupon.expiry_date.isoformat() if coupon.expiry_date else None,
        "usage_limit": coupon.usage_limit,
        "usage_count": coupon.usage_count,
        "is_active": bool(coupon.is_active),
        "created_at": coupon.created_at.isoformat() if coupon.created_at else None,
    }


def _serialize_vendor_promo_code(promo: VendorPromoCode) -> dict[str, Any]:
    return {
        "id": promo.id,
        "vendor_id": promo.vendor_id,
        "code": promo.code,
        "title": promo.title,
        "description": promo.description,
        "discount_type": promo.discount_type,
        "discount_value": float(_quantize_money(promo.discount_value or Decimal("0"))),
        "min_booking_amount": float(_quantize_money(promo.min_booking_amount or Decimal("0"))),
        "max_discount_amount": float(_quantize_money(promo.max_discount_amount or Decimal("0")))
        if promo.max_discount_amount is not None
        else None,
        "usage_limit": promo.usage_limit,
        "usage_count": promo.usage_count,
        "per_user_limit": promo.per_user_limit,
        "seat_category_scope": promo.seat_category_scope,
        "requires_student": bool(promo.requires_student),
        "allowed_weekdays": _parse_allowed_weekdays(promo.allowed_weekdays),
        "valid_from": promo.valid_from.isoformat() if promo.valid_from else None,
        "valid_until": promo.valid_until.isoformat() if promo.valid_until else None,
        "is_flash_sale": bool(promo.is_flash_sale),
        "is_active": bool(promo.is_active),
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
    }


def _serialize_vendor_campaign(campaign: VendorCampaign) -> dict[str, Any]:
    return {
        "id": campaign.id,
        "vendor_id": campaign.vendor_id,
        "name": campaign.name,
        "message_template": campaign.message_template,
        "delivery_channel": campaign.delivery_channel,
        "status": campaign.status,
        "target_movie_id": campaign.target_movie_id,
        "recommended_movie_id": campaign.recommended_movie_id,
        "promo_code_id": campaign.promo_code_id,
        "promo_code": campaign.promo_code.code if campaign.promo_code_id and campaign.promo_code else None,
        "include_past_attendees_only": bool(campaign.include_past_attendees_only),
        "min_days_since_booking": int(campaign.min_days_since_booking or 0),
        "scheduled_at": campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        "last_run_at": campaign.last_run_at.isoformat() if campaign.last_run_at else None,
        "sent_count": int(campaign.sent_count or 0),
        "failed_count": int(campaign.failed_count or 0),
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
    }


def _serialize_vendor_campaign_dispatch(dispatch: VendorCampaignDispatch) -> dict[str, Any]:
    return {
        "id": dispatch.id,
        "campaign_id": dispatch.campaign_id,
        "user_id": dispatch.user_id,
        "channel": dispatch.channel,
        "contact": dispatch.contact,
        "status": dispatch.status,
        "error_message": dispatch.error_message,
        "sent_at": dispatch.sent_at.isoformat() if dispatch.sent_at else None,
    }


def _parse_allowed_weekdays(value: Any) -> list[str]:
    text = str(value or "").strip().upper()
    if not text:
        return []
    output = []
    for token in re.split(r"[\s,;|]+", text):
        token = token.strip().upper()
        if token in WEEKDAY_CODES and token not in output:
            output.append(token)
    return output


def _parse_coupon_expiry(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed_datetime = parse_datetime_utc(text)
    if parsed_datetime:
        return parsed_datetime

    parsed_date = parse_date(text)
    if not parsed_date:
        return None
    return ensure_utc_datetime(datetime.combine(parsed_date, time_cls.max))


def _parse_datetime_value(value: Any) -> Optional[datetime]:
    return parse_datetime_utc(value)


def _resolve_vendor_id_from_discount_context(context: Optional[dict[str, Any]]) -> Optional[int]:
    if not isinstance(context, dict):
        return None

    vendor_id = _coerce_int(coalesce(context, "vendor_id", "vendorId", "cinema_id", "cinemaId"))
    if vendor_id:
        return vendor_id

    show_id = _coerce_int(coalesce(context, "show_id", "showId"))
    if show_id:
        show = Show.objects.filter(id=show_id).only("vendor_id").first()
        if show:
            return show.vendor_id

    showtime_id = _coerce_int(coalesce(context, "showtime_id", "showtimeId"))
    if showtime_id:
        showtime = Showtime.objects.select_related("screen").filter(id=showtime_id).first()
        if showtime and showtime.screen:
            return showtime.screen.vendor_id

    return None


def _resolve_discount_context_weekday(context: Optional[dict[str, Any]]) -> str:
    base_time = ensure_utc_datetime(timezone.now())
    if isinstance(context, dict):
        show_date = parse_date(coalesce(context, "show_date", "showDate", "date"))
        if show_date:
            try:
                weekday_idx = show_date.weekday()
                return WEEKDAY_CODES[weekday_idx]
            except Exception:
                pass
    return WEEKDAY_CODES[base_time.weekday()]


def _normalize_seat_categories(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized = []
    for raw in values:
        text = str(raw or "").strip().upper()
        if not text:
            continue
        if text.startswith("EXEC"):
            text = VendorPromoCode.SEAT_CATEGORY_EXECUTIVE
        elif text.startswith("PREM"):
            text = VendorPromoCode.SEAT_CATEGORY_PREMIUM
        elif text.startswith("VIP"):
            text = VendorPromoCode.SEAT_CATEGORY_VIP
        else:
            text = VendorPromoCode.SEAT_CATEGORY_NORMAL
        if text not in normalized:
            normalized.append(text)
    return normalized


def _vendor_promo_discount_for_amount(
    promo: VendorPromoCode,
    subtotal: Decimal,
    seat_count: int,
) -> Decimal:
    subtotal = _quantize_money(subtotal)
    if subtotal <= Decimal("0"):
        return Decimal("0.00")

    if promo.discount_type == VendorPromoCode.DISCOUNT_TYPE_PERCENTAGE:
        discount = _quantize_money(
            (subtotal * _quantize_money(promo.discount_value or Decimal("0"))) / Decimal("100")
        )
    elif promo.discount_type == VendorPromoCode.DISCOUNT_TYPE_FIXED:
        discount = _quantize_money(promo.discount_value or Decimal("0"))
    else:
        if seat_count < 2:
            return Decimal("0.00")
        average_seat_price = _quantize_money(subtotal / Decimal(max(seat_count, 1)))
        free_seat_count = int(seat_count // 2)
        discount = _quantize_money(average_seat_price * Decimal(free_seat_count))

    if promo.max_discount_amount is not None:
        max_discount = _quantize_money(promo.max_discount_amount or Decimal("0"))
        if discount > max_discount:
            discount = max_discount
    if discount > subtotal:
        discount = subtotal
    return discount


def _validate_vendor_promo_for_subtotal(
    coupon_code: Any,
    subtotal: Decimal,
    *,
    context: Optional[dict[str, Any]] = None,
    lock_for_update: bool = False,
) -> tuple[Optional[VendorPromoCode], Optional[dict[str, Any]], int]:
    code = _normalize_coupon_code(coupon_code)
    if not code:
        return None, {"message": "coupon_code is required."}, status.HTTP_400_BAD_REQUEST

    vendor_id = _resolve_vendor_id_from_discount_context(context)
    if not vendor_id:
        return None, {"message": "Promo code requires vendor booking context."}, status.HTTP_400_BAD_REQUEST

    queryset = VendorPromoCode.objects.filter(vendor_id=vendor_id, code__iexact=code)
    if lock_for_update:
        queryset = queryset.select_for_update()
    promo = queryset.first()
    if not promo:
        return None, {"message": "Promo code not found for this cinema."}, status.HTTP_404_NOT_FOUND

    if not promo.is_active:
        return None, {"message": "Promo code is inactive."}, status.HTTP_400_BAD_REQUEST

    now = timezone.now()
    if promo.valid_from and promo.valid_from > now:
        return None, {"message": "Promo code is not active yet."}, status.HTTP_400_BAD_REQUEST
    if promo.valid_until and promo.valid_until < now:
        return None, {"message": "Promo code has expired."}, status.HTTP_400_BAD_REQUEST

    if promo.usage_limit is not None and promo.usage_count >= promo.usage_limit:
        return None, {"message": "Promo usage limit reached."}, status.HTTP_400_BAD_REQUEST

    normalized_subtotal = _quantize_money(subtotal)
    min_amount = _quantize_money(promo.min_booking_amount or Decimal("0"))
    if normalized_subtotal < min_amount:
        return (
            None,
            {
                "message": "Order amount does not meet promo minimum requirement.",
                "min_booking_amount": float(min_amount),
            },
            status.HTTP_400_BAD_REQUEST,
        )

    weekday_filters = _parse_allowed_weekdays(promo.allowed_weekdays)
    weekday_code = _resolve_discount_context_weekday(context)
    if weekday_filters and weekday_code not in weekday_filters:
        return None, {"message": "Promo code is not valid for this day."}, status.HTTP_400_BAD_REQUEST

    seat_categories = _normalize_seat_categories(coalesce(context or {}, "seat_categories", "seatCategories", default=[]))
    if promo.seat_category_scope != VendorPromoCode.SEAT_CATEGORY_ALL:
        if not seat_categories or promo.seat_category_scope not in seat_categories:
            return (
                None,
                {"message": "Promo code is not valid for selected seat category."},
                status.HTTP_400_BAD_REQUEST,
            )

    is_student = bool(parse_bool(coalesce(context or {}, "is_student", "isStudent"), default=False))
    if promo.requires_student and not is_student:
        return None, {"message": "Promo code is only valid for student bookings."}, status.HTTP_400_BAD_REQUEST

    user_id = _coerce_int(coalesce(context or {}, "user_id", "userId"))
    if promo.per_user_limit is not None and user_id:
        used_count = Booking.objects.filter(user_id=user_id, vendor_promo_code_id=promo.id).count()
        if used_count >= promo.per_user_limit:
            return None, {"message": "Per-user promo limit reached."}, status.HTTP_400_BAD_REQUEST

    return promo, None, status.HTTP_200_OK


def _coupon_discount_for_amount(coupon: Coupon, subtotal: Decimal) -> Decimal:
    subtotal = _quantize_money(subtotal)
    if subtotal <= Decimal("0"):
        return Decimal("0.00")

    if coupon.discount_type == Coupon.DISCOUNT_TYPE_PERCENTAGE:
        discount = _quantize_money(
            (subtotal * _quantize_money(coupon.discount_value or Decimal("0")))
            / Decimal("100")
        )
    else:
        discount = _quantize_money(coupon.discount_value or Decimal("0"))
    if discount > subtotal:
        discount = subtotal
    return discount


def _validate_coupon_for_subtotal(
    coupon_code: Any,
    subtotal: Decimal,
    *,
    lock_for_update: bool = False,
) -> tuple[Optional[Coupon], Optional[dict[str, Any]], int]:
    code = _normalize_coupon_code(coupon_code)
    if not code:
        return None, {"message": "coupon_code is required."}, status.HTTP_400_BAD_REQUEST

    queryset = Coupon.objects.filter(code__iexact=code)
    if lock_for_update:
        queryset = queryset.select_for_update()
    coupon = queryset.first()
    if not coupon:
        return None, {"message": "Coupon not found."}, status.HTTP_404_NOT_FOUND

    if not coupon.is_active:
        return None, {"message": "Coupon is inactive."}, status.HTTP_400_BAD_REQUEST

    now = timezone.now()
    if coupon.expiry_date and coupon.expiry_date < now:
        return None, {"message": "Coupon has expired."}, status.HTTP_400_BAD_REQUEST

    if coupon.usage_limit is not None and coupon.usage_count >= coupon.usage_limit:
        return None, {"message": "Coupon usage limit reached."}, status.HTTP_400_BAD_REQUEST

    normalized_subtotal = _quantize_money(subtotal)
    min_amount = _quantize_money(coupon.min_booking_amount or Decimal("0"))
    if normalized_subtotal < min_amount:
        return (
            None,
            {
                "message": "Order amount does not meet coupon minimum requirement.",
                "min_booking_amount": float(min_amount),
            },
            status.HTTP_400_BAD_REQUEST,
        )

    return coupon, None, status.HTTP_200_OK


def _apply_coupon_to_subtotal(
    coupon_code: Any,
    subtotal: Decimal,
    *,
    context: Optional[dict[str, Any]] = None,
    lock_for_update: bool = False,
    consume: bool = False,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    promo, promo_error, promo_status = _validate_vendor_promo_for_subtotal(
        coupon_code,
        subtotal,
        context=context,
        lock_for_update=lock_for_update,
    )
    if promo:
        seat_count = _coerce_int(coalesce(context or {}, "seat_count", "seatCount")) or 0
        discount = _vendor_promo_discount_for_amount(promo, subtotal, seat_count=seat_count)
        final_total = _quantize_money(_quantize_money(subtotal) - discount)

        if consume:
            promo.usage_count = int(promo.usage_count or 0) + 1
            promo.save(update_fields=["usage_count", "updated_at"])

        return {
            "coupon": None,
            "promo_code": _serialize_vendor_promo_code(promo),
            "discount_source": "VENDOR_PROMO",
            "discount_amount": float(discount),
            "subtotal": float(_quantize_money(subtotal)),
            "final_total": float(final_total),
        }, None, status.HTTP_200_OK

    coupon, error, status_code = _validate_coupon_for_subtotal(
        coupon_code,
        subtotal,
        lock_for_update=lock_for_update,
    )
    if error:
        if promo_error:
            return None, promo_error, promo_status
        return None, error, status_code

    discount = _coupon_discount_for_amount(coupon, subtotal)
    final_total = _quantize_money(_quantize_money(subtotal) - discount)

    if consume:
        coupon.usage_count = int(coupon.usage_count or 0) + 1
        coupon.save(update_fields=["usage_count", "updated_at"])

    payload = {
        "coupon": _serialize_coupon(coupon),
        "promo_code": None,
        "discount_source": "ADMIN_COUPON",
        "discount_amount": float(discount),
        "subtotal": float(_quantize_money(subtotal)),
        "final_total": float(final_total),
    }
    return payload, None, status.HTTP_200_OK


def list_admin_coupons() -> list[dict[str, Any]]:
    return [_serialize_coupon(item) for item in Coupon.objects.all().order_by("-created_at", "-id")]


def create_admin_coupon(request: Any) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    code = _normalize_coupon_code(coalesce(payload, "code", "coupon_code", "couponCode"))
    if not code:
        return {"message": "code is required."}, status.HTTP_400_BAD_REQUEST
    if Coupon.objects.filter(code__iexact=code).exists():
        return {"message": "Coupon code already exists."}, status.HTTP_400_BAD_REQUEST

    discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
    if discount_type not in {
        Coupon.DISCOUNT_TYPE_PERCENTAGE,
        Coupon.DISCOUNT_TYPE_FIXED,
    }:
        return {"message": "discount_type must be PERCENTAGE or FIXED."}, status.HTTP_400_BAD_REQUEST

    discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
    if discount_value is None:
        return {"message": "discount_value must be a non-negative number."}, status.HTTP_400_BAD_REQUEST

    min_booking_amount = _parse_price_amount(
        coalesce(payload, "min_booking_amount", "minBookingAmount")
    )
    if min_booking_amount is None:
        min_booking_amount = Decimal("0.00")

    usage_limit_raw = coalesce(payload, "usage_limit", "usageLimit")
    usage_limit = _coerce_int(usage_limit_raw)
    if usage_limit_raw not in (None, "") and (usage_limit is None or usage_limit < 1):
        return {"message": "usage_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST

    expiry_date = _parse_coupon_expiry(coalesce(payload, "expiry_date", "expiryDate"))
    if coalesce(payload, "expiry_date", "expiryDate") not in (None, "") and not expiry_date:
        return {"message": "expiry_date is invalid."}, status.HTTP_400_BAD_REQUEST

    coupon = Coupon.objects.create(
        code=code,
        discount_type=discount_type,
        discount_value=discount_value,
        min_booking_amount=min_booking_amount,
        expiry_date=expiry_date,
        usage_limit=usage_limit,
        is_active=parse_bool(coalesce(payload, "is_active", "isActive"), default=True),
    )
    return {"message": "Coupon created.", "coupon": _serialize_coupon(coupon)}, status.HTTP_201_CREATED


def update_admin_coupon(request: Any, coupon: Coupon) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    updates: dict[str, Any] = {}

    if "code" in payload or "coupon_code" in payload or "couponCode" in payload:
        code = _normalize_coupon_code(coalesce(payload, "code", "coupon_code", "couponCode"))
        if not code:
            return {"message": "code cannot be empty."}, status.HTTP_400_BAD_REQUEST
        existing = Coupon.objects.filter(code__iexact=code).exclude(id=coupon.id).exists()
        if existing:
            return {"message": "Coupon code already exists."}, status.HTTP_400_BAD_REQUEST
        updates["code"] = code

    if "discount_type" in payload or "discountType" in payload:
        discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
        if discount_type not in {
            Coupon.DISCOUNT_TYPE_PERCENTAGE,
            Coupon.DISCOUNT_TYPE_FIXED,
        }:
            return {"message": "discount_type must be PERCENTAGE or FIXED."}, status.HTTP_400_BAD_REQUEST
        updates["discount_type"] = discount_type

    if "discount_value" in payload or "discountValue" in payload:
        discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
        if discount_value is None:
            return {"message": "discount_value must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["discount_value"] = discount_value

    if "min_booking_amount" in payload or "minBookingAmount" in payload:
        min_booking_amount = _parse_price_amount(
            coalesce(payload, "min_booking_amount", "minBookingAmount")
        )
        if min_booking_amount is None:
            return {"message": "min_booking_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["min_booking_amount"] = min_booking_amount

    if "usage_limit" in payload or "usageLimit" in payload:
        usage_limit_raw = coalesce(payload, "usage_limit", "usageLimit")
        usage_limit = _coerce_int(usage_limit_raw)
        if usage_limit_raw in (None, ""):
            updates["usage_limit"] = None
        elif usage_limit is None or usage_limit < 1:
            return {"message": "usage_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST
        else:
            updates["usage_limit"] = usage_limit

    if "usage_count" in payload:
        usage_count = _coerce_int(payload.get("usage_count"))
        if usage_count is None or usage_count < 0:
            return {"message": "usage_count must be zero or greater."}, status.HTTP_400_BAD_REQUEST
        updates["usage_count"] = usage_count

    if "expiry_date" in payload or "expiryDate" in payload:
        raw_expiry = coalesce(payload, "expiry_date", "expiryDate")
        if raw_expiry in (None, ""):
            updates["expiry_date"] = None
        else:
            expiry_date = _parse_coupon_expiry(raw_expiry)
            if not expiry_date:
                return {"message": "expiry_date is invalid."}, status.HTTP_400_BAD_REQUEST
            updates["expiry_date"] = expiry_date

    if "is_active" in payload or "isActive" in payload:
        updates["is_active"] = parse_bool(coalesce(payload, "is_active", "isActive"), default=True)

    if not updates:
        return {"message": "No coupon changes provided."}, status.HTTP_400_BAD_REQUEST

    for key, value in updates.items():
        setattr(coupon, key, value)
    coupon.save()
    return {"message": "Coupon updated.", "coupon": _serialize_coupon(coupon)}, status.HTTP_200_OK


def delete_admin_coupon(coupon: Coupon) -> tuple[dict[str, Any], int]:
    coupon.delete()
    return {"message": "Coupon deleted."}, status.HTTP_200_OK


def list_vendor_promo_codes(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
    promos = VendorPromoCode.objects.filter(vendor_id=vendor.id).order_by("-created_at", "-id")
    return {"promo_codes": [_serialize_vendor_promo_code(item) for item in promos]}, status.HTTP_200_OK


def _parse_promo_payload(payload: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    code = _normalize_coupon_code(coalesce(payload, "code", "promo_code", "promoCode"))
    title = str(coalesce(payload, "title", "name") or "").strip()
    discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
    discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
    if not code:
        return None, "code is required."
    if not title:
        return None, "title is required."
    if discount_type not in {
        VendorPromoCode.DISCOUNT_TYPE_PERCENTAGE,
        VendorPromoCode.DISCOUNT_TYPE_FIXED,
        VendorPromoCode.DISCOUNT_TYPE_BOGO,
    }:
        return None, "discount_type must be PERCENTAGE, FIXED, or BOGO."
    if discount_value is None:
        return None, "discount_value must be a non-negative number."

    min_booking_amount = _parse_price_amount(coalesce(payload, "min_booking_amount", "minBookingAmount"))
    if min_booking_amount is None:
        min_booking_amount = Decimal("0.00")

    max_discount_amount = _parse_price_amount(coalesce(payload, "max_discount_amount", "maxDiscountAmount"))
    usage_limit_raw = coalesce(payload, "usage_limit", "usageLimit")
    usage_limit = _coerce_int(usage_limit_raw)
    if usage_limit_raw not in (None, "") and (usage_limit is None or usage_limit < 1):
        return None, "usage_limit must be a positive integer."

    per_user_limit_raw = coalesce(payload, "per_user_limit", "perUserLimit")
    per_user_limit = _coerce_int(per_user_limit_raw)
    if per_user_limit_raw not in (None, "") and (per_user_limit is None or per_user_limit < 1):
        return None, "per_user_limit must be a positive integer."

    seat_scope = str(coalesce(payload, "seat_category_scope", "seatCategoryScope") or VendorPromoCode.SEAT_CATEGORY_ALL).strip().upper()
    if seat_scope not in {
        VendorPromoCode.SEAT_CATEGORY_ALL,
        VendorPromoCode.SEAT_CATEGORY_NORMAL,
        VendorPromoCode.SEAT_CATEGORY_EXECUTIVE,
        VendorPromoCode.SEAT_CATEGORY_PREMIUM,
        VendorPromoCode.SEAT_CATEGORY_VIP,
    }:
        return None, "seat_category_scope is invalid."

    valid_from = _parse_datetime_value(coalesce(payload, "valid_from", "validFrom"))
    valid_until = _parse_datetime_value(coalesce(payload, "valid_until", "validUntil"))
    if valid_from and valid_until and valid_from > valid_until:
        return None, "valid_until must be after valid_from."

    weekday_values = coalesce(payload, "allowed_weekdays", "allowedWeekdays", default="")
    if isinstance(weekday_values, (list, tuple, set)):
        weekdays_text = ",".join([str(item).strip().upper() for item in weekday_values])
    else:
        weekdays_text = str(weekday_values or "").strip().upper()

    return {
        "code": code,
        "title": title,
        "description": str(coalesce(payload, "description") or "").strip() or None,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "min_booking_amount": min_booking_amount,
        "max_discount_amount": max_discount_amount,
        "usage_limit": usage_limit,
        "per_user_limit": per_user_limit,
        "seat_category_scope": seat_scope,
        "requires_student": parse_bool(coalesce(payload, "requires_student", "requiresStudent"), default=False),
        "allowed_weekdays": weekdays_text or None,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "is_flash_sale": parse_bool(coalesce(payload, "is_flash_sale", "isFlashSale"), default=False),
        "is_active": parse_bool(coalesce(payload, "is_active", "isActive"), default=True),
    }, None


def create_vendor_promo_code(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    parsed, error_message = _parse_promo_payload(payload)
    if error_message:
        return {"message": error_message}, status.HTTP_400_BAD_REQUEST

    if VendorPromoCode.objects.filter(code__iexact=parsed["code"]).exists() or Coupon.objects.filter(code__iexact=parsed["code"]).exists():
        return {"message": "Promo code already exists."}, status.HTTP_400_BAD_REQUEST

    promo = VendorPromoCode.objects.create(vendor_id=vendor.id, **parsed)
    return {
        "message": "Vendor promo code created.",
        "promo_code": _serialize_vendor_promo_code(promo),
    }, status.HTTP_201_CREATED


def update_vendor_promo_code(request: Any, promo: VendorPromoCode) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    updates: dict[str, Any] = {}

    if "code" in payload or "promo_code" in payload or "promoCode" in payload:
        code = _normalize_coupon_code(coalesce(payload, "code", "promo_code", "promoCode"))
        if not code:
            return {"message": "code cannot be empty."}, status.HTTP_400_BAD_REQUEST
        if (
            VendorPromoCode.objects.filter(code__iexact=code).exclude(id=promo.id).exists()
            or Coupon.objects.filter(code__iexact=code).exists()
        ):
            return {"message": "Promo code already exists."}, status.HTTP_400_BAD_REQUEST
        updates["code"] = code

    if "title" in payload or "name" in payload:
        title = str(coalesce(payload, "title", "name") or "").strip()
        if not title:
            return {"message": "title cannot be empty."}, status.HTTP_400_BAD_REQUEST
        updates["title"] = title

    if "description" in payload:
        updates["description"] = str(payload.get("description") or "").strip() or None

    if "discount_type" in payload or "discountType" in payload:
        discount_type = str(coalesce(payload, "discount_type", "discountType") or "").strip().upper()
        if discount_type not in {
            VendorPromoCode.DISCOUNT_TYPE_PERCENTAGE,
            VendorPromoCode.DISCOUNT_TYPE_FIXED,
            VendorPromoCode.DISCOUNT_TYPE_BOGO,
        }:
            return {"message": "discount_type must be PERCENTAGE, FIXED, or BOGO."}, status.HTTP_400_BAD_REQUEST
        updates["discount_type"] = discount_type

    if "discount_value" in payload or "discountValue" in payload:
        discount_value = _parse_price_amount(coalesce(payload, "discount_value", "discountValue"))
        if discount_value is None:
            return {"message": "discount_value must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["discount_value"] = discount_value

    if "min_booking_amount" in payload or "minBookingAmount" in payload:
        min_amount = _parse_price_amount(coalesce(payload, "min_booking_amount", "minBookingAmount"))
        if min_amount is None:
            return {"message": "min_booking_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        updates["min_booking_amount"] = min_amount

    if "max_discount_amount" in payload or "maxDiscountAmount" in payload:
        raw = coalesce(payload, "max_discount_amount", "maxDiscountAmount")
        if raw in (None, ""):
            updates["max_discount_amount"] = None
        else:
            max_amount = _parse_price_amount(raw)
            if max_amount is None:
                return {"message": "max_discount_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
            updates["max_discount_amount"] = max_amount

    if "usage_limit" in payload or "usageLimit" in payload:
        raw = coalesce(payload, "usage_limit", "usageLimit")
        if raw in (None, ""):
            updates["usage_limit"] = None
        else:
            usage_limit = _coerce_int(raw)
            if usage_limit is None or usage_limit < 1:
                return {"message": "usage_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST
            updates["usage_limit"] = usage_limit

    if "per_user_limit" in payload or "perUserLimit" in payload:
        raw = coalesce(payload, "per_user_limit", "perUserLimit")
        if raw in (None, ""):
            updates["per_user_limit"] = None
        else:
            per_user_limit = _coerce_int(raw)
            if per_user_limit is None or per_user_limit < 1:
                return {"message": "per_user_limit must be a positive integer."}, status.HTTP_400_BAD_REQUEST
            updates["per_user_limit"] = per_user_limit

    if "seat_category_scope" in payload or "seatCategoryScope" in payload:
        seat_scope = str(coalesce(payload, "seat_category_scope", "seatCategoryScope") or "").strip().upper()
        if seat_scope not in {
            VendorPromoCode.SEAT_CATEGORY_ALL,
            VendorPromoCode.SEAT_CATEGORY_NORMAL,
            VendorPromoCode.SEAT_CATEGORY_EXECUTIVE,
            VendorPromoCode.SEAT_CATEGORY_PREMIUM,
            VendorPromoCode.SEAT_CATEGORY_VIP,
        }:
            return {"message": "seat_category_scope is invalid."}, status.HTTP_400_BAD_REQUEST
        updates["seat_category_scope"] = seat_scope

    if "requires_student" in payload or "requiresStudent" in payload:
        updates["requires_student"] = parse_bool(
            coalesce(payload, "requires_student", "requiresStudent"),
            default=promo.requires_student,
        )

    if "allowed_weekdays" in payload or "allowedWeekdays" in payload:
        weekday_values = coalesce(payload, "allowed_weekdays", "allowedWeekdays", default="")
        if isinstance(weekday_values, (list, tuple, set)):
            weekdays_text = ",".join([str(item).strip().upper() for item in weekday_values])
        else:
            weekdays_text = str(weekday_values or "").strip().upper()
        updates["allowed_weekdays"] = weekdays_text or None

    if "valid_from" in payload or "validFrom" in payload:
        updates["valid_from"] = _parse_datetime_value(coalesce(payload, "valid_from", "validFrom"))

    if "valid_until" in payload or "validUntil" in payload:
        updates["valid_until"] = _parse_datetime_value(coalesce(payload, "valid_until", "validUntil"))

    if "is_flash_sale" in payload or "isFlashSale" in payload:
        updates["is_flash_sale"] = parse_bool(
            coalesce(payload, "is_flash_sale", "isFlashSale"),
            default=promo.is_flash_sale,
        )

    if "is_active" in payload or "isActive" in payload:
        updates["is_active"] = parse_bool(
            coalesce(payload, "is_active", "isActive"),
            default=promo.is_active,
        )

    if not updates:
        return {"message": "No promo code changes provided."}, status.HTTP_400_BAD_REQUEST

    for key, value in updates.items():
        setattr(promo, key, value)
    promo.save()

    return {
        "message": "Vendor promo code updated.",
        "promo_code": _serialize_vendor_promo_code(promo),
    }, status.HTTP_200_OK


def delete_vendor_promo_code(promo: VendorPromoCode) -> tuple[dict[str, Any], int]:
    promo.delete()
    return {"message": "Vendor promo code deleted."}, status.HTTP_200_OK


def _render_vendor_campaign_message(
    template: str,
    *,
    user: User,
    last_movie_title: str,
    recommended_movie_title: str,
    promo_code: Optional[str],
    promo_value: Optional[str],
) -> str:
    safe_template = str(template or "").strip() or (
        "Hey {first_name}, you watched {last_movie} with us. "
        "Book {next_movie} early with {promo_code}!"
    )
    full_name = " ".join(
        [part for part in [user.first_name, user.middle_name, user.last_name] if part]
    ).strip()
    values = {
        "first_name": user.first_name or "Customer",
        "full_name": full_name or user.email or "Customer",
        "last_movie": last_movie_title or "your recent movie",
        "next_movie": recommended_movie_title or "our latest show",
        "promo_code": promo_code or "a special offer",
        "discount_value": promo_value or "",
    }
    return safe_template.format(**values)


def _get_campaign_audience(campaign: VendorCampaign) -> list[tuple[User, str]]:
    queryset = (
        Booking.objects.filter(
            Q(showtime__vendor_id=campaign.vendor_id)
            | Q(showtime__screen__vendor_id=campaign.vendor_id),
            booking_status=Booking.Status.CONFIRMED,
            user__isnull=False,
        )
        .select_related("user", "showtime__movie")
    )

    if campaign.target_movie_id:
        queryset = queryset.filter(showtime__movie_id=campaign.target_movie_id)

    if campaign.min_days_since_booking and campaign.min_days_since_booking > 0:
        threshold = timezone.now() - timedelta(days=int(campaign.min_days_since_booking))
        queryset = queryset.filter(booking_date__lte=threshold)

    latest_by_user: dict[int, tuple[User, str]] = {}
    for booking in queryset.order_by("user_id", "-booking_date", "-id"):
        if booking.user_id in latest_by_user:
            continue
        movie_title = booking.showtime.movie.title if booking.showtime and booking.showtime.movie else ""
        latest_by_user[booking.user_id] = (booking.user, movie_title)

    return list(latest_by_user.values())


def _dispatch_vendor_campaign(campaign: VendorCampaign) -> dict[str, Any]:
    audience = _get_campaign_audience(campaign)
    sent_count = 0
    failed_count = 0
    recommended_movie_title = campaign.recommended_movie.title if campaign.recommended_movie_id and campaign.recommended_movie else ""
    promo_code = campaign.promo_code.code if campaign.promo_code_id and campaign.promo_code else None
    promo_value = (
        str(_quantize_money(campaign.promo_code.discount_value or Decimal("0")))
        if campaign.promo_code_id and campaign.promo_code
        else None
    )

    campaign.status = VendorCampaign.STATUS_RUNNING
    campaign.save(update_fields=["status", "updated_at"])

    for user, last_movie_title in audience:
        message = _render_vendor_campaign_message(
            campaign.message_template,
            user=user,
            last_movie_title=last_movie_title,
            recommended_movie_title=recommended_movie_title,
            promo_code=promo_code,
            promo_value=promo_value,
        )

        if campaign.delivery_channel in {VendorCampaign.CHANNEL_PUSH, VendorCampaign.CHANNEL_BOTH}:
            try:
                _create_notification(
                    recipient_role=Notification.ROLE_CUSTOMER,
                    recipient_id=user.id,
                    recipient_email=user.email,
                    event_type=Notification.EVENT_MARKETING_CAMPAIGN,
                    title=f"{campaign.vendor.name}: Special Offer",
                    message=message,
                    metadata={
                        "campaign_id": campaign.id,
                        "vendor_id": campaign.vendor_id,
                        "promo_code": promo_code,
                    },
                    send_email_too=False,
                )
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_PUSH,
                    contact=user.email,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_SENT,
                )
                sent_count += 1
            except Exception as exc:
                failed_count += 1
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_PUSH,
                    contact=user.email,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_FAILED,
                    error_message=str(exc)[:255],
                )

        if campaign.delivery_channel in {VendorCampaign.CHANNEL_SMS, VendorCampaign.CHANNEL_BOTH}:
            phone = str(user.phone_number or "").strip()
            if phone:
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_SMS,
                    contact=phone,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_SENT,
                )
                sent_count += 1
            else:
                failed_count += 1
                VendorCampaignDispatch.objects.create(
                    campaign_id=campaign.id,
                    user_id=user.id,
                    channel=VendorCampaignDispatch.CHANNEL_SMS,
                    contact=None,
                    message=message,
                    status=VendorCampaignDispatch.STATUS_FAILED,
                    error_message="User phone number is missing.",
                )

    campaign.sent_count = int(campaign.sent_count or 0) + sent_count
    campaign.failed_count = int(campaign.failed_count or 0) + failed_count
    campaign.last_run_at = timezone.now()
    campaign.status = VendorCampaign.STATUS_COMPLETED
    campaign.save(update_fields=["sent_count", "failed_count", "last_run_at", "status", "updated_at"])

    return {
        "audience_count": len(audience),
        "sent_count": sent_count,
        "failed_count": failed_count,
    }


def _sync_due_vendor_campaigns(vendor_id: int) -> None:
    now = timezone.now()
    campaigns = VendorCampaign.objects.filter(
        vendor_id=vendor_id,
        status=VendorCampaign.STATUS_SCHEDULED,
        scheduled_at__isnull=False,
        scheduled_at__lte=now,
    ).select_related("vendor", "promo_code", "recommended_movie")
    for campaign in campaigns:
        try:
            _dispatch_vendor_campaign(campaign)
        except Exception:
            logger.exception("Failed to auto-dispatch vendor campaign %s", campaign.id)


def list_vendor_campaigns(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    _sync_due_vendor_campaigns(vendor.id)

    campaigns = VendorCampaign.objects.filter(vendor_id=vendor.id).select_related(
        "promo_code", "target_movie", "recommended_movie"
    ).order_by("-created_at", "-id")
    return {"campaigns": [_serialize_vendor_campaign(item) for item in campaigns]}, status.HTTP_200_OK


def create_vendor_campaign(request: Any) -> tuple[dict[str, Any], int]:
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    name = str(coalesce(payload, "name", "title") or "").strip()
    message_template = str(coalesce(payload, "message_template", "messageTemplate", "message") or "").strip()
    if not name:
        return {"message": "name is required."}, status.HTTP_400_BAD_REQUEST
    if not message_template:
        return {"message": "message_template is required."}, status.HTTP_400_BAD_REQUEST

    channel = str(coalesce(payload, "delivery_channel", "deliveryChannel") or VendorCampaign.CHANNEL_BOTH).strip().upper()
    if channel not in {VendorCampaign.CHANNEL_PUSH, VendorCampaign.CHANNEL_SMS, VendorCampaign.CHANNEL_BOTH}:
        return {"message": "delivery_channel must be PUSH, SMS, or BOTH."}, status.HTTP_400_BAD_REQUEST

    target_movie_id = _coerce_int(coalesce(payload, "target_movie_id", "targetMovieId"))
    recommended_movie_id = _coerce_int(coalesce(payload, "recommended_movie_id", "recommendedMovieId"))
    promo_code_id = _coerce_int(coalesce(payload, "promo_code_id", "promoCodeId"))

    promo_code = None
    if promo_code_id:
        promo_code = VendorPromoCode.objects.filter(id=promo_code_id, vendor_id=vendor.id, is_active=True).first()
        if not promo_code:
            return {"message": "promo_code_id is invalid."}, status.HTTP_400_BAD_REQUEST

    campaign = VendorCampaign.objects.create(
        vendor_id=vendor.id,
        name=name,
        message_template=message_template,
        delivery_channel=channel,
        status=VendorCampaign.STATUS_SCHEDULED
        if coalesce(payload, "scheduled_at", "scheduledAt")
        else VendorCampaign.STATUS_DRAFT,
        target_movie_id=target_movie_id,
        recommended_movie_id=recommended_movie_id,
        promo_code=promo_code,
        include_past_attendees_only=parse_bool(
            coalesce(payload, "include_past_attendees_only", "includePastAttendeesOnly"),
            default=True,
        ),
        min_days_since_booking=max(0, _coerce_int(coalesce(payload, "min_days_since_booking", "minDaysSinceBooking")) or 0),
        scheduled_at=_parse_datetime_value(coalesce(payload, "scheduled_at", "scheduledAt")),
    )

    if parse_bool(coalesce(payload, "run_now", "runNow"), default=False):
        stats = _dispatch_vendor_campaign(campaign)
        return {
            "message": "Campaign created and dispatched.",
            "campaign": _serialize_vendor_campaign(campaign),
            "dispatch": stats,
        }, status.HTTP_201_CREATED

    return {
        "message": "Vendor campaign created.",
        "campaign": _serialize_vendor_campaign(campaign),
    }, status.HTTP_201_CREATED


def update_vendor_campaign(request: Any, campaign: VendorCampaign) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    updates: dict[str, Any] = {}

    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            return {"message": "name cannot be empty."}, status.HTTP_400_BAD_REQUEST
        updates["name"] = name

    if "message_template" in payload or "messageTemplate" in payload or "message" in payload:
        message_template = str(coalesce(payload, "message_template", "messageTemplate", "message") or "").strip()
        if not message_template:
            return {"message": "message_template cannot be empty."}, status.HTTP_400_BAD_REQUEST
        updates["message_template"] = message_template

    if "delivery_channel" in payload or "deliveryChannel" in payload:
        channel = str(coalesce(payload, "delivery_channel", "deliveryChannel") or "").strip().upper()
        if channel not in {VendorCampaign.CHANNEL_PUSH, VendorCampaign.CHANNEL_SMS, VendorCampaign.CHANNEL_BOTH}:
            return {"message": "delivery_channel must be PUSH, SMS, or BOTH."}, status.HTTP_400_BAD_REQUEST
        updates["delivery_channel"] = channel

    if "target_movie_id" in payload or "targetMovieId" in payload:
        updates["target_movie_id"] = _coerce_int(coalesce(payload, "target_movie_id", "targetMovieId"))

    if "recommended_movie_id" in payload or "recommendedMovieId" in payload:
        updates["recommended_movie_id"] = _coerce_int(coalesce(payload, "recommended_movie_id", "recommendedMovieId"))

    if "promo_code_id" in payload or "promoCodeId" in payload:
        promo_code_id = _coerce_int(coalesce(payload, "promo_code_id", "promoCodeId"))
        if promo_code_id:
            promo_code = VendorPromoCode.objects.filter(
                id=promo_code_id,
                vendor_id=campaign.vendor_id,
                is_active=True,
            ).first()
            if not promo_code:
                return {"message": "promo_code_id is invalid."}, status.HTTP_400_BAD_REQUEST
            updates["promo_code"] = promo_code
        else:
            updates["promo_code"] = None

    if "include_past_attendees_only" in payload or "includePastAttendeesOnly" in payload:
        updates["include_past_attendees_only"] = parse_bool(
            coalesce(payload, "include_past_attendees_only", "includePastAttendeesOnly"),
            default=campaign.include_past_attendees_only,
        )

    if "min_days_since_booking" in payload or "minDaysSinceBooking" in payload:
        updates["min_days_since_booking"] = max(
            0,
            _coerce_int(coalesce(payload, "min_days_since_booking", "minDaysSinceBooking")) or 0,
        )

    if "scheduled_at" in payload or "scheduledAt" in payload:
        updates["scheduled_at"] = _parse_datetime_value(coalesce(payload, "scheduled_at", "scheduledAt"))

    if "status" in payload:
        next_status = str(payload.get("status") or "").strip().upper()
        if next_status not in {
            VendorCampaign.STATUS_DRAFT,
            VendorCampaign.STATUS_SCHEDULED,
            VendorCampaign.STATUS_RUNNING,
            VendorCampaign.STATUS_COMPLETED,
        }:
            return {"message": "status is invalid."}, status.HTTP_400_BAD_REQUEST
        updates["status"] = next_status

    if not updates:
        return {"message": "No campaign changes provided."}, status.HTTP_400_BAD_REQUEST

    for key, value in updates.items():
        setattr(campaign, key, value)
    campaign.save()

    return {
        "message": "Vendor campaign updated.",
        "campaign": _serialize_vendor_campaign(campaign),
    }, status.HTTP_200_OK


def run_vendor_campaign(campaign: VendorCampaign) -> tuple[dict[str, Any], int]:
    stats = _dispatch_vendor_campaign(campaign)
    recent_dispatches = VendorCampaignDispatch.objects.filter(campaign_id=campaign.id).order_by("-id")[:20]
    return {
        "message": "Campaign dispatched.",
        "campaign": _serialize_vendor_campaign(campaign),
        "dispatch": stats,
        "recent_logs": [_serialize_vendor_campaign_dispatch(item) for item in recent_dispatches],
    }, status.HTTP_200_OK


def apply_coupon_for_booking(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    subtotal = _parse_price_amount(
        coalesce(payload, "subtotal", "ticket_total", "ticketTotal", "amount")
    )
    if subtotal is None or subtotal <= Decimal("0"):
        return {"message": "A valid subtotal amount is required."}, status.HTTP_400_BAD_REQUEST

    coupon_code = coalesce(payload, "coupon_code", "couponCode", "code")
    result, error, status_code = _apply_coupon_to_subtotal(
        coupon_code,
        subtotal,
        context=payload,
        lock_for_update=False,
        consume=False,
    )
    if error:
        return error, status_code

    return {
        "message": "Coupon applied successfully.",
        "coupon": result["coupon"],
        "promo_code": result.get("promo_code"),
        "discount_source": result.get("discount_source"),
        "subtotal": result["subtotal"],
        "discount_amount": result["discount_amount"],
        "final_total": result["final_total"],
    }, status.HTTP_200_OK


def build_user_payload(user: User, request: Any) -> dict[str, Any]:
    """Build the API payload for a user."""
    full_name = " ".join(
        [part for part in [user.first_name, user.middle_name, user.last_name] if part]
    ).strip()
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "referral_code": user.referral_code,
        "first_name": user.first_name,
        "middle_name": user.middle_name,
        "last_name": user.last_name,
        "full_name": full_name,
        "phone_number": user.phone_number,
        "profile_image": get_profile_image_url(request, user),
        "dob": user.dob.isoformat() if user.dob else None,
        "is_active": getattr(user, "is_active", True),
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
    }


def build_admin_payload(admin_user: Admin, request: Any) -> dict[str, Any]:
    """Build the API payload for an admin user."""
    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "username": admin_user.username,
        "full_name": admin_user.full_name,
        "phone_number": admin_user.phone_number,
        "is_active": admin_user.is_active,
        "profile_image": get_profile_image_url(request, admin_user),
        "date_joined": admin_user.date_joined.isoformat()
        if admin_user.date_joined
        else None,
    }


def build_vendor_payload(vendor_user: Vendor, request: Any) -> dict[str, Any]:
    """Build the API payload for a vendor user."""
    return {
        "id": vendor_user.id,
        "name": vendor_user.name,
        "email": vendor_user.email,
        "username": vendor_user.username,
        "phone_number": vendor_user.phone_number,
        "theatre": vendor_user.theatre,
        "city": vendor_user.city,
        "commission_percent": float(_resolve_vendor_commission_percent(vendor_user)),
        "status": vendor_user.status,
        "is_active": vendor_user.is_active,
        "created_at": vendor_user.created_at.isoformat() if vendor_user.created_at else None,
        "profile_image": get_profile_image_url(request, vendor_user),
    }


def build_vendor_staff_payload(staff_user: VendorStaff) -> dict[str, Any]:
    """Build the API payload for a vendor staff user."""
    return {
        "id": staff_user.id,
        "vendor_id": staff_user.vendor_id,
        "full_name": staff_user.full_name,
        "email": staff_user.email,
        "phone_number": staff_user.phone_number,
        "username": staff_user.username,
        "role": staff_user.role,
        "is_active": staff_user.is_active,
        "created_at": staff_user.created_at.isoformat() if staff_user.created_at else None,
        "updated_at": staff_user.updated_at.isoformat() if staff_user.updated_at else None,
    }


def _login_identity_query(
    identifier: str,
    phone_candidates: Optional[set[str]] = None,
    include_username: bool = True,
) -> Q:
    """Build a login query for email/phone/username."""
    query = Q(email__iexact=identifier)
    if phone_candidates:
        query |= Q(phone_number__in=phone_candidates)
    else:
        query |= Q(phone_number=identifier)
    if include_username:
        query |= Q(username__iexact=identifier)
    return query


def _admin_lookup_query_from_user(user: User) -> Q:
    """Build a query to find an Admin matching a User identity."""
    query = Q(email__iexact=user.email)
    if user.username:
        query |= Q(username__iexact=user.username)
    if user.phone_number:
        query |= Q(phone_number=user.phone_number)
    return query


def _admin_login_payload(admin: Admin, password: str, request: Any) -> tuple[dict[str, Any], int]:
    """Return the admin login response payload."""
    if not admin.is_active:
        return {"message": "Admin account is inactive"}, status.HTTP_403_FORBIDDEN
    if not admin.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED
    display_name = admin.full_name or admin.username or admin.email
    token_payload = _issue_session_tokens("admin", admin.id)
    return {
        "message": f"Admin login successful. Welcome {display_name}!",
        "role": "admin",
        "admin": build_admin_payload(admin, request),
        **token_payload,
    }, status.HTTP_200_OK


def _vendor_login_payload(vendor: Vendor, password: str, request: Any) -> tuple[dict[str, Any], int]:
    """Return the vendor login response payload."""
    if not vendor.is_active or str(vendor.status).lower() == "blocked":
        return {"message": "Vendor account is inactive"}, status.HTTP_403_FORBIDDEN
    if not vendor.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED
    display_name = vendor.name or vendor.username or vendor.email
    token_payload = _issue_session_tokens("vendor", vendor.id)
    return {
        "message": f"Vendor login successful. Welcome {display_name}!",
        "role": "vendor",
        "vendor": build_vendor_payload(vendor, request),
        "vendor_staff": None,
        **token_payload,
    }, status.HTTP_200_OK


def _vendor_staff_login_payload(
    staff: VendorStaff,
    password: str,
    request: Any,
) -> tuple[dict[str, Any], int]:
    """Return the vendor staff login payload as a vendor-scoped session."""
    vendor = staff.vendor
    if not staff.is_active:
        return {"message": "Vendor staff account is inactive"}, status.HTTP_403_FORBIDDEN
    if not vendor.is_active or str(vendor.status).lower() == "blocked":
        return {"message": "Vendor account is inactive"}, status.HTTP_403_FORBIDDEN
    if not staff.check_password(password):
        return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED

    display_name = staff.full_name or staff.username or staff.email
    token_payload = _issue_session_tokens(
        "vendor",
        vendor.id,
        extras={
            "staff_id": staff.id,
            "staff_role": staff.role,
        },
    )
    return {
        "message": f"Vendor login successful. Welcome {display_name}!",
        "role": "vendor",
        "vendor": build_vendor_payload(vendor, request),
        "vendor_staff": build_vendor_staff_payload(staff),
        **token_payload,
    }, status.HTTP_200_OK


def _is_truthy_flag(value: Any) -> bool:
    """Normalize common truthy flag values."""
    return str(value or "").lower() in ("1", "true", "yes")


def _update_profile_image(instance: Any, uploaded_image: Any, remove_avatar: bool) -> None:
    """Update or clear profile image based on inputs."""
    if remove_avatar:
        if instance.profile_image:
            instance.profile_image.delete(save=False)
        instance.profile_image = None
        instance.save()
        return
    if uploaded_image:
        if instance.profile_image:
            instance.profile_image.delete(save=False)
        instance.profile_image = uploaded_image
        instance.save()


def register_user(request: Any) -> tuple[dict[str, Any], int]:
    """Register a new user account."""
    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        email = str(serializer.validated_data.get("email") or "").strip().lower()
        if not _has_verified_registration_otp(email):
            return {
                "message": (
                    "Email verification required. Send OTP and verify your email "
                    "before registering."
                )
            }, status.HTTP_400_BAD_REQUEST

        payload = get_payload(request)
        requested_referral_code = str(
            coalesce(payload, "referral_code", "referralCode", default=serializer.validated_data.get("referral_code"))
            or ""
        ).strip().upper()
        signup_ip = _extract_client_ip(request)
        signup_user_agent = _extract_client_user_agent(request)
        signup_device_fingerprint = _extract_device_fingerprint(request, payload)

        try:
            with transaction.atomic():
                user = serializer.save()
                ensure_user_referral_code(user)
                _update_signup_metadata(
                    user,
                    signup_ip=signup_ip,
                    signup_user_agent=signup_user_agent,
                    signup_device_fingerprint=signup_device_fingerprint,
                )

                referral_result = None
                if requested_referral_code:
                    referral_result = _link_referral_on_signup(
                        user=user,
                        referral_code=requested_referral_code,
                        signup_ip=signup_ip,
                        signup_user_agent=signup_user_agent,
                        signup_device_fingerprint=signup_device_fingerprint,
                    )

                OTPVerification.objects.filter(email__iexact=email).delete()

            response_payload: dict[str, Any] = {
                "message": "Registration successful",
                "user": build_user_payload(user, request),
            }
            if referral_result:
                response_payload["referral"] = referral_result

            return response_payload, status.HTTP_201_CREATED
        except Exception as exc:
            logger.exception("Error saving user")
            return {
                "message": "Failed to create user",
                "error": str(exc),
            }, status.HTTP_500_INTERNAL_SERVER_ERROR

    return {
        "message": "Registration failed",
        "errors": serializer.errors,
    }, status.HTTP_400_BAD_REQUEST


def _has_verified_registration_otp(email: Optional[str]) -> bool:
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        return False

    cutoff = timezone.now() - timedelta(minutes=EMAIL_OTP_TTL_MINUTES)
    return OTPVerification.objects.filter(
        email__iexact=normalized_email,
        is_verified=True,
        created_at__gte=cutoff,
    ).exists()


def request_registration_otp(email: Optional[str]) -> tuple[dict[str, Any], int]:
    """Send email OTP for registration verification."""
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        return {"message": "Email is required"}, status.HTTP_400_BAD_REQUEST

    if "@" not in normalized_email or "." not in normalized_email.split("@")[-1]:
        return {"message": "Invalid email format"}, status.HTTP_400_BAD_REQUEST

    if User.objects.filter(email__iexact=normalized_email).exists():
        return {
            "message": "Email is already registered. Please login with this email."
        }, status.HTTP_409_CONFLICT

    email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "").strip().lower()
    smtp_backend = "django.core.mail.backends.smtp.emailbackend"
    if email_backend == smtp_backend:
        smtp_user = str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
        smtp_password = str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip()
        if not smtp_user or not smtp_password:
            return {
                "message": (
                    "Email service is not configured. Set EMAIL_HOST_USER and "
                    "EMAIL_HOST_PASSWORD in .env.local, then restart backend."
                )
            }, status.HTTP_503_SERVICE_UNAVAILABLE

    otp = f"{random.randint(100000, 999999)}"
    otp_record = OTPVerification.objects.create(email=normalized_email, otp=otp)
    subject = "Mero Ticket registration OTP"
    message = (
        "Your Mero Ticket registration OTP is: "
        f"{otp}\n\n"
        f"This OTP is valid for {EMAIL_OTP_TTL_MINUTES} minutes.\n"
        "If you did not request this, please ignore this email."
    )
    html_message = _build_password_reset_otp_html(otp)

    email_sent = _send_notification_email(
        subject=subject,
        message=message,
        recipient_email=normalized_email,
        html_message=html_message,
    )
    if not email_sent:
        otp_record.delete()
        return {
            "message": "Failed to send registration OTP email. Please try again later."
        }, status.HTTP_500_INTERNAL_SERVER_ERROR

    if bool(getattr(settings, "DEBUG", False)):
        print(f"DEBUG REGISTER OTP for {normalized_email}: {otp}")

    return {"message": "Registration OTP sent to your email"}, status.HTTP_200_OK


def verify_registration_otp(email: Optional[str], otp: Optional[str]) -> tuple[dict[str, Any], int]:
    """Verify registration OTP for an email address."""
    normalized_email = str(email or "").strip().lower()
    otp_value = str(otp or "").strip()
    if not normalized_email or not otp_value:
        return {
            "message": "Email and OTP are required"
        }, status.HTTP_400_BAD_REQUEST

    cutoff = timezone.now() - timedelta(minutes=EMAIL_OTP_TTL_MINUTES)
    record = (
        OTPVerification.objects.filter(
            email__iexact=normalized_email,
            otp=otp_value,
            created_at__gte=cutoff,
        )
        .order_by("-created_at")
        .first()
    )
    if not record:
        return {
            "message": "Invalid or expired OTP"
        }, status.HTTP_400_BAD_REQUEST

    record.is_verified = True
    record.save(update_fields=["is_verified"])
    return {"message": "Registration OTP verified"}, status.HTTP_200_OK


def login_user(request: Any) -> tuple[dict[str, Any], int]:
    """Authenticate a user, vendor, or admin."""
    serializer = UserLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return {
            "message": "Invalid input",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    raw_identifier = serializer.validated_data["email_or_phone"].strip()
    password = serializer.validated_data["password"]
    phone_candidates: Optional[set[str]] = None
    if is_phone_like(raw_identifier):
        normalized_phone = normalize_phone_number(raw_identifier)
        if normalized_phone:
            phone_candidates = {normalized_phone, raw_identifier}

    try:
        admin = Admin.objects.filter(
            _login_identity_query(raw_identifier, phone_candidates)
        ).first()
        if admin:
            return _admin_login_payload(admin, password, request)

        vendor_query = _login_identity_query(raw_identifier, phone_candidates)
        if str(raw_identifier).isdigit():
            try:
                vendor_query |= Q(id=int(raw_identifier))
            except ValueError:
                pass

        vendor = Vendor.objects.filter(vendor_query).first()

        if vendor:
            return _vendor_login_payload(vendor, password, request)

        staff_query = _login_identity_query(raw_identifier, phone_candidates)
        staff = VendorStaff.objects.select_related("vendor").filter(staff_query).first()
        if staff:
            return _vendor_staff_login_payload(staff, password, request)

        user_phone_query = (
            Q(phone_number__in=phone_candidates)
            if phone_candidates
            else Q(phone_number=raw_identifier)
        )
        user = User.objects.filter(
            Q(email__iexact=raw_identifier) | user_phone_query
        ).first()

        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        admin_for_user = Admin.objects.filter(_admin_lookup_query_from_user(user)).first()
        if admin_for_user:
            return _admin_login_payload(admin_for_user, password, request)

        if hasattr(user, "is_active") and not user.is_active:
            return {"message": "User account is inactive"}, status.HTTP_403_FORBIDDEN

        if not user.check_password(password):
            return {"message": "Incorrect password"}, status.HTTP_401_UNAUTHORIZED

        ensure_user_referral_code(user)
        token_payload = _issue_session_tokens("customer", user.id)
        try:
            _ensure_customer_login_offer_notification(user)
        except Exception:
            logger.exception("Failed to create login offer notification for user %s", user.id)
        return {
            "message": f"Login successful. Welcome {user.first_name}!",
            "role": "customer",
            "user": build_user_payload(user, request),
            **token_payload,
        }, status.HTTP_200_OK

    except Exception as exc:
        logger.exception("Login error")
        return {
            "message": "An error occurred during login",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR



def list_vendors_payload(request: Any) -> list[dict[str, Any]]:
    """Return vendor payloads for admin/vendor views."""
    vendors = Vendor.objects.all().order_by("-created_at")
    vendor = resolve_vendor(request)
    if vendor:
        vendors = vendors.filter(pk=vendor.pk)
    return [build_vendor_payload(vendor, request) for vendor in vendors]


def list_users_payload(request: Any) -> list[dict[str, Any]]:
    """Return user payloads for admin views."""
    users = User.objects.all().order_by("-date_joined")
    return [build_user_payload(user, request) for user in users]


def _seat_label(seat: Seat) -> str:
    """Return a readable seat label for admin booking views."""
    if seat.row_label:
        return f"{seat.row_label}{seat.seat_number}"
    return str(seat.seat_number or "")


def _status_from_payment(payment_status: Optional[str]) -> Optional[str]:
    if not payment_status:
        return None
    status_value = str(payment_status).strip().lower()
    if status_value in {
        PAYMENT_STATUS_SUCCESS.lower(),
        PAYMENT_STATUS_REFUNDED.lower(),
        PAYMENT_STATUS_PARTIALLY_REFUNDED.lower(),
        "paid",
        "completed",
        "confirmed",
    }:
        return "Paid"
    if status_value in {PAYMENT_STATUS_PENDING.lower()}:
        return "Pending"
    if status_value in {PAYMENT_STATUS_FAILED.lower(), "declined"}:
        return "Failed"
    return None


def _refund_label(refund_status: Optional[str]) -> Optional[str]:
    if not refund_status:
        return None
    status_value = str(refund_status).strip().lower()
    if status_value in {REFUND_STATUS_COMPLETED.lower(), "refunded", "success"}:
        return "Refunded"
    if status_value == REFUND_STATUS_PENDING.lower():
        return "Pending"
    if status_value == Refund.Status.FAILED.lower():
        return "Failed"
    return refund_status


def _latest_cancel_request_status(booking: Booking) -> Optional[str]:
    """Return latest cancellation request status from notification metadata."""
    item = (
        Notification.objects.filter(
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=booking.id,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if not item:
        return None
    status_value = str((item.metadata or {}).get("request_status") or "").strip().upper()
    return status_value or None


def _percent_decimal(value: Any, default: Decimal) -> Decimal:
    """Normalize percentage inputs into 0..100 range."""
    parsed = _parse_price_amount(value)
    if parsed is None:
        parsed = default
    if parsed < Decimal("0"):
        parsed = Decimal("0")
    if parsed > Decimal("100"):
        parsed = Decimal("100")
    return _quantize_money(parsed)


def _default_cancellation_policy_payload(
    *,
    vendor: Optional[Vendor] = None,
    screen: Optional[Screen] = None,
) -> dict[str, Any]:
    return {
        "id": None,
        "vendor_id": vendor.id if vendor else None,
        "screen_id": screen.id if screen else None,
        "screen_number": screen.screen_number if screen else None,
        "allow_customer_cancellation": True,
        "is_active": True,
        "refund_percent_2h_plus": float(DEFAULT_REFUND_PERCENT_2H_PLUS),
        "refund_percent_1_to_2h": float(DEFAULT_REFUND_PERCENT_1_TO_2H),
        "refund_percent_less_than_1h": float(DEFAULT_REFUND_PERCENT_LESS_THAN_1H),
        "note": None,
        "is_default": True,
        "source": "SYSTEM_DEFAULT",
        "updated_at": None,
    }


def _serialize_cancellation_policy(policy: VendorCancellationPolicy) -> dict[str, Any]:
    screen = policy.screen
    return {
        "id": policy.id,
        "vendor_id": policy.vendor_id,
        "screen_id": policy.screen_id,
        "screen_number": screen.screen_number if screen else None,
        "allow_customer_cancellation": bool(policy.allow_customer_cancellation),
        "is_active": bool(policy.is_active),
        "refund_percent_2h_plus": float(
            _percent_decimal(policy.refund_percent_2h_plus, DEFAULT_REFUND_PERCENT_2H_PLUS)
        ),
        "refund_percent_1_to_2h": float(
            _percent_decimal(policy.refund_percent_1_to_2h, DEFAULT_REFUND_PERCENT_1_TO_2H)
        ),
        "refund_percent_less_than_1h": float(
            _percent_decimal(
                policy.refund_percent_less_than_1h,
                DEFAULT_REFUND_PERCENT_LESS_THAN_1H,
            )
        ),
        "note": policy.note,
        "is_default": policy.screen_id is None,
        "source": "VENDOR_POLICY",
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def _resolve_cancellation_policy_for_booking(booking: Booking) -> dict[str, Any]:
    """Resolve effective cancellation policy for a booking with hall-level override."""
    showtime = booking.showtime
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    if not vendor:
        payload = _default_cancellation_policy_payload()
        payload["allow_customer_cancellation"] = False
        payload["is_active"] = False
        payload["source"] = "UNSCOPED"
        return payload

    scoped = VendorCancellationPolicy.objects.filter(
        vendor_id=vendor.id,
        is_active=True,
    )
    selected = None
    if screen:
        selected = scoped.filter(screen_id=screen.id).select_related("screen").first()
    if not selected:
        selected = scoped.filter(screen__isnull=True).first()
    if selected:
        payload = _serialize_cancellation_policy(selected)
        if screen and not selected.screen_id:
            payload["screen_id"] = screen.id
            payload["screen_number"] = screen.screen_number
            payload["source"] = "VENDOR_DEFAULT_FALLBACK"
        return payload
    return _default_cancellation_policy_payload(vendor=vendor, screen=screen)


def _booking_amount_for_refund(booking: Booking, latest_payment: Optional[Payment] = None) -> Decimal:
    amount = _quantize_money(booking.total_amount or Decimal("0"))
    if amount <= Decimal("0") and latest_payment:
        amount = _quantize_money(latest_payment.amount or Decimal("0"))
    return amount


def _compute_booking_cancellation_quote(
    booking: Booking,
    latest_payment: Optional[Payment] = None,
) -> dict[str, Any]:
    """Compute cancellation eligibility and refund values from vendor policy + showtime."""
    policy = _resolve_cancellation_policy_for_booking(booking)
    showtime = booking.showtime
    amount = _booking_amount_for_refund(booking, latest_payment=latest_payment)

    if not showtime or not showtime.start_time:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Show time is unavailable.",
            "hours_until_show": None,
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "policy": policy,
        }

    now = timezone.now()
    diff = showtime.start_time - now
    hours_until_show = diff.total_seconds() / 3600

    allow_customer = bool(policy.get("allow_customer_cancellation"))
    if not allow_customer:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Cancellation is disabled by vendor policy.",
            "hours_until_show": round(hours_until_show, 2),
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "policy": policy,
        }

    if hours_until_show <= 0:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Show has already started.",
            "hours_until_show": round(hours_until_show, 2),
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "policy": policy,
        }

    if hours_until_show < 1:
        return {
            "is_cancellable": False,
            "is_refund_available": False,
            "reason": "Cancellation is only allowed at least 1 hour before showtime.",
            "hours_until_show": round(hours_until_show, 2),
            "refund_percent": 0.0,
            "refund_amount": 0.0,
            "cancellation_charge_amount": float(amount),
            "amount_basis": float(amount),
            "policy": policy,
        }

    if hours_until_show >= 2:
        percent = _percent_decimal(
            policy.get("refund_percent_2h_plus"),
            DEFAULT_REFUND_PERCENT_2H_PLUS,
        )
    elif hours_until_show >= 1:
        percent = _percent_decimal(
            policy.get("refund_percent_1_to_2h"),
            DEFAULT_REFUND_PERCENT_1_TO_2H,
        )
    else:
        percent = _percent_decimal(
            policy.get("refund_percent_less_than_1h"),
            DEFAULT_REFUND_PERCENT_LESS_THAN_1H,
        )

    refund_amount = _quantize_money((amount * percent) / Decimal("100"))
    if refund_amount > amount:
        refund_amount = amount
    charge_amount = _quantize_money(amount - refund_amount)

    return {
        "is_cancellable": True,
        "is_refund_available": refund_amount > Decimal("0"),
        "reason": None,
        "hours_until_show": round(hours_until_show, 2),
        "refund_percent": float(percent),
        "refund_amount": float(refund_amount),
        "cancellation_charge_amount": float(charge_amount),
        "amount_basis": float(amount),
        "policy": policy,
    }


def build_booking_payload(booking: Booking) -> dict[str, Any]:
    """Build the admin booking payload for a single booking."""
    from .cancellations import _compute_booking_cancellation_quote
    from .cancellations import _latest_cancel_request_status

    user = booking.user
    showtime = booking.showtime
    movie = getattr(showtime, "movie", None) if showtime else None
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None

    user_name = " ".join(
        [part for part in [user.first_name, user.middle_name, user.last_name] if part]
    ).strip()
    if not user_name:
        user_name = user.email or str(user.id)

    seat_labels = []
    for booking_seat in booking.booking_seats.all():
        if booking_seat.seat:
            seat_labels.append(_seat_label(booking_seat.seat))

    latest_payment = None
    if hasattr(booking, "payments"):
        latest_payment = (
            booking.payments.all().order_by("-payment_date", "-id").first()
        )
    latest_refund = None
    if latest_payment and hasattr(latest_payment, "refunds"):
        latest_refund = (
            latest_payment.refunds.all().order_by("-refund_date", "-id").first()
        )

    payment_status = getattr(latest_payment, "payment_status", None)
    refund_status = getattr(latest_refund, "refund_status", None)
    refund_label = _refund_label(refund_status)

    total_amount = booking.total_amount
    if total_amount is None and latest_payment is not None:
        total_amount = latest_payment.amount
    if total_amount is None:
        seat_prices = [
            seat.seat_price
            for seat in booking.booking_seats.all()
            if seat.seat_price is not None
        ]
        if seat_prices:
            total_amount = sum(seat_prices)
        elif showtime and showtime.price is not None:
            total_amount = showtime.price * max(len(seat_labels), 1)

    cancel_request_status = _latest_cancel_request_status(booking)

    status_label = None
    if refund_label and str(refund_label).lower() == "refunded":
        status_label = "Refunded"
    elif str(booking.booking_status).lower() == "cancelled":
        status_label = "Cancelled"
    elif cancel_request_status == "PENDING":
        status_label = "Cancel Pending"
    else:
        status_label = _status_from_payment(payment_status)
        if not status_label and str(booking.booking_status).lower() in {"confirmed", "paid"}:
            status_label = "Paid"
    if not status_label:
        status_label = "Pending"

    show_time = None
    if showtime and showtime.start_time:
        show_time = showtime.start_time.strftime("%Y-%m-%d %H:%M")

    cancellation_quote = _compute_booking_cancellation_quote(
        booking,
        latest_payment=latest_payment,
    )
    cancellation_quote["request_status"] = cancel_request_status

    fraud_payload = build_fraud_risk_payload(
        score=getattr(booking, "fraud_score", 0),
        signals=getattr(booking, "fraud_signals", []),
        review_threshold=_booking_fraud_review_threshold(),
    )

    return {
        "id": booking.id,
        "userId": user.id,
        "user": user_name,
        "movie": movie.title if movie else None,
        "vendor": vendor.name if vendor else None,
        "showTime": show_time,
        "seats": ", ".join(seat_labels),
        "seatCount": len(seat_labels),
        "total": float(total_amount) if total_amount is not None else None,
        "status": status_label,
        "paymentStatus": payment_status,
        "paymentMethod": getattr(latest_payment, "payment_method", None),
        "paymentAmount": float(getattr(latest_payment, "amount", 0) or 0),
        "refundStatus": refund_label or "N/A",
        "loyaltyPointsRedeemed": int(booking.loyalty_points_redeemed or 0),
        "loyaltyDiscountAmount": float(_quantize_money(booking.loyalty_discount_amount or Decimal("0"))),
        "subscriptionPlanId": booking.subscription_plan_id,
        "subscriptionPlanName": getattr(booking.subscription_plan, "name", None),
        "userSubscriptionId": booking.user_subscription_id,
        "subscriptionDiscountAmount": float(
            _quantize_money(booking.subscription_discount_amount or Decimal("0"))
        ),
        "subscriptionFreeTicketsUsed": int(booking.subscription_free_tickets_used or 0),
        "referralWalletUsedAmount": float(_quantize_money(booking.referral_wallet_used_amount or Decimal("0"))),
        "referralWalletRefundedAmount": float(_quantize_money(booking.referral_wallet_refunded_amount or Decimal("0"))),
        "rewardRedemptionId": booking.reward_redemption_id,
        "fraudScore": int(fraud_payload["score"]),
        "fraudLevel": fraud_payload["level"],
        "fraudSignals": fraud_payload["signals"],
        "requiresManualReview": bool(fraud_payload["requires_manual_review"]),
        "fraudRisk": {
            "score": int(fraud_payload["score"]),
            "level": fraud_payload["level"],
            "signals": fraud_payload["signals"],
            "requiresManualReview": bool(fraud_payload["requires_manual_review"]),
        },
        "sourceIp": getattr(booking, "source_ip", None),
        "cancellation": cancellation_quote,
        "createdAt": booking.booking_date.isoformat() if booking.booking_date else None,
    }


def list_bookings_payload(request: Any) -> list[dict[str, Any]]:
    """Return booking payloads for admin views."""
    bookings = (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .order_by("-booking_date", "-id")
    )
    vendor = resolve_vendor(request)
    if vendor:
        bookings = bookings.filter(showtime__screen__vendor_id=vendor.id)
    return [build_booking_payload(booking) for booking in bookings]


def _serialize_referral_entry(referral: Referral) -> dict[str, Any]:
    referred_user = referral.referred_user
    referrer = referral.referrer

    referred_name = " ".join(
        [
            part
            for part in [
                getattr(referred_user, "first_name", ""),
                getattr(referred_user, "middle_name", ""),
                getattr(referred_user, "last_name", ""),
            ]
            if part
        ]
    ).strip()
    referrer_name = " ".join(
        [
            part
            for part in [
                getattr(referrer, "first_name", ""),
                getattr(referrer, "middle_name", ""),
                getattr(referrer, "last_name", ""),
            ]
            if part
        ]
    ).strip()

    return {
        "id": referral.id,
        "status": referral.status,
        "referral_code": referral.referral_code,
        "referrer_id": referral.referrer_id,
        "referrer_name": referrer_name or getattr(referrer, "email", None),
        "referred_user_id": referral.referred_user_id,
        "referred_user_name": referred_name or getattr(referred_user, "email", None),
        "referred_user_email": getattr(referred_user, "email", None),
        "reward_trigger_booking_id": referral.reward_trigger_booking_id,
        "rejection_reason": referral.rejection_reason,
        "reversal_reason": referral.reversal_reason,
        "rewarded_at": referral.rewarded_at.isoformat() if referral.rewarded_at else None,
        "reversed_at": referral.reversed_at.isoformat() if referral.reversed_at else None,
        "expires_at": referral.expires_at.isoformat() if referral.expires_at else None,
        "created_at": referral.created_at.isoformat() if referral.created_at else None,
        "updated_at": referral.updated_at.isoformat() if referral.updated_at else None,
        "metadata": referral.metadata or {},
    }


def _serialize_referral_wallet_transaction(tx: ReferralTransaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "user_id": tx.user_id,
        "transaction_type": tx.transaction_type,
        "status": tx.status,
        "reason": tx.reason,
        "amount": float(_quantize_money(tx.amount or Decimal("0"))),
        "remaining_amount": float(_quantize_money(tx.remaining_amount or Decimal("0"))),
        "available_at": tx.available_at.isoformat() if tx.available_at else None,
        "referral_id": tx.referral_id,
        "booking_id": tx.booking_id,
        "expires_at": tx.expires_at.isoformat() if tx.expires_at else None,
        "processed_at": tx.processed_at.isoformat() if tx.processed_at else None,
        "created_at": tx.created_at.isoformat() if tx.created_at else None,
        "metadata": tx.metadata or {},
    }


def get_customer_referral_dashboard(request: Any) -> tuple[dict[str, Any], int]:
    """Return referral code, wallet summary, referral stats, and recent activity."""
    user = resolve_customer(request)
    if not user:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    ensure_user_referral_code(user)
    expire_referral_wallet_credits(user_id=user.id)

    wallet = get_referral_wallet_snapshot(user, use_cache=False)
    signup_reward_amount = _referral_signup_reward_amount()
    cap_percent = _referral_wallet_cap_percent()

    sent_queryset = Referral.objects.filter(referrer_id=user.id)
    status_counts = {
        Referral.STATUS_PENDING: 0,
        Referral.STATUS_REWARDED: 0,
        Referral.STATUS_REJECTED: 0,
        Referral.STATUS_REVERSED: 0,
        Referral.STATUS_EXPIRED: 0,
    }
    for row in sent_queryset.values("status").annotate(total=Count("id")):
        key = str(row.get("status") or "").upper()
        status_counts[key] = int(row.get("total") or 0)

    recent_sent = list(
        sent_queryset.select_related("referred_user", "referrer")
        .order_by("-created_at", "-id")[:30]
    )
    received_referral = (
        Referral.objects.select_related("referrer", "referred_user")
        .filter(referred_user_id=user.id)
        .order_by("-created_at", "-id")
        .first()
    )

    recent_transactions = list(
        ReferralTransaction.objects.filter(user_id=user.id)
        .order_by("-created_at", "-id")[:40]
    )

    frontend_base = str(
        getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173") or "http://localhost:5173"
    ).rstrip("/")
    referral_link = f"{frontend_base}/register?ref={user.referral_code}"

    return {
        "referral": {
            "code": user.referral_code,
            "link": referral_link,
            "sent": [_serialize_referral_entry(item) for item in recent_sent],
            "received": _serialize_referral_entry(received_referral) if received_referral else None,
            "summary": {
                "pending": status_counts.get(Referral.STATUS_PENDING, 0),
                "rewarded": status_counts.get(Referral.STATUS_REWARDED, 0),
                "rejected": status_counts.get(Referral.STATUS_REJECTED, 0),
                "reversed": status_counts.get(Referral.STATUS_REVERSED, 0),
                "expired": status_counts.get(Referral.STATUS_EXPIRED, 0),
                "total": sent_queryset.count(),
            },
            "reward_policy": {
                "referrer_reward_amount": float(signup_reward_amount),
                "referred_reward_amount": 0.0,
                "hold_days": _referral_reward_hold_period_days(),
                "expiry_days": _referral_reward_expiry_days(),
                "reward_mode": "SIGNUP_IMMEDIATE",
            },
        },
        "wallet": {
            **wallet,
            "cap_percent": float(cap_percent),
        },
        "transactions": [_serialize_referral_wallet_transaction(item) for item in recent_transactions],
    }, status.HTTP_200_OK


def list_customer_referral_wallet_transactions(request: Any) -> tuple[dict[str, Any], int]:
    """List referral wallet transactions for the authenticated customer."""
    user = resolve_customer(request)
    if not user:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    expire_referral_wallet_credits(user_id=user.id)

    limit = _coerce_int(coalesce(request.query_params, "limit")) or 50
    offset = _coerce_int(coalesce(request.query_params, "offset")) or 0
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))

    queryset = ReferralTransaction.objects.filter(user_id=user.id).order_by("-created_at", "-id")
    total = queryset.count()
    rows = list(queryset[offset: offset + limit])

    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "transactions": [_serialize_referral_wallet_transaction(item) for item in rows],
    }, status.HTTP_200_OK


def preview_customer_referral_wallet_checkout(request: Any) -> tuple[dict[str, Any], int]:
    """Preview how much referral wallet credit can be applied to checkout."""
    user = resolve_customer(request)
    if not user:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    subtotal = _parse_price_amount(
        coalesce(payload, "subtotal", "ticket_total", "ticketTotal", "amount")
    )
    if subtotal is None or subtotal <= Decimal("0"):
        return {"message": "A valid subtotal amount is required."}, status.HTTP_400_BAD_REQUEST

    use_wallet = parse_bool(
        coalesce(payload, "use_referral_wallet", "useReferralWallet", "enabled"),
        default=True,
    )
    requested_amount = _parse_price_amount(
        coalesce(
            payload,
            "requested_amount",
            "requestedAmount",
            "wallet_amount",
            "walletAmount",
            "amount_to_use",
            "amountToUse",
        )
    )
    if not use_wallet:
        requested_amount = Decimal("0.00")

    preview = preview_referral_wallet_usage_for_user(
        user,
        subtotal=subtotal,
        requested_amount=requested_amount,
    )
    return {"preview": preview}, status.HTTP_200_OK


def _serialize_referral_policy(policy: ReferralPolicy) -> dict[str, Any]:
    return {
        "referrer_reward_amount": float(_quantize_money(policy.referrer_reward_amount)),
        "referred_reward_amount": float(_quantize_money(policy.referred_reward_amount)),
        "reward_hold_period_days": int(policy.reward_hold_period_days or 0),
        "reward_expiry_days": int(policy.reward_expiry_days or 0),
        "wallet_cap_percent": float(_quantize_money(policy.wallet_cap_percent)),
        "max_signups_per_ip_per_day": int(policy.max_signups_per_ip_per_day or 0),
        "max_signups_per_device_per_day": int(policy.max_signups_per_device_per_day or 0),
        "auto_approve_rewards": bool(policy.auto_approve_rewards),
        "is_active": bool(policy.is_active),
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else None,
    }


def get_admin_referral_control_payload(request: Any) -> tuple[dict[str, Any], int]:
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    policy = _get_referral_policy()
    status_filter = str(coalesce(request.query_params, "status") or "").strip().upper()
    limit = _coerce_int(coalesce(request.query_params, "limit")) or 100
    limit = max(1, min(300, int(limit)))

    referrals_qs = Referral.objects.select_related("referrer", "referred_user", "reward_trigger_booking").order_by(
        "-created_at", "-id"
    )
    if status_filter:
        referrals_qs = referrals_qs.filter(status=status_filter)

    referrals = list(referrals_qs[:limit])
    status_counts = {
        Referral.STATUS_PENDING: 0,
        Referral.STATUS_REWARDED: 0,
        Referral.STATUS_REJECTED: 0,
        Referral.STATUS_REVERSED: 0,
        Referral.STATUS_EXPIRED: 0,
    }
    for row in Referral.objects.values("status").annotate(total=Count("id")):
        key = str(row.get("status") or "").upper()
        status_counts[key] = int(row.get("total") or 0)

    wallet_totals = ReferralWallet.objects.aggregate(
        total_balance=Sum("balance"),
        total_credited=Sum("total_credited"),
        total_debited=Sum("total_debited"),
        total_expired=Sum("total_expired"),
    )

    return {
        "policy": _serialize_referral_policy(policy),
        "summary": {
            "pending": status_counts.get(Referral.STATUS_PENDING, 0),
            "rewarded": status_counts.get(Referral.STATUS_REWARDED, 0),
            "rejected": status_counts.get(Referral.STATUS_REJECTED, 0),
            "reversed": status_counts.get(Referral.STATUS_REVERSED, 0),
            "expired": status_counts.get(Referral.STATUS_EXPIRED, 0),
            "total": int(sum(status_counts.values())),
            "wallet_total_balance": float(_quantize_money(wallet_totals.get("total_balance") or Decimal("0"))),
            "wallet_total_credited": float(_quantize_money(wallet_totals.get("total_credited") or Decimal("0"))),
            "wallet_total_debited": float(_quantize_money(wallet_totals.get("total_debited") or Decimal("0"))),
            "wallet_total_expired": float(_quantize_money(wallet_totals.get("total_expired") or Decimal("0"))),
        },
        "referrals": [_serialize_referral_entry(item) for item in referrals],
    }, status.HTTP_200_OK


def update_admin_referral_policy(request: Any) -> tuple[dict[str, Any], int]:
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    policy = _get_referral_policy()

    if "referrer_reward_amount" in payload:
        value = _parse_price_amount(payload.get("referrer_reward_amount"))
        if value is None or value < Decimal("0"):
            return {"message": "referrer_reward_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        policy.referrer_reward_amount = value

    if "referred_reward_amount" in payload:
        value = _parse_price_amount(payload.get("referred_reward_amount"))
        if value is None or value < Decimal("0"):
            return {"message": "referred_reward_amount must be a non-negative number."}, status.HTTP_400_BAD_REQUEST
        policy.referred_reward_amount = value

    if "reward_hold_period_days" in payload:
        value = _coerce_int(payload.get("reward_hold_period_days"))
        if value is None or value < 0:
            return {"message": "reward_hold_period_days must be zero or more."}, status.HTTP_400_BAD_REQUEST
        policy.reward_hold_period_days = value

    if "reward_expiry_days" in payload:
        value = _coerce_int(payload.get("reward_expiry_days"))
        if value is None or value < 1:
            return {"message": "reward_expiry_days must be at least 1."}, status.HTTP_400_BAD_REQUEST
        policy.reward_expiry_days = value

    if "wallet_cap_percent" in payload:
        value = _parse_price_amount(payload.get("wallet_cap_percent"))
        if value is None or value < Decimal("0") or value > Decimal("100"):
            return {"message": "wallet_cap_percent must be between 0 and 100."}, status.HTTP_400_BAD_REQUEST
        policy.wallet_cap_percent = value

    if "max_signups_per_ip_per_day" in payload:
        value = _coerce_int(payload.get("max_signups_per_ip_per_day"))
        if value is None or value < 1:
            return {"message": "max_signups_per_ip_per_day must be at least 1."}, status.HTTP_400_BAD_REQUEST
        policy.max_signups_per_ip_per_day = value

    if "max_signups_per_device_per_day" in payload:
        value = _coerce_int(payload.get("max_signups_per_device_per_day"))
        if value is None or value < 1:
            return {"message": "max_signups_per_device_per_day must be at least 1."}, status.HTTP_400_BAD_REQUEST
        policy.max_signups_per_device_per_day = value

    if "auto_approve_rewards" in payload:
        policy.auto_approve_rewards = parse_bool(payload.get("auto_approve_rewards"), default=policy.auto_approve_rewards)

    if "is_active" in payload:
        policy.is_active = parse_bool(payload.get("is_active"), default=policy.is_active)

    policy.save()
    return {
        "message": "Referral policy updated.",
        "policy": _serialize_referral_policy(policy),
    }, status.HTTP_200_OK


def update_admin_referral_status(request: Any, referral: Referral) -> tuple[dict[str, Any], int]:
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    action = str(coalesce(payload, "action", "status") or "").strip().upper()
    if action not in {"APPROVE", "REJECT", "REVERSE", "PENDING"}:
        return {
            "message": "action must be one of APPROVE, REJECT, REVERSE, or PENDING.",
        }, status.HTTP_400_BAD_REQUEST

    reason = str(coalesce(payload, "reason", "rejection_reason", "reversal_reason") or "").strip()

    with transaction.atomic():
        locked_referral = Referral.objects.select_for_update().filter(id=referral.id).first()
        if not locked_referral:
            return {"message": "Referral not found."}, status.HTTP_404_NOT_FOUND

        metadata = dict(locked_referral.metadata or {})
        now_iso = timezone.now().isoformat()

        if action == "APPROVE":
            metadata["admin_approved"] = True
            metadata["admin_approved_at"] = now_iso
            metadata["admin_action"] = "APPROVE"
            if reason:
                metadata["admin_note"] = reason
            locked_referral.metadata = metadata
            locked_referral.save(update_fields=["metadata", "updated_at"])

        elif action == "REJECT":
            locked_referral.status = Referral.STATUS_REJECTED
            locked_referral.rejection_reason = reason or "Rejected by admin."
            metadata["admin_action"] = "REJECT"
            metadata["admin_action_at"] = now_iso
            locked_referral.metadata = metadata
            locked_referral.save(
                update_fields=["status", "rejection_reason", "metadata", "updated_at"]
            )

        elif action == "REVERSE":
            if locked_referral.status == Referral.STATUS_REWARDED and locked_referral.reward_trigger_booking_id:
                reverse_referral_effects_for_booking(
                    locked_referral.reward_trigger_booking,
                    reason=reason or "Referral reversed by admin.",
                )
                locked_referral.refresh_from_db()
            locked_referral.status = Referral.STATUS_REVERSED
            locked_referral.reversal_reason = reason or "Reversed by admin."
            locked_referral.reversed_at = timezone.now()
            metadata["admin_action"] = "REVERSE"
            metadata["admin_action_at"] = now_iso
            locked_referral.metadata = metadata
            locked_referral.save(
                update_fields=["status", "reversal_reason", "reversed_at", "metadata", "updated_at"]
            )

        else:
            locked_referral.status = Referral.STATUS_PENDING
            locked_referral.rejection_reason = None
            locked_referral.reversal_reason = None
            metadata["admin_action"] = "PENDING"
            metadata["admin_action_at"] = now_iso
            locked_referral.metadata = metadata
            locked_referral.save(
                update_fields=[
                    "status",
                    "rejection_reason",
                    "reversal_reason",
                    "metadata",
                    "updated_at",
                ]
            )

    return {
        "message": "Referral updated.",
        "referral": _serialize_referral_entry(locked_referral),
    }, status.HTTP_200_OK


def _get_booking_or_none(booking_id: int) -> Optional[Booking]:
    return (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(pk=booking_id)
        .first()
    )


def _get_vendor_booking_or_none(request: Any, booking_id: int) -> Optional[Booking]:
    """Return a booking only when it belongs to the authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return None
    return (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(pk=booking_id, showtime__screen__vendor_id=vendor.id)
        .first()
    )


def list_customer_bookings_payload(request: Any) -> list[dict[str, Any]]:
    """Return booking payloads for the authenticated customer only."""
    customer = resolve_customer(request)
    if not customer:
        return []

    enqueue_stale_pending_cleanup_job(
        metadata={
            "source": "list_customer_bookings_payload",
            "user_id": customer.id,
        }
    )

    bookings = (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(user_id=customer.id)
        .order_by("-booking_date", "-id")
    )
    return [build_booking_payload(booking) for booking in bookings]


def _get_customer_booking_or_none(request: Any, booking_id: int) -> Optional[Booking]:
    """Return one booking only if it belongs to the authenticated customer."""
    customer = resolve_customer(request)
    if not customer:
        return None

    enqueue_stale_pending_cleanup_job(
        metadata={
            "source": "get_customer_booking",
            "user_id": customer.id,
        }
    )

    return (
        Booking.objects.select_related(
            "user",
            "showtime__movie",
            "showtime__screen__vendor",
        )
        .prefetch_related("booking_seats__seat", "payments__refunds")
        .filter(pk=booking_id, user_id=customer.id)
        .first()
    )


def build_booking_detail_payload(booking: Booking) -> dict[str, Any]:
    """Build a detailed booking payload for admin views."""
    base = build_booking_payload(booking)
    payments = []
    for payment in booking.payments.all().order_by("-payment_date", "-id"):
        refunds = []
        for refund in payment.refunds.all().order_by("-refund_date", "-id"):
            refunds.append(
                {
                    "id": refund.id,
                    "amount": float(refund.refund_amount),
                    "status": refund.refund_status,
                    "reason": refund.refund_reason,
                    "refundedAt": refund.refund_date.isoformat()
                    if refund.refund_date
                    else None,
                }
            )
        payments.append(
            {
                "id": payment.id,
                "method": payment.payment_method,
                "status": payment.payment_status,
                "amount": float(payment.amount),
                "paidAt": payment.payment_date.isoformat()
                if payment.payment_date
                else None,
                "refunds": refunds,
            }
        )

    seats = []
    for booking_seat in booking.booking_seats.all():
        seat = booking_seat.seat
        if not seat:
            continue
        seats.append(
            {
                "id": seat.id,
                "label": _seat_label(seat),
                "row": seat.row_label,
                "number": seat.seat_number,
                "type": seat.seat_type,
                "price": float(booking_seat.seat_price)
                if booking_seat.seat_price is not None
                else None,
            }
        )

    base.update(
        {
            "userEmail": booking.user.email if booking.user else None,
            "payments": payments,
            "seatsDetail": seats,
        }
    )
    return base


def _release_booking_seats(booking: Booking) -> None:
    """Release seat availability for a booking if no other active booking holds it."""
    showtime = booking.showtime
    if not showtime:
        return
    for booking_seat in booking.booking_seats.select_related("seat"):
        seat = booking_seat.seat
        if not seat:
            continue
        still_sold = BookingSeat.objects.filter(
            seat=seat,
            booking__showtime=showtime,
        ).exclude(
            booking=booking
        ).exclude(
            booking__booking_status__iexact="Cancelled"
        ).exists()
        if still_sold:
            continue
        SeatAvailability.objects.filter(seat=seat, showtime=showtime).update(
            seat_status=SEAT_STATUS_AVAILABLE,
            locked_until=None,
        )


def cleanup_expired_pending_bookings(
    *,
    user_id: Optional[int] = None,
    ttl_seconds: Optional[int] = None,
) -> int:
    """Cancel stale pending eSewa bookings and release held seats.

    This keeps booking history accurate (Pending -> Cancelled) and frees seats if
    a payment was not completed within the hold window.
    """
    configured_ttl = ttl_seconds if ttl_seconds is not None else getattr(
        settings,
        "ESEWA_PENDING_TTL_SECONDS",
        1800,
    )
    try:
        hold_seconds = int(configured_ttl)
    except (TypeError, ValueError):
        hold_seconds = 1800
    hold_seconds = max(60, hold_seconds)

    cutoff = timezone.now() - timedelta(seconds=hold_seconds)
    pending_payments = Payment.objects.select_related("booking").filter(
        payment_status__iexact=PAYMENT_STATUS_PENDING,
        payment_method__startswith=ESEWA_PAYMENT_METHOD_PREFIX,
        payment_date__lte=cutoff,
        booking__booking_status__iexact=BOOKING_STATUS_PENDING,
    )
    if user_id:
        pending_payments = pending_payments.filter(booking__user_id=user_id)

    expired = 0
    processed_booking_ids: set[int] = set()
    for payment in pending_payments.order_by("payment_date", "id"):
        booking = payment.booking
        if not booking or booking.id in processed_booking_ids:
            continue

        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().filter(pk=booking.id).first()
            if not locked_booking:
                continue
            if str(locked_booking.booking_status).strip().lower() != BOOKING_STATUS_PENDING.lower():
                continue

            seat_count = BookingSeat.objects.filter(booking=locked_booking).count()
            transaction_uuid = _transaction_uuid_from_payment_method(payment.payment_method)

            _release_booking_seats(locked_booking)
            BookingSeat.objects.filter(booking=locked_booking).delete()
            locked_booking.booking_status = BOOKING_STATUS_CANCELLED
            locked_booking.save(update_fields=["booking_status"])
            Payment.objects.filter(
                booking=locked_booking,
                payment_status__iexact=PAYMENT_STATUS_PENDING,
            ).update(payment_status=PAYMENT_STATUS_FAILED)

            _record_booking_dropoff_event(
                stage=BookingDropoffEvent.STAGE_PAYMENT,
                reason=BookingDropoffEvent.REASON_PAYMENT_EXPIRED,
                seat_count=seat_count,
                booking=locked_booking,
                payment=payment,
                transaction_uuid=transaction_uuid,
                metadata={
                    "expired_by": "cleanup_expired_pending_bookings",
                    "ttl_seconds": hold_seconds,
                },
                dedupe_by_transaction=True,
            )

        processed_booking_ids.add(booking.id)
        expired += 1

    return expired


def cleanup_stale_seat_locks(*, showtime_id: Optional[int] = None) -> int:
    """Release stale seat holds that have passed lock expiry."""
    now = timezone.now()
    queryset = SeatAvailability.objects.filter(
        locked_until__isnull=False,
        locked_until__lte=now,
    ).exclude(
        seat_status__in=[SEAT_STATUS_BOOKED, SEAT_STATUS_SOLD]
    )
    if showtime_id:
        queryset = queryset.filter(showtime_id=showtime_id)
    return int(queryset.update(locked_until=None) or 0)


def admin_cancel_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Cancel a booking and release seats."""
    if str(booking.booking_status).strip().upper() == BOOKING_STATUS_CANCELLED:
        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    payload = get_payload(request)
    reason = str(coalesce(payload, "reason", "cancellation_reason") or "").strip() or "Cancelled by admin"

    with transaction.atomic():
        booking.booking_status = BOOKING_STATUS_CANCELLED
        booking.save(update_fields=["booking_status"])
        _release_booking_seats(booking)
        loyalty.reverse_booking_points(booking, reason=reason)
        subscription.reverse_booking_subscription_effects(booking, reason=reason)
        reverse_referral_effects_for_booking(booking, reason=reason)

    refreshed = _get_booking_or_none(booking.id) or booking
    _notify_customer_booking_cancelled(
        refreshed,
        actor_label="admin",
        reason=reason,
    )

    return {
        "message": "Booking cancelled",
        "booking": build_booking_payload(refreshed),
    }, status.HTTP_200_OK


def _get_booking_vendor(booking: Booking) -> Optional[Vendor]:
    showtime = booking.showtime if booking else None
    screen = getattr(showtime, "screen", None) if showtime else None
    vendor = getattr(screen, "vendor", None) if screen else None
    return vendor


def _find_pending_cancel_request_notification(
    booking: Booking,
    vendor: Vendor,
) -> Optional[Notification]:
    pending = (
        Notification.objects.filter(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=vendor.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=booking.id,
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if not pending:
        return None
    status_value = str((pending.metadata or {}).get("request_status") or "").upper()
    return pending if status_value in {"", "PENDING"} else None


def _close_cancel_request_notifications(
    booking: Booking,
    *,
    resolved_by: str,
    resolved_status: str,
) -> None:
    """Mark pending vendor cancel-request notifications as resolved."""
    rows = Notification.objects.filter(
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        metadata__booking_id=booking.id,
        metadata__request_status="PENDING",
    )
    for item in rows:
        metadata = dict(item.metadata or {})
        metadata["request_status"] = resolved_status
        metadata["resolved_by"] = resolved_by
        metadata["resolved_at"] = timezone.now().isoformat()
        item.metadata = metadata
        item.save(update_fields=["metadata"])


def _notify_customer_cancel_request_rejected(
    booking: Booking,
    *,
    resolved_by: str,
    reason: Optional[str],
) -> None:
    customer = booking.user
    if not customer:
        return

    pending = (
        Notification.objects.filter(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=customer.id,
            event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
            metadata__booking_id=booking.id,
        )
        .order_by("-created_at", "-id")
        .first()
    )

    message = f"Your cancellation request for booking #{booking.id} was rejected by the vendor."
    if reason:
        message = (
            f"Your cancellation request for booking #{booking.id} was rejected by the vendor. "
            f"Reason: {reason}."
        )

    if pending:
        metadata = dict(pending.metadata or {})
        metadata.update(
            {
                "request_status": "REJECTED",
                "resolved_by": resolved_by,
                "resolved_reason": reason,
                "resolved_at": timezone.now().isoformat(),
            }
        )
        pending.title = "Cancellation request rejected"
        pending.message = message
        pending.metadata = metadata
        pending.is_read = False
        pending.read_at = None
        pending.save(update_fields=["title", "message", "metadata", "is_read", "read_at"])
        return

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "request_status": "REJECTED",
            "resolved_by": resolved_by,
            "resolved_reason": reason,
        }
    )
    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        title="Cancellation request rejected",
        message=message,
        metadata=metadata,
        send_email_too=True,
    )


def _notify_customer_cancel_request_submitted(
    booking: Booking,
    *,
    quote: dict[str, Any],
    request_id: int,
) -> None:
    customer = booking.user
    if not customer:
        return

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "request_id": request_id,
            "request_status": "PENDING",
            "request_type": "CANCEL_AND_REFUND",
            "refund_preview": {
                "is_refund_available": bool(quote.get("is_refund_available")),
                "refund_percent": float(quote.get("refund_percent") or 0),
                "refund_amount": float(quote.get("refund_amount") or 0),
                "cancellation_charge_amount": float(quote.get("cancellation_charge_amount") or 0),
                "hours_until_show": quote.get("hours_until_show"),
            },
            "policy": quote.get("policy") or {},
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        title="Cancellation request submitted",
        message=(
            f"Your cancellation request for booking #{booking.id} was sent to the cinema. "
            "You will be notified once the vendor approves refund."
        ),
        metadata=metadata,
        send_email_too=True,
    )


def _notify_customer_booking_cancelled(
    booking: Booking,
    *,
    actor_label: str,
    reason: Optional[str],
) -> None:
    customer = booking.user
    if not customer:
        return

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "processed_by": actor_label,
            "processed_reason": reason,
            "refund_processed": {
                "refund_amount": 0.0,
                "refund_percent": 0.0,
                "cancellation_charge_amount": float(metadata.get("amount_basis") or 0),
                "hours_until_show": None,
                "is_refund_available": False,
            },
        }
    )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=Notification.EVENT_BOOKING_CANCELLED,
        title="Booking cancelled",
        message=f"Your booking #{booking.id} has been cancelled.",
        metadata=metadata,
        send_email_too=True,
    )


def _notify_vendor_cancel_request(
    booking: Booking,
    *,
    vendor: Vendor,
    quote: dict[str, Any],
    reason: Optional[str],
) -> Notification:
    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "request_status": "PENDING",
            "request_type": "CANCEL_AND_REFUND",
            "requested_by": "customer",
            "requested_reason": reason,
            "refund_preview": {
                "is_refund_available": bool(quote.get("is_refund_available")),
                "refund_percent": float(quote.get("refund_percent") or 0),
                "refund_amount": float(quote.get("refund_amount") or 0),
                "cancellation_charge_amount": float(quote.get("cancellation_charge_amount") or 0),
                "hours_until_show": quote.get("hours_until_show"),
            },
            "policy": quote.get("policy") or {},
        }
    )

    return _create_notification(
        recipient_role=Notification.ROLE_VENDOR,
        recipient_id=vendor.id,
        recipient_email=vendor.email,
        event_type=Notification.EVENT_BOOKING_CANCEL_REQUEST,
        title="Refund request pending approval",
        message=(
            f"Customer requested cancellation/refund for booking #{booking.id}. "
            "Review and process manually from vendor bookings."
        ),
        metadata=metadata,
        send_email_too=True,
    )


def _notify_customer_refund_result(
    booking: Booking,
    *,
    quote: dict[str, Any],
    refund_amount: Decimal,
    actor_label: str,
    reason: Optional[str],
) -> None:
    customer = booking.user
    if not customer:
        return

    refunded = _quantize_money(refund_amount or Decimal("0"))
    charge_amount = _quantize_money((Decimal(str(quote.get("amount_basis") or 0)) - refunded))
    if charge_amount < Decimal("0"):
        charge_amount = Decimal("0")

    metadata = _build_booking_notification_metadata(booking, include_booking_detail=True)
    metadata.update(
        {
            "processed_by": actor_label,
            "processed_reason": reason,
            "refund_processed": {
                "refund_amount": float(refunded),
                "refund_percent": float(quote.get("refund_percent") or 0),
                "cancellation_charge_amount": float(charge_amount),
                "hours_until_show": quote.get("hours_until_show"),
                "is_refund_available": bool(refunded > Decimal("0")),
            },
            "policy": quote.get("policy") or {},
        }
    )

    if refunded > Decimal("0"):
        event_type = Notification.EVENT_REFUND_PROCESSED
        title = "Refund processed successfully"
        message = (
            f"Your booking #{booking.id} has been cancelled and refund of NPR {refunded} was processed."
        )
    else:
        event_type = Notification.EVENT_BOOKING_CANCELLED
        title = "Booking cancelled"
        message = (
            f"Your booking #{booking.id} has been cancelled. No refund is applicable under current policy."
        )

    _create_notification(
        recipient_role=Notification.ROLE_CUSTOMER,
        recipient_id=customer.id,
        recipient_email=customer.email,
        event_type=event_type,
        title=title,
        message=message,
        metadata=metadata,
        send_email_too=True,
    )


def _apply_booking_cancellation_with_policy(
    request: Any,
    booking: Booking,
    *,
    actor_label: str,
    require_policy_eligibility: bool,
    require_payment_for_refund: bool = False,
    close_pending_cancel_requests: bool = False,
) -> tuple[dict[str, Any], int]:
    """Cancel booking and apply refund according to effective vendor policy."""
    latest_payment = booking.payments.all().order_by("-payment_date", "-id").first()

    if str(booking.booking_status).lower() == "cancelled":
        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    quote = _compute_booking_cancellation_quote(booking, latest_payment=latest_payment)
    if require_policy_eligibility and not quote.get("is_cancellable"):
        return {
            "message": str(quote.get("reason") or "Cancellation is not allowed for this booking."),
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    reason_value = str(
        coalesce(get_payload(request), "reason", "refund_reason", "cancellation_reason") or ""
    ).strip()
    reason = reason_value or f"Cancelled by {actor_label}"
    refund_amount = _quantize_money(quote.get("refund_amount") or Decimal("0"))

    with transaction.atomic():
        created_refund: Optional[Refund] = None
        locked_booking = Booking.objects.select_for_update().filter(pk=booking.id).first()
        if not locked_booking:
            return {"message": "Booking not found"}, status.HTTP_404_NOT_FOUND
        if str(locked_booking.booking_status).lower() == "cancelled":
            return {
                "message": "Booking already cancelled",
                "booking": build_booking_payload(locked_booking),
            }, status.HTTP_200_OK

        locked_payment = (
            Payment.objects.select_for_update()
            .filter(booking_id=locked_booking.id)
            .order_by("-payment_date", "-id")
            .first()
        )
        if require_payment_for_refund and not locked_payment:
            return {
                "message": "Payment record not found for booking.",
                "booking": build_booking_payload(locked_booking),
            }, status.HTTP_404_NOT_FOUND

        if locked_payment:
            locked_refund = (
                Refund.objects.select_for_update()
                .filter(payment_id=locked_payment.id)
                .order_by("-refund_date", "-id")
                .first()
            )
            if locked_refund and str(locked_refund.refund_status).strip().upper() == REFUND_STATUS_COMPLETED:
                refund_amount = Decimal("0")
            elif refund_amount > Decimal("0"):
                created_refund = Refund.objects.create(
                    payment=locked_payment,
                    refund_amount=refund_amount,
                    refund_reason=reason,
                    refund_status=REFUND_STATUS_COMPLETED,
                )
                refund_vendor = None
                if locked_booking.showtime and locked_booking.showtime.screen:
                    refund_vendor = locked_booking.showtime.screen.vendor
                if refund_vendor:
                    RefundLedger.objects.create(
                        payment=locked_payment,
                        refund=created_refund,
                        booking=locked_booking,
                        vendor=refund_vendor,
                        status=RefundLedger.STATUS_COMPLETED,
                        amount=refund_amount,
                        gross_amount=_quantize_money(locked_payment.amount or Decimal("0")),
                        refund_reason=reason,
                        metadata={"source": "booking_refund"},
                    )
                full_amount = _quantize_money(locked_payment.amount or Decimal("0"))
                if refund_amount >= full_amount:
                    locked_payment.payment_status = PAYMENT_STATUS_REFUNDED
                else:
                    locked_payment.payment_status = PAYMENT_STATUS_PARTIALLY_REFUNDED
                locked_payment.save(update_fields=["payment_status"])

        locked_booking.booking_status = BOOKING_STATUS_CANCELLED
        locked_booking.save(update_fields=["booking_status"])
        _release_booking_seats(locked_booking)
        loyalty.reverse_booking_points(locked_booking, reason=reason)
        subscription.reverse_booking_subscription_effects(locked_booking, reason=reason)
        reverse_referral_effects_for_booking(locked_booking, reason=reason)

        if close_pending_cancel_requests:
            _close_cancel_request_notifications(
                locked_booking,
                resolved_by=actor_label,
                resolved_status="APPROVED",
            )

        if refund_amount > Decimal("0") and created_refund:
            _credit_user_wallet_for_booking_refund(
                booking=locked_booking,
                amount=refund_amount,
                refund=created_refund,
                reason=reason,
                source=f"{actor_label}_booking_refund",
            )
            _reverse_vendor_booking_earning(locked_booking, reason=reason)

    refreshed = _get_booking_or_none(booking.id) or booking
    _notify_customer_refund_result(
        refreshed,
        quote=quote,
        refund_amount=refund_amount,
        actor_label=actor_label,
        reason=reason,
    )

    message = "Booking cancelled"
    if refund_amount > Decimal("0"):
        message = "Booking cancelled and refund processed"
    elif quote.get("is_cancellable") and not quote.get("is_refund_available"):
        message = "Booking cancelled. Refund not available for current policy window"
    return {
        "message": message,
        "booking": build_booking_payload(refreshed),
        "cancellation": quote,
    }, status.HTTP_200_OK


def customer_cancel_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Submit customer cancellation/refund request for vendor approval."""
    if str(booking.booking_status).lower() == "cancelled":
        return {
            "message": "Booking already cancelled",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    quote = _compute_booking_cancellation_quote(booking, latest_payment=_get_latest_payment_for_booking(booking))
    showtime = booking.showtime
    if not showtime or not showtime.start_time:
        return {
            "message": "Show time is unavailable.",
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST
    if not quote.get("is_cancellable"):
        return {
            "message": str(quote.get("reason") or "Cancellation is not allowed for this booking."),
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    vendor = _get_booking_vendor(booking)
    if not vendor:
        return {"message": "Vendor not found for booking."}, status.HTTP_400_BAD_REQUEST

    payload = get_payload(request)
    reason = str(coalesce(payload, "reason", "refund_reason", "cancellation_reason") or "").strip() or None

    existing = _find_pending_cancel_request_notification(booking, vendor)
    if existing:
        metadata = dict(existing.metadata or {})
        metadata["request_status"] = "PENDING"
        metadata["reminded_at"] = timezone.now().isoformat()
        if reason:
            metadata["requested_reason"] = reason
        existing.metadata = metadata

        update_fields = ["metadata"]
        if bool(existing.is_read):
            existing.is_read = False
            existing.read_at = None
            update_fields.extend(["is_read", "read_at"])
        existing.save(update_fields=update_fields)

        return {
            "message": "Cancellation request is already pending vendor approval.",
            "request_id": existing.id,
            "cancellation": quote,
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    vendor_notification = _notify_vendor_cancel_request(
        booking,
        vendor=vendor,
        quote=quote,
        reason=reason,
    )
    _notify_customer_cancel_request_submitted(
        booking,
        quote=quote,
        request_id=vendor_notification.id,
    )

    return {
        "message": "Cancellation request submitted. Vendor will review and process refund manually.",
        "request_id": vendor_notification.id,
        "cancellation": quote,
        "booking": build_booking_payload(booking),
    }, status.HTTP_202_ACCEPTED


def vendor_cancel_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Resolve a vendor booking cancellation request."""
    vendor = _get_booking_vendor(booking)
    if not vendor:
        return {"message": "Vendor not found for booking."}, status.HTTP_400_BAD_REQUEST

    payload = get_payload(request)
    action = str(coalesce(payload, "action", "decision") or "APPROVE").strip().upper()
    reason = str(coalesce(payload, "reason", "refund_reason", "cancellation_reason") or "").strip() or None

    pending_request = _find_pending_cancel_request_notification(booking, vendor)
    if not pending_request:
        return {
            "message": "No pending cancellation request found for this booking.",
            "booking": build_booking_payload(booking),
        }, status.HTTP_400_BAD_REQUEST

    if action == "REJECT":
        _close_cancel_request_notifications(
            booking,
            resolved_by="vendor",
            resolved_status="REJECTED",
        )
        _notify_customer_cancel_request_rejected(
            booking,
            resolved_by="vendor",
            reason=reason,
        )
        return {
            "message": "Cancellation request rejected.",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    return _apply_booking_cancellation_with_policy(
        request,
        booking,
        actor_label="vendor",
        require_policy_eligibility=True,
        require_payment_for_refund=False,
        close_pending_cancel_requests=True,
    )


def vendor_refund_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Vendor manual refund action; releases seats only after refund processing."""
    return _apply_booking_cancellation_with_policy(
        request,
        booking,
        actor_label="vendor",
        require_policy_eligibility=False,
        require_payment_for_refund=True,
        close_pending_cancel_requests=True,
    )


def admin_refund_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Refund a booking and release seats."""
    latest_payment = booking.payments.all().order_by("-payment_date", "-id").first()
    if not latest_payment:
        return {"message": "Payment record not found for booking."}, status.HTTP_404_NOT_FOUND

    latest_refund = latest_payment.refunds.all().order_by("-refund_date", "-id").first()
    if latest_refund and str(latest_refund.refund_status).strip().upper() == REFUND_STATUS_COMPLETED:
        return {
            "message": "Booking already refunded",
            "booking": build_booking_payload(booking),
        }, status.HTTP_200_OK

    payload = get_payload(request)
    reason = str(payload.get("reason") or payload.get("refund_reason") or "").strip() or None
    amount_value = payload.get("amount") or payload.get("refund_amount")
    try:
        amount = float(amount_value) if amount_value is not None else float(latest_payment.amount)
    except (TypeError, ValueError):
        amount = float(latest_payment.amount)
    refund_amount = _quantize_money(Decimal(str(amount)))
    basis_amount = _quantize_money(Decimal(str(latest_payment.amount or 0)))
    actor_reason = reason or "Admin refund"

    with transaction.atomic():
        created_refund = Refund.objects.create(
            payment=latest_payment,
            refund_amount=refund_amount,
            refund_reason=reason,
            refund_status=REFUND_STATUS_COMPLETED,
        )
        refund_vendor = None
        if booking.showtime and booking.showtime.screen:
            refund_vendor = booking.showtime.screen.vendor
        if refund_vendor:
            RefundLedger.objects.create(
                payment=latest_payment,
                refund=created_refund,
                booking=booking,
                vendor=refund_vendor,
                status=RefundLedger.STATUS_COMPLETED,
                amount=refund_amount,
                gross_amount=basis_amount,
                refund_reason=reason,
                metadata={"source": "admin_booking_refund"},
            )
        latest_payment.payment_status = PAYMENT_STATUS_REFUNDED
        latest_payment.save(update_fields=["payment_status"])
        booking.booking_status = BOOKING_STATUS_CANCELLED
        booking.save(update_fields=["booking_status"])
        _release_booking_seats(booking)
        loyalty.reverse_booking_points(booking, reason=actor_reason)
        subscription.reverse_booking_subscription_effects(booking, reason=actor_reason)
        reverse_referral_effects_for_booking(booking, reason=actor_reason)
        if refund_amount > Decimal("0"):
            _credit_user_wallet_for_booking_refund(
                booking=booking,
                amount=refund_amount,
                refund=created_refund,
                reason=actor_reason,
                source="admin_booking_refund",
            )
            _reverse_vendor_booking_earning(booking, reason=actor_reason)

    refreshed = _get_booking_or_none(booking.id) or booking
    _notify_customer_refund_result(
        refreshed,
        quote={
            "amount_basis": float(basis_amount),
            "refund_percent": 0,
            "hours_until_show": None,
            "policy": {"source": "admin_manual_refund"},
        },
        refund_amount=refund_amount,
        actor_label="admin",
        reason=actor_reason,
    )

    return {
        "message": "Booking refunded",
        "booking": build_booking_payload(refreshed),
    }, status.HTTP_200_OK


def admin_delete_booking(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Delete a booking and release seats."""
    with transaction.atomic():
        _release_booking_seats(booking)
        booking.delete()
    return {"message": "Booking deleted"}, status.HTTP_200_OK


def create_admin_user(request: Any) -> tuple[dict[str, Any], int]:
    """Create a user account from the admin panel."""
    payload = get_payload(request)

    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    middle_name = str(payload.get("middle_name") or "").strip() or None
    email = str(payload.get("email") or "").strip().lower()
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    password = str(payload.get("password") or "")
    dob_value = payload.get("dob")
    dob = parse_date(dob_value)
    is_active = parse_bool(payload.get("is_active"), default=True)

    if not first_name or not last_name or not email or not raw_phone or not password:
        return {
            "message": "First name, last name, email, phone number, and password are required"
        }, status.HTTP_400_BAD_REQUEST

    if dob is None:
        return {"message": "Date of birth is required"}, status.HTTP_400_BAD_REQUEST

    if not phone_number or not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if User.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST

    if User.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST

    if username and User.objects.filter(username__iexact=username).exists():
        return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST

    if not username:
        username = generate_unique_username(first_name, last_name)

    user = User(
        phone_number=phone_number,
        email=email,
        dob=dob,
        first_name=first_name,
        middle_name=middle_name,
        last_name=last_name,
        username=username,
        is_active=is_active,
    )
    user.set_password(password)
    user.save()
    ensure_user_referral_code(user)

    return {
        "message": "User created",
        "user": build_user_payload(user, request),
    }, status.HTTP_201_CREATED


def update_admin_user(user: User, request: Any) -> tuple[dict[str, Any], int]:
    """Update a user account from the admin panel."""
    payload = get_payload(request)
    password_changed = False

    if "first_name" in payload:
        first_name = str(payload.get("first_name") or "").strip()
        if not first_name:
            return {"message": "First name is required"}, status.HTTP_400_BAD_REQUEST
        user.first_name = first_name

    if "last_name" in payload:
        last_name = str(payload.get("last_name") or "").strip()
        if not last_name:
            return {"message": "Last name is required"}, status.HTTP_400_BAD_REQUEST
        user.last_name = last_name

    if "middle_name" in payload:
        middle_name = str(payload.get("middle_name") or "").strip() or None
        user.middle_name = middle_name

    if "email" in payload:
        email = str(payload.get("email") or "").strip().lower()
        if not email:
            return {"message": "Email is required"}, status.HTTP_400_BAD_REQUEST
        if User.objects.filter(email__iexact=email).exclude(pk=user.id).exists():
            return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST
        user.email = email

    if "phone_number" in payload:
        raw_phone = str(payload.get("phone_number") or "").strip()
        phone_number = normalize_phone_number(raw_phone)
        if not raw_phone:
            return {"message": "Phone number is required"}, status.HTTP_400_BAD_REQUEST
        if not phone_number or not PHONE_REGEX.match(phone_number):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if (
            User.objects.filter(phone_number=phone_number)
            .exclude(pk=user.id)
            .exists()
        ):
            return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST
        user.phone_number = phone_number

    if "username" in payload:
        username = str(payload.get("username") or "").strip() or None
        if username and User.objects.filter(username__iexact=username).exclude(pk=user.id).exists():
            return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST
        user.username = username

    if "dob" in payload:
        dob_value = payload.get("dob")
        dob = parse_date(dob_value)
        if dob is None:
            return {"message": "Invalid date of birth"}, status.HTTP_400_BAD_REQUEST
        user.dob = dob

    if "is_active" in payload:
        user.is_active = parse_bool(payload.get("is_active"), default=True)

    if "password" in payload:
        password = str(payload.get("password") or "")
        if password:
            user.set_password(password)
            password_changed = True

    user.save()

    if password_changed and not _send_password_changed_email(
        user.email,
        context_label="changed by an administrator",
    ):
        logger.warning(
            "Password changed email could not be sent to %s after admin update",
            user.email,
        )

    return {
        "message": "User updated",
        "user": build_user_payload(user, request),
    }, status.HTTP_200_OK


def create_vendor(request: Any) -> tuple[dict[str, Any], int]:
    """Create a vendor account."""
    payload = get_payload(request)

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    theatre = (
        str(payload.get("theatre") or payload.get("theatre_name") or "").strip()
        or None
    )
    city = str(payload.get("city") or "").strip() or None
    commission_percent = _parse_price_amount(
        coalesce(payload, "commission_percent", "commissionPercent", "platform_commission_percent")
    )
    if commission_percent is not None and (commission_percent < Decimal("0") or commission_percent > Decimal("100")):
        return {"message": "commission_percent must be between 0 and 100."}, status.HTTP_400_BAD_REQUEST
    status_label = str(payload.get("status") or DEFAULT_VENDOR_STATUS).strip() or DEFAULT_VENDOR_STATUS
    status_label = status_label.title()

    if not name or not email or not password:
        return {
            "message": "Name, email, and password are required"
        }, status.HTTP_400_BAD_REQUEST

    if Vendor.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists"}, status.HTTP_400_BAD_REQUEST

    if raw_phone and not phone_number:
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and Vendor.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists"}, status.HTTP_400_BAD_REQUEST

    if username and Vendor.objects.filter(username__iexact=username).exists():
        return {"message": "Username already exists"}, status.HTTP_400_BAD_REQUEST

    is_active = status_label.lower() != STATUS_BLOCKED.lower()
    vendor = Vendor(
        name=name,
        email=email,
        phone_number=phone_number or None,
        username=username,
        theatre=theatre,
        city=city,
        commission_percent=commission_percent,
        status=status_label,
        is_active=is_active,
    )
    vendor.set_password(password)
    vendor.save()

    return {
        "message": "Vendor created",
        "vendor": build_vendor_payload(vendor, request),
    }, status.HTTP_201_CREATED


def list_vendor_staff_accounts(request: Any) -> tuple[dict[str, Any], int]:
    """List staff accounts for the authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    staff_accounts = VendorStaff.objects.filter(vendor_id=vendor.id).order_by("-created_at", "-id")
    return {
        "staff": [build_vendor_staff_payload(staff) for staff in staff_accounts],
    }, status.HTTP_200_OK


def _username_taken_across_accounts(username: str, current_staff_id: Optional[int] = None) -> bool:
    """Return whether a username already exists across account tables."""
    normalized = str(username or "").strip()
    if not normalized:
        return False
    if Admin.objects.filter(username__iexact=normalized).exists():
        return True
    if Vendor.objects.filter(username__iexact=normalized).exists():
        return True
    if User.objects.filter(username__iexact=normalized).exists():
        return True

    query = VendorStaff.objects.filter(username__iexact=normalized)
    if current_staff_id:
        query = query.exclude(id=current_staff_id)
    return query.exists()


def create_vendor_staff_account(request: Any) -> tuple[dict[str, Any], int]:
    """Create a staff sub-account for the authenticated vendor owner."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    full_name = str(payload.get("full_name") or payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    raw_phone = str(payload.get("phone_number") or "").strip()
    phone_number = normalize_phone_number(raw_phone)
    username = str(payload.get("username") or "").strip() or None
    role = VendorStaff.ROLE_CASHIER

    if not full_name or not email or not password:
        return {
            "message": "Full name, email, and password are required."
        }, status.HTTP_400_BAD_REQUEST

    if raw_phone and not phone_number:
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if phone_number and not PHONE_REGEX.match(phone_number):
        return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST

    if Admin.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists() or Vendor.objects.filter(email__iexact=email).exists() or VendorStaff.objects.filter(email__iexact=email).exists():
        return {"message": "Email already exists."}, status.HTTP_400_BAD_REQUEST

    if phone_number and VendorStaff.objects.filter(phone_number=phone_number).exists():
        return {"message": "Phone number already exists."}, status.HTTP_400_BAD_REQUEST

    if username and _username_taken_across_accounts(username):
        return {"message": "Username already exists."}, status.HTTP_400_BAD_REQUEST

    staff = VendorStaff(
        vendor_id=vendor.id,
        full_name=full_name,
        email=email,
        phone_number=phone_number or None,
        username=username,
        role=role,
        is_active=parse_bool(payload.get("is_active"), default=True),
    )
    staff.set_password(password)
    staff.save()

    return {
        "message": "Vendor staff account created.",
        "staff": build_vendor_staff_payload(staff),
    }, status.HTTP_201_CREATED


def update_vendor_staff_account(
    request: Any,
    staff: VendorStaff,
) -> tuple[dict[str, Any], int]:
    """Update a vendor staff account."""
    payload = get_payload(request)

    if "full_name" in payload or "name" in payload:
        full_name = str(payload.get("full_name") or payload.get("name") or "").strip()
        if not full_name:
            return {"message": "Full name cannot be empty."}, status.HTTP_400_BAD_REQUEST
        staff.full_name = full_name

    if "email" in payload:
        email = str(payload.get("email") or "").strip().lower()
        if not email:
            return {"message": "Email cannot be empty."}, status.HTTP_400_BAD_REQUEST
        if Admin.objects.filter(email__iexact=email).exists() or User.objects.filter(email__iexact=email).exists() or Vendor.objects.filter(email__iexact=email).exists() or VendorStaff.objects.filter(email__iexact=email).exclude(id=staff.id).exists():
            return {"message": "Email already exists."}, status.HTTP_400_BAD_REQUEST
        staff.email = email

    if "phone_number" in payload:
        raw_phone = str(payload.get("phone_number") or "").strip()
        if not raw_phone:
            staff.phone_number = None
        else:
            phone_number = normalize_phone_number(raw_phone)
            if not phone_number or not PHONE_REGEX.match(phone_number):
                return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
            if VendorStaff.objects.filter(phone_number=phone_number).exclude(id=staff.id).exists():
                return {"message": "Phone number already exists."}, status.HTTP_400_BAD_REQUEST
            staff.phone_number = phone_number

    if "username" in payload:
        username = str(payload.get("username") or "").strip() or None
        if username and _username_taken_across_accounts(username, current_staff_id=staff.id):
            return {"message": "Username already exists."}, status.HTTP_400_BAD_REQUEST
        staff.username = username

    if "is_active" in payload:
        staff.is_active = parse_bool(payload.get("is_active"), default=staff.is_active)

    if "password" in payload:
        raw_password = str(payload.get("password") or "")
        if raw_password:
            staff.set_password(raw_password)

    staff.save()
    return {
        "message": "Vendor staff account updated.",
        "staff": build_vendor_staff_payload(staff),
    }, status.HTTP_200_OK


def list_cinemas_payload(request: Any, city: Optional[str] = None) -> list[dict[str, Any]]:
    """Return cinema vendor payloads for public views."""
    vendors = selectors.list_cinema_vendors(city=city)
    return build_cinemas_payload(vendors, request)


def build_cinemas_payload(
    vendors: Iterable[Vendor], request: Optional[Any] = None
) -> list[dict[str, Any]]:
    """Build cinema payloads for dropdowns and listings."""
    payload = []
    used_slugs = set()
    for vendor in vendors:
        display_name = (
            vendor.name
            or vendor.theatre
            or vendor.username
            or vendor.email
            or f"Vendor {vendor.id}"
        )
        slug_base = slugify_text(display_name)
        slug = slug_base or f"vendor-{vendor.id}"
        if slug in used_slugs:
            slug = f"{slug}-{vendor.id}"
        used_slugs.add(slug)
        payload.append(
            {
                "id": vendor.id,
                "name": display_name,
                "theatre": vendor.theatre,
                "city": vendor.city,
                "slug": slug,
                "short": short_label(display_name),
                "profile_image": get_profile_image_url(request, vendor),
            }
        )
    return payload


def _sync_collab_details(slide: HomeSlide, payload: dict[str, Any]) -> Optional[Any]:
    """Sync collaboration details for a slide."""
    if slide.slide_type != HomeSlide.SLIDE_COLLAB:
        if hasattr(slide, "collab_details"):
            slide.collab_details.delete()
        return None

    instance = getattr(slide, "collab_details", None)
    serializer = CollabDetailsAdminSerializer(
        instance=instance,
        data=payload,
        partial=instance is not None,
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save(slide=slide)


def create_home_slide(data: dict[str, Any]) -> HomeSlide:
    """Create a home slide with optional collaboration details."""
    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, data)
    return slide


def update_home_slide(slide: HomeSlide, data: dict[str, Any]) -> HomeSlide:
    """Update a home slide with optional collaboration details."""
    with transaction.atomic():
        serializer = HomeSlideAdminSerializer(slide, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        slide = serializer.save()
        _sync_collab_details(slide, data)
    return slide


def toggle_home_slide(slide: HomeSlide) -> HomeSlide:
    """Toggle the active state for a home slide."""
    slide.is_active = not slide.is_active
    slide.save(update_fields=["is_active"])
    return slide


def create_collaborator(data: dict[str, Any]) -> Collaborator:
    """Create a collaborator."""
    serializer = CollaboratorAdminSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def update_collaborator(collaborator: Collaborator, data: dict[str, Any]) -> Collaborator:
    """Update a collaborator."""
    serializer = CollaboratorAdminSerializer(collaborator, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def toggle_collaborator(collaborator: Collaborator) -> Collaborator:
    """Toggle collaborator active state."""
    collaborator.is_active = not collaborator.is_active
    collaborator.save(update_fields=["is_active"])
    return collaborator


def create_banner(data: dict[str, Any]) -> Banner:
    """Create a banner."""
    serializer = BannerCreateUpdateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def update_banner(banner: Banner, data: dict[str, Any]) -> Banner:
    """Update a banner."""
    serializer = BannerCreateUpdateSerializer(banner, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def _coerce_list(value: Any) -> Optional[list[Any]]:
    """Normalize a payload field into a list if possible."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return None
    return None


def _normalize_credit_role_type(
    value: Any,
    *,
    default_role_type: Optional[str] = None,
) -> Optional[str]:
    """Normalize incoming role values into MovieCredit role constants."""
    raw_value = str(value or default_role_type or "").strip().upper()
    if raw_value in {MovieCredit.ROLE_CAST, "ACTOR", "ACTRESS"}:
        return MovieCredit.ROLE_CAST
    if raw_value in {MovieCredit.ROLE_CREW, "STAFF"}:
        return MovieCredit.ROLE_CREW
    return None


def _normalize_credit_item(
    item: Any, default_role_type: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Normalize a credit payload into the canonical schema."""
    if not isinstance(item, dict):
        return None
    role_type = _normalize_credit_role_type(
        item.get("role_type")
        or item.get("roleType")
        or item.get("credit_type")
        or item.get("creditType")
        or default_role_type,
    )
    if not role_type:
        return None
    role_value = (
        item.get("role")
        or item.get("role_name")
        or item.get("roleName")
        or item.get("character_name")
        or item.get("characterName")
        or item.get("job_title")
        or item.get("jobTitle")
        or item.get("department")
    )
    character_name = (
        item.get("character_name")
        or item.get("characterName")
        or item.get("role_name")
        or item.get("roleName")
    )
    job_title = item.get("job_title") or item.get("jobTitle") or item.get("department")
    if not character_name and role_type == MovieCredit.ROLE_CAST:
        character_name = role_value
    if not job_title and role_type == MovieCredit.ROLE_CREW:
        job_title = role_value
    person_payload = item.get("person") or item.get("person_data") or {}
    if not person_payload:
        name_value = item.get("full_name") or item.get("fullName") or item.get("name")
        if name_value:
            person_payload = {"full_name": name_value}
    elif isinstance(person_payload, dict):
        person_payload = {
            **person_payload,
            "full_name": person_payload.get("full_name")
            or person_payload.get("fullName")
            or person_payload.get("name"),
            "photo_url": person_payload.get("photo_url")
            or person_payload.get("photoUrl"),
            "date_of_birth": person_payload.get("date_of_birth")
            or person_payload.get("dateOfBirth"),
            "photo_upload_key": person_payload.get("photo_upload_key")
            or person_payload.get("photoUploadKey"),
        }
    return {
        "id": item.get("id"),
        "role_type": role_type,
        "character_name": character_name,
        "job_title": job_title,
        "position": item.get("position") or item.get("order"),
        "person_id": item.get("person_id") or item.get("personId"),
        "person": person_payload,
    }


def _extract_credits_payload(payload: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """Extract normalized credits payload from request data."""
    if "credits" in payload:
        normalized = [
            item
            for item in (
                _normalize_credit_item(entry)
                for entry in (_coerce_list(payload.get("credits")) or [])
            )
            if item
        ]
        if normalized:
            return normalized

        # Fallback to cast/crew keys when credits key exists but cannot be parsed.
        cast_fallback = _coerce_list(payload.get("cast"))
        crew_fallback = _coerce_list(payload.get("crew"))
        if cast_fallback is None and crew_fallback is None:
            return []

    cast = _coerce_list(payload.get("cast"))
    crew = _coerce_list(payload.get("crew"))
    if cast is None and crew is None:
        return None
    credits = []
    if cast:
        credits.extend(
            filter(
                None,
                [
                    _normalize_credit_item(item, default_role_type=MovieCredit.ROLE_CAST)
                    for item in cast
                ],
            )
        )
    if crew:
        credits.extend(
            filter(
                None,
                [
                    _normalize_credit_item(item, default_role_type=MovieCredit.ROLE_CREW)
                    for item in crew
                ],
            )
        )
    return credits


def _normalize_trailer_urls(value: Any) -> list[str]:
    """Normalize trailer URL input into a unique ordered list."""
    raw_items: list[Any] = []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raw_items = []
        else:
            parsed_json = None
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed_json = json.loads(text)
                except Exception:
                    parsed_json = None
            if isinstance(parsed_json, list):
                raw_items = parsed_json
            else:
                raw_items = re.split(r"[\n,]", text)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)

    urls: list[str] = []
    for item in raw_items:
        url = str(item or "").strip()
        if not url or url in urls:
            continue
        urls.append(url)
    return urls


def _extract_trailer_urls_payload(payload: dict[str, Any]) -> list[str]:
    """Extract trailer URLs from known payload keys."""
    urls = _normalize_trailer_urls(
        coalesce(payload, "trailerUrls", "trailer_urls", "trailers", default=[])
    )
    single = str(
        coalesce(payload, "trailerUrl", "trailer_url", "trailer", default="") or ""
    ).strip()
    if single and single not in urls:
        urls.insert(0, single)
    return urls


def _resolve_person_from_credit(request: Any, credit: dict[str, Any]) -> Optional[Person]:
    """Resolve or create a person from a credit payload."""
    person_id = credit.get("person_id")
    if person_id:
        return Person.objects.filter(pk=person_id).first()
    person_data = credit.get("person") if isinstance(credit.get("person"), dict) else {}
    if person_data.get("id"):
        return Person.objects.filter(pk=person_data.get("id")).first()
    full_name = (person_data.get("full_name") or person_data.get("fullName") or "").strip()
    if not full_name:
        return None
    existing = Person.objects.filter(full_name__iexact=full_name).first()
    if existing:
        return existing
    upload_key = person_data.get("photo_upload_key") or person_data.get("photoUploadKey")
    uploaded_photo = request.FILES.get(upload_key) if upload_key else None
    return Person.objects.create(
        full_name=full_name,
        photo=uploaded_photo or person_data.get("photo"),
        photo_url=person_data.get("photo_url") or person_data.get("photoUrl"),
        bio=person_data.get("bio"),
        date_of_birth=parse_date(person_data.get("date_of_birth") or person_data.get("dateOfBirth")),
        nationality=person_data.get("nationality"),
        instagram=person_data.get("instagram"),
        imdb=person_data.get("imdb"),
        facebook=person_data.get("facebook"),
    )


def _sync_movie_credits(
    request: Any, movie: Movie, credits_payload: Optional[list[dict[str, Any]]]
) -> None:
    """Synchronize movie credits with the provided payload."""
    if credits_payload is None:
        return
    existing = {credit.id: credit for credit in movie.credits.all()}
    seen_ids = set()
    for idx, item in enumerate(credits_payload):
        credit = _normalize_credit_item(item, default_role_type=item.get("role_type"))
        if not credit:
            continue
        person = _resolve_person_from_credit(request, credit)
        if not person:
            continue
        position = credit.get("position")
        if position is None:
            position = idx + 1
        credit_id = credit.get("id")
        if credit_id and credit_id in existing:
            instance = existing[credit_id]
            instance.role_type = credit.get("role_type")
            instance.character_name = credit.get("character_name")
            instance.job_title = credit.get("job_title")
            instance.position = position
            instance.person = person
            instance.save()
            seen_ids.add(instance.id)
        else:
            instance = MovieCredit.objects.create(
                movie=movie,
                person=person,
                role_type=credit.get("role_type"),
                character_name=credit.get("character_name"),
                job_title=credit.get("job_title"),
                position=position,
            )
            seen_ids.add(instance.id)
    for credit_id, instance in existing.items():
        if credit_id not in seen_ids:
            instance.delete()


def create_movie(request: Any) -> tuple[dict[str, Any], int]:
    """Create a movie (admin/vendor)."""
    admin_actor = resolve_admin(request)
    vendor_actor = resolve_vendor(request)
    if not admin_actor and not vendor_actor:
        return {"message": "Admin or vendor access required"}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    title = str(coalesce(payload, "title", "name", default="") or "").strip()
    if not title:
        return {"message": "Title is required"}, status.HTTP_400_BAD_REQUEST

    duration_minutes_value = coalesce(payload, "durationMinutes", "duration_minutes")
    try:
        duration_minutes_value = (
            int(duration_minutes_value) if duration_minutes_value is not None else None
        )
    except (TypeError, ValueError):
        duration_minutes_value = None

    trailer_urls = _extract_trailer_urls_payload(payload)

    movie = Movie(
        title=title,
        short_description=coalesce(payload, "shortDescription", "short_description"),
        description=coalesce(payload, "description", "synopsis"),
        long_description=coalesce(payload, "longDescription", "long_description"),
        language=coalesce(payload, "language", "lang"),
        genre=coalesce(payload, "genre", "category"),
        duration=coalesce(payload, "duration", "runtime"),
        duration_minutes=duration_minutes_value,
        rating=coalesce(payload, "rating", "censor"),
        release_date=parse_date(coalesce(payload, "releaseDate", "release_date")),
        poster_url=coalesce(payload, "posterUrl", "poster_url", "poster"),
        trailer_url=trailer_urls[0] if trailer_urls else None,
        trailer_urls=trailer_urls,
        status=coalesce(payload, "status", default=Movie.STATUS_COMING_SOON),
        is_active=coalesce(payload, "isActive", "is_active", default=True),
    )
    now = timezone.now()
    if admin_actor:
        movie.approval_status = Movie.ApprovalStatus.APPROVED
        movie.approved_by = admin_actor
        movie.approved_at = now
        movie.approval_reason = str(coalesce(payload, "approvalReason", "approval_reason") or "").strip() or None
        movie.approval_metadata = {
            "source": "admin_create",
            "decision": Movie.ApprovalStatus.APPROVED,
            "decision_by": admin_actor.id,
            "decision_at": now.isoformat(),
            "reason": movie.approval_reason,
        }
    else:
        movie.approval_status = Movie.ApprovalStatus.PENDING
        movie.approved_by = None
        movie.approved_at = None
        movie.approval_reason = None
        movie.approval_metadata = {
            "source": "vendor_submission",
            "submitted_by": "vendor",
            "submitted_by_id": vendor_actor.id if vendor_actor else None,
            "submitted_at": now.isoformat(),
            "decision": Movie.ApprovalStatus.PENDING,
        }
    poster_image = request.FILES.get("poster_image") or request.FILES.get("posterImage")
    banner_image = request.FILES.get("banner_image") or request.FILES.get("bannerImage")
    if poster_image:
        movie.poster_image = poster_image
    if banner_image:
        movie.banner_image = banner_image
    movie.save()
    genre_ids = coalesce(payload, "genreIds", "genres")
    if genre_ids:
        try:
            movie.genres.set(genre_ids)
        except Exception:
            pass
    _sync_movie_credits(request, movie, _extract_credits_payload(payload))

    # Vendor submissions should notify admins for moderation/approval.
    if vendor_actor:
        try:
            vendor_name = str(getattr(vendor_actor, "name", "") or "").strip() or "Vendor"
            vendor_id = getattr(vendor_actor, "id", None)
            notification_title = "New movie submitted for approval"
            notification_message = (
                f"{vendor_name} submitted '{movie.title}' and it is waiting for admin approval."
            )
            notification_metadata = {
                "movie_id": movie.id,
                "movie_title": movie.title,
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "approval_status": movie.approval_status,
                "action": "movie_submission",
            }
            for admin in Admin.objects.filter(is_active=True).only("id", "email"):
                _create_notification(
                    recipient_role=Notification.ROLE_ADMIN,
                    recipient_id=admin.id,
                    recipient_email=admin.email,
                    event_type=Notification.EVENT_SHOW_UPDATE,
                    title=notification_title,
                    message=notification_message,
                    metadata=notification_metadata,
                    send_email_too=True,
                )
        except Exception:
            logger.exception("Failed to dispatch vendor movie submission notifications for movie %s", movie.id)

    response_builder = build_movie_admin_payload if admin_actor else build_movie_vendor_payload
    return {"movie": response_builder(movie, request=request)}, status.HTTP_201_CREATED


def update_movie(request: Any, movie: Movie) -> tuple[dict[str, Any], int]:
    """Update a movie (admin only)."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    now = timezone.now()
    for field, keys in {
        "title": ("title", "name"),
        "short_description": ("shortDescription", "short_description"),
        "description": ("description", "synopsis"),
        "long_description": ("longDescription", "long_description"),
        "language": ("language", "lang"),
        "genre": ("genre", "category"),
        "duration": ("duration", "runtime"),
        "rating": ("rating", "censor"),
        "poster_url": ("posterUrl", "poster_url", "poster"),
        "status": ("status",),
        "is_active": ("isActive", "is_active"),
        "is_approved": ("isApproved", "is_approved"),
    }.items():
        value = coalesce(payload, *keys)
        if value is not None:
            setattr(movie, field, value)

    approval_status = coalesce(payload, "approvalStatus", "approval_status")
    approval_reason = coalesce(payload, "approvalReason", "approval_reason")
    if approval_status is not None or coalesce(payload, "isApproved", "is_approved") is not None:
        normalized_approval_status = str(approval_status or "").strip().upper()
        if not normalized_approval_status:
            normalized_approval_status = (
                Movie.ApprovalStatus.APPROVED
                if bool(coalesce(payload, "isApproved", "is_approved"))
                else Movie.ApprovalStatus.REJECTED
            )
        if normalized_approval_status not in Movie.ApprovalStatus.values:
            normalized_approval_status = Movie.ApprovalStatus.APPROVED if movie.is_approved else Movie.ApprovalStatus.PENDING
        movie.approval_status = normalized_approval_status
        movie.approved_by = resolve_admin(request)
        movie.approved_at = now
        movie.approval_reason = str(approval_reason or "").strip() or None
        approval_metadata = dict(movie.approval_metadata or {})
        approval_metadata.update(
            {
                "source": "admin_update",
                "decision": normalized_approval_status,
                "decision_by": getattr(movie.approved_by, "id", None),
                "decision_at": now.isoformat(),
                "reason": movie.approval_reason,
            }
        )
        movie.approval_metadata = approval_metadata

    trailer_keys = {
        "trailerUrls",
        "trailer_urls",
        "trailers",
        "trailerUrl",
        "trailer_url",
        "trailer",
    }
    if any(key in payload for key in trailer_keys):
        trailer_urls = _extract_trailer_urls_payload(payload)
        movie.trailer_urls = trailer_urls
        movie.trailer_url = trailer_urls[0] if trailer_urls else None

    duration_minutes_value = coalesce(payload, "durationMinutes", "duration_minutes")
    if duration_minutes_value is not None:
        try:
            movie.duration_minutes = int(duration_minutes_value)
        except (TypeError, ValueError):
            movie.duration_minutes = None

    release_value = coalesce(payload, "releaseDate", "release_date")
    if release_value is not None:
        movie.release_date = parse_date(release_value)

    poster_image = request.FILES.get("poster_image") or request.FILES.get("posterImage")
    banner_image = request.FILES.get("banner_image") or request.FILES.get("bannerImage")
    if poster_image:
        movie.poster_image = poster_image
    if banner_image:
        movie.banner_image = banner_image

    movie.save()
    genre_ids = coalesce(payload, "genreIds", "genres")
    if genre_ids is not None:
        try:
            movie.genres.set(genre_ids)
        except Exception:
            pass
    _sync_movie_credits(request, movie, _extract_credits_payload(payload))
    response_builder = build_movie_admin_payload if is_admin_request(request) else build_movie_vendor_payload
    return {"movie": response_builder(movie, request=request)}, status.HTTP_200_OK


def delete_movie(request: Any, movie: Movie) -> tuple[dict[str, Any], int]:
    """Delete a movie (admin only)."""
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    movie.delete()
    return {"message": "Movie deleted"}, status.HTTP_200_OK


def _parse_duration_text_to_minutes(value: Any) -> Optional[int]:
    """Parse common movie duration text formats into minutes."""
    text = str(value or "").strip().lower()
    if not text:
        return None

    if text.isdigit():
        parsed = int(text)
        return parsed if parsed > 0 else None

    hh_mm_match = re.fullmatch(r"(\d{1,2}):(\d{1,2})", text)
    if hh_mm_match:
        hours = int(hh_mm_match.group(1))
        minutes = int(hh_mm_match.group(2))
        total = (hours * 60) + minutes
        return total if total > 0 else None

    hour_match = re.search(r"(\d+)\s*h(?:ours?)?", text)
    minute_match = re.search(r"(\d+)\s*m(?:in(?:ute)?s?)?", text)
    if hour_match or minute_match:
        hours = int(hour_match.group(1)) if hour_match else 0
        minutes = int(minute_match.group(1)) if minute_match else 0
        total = (hours * 60) + minutes
        return total if total > 0 else None

    number_match = re.search(r"(\d+)", text)
    if number_match:
        parsed = int(number_match.group(1))
        return parsed if parsed > 0 else None
    return None


def _resolve_movie_duration_minutes(movie: Movie) -> Optional[int]:
    """Return effective movie duration in minutes from canonical or text fields."""
    raw_minutes = getattr(movie, "duration_minutes", None)
    try:
        parsed_minutes = int(raw_minutes) if raw_minutes is not None else None
    except (TypeError, ValueError):
        parsed_minutes = None
    if parsed_minutes and parsed_minutes > 0:
        return parsed_minutes
    return _parse_duration_text_to_minutes(getattr(movie, "duration", None))


def _resolve_show_buffer_minutes(payload: dict[str, Any]) -> int:
    """Resolve show buffer time in minutes from payload or settings."""
    configured = coalesce(
        payload,
        "buffer_minutes",
        "bufferMinutes",
        default=getattr(settings, "SHOW_BUFFER_MINUTES", SHOW_BUFFER_MINUTES_DEFAULT),
    )
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = SHOW_BUFFER_MINUTES_DEFAULT
    parsed = max(1, min(parsed, SHOW_BUFFER_MINUTES_MAX))
    return parsed


def _resolve_show_min_lead_hours() -> int:
    """Resolve minimum lead hours required before creating a show."""
    configured = getattr(settings, "SHOW_MIN_LEAD_HOURS", SHOW_MIN_LEAD_HOURS_DEFAULT)
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = SHOW_MIN_LEAD_HOURS_DEFAULT
    return max(parsed, 0)


def _resolve_show_operating_hours() -> tuple[time_cls, time_cls]:
    """Resolve daily operating window for show scheduling."""
    open_raw = getattr(
        settings,
        "SHOW_OPERATING_OPEN_TIME",
        SHOW_OPERATING_OPEN_TIME_DEFAULT.strftime("%H:%M"),
    )
    close_raw = getattr(
        settings,
        "SHOW_OPERATING_CLOSE_TIME",
        SHOW_OPERATING_CLOSE_TIME_DEFAULT.strftime("%H:%M"),
    )
    open_time = _parse_flexible_time(open_raw) or SHOW_OPERATING_OPEN_TIME_DEFAULT
    close_time = _parse_flexible_time(close_raw) or SHOW_OPERATING_CLOSE_TIME_DEFAULT
    return open_time, close_time


def _show_operating_window_for_date(
    show_date: date_cls,
) -> tuple[datetime, datetime, time_cls, time_cls]:
    """Build opening and closing datetimes for one show date."""
    open_time, close_time = _resolve_show_operating_hours()
    open_at = _combine_show_datetime(show_date, open_time)
    close_at = _combine_show_datetime(show_date, close_time)
    if close_at <= open_at:
        close_at += timedelta(days=1)
    return open_at, close_at, open_time, close_time


def _existing_show_time_window(
    show: Show,
    *,
    buffer_minutes: int,
) -> tuple[datetime, datetime, datetime]:
    """Return start/end/blocked-end datetimes for an existing show."""
    start_at = _combine_show_datetime(show.show_date, show.start_time)
    if show.end_time:
        end_at = _combine_show_datetime(show.show_date, show.end_time)
        if end_at <= start_at:
            end_at += timedelta(days=1)
    else:
        duration_minutes = _resolve_movie_duration_minutes(show.movie)
        if duration_minutes:
            end_at = start_at + timedelta(minutes=duration_minutes)
        else:
            end_at = start_at
    blocked_end = end_at + timedelta(minutes=buffer_minutes)
    return start_at, end_at, blocked_end


def _find_overlapping_show(
    *,
    vendor: Vendor,
    hall: str,
    show_date: date_cls,
    proposed_start_at: datetime,
    proposed_end_at: datetime,
    buffer_minutes: int,
) -> tuple[Optional[Show], Optional[datetime], Optional[datetime]]:
    """Find an existing show that conflicts with proposed show + buffer window."""
    proposed_blocked_end = proposed_end_at + timedelta(minutes=buffer_minutes)
    existing_shows = (
        Show.objects.filter(
            vendor=vendor,
            hall__iexact=hall,
            show_date=show_date,
        )
        .select_related("movie")
        .order_by("start_time", "id")
    )
    for existing_show in existing_shows:
        existing_start_at, existing_end_at, existing_blocked_end = _existing_show_time_window(
            existing_show,
            buffer_minutes=buffer_minutes,
        )
        if (
            proposed_start_at < existing_blocked_end
            and existing_start_at < proposed_blocked_end
        ):
            return existing_show, existing_end_at, existing_blocked_end
    return None, None, None


def _parse_show_dates(payload: dict[str, Any], base_date: Optional[date_cls]) -> list[date_cls]:
    """Build the list of dates for show creation from explicit dates or repeat days."""
    raw_dates = coalesce(payload, "dates", "show_dates", "showDates")
    date_items: list[Any] = []

    if isinstance(raw_dates, list):
        date_items = raw_dates
    elif isinstance(raw_dates, str):
        parsed_list = _coerce_list(raw_dates)
        if isinstance(parsed_list, list):
            date_items = parsed_list
        else:
            date_items = [part.strip() for part in raw_dates.split(",") if part.strip()]

    parsed_dates: list[date_cls] = []
    seen: set[str] = set()
    for item in date_items:
        parsed = parse_date(item)
        if not parsed:
            continue
        iso = parsed.isoformat()
        if iso in seen:
            continue
        seen.add(iso)
        parsed_dates.append(parsed)

    if parsed_dates:
        return parsed_dates

    repeat_days_raw = coalesce(payload, "repeatDays", "repeat_days", default=1)
    try:
        repeat_days = int(repeat_days_raw)
    except (TypeError, ValueError):
        repeat_days = 1

    if repeat_days < 1:
        repeat_days = 1
    if repeat_days > 60:
        repeat_days = 60

    if not base_date:
        return []

    return [base_date + timedelta(days=offset) for offset in range(repeat_days)]


def _initialize_showtime_seat_availability(show: Show, screen: Screen) -> None:
    """Create per-show availability rows for all seats in a hall."""
    if not show or not screen:
        return

    _, showtime = _get_or_create_showtime_for_context(
        show,
        hall_override=screen.screen_number,
    )
    seat_ids = list(
        Seat.objects.filter(screen_id=screen.id).values_list("id", flat=True)
    )
    if not seat_ids:
        return

    existing_seat_ids = set(
        SeatAvailability.objects.filter(
            showtime=showtime,
            seat_id__in=seat_ids,
        ).values_list("seat_id", flat=True)
    )
    missing_ids = [seat_id for seat_id in seat_ids if seat_id not in existing_seat_ids]
    if not missing_ids:
        return

    SeatAvailability.objects.bulk_create(
        [
            SeatAvailability(
                seat_id=seat_id,
                showtime=showtime,
                seat_status=SEAT_STATUS_AVAILABLE,
            )
            for seat_id in missing_ids
        ],
        ignore_conflicts=True,
    )


def create_show(request: Any) -> tuple[dict[str, Any], int]:
    """Create a show entry (admin/vendor only)."""
    if not is_authenticated(request):
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    vendor_id = coalesce(payload, "vendorId", "vendor_id")
    movie_id = coalesce(payload, "movieId", "movie_id")

    if not vendor_id or not movie_id:
        return {
            "message": "vendorId and movieId are required"
        }, status.HTTP_400_BAD_REQUEST

    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    if vendor_actor and str(vendor_id) != str(vendor_actor.id):
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN
    if not vendor_actor and not admin_actor:
        return {"message": "Vendor access required"}, status.HTTP_403_FORBIDDEN

    if vendor_actor:
        vendor_id = vendor_actor.id

    try:
        vendor = Vendor.objects.get(pk=vendor_id)
    except Vendor.DoesNotExist:
        return {"message": "Vendor not found"}, status.HTTP_404_NOT_FOUND

    try:
        movie = Movie.objects.get(pk=movie_id)
    except Movie.DoesNotExist:
        return {"message": "Movie not found"}, status.HTTP_404_NOT_FOUND

    # Ensure scheduled titles are visible in customer catalog.
    if not movie.is_active:
        movie.is_active = True
        movie.save(update_fields=["is_active"])

    base_show_date = parse_date(coalesce(payload, "date", "show_date", "showDate"))
    start_time = _parse_flexible_time(coalesce(payload, "start", "start_time", "startTime"))
    hall = " ".join(str(coalesce(payload, "hall") or "").split())

    if not hall:
        return {"message": "hall is required"}, status.HTTP_400_BAD_REQUEST

    hall_screen = Screen.objects.filter(vendor_id=vendor.id, screen_number__iexact=hall).first()
    if not hall_screen:
        return {
            "message": "Selected hall does not exist. Please add a hall first.",
        }, status.HTTP_400_BAD_REQUEST

    hall = str(hall_screen.screen_number or "").strip()
    if not hall:
        return {"message": "hall is required"}, status.HTTP_400_BAD_REQUEST

    if not Seat.objects.filter(screen_id=hall_screen.id).exists():
        return {
            "message": "Seat layout is not configured for the selected hall. Configure seats before adding shows.",
        }, status.HTTP_400_BAD_REQUEST

    if not start_time:
        return {"message": "show date and start time are required"}, status.HTTP_400_BAD_REQUEST

    show_dates = _parse_show_dates(payload, base_show_date)
    if not show_dates:
        return {"message": "show date and start time are required"}, status.HTTP_400_BAD_REQUEST

    movie_duration_minutes = _resolve_movie_duration_minutes(movie)
    if not movie_duration_minutes:
        return {
            "message": "Movie duration is required before scheduling shows.",
        }, status.HTTP_400_BAD_REQUEST

    buffer_minutes = _resolve_show_buffer_minutes(payload)
    min_lead_hours = _resolve_show_min_lead_hours()
    now = ensure_utc_datetime(timezone.now())
    minimum_start_at = now + timedelta(hours=min_lead_hours)

    created_payloads: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for show_date in show_dates:
        start_at = _combine_show_datetime(show_date, start_time)
        end_at = start_at + timedelta(minutes=movie_duration_minutes)

        if min_lead_hours and start_at < minimum_start_at:
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "too_soon",
                    "message": (
                        f"Shows must be added at least {min_lead_hours} hour(s) in advance. "
                        f"Minimum allowed start is {minimum_start_at.strftime('%Y-%m-%d %H:%M')}."
                    ),
                }
            )
            continue

        # Show.end_time stores only time, so we do not allow windows that spill into next date.
        if end_at.date() != start_at.date():
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "outside_operating_hours",
                    "message": "Show must finish within the same day before midnight.",
                }
            )
            continue

        operating_open_at, operating_close_at, open_time, close_time = _show_operating_window_for_date(
            show_date
        )
        if start_at < operating_open_at or end_at > operating_close_at:
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "outside_operating_hours",
                    "message": (
                        "Show timing is outside operating hours "
                        f"({open_time.strftime('%H:%M')} - {close_time.strftime('%H:%M')})."
                    ),
                }
            )
            continue

        conflict_qs = Show.objects.filter(
            vendor=vendor,
            hall__iexact=hall,
            show_date=show_date,
            start_time=start_time,
        )
        if conflict_qs.exists():
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "duplicate",
                    "message": "A show already exists for this hall and start time.",
                }
            )
            continue

        overlapping_show, overlapping_end_at, overlapping_blocked_until = _find_overlapping_show(
            vendor=vendor,
            hall=hall,
            show_date=show_date,
            proposed_start_at=start_at,
            proposed_end_at=end_at,
            buffer_minutes=buffer_minutes,
        )
        if overlapping_show:
            end_label = (
                overlapping_end_at.strftime("%H:%M") if overlapping_end_at else "-"
            )
            blocked_until_label = (
                overlapping_blocked_until.strftime("%H:%M")
                if overlapping_blocked_until
                else "-"
            )
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "overlap",
                    "conflict_show_id": overlapping_show.id,
                    "message": (
                        "Show overlaps with existing schedule "
                        f"({overlapping_show.start_time.strftime('%H:%M')} - {end_label}). "
                        f"Next slot starts from {blocked_until_label} after {buffer_minutes} min buffer."
                    ),
                }
            )
            continue

        show = Show(
            vendor=vendor,
            movie=movie,
            hall=hall,
            slot=coalesce(payload, "slot"),
            screen_type=coalesce(
                payload,
                "screenType",
                "screen_type",
                default=hall_screen.screen_type,
            ),
            price=coalesce(payload, "price"),
            status=_normalize_show_status(coalesce(payload, "status")),
            listing_status=coalesce(
                payload, "listingStatus", "listing_status", default="Now Showing"
            ),
            show_date=show_date,
            start_time=start_time,
            end_time=end_at.time(),
        )
        try:
            with transaction.atomic():
                show.save()
                _initialize_showtime_seat_availability(show, hall_screen)
        except IntegrityError:
            conflicts.append(
                {
                    "date": show_date.isoformat(),
                    "time": start_time.strftime("%H:%M"),
                    "hall": hall,
                    "reason": "duplicate",
                    "message": "A show already exists for this hall and start time.",
                }
            )
            continue

        created_payloads.append(build_show_payload(show))

    if not created_payloads:
        first_message = (
            str(conflicts[0].get("message")).strip()
            if conflicts and conflicts[0].get("message")
            else "Unable to schedule show for the selected time."
        )
        conflict_reasons = {str(item.get("reason") or "").strip() for item in conflicts}
        response_status = (
            status.HTTP_409_CONFLICT
            if conflict_reasons and conflict_reasons.issubset({"duplicate", "overlap"})
            else status.HTTP_400_BAD_REQUEST
        )
        return {
            "message": first_message,
            "created_count": 0,
            "requested_count": len(show_dates),
            "conflicts": conflicts,
            "shows": [],
        }, response_status

    response_payload: dict[str, Any] = {
        "shows": created_payloads,
        "show": created_payloads[0],
        "created_count": len(created_payloads),
        "requested_count": len(show_dates),
        "conflicts": conflicts,
    }

    if conflicts:
        response_payload["message"] = (
            f"Created {len(created_payloads)} show(s). "
            f"Skipped {len(conflicts)} conflicting/invalid schedule(s)."
        )
    elif len(created_payloads) > 1:
        response_payload["message"] = f"Created {len(created_payloads)} shows successfully."

    first_created = created_payloads[0]
    show_date_text = first_created.get("date") or "selected date"
    show_time_text = first_created.get("start") or "selected time"
    notification_title = "Show schedule updated"
    notification_message = (
        f"{movie.title} was scheduled on {show_date_text} at {show_time_text} in hall {hall}."
    )
    _notify_show_update(
        vendor=vendor,
        movie=movie,
        title=notification_title,
        message=notification_message,
        metadata={
            "movie_id": movie.id,
            "vendor_id": vendor.id,
            "created_count": len(created_payloads),
            "show_ids": [entry.get("id") for entry in created_payloads if entry.get("id")],
        },
    )

    return response_payload, status.HTTP_201_CREATED


def delete_show(request: Any, show: Show) -> tuple[dict[str, Any], int]:
    """Delete a show entry (admin/vendor only)."""
    if not is_authenticated(request):
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    if vendor_actor and show.vendor_id != vendor_actor.id:
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN
    if not vendor_actor and not admin_actor:
        return {"message": "Vendor access required"}, status.HTTP_403_FORBIDDEN

    title = "Show schedule updated"
    show_date_text = show.show_date.isoformat() if show.show_date else "selected date"
    show_time_text = show.start_time.strftime("%H:%M") if show.start_time else "selected time"
    message = (
        f"{show.movie.title} show on {show_date_text} at {show_time_text} in hall {show.hall or '-'} was removed."
    )
    _notify_show_update(
        vendor=show.vendor,
        movie=show.movie,
        title=title,
        message=message,
        metadata={
            "show_id": show.id,
            "movie_id": show.movie_id,
            "vendor_id": show.vendor_id,
            "action": "deleted",
        },
    )

    show.delete()
    return {"message": "Show deleted"}, status.HTTP_200_OK


def _seat_category_key(value: Any) -> str:
    """Normalize seat type to a stable category key."""
    return SEAT_CATEGORY_KEYS.get(_normalize_seat_category(value), "normal")


def _booked_count_for_showtime(showtime: Showtime) -> int:
    """Count non-cancelled booked seats for a showtime."""
    return BookingSeat.objects.filter(showtime=showtime).exclude(
        booking__booking_status__iexact="Cancelled"
    ).count()


def _available_target_seats_for_showtime(showtime: Showtime, screen: Screen) -> list[Seat]:
    """Return currently available seats for a target showtime in deterministic order."""
    now = timezone.now()
    occupied_ids: set[int] = set(
        BookingSeat.objects.filter(showtime=showtime)
        .exclude(booking__booking_status__iexact="Cancelled")
        .values_list("seat_id", flat=True)
    )

    for availability in SeatAvailability.objects.filter(showtime=showtime).select_related("seat"):
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value in BOOKED_STATUSES or status_value == SEAT_STATUS_UNAVAILABLE.lower():
            occupied_ids.add(availability.seat_id)
            continue
        if availability.locked_until and availability.locked_until > now:
            occupied_ids.add(availability.seat_id)

    seats = list(
        Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
    )
    return [seat for seat in seats if seat.id not in occupied_ids]


def preview_vendor_quick_hall_swap(show: Show) -> tuple[dict[str, Any], int]:
    """Return candidate halls and capacity fit for one-click hall swap."""
    source_hall = str(show.hall or "").strip()
    if not source_hall:
        return {"message": "Source hall is not set for this show."}, status.HTTP_400_BAD_REQUEST

    source_screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=source_hall).first()
    source_showtime = _find_showtime_for_context(show, source_hall)
    if not source_showtime:
        _, source_showtime = _get_or_create_showtime_for_context(show, source_hall)

    booked_count = _booked_count_for_showtime(source_showtime)
    source_capacity = int(source_screen.capacity or 0) if source_screen else 0

    candidates = []
    screens = Screen.objects.filter(vendor_id=show.vendor_id).exclude(screen_number__iexact=source_hall)
    for screen in screens:
        hall_name = str(screen.screen_number or "").strip()
        if not hall_name:
            continue

        has_timing_conflict = Show.objects.filter(
            vendor_id=show.vendor_id,
            show_date=show.show_date,
            start_time=show.start_time,
            hall__iexact=hall_name,
        ).exclude(id=show.id).exists()

        target_start = _combine_show_datetime(show.show_date, show.start_time)
        target_showtime = Showtime.objects.filter(
            movie_id=show.movie_id,
            screen=screen,
            start_time=target_start,
        ).first()

        if target_showtime:
            available_target_seats = _available_target_seats_for_showtime(target_showtime, screen)
        else:
            available_target_seats = list(
                Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
            )
        total_capacity = int(screen.capacity or len(Seat.objects.filter(screen=screen)) or 0)
        free_capacity = len(available_target_seats)
        candidates.append(
            {
                "hall": hall_name,
                "capacity": total_capacity,
                "free_capacity": free_capacity,
                "can_fit": (not has_timing_conflict) and free_capacity >= booked_count,
                "timing_conflict": has_timing_conflict,
                "screen_type": screen.screen_type,
                "recommended": (not has_timing_conflict)
                and free_capacity >= booked_count
                and total_capacity > source_capacity,
            }
        )

    candidates.sort(
        key=lambda item: (
            0 if item["recommended"] else 1,
            0 if item["can_fit"] else 1,
            -int(item["capacity"] or 0),
            str(item["hall"]),
        )
    )

    return {
        "show": build_show_payload(show),
        "source": {
            "hall": source_hall,
            "capacity": source_capacity,
            "booked_seats": booked_count,
        },
        "candidates": candidates,
    }, status.HTTP_200_OK


def quick_swap_show_hall(request: Any, show: Show) -> tuple[dict[str, Any], int]:
    """Swap a show to another hall and remap booked seats to equivalent target seats."""
    payload = get_payload(request)
    target_hall = str(coalesce(payload, "target_hall", "targetHall", "hall") or "").strip()
    source_hall = str(show.hall or "").strip()

    if not target_hall:
        return {"message": "target_hall is required."}, status.HTTP_400_BAD_REQUEST
    if not source_hall:
        return {"message": "Source hall is not set for this show."}, status.HTTP_400_BAD_REQUEST
    if target_hall.lower() == source_hall.lower():
        return {"message": "Target hall must be different from source hall."}, status.HTTP_400_BAD_REQUEST

    target_screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=target_hall).first()
    if not target_screen:
        return {"message": "Target hall layout is not configured."}, status.HTTP_400_BAD_REQUEST

    if Show.objects.filter(
        vendor_id=show.vendor_id,
        show_date=show.show_date,
        start_time=show.start_time,
        hall__iexact=target_hall,
    ).exclude(id=show.id).exists():
        return {
            "message": f"Hall {target_hall} already has a show at this time.",
        }, status.HTTP_409_CONFLICT

    with transaction.atomic():
        source_screen, source_showtime = _get_or_create_showtime_for_context(show, source_hall)

        target_start = _combine_show_datetime(show.show_date, show.start_time)
        target_end = _combine_show_datetime(show.show_date, show.end_time) if show.end_time else None
        target_showtime, _ = Showtime.objects.get_or_create(
            movie_id=show.movie_id,
            screen=target_screen,
            start_time=target_start,
            defaults={"end_time": target_end, "price": show.price},
        )
        if target_end and not target_showtime.end_time:
            target_showtime.end_time = target_end
            target_showtime.save(update_fields=["end_time"])

        booking_seats = list(
            BookingSeat.objects.select_for_update()
            .select_related("seat", "booking")
            .filter(showtime=source_showtime)
            .exclude(booking__booking_status__iexact="Cancelled")
            .order_by("booking_id", "id")
        )
        original_source_seat_ids = {item.seat_id for item in booking_seats if item.seat_id}

        if not booking_seats:
            show.hall = target_hall
            if target_screen.screen_type:
                show.screen_type = target_screen.screen_type
            show.save(update_fields=["hall", "screen_type"])
            return {
                "message": f"Show moved to {target_hall}. No existing bookings required remapping.",
                "show": build_show_payload(show),
                "source_hall": source_hall,
                "target_hall": target_hall,
                "moved_booking_count": 0,
                "moved_seat_count": 0,
            }, status.HTTP_200_OK

        target_available = _available_target_seats_for_showtime(target_showtime, target_screen)
        if len(target_available) < len(booking_seats):
            return {
                "message": "Target hall does not have enough available seats for transfer.",
                "required_seats": len(booking_seats),
                "available_seats": len(target_available),
            }, status.HTTP_409_CONFLICT

        target_by_label: dict[str, Seat] = {}
        target_by_category: dict[str, list[Seat]] = {
            "normal": [],
            "executive": [],
            "premium": [],
            "vip": [],
        }
        for seat in target_available:
            label = _join_seat_label(seat.row_label, seat.seat_number)
            target_by_label[label] = seat
            target_by_category[_seat_category_key(seat.seat_type)].append(seat)

        for category in target_by_category:
            target_by_category[category].sort(key=lambda s: _seat_sort_key(_join_seat_label(s.row_label, s.seat_number)))

        target_remaining = sorted(
            target_available,
            key=lambda s: _seat_sort_key(_join_seat_label(s.row_label, s.seat_number)),
        )

        assigned_target_ids: set[int] = set()
        seat_mapping: list[dict[str, Any]] = []
        booking_updates: set[int] = set()

        for booking_seat in booking_seats:
            source_seat = booking_seat.seat
            source_label = _join_seat_label(source_seat.row_label, source_seat.seat_number)
            source_category = _seat_category_key(source_seat.seat_type)

            selected: Optional[Seat] = None
            exact = target_by_label.get(source_label)
            if exact and exact.id not in assigned_target_ids:
                selected = exact

            if not selected:
                for candidate in target_by_category.get(source_category, []):
                    if candidate.id in assigned_target_ids:
                        continue
                    selected = candidate
                    break

            if not selected:
                for candidate in target_remaining:
                    if candidate.id in assigned_target_ids:
                        continue
                    selected = candidate
                    break

            if not selected:
                return {
                    "message": "Unable to map all bookings to equivalent seats in target hall.",
                }, status.HTTP_409_CONFLICT

            assigned_target_ids.add(selected.id)
            booking_updates.add(booking_seat.booking_id)
            seat_mapping.append(
                {
                    "booking_id": booking_seat.booking_id,
                    "from_seat": source_label,
                    "to_seat": _join_seat_label(selected.row_label, selected.seat_number),
                    "from_category": _normalize_seat_category(source_seat.seat_type),
                    "to_category": _normalize_seat_category(selected.seat_type),
                }
            )

            booking_seat.seat = selected
            booking_seat.showtime = target_showtime
            booking_seat.save(update_fields=["seat", "showtime"])

        Booking.objects.filter(id__in=list(booking_updates)).update(showtime=target_showtime)

        for target_seat_id in assigned_target_ids:
            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat_id=target_seat_id,
                showtime=target_showtime,
                defaults={"seat_status": SEAT_STATUS_BOOKED},
            )
            availability.seat_status = SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

        for seat_id in original_source_seat_ids:
            still_booked = BookingSeat.objects.filter(
                showtime=source_showtime,
                seat_id=seat_id,
            ).exclude(booking__booking_status__iexact="Cancelled").exists()
            if still_booked:
                continue
            SeatAvailability.objects.filter(showtime=source_showtime, seat_id=seat_id).update(
                seat_status=SEAT_STATUS_AVAILABLE,
                locked_until=None,
            )

        show.hall = target_hall
        if target_screen.screen_type:
            show.screen_type = target_screen.screen_type
        show.save(update_fields=["hall", "screen_type"])

        _notify_show_update(
            vendor=show.vendor,
            movie=show.movie,
            title="Quick hall swap completed",
            message=(
                f"{show.movie.title} moved from {source_hall} to {target_hall}. "
                f"{len(booking_updates)} booking(s) were remapped automatically."
            ),
            metadata={
                "show_id": show.id,
                "vendor_id": show.vendor_id,
                "source_hall": source_hall,
                "target_hall": target_hall,
                "moved_booking_count": len(booking_updates),
                "moved_seat_count": len(seat_mapping),
            },
        )

    return {
        "message": (
            f"Swapped to {target_hall}. Transferred {len(booking_updates)} booking(s) and "
            f"{len(seat_mapping)} seat(s)."
        ),
        "show": build_show_payload(show),
        "source_hall": source_hall,
        "target_hall": target_hall,
        "moved_booking_count": len(booking_updates),
        "moved_seat_count": len(seat_mapping),
        "seat_mappings": seat_mapping[:30],
    }, status.HTTP_200_OK


def request_password_otp(email: Optional[str]) -> tuple[dict[str, Any], int]:
    """Create or refresh an OTP for password reset."""
    email = str(email or "").strip()
    if not email:
        return {"message": "Email is required"}, status.HTTP_400_BAD_REQUEST

    try:
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "").strip().lower()
        smtp_backend = "django.core.mail.backends.smtp.emailbackend"
        if email_backend == smtp_backend:
            smtp_user = str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
            smtp_password = str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip()
            if not smtp_user or not smtp_password:
                return {
                    "message": (
                        "Email service is not configured. Set EMAIL_HOST_USER and "
                        "EMAIL_HOST_PASSWORD in .env.local, then restart backend."
                    )
                }, status.HTTP_503_SERVICE_UNAVAILABLE

        otp = f"{random.randint(100000, 999999)}"
        otp_record = OTPVerification.objects.create(email=email, otp=otp)

        email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "").strip()
        is_console_backend = "console" in email_backend.lower()
        debug_mode = bool(getattr(settings, "DEBUG", False))

        email_sent = _send_password_reset_otp_email(email, otp)
        if not email_sent:
            if debug_mode:
                logger.warning(
                    "OTP email delivery failed for %s; using debug console fallback",
                    email,
                )
                print(f"DEBUG OTP for {email}: {otp}")
                return {
                    "message": (
                        "Email delivery failed. OTP printed in backend console. "
                        "For Gmail SMTP, use an App Password in EMAIL_HOST_PASSWORD "
                        "and restart backend."
                    )
                }, status.HTTP_200_OK
            otp_record.delete()
            return {
                "message": "Failed to send OTP email. Please try again later."
            }, status.HTTP_500_INTERNAL_SERVER_ERROR

        logger.info("Generated OTP for %s: %s", email, otp)
        if debug_mode:
            print(f"DEBUG OTP for {email}: {otp}")

        if is_console_backend:
            return {
                "message": (
                    "OTP generated in backend console. Configure SMTP "
                    "to send OTP to user email."
                )
            }, status.HTTP_200_OK

        return {"message": "OTP sent to your email"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("forgot_password error")
        return {
            "message": "Failed to send OTP",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def verify_password_otp(email: Optional[str], otp: Optional[str]) -> tuple[dict[str, Any], int]:
    """Verify a password reset OTP."""
    email = str(email or "").strip()
    otp = str(otp or "").strip()
    if not email or not otp:
        return {
            "message": "Email and OTP are required"
        }, status.HTTP_400_BAD_REQUEST

    try:
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(
                email__iexact=email, otp=otp, created_at__gte=cutoff
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return {
                "message": "Invalid or expired OTP"
            }, status.HTTP_400_BAD_REQUEST

        record.is_verified = True
        record.save()
        return {"message": "OTP verified"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("verify_otp error")
        return {
            "message": "Failed to verify OTP",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def reset_password_with_otp(
    email: Optional[str], otp: Optional[str], new_password: Optional[str]
) -> tuple[dict[str, Any], int]:
    """Reset a user's password using a verified OTP."""
    email = str(email or "").strip()
    otp = str(otp or "").strip()
    if not email or not otp or not new_password:
        return {
            "message": "Email, OTP and new_password are required"
        }, status.HTTP_400_BAD_REQUEST

    try:
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(
                email__iexact=email,
                otp=otp,
                created_at__gte=cutoff,
                is_verified=True,
            )
            .order_by("-created_at")
            .first()
        )
        if not record:
            return {
                "message": "Invalid or unverified OTP"
            }, status.HTTP_400_BAD_REQUEST

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return {"message": "User not found"}, status.HTTP_404_NOT_FOUND

        user.set_password(new_password)
        user.save()

        record.is_verified = False
        record.save()

        if not _send_password_changed_email(
            user.email,
            context_label="password reset with OTP",
        ):
            logger.warning(
                "Password reset confirmation email could not be sent to %s",
                user.email,
            )

        return {"message": "Password reset successful"}, status.HTTP_200_OK
    except Exception as exc:
        logger.exception("reset_password error")
        return {
            "message": "Failed to reset password",
            "error": str(exc),
        }, status.HTTP_500_INTERNAL_SERVER_ERROR


def update_user_profile(request: Any, user: User) -> tuple[dict[str, Any], int]:
    """Update a user's profile information."""
    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("profile_image", None)

    for key in ("first_name", "middle_name", "last_name"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip()
            if key == "middle_name" and data[key] == "":
                data[key] = None

    if "dob" in data and not str(data["dob"]).strip():
        data.pop("dob")

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = UserProfileUpdateSerializer(user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_user = serializer.save()

    _update_profile_image(updated_user, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "user": build_user_payload(updated_user, request),
    }, status.HTTP_200_OK


def update_admin_profile(request: Any, admin_user: Admin) -> tuple[dict[str, Any], int]:
    """Update an admin's profile information."""
    actor_admin = resolve_admin(request)
    actor_id = getattr(actor_admin, "id", None)
    if actor_admin and actor_id and int(actor_id) != int(admin_user.id):
        if not getattr(actor_admin, "is_superuser", False):
            return {"message": "Admin access denied"}, status.HTTP_403_FORBIDDEN

    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("email", None)
    data.pop("profile_image", None)

    if "full_name" in data and isinstance(data["full_name"], str):
        data["full_name"] = data["full_name"].strip()
        if data["full_name"] == "":
            data["full_name"] = None

    if "phone_number" in data:
        raw_phone = str(data["phone_number"]).strip()
        phone = normalize_phone_number(raw_phone)
        data["phone_number"] = phone or None
        if raw_phone and not phone:
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and not PHONE_REGEX.match(phone):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and Admin.objects.filter(phone_number=phone).exclude(pk=admin_user.id).exists():
            return {
                "message": "Phone number already exists"
            }, status.HTTP_400_BAD_REQUEST

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = AdminProfileUpdateSerializer(admin_user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_admin = serializer.save()

    _update_profile_image(updated_admin, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "admin": build_admin_payload(updated_admin, request),
    }, status.HTTP_200_OK


def update_vendor_profile(request: Any, vendor_user: Vendor) -> tuple[dict[str, Any], int]:
    """Update a vendor's profile information."""
    actor_vendor = resolve_vendor(request)
    if actor_vendor and actor_vendor.id != vendor_user.id:
        return {"message": "Vendor access denied"}, status.HTTP_403_FORBIDDEN

    data = request_data_to_dict(request)
    uploaded_image = request.FILES.get("profile_image")
    remove_avatar = _is_truthy_flag(data.pop("remove_avatar", ""))
    data.pop("username", None)
    data.pop("email", None)
    data.pop("status", None)
    data.pop("is_active", None)
    data.pop("created_at", None)
    data.pop("profile_image", None)

    if "name" in data and isinstance(data["name"], str):
        data["name"] = data["name"].strip()
        if data["name"] == "":
            return {"message": "Vendor name is required"}, status.HTTP_400_BAD_REQUEST

    if "phone_number" in data:
        raw_phone = str(data["phone_number"]).strip()
        phone = normalize_phone_number(raw_phone)
        data["phone_number"] = phone or None
        if raw_phone and not phone:
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and not PHONE_REGEX.match(phone):
            return {"message": INVALID_PHONE_MESSAGE}, status.HTTP_400_BAD_REQUEST
        if phone and Vendor.objects.filter(phone_number=phone).exclude(pk=vendor_user.id).exists():
            return {
                "message": "Phone number already exists"
            }, status.HTTP_400_BAD_REQUEST

    for key in ("theatre", "city"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip() or None

    if not data and not uploaded_image and not remove_avatar:
        return {"message": "No profile changes provided"}, status.HTTP_400_BAD_REQUEST

    serializer = VendorProfileUpdateSerializer(vendor_user, data=data, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Profile update failed",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    updated_vendor = serializer.save()

    _update_profile_image(updated_vendor, uploaded_image, remove_avatar)

    return {
        "message": "Profile updated",
        "vendor": build_vendor_payload(updated_vendor, request),
    }, status.HTTP_200_OK


def _safe_number(value: Any) -> float:
    """Coerce a value to a float, returning 0 on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_int(value: Any) -> Optional[int]:
    """Coerce a value to int if possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_flexible_time(value: Any) -> Optional[time_cls]:
    """Parse a time value from common 24h and 12h formats."""
    if not value:
        return None
    if isinstance(value, time_cls):
        return value

    parsed = parse_time(value)
    if parsed:
        return parsed

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%I:%M %p", "%I %p", "%H:%M:%S"):
        try:
            return datetime.strptime(text.upper(), fmt).time()
        except ValueError:
            continue
    return None


def _normalize_seat_labels(value: Any) -> list[str]:
    """Normalize seat labels into uppercase tokens like A10."""
    raw_labels: list[str] = []
    if isinstance(value, str):
        matches = re.findall(r"[A-Za-z]+\s*\d+[A-Za-z]?", value)
        if matches:
            raw_labels.extend(matches)
        elif value.strip():
            raw_labels.append(value.strip())
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            raw_labels.extend(_normalize_seat_labels(item))

    labels: list[str] = []
    seen = set()
    for label in raw_labels:
        normalized = re.sub(r"\s+", "", str(label)).upper()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        labels.append(normalized)
    return labels


def _split_seat_label(value: str) -> tuple[str, str]:
    """Split a seat label into row and seat number parts."""
    label = re.sub(r"\s+", "", str(value or "")).upper()
    if not label:
        return "", ""

    match = re.match(r"^([A-Z]+)(\d+[A-Z]?)$", label)
    if match:
        return match.group(1), match.group(2)

    match = re.match(r"^(\d+[A-Z]?)$", label)
    if match:
        return "", match.group(1)

    row = label[:1] if label and label[0].isalpha() else ""
    seat_number = label[len(row):] if row else label
    return row, seat_number


def _join_seat_label(row_label: Any, seat_number: Any) -> str:
    """Build a canonical seat label from row and seat number."""
    row = str(row_label or "").strip().upper()
    number = str(seat_number or "").strip().upper()
    return f"{row}{number}".strip()


def _seat_sort_key(label: str) -> tuple[str, int, str]:
    """Sort seat labels by row then seat number."""
    cleaned = re.sub(r"\s+", "", str(label or "")).upper()
    match = re.match(r"^([A-Z]+)?(\d+)?([A-Z]*)$", cleaned)
    if not match:
        return cleaned, 0, ""
    row = match.group(1) or ""
    number = int(match.group(2) or 0)
    suffix = match.group(3) or ""
    return row, number, suffix


def _combine_show_datetime(show_date: date_cls, show_time: time_cls) -> datetime:
    """Combine date/time in the active timezone and normalize into UTC."""
    local_dt = datetime.combine(show_date, show_time)
    if timezone.is_naive(local_dt):
        local_dt = timezone.make_aware(local_dt, timezone.get_current_timezone())
    return local_dt.astimezone(datetime_timezone.utc)


def _resolve_booking_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract booking context fields from request/order payloads."""
    booking_data = payload.get("booking") if isinstance(payload.get("booking"), dict) else {}
    movie_data = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}

    cinema_id = _coerce_int(
        coalesce(
            booking_data,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
            default=coalesce(
                payload,
                "cinema_id",
                "cinemaId",
                "vendor_id",
                "vendorId",
                default=coalesce(movie_data, "cinemaId", "vendorId"),
            ),
        )
    )
    movie_id = _coerce_int(
        coalesce(
            booking_data,
            "movie_id",
            "movieId",
            "movie",
            default=coalesce(
                payload,
                "movie_id",
                "movieId",
                "movie",
                default=coalesce(movie_data, "movieId", "movie_id", "id"),
            ),
        )
    )
    show_id = _coerce_int(
        coalesce(
            booking_data,
            "show_id",
            "showId",
            default=coalesce(payload, "show_id", "showId"),
        )
    )
    show_date = parse_date(
        coalesce(
            booking_data,
            "date",
            "show_date",
            "showDate",
            default=coalesce(payload, "date", "show_date", "showDate"),
        )
    )
    show_time = _parse_flexible_time(
        coalesce(
            booking_data,
            "time",
            "start",
            "start_time",
            "startTime",
            "show_time",
            "showTime",
            default=coalesce(payload, "time", "start", "start_time", "startTime"),
        )
    )
    hall = str(
        coalesce(
            booking_data,
            "hall",
            "cinema_hall",
            "cinemaHall",
            default=coalesce(payload, "hall", "cinema_hall", "cinemaHall"),
        )
        or ""
    ).strip()
    selected_seats = _normalize_seat_labels(
        coalesce(
            booking_data,
            "selected_seats",
            "selectedSeats",
            "seats",
            default=coalesce(payload, "selected_seats", "selectedSeats", "seats"),
        )
    )
    user_id = _coerce_int(
        coalesce(booking_data, "user_id", "userId", default=coalesce(payload, "user_id", "userId"))
    )

    return {
        "show_id": show_id,
        "movie_id": movie_id,
        "cinema_id": cinema_id,
        "show_date": show_date,
        "show_time": show_time,
        "hall": hall or None,
        "selected_seats": selected_seats,
        "user_id": user_id,
    }


def _resolve_show_for_context(context: dict[str, Any]) -> Optional[Show]:
    """Resolve a Show row from booking context fields."""
    show_id = context.get("show_id")
    if show_id:
        return Show.objects.filter(pk=show_id).first()

    cinema_id = context.get("cinema_id")
    movie_id = context.get("movie_id")
    show_date = context.get("show_date")
    show_time = context.get("show_time")
    if not cinema_id or not movie_id or not show_date or not show_time:
        return None

    queryset = Show.objects.filter(
        vendor_id=cinema_id,
        movie_id=movie_id,
        show_date=show_date,
        start_time=show_time,
    )
    hall = context.get("hall")
    if hall:
        queryset = queryset.filter(hall__iexact=hall)
    return queryset.order_by("id").first()


def _resolve_screen_number(show: Show, hall_override: Optional[str] = None) -> str:
    """Resolve the screen number identifier for a show."""
    hall = str(hall_override or show.hall or "").strip()
    if hall:
        return hall
    return f"Hall-{show.id}"


def _find_showtime_for_context(show: Show, hall_override: Optional[str] = None) -> Optional[Showtime]:
    """Find an existing showtime row that maps to the selected show context."""
    screen_number = _resolve_screen_number(show, hall_override)
    screen = Screen.objects.filter(
        vendor_id=show.vendor_id,
        screen_number__iexact=screen_number,
    ).first()
    if not screen:
        return None
    start_at = _combine_show_datetime(show.show_date, show.start_time)
    return Showtime.objects.filter(
        movie_id=show.movie_id,
        screen_id=screen.id,
        start_time=start_at,
    ).first()


def _get_or_create_showtime_for_context(
    show: Show, hall_override: Optional[str] = None
) -> tuple[Screen, Showtime]:
    """Get or create the Screen/Showtime records for a selected show."""
    screen_number = _resolve_screen_number(show, hall_override)
    screen = Screen.objects.filter(
        vendor_id=show.vendor_id,
        screen_number__iexact=screen_number,
    ).first()
    if not screen:
        screen = Screen.objects.create(
            vendor_id=show.vendor_id,
            screen_number=screen_number,
            screen_type=show.screen_type,
            status="Active",
        )
    if show.screen_type and not screen.screen_type:
        screen.screen_type = show.screen_type
        screen.save(update_fields=["screen_type"])

    start_at = _combine_show_datetime(show.show_date, show.start_time)
    end_at = (
        _combine_show_datetime(show.show_date, show.end_time)
        if show.end_time
        else None
    )
    showtime, created = Showtime.objects.get_or_create(
        movie_id=show.movie_id,
        screen=screen,
        start_time=start_at,
        defaults={
            "end_time": end_at,
            "price": show.price,
        },
    )
    if not created:
        updated_fields: list[str] = []
        if end_at and not showtime.end_time:
            showtime.end_time = end_at
            updated_fields.append("end_time")
        if show.price is not None and showtime.price is None:
            showtime.price = show.price
            updated_fields.append("price")
        if updated_fields:
            showtime.save(update_fields=updated_fields)

    return screen, showtime


def _collect_sold_labels_for_showtime(showtime: Showtime, lock: bool = False) -> list[str]:
    """Collect sold seat labels from availability + confirmed bookings."""
    sold_labels = set()

    availability_qs = SeatAvailability.objects.filter(showtime=showtime).select_related(
        "seat"
    )
    if lock:
        availability_qs = availability_qs.select_for_update()
    for availability in availability_qs:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value not in BOOKED_STATUSES:
            continue
        sold_labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )

    booking_seat_qs = BookingSeat.objects.filter(
        booking__showtime=showtime,
    ).exclude(
        booking__booking_status__iexact="Cancelled"
    ).select_related("seat")
    if lock:
        booking_seat_qs = booking_seat_qs.select_for_update()
    for booking_seat in booking_seat_qs:
        sold_labels.add(
            _join_seat_label(booking_seat.seat.row_label, booking_seat.seat.seat_number)
        )

    return sorted(sold_labels, key=_seat_sort_key)


def _collect_unavailable_labels_for_showtime(
    showtime: Showtime, lock: bool = False
) -> list[str]:
    """Collect unavailable seat labels for a showtime."""
    labels = set()
    queryset = SeatAvailability.objects.filter(showtime=showtime).select_related("seat")
    if lock:
        queryset = queryset.select_for_update()
    for availability in queryset:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value != SEAT_STATUS_UNAVAILABLE.lower():
            continue
        labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )
    return sorted(labels, key=_seat_sort_key)


def _prune_expired_reservations(showtime: Showtime) -> None:
    """Clear expired seat reservations for a showtime."""
    now = timezone.now()
    SeatAvailability.objects.filter(
        showtime=showtime,
        locked_until__isnull=False,
        locked_until__lte=now,
    ).update(locked_until=None)


def _collect_reserved_labels_for_showtime(
    showtime: Showtime, lock: bool = False
) -> list[str]:
    """Collect reserved seat labels for a showtime based on locks."""
    now = timezone.now()
    queryset = SeatAvailability.objects.filter(
        showtime=showtime,
        locked_until__gt=now,
    ).select_related("seat")
    if lock:
        queryset = queryset.select_for_update()
    labels = set()
    for availability in queryset:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value in BOOKED_STATUSES:
            continue
        if status_value == SEAT_STATUS_UNAVAILABLE.lower():
            continue
        labels.add(
            _join_seat_label(availability.seat.row_label, availability.seat.seat_number)
        )
    return sorted(labels, key=_seat_sort_key)


def _collect_reserved_lock_deadlines_for_showtime(
    showtime: Showtime, lock: bool = False
) -> dict[str, str]:
    """Collect active seat lock deadlines keyed by seat label."""
    now = timezone.now()
    queryset = SeatAvailability.objects.filter(
        showtime=showtime,
        locked_until__gt=now,
    ).select_related("seat")
    if lock:
        queryset = queryset.select_for_update()

    lock_deadlines: dict[str, str] = {}
    for availability in queryset:
        status_value = str(availability.seat_status or "").strip().lower()
        if status_value in BOOKED_STATUSES:
            continue
        if status_value == SEAT_STATUS_UNAVAILABLE.lower():
            continue

        seat_label = _join_seat_label(
            availability.seat.row_label,
            availability.seat.seat_number,
        )
        if not seat_label or not availability.locked_until:
            continue
        lock_deadlines[seat_label] = availability.locked_until.isoformat()

    return {
        key: lock_deadlines[key]
        for key in sorted(lock_deadlines.keys(), key=_seat_sort_key)
    }


def _next_guest_phone_number() -> str:
    """Generate a unique phone number for fallback guest users."""
    for suffix in range(1000):
        candidate = str(9800000000 + suffix)
        if not User.objects.filter(phone_number=candidate).exists():
            return candidate
    while True:
        candidate = str(random.randint(9000000000, 9999999999))
        if not User.objects.filter(phone_number=candidate).exists():
            return candidate


def _resolve_booking_user(context: dict[str, Any]) -> User:
    """Resolve booking user from payload or fallback guest account."""
    user_id = context.get("user_id")
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            return user

    guest = User.objects.filter(email__iexact=DEFAULT_GUEST_EMAIL).first()
    if guest:
        return guest

    guest_user = User(
        email=DEFAULT_GUEST_EMAIL,
        phone_number=_next_guest_phone_number(),
        dob=date_cls(2000, 1, 1),
        first_name=DEFAULT_GUEST_NAME,
        last_name="User",
        username=f"guest-{uuid.uuid4().hex[:8]}",
    )
    guest_user.set_password(uuid.uuid4().hex)
    guest_user.save()
    return guest_user


def _run_post_booking_rewards(booking_id: int, event_name: str = "") -> None:
    """Run post-booking loyalty and referral rewards after DB commit."""
    booking = (
        Booking.objects.select_related("user", "showtime__screen__vendor")
        .filter(id=booking_id)
        .first()
    )
    if not booking:
        return

    try:
        loyalty.award_booking_points(booking, event_name=event_name)
    except Exception:
        logger.exception("Failed to award loyalty points for booking %s", booking_id)

    try:
        process_referral_reward_for_booking(booking)
    except Exception:
        logger.exception("Failed to apply referral wallet rewards for booking %s", booking_id)


def _create_booking_from_order(
    order: dict[str, Any],
    request: Any | None = None,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    """Create booking + sold seat records from order context."""
    enqueue_stale_pending_cleanup_job(metadata={"source": "create_booking"})

    context = _resolve_booking_context(order)
    source_ip = _normalize_booking_source_ip(
        _extract_client_ip(request) if request else None
    )
    if not source_ip:
        source_ip = _normalize_booking_source_ip(
            coalesce(order, "source_ip", "sourceIp", "client_ip", "clientIp", "ip")
            or coalesce(context, "source_ip", "sourceIp", "client_ip", "clientIp", "ip")
        )

    user_agent = _normalize_booking_user_agent(
        _extract_client_user_agent(request) if request else None
    )
    if not user_agent:
        user_agent = _normalize_booking_user_agent(
            coalesce(order, "user_agent", "userAgent", "ua")
            or coalesce(context, "user_agent", "userAgent", "ua")
        )

    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return None, None, status.HTTP_200_OK

    if not context.get("movie_id") or not context.get("cinema_id") or not context.get("show_date") or not context.get("show_time"):
        return (
            None,
            {
                "message": "Booking context is incomplete. Provide cinema, movie, date, time, and selected seats.",
            },
            status.HTTP_400_BAD_REQUEST,
        )

    show = _resolve_show_for_context(context)
    if not show:
        return (
            None,
            {"message": "Selected show was not found."},
            status.HTTP_404_NOT_FOUND,
        )
    show_booking_error, show_booking_status = _ensure_show_is_bookable(show)
    if show_booking_error:
        return None, show_booking_error, int(show_booking_status)

    normalized_labels = _normalize_seat_labels(selected_seats)
    parsed_labels: list[tuple[str, str, str]] = []
    invalid_labels: list[str] = []
    for label in normalized_labels:
        row_label, seat_number = _split_seat_label(label)
        if not seat_number:
            invalid_labels.append(label)
            continue
        parsed_labels.append((label, row_label, seat_number))

    if invalid_labels:
        return (
            None,
            {"message": "Invalid seat labels in request.", "invalid_seats": invalid_labels},
            status.HTTP_400_BAD_REQUEST,
        )

    user = _resolve_booking_user(context)
    provided_ticket_total = _safe_number(
        coalesce(order, "ticketTotal", "ticket_total", default=order.get("total"))
    )
    coupon_code = coalesce(order, "coupon_code", "couponCode", "coupon")
    event_name = str(
        coalesce(order, "event", "event_name", "festival", "festival_name")
        or coalesce(context, "event", "event_name", "festival", "festival_name")
        or ""
    ).strip()
    loyalty_payload = order.get("loyalty") if isinstance(order.get("loyalty"), dict) else {}
    requested_reward_id = _coerce_int(
        coalesce(
            order,
            "reward_id",
            "rewardId",
            default=coalesce(loyalty_payload, "reward_id", "rewardId"),
        )
    )
    requested_points_to_redeem = _coerce_int(
        coalesce(
            order,
            "loyalty_points_to_redeem",
            "loyaltyPointsToRedeem",
            "points_to_redeem",
            "pointsToRedeem",
            default=coalesce(
                loyalty_payload,
                "loyalty_points_to_redeem",
                "loyaltyPointsToRedeem",
                "points_to_redeem",
                "pointsToRedeem",
                "points",
            ),
        )
    )
    if requested_points_to_redeem is None:
        requested_points_to_redeem = 0
    subscription_payload = order.get("subscription") if isinstance(order.get("subscription"), dict) else {}
    use_subscription = parse_bool(
        coalesce(
            order,
            "use_subscription",
            "useSubscription",
            "apply_subscription",
            "applySubscription",
            default=coalesce(subscription_payload, "enabled", "use", "apply"),
        ),
        default=False,
    )
    requested_user_subscription_id = _coerce_int(
        coalesce(
            order,
            "user_subscription_id",
            "userSubscriptionId",
            "subscription_id",
            "subscriptionId",
            default=coalesce(
                subscription_payload,
                "user_subscription_id",
                "userSubscriptionId",
                "subscription_id",
                "subscriptionId",
                "id",
            ),
        )
    )
    use_subscription_free_ticket = parse_bool(
        coalesce(
            order,
            "use_subscription_free_ticket",
            "useSubscriptionFreeTicket",
            default=coalesce(subscription_payload, "use_free_ticket", "useFreeTicket"),
        ),
        default=False,
    )
    requested_subscription_free_tickets = _coerce_int(
        coalesce(
            order,
            "subscription_free_tickets",
            "subscriptionFreeTickets",
            default=coalesce(
                subscription_payload,
                "requested_free_tickets",
                "requestedFreeTickets",
                "free_tickets",
                "freeTickets",
            ),
        )
    )
    if requested_subscription_free_tickets is None:
        requested_subscription_free_tickets = 1
    if requested_subscription_free_tickets < 0:
        requested_subscription_free_tickets = 0
    referral_wallet_payload = order.get("referral_wallet") if isinstance(order.get("referral_wallet"), dict) else {}
    use_referral_wallet = parse_bool(
        coalesce(
            order,
            "use_referral_wallet",
            "useReferralWallet",
            "apply_referral_wallet",
            "applyReferralWallet",
            default=coalesce(referral_wallet_payload, "enabled", "use", "apply"),
        ),
        default=False,
    )
    requested_referral_wallet_amount = _parse_price_amount(
        coalesce(
            order,
            "referral_wallet_amount",
            "referralWalletAmount",
            "wallet_credit_to_use",
            "walletCreditToUse",
            default=coalesce(
                referral_wallet_payload,
                "amount",
                "amount_to_use",
                "amountToUse",
            ),
        )
    )
    price_lock_token = _extract_price_lock_token(order if isinstance(order, dict) else {})
    price_lock_snapshot = _load_price_lock(price_lock_token) if price_lock_token else None
    strict_price_lock = parse_bool(
        coalesce(order, "strict_price_lock", "strictPriceLock"),
        default=bool(price_lock_token),
    )

    with transaction.atomic():
        screen, showtime = _get_or_create_showtime_for_context(show, context.get("hall"))
        if price_lock_token and not _is_price_lock_compatible(
            price_lock_snapshot,
            show=show,
            showtime=showtime,
            selected_seats=normalized_labels,
        ):
            if strict_price_lock:
                return (
                    None,
                    {
                        "message": "Locked ticket price expired or no longer matches selected seats. Please refresh price and retry.",
                        "code": "PRICE_LOCK_EXPIRED",
                    },
                    status.HTTP_409_CONFLICT,
                )
            price_lock_snapshot = None

        occupancy_snapshot = _showtime_occupancy_snapshot(showtime=showtime, screen=screen)
        existing_sold = set(_collect_sold_labels_for_showtime(showtime, lock=True))
        conflicts = [label for label, _, _ in parsed_labels if label in existing_sold]
        if conflicts:
            return (
                None,
                {
                    "message": "Some selected seats are already sold.",
                    "sold_seats": sorted(conflicts, key=_seat_sort_key),
                },
                status.HTTP_409_CONFLICT,
            )

        seat_records: list[tuple[str, str, str, Seat, SeatAvailability, Optional[Decimal]]] = []
        persisted_seats: list[str] = []
        for label, row_label, seat_number in parsed_labels:
            seat = Seat.objects.filter(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            ).first()
            if not seat:
                return (
                    None,
                    {
                        "message": "Some selected seats do not exist in this hall layout.",
                        "invalid_seats": [label],
                    },
                    status.HTTP_400_BAD_REQUEST,
                )

            availability = (
                SeatAvailability.objects.select_for_update()
                .filter(seat=seat, showtime=showtime)
                .first()
            )
            if not availability:
                availability = SeatAvailability.objects.create(
                    seat=seat,
                    showtime=showtime,
                    seat_status=SEAT_STATUS_AVAILABLE,
                )

            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                return (
                    None,
                    {
                        "message": "Some selected seats are already sold.",
                        "sold_seats": [label],
                    },
                    status.HTTP_409_CONFLICT,
                )
            if current_status == SEAT_STATUS_UNAVAILABLE.lower():
                return (
                    None,
                    {
                        "message": "Some selected seats are unavailable.",
                        "unavailable_seats": [label],
                    },
                    status.HTTP_409_CONFLICT,
                )
            seat_price = _seat_price_from_lock(price_lock_snapshot, label)
            if seat_price is None:
                seat_price, _ = _resolve_dynamic_seat_price(
                    show=show,
                    showtime=showtime,
                    screen=screen,
                    seat_type=seat.seat_type,
                    occupancy_snapshot=occupancy_snapshot,
                    event_name=event_name,
                )
            seat_records.append((label, row_label, seat_number, seat, availability, seat_price))

        computed_total = Decimal("0.00")
        if seat_records:
            for *_, seat_price in seat_records:
                if seat_price is not None:
                    computed_total += seat_price

        subtotal_amount = _parse_price_amount(provided_ticket_total)
        if computed_total > Decimal("0"):
            subtotal_amount = computed_total
        if subtotal_amount is None:
            subtotal_amount = Decimal("0.00")

        coupon = None
        vendor_promo = None
        discount_amount = Decimal("0.00")
        total_amount = subtotal_amount
        loyalty_preview: Optional[dict[str, Any]] = None
        loyalty_points_used = 0
        loyalty_discount_amount = Decimal("0.00")
        subscription_preview: Optional[dict[str, Any]] = None
        subscription_discount_amount = Decimal("0.00")
        subscription_free_tickets_used = 0
        referral_wallet_preview: Optional[dict[str, Any]] = None
        referral_wallet_used_amount = Decimal("0.00")
        if coupon_code:
            seat_categories = [
                seat.seat_type
                for _, _, _, seat, _, _ in seat_records
                if seat and seat.seat_type
            ]
            discount_context = {
                **context,
                "vendor_id": show.vendor_id,
                "show_id": show.id,
                "showtime_id": showtime.id,
                "seat_categories": seat_categories,
                "seat_count": len(seat_records),
                "user_id": user.id,
                "is_student": parse_bool(coalesce(order, "is_student", "isStudent"), default=False),
            }
            coupon_result, coupon_error, coupon_status = _apply_coupon_to_subtotal(
                coupon_code,
                subtotal_amount,
                context=discount_context,
                lock_for_update=True,
                consume=True,
            )
            if coupon_error:
                return None, coupon_error, coupon_status
            if coupon_result.get("coupon"):
                coupon = Coupon.objects.filter(id=coupon_result["coupon"]["id"]).first()
            if coupon_result.get("promo_code"):
                vendor_promo = VendorPromoCode.objects.filter(id=coupon_result["promo_code"]["id"]).first()
            discount_amount = _parse_price_amount(coupon_result.get("discount_amount")) or Decimal("0.00")
            total_amount = _parse_price_amount(coupon_result.get("final_total")) or subtotal_amount

        if requested_reward_id or requested_points_to_redeem > 0:
            loyalty_preview, loyalty_error, loyalty_status = loyalty.preview_checkout_redemption(
                user,
                {
                    "subtotal": float(_quantize_money(total_amount)),
                    "reward_id": requested_reward_id,
                    "points_to_redeem": requested_points_to_redeem,
                    "vendor_id": show.vendor_id,
                },
            )
            if loyalty_error:
                return None, loyalty_error, loyalty_status

            loyalty_points_used = int((loyalty_preview or {}).get("total_points_to_use") or 0)
            loyalty_discount_amount = _parse_price_amount(
                (loyalty_preview or {}).get("total_discount")
            ) or Decimal("0.00")
            if loyalty_discount_amount > Decimal("0"):
                total_amount = _quantize_money(total_amount - loyalty_discount_amount)
                if total_amount < Decimal("0"):
                    total_amount = Decimal("0.00")

        if use_subscription:
            subscription_preview, subscription_error, subscription_status = subscription.preview_checkout_subscription(
                user.id,
                {
                    "subtotal": float(_quantize_money(total_amount)),
                    "vendor_id": show.vendor_id,
                    "seat_count": max(len(seat_records), 1),
                    "user_subscription_id": requested_user_subscription_id,
                    "use_free_ticket": use_subscription_free_ticket,
                    "requested_free_tickets": requested_subscription_free_tickets,
                    "coupon_applied": bool(coupon and discount_amount > Decimal("0")),
                    "loyalty_applied": bool(loyalty_discount_amount > Decimal("0")),
                    "referral_wallet_applied": False,
                },
            )
            if subscription_error:
                return None, subscription_error, subscription_status

            subscription_discount_amount = _parse_price_amount(
                coalesce(subscription_preview or {}, "total_discount", "discount_amount")
            ) or Decimal("0.00")
            subscription_free_tickets_used = int((subscription_preview or {}).get("free_tickets_to_use") or 0)

            if subscription_discount_amount > Decimal("0"):
                total_amount = _quantize_money(total_amount - subscription_discount_amount)
                if total_amount < Decimal("0"):
                    total_amount = Decimal("0.00")

        if use_referral_wallet and subscription_preview:
            plan_payload = (subscription_preview or {}).get("plan")
            if isinstance(plan_payload, dict) and not bool(plan_payload.get("is_stackable_with_referral_wallet", True)):
                return (
                    None,
                    {"message": "Selected subscription cannot be combined with referral wallet credit."},
                    status.HTTP_400_BAD_REQUEST,
                )

        if use_referral_wallet:
            referral_wallet_preview = preview_referral_wallet_usage_for_user(
                user,
                subtotal=total_amount,
                requested_amount=requested_referral_wallet_amount,
            )
            referral_wallet_used_amount = _parse_price_amount(
                referral_wallet_preview.get("applied_amount")
            ) or Decimal("0.00")
            if referral_wallet_used_amount > Decimal("0"):
                total_amount = _quantize_money(total_amount - referral_wallet_used_amount)
                if total_amount < Decimal("0"):
                    total_amount = Decimal("0.00")

        booking_fraud_payload = assess_booking_fraud_risk(
            user=user,
            show=show,
            seat_count=len(seat_records),
            subtotal_amount=subtotal_amount,
            total_amount=total_amount,
            discount_amount=discount_amount,
            loyalty_discount_amount=loyalty_discount_amount,
            subscription_discount_amount=subscription_discount_amount,
            referral_wallet_used_amount=referral_wallet_used_amount,
            source_ip=source_ip,
            user_agent=user_agent,
        )
        fraud_score = int(booking_fraud_payload.get("score") or 0)
        fraud_level = str(booking_fraud_payload.get("level") or Booking.FRAUD_LEVEL_LOW)
        fraud_signals = (
            booking_fraud_payload.get("signals")
            if isinstance(booking_fraud_payload.get("signals"), list)
            else []
        )

        booking = Booking.objects.create(
            user=user,
            showtime=showtime,
            booking_status=BOOKING_STATUS_CONFIRMED,
            total_amount=total_amount,
            coupon=coupon,
            vendor_promo_code=vendor_promo,
            discount_amount=discount_amount,
            loyalty_points_redeemed=loyalty_points_used,
            loyalty_discount_amount=loyalty_discount_amount,
            subscription_discount_amount=subscription_discount_amount,
            subscription_free_tickets_used=subscription_free_tickets_used,
            referral_wallet_used_amount=referral_wallet_used_amount,
            fraud_score=fraud_score,
            fraud_level=fraud_level,
            fraud_signals=fraud_signals,
            source_ip=source_ip,
            user_agent=user_agent,
        )

        for _, row_label, seat_number, seat, availability, seat_price in seat_records:
            availability.seat_status = SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

            BookingSeat.objects.create(
                booking=booking,
                showtime=showtime,
                seat=seat,
                seat_price=seat_price,
            )
            persisted_seats.append(_join_seat_label(row_label, seat_number))

        if loyalty_preview and (loyalty_points_used > 0 or loyalty_preview.get("reward")):
            loyalty_result, loyalty_status = loyalty.consume_checkout_redemption(
                user=user,
                booking=booking,
                preview=loyalty_preview,
            )
            if loyalty_status >= status.HTTP_400_BAD_REQUEST:
                transaction.set_rollback(True)
                return None, loyalty_result, loyalty_status

        if subscription_preview and (
            subscription_discount_amount > Decimal("0")
            or subscription_free_tickets_used > 0
            or (subscription_preview or {}).get("user_subscription_id")
        ):
            subscription_result, subscription_status = subscription.consume_checkout_subscription(
                user_id=user.id,
                booking=booking,
                preview=subscription_preview,
            )
            if subscription_status >= status.HTTP_400_BAD_REQUEST:
                transaction.set_rollback(True)
                return None, subscription_result, subscription_status

        if referral_wallet_used_amount > Decimal("0"):
            _, wallet_error, wallet_status = _debit_referral_wallet(
                user=user,
                amount=referral_wallet_used_amount,
                reason=ReferralTransaction.REASON_BOOKING_WALLET_USE,
                booking=booking,
                metadata={
                    "requested_amount": float(requested_referral_wallet_amount or Decimal("0.00")),
                    "preview": referral_wallet_preview or {},
                },
                require_available_balance=True,
                allow_negative_balance=False,
            )
            if wallet_error:
                transaction.set_rollback(True)
                return None, wallet_error, wallet_status

        transaction.on_commit(lambda booking_id=booking.id, event=event_name: _run_post_booking_rewards(booking_id, event))

    try:
        _notify_booking_created(booking, show)
    except Exception:
        logger.exception("Failed to dispatch booking-created notifications for booking %s", booking.id)
    try:
        _notify_vendor_when_show_fully_booked(show=show, showtime=showtime, screen=screen)
    except Exception:
        logger.exception(
            "Failed to dispatch full-capacity notification for show %s (booking %s)",
            show.id,
            booking.id,
        )

    return (
        {
            "booking_id": booking.id,
            "show_id": show.id,
            "showtime_id": showtime.id,
            "screen": screen.screen_number,
            "referral_wallet_used_amount": float(referral_wallet_used_amount),
            "subscription_discount_amount": float(subscription_discount_amount),
            "subscription_free_tickets_used": int(subscription_free_tickets_used),
            "user_subscription_id": booking.user_subscription_id,
            "price_lock_token": price_lock_token or None,
            "sold_seats": sorted(persisted_seats, key=_seat_sort_key),
            "fraud_score": fraud_score,
            "fraud_level": fraud_level,
            "fraud_signals": fraud_signals,
            "requires_manual_review": bool(booking_fraud_payload.get("requires_manual_review")),
        },
        None,
        status.HTTP_201_CREATED,
    )


def list_sold_seats_for_context(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return sold seat labels for a selected movie/cinema/date/time context."""
    layout_payload, status_code = list_booking_seat_layout(payload)
    sold_labels = list(layout_payload.get("sold_seats") or [])
    unavailable_labels = list(layout_payload.get("unavailable_seats") or [])
    return {
        "sold_seats": sold_labels,
        "soldSeats": sold_labels,
        "unavailable_seats": unavailable_labels,
        "unavailableSeats": unavailable_labels,
        "show_id": layout_payload.get("show_id"),
        "showtime_id": layout_payload.get("showtime_id"),
    }, status_code


def list_available_seats_for_context(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return available seat entries for a selected movie/cinema/date/time context."""
    layout_payload, status_code = list_booking_seat_layout(payload)
    seats = layout_payload.get("seats") if isinstance(layout_payload.get("seats"), list) else []
    available = [seat for seat in seats if str(seat.get("status") or "").lower() == "available"]
    available_labels = [str(seat.get("label") or "").upper() for seat in available if seat.get("label")]
    return {
        "available_seats": available,
        "available_labels": sorted(available_labels, key=_seat_sort_key),
        "show_id": layout_payload.get("show_id"),
        "showtime_id": layout_payload.get("showtime_id"),
        "category_prices": layout_payload.get("category_prices") or {},
    }, status_code


def _build_pricing_rule_payload(rule: PricingRule) -> dict[str, Any]:
    """Serialize one pricing rule for API responses."""
    return {
        "id": rule.id,
        "name": rule.name,
        "vendor_id": rule.vendor_id,
        "is_global": rule.vendor_id is None,
        "movie_id": rule.movie_id,
        "hall": rule.hall,
        "seat_category": rule.seat_category,
        "day_of_week": getattr(rule, "day_of_week", PricingRule.DAY_OF_WEEK_ALL),
        "start_time": rule.start_time.strftime("%H:%M") if getattr(rule, "start_time", None) else None,
        "end_time": rule.end_time.strftime("%H:%M") if getattr(rule, "end_time", None) else None,
        "occupancy_threshold": float(rule.occupancy_threshold) if getattr(rule, "occupancy_threshold", None) is not None else None,
        "price_multiplier": float(rule.price_multiplier) if getattr(rule, "price_multiplier", None) is not None else None,
        "flat_adjustment": float(rule.flat_adjustment) if getattr(rule, "flat_adjustment", None) is not None else None,
        "min_price_cap": float(rule.min_price_cap) if getattr(rule, "min_price_cap", None) is not None else None,
        "max_price_cap": float(rule.max_price_cap) if getattr(rule, "max_price_cap", None) is not None else None,
        "day_type": rule.day_type,
        "is_festival_pricing": bool(rule.is_festival_pricing),
        "festival_name": rule.festival_name,
        "start_date": rule.start_date.isoformat() if rule.start_date else None,
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "adjustment_type": rule.adjustment_type,
        "adjustment_value": float(rule.adjustment_value),
        "priority": int(rule.priority or 0),
        "is_active": bool(rule.is_active),
    }


def _clean_pricing_rule_input(payload: dict[str, Any], partial: bool = False) -> tuple[dict[str, Any], Optional[str]]:
    """Validate and normalize pricing rule request payload."""
    cleaned: dict[str, Any] = {}

    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            return {}, "name is required."
        cleaned["name"] = name[:120]

    if "movie_id" in payload or "movieId" in payload:
        movie_id = _coerce_int(coalesce(payload, "movie_id", "movieId"))
        cleaned["movie_id"] = movie_id

    if "hall" in payload:
        cleaned["hall"] = str(payload.get("hall") or "").strip() or None

    if not partial or "seat_category" in payload or "seatCategory" in payload:
        seat_category = str(coalesce(payload, "seat_category", "seatCategory") or PricingRule.SEAT_CATEGORY_ALL).upper()
        allowed = {
            PricingRule.SEAT_CATEGORY_ALL,
            PricingRule.SEAT_CATEGORY_NORMAL,
            PricingRule.SEAT_CATEGORY_EXECUTIVE,
            PricingRule.SEAT_CATEGORY_PREMIUM,
            PricingRule.SEAT_CATEGORY_VIP,
            PricingRule.SEAT_CATEGORY_SILVER,
            PricingRule.SEAT_CATEGORY_GOLD,
            PricingRule.SEAT_CATEGORY_PLATINUM,
        }
        if seat_category not in allowed:
            return {}, "seat_category is invalid."
        cleaned["seat_category"] = seat_category

    if not partial or "day_of_week" in payload or "dayOfWeek" in payload:
        day_of_week = str(
            coalesce(payload, "day_of_week", "dayOfWeek") or PricingRule.DAY_OF_WEEK_ALL
        ).upper()
        allowed = {
            PricingRule.DAY_OF_WEEK_ALL,
            PricingRule.DAY_OF_WEEK_WEEKDAY,
            PricingRule.DAY_OF_WEEK_WEEKEND,
            PricingRule.DAY_OF_WEEK_MON,
            PricingRule.DAY_OF_WEEK_TUE,
            PricingRule.DAY_OF_WEEK_WED,
            PricingRule.DAY_OF_WEEK_THU,
            PricingRule.DAY_OF_WEEK_FRI,
            PricingRule.DAY_OF_WEEK_SAT,
            PricingRule.DAY_OF_WEEK_SUN,
        }
        if day_of_week not in allowed:
            return {}, "day_of_week is invalid."
        cleaned["day_of_week"] = day_of_week

    if not partial or "day_type" in payload or "dayType" in payload:
        day_type = str(coalesce(payload, "day_type", "dayType") or PricingRule.DAY_TYPE_ALL).upper()
        allowed = {
            PricingRule.DAY_TYPE_ALL,
            PricingRule.DAY_TYPE_WEEKDAY,
            PricingRule.DAY_TYPE_WEEKEND,
        }
        if day_type not in allowed:
            return {}, "day_type is invalid."
        cleaned["day_type"] = day_type

    if "start_time" in payload or "startTime" in payload:
        cleaned["start_time"] = parse_time(coalesce(payload, "start_time", "startTime"))

    if "end_time" in payload or "endTime" in payload:
        cleaned["end_time"] = parse_time(coalesce(payload, "end_time", "endTime"))

    if "occupancy_threshold" in payload or "occupancyThreshold" in payload:
        occupancy_threshold = _parse_price_amount(
            coalesce(payload, "occupancy_threshold", "occupancyThreshold")
        )
        if occupancy_threshold is None:
            return {}, "occupancy_threshold must be a number between 0 and 100."
        if occupancy_threshold > Decimal("100"):
            return {}, "occupancy_threshold cannot exceed 100."
        cleaned["occupancy_threshold"] = occupancy_threshold

    if "price_multiplier" in payload or "priceMultiplier" in payload:
        price_multiplier = _parse_price_amount(
            coalesce(payload, "price_multiplier", "priceMultiplier")
        )
        if price_multiplier is None or price_multiplier <= Decimal("0"):
            return {}, "price_multiplier must be a positive number."
        cleaned["price_multiplier"] = price_multiplier.quantize(Decimal("0.0001"))

    if "flat_adjustment" in payload or "flatAdjustment" in payload:
        flat_adjustment = _parse_signed_price_amount(
            coalesce(payload, "flat_adjustment", "flatAdjustment")
        )
        if flat_adjustment is None:
            return {}, "flat_adjustment must be a valid number."
        cleaned["flat_adjustment"] = flat_adjustment

    if "min_price_cap" in payload or "minPriceCap" in payload:
        min_price_cap = _parse_price_amount(coalesce(payload, "min_price_cap", "minPriceCap"))
        if min_price_cap is None:
            return {}, "min_price_cap must be a valid non-negative number."
        cleaned["min_price_cap"] = min_price_cap

    if "max_price_cap" in payload or "maxPriceCap" in payload:
        max_price_cap = _parse_price_amount(coalesce(payload, "max_price_cap", "maxPriceCap"))
        if max_price_cap is None:
            return {}, "max_price_cap must be a valid non-negative number."
        cleaned["max_price_cap"] = max_price_cap

    if cleaned.get("min_price_cap") is not None and cleaned.get("max_price_cap") is not None:
        if cleaned["min_price_cap"] > cleaned["max_price_cap"]:
            return {}, "min_price_cap cannot be greater than max_price_cap."

    if "is_festival_pricing" in payload or "isFestivalPricing" in payload:
        cleaned["is_festival_pricing"] = parse_bool(
            coalesce(payload, "is_festival_pricing", "isFestivalPricing"),
            default=False,
        )

    if "festival_name" in payload or "festivalName" in payload:
        cleaned["festival_name"] = str(coalesce(payload, "festival_name", "festivalName") or "").strip() or None

    if "start_date" in payload or "startDate" in payload:
        cleaned["start_date"] = parse_date(coalesce(payload, "start_date", "startDate"))
    if "end_date" in payload or "endDate" in payload:
        cleaned["end_date"] = parse_date(coalesce(payload, "end_date", "endDate"))
    if cleaned.get("start_date") and cleaned.get("end_date") and cleaned["start_date"] > cleaned["end_date"]:
        return {}, "start_date must be on or before end_date."

    has_modern_adjustment = any(
        key in payload
        for key in (
            "price_multiplier",
            "priceMultiplier",
            "flat_adjustment",
            "flatAdjustment",
        )
    )

    if (
        not partial
        and not has_modern_adjustment
        and "adjustment_type" not in payload
        and "adjustmentType" not in payload
    ):
        cleaned["adjustment_type"] = PricingRule.ADJUSTMENT_INCREMENT
    elif "adjustment_type" in payload or "adjustmentType" in payload or (not partial and not has_modern_adjustment):
        adjustment_type = str(
            coalesce(payload, "adjustment_type", "adjustmentType") or PricingRule.ADJUSTMENT_INCREMENT
        ).upper()
        allowed = {
            PricingRule.ADJUSTMENT_FIXED,
            PricingRule.ADJUSTMENT_INCREMENT,
            PricingRule.ADJUSTMENT_PERCENT,
            PricingRule.ADJUSTMENT_MULTIPLIER,
        }
        if adjustment_type not in allowed:
            return {}, "adjustment_type is invalid."
        cleaned["adjustment_type"] = adjustment_type

    if (
        not partial
        and not has_modern_adjustment
        and "adjustment_value" not in payload
        and "adjustmentValue" not in payload
    ):
        cleaned["adjustment_value"] = Decimal("0.00")
    elif "adjustment_value" in payload or "adjustmentValue" in payload or (not partial and not has_modern_adjustment):
        adjustment_value = _parse_signed_price_amount(coalesce(payload, "adjustment_value", "adjustmentValue"))
        if adjustment_value is None:
            return {}, "adjustment_value must be a valid number."
        cleaned["adjustment_value"] = adjustment_value

    if not partial and not has_modern_adjustment:
        has_legacy_adjustment = cleaned.get("adjustment_value") is not None
        if not has_legacy_adjustment:
            return {}, "Provide either price_multiplier/flat_adjustment or adjustment_value."

    if not partial and has_modern_adjustment and "adjustment_value" not in cleaned:
        cleaned["adjustment_value"] = Decimal("0.00")
    if not partial and has_modern_adjustment and "adjustment_type" not in cleaned:
        cleaned["adjustment_type"] = PricingRule.ADJUSTMENT_INCREMENT

    if "priority" in payload:
        cleaned["priority"] = _parse_positive_int(payload.get("priority"), default=100, minimum=1, maximum=9999)

    if "is_active" in payload or "isActive" in payload:
        cleaned["is_active"] = parse_bool(coalesce(payload, "is_active", "isActive"), default=True)

    return cleaned, None

def get_vendor_cancellation_policy(request: Any) -> tuple[dict[str, Any], int]:
    """Return vendor cancellation policy, optionally scoped to a screen/hall."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    screen_id = _coerce_int(
        coalesce(request.query_params, "screen_id", "screenId", "hall_id", "hallId")
    )
    screen = None
    if screen_id:
        screen = Screen.objects.filter(id=screen_id, vendor_id=vendor.id).first()
        if not screen:
            return {"message": "screen_id is invalid for this vendor."}, status.HTTP_400_BAD_REQUEST

    if screen:
        policy = VendorCancellationPolicy.objects.filter(
            vendor_id=vendor.id,
            screen_id=screen.id,
        ).select_related("screen").first()
        if policy:
            return {"policy": _serialize_cancellation_policy(policy)}, status.HTTP_200_OK

    default_policy = VendorCancellationPolicy.objects.filter(
        vendor_id=vendor.id,
        screen__isnull=True,
    ).first()
    if default_policy:
        payload = _serialize_cancellation_policy(default_policy)
        if screen and not payload.get("screen_id"):
            payload["screen_id"] = screen.id
            payload["screen_number"] = screen.screen_number
            payload["source"] = "VENDOR_DEFAULT_FALLBACK"
        return {"policy": payload}, status.HTTP_200_OK

    return {
        "policy": _default_cancellation_policy_payload(vendor=vendor, screen=screen),
    }, status.HTTP_200_OK


def update_vendor_cancellation_policy(request: Any) -> tuple[dict[str, Any], int]:
    """Create or update vendor cancellation policy for default scope or one screen."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    screen_id = _coerce_int(
        coalesce(payload, "screen_id", "screenId", "hall_id", "hallId")
        or coalesce(request.query_params, "screen_id", "screenId", "hall_id", "hallId")
    )
    screen = None
    if screen_id:
        screen = Screen.objects.filter(id=screen_id, vendor_id=vendor.id).first()
        if not screen:
            return {"message": "screen_id is invalid for this vendor."}, status.HTTP_400_BAD_REQUEST

    policy, created = VendorCancellationPolicy.objects.get_or_create(
        vendor_id=vendor.id,
        screen_id=screen.id if screen else None,
    )

    changed = False
    if "allow_customer_cancellation" in payload or "allowCustomerCancellation" in payload:
        policy.allow_customer_cancellation = parse_bool(
            coalesce(payload, "allow_customer_cancellation", "allowCustomerCancellation"),
            default=True,
        )
        changed = True

    if "is_active" in payload or "isActive" in payload:
        policy.is_active = parse_bool(coalesce(payload, "is_active", "isActive"), default=True)
        changed = True

    if "refund_percent_2h_plus" in payload or "refundPercent2hPlus" in payload:
        policy.refund_percent_2h_plus = _percent_decimal(
            coalesce(payload, "refund_percent_2h_plus", "refundPercent2hPlus"),
            DEFAULT_REFUND_PERCENT_2H_PLUS,
        )
        changed = True

    if "refund_percent_1_to_2h" in payload or "refundPercent1to2h" in payload:
        policy.refund_percent_1_to_2h = _percent_decimal(
            coalesce(payload, "refund_percent_1_to_2h", "refundPercent1to2h"),
            DEFAULT_REFUND_PERCENT_1_TO_2H,
        )
        changed = True

    if "refund_percent_less_than_1h" in payload or "refundPercentLessThan1h" in payload:
        policy.refund_percent_less_than_1h = _percent_decimal(
            coalesce(payload, "refund_percent_less_than_1h", "refundPercentLessThan1h"),
            DEFAULT_REFUND_PERCENT_LESS_THAN_1H,
        )
        changed = True

    if "note" in payload:
        policy.note = str(payload.get("note") or "").strip() or None
        changed = True

    if not changed and not created:
        return {
            "message": "No policy updates provided.",
            "policy": _serialize_cancellation_policy(policy),
        }, status.HTTP_400_BAD_REQUEST

    policy.save()
    message = "Cancellation policy created." if created else "Cancellation policy updated."
    return {
        "message": message,
        "policy": _serialize_cancellation_policy(policy),
    }, status.HTTP_200_OK


def list_vendor_pricing_rules(request: Any) -> list[dict[str, Any]]:
    """List pricing rules for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return []

    include_global = parse_bool(
        coalesce(request.query_params, "include_global", "includeGlobal"),
        default=True,
    )
    queryset = PricingRule.objects.filter(vendor_id=vendor.id)
    if include_global:
        queryset = PricingRule.objects.filter(Q(vendor_id=vendor.id) | Q(vendor__isnull=True))

    movie_id = _coerce_int(coalesce(request.query_params, "movie_id", "movieId"))
    if movie_id:
        queryset = queryset.filter(Q(movie_id=movie_id) | Q(movie_id__isnull=True))

    if "is_active" in request.query_params or "isActive" in request.query_params:
        is_active = parse_bool(coalesce(request.query_params, "is_active", "isActive"), default=True)
        queryset = queryset.filter(is_active=is_active)

    rules = list(queryset.order_by("priority", "id"))
    if include_global:
        vendor_rules = [rule for rule in rules if rule.vendor_id == vendor.id]
        global_rules = [rule for rule in rules if rule.vendor_id is None]
        vendor_override_keys = {_pricing_rule_override_key(rule) for rule in vendor_rules}
        rules = vendor_rules + [
            rule for rule in global_rules if _pricing_rule_override_key(rule) not in vendor_override_keys
        ]
        rules = sorted(rules, key=lambda item: (int(item.priority or 0), int(item.id or 0)))

    return [_build_pricing_rule_payload(rule) for rule in rules]


def create_vendor_pricing_rule(request: Any) -> tuple[dict[str, Any], int]:
    """Create a pricing rule for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    cleaned, error = _clean_pricing_rule_input(payload, partial=False)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    movie_id = cleaned.get("movie_id")
    if movie_id and not Movie.objects.filter(pk=movie_id).exists():
        return {"message": "movie_id is invalid."}, status.HTTP_400_BAD_REQUEST

    rule = PricingRule.objects.create(vendor_id=vendor.id, **cleaned)
    return {"message": "Pricing rule created.", "rule": _build_pricing_rule_payload(rule)}, status.HTTP_201_CREATED


def update_vendor_pricing_rule(request: Any, rule: PricingRule) -> tuple[dict[str, Any], int]:
    """Update one vendor pricing rule."""
    payload = get_payload(request)
    cleaned, error = _clean_pricing_rule_input(payload, partial=True)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST
    if not cleaned:
        return {"message": "No pricing rule changes provided."}, status.HTTP_400_BAD_REQUEST

    movie_id = cleaned.get("movie_id")
    if movie_id and not Movie.objects.filter(pk=movie_id).exists():
        return {"message": "movie_id is invalid."}, status.HTTP_400_BAD_REQUEST

    for key, value in cleaned.items():
        setattr(rule, key, value)
    rule.save()
    return {"message": "Pricing rule updated.", "rule": _build_pricing_rule_payload(rule)}, status.HTTP_200_OK


def delete_vendor_pricing_rule(rule: PricingRule) -> tuple[dict[str, Any], int]:
    """Delete one vendor pricing rule."""
    rule.delete()
    return {"message": "Pricing rule deleted."}, status.HTTP_200_OK


def list_admin_pricing_rules(request: Any) -> tuple[dict[str, Any], int]:
    """List pricing rules for admin with optional scope filters."""
    queryset = PricingRule.objects.all()

    scope = str(coalesce(request.query_params, "scope") or "ALL").strip().upper()
    vendor_id = _coerce_int(coalesce(request.query_params, "vendor_id", "vendorId"))
    if scope == "GLOBAL":
        queryset = queryset.filter(vendor__isnull=True)
    elif scope == "VENDOR":
        queryset = queryset.filter(vendor__isnull=False)

    if vendor_id is not None:
        queryset = queryset.filter(vendor_id=vendor_id)

    movie_id = _coerce_int(coalesce(request.query_params, "movie_id", "movieId"))
    if movie_id:
        queryset = queryset.filter(Q(movie_id=movie_id) | Q(movie_id__isnull=True))

    if "is_active" in request.query_params or "isActive" in request.query_params:
        is_active = parse_bool(coalesce(request.query_params, "is_active", "isActive"), default=True)
        queryset = queryset.filter(is_active=is_active)

    rules = [_build_pricing_rule_payload(rule) for rule in queryset.order_by("priority", "id")]
    return {"rules": rules}, status.HTTP_200_OK


def create_admin_pricing_rule(request: Any) -> tuple[dict[str, Any], int]:
    """Create admin pricing rule scoped globally or to a vendor."""
    payload = get_payload(request)
    cleaned, error = _clean_pricing_rule_input(payload, partial=False)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    vendor_id = _coerce_int(coalesce(payload, "vendor_id", "vendorId"))
    if vendor_id is not None and not Vendor.objects.filter(pk=vendor_id).exists():
        return {"message": "vendor_id is invalid."}, status.HTTP_400_BAD_REQUEST

    movie_id = cleaned.get("movie_id")
    if movie_id and not Movie.objects.filter(pk=movie_id).exists():
        return {"message": "movie_id is invalid."}, status.HTTP_400_BAD_REQUEST

    rule = PricingRule.objects.create(vendor_id=vendor_id, **cleaned)
    return {
        "message": "Pricing rule created.",
        "rule": _build_pricing_rule_payload(rule),
    }, status.HTTP_201_CREATED


def update_admin_pricing_rule(request: Any, rule: PricingRule) -> tuple[dict[str, Any], int]:
    """Update one admin pricing rule, including vendor/global scope changes."""
    payload = get_payload(request)
    cleaned, error = _clean_pricing_rule_input(payload, partial=True)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    if "vendor_id" in payload or "vendorId" in payload:
        next_vendor_id = _coerce_int(coalesce(payload, "vendor_id", "vendorId"))
        if next_vendor_id is not None and not Vendor.objects.filter(pk=next_vendor_id).exists():
            return {"message": "vendor_id is invalid."}, status.HTTP_400_BAD_REQUEST
        cleaned["vendor_id"] = next_vendor_id

    if not cleaned:
        return {"message": "No pricing rule changes provided."}, status.HTTP_400_BAD_REQUEST

    movie_id = cleaned.get("movie_id")
    if movie_id and not Movie.objects.filter(pk=movie_id).exists():
        return {"message": "movie_id is invalid."}, status.HTTP_400_BAD_REQUEST

    for key, value in cleaned.items():
        setattr(rule, key, value)
    rule.save()
    return {
        "message": "Pricing rule updated.",
        "rule": _build_pricing_rule_payload(rule),
    }, status.HTTP_200_OK


def delete_admin_pricing_rule(rule: PricingRule) -> tuple[dict[str, Any], int]:
    """Delete one admin pricing rule."""
    rule.delete()
    return {"message": "Pricing rule deleted."}, status.HTTP_200_OK


def _serialize_show_base_price_payload(item: ShowBasePrice) -> dict[str, Any]:
    return {
        "id": item.id,
        "show_id": item.show_id,
        "seat_category": item.seat_category,
        "base_price": float(item.base_price),
        "is_active": bool(item.is_active),
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def list_vendor_show_base_prices(request: Any) -> tuple[dict[str, Any], int]:
    """List per-show base prices for the authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    show_id = _coerce_int(coalesce(request.query_params, "show_id", "showId"))
    if not show_id:
        return {"message": "show_id is required."}, status.HTTP_400_BAD_REQUEST

    show = Show.objects.filter(id=show_id, vendor_id=vendor.id).first()
    if not show:
        return {"message": "show_id is invalid for this vendor."}, status.HTTP_400_BAD_REQUEST

    rows = list(ShowBasePrice.objects.filter(show_id=show.id).order_by("seat_category", "id"))
    return {
        "show_id": show.id,
        "movie_id": show.movie_id,
        "hall": show.hall,
        "base_prices": [_serialize_show_base_price_payload(item) for item in rows],
    }, status.HTTP_200_OK


def upsert_vendor_show_base_prices(request: Any) -> tuple[dict[str, Any], int]:
    """Create or update per-show category base prices for vendor pricing engine."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    show_id = _coerce_int(coalesce(payload, "show_id", "showId"))
    if not show_id:
        return {"message": "show_id is required."}, status.HTTP_400_BAD_REQUEST

    show = Show.objects.filter(id=show_id, vendor_id=vendor.id).first()
    if not show:
        return {"message": "show_id is invalid for this vendor."}, status.HTTP_400_BAD_REQUEST

    incoming = payload.get("base_prices") if isinstance(payload.get("base_prices"), list) else []
    if not incoming and isinstance(payload.get("prices"), list):
        incoming = payload.get("prices")

    if not incoming:
        single = {
            "seat_category": coalesce(payload, "seat_category", "seatCategory"),
            "base_price": coalesce(payload, "base_price", "basePrice", "price"),
            "is_active": coalesce(payload, "is_active", "isActive", default=True),
        }
        if single.get("seat_category") is not None:
            incoming = [single]

    if not incoming:
        return {"message": "base_prices payload is required."}, status.HTTP_400_BAD_REQUEST

    allowed_categories = {
        PricingRule.SEAT_CATEGORY_NORMAL,
        PricingRule.SEAT_CATEGORY_EXECUTIVE,
        PricingRule.SEAT_CATEGORY_PREMIUM,
        PricingRule.SEAT_CATEGORY_VIP,
        PricingRule.SEAT_CATEGORY_SILVER,
        PricingRule.SEAT_CATEGORY_GOLD,
        PricingRule.SEAT_CATEGORY_PLATINUM,
    }

    with transaction.atomic():
        for row in incoming:
            if not isinstance(row, dict):
                return {"message": "Each base_prices item must be an object."}, status.HTTP_400_BAD_REQUEST

            seat_category = str(coalesce(row, "seat_category", "seatCategory") or "").strip().upper()
            if seat_category not in allowed_categories:
                return {"message": f"Invalid seat_category: {seat_category or 'blank'}."}, status.HTTP_400_BAD_REQUEST

            base_price = _parse_price_amount(coalesce(row, "base_price", "basePrice", "price"))
            if base_price is None:
                return {"message": f"base_price is required for {seat_category}."}, status.HTTP_400_BAD_REQUEST

            is_active = parse_bool(coalesce(row, "is_active", "isActive"), default=True)

            ShowBasePrice.objects.update_or_create(
                show_id=show.id,
                seat_category=seat_category,
                defaults={
                    "base_price": base_price,
                    "is_active": is_active,
                },
            )

    rows = list(ShowBasePrice.objects.filter(show_id=show.id).order_by("seat_category", "id"))
    return {
        "message": "Show base prices updated.",
        "show_id": show.id,
        "base_prices": [_serialize_show_base_price_payload(item) for item in rows],
    }, status.HTTP_200_OK


def get_show_dynamic_prices(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return real-time dynamic category prices for a show context."""
    context = _resolve_booking_context(payload)
    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND

    hall = str(context.get("hall") or show.hall or "").strip() or None
    showtime = _find_showtime_for_context(show, hall)
    screen = None
    if hall:
        screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=hall).first()
    if not screen and showtime:
        screen = showtime.screen
    if not screen:
        screen = Screen.objects.filter(vendor_id=show.vendor_id).order_by("id").first()

    event_name = str(coalesce(payload, "event", "event_name", "festival", "festival_name") or "").strip()

    cache_key = (
        f"{PRICING_CATEGORY_CACHE_PREFIX}{show.id}:"
        f"{showtime.id if showtime else 'na'}:{(event_name or '').lower()}"
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached, status.HTTP_200_OK

    occupancy = _showtime_occupancy_snapshot(showtime=showtime, screen=screen)

    categories: list[tuple[str, str]] = [
        ("normal", SEAT_CATEGORY_NORMAL),
        ("executive", SEAT_CATEGORY_EXECUTIVE),
        ("premium", SEAT_CATEGORY_PREMIUM),
        ("vip", SEAT_CATEGORY_VIP),
    ]
    category_payload: dict[str, Any] = {}
    for key, seat_type in categories:
        base_price = _seat_price_for_category(screen=screen, showtime=showtime, seat_type=seat_type, show=show)
        final_price, applied_rules = _resolve_dynamic_seat_price(
            show=show,
            showtime=showtime,
            screen=screen,
            seat_type=seat_type,
            occupancy_snapshot=occupancy,
            event_name=event_name,
        )
        category_payload[key] = {
            "seat_type": seat_type,
            "base_price": float(base_price) if base_price is not None else None,
            "dynamic_price": float(final_price) if final_price is not None else None,
            "rule_count": len(applied_rules),
        }

    response_payload = {
        "show_id": show.id,
        "showtime_id": showtime.id if showtime else None,
        "hall": hall or (screen.screen_number if screen else None),
        "occupancy": occupancy,
        "categories": category_payload,
        "indicator": "Price may increase as seats fill.",
        "currency": "NPR",
    }
    cache.set(cache_key, response_payload, timeout=PRICING_CATEGORY_CACHE_TTL_SECONDS)
    return response_payload, status.HTTP_200_OK


def _settlement_status_for_amounts(amount_paid: Any, total_amount: Any) -> str:
    """Return a simple settlement state for partial invoice tracking."""
    paid_value = _quantize_money(_parse_price_amount(amount_paid) or Decimal("0"))
    total_value = _quantize_money(_parse_price_amount(total_amount) or Decimal("0"))
    if paid_value <= Decimal("0"):
        return "UNSETTLED"
    if paid_value >= total_value:
        return "SETTLED"
    return "PARTIALLY_SETTLED"


def _serialize_private_screening_request(item: PrivateScreeningRequest) -> dict[str, Any]:
    """Serialize private screening request for API responses."""
    invoice_total_amount = _quantize_money(item.invoice_total_amount or Decimal("0"))
    amount_paid = _quantize_money(item.amount_paid or Decimal("0"))
    return {
        "id": item.id,
        "requester_type": item.requester_type,
        "organization_name": item.organization_name,
        "contact_person": item.contact_person,
        "contact_email": item.contact_email,
        "contact_phone": item.contact_phone,
        "preferred_date": item.preferred_date.isoformat() if item.preferred_date else None,
        "preferred_start_time": item.preferred_start_time.strftime("%H:%M") if item.preferred_start_time else None,
        "attendee_count": item.attendee_count,
        "preferred_movie_title": item.preferred_movie_title,
        "hall_preference": item.hall_preference,
        "special_requirements": item.special_requirements,
        "estimated_budget": float(item.estimated_budget) if item.estimated_budget is not None else None,
        "invoice_total_amount": float(invoice_total_amount),
        "amount_paid": float(amount_paid),
        "balance_due": float(max(invoice_total_amount - amount_paid, Decimal("0"))),
        "settlement_status": item.settlement_status or _settlement_status_for_amounts(amount_paid, invoice_total_amount),
        "status": item.status,
        "vendor_id": item.vendor_id,
        "vendor_name": item.vendor.name if item.vendor else None,
        "vendor_notes": item.vendor_notes,
        "quoted_amount": float(item.quoted_amount) if item.quoted_amount is not None else None,
        "counter_offer_amount": float(item.counter_offer_amount) if item.counter_offer_amount is not None else None,
        "invoice_number": item.invoice_number,
        "invoice_notes": item.invoice_notes,
        "invoiced_at": item.invoiced_at.isoformat() if item.invoiced_at else None,
        "finalized_at": item.finalized_at.isoformat() if item.finalized_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def create_private_screening_request(request: Any) -> tuple[dict[str, Any], int]:
    """Create a private screening quote request."""
    payload = get_payload(request)

    organization_name = str(coalesce(payload, "organization_name", "organizationName", "company_name", "companyName") or "").strip()
    contact_person = str(coalesce(payload, "contact_person", "contactPerson", "name") or "").strip()
    contact_email = str(coalesce(payload, "contact_email", "contactEmail", "email") or "").strip()
    if not organization_name or not contact_person or not contact_email:
        return {
            "message": "organization_name, contact_person, and contact_email are required.",
        }, status.HTTP_400_BAD_REQUEST

    attendee_count = _parse_positive_int(
        coalesce(payload, "attendee_count", "attendeeCount", "group_size", "groupSize"),
        default=0,
        minimum=1,
        maximum=5000,
    )
    if attendee_count <= 0:
        return {"message": "attendee_count must be at least 1."}, status.HTTP_400_BAD_REQUEST

    preferred_date = parse_date(coalesce(payload, "preferred_date", "preferredDate", "date"))
    preferred_start_time = parse_time(coalesce(payload, "preferred_start_time", "preferredStartTime", "time"))

    vendor = None
    vendor_id = _coerce_int(coalesce(payload, "vendor_id", "vendorId"))
    if vendor_id:
        vendor = Vendor.objects.filter(pk=vendor_id, is_active=True).exclude(status__iexact=STATUS_BLOCKED).first()
        if not vendor:
            return {"message": "vendor_id is invalid."}, status.HTTP_400_BAD_REQUEST

    estimated_budget = _parse_price_amount(coalesce(payload, "estimated_budget", "estimatedBudget", "budget"))
    if estimated_budget is not None and estimated_budget < Decimal("0"):
        return {"message": "estimated_budget must be non-negative."}, status.HTTP_400_BAD_REQUEST

    item = PrivateScreeningRequest.objects.create(
        requester_type=str(coalesce(payload, "requester_type", "requesterType", "type") or "").strip() or None,
        organization_name=organization_name,
        contact_person=contact_person,
        contact_email=contact_email,
        contact_phone=str(coalesce(payload, "contact_phone", "contactPhone", "phone") or "").strip() or None,
        preferred_date=preferred_date,
        preferred_start_time=preferred_start_time,
        attendee_count=attendee_count,
        preferred_movie_title=str(coalesce(payload, "preferred_movie_title", "preferredMovieTitle", "movie_title", "movieTitle") or "").strip() or None,
        hall_preference=str(coalesce(payload, "hall_preference", "hallPreference", "hall") or "").strip() or None,
        special_requirements=str(coalesce(payload, "special_requirements", "specialRequirements", "requirements") or "").strip() or None,
        estimated_budget=estimated_budget,
        vendor=vendor,
    )

    item.invoice_total_amount = estimated_budget or Decimal("0.00")
    item.amount_paid = Decimal("0.00")
    item.settlement_status = _settlement_status_for_amounts(item.amount_paid, item.invoice_total_amount)
    item.save(update_fields=["invoice_total_amount", "amount_paid", "settlement_status"])

    if vendor:
        _create_notification(
            recipient_role=Notification.ROLE_VENDOR,
            recipient_id=vendor.id,
            recipient_email=vendor.email,
            event_type=Notification.EVENT_SHOW_UPDATE,
            title="New private screening request",
            message=f"{organization_name} requested a private screening quote.",
            metadata={"screening_request_id": item.id},
            send_email_too=False,
        )

    return {
        "message": "Private screening request submitted.",
        "request": _serialize_private_screening_request(item),
    }, status.HTTP_201_CREATED


def list_vendor_private_screening_requests(request: Any) -> tuple[dict[str, Any], int]:
    """List private screening requests for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    queryset = PrivateScreeningRequest.objects.filter(vendor_id=vendor.id)
    status_filter = str(coalesce(request.query_params, "status") or "").strip().upper()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    items = list(queryset.order_by("-created_at", "-id")[:300])
    return {
        "requests": [_serialize_private_screening_request(item) for item in items],
    }, status.HTTP_200_OK


def update_vendor_private_screening_request(request: Any, item: PrivateScreeningRequest) -> tuple[dict[str, Any], int]:
    """Update private screening request with vendor quote/counter/invoice actions."""
    payload = get_payload(request)

    next_status = str(coalesce(payload, "status", "action") or "").strip().upper()
    allowed_statuses = {
        PrivateScreeningRequest.STATUS_REVIEWED,
        PrivateScreeningRequest.STATUS_COUNTERED,
        PrivateScreeningRequest.STATUS_ACCEPTED,
        PrivateScreeningRequest.STATUS_REJECTED,
        PrivateScreeningRequest.STATUS_INVOICED,
        PrivateScreeningRequest.STATUS_COMPLETED,
    }
    if next_status and next_status not in allowed_statuses:
        return {"message": "status/action is invalid."}, status.HTTP_400_BAD_REQUEST

    quoted_amount = _parse_price_amount(coalesce(payload, "quoted_amount", "quotedAmount"))
    counter_offer = _parse_price_amount(coalesce(payload, "counter_offer_amount", "counterOfferAmount"))
    if quoted_amount is not None and quoted_amount < Decimal("0"):
        return {"message": "quoted_amount must be non-negative."}, status.HTTP_400_BAD_REQUEST
    if counter_offer is not None and counter_offer < Decimal("0"):
        return {"message": "counter_offer_amount must be non-negative."}, status.HTTP_400_BAD_REQUEST

    if quoted_amount is not None:
        item.quoted_amount = quoted_amount
    if counter_offer is not None:
        item.counter_offer_amount = counter_offer

    invoice_total_amount = _parse_price_amount(coalesce(payload, "invoice_total_amount", "invoiceTotalAmount"))
    if invoice_total_amount is not None:
        item.invoice_total_amount = invoice_total_amount

    amount_paid = _parse_price_amount(coalesce(payload, "amount_paid", "amountPaid", "paid_amount", "paidAmount"))
    if amount_paid is not None:
        item.amount_paid = amount_paid

    if "vendor_notes" in payload or "vendorNotes" in payload:
        item.vendor_notes = str(coalesce(payload, "vendor_notes", "vendorNotes") or "").strip() or None
    if "invoice_notes" in payload or "invoiceNotes" in payload:
        item.invoice_notes = str(coalesce(payload, "invoice_notes", "invoiceNotes") or "").strip() or None
    if "invoice_number" in payload or "invoiceNumber" in payload:
        item.invoice_number = str(coalesce(payload, "invoice_number", "invoiceNumber") or "").strip() or None

    if next_status:
        item.status = next_status
        if next_status == PrivateScreeningRequest.STATUS_INVOICED:
            item.invoiced_at = timezone.now()
            if not item.invoice_number:
                item.invoice_number = f"INV-{item.id}-{timezone.now().strftime('%Y%m%d')}"
            if item.invoice_total_amount <= Decimal("0"):
                fallback_total = item.counter_offer_amount or item.quoted_amount or item.estimated_budget or Decimal("0")
                item.invoice_total_amount = _quantize_money(fallback_total)
        if next_status == PrivateScreeningRequest.STATUS_COMPLETED:
            item.finalized_at = timezone.now()

    item.settlement_status = _settlement_status_for_amounts(item.amount_paid, item.invoice_total_amount)

    item.save()

    return {
        "message": "Private screening request updated.",
        "request": _serialize_private_screening_request(item),
    }, status.HTTP_200_OK


def _serialize_bulk_ticket_item(
    item: BulkTicketItem,
    request: Any,
    *,
    include_qr: bool = False,
) -> dict[str, Any]:
    """Serialize one bulk ticket item with optional QR payload."""
    reference = item.ticket.reference
    details_url = request.build_absolute_uri(f"/api/ticket/{reference}/details/")
    payload: dict[str, Any] = {
        "id": item.id,
        "ticket_id": str(item.ticket.ticket_id) if item.ticket and item.ticket.ticket_id else None,
        "reference": reference,
        "employee_code": item.employee_code,
        "recipient_name": item.recipient_name,
        "recipient_email": item.recipient_email,
        "status": item.status,
        "details_url": details_url,
        "download_url": request.build_absolute_uri(f"/api/ticket/{reference}/download/"),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }
    if include_qr:
        qr_payload = build_ticket_qr_payload(item.ticket)
        qr_image = _build_qr_image(json.dumps(qr_payload, separators=(",", ":")))
        payload["qr_payload"] = qr_payload
        payload["qr_code"] = _image_to_data_url(qr_image) if qr_image else None
    return payload


def _serialize_bulk_ticket_batch(batch: BulkTicketBatch) -> dict[str, Any]:
    """Serialize a bulk ticket batch summary."""
    tickets = list(batch.tickets.all())
    total_count = len(tickets)
    active_count = sum(1 for item in tickets if item.status == BulkTicketItem.STATUS_ACTIVE)
    redeemed_count = sum(1 for item in tickets if item.status == BulkTicketItem.STATUS_REDEEMED)
    invoice_total_amount = _quantize_money(batch.invoice_total_amount or batch.total_amount or Decimal("0"))
    amount_paid = _quantize_money(batch.amount_paid or Decimal("0"))
    return {
        "id": batch.id,
        "vendor_id": batch.vendor_id,
        "corporate_name": batch.corporate_name,
        "contact_person": batch.contact_person,
        "contact_email": batch.contact_email,
        "movie_title": batch.movie_title,
        "hall": batch.hall,
        "show_date": batch.show_date.isoformat() if batch.show_date else None,
        "show_time": batch.show_time.strftime("%H:%M") if batch.show_time else None,
        "valid_until": batch.valid_until.isoformat() if batch.valid_until else None,
        "seat_hold_count": int(batch.seat_hold_count or 0),
        "seat_hold_expires_at": batch.seat_hold_expires_at.isoformat() if batch.seat_hold_expires_at else None,
        "unit_price": float(batch.unit_price or Decimal("0")),
        "total_amount": float(batch.total_amount or Decimal("0")),
        "invoice_number": batch.invoice_number,
        "invoice_total_amount": float(invoice_total_amount),
        "amount_paid": float(amount_paid),
        "balance_due": float(max(invoice_total_amount - amount_paid, Decimal("0"))),
        "settlement_status": batch.settlement_status or _settlement_status_for_amounts(amount_paid, invoice_total_amount),
        "status": batch.status,
        "notes": batch.notes,
        "ticket_count": total_count,
        "active_count": active_count,
        "redeemed_count": redeemed_count,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
    }


def create_vendor_bulk_ticket_batch(request: Any) -> tuple[dict[str, Any], int]:
    """Generate many valid ticket references for a corporate batch."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    corporate_name = str(coalesce(payload, "corporate_name", "corporateName", "company_name", "companyName") or "").strip()
    if not corporate_name:
        return {"message": "corporate_name is required."}, status.HTTP_400_BAD_REQUEST

    ticket_count = _parse_positive_int(
        coalesce(payload, "ticket_count", "ticketCount", "quantity", "count"),
        default=0,
        minimum=1,
        maximum=2000,
    )
    if ticket_count <= 0:
        return {"message": "ticket_count must be between 1 and 2000."}, status.HTTP_400_BAD_REQUEST

    unit_price = _parse_price_amount(coalesce(payload, "unit_price", "unitPrice", "price"))
    if unit_price is None:
        unit_price = Decimal("0.00")
    if unit_price < Decimal("0.00"):
        return {"message": "unit_price must be non-negative."}, status.HTTP_400_BAD_REQUEST

    selected_show = None
    show_id = _coerce_int(coalesce(payload, "show_id", "showId"))
    if show_id:
        selected_show = (
            Show.objects.select_related("movie")
            .filter(id=show_id, vendor_id=vendor.id)
            .first()
        )
        if not selected_show:
            return {"message": "show_id is invalid for this vendor."}, status.HTTP_400_BAD_REQUEST

        lifecycle = selectors.get_show_lifecycle_state(selected_show)
        if not lifecycle.get("booking_open"):
            return {
                "message": "Selected show is not open for booking. Choose an available show slot."
            }, status.HTTP_400_BAD_REQUEST

    show_date = parse_date(coalesce(payload, "show_date", "showDate", "date"))
    show_time = parse_time(coalesce(payload, "show_time", "showTime", "time"))
    valid_until = parse_date(coalesce(payload, "valid_until", "validUntil", "expiry_date", "expiryDate"))

    movie_title = str(coalesce(payload, "movie_title", "movieTitle") or "").strip() or None
    hall_name = str(coalesce(payload, "hall") or "").strip() or None
    seat_hold_count = _parse_positive_int(
        coalesce(payload, "seat_hold_count", "seatHoldCount", "hold_count", "holdCount"),
        default=ticket_count,
        minimum=0,
        maximum=2000,
    )
    invoice_total_amount = _parse_price_amount(coalesce(payload, "invoice_total_amount", "invoiceTotalAmount"))
    if invoice_total_amount is None:
        invoice_total_amount = (unit_price * Decimal(ticket_count)).quantize(Decimal("0.01"))
    amount_paid = _parse_price_amount(coalesce(payload, "amount_paid", "amountPaid", "paid_amount", "paidAmount"))
    if amount_paid is None:
        amount_paid = Decimal("0.00")
    invoice_number = str(coalesce(payload, "invoice_number", "invoiceNumber") or "").strip() or None
    hold_expires_at = _parse_datetime_value(
        coalesce(payload, "seat_hold_expires_at", "seatHoldExpiresAt")
    )
    if hold_expires_at is None and valid_until:
        hold_expires_at = _combine_local_date_time(valid_until, time_cls(23, 59))
    if hold_expires_at is None:
        hold_expires_at = timezone.now() + timedelta(days=1)

    if selected_show:
        movie_title = str(selected_show.movie.title if selected_show.movie else movie_title or "").strip() or None
        hall_name = str(selected_show.hall or hall_name or "").strip() or None
        show_date = selected_show.show_date or show_date
        show_time = selected_show.start_time or show_time
        if unit_price <= Decimal("0.00") and selected_show.price is not None:
            unit_price = Decimal(selected_show.price).quantize(Decimal("0.01"))

    if show_date and valid_until and valid_until < show_date:
        return {
            "message": "valid_until cannot be earlier than show_date."
        }, status.HTTP_400_BAD_REQUEST

    recipient_items = payload.get("recipients") if isinstance(payload.get("recipients"), list) else []

    with transaction.atomic():
        batch = BulkTicketBatch.objects.create(
            vendor=vendor,
            corporate_name=corporate_name,
            contact_person=str(coalesce(payload, "contact_person", "contactPerson") or "").strip() or None,
            contact_email=str(coalesce(payload, "contact_email", "contactEmail") or "").strip() or None,
            movie_title=movie_title,
            hall=hall_name,
            show_date=show_date,
            show_time=show_time,
            valid_until=valid_until,
            seat_hold_count=seat_hold_count,
            seat_hold_expires_at=hold_expires_at,
            unit_price=unit_price,
            total_amount=(unit_price * Decimal(ticket_count)).quantize(Decimal("0.01")),
            invoice_number=invoice_number,
            invoice_total_amount=invoice_total_amount,
            amount_paid=amount_paid,
            settlement_status=_settlement_status_for_amounts(amount_paid, invoice_total_amount),
            notes=str(coalesce(payload, "notes", "note") or "").strip() or None,
            status=BulkTicketBatch.STATUS_GENERATED,
        )

        generated_items: list[BulkTicketItem] = []
        bulk_show_datetime = None
        if selected_show:
            bulk_show_datetime = _ensure_timezone_aware(selected_show.start_datetime)
        if not bulk_show_datetime and batch.show_date and batch.show_time:
            bulk_show_datetime = _combine_local_date_time(batch.show_date, batch.show_time)

        for index in range(ticket_count):
            recipient = recipient_items[index] if index < len(recipient_items) and isinstance(recipient_items[index], dict) else {}
            reference = uuid.uuid4().hex[:10].upper()
            details_url = request.build_absolute_uri(f"/api/ticket/{reference}/details/")
            movie_payload = {
                "title": batch.movie_title or "Corporate Ticket",
                "venue_name": vendor.theatre or vendor.name,
                "venue_location": vendor.city or "",
                "show_date": batch.show_date.isoformat() if batch.show_date else "",
                "show_time": batch.show_time.strftime("%I:%M %p") if batch.show_time else "",
                "theater": batch.hall or "Private Hall",
                "cinema_id": vendor.id,
            }
            ticket_payload = {
                "reference": reference,
                "movie": movie_payload,
                "selected_seats": [],
                "ticket_total": float(unit_price),
                "food_total": 0,
                "total": float(unit_price),
                "items": [],
                "user": {
                    "name": str(coalesce(recipient, "name", "recipient_name", "recipientName") or "").strip() or None,
                    "email": str(coalesce(recipient, "email", "recipient_email", "recipientEmail") or "").strip() or None,
                },
                "booking": {
                    "vendor_id": vendor.id,
                    "vendor_name": vendor.name,
                    "bulk_batch_id": batch.id,
                },
                "bulk": {
                    "batch_id": batch.id,
                    "corporate_name": batch.corporate_name,
                    "employee_code": str(coalesce(recipient, "employee_code", "employeeCode", default=f"EMP-{index + 1:04d}") or "").strip(),
                    "valid_until": batch.valid_until.isoformat() if batch.valid_until else None,
                },
                "created_at": timezone.now().isoformat(),
                "details_url": details_url,
            }
            ticket_security_fields = build_ticket_security_fields(
                show=selected_show,
                show_datetime=bulk_show_datetime,
                payment_status=TICKET_PAYMENT_STATUS_PAID,
            )
            ticket = Ticket.objects.create(
                reference=reference,
                payload=ticket_payload,
                **ticket_security_fields,
            )
            persist_ticket_render_artifacts(ticket)
            generated_items.append(
                BulkTicketItem(
                    batch=batch,
                    ticket=ticket,
                    employee_code=str(coalesce(recipient, "employee_code", "employeeCode", default=f"EMP-{index + 1:04d}") or "").strip() or None,
                    recipient_name=str(coalesce(recipient, "name", "recipient_name", "recipientName") or "").strip() or None,
                    recipient_email=str(coalesce(recipient, "email", "recipient_email", "recipientEmail") or "").strip() or None,
                    status=BulkTicketItem.STATUS_ACTIVE,
                )
            )

        BulkTicketItem.objects.bulk_create(generated_items, batch_size=200)

    return {
        "message": "Bulk tickets generated successfully.",
        "batch": _serialize_bulk_ticket_batch(batch),
    }, status.HTTP_201_CREATED


def list_vendor_bulk_ticket_batches(request: Any) -> tuple[dict[str, Any], int]:
    """List bulk ticket batches for authenticated vendor."""
    vendor = resolve_vendor(request)
    if not vendor:
        return {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND

    queryset = BulkTicketBatch.objects.filter(vendor_id=vendor.id).prefetch_related("tickets")
    status_filter = str(coalesce(request.query_params, "status") or "").strip().upper()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    batches = list(queryset.order_by("-created_at", "-id")[:120])
    return {
        "batches": [_serialize_bulk_ticket_batch(batch) for batch in batches],
    }, status.HTTP_200_OK


def export_vendor_bulk_ticket_batch(request: Any, batch: BulkTicketBatch) -> tuple[dict[str, Any], int]:
    """Export one batch with CSV payload and ticket QR data URLs."""
    include_qr = parse_bool(coalesce(request.query_params, "include_qr", "includeQr"), default=True)
    items = list(batch.tickets.select_related("ticket").order_by("id"))

    rows: list[dict[str, Any]] = []
    tickets_payload: list[dict[str, Any]] = []
    for item in items:
        serialized = _serialize_bulk_ticket_item(item, request, include_qr=include_qr)
        tickets_payload.append(serialized)
        rows.append(
            {
                "reference": serialized["reference"],
                "employee_code": serialized["employee_code"] or "",
                "recipient_name": serialized["recipient_name"] or "",
                "recipient_email": serialized["recipient_email"] or "",
                "status": serialized["status"],
                "details_url": serialized["details_url"],
                "download_url": serialized["download_url"],
                "qr_code": serialized.get("qr_code") or "",
            }
        )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "reference",
            "employee_code",
            "recipient_name",
            "recipient_email",
            "status",
            "details_url",
            "download_url",
            "qr_code",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

    if batch.status != BulkTicketBatch.STATUS_EXPORTED:
        batch.status = BulkTicketBatch.STATUS_EXPORTED
        batch.save(update_fields=["status", "updated_at"])

    encoded_csv = base64.b64encode(output.getvalue().encode("utf-8")).decode("ascii")
    return {
        "message": "Bulk ticket export prepared.",
        "batch": _serialize_bulk_ticket_batch(batch),
        "csv_base64": encoded_csv,
        "filename": f"bulk_tickets_batch_{batch.id}.csv",
        "tickets": tickets_payload,
    }, status.HTTP_200_OK


def calculate_dynamic_ticket_price(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Calculate final ticket price dynamically for selected seats and context."""
    context = _resolve_booking_context(payload)
    selected_seats = _normalize_seat_labels(context.get("selected_seats") or [])
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    lock_requested = parse_bool(coalesce(payload, "lock_price", "lockPrice"), default=True)
    use_preview_cache = parse_bool(coalesce(payload, "use_cache", "useCache"), default=True) and not lock_requested
    preview_cache_key = _pricing_preview_cache_key(payload, context)
    if use_preview_cache:
        cached = cache.get(preview_cache_key)
        if isinstance(cached, dict):
            return cached, status.HTTP_200_OK

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND

    hall = context.get("hall") or show.hall
    showtime = _find_showtime_for_context(show, hall)
    screen = None
    if showtime:
        screen = showtime.screen
    if not screen and hall:
        screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=str(hall)).first()
    if not screen:
        screen = Screen.objects.filter(vendor_id=show.vendor_id).order_by("id").first()

    event_name = str(coalesce(payload, "event", "event_name", "festival", "festival_name") or "").strip()
    occupancy_payload = _showtime_occupancy_snapshot(showtime=showtime, screen=screen)

    seats_payload: list[dict[str, Any]] = []
    seat_price_lock_map: dict[str, str] = {}
    total = Decimal("0.00")
    base_subtotal = Decimal("0.00")
    occupancy_adjustment_total = Decimal("0.00")
    rule_adjustment_total = Decimal("0.00")
    invalid_seats: list[str] = []

    for label in selected_seats:
        row_label, seat_number = _split_seat_label(label)
        if not seat_number:
            invalid_seats.append(str(label))
            continue

        seat = None
        if screen:
            seat = Seat.objects.filter(screen=screen, row_label=row_label or None, seat_number=seat_number).first()
        seat_type = seat.seat_type if seat else SEAT_CATEGORY_NORMAL
        final_price, applied_rules = _resolve_dynamic_seat_price(
            show=show,
            showtime=showtime,
            screen=screen,
            seat_type=seat_type,
            occupancy_snapshot=occupancy_payload,
            event_name=event_name,
        )
        base_price = _seat_price_for_category(screen=screen, showtime=showtime, seat_type=seat_type, show=show)
        normalized_label = _join_seat_label(row_label, seat_number)

        occupancy_delta = Decimal("0.00")
        for applied in applied_rules:
            if str(applied.get("adjustment_type") or "").upper() != "SYSTEM_OCCUPANCY_MULTIPLIER":
                continue
            before_value = _parse_signed_price_amount(applied.get("before")) or Decimal("0.00")
            after_value = _parse_signed_price_amount(applied.get("after")) or Decimal("0.00")
            occupancy_delta += (after_value - before_value)

        if final_price is not None:
            total += final_price
            seat_price_lock_map[normalize_seat_label(normalized_label)] = f"{final_price.quantize(Decimal('0.01'))}"
        if base_price is not None:
            base_subtotal += base_price
        base_for_delta = base_price or Decimal("0.00")
        final_for_delta = final_price or Decimal("0.00")
        seat_delta = final_for_delta - base_for_delta
        rule_adjustment_total += (seat_delta - occupancy_delta)
        occupancy_adjustment_total += occupancy_delta

        seats_payload.append(
            {
                "label": normalized_label,
                "seat_type": _normalize_seat_category(seat_type),
                "base_price": float(base_price) if base_price is not None else None,
                "final_price": float(final_price) if final_price is not None else None,
                "applied_rules": applied_rules,
            }
        )

    if invalid_seats:
        return {
            "message": "Some selected_seats are invalid.",
            "invalid_seats": invalid_seats,
        }, status.HTTP_400_BAD_REQUEST

    normalized_total = total.quantize(Decimal("0.01"))
    coupon_payload = None
    discount_amount = Decimal("0.00")
    payable_total = normalized_total

    coupon_code = coalesce(payload, "coupon_code", "couponCode", "code")
    if coupon_code:
        discount_context = {
            **(payload if isinstance(payload, dict) else {}),
            "vendor_id": show.vendor_id,
            "show_id": show.id,
            "showtime_id": showtime.id if showtime else None,
            "seat_categories": [seat.get("seat_type") for seat in seats_payload],
            "seat_count": len(seats_payload),
        }
        coupon_result, coupon_error, coupon_status = _apply_coupon_to_subtotal(
            coupon_code,
            normalized_total,
            context=discount_context,
            lock_for_update=False,
            consume=False,
        )
        if coupon_error:
            return coupon_error, coupon_status
        coupon_payload = coupon_result.get("coupon")
        promo_payload = coupon_result.get("promo_code")
        discount_amount = _parse_price_amount(coupon_result.get("discount_amount")) or Decimal("0.00")
        payable_total = _parse_price_amount(coupon_result.get("final_total")) or normalized_total
    else:
        promo_payload = None

    lock_payload = None
    if lock_requested:
        lock_payload = _create_price_lock(
            {
                "show_id": show.id,
                "showtime_id": showtime.id if showtime else None,
                "hall": hall,
                "selected_seats": [seat.get("label") for seat in seats_payload],
                "seat_prices": seat_price_lock_map,
                "subtotal": f"{normalized_total}",
                "currency": "NPR",
                "occupancy": occupancy_payload,
            },
            ttl_seconds=_settings_int("PRICING_LOCK_TTL_SECONDS", PRICING_LOCK_TTL_SECONDS),
        )

    category_snapshot_payload, _ = get_show_dynamic_prices(
        {
            "show_id": show.id,
            "hall": hall,
            "event": event_name,
        }
    )

    response_payload = {
        "show_id": show.id,
        "showtime_id": showtime.id if showtime else None,
        "currency": "NPR",
        "seat_count": len(seats_payload),
        "seats": seats_payload,
        "occupancy": occupancy_payload,
        "dynamic_by_category": category_snapshot_payload.get("categories") or {},
        "pricing_indicator": "Price may increase as seats fill.",
        "breakdown": {
            "base_subtotal": float(base_subtotal.quantize(Decimal("0.01"))),
            "rule_adjustment": float(rule_adjustment_total.quantize(Decimal("0.01"))),
            "occupancy_adjustment": float(occupancy_adjustment_total.quantize(Decimal("0.01"))),
            "subtotal": float(normalized_total),
            "discount_amount": float(discount_amount),
            "final_total": float(payable_total),
        },
        "subtotal": float(normalized_total),
        "discount_amount": float(discount_amount),
        "total": float(payable_total),
        "coupon": coupon_payload,
        "promo_code": promo_payload,
    }
    if lock_payload:
        response_payload["price_lock"] = lock_payload

    if use_preview_cache:
        cache.set(
            preview_cache_key,
            response_payload,
            timeout=PRICING_PREVIEW_CACHE_TTL_SECONDS,
        )

    return response_payload, status.HTTP_200_OK


def _row_label_from_index(index: int) -> str:
    """Convert a zero-based row index into a label (A..Z, AA..)."""
    label = ""
    current = int(index)
    while True:
        current, remainder = divmod(current, 26)
        label = chr(65 + remainder) + label
        if current == 0:
            break
        current -= 1
    return label


def _row_label_sort_key(value: Any) -> int:
    """Sort row labels lexicographically in base-26 order."""
    label = str(value or "").strip().upper()
    score = 0
    for char in label:
        if not ("A" <= char <= "Z"):
            continue
        score = (score * 26) + (ord(char) - 64)
    return score


def _parse_positive_int(
    value: Any, default: int, minimum: int = 1, maximum: int = 100
) -> int:
    """Parse an int with bounds and fallback."""
    parsed = _coerce_int(value)
    if parsed is None:
        return default
    return max(minimum, min(maximum, parsed))


def _payload_has_non_empty_value(payload: dict[str, Any], *keys: str) -> bool:
    """Return True when any provided payload key has a meaningful value."""
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def _parse_numeric_seat_number(value: Any) -> Optional[int]:
    """Extract a numeric seat index from seat labels like '1' or 'S12'."""
    match = re.search(r"\d+", str(value or "").strip())
    if not match:
        return None
    try:
        parsed = int(match.group(0))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _seat_has_booked_history(seat: Seat) -> bool:
    """Return True if a seat is already sold/booked in any show."""
    if seat.booking_seats.exists():
        return True
    return seat.availabilities.filter(
        Q(seat_status__iexact=SEAT_STATUS_BOOKED)
        | Q(seat_status__iexact=SEAT_STATUS_SOLD)
    ).exists()


def _seat_has_layout_mutation_lock(seat: Seat) -> bool:
    """Return True when seat cannot be removed due active usage/locks."""
    if _seat_has_booked_history(seat):
        return True
    now = timezone.now()
    return seat.availabilities.filter(
        Q(seat_status__iexact=SEAT_STATUS_UNAVAILABLE)
        | Q(locked_until__gt=now)
    ).exists()


def _normalize_seat_category(value: Any) -> str:
    """Normalize free-text seat category labels."""
    text = str(value or "").strip().lower()
    if text.startswith("vip"):
        return SEAT_CATEGORY_VIP
    if text.startswith("prem"):
        return SEAT_CATEGORY_PREMIUM
    if text.startswith("exec"):
        return SEAT_CATEGORY_EXECUTIVE
    return SEAT_CATEGORY_NORMAL


def _rule_categories_for_seat(seat_type: Any) -> set[str]:
    """Return all rule category values compatible with a seat type."""
    normalized = _normalize_seat_category(seat_type)
    aliases = SEAT_CATEGORY_RULE_ALIASES.get(normalized)
    if aliases:
        return set(aliases)
    primary = SEAT_CATEGORY_RULE_VALUES.get(normalized, PricingRule.SEAT_CATEGORY_NORMAL)
    return {primary}


def _parse_price_amount(value: Any) -> Optional[Decimal]:
    """Parse a price value into Decimal(0.01) or return None for invalid input."""
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if parsed < Decimal("0"):
        return None
    return parsed.quantize(Decimal("0.01"))


def _parse_signed_price_amount(value: Any) -> Optional[Decimal]:
    """Parse signed price values like +50/-25.5 and quantize to 0.01."""
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed.quantize(Decimal("0.01"))


def _pricing_preview_cache_key(payload: dict[str, Any], context: dict[str, Any]) -> str:
    """Build stable cache key for preview requests with short-lived context."""
    selected = sorted(_normalize_seat_labels(context.get("selected_seats") or []), key=_seat_sort_key)
    key_payload = {
        "show_id": context.get("show_id"),
        "movie_id": context.get("movie_id"),
        "cinema_id": context.get("cinema_id"),
        "show_date": context.get("show_date").isoformat() if context.get("show_date") else None,
        "show_time": context.get("show_time").strftime("%H:%M") if context.get("show_time") else None,
        "hall": str(context.get("hall") or "").strip().lower(),
        "event": str(coalesce(payload, "event", "event_name", "festival", "festival_name") or "").strip().lower(),
        "coupon": str(coalesce(payload, "coupon_code", "couponCode", "code") or "").strip().upper(),
        "selected": selected,
    }
    encoded = json.dumps(key_payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{PRICING_PREVIEW_CACHE_PREFIX}{digest}"


def _pricing_lock_cache_key(lock_token: str) -> str:
    token = str(lock_token or "").strip()
    return f"{PRICING_LOCK_CACHE_PREFIX}{token}"


def _create_price_lock(payload: dict[str, Any], ttl_seconds: int = PRICING_LOCK_TTL_SECONDS) -> dict[str, Any]:
    """Persist locked price snapshot for checkout consistency."""
    token = uuid.uuid4().hex
    now = timezone.now()
    expires_at = now + timedelta(seconds=max(60, int(ttl_seconds or PRICING_LOCK_TTL_SECONDS)))
    snapshot = {
        **payload,
        "token": token,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    cache.set(_pricing_lock_cache_key(token), snapshot, timeout=max(60, int(ttl_seconds or PRICING_LOCK_TTL_SECONDS)))
    return {
        "token": token,
        "expires_at": expires_at.isoformat(),
        "ttl_seconds": max(60, int(ttl_seconds or PRICING_LOCK_TTL_SECONDS)),
    }


def _load_price_lock(lock_token: Any) -> Optional[dict[str, Any]]:
    token = str(lock_token or "").strip()
    if not token:
        return None
    payload = cache.get(_pricing_lock_cache_key(token))
    return payload if isinstance(payload, dict) else None


def _extract_price_lock_token(payload: dict[str, Any]) -> str:
    """Extract a lock token from top-level payload, booking, or pricing objects."""
    booking_payload = payload.get("booking") if isinstance(payload.get("booking"), dict) else {}
    booking_context = payload.get("bookingContext") if isinstance(payload.get("bookingContext"), dict) else {}
    pricing_payload = payload.get("pricing") if isinstance(payload.get("pricing"), dict) else {}
    return str(
        coalesce(
            payload,
            "price_lock_token",
            "priceLockToken",
            default=coalesce(
                pricing_payload,
                "price_lock_token",
                "priceLockToken",
                default=coalesce(
                    booking_payload,
                    "price_lock_token",
                    "priceLockToken",
                    default=coalesce(booking_context, "price_lock_token", "priceLockToken", default=""),
                ),
            ),
        )
        or ""
    ).strip()


def _seat_price_from_lock(lock_snapshot: Optional[dict[str, Any]], seat_label: str) -> Optional[Decimal]:
    """Read locked seat price from cached lock snapshot payload."""
    if not isinstance(lock_snapshot, dict):
        return None
    seat_prices = lock_snapshot.get("seat_prices")
    if not isinstance(seat_prices, dict):
        return None
    return _parse_price_amount(seat_prices.get(normalize_seat_label(seat_label)))


def normalize_seat_label(value: Any) -> str:
    """Normalize seat labels to comparable uppercase format."""
    return str(value or "").replace(" ", "").strip().upper()


def _is_price_lock_compatible(
    lock_snapshot: Optional[dict[str, Any]],
    *,
    show: Optional[Show],
    showtime: Optional[Showtime],
    selected_seats: list[str],
) -> bool:
    if not isinstance(lock_snapshot, dict) or not show:
        return False
    locked_show_id = _coerce_int(lock_snapshot.get("show_id"))
    if locked_show_id and locked_show_id != int(show.id):
        return False
    locked_showtime_id = _coerce_int(lock_snapshot.get("showtime_id"))
    if locked_showtime_id and showtime and locked_showtime_id != int(showtime.id):
        return False

    locked_seats_raw = lock_snapshot.get("selected_seats")
    if isinstance(locked_seats_raw, list):
        locked_seats = sorted([normalize_seat_label(item) for item in locked_seats_raw if normalize_seat_label(item)], key=_seat_sort_key)
        incoming_seats = sorted([normalize_seat_label(item) for item in selected_seats if normalize_seat_label(item)], key=_seat_sort_key)
        if locked_seats != incoming_seats:
            return False

    return True


def _showtime_occupancy_snapshot(
    *,
    showtime: Optional[Showtime],
    screen: Optional[Screen],
) -> dict[str, Any]:
    """Compute booked seat ratio with short cache to avoid repeated heavy counting."""
    if not showtime:
        return {
            "booked_seats": 0,
            "total_seats": int(screen.capacity or 0) if screen and screen.capacity else 0,
            "occupancy_percent": 0.0,
            "occupancy_multiplier": float(PRICING_OCCUPANCY_NORMAL_MULTIPLIER),
            "occupancy_band": "NORMAL",
        }

    cache_key = f"{PRICING_OCCUPANCY_CACHE_PREFIX}{showtime.id}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    booked_from_availability = SeatAvailability.objects.filter(
        showtime_id=showtime.id,
        seat_status__in=[SEAT_STATUS_BOOKED, SEAT_STATUS_SOLD],
    ).count()
    booked_from_bookings = (
        BookingSeat.objects.filter(showtime_id=showtime.id)
        .exclude(booking__booking_status__iexact=BOOKING_STATUS_CANCELLED)
        .values("seat_id")
        .distinct()
        .count()
    )
    booked_seats = max(int(booked_from_availability or 0), int(booked_from_bookings or 0))

    if screen and screen.id:
        total_seats = Seat.objects.filter(screen_id=screen.id).count()
        if total_seats <= 0:
            total_seats = int(screen.capacity or 0)
    else:
        total_seats = 0

    if total_seats <= 0:
        occupancy_percent = Decimal("0.00")
    else:
        occupancy_percent = ((Decimal(booked_seats) / Decimal(total_seats)) * Decimal("100")).quantize(Decimal("0.01"))

    if occupancy_percent <= PRICING_OCCUPANCY_LOW_MAX:
        occupancy_band = "LOW"
        occupancy_multiplier = PRICING_OCCUPANCY_LOW_MULTIPLIER
    elif occupancy_percent < PRICING_OCCUPANCY_HIGH_MIN:
        occupancy_band = "NORMAL"
        occupancy_multiplier = PRICING_OCCUPANCY_NORMAL_MULTIPLIER
    else:
        occupancy_band = "HIGH"
        occupancy_multiplier = PRICING_OCCUPANCY_HIGH_MULTIPLIER

    payload = {
        "booked_seats": int(booked_seats),
        "total_seats": int(total_seats),
        "occupancy_percent": float(occupancy_percent),
        "occupancy_multiplier": float(occupancy_multiplier),
        "occupancy_band": occupancy_band,
    }
    cache.set(cache_key, payload, timeout=PRICING_OCCUPANCY_CACHE_TTL_SECONDS)
    return payload


def _is_time_in_range(
    current: Optional[time_cls],
    start: Optional[time_cls],
    end: Optional[time_cls],
) -> bool:
    """Check if current time falls in [start,end], including overnight windows."""
    if not current:
        return True
    if not start and not end:
        return True
    if start and not end:
        return current >= start
    if end and not start:
        return current <= end
    if not start or not end:
        return True
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _collect_screen_category_prices(
    screen: Optional[Screen],
    showtime: Optional[Showtime] = None,
) -> dict[str, Optional[Decimal]]:
    """Collect category prices from screen fields with showtime/base fallback."""
    base_price = None
    if showtime and showtime.price is not None:
        base_price = _parse_price_amount(showtime.price)

    prices: dict[str, Optional[Decimal]] = {}
    for key, field_name in SEAT_CATEGORY_SCREEN_FIELDS.items():
        screen_price = _parse_price_amount(getattr(screen, field_name, None) if screen else None)
        prices[key] = screen_price if screen_price is not None else base_price
    return prices


def _normalize_category_prices(
    payload: dict[str, Any],
    screen: Optional[Screen] = None,
    showtime: Optional[Showtime] = None,
) -> dict[str, Optional[Decimal]]:
    """Normalize category price payload with screen/showtime fallback values."""
    raw_prices = payload.get("category_prices") if isinstance(payload.get("category_prices"), dict) else {}
    prices = _collect_screen_category_prices(screen=screen, showtime=showtime)
    for key in ("normal", "executive", "premium", "vip"):
        incoming = coalesce(
            raw_prices,
            key,
            default=coalesce(payload, f"{key}_price", f"{key}Price"),
        )
        parsed = _parse_price_amount(incoming)
        if parsed is not None:
            prices[key] = parsed
    return prices


def _seat_price_for_category(
    screen: Optional[Screen],
    showtime: Optional[Showtime],
    seat_type: Any,
    show: Optional[Show] = None,
) -> Optional[Decimal]:
    """Resolve effective seat price for one category from screen/showtime values."""
    normalized = _normalize_seat_category(seat_type)
    category_key = SEAT_CATEGORY_KEYS.get(normalized, "normal")

    if show and show.id:
        candidates = list(_rule_categories_for_seat(normalized))
        primary = _normalize_rule_seat_category(normalized)
        show_base_prices = list(
            ShowBasePrice.objects.filter(
                show_id=show.id,
                is_active=True,
                seat_category__in=candidates,
            ).order_by("id")
        )
        if show_base_prices:
            preferred = next(
                (item for item in show_base_prices if str(item.seat_category or "").upper() == primary),
                show_base_prices[0],
            )
            parsed = _parse_price_amount(preferred.base_price)
            if parsed is not None:
                return parsed

    return _collect_screen_category_prices(screen=screen, showtime=showtime).get(category_key)


def _serialize_category_prices(prices: dict[str, Optional[Decimal]]) -> dict[str, Optional[float]]:
    """Serialize Decimal category prices for API payloads."""
    return {
        key: (float(value) if value is not None else None)
        for key, value in prices.items()
    }


def _is_weekend(value: Optional[date_cls]) -> bool:
    """Return True if date is weekend (Saturday/Sunday)."""
    if not value:
        return False
    return value.weekday() >= 5


def _normalize_rule_seat_category(seat_type: Any) -> str:
    """Map seat category labels to PricingRule seat category enum values."""
    category_label = _normalize_seat_category(seat_type)
    return SEAT_CATEGORY_RULE_VALUES.get(category_label, PricingRule.SEAT_CATEGORY_NORMAL)


def _apply_pricing_adjustment(
    price: Optional[Decimal],
    adjustment_type: str,
    adjustment_value: Optional[Decimal],
) -> Optional[Decimal]:
    """Apply one rule adjustment to a seat price."""
    if adjustment_value is None:
        return price

    current = price if price is not None else Decimal("0")
    kind = str(adjustment_type or "").upper()

    if kind == PricingRule.ADJUSTMENT_FIXED:
        result = adjustment_value
    elif kind == PricingRule.ADJUSTMENT_INCREMENT:
        result = current + adjustment_value
    elif kind == PricingRule.ADJUSTMENT_PERCENT:
        result = current + (current * (adjustment_value / Decimal("100")))
    elif kind == PricingRule.ADJUSTMENT_MULTIPLIER:
        result = current * adjustment_value
    else:
        result = current

    if result < Decimal("0"):
        result = Decimal("0")
    return result.quantize(Decimal("0.01"))


def _rule_matches_day(rule: PricingRule, show_date: Optional[date_cls]) -> bool:
    """Return True when rule day constraints match the selected show date."""
    if not show_date:
        return True

    day_code = WEEKDAY_TO_DAY_CODE.get(show_date.weekday(), PricingRule.DAY_OF_WEEK_MON)
    day_of_week = str(getattr(rule, "day_of_week", "") or "").strip().upper() or PricingRule.DAY_OF_WEEK_ALL
    is_weekend = show_date.weekday() >= 5
    if day_of_week == PricingRule.DAY_OF_WEEK_WEEKDAY and is_weekend:
        return False
    if day_of_week == PricingRule.DAY_OF_WEEK_WEEKEND and not is_weekend:
        return False
    if day_of_week not in {
        PricingRule.DAY_OF_WEEK_ALL,
        PricingRule.DAY_OF_WEEK_WEEKDAY,
        PricingRule.DAY_OF_WEEK_WEEKEND,
    } and day_of_week != day_code:
        return False

    # Backward compatibility for legacy day_type rules.
    day_type = str(getattr(rule, "day_type", "") or "").strip().upper() or PricingRule.DAY_TYPE_ALL
    if day_type == PricingRule.DAY_TYPE_WEEKDAY and is_weekend:
        return False
    if day_type == PricingRule.DAY_TYPE_WEEKEND and not is_weekend:
        return False
    return True


def _rule_matches_occupancy(rule: PricingRule, occupancy_percent: Decimal) -> bool:
    """Apply occupancy threshold rules; discount-like rules use <= threshold, surcharge uses >=."""
    threshold = _parse_price_amount(getattr(rule, "occupancy_threshold", None))
    if threshold is None:
        return True

    multiplier = _parse_signed_price_amount(getattr(rule, "price_multiplier", None))
    flat_adjustment = _parse_signed_price_amount(getattr(rule, "flat_adjustment", None))
    legacy_adjustment = _parse_signed_price_amount(getattr(rule, "adjustment_value", None))
    adjustment_type = str(getattr(rule, "adjustment_type", "") or "").strip().upper()

    is_discount_like = (
        (multiplier is not None and multiplier < Decimal("1"))
        or (flat_adjustment is not None and flat_adjustment < Decimal("0"))
        or (adjustment_type == PricingRule.ADJUSTMENT_PERCENT and legacy_adjustment is not None and legacy_adjustment < Decimal("0"))
        or (adjustment_type == PricingRule.ADJUSTMENT_INCREMENT and legacy_adjustment is not None and legacy_adjustment < Decimal("0"))
    )

    if is_discount_like:
        return occupancy_percent <= threshold
    return occupancy_percent >= threshold


def _pricing_rule_override_key(rule: PricingRule) -> tuple[Any, ...]:
    """Build override key so vendor-specific rules can override matching global scope."""
    return (
        int(rule.movie_id or 0),
        str(rule.hall or "").strip().lower(),
        str(rule.seat_category or "").strip().upper(),
        str(getattr(rule, "day_of_week", "") or "").strip().upper(),
        str(getattr(rule, "day_type", "") or "").strip().upper(),
        rule.start_time.isoformat() if getattr(rule, "start_time", None) else "",
        rule.end_time.isoformat() if getattr(rule, "end_time", None) else "",
        str(getattr(rule, "occupancy_threshold", "") or ""),
        bool(getattr(rule, "is_festival_pricing", False)),
        str(getattr(rule, "festival_name", "") or "").strip().lower(),
    )


def _apply_rule_price_modifiers(
    current_price: Optional[Decimal],
    rule: PricingRule,
) -> tuple[Optional[Decimal], str, Optional[Decimal], Optional[Decimal]]:
    """Apply modern multiplier/flat fields first, fallback to legacy adjustment fields."""
    current = current_price if current_price is not None else Decimal("0.00")
    multiplier = _parse_signed_price_amount(getattr(rule, "price_multiplier", None))
    flat_adjustment = _parse_signed_price_amount(getattr(rule, "flat_adjustment", None))

    if multiplier is not None or flat_adjustment is not None:
        next_price = current
        if multiplier is not None:
            next_price = (next_price * multiplier).quantize(Decimal("0.01"))
        if flat_adjustment is not None:
            next_price = (next_price + flat_adjustment).quantize(Decimal("0.01"))
        if next_price < Decimal("0"):
            next_price = Decimal("0.00")
        return next_price, "RULE_COMPOSITE", multiplier, flat_adjustment

    legacy_adjustment = _parse_signed_price_amount(getattr(rule, "adjustment_value", None))
    next_price = _apply_pricing_adjustment(current, rule.adjustment_type, legacy_adjustment)
    return next_price, str(rule.adjustment_type or "").upper(), None, legacy_adjustment


def _list_applicable_pricing_rules(
    show: Show,
    seat_category_rules: set[str],
    hall: Optional[str],
    show_date: Optional[date_cls],
    show_time: Optional[time_cls],
    occupancy_percent: Decimal,
    event_name: str = "",
) -> list[PricingRule]:
    """List active pricing rules (vendor + global fallback) for one show context."""
    queryset = PricingRule.objects.filter(
        is_active=True,
    ).filter(
        Q(vendor_id=show.vendor_id) | Q(vendor__isnull=True)
    ).filter(
        Q(movie_id__isnull=True) | Q(movie_id=show.movie_id)
    )

    hall_text = str(hall or "").strip()
    if hall_text:
        queryset = queryset.filter(Q(hall__isnull=True) | Q(hall="") | Q(hall__iexact=hall_text))
    else:
        queryset = queryset.filter(Q(hall__isnull=True) | Q(hall=""))

    if show_date:
        queryset = queryset.filter(
            Q(start_date__isnull=True) | Q(start_date__lte=show_date),
            Q(end_date__isnull=True) | Q(end_date__gte=show_date),
        )

    category_query = Q(seat_category=PricingRule.SEAT_CATEGORY_ALL)
    for category_value in seat_category_rules:
        category_query |= Q(seat_category=str(category_value).upper())
    queryset = queryset.filter(category_query)

    event_text = str(event_name or "").strip().lower()
    rules = list(queryset.order_by("priority", "id"))

    vendor_rules = [rule for rule in rules if rule.vendor_id == show.vendor_id]
    global_rules = [rule for rule in rules if rule.vendor_id is None]
    vendor_override_keys = {_pricing_rule_override_key(rule) for rule in vendor_rules}
    merged_rules = vendor_rules + [
        rule for rule in global_rules if _pricing_rule_override_key(rule) not in vendor_override_keys
    ]

    applicable: list[PricingRule] = []
    for rule in sorted(merged_rules, key=lambda item: (int(item.priority or 0), int(item.id or 0))):
        if not _rule_matches_day(rule, show_date):
            continue
        if not _is_time_in_range(show_time, getattr(rule, "start_time", None), getattr(rule, "end_time", None)):
            continue
        if not _rule_matches_occupancy(rule, occupancy_percent):
            continue

        if not rule.is_festival_pricing:
            applicable.append(rule)
            continue

        rule_event = str(rule.festival_name or "").strip().lower()
        if not rule_event or not event_text or event_text == rule_event:
            applicable.append(rule)

    return applicable


def _resolve_dynamic_seat_price(
    show: Show,
    showtime: Optional[Showtime],
    screen: Optional[Screen],
    seat_type: Any,
    occupancy_snapshot: Optional[dict[str, Any]] = None,
    event_name: str = "",
) -> tuple[Optional[Decimal], list[dict[str, Any]]]:
    """Resolve final seat price after applying vendor pricing rules."""
    base_price = _seat_price_for_category(screen=screen, showtime=showtime, seat_type=seat_type, show=show)
    if base_price is None:
        base_price = _parse_price_amount(show.price)

    hall = None
    if screen and screen.screen_number:
        hall = str(screen.screen_number)
    elif show.hall:
        hall = str(show.hall)
    show_date = show.show_date
    show_time = show.start_time
    seat_category_rules = _rule_categories_for_seat(seat_type)
    occupancy_payload = occupancy_snapshot or _showtime_occupancy_snapshot(showtime=showtime, screen=screen)
    occupancy_percent = _parse_price_amount(occupancy_payload.get("occupancy_percent")) or Decimal("0.00")
    rules = _list_applicable_pricing_rules(
        show=show,
        seat_category_rules=seat_category_rules,
        hall=hall,
        show_date=show_date,
        show_time=show_time,
        occupancy_percent=occupancy_percent,
        event_name=event_name,
    )

    current = base_price
    applied: list[dict[str, Any]] = []
    for rule in rules:
        before = current
        current, mode, multiplier, flat_adjustment = _apply_rule_price_modifiers(current, rule)

        min_cap = _parse_price_amount(getattr(rule, "min_price_cap", None))
        max_cap = _parse_price_amount(getattr(rule, "max_price_cap", None))
        if current is not None and min_cap is not None and current < min_cap:
            current = min_cap
        if current is not None and max_cap is not None and current > max_cap:
            current = max_cap

        applied.append(
            {
                "rule_id": rule.id,
                "name": rule.name,
                "adjustment_type": mode,
                "price_multiplier": float(multiplier) if multiplier is not None else None,
                "flat_adjustment": float(flat_adjustment) if flat_adjustment is not None else None,
                "adjustment_value": float(_parse_signed_price_amount(rule.adjustment_value) or Decimal("0.00")),
                "before": float(before) if before is not None else None,
                "after": float(current) if current is not None else None,
                "is_festival_pricing": bool(rule.is_festival_pricing),
                "festival_name": rule.festival_name,
                "occupancy_threshold": float(rule.occupancy_threshold) if rule.occupancy_threshold is not None else None,
            }
        )

    # Roll out occupancy slab pricing only when at least one rule is configured for this seat context.
    apply_occupancy_slab = bool(rules)
    occupancy_multiplier = _parse_price_amount(occupancy_payload.get("occupancy_multiplier"))
    if apply_occupancy_slab and current is not None and occupancy_multiplier is not None and occupancy_multiplier != Decimal("1.00"):
        before = current
        current = (current * occupancy_multiplier).quantize(Decimal("0.01"))
        applied.append(
            {
                "rule_id": None,
                "name": "Occupancy Demand Slab",
                "adjustment_type": "SYSTEM_OCCUPANCY_MULTIPLIER",
                "price_multiplier": float(occupancy_multiplier),
                "flat_adjustment": None,
                "adjustment_value": float(occupancy_multiplier),
                "before": float(before),
                "after": float(current),
                "occupancy_band": occupancy_payload.get("occupancy_band"),
                "occupancy_percent": occupancy_payload.get("occupancy_percent"),
            }
        )

    if base_price is not None and current is not None:
        min_allowed = (base_price * PRICING_MIN_PRICE_FACTOR).quantize(Decimal("0.01"))
        max_allowed = (base_price * PRICING_MAX_PRICE_FACTOR).quantize(Decimal("0.01"))
        if current < min_allowed:
            before = current
            current = min_allowed
            applied.append(
                {
                    "rule_id": None,
                    "name": "Safety Floor Cap",
                    "adjustment_type": "SYSTEM_MIN_CAP",
                    "before": float(before),
                    "after": float(current),
                    "cap_value": float(min_allowed),
                }
            )
        if current > max_allowed:
            before = current
            current = max_allowed
            applied.append(
                {
                    "rule_id": None,
                    "name": "Safety Ceiling Cap",
                    "adjustment_type": "SYSTEM_MAX_CAP",
                    "before": float(before),
                    "after": float(current),
                    "cap_value": float(max_allowed),
                }
            )

    return current, applied


def _default_category_counts(total_rows: int) -> dict[str, int]:
    """Build default row distribution for seat categories."""
    rows = max(1, int(total_rows))
    normal = max(1, round(rows * 0.3))
    executive = max(1, round(rows * 0.3))
    premium = max(1, round(rows * 0.2))
    vip = max(1, rows - (normal + executive + premium))
    diff = rows - (normal + executive + premium + vip)
    normal += diff
    return {
        "normal": normal,
        "executive": executive,
        "premium": premium,
        "vip": vip,
    }


def _normalize_category_counts(total_rows: int, payload: dict[str, Any]) -> dict[str, int]:
    """Normalize category row counts from payload into a complete distribution."""
    category_rows = (
        payload.get("category_rows")
        if isinstance(payload.get("category_rows"), dict)
        else {}
    )
    counts = {
        "normal": _parse_positive_int(
            coalesce(
                category_rows,
                "normal",
                default=coalesce(payload, "normal_rows", "normalRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "executive": _parse_positive_int(
            coalesce(
                category_rows,
                "executive",
                default=coalesce(
                    payload, "executive_rows", "executiveRows", default=0
                ),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "premium": _parse_positive_int(
            coalesce(
                category_rows,
                "premium",
                default=coalesce(payload, "premium_rows", "premiumRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
        "vip": _parse_positive_int(
            coalesce(
                category_rows,
                "vip",
                default=coalesce(payload, "vip_rows", "vipRows", default=0),
            ),
            default=0,
            minimum=0,
            maximum=total_rows,
        ),
    }

    provided_total = sum(counts.values())
    if provided_total <= 0:
        return _default_category_counts(total_rows)

    if provided_total < total_rows:
        counts["normal"] += total_rows - provided_total
    elif provided_total > total_rows:
        overflow = provided_total - total_rows
        for key in ("vip", "premium", "executive", "normal"):
            if overflow <= 0:
                break
            reducible = min(counts[key], overflow)
            counts[key] -= reducible
            overflow -= reducible
        if overflow > 0:
            defaults = _default_category_counts(total_rows)
            return defaults
    return counts


def _build_row_category_map(
    row_labels: list[str], category_counts: dict[str, int]
) -> dict[str, str]:
    """Map each row label to its seat category in front-to-back order."""
    ordered_categories = [
        ("normal", SEAT_CATEGORY_NORMAL),
        ("executive", SEAT_CATEGORY_EXECUTIVE),
        ("premium", SEAT_CATEGORY_PREMIUM),
        ("vip", SEAT_CATEGORY_VIP),
    ]
    mapping: dict[str, str] = {}
    index = 0
    for key, label in ordered_categories:
        count = max(0, int(category_counts.get(key, 0)))
        for _ in range(count):
            if index >= len(row_labels):
                break
            mapping[row_labels[index]] = label
            index += 1
    while index < len(row_labels):
        mapping[row_labels[index]] = SEAT_CATEGORY_VIP
        index += 1
    return mapping


def _build_default_layout_payload() -> dict[str, Any]:
    """Return fallback seat layout payload compatible with existing frontend grid."""
    return {
        "seat_groups": [
            {"key": "normal", "label": SEAT_CATEGORY_NORMAL, "rows": ["A", "B", "C"]},
            {
                "key": "executive",
                "label": SEAT_CATEGORY_EXECUTIVE,
                "rows": ["D", "E", "F"],
            },
            {"key": "premium", "label": SEAT_CATEGORY_PREMIUM, "rows": ["G", "H"]},
            {"key": "vip", "label": SEAT_CATEGORY_VIP, "rows": ["I", "J"]},
        ],
        "seat_columns": list(range(1, 16)),
        "sold_seats": [],
        "unavailable_seats": [],
        "reserved_seats": [],
        "reserved_seat_locks": {},
        "reservation_hold_minutes": RESERVE_HOLD_MINUTES,
        "category_prices": {
            "normal": None,
            "executive": None,
            "premium": None,
            "vip": None,
        },
        "seats": [],
        "total_rows": 10,
        "total_columns": 15,
    }


def _summarize_screen_layout(
    screen: Screen,
    *,
    seat_count_hint: Optional[int] = None,
) -> dict[str, Any]:
    """Summarize hall seat-grid metrics for hall listing payloads."""
    category_rows = {
        "normal": 0,
        "executive": 0,
        "premium": 0,
        "vip": 0,
    }
    seat_count = int(seat_count_hint or 0)
    if seat_count <= 0:
        seat_count = Seat.objects.filter(screen_id=screen.id).count()
    if seat_count <= 0:
        return {
            "seat_count": 0,
            "total_rows": 0,
            "total_columns": 0,
            "category_rows": category_rows,
        }

    seats = list(
        Seat.objects.filter(screen_id=screen.id).values_list(
            "row_label", "seat_number", "seat_type"
        )
    )
    if not seats:
        return {
            "seat_count": seat_count,
            "total_rows": 0,
            "total_columns": 0,
            "category_rows": category_rows,
        }

    row_labels = sorted(
        {
            str(row_label or "").strip().upper()
            for row_label, _, _ in seats
            if str(row_label or "").strip()
        },
        key=_row_label_sort_key,
    )

    column_set: set[int] = set()
    row_category_map: dict[str, str] = {}
    for row_label, seat_number, seat_type in seats:
        parsed_column = _parse_numeric_seat_number(seat_number)
        if parsed_column is not None:
            column_set.add(parsed_column)

        row_text = str(row_label or "").strip().upper()
        if not row_text or row_text in row_category_map:
            continue
        row_category_map[row_text] = _normalize_seat_category(seat_type)

    for row_label in row_labels:
        category_label = row_category_map.get(row_label, SEAT_CATEGORY_NORMAL)
        key = SEAT_CATEGORY_KEYS.get(category_label, "normal")
        category_rows[key] += 1

    return {
        "seat_count": seat_count,
        "total_rows": len(row_labels),
        "total_columns": len(column_set),
        "category_rows": category_rows,
    }


_AUTO_HALL_PATTERN = re.compile(r"^hall\s+([a-z]+)$", re.IGNORECASE)


def _hall_letters_to_index(value: str) -> Optional[int]:
    """Convert alphabetical hall suffix (A, Z, AA) to a 1-based index."""
    letters = str(value or "").strip().upper()
    if not letters or not letters.isalpha():
        return None
    index = 0
    for char in letters:
        index = (index * 26) + (ord(char) - ord("A") + 1)
    return index if index > 0 else None


def _hall_index_to_letters(index: int) -> str:
    """Convert a 1-based index to alphabetical hall suffix (1->A, 27->AA)."""
    value = max(1, int(index))
    letters: list[str] = []
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _hall_name_sort_key(value: Any) -> tuple[int, int, str]:
    """Sort auto-generated hall names in natural sequence before custom names."""
    text = str(value or "").strip()
    if not text:
        return (2, 0, "")
    match = _AUTO_HALL_PATTERN.fullmatch(text)
    if match:
        hall_index = _hall_letters_to_index(match.group(1))
        if hall_index is not None:
            return (0, hall_index, "")
    return (1, 0, text.lower())


def _next_auto_hall_name(vendor: Vendor) -> str:
    """Return the next unique auto-generated hall name for one vendor."""
    existing_names = [
        str(item or "").strip()
        for item in Screen.objects.filter(vendor_id=vendor.id).values_list(
            "screen_number", flat=True
        )
    ]
    occupied = {name.lower() for name in existing_names if name}

    max_index = 0
    for name in existing_names:
        match = _AUTO_HALL_PATTERN.fullmatch(name)
        if not match:
            continue
        hall_index = _hall_letters_to_index(match.group(1))
        if hall_index and hall_index > max_index:
            max_index = hall_index

    next_index = max_index + 1
    while next_index <= 10000:
        candidate = f"Hall {_hall_index_to_letters(next_index)}"
        if candidate.lower() not in occupied:
            return candidate
        next_index += 1

    # Fallback should never be reached under normal usage.
    return f"Hall {_hall_index_to_letters(max_index + 1)}"


def _serialize_vendor_hall(screen: Screen) -> dict[str, Any]:
    """Serialize hall metadata for vendor hall management views."""
    seat_count_hint = getattr(screen, "seat_count", None)
    seat_count = int(seat_count_hint or 0)
    layout_summary = _summarize_screen_layout(screen, seat_count_hint=seat_count)
    return {
        "id": screen.id,
        "hall": screen.screen_number,
        "screen_type": screen.screen_type,
        "capacity": int(screen.capacity or 0) if screen.capacity is not None else 0,
        "seat_count": layout_summary["seat_count"],
        "has_layout": bool(layout_summary["seat_count"] > 0),
        "total_rows": layout_summary["total_rows"],
        "total_columns": layout_summary["total_columns"],
        "category_rows": layout_summary["category_rows"],
        "status": screen.status,
    }


def list_vendor_halls(request: Any) -> tuple[dict[str, Any], int]:
    """List halls/screens for the authenticated vendor."""
    query_payload = {
        key: request.query_params.get(key) for key in request.query_params.keys()
    }
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, query_payload)
    if error_payload:
        return error_payload, status_code

    screens = list(
        Screen.objects.filter(vendor_id=vendor.id)
        .annotate(seat_count=Count("seats", distinct=True))
        .order_by("id")
    )
    screens.sort(key=lambda item: _hall_name_sort_key(item.screen_number))

    return {
        "vendor_id": vendor.id,
        "vendor_name": vendor.name,
        "halls": [_serialize_vendor_hall(screen) for screen in screens],
        "next_hall_name": _next_auto_hall_name(vendor),
    }, status.HTTP_200_OK


def create_vendor_hall(request: Any) -> tuple[dict[str, Any], int]:
    """Create a new vendor hall with auto-generated sequential name."""
    payload = get_payload(request)
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, payload)
    if error_payload:
        return error_payload, status_code

    screen_type_value = str(coalesce(payload, "screen_type", "screenType") or "").strip() or None

    total_rows = _parse_positive_int(
        coalesce(payload, "rows", "row_count", "rowCount"),
        default=10,
        minimum=1,
        maximum=52,
    )
    total_columns = _parse_positive_int(
        coalesce(payload, "columns", "cols", "column_count", "columnCount"),
        default=15,
        minimum=1,
        maximum=40,
    )
    category_counts = _normalize_category_counts(total_rows, payload)

    created_screen = None
    category_prices: dict[str, Optional[Decimal]] = {
        "normal": None,
        "executive": None,
        "premium": None,
        "vip": None,
    }
    created_seat_count = 0
    with transaction.atomic():
        for _ in range(10):
            next_name = _next_auto_hall_name(vendor)
            try:
                created_screen = Screen.objects.create(
                    vendor_id=vendor.id,
                    screen_number=next_name,
                    screen_type=screen_type_value,
                    status="Active",
                )
                break
            except IntegrityError:
                continue

        if created_screen:
            category_prices = _normalize_category_prices(payload, screen=created_screen)
            created_screen.capacity = total_rows * total_columns
            created_screen.normal_price = category_prices.get("normal")
            created_screen.executive_price = category_prices.get("executive")
            created_screen.premium_price = category_prices.get("premium")
            created_screen.vip_price = category_prices.get("vip")
            created_screen.status = "Active"
            created_screen.save(
                update_fields=[
                    "capacity",
                    "normal_price",
                    "executive_price",
                    "premium_price",
                    "vip_price",
                    "status",
                ]
            )

            row_labels = [_row_label_from_index(index) for index in range(total_rows)]
            row_category_map = _build_row_category_map(row_labels, category_counts)
            seats_to_create: list[Seat] = []
            for row_label in row_labels:
                seat_category = row_category_map.get(row_label, SEAT_CATEGORY_NORMAL)
                for col in range(1, total_columns + 1):
                    seats_to_create.append(
                        Seat(
                            screen=created_screen,
                            row_label=row_label,
                            seat_number=str(col),
                            seat_type=seat_category,
                        )
                    )
            if seats_to_create:
                Seat.objects.bulk_create(seats_to_create)
                created_seat_count = len(seats_to_create)

    if not created_screen:
        return {
            "message": "Unable to auto-generate a unique hall name. Please try again.",
        }, status.HTTP_409_CONFLICT

    created_screen.seat_count = created_seat_count
    return {
        "message": "Hall created with default seat layout.",
        "vendor_id": vendor.id,
        "hall": _serialize_vendor_hall(created_screen),
        "layout": {
            "total_rows": total_rows,
            "total_columns": total_columns,
            "category_rows": category_counts,
            "category_prices": _serialize_category_prices(category_prices),
            "total_seats": created_seat_count,
        },
        "next_hall_name": _next_auto_hall_name(vendor),
    }, status.HTTP_201_CREATED


def _resolve_vendor_for_payload(
    request: Any, payload: dict[str, Any]
) -> tuple[Optional[Vendor], Optional[dict[str, Any]], int]:
    """Resolve vendor identity from request or explicit payload values."""
    vendor_actor = resolve_vendor(request)
    admin_actor = resolve_admin(request)
    vendor_id = _coerce_int(
        coalesce(payload, "vendor_id", "vendorId", "cinema_id", "cinemaId")
    )

    if vendor_actor:
        if vendor_id and int(vendor_id) != int(vendor_actor.id):
            return None, {"message": "Vendor access denied."}, status.HTTP_403_FORBIDDEN
        return vendor_actor, None, status.HTTP_200_OK

    if admin_actor:
        if not vendor_id:
            return (
                None,
                {"message": "vendor_id is required for admin requests."},
                status.HTTP_400_BAD_REQUEST,
            )
        vendor = Vendor.objects.filter(pk=vendor_id).first()
        if not vendor:
            return None, {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
        return vendor, None, status.HTTP_200_OK

    if not vendor_id:
        return (
            None,
            {"message": "vendor_id is required."},
            status.HTTP_400_BAD_REQUEST,
        )

    vendor = Vendor.objects.filter(pk=vendor_id).first()
    if not vendor:
        return None, {"message": "Vendor not found."}, status.HTTP_404_NOT_FOUND
    return vendor, None, status.HTTP_200_OK


def _resolve_show_for_vendor(vendor: Vendor, payload: dict[str, Any]) -> Optional[Show]:
    """Resolve a vendor-owned show from payload context."""
    show_id = _coerce_int(coalesce(payload, "show_id", "showId"))
    if show_id:
        return Show.objects.filter(pk=show_id, vendor_id=vendor.id).first()

    movie_id = _coerce_int(coalesce(payload, "movie_id", "movieId", "movie"))
    show_date = parse_date(coalesce(payload, "date", "show_date", "showDate"))
    show_time = _parse_flexible_time(
        coalesce(payload, "time", "start", "start_time", "startTime")
    )
    if not movie_id or not show_date or not show_time:
        return None

    queryset = Show.objects.filter(
        vendor_id=vendor.id,
        movie_id=movie_id,
        show_date=show_date,
        start_time=show_time,
    )
    hall = str(coalesce(payload, "hall", "cinema_hall", "cinemaHall") or "").strip()
    if hall:
        queryset = queryset.filter(hall__iexact=hall)
    return queryset.order_by("id").first()


def _build_screen_layout_payload(
    screen: Optional[Screen], showtime: Optional[Showtime] = None, show: Optional[Show] = None
) -> dict[str, Any]:
    """Build seat layout payload from screen seats and optional showtime statuses."""
    if not screen:
        return _build_default_layout_payload()

    seats = list(
        Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
    )
    if not seats:
        payload = _build_default_layout_payload()
        payload.update(
            {
                "screen_id": screen.id,
                "hall": screen.screen_number,
                "vendor_id": screen.vendor_id,
                "show_id": show.id if show else None,
                "showtime_id": showtime.id if showtime else None,
            }
        )
        return payload

    row_labels = sorted(
        {str(seat.row_label or "").strip().upper() for seat in seats if seat.row_label},
        key=_row_label_sort_key,
    )
    parsed_columns = []
    for seat in seats:
        number_text = str(seat.seat_number or "").strip()
        match = re.search(r"\d+", number_text)
        if not match:
            continue
        parsed_columns.append(int(match.group(0)))
    seat_columns = sorted(set(parsed_columns)) or list(range(1, 16))

    if showtime:
        _prune_expired_reservations(showtime)
    sold_labels = set(_collect_sold_labels_for_showtime(showtime, lock=False)) if showtime else set()
    unavailable_labels = (
        set(_collect_unavailable_labels_for_showtime(showtime, lock=False)) if showtime else set()
    )
    reserved_labels = (
        set(_collect_reserved_labels_for_showtime(showtime, lock=False)) if showtime else set()
    )
    reserved_lock_deadlines = (
        _collect_reserved_lock_deadlines_for_showtime(showtime, lock=False)
        if showtime
        else {}
    )
    category_prices = _collect_screen_category_prices(screen=screen, showtime=showtime)

    category_rows: dict[str, set[str]] = {
        category: set() for category in SEAT_CATEGORY_ORDER
    }
    seat_items = []
    for seat in seats:
        category_label = _normalize_seat_category(seat.seat_type)
        row_label = str(seat.row_label or "").strip().upper()
        seat_label = _join_seat_label(row_label, seat.seat_number)
        category_rows[category_label].add(row_label)

        seat_status = "available"
        if seat_label in sold_labels:
            seat_status = "booked"
        elif seat_label in unavailable_labels:
            seat_status = "unavailable"
        elif seat_label in reserved_labels:
            seat_status = "reserved"

        seat_items.append(
            {
                "id": seat.id,
                "row_label": row_label,
                "seat_number": str(seat.seat_number or ""),
                "label": seat_label,
                "seat_type": category_label,
                "seat_price": (
                    float(category_prices.get(SEAT_CATEGORY_KEYS[category_label]))
                    if category_prices.get(SEAT_CATEGORY_KEYS[category_label]) is not None
                    else None
                ),
                "status": seat_status,
            }
        )

    seat_groups = []
    for category_label in SEAT_CATEGORY_ORDER:
        rows = sorted(category_rows[category_label], key=_row_label_sort_key)
        seat_groups.append(
            {
                "key": SEAT_CATEGORY_KEYS[category_label],
                "label": category_label,
                "rows": rows,
            }
        )

    return {
        "screen_id": screen.id,
        "hall": screen.screen_number,
        "vendor_id": screen.vendor_id,
        "show_id": show.id if show else None,
        "showtime_id": showtime.id if showtime else None,
        "category_prices": _serialize_category_prices(category_prices),
        "seat_groups": seat_groups,
        "seat_columns": seat_columns,
        "row_labels": row_labels,
        "seats": seat_items,
        "sold_seats": sorted(sold_labels, key=_seat_sort_key),
        "unavailable_seats": sorted(unavailable_labels, key=_seat_sort_key),
        "reserved_seats": sorted(reserved_labels, key=_seat_sort_key),
        "reserved_seat_locks": reserved_lock_deadlines,
        "reservation_hold_minutes": RESERVE_HOLD_MINUTES,
        "total_rows": len(row_labels),
        "total_columns": len(seat_columns),
        "total_seats": len(seat_items),
    }


def list_vendor_seat_layout(request: Any) -> tuple[dict[str, Any], int]:
    """Return vendor seat layout for hall/show management."""
    query_payload = {
        key: request.query_params.get(key) for key in request.query_params.keys()
    }
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, query_payload)
    if error_payload:
        return error_payload, status_code

    show = _resolve_show_for_vendor(vendor, query_payload)
    hall = str(
        coalesce(query_payload, "hall", "cinema_hall", "cinemaHall", default=show.hall if show else "")
        or ""
    ).strip()

    screen = None
    if hall:
        screen = Screen.objects.filter(vendor_id=vendor.id, screen_number__iexact=hall).first()
        if screen:
            hall = str(screen.screen_number or "").strip()
        else:
            return {
                "message": "Selected hall does not exist.",
            }, status.HTTP_404_NOT_FOUND
    if not screen:
        screen = Screen.objects.filter(vendor_id=vendor.id).order_by("id").first()

    showtime = None
    if show:
        showtime = _find_showtime_for_context(show, hall or None)

    payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "hall": hall or payload.get("hall"),
            "reservedSeats": payload.get("reserved_seats") or [],
        }
    )
    return payload, status.HTTP_200_OK


def create_or_update_vendor_seat_layout(request: Any) -> tuple[dict[str, Any], int]:
    """Create or update seat layout rows/columns/categories for a vendor hall."""
    payload = get_payload(request)
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, payload)
    if error_payload:
        return error_payload, status_code

    hall = str(coalesce(payload, "hall", "cinema_hall", "cinemaHall") or "").strip()
    if not hall:
        return {"message": "hall is required."}, status.HTTP_400_BAD_REQUEST

    screen = Screen.objects.filter(vendor_id=vendor.id, screen_number__iexact=hall).first()
    if not screen:
        return {
            "message": "Selected hall does not exist. Please add hall first.",
        }, status.HTTP_400_BAD_REQUEST

    hall = str(screen.screen_number or "").strip() or hall

    existing_layout_seats = list(
        Seat.objects.filter(screen=screen).order_by("row_label", "seat_number", "id")
    )
    existing_row_labels = sorted(
        {
            str(seat.row_label or "").strip().upper()
            for seat in existing_layout_seats
            if str(seat.row_label or "").strip()
        },
        key=_row_label_sort_key,
    )
    existing_column_set: set[int] = set()
    for seat in existing_layout_seats:
        parsed_column = _parse_numeric_seat_number(seat.seat_number)
        if parsed_column is not None:
            existing_column_set.add(parsed_column)
    existing_columns = sorted(existing_column_set)

    rows_provided = _payload_has_non_empty_value(payload, "rows", "row_count", "rowCount")

    total_rows = _parse_positive_int(
        coalesce(payload, "rows", "row_count", "rowCount"),
        default=len(existing_row_labels) if existing_row_labels else 10,
        minimum=1,
        maximum=52,
    )
    total_columns = _parse_positive_int(
        coalesce(payload, "columns", "cols", "column_count", "columnCount"),
        default=len(existing_columns) if existing_columns else 15,
        minimum=1,
        maximum=40,
    )
    raw_category_rows = (
        payload.get("category_rows")
        if isinstance(payload.get("category_rows"), dict)
        else {}
    )
    has_category_row_overrides = bool(raw_category_rows) or _payload_has_non_empty_value(
        payload,
        "normal_rows",
        "normalRows",
        "executive_rows",
        "executiveRows",
        "premium_rows",
        "premiumRows",
        "vip_rows",
        "vipRows",
    )

    if has_category_row_overrides:
        provided_counts = {
            "normal": _parse_positive_int(
                coalesce(
                    raw_category_rows,
                    "normal",
                    default=coalesce(payload, "normal_rows", "normalRows", default=0),
                ),
                default=0,
                minimum=0,
                maximum=52,
            ),
            "executive": _parse_positive_int(
                coalesce(
                    raw_category_rows,
                    "executive",
                    default=coalesce(payload, "executive_rows", "executiveRows", default=0),
                ),
                default=0,
                minimum=0,
                maximum=52,
            ),
            "premium": _parse_positive_int(
                coalesce(
                    raw_category_rows,
                    "premium",
                    default=coalesce(payload, "premium_rows", "premiumRows", default=0),
                ),
                default=0,
                minimum=0,
                maximum=52,
            ),
            "vip": _parse_positive_int(
                coalesce(
                    raw_category_rows,
                    "vip",
                    default=coalesce(payload, "vip_rows", "vipRows", default=0),
                ),
                default=0,
                minimum=0,
                maximum=52,
            ),
        }
        provided_total = sum(provided_counts.values())
        if rows_provided and provided_total > 0 and provided_total != total_rows:
            return {
                "message": (
                    f"rows ({total_rows}) must match the total category rows ({provided_total})."
                )
            }, status.HTTP_400_BAD_REQUEST
        if provided_total > 0 and not rows_provided:
            total_rows = max(1, min(52, provided_total))
        category_counts = _normalize_category_counts(total_rows, payload)
    elif existing_row_labels:
        existing_category_counts = {
            "normal": 0,
            "executive": 0,
            "premium": 0,
            "vip": 0,
        }
        row_category_map_existing: dict[str, str] = {}
        for seat in existing_layout_seats:
            row_text = str(seat.row_label or "").strip().upper()
            if not row_text or row_text in row_category_map_existing:
                continue
            row_category_map_existing[row_text] = _normalize_seat_category(seat.seat_type)
        for row_label in existing_row_labels:
            category_label = row_category_map_existing.get(row_label, SEAT_CATEGORY_NORMAL)
            existing_category_counts[SEAT_CATEGORY_KEYS.get(category_label, "normal")] += 1
        category_counts = _normalize_category_counts(
            total_rows,
            {"category_rows": existing_category_counts},
        )
    else:
        category_counts = _default_category_counts(total_rows)

    screen.capacity = total_rows * total_columns
    provided_screen_type = coalesce(payload, "screen_type", "screenType")
    if provided_screen_type:
        screen.screen_type = provided_screen_type
    category_prices = _normalize_category_prices(payload, screen=screen)
    screen.normal_price = category_prices.get("normal")
    screen.executive_price = category_prices.get("executive")
    screen.premium_price = category_prices.get("premium")
    screen.vip_price = category_prices.get("vip")
    screen.status = "Active"
    screen.save(
        update_fields=[
            "capacity",
            "screen_type",
            "normal_price",
            "executive_price",
            "premium_price",
            "vip_price",
            "status",
        ]
    )

    row_labels = [_row_label_from_index(index) for index in range(total_rows)]
    row_category_map = _build_row_category_map(row_labels, category_counts)
    mutation_conflicts = {"category_locked": [], "deletion_locked": []}

    desired_pairs = set()
    for row_label in row_labels:
        seat_category = row_category_map.get(row_label, SEAT_CATEGORY_NORMAL)
        for col in range(1, total_columns + 1):
            seat_number = str(col)
            desired_pairs.add((row_label, seat_number))
            seat, created = Seat.objects.get_or_create(
                screen=screen,
                row_label=row_label,
                seat_number=seat_number,
                defaults={"seat_type": seat_category},
            )
            if not created and _normalize_seat_category(seat.seat_type) != seat_category:
                if _seat_has_booked_history(seat):
                    mutation_conflicts["category_locked"].append(
                        _join_seat_label(row_label, seat_number)
                    )
                    continue
                seat.seat_type = seat_category
                seat.save(update_fields=["seat_type"])

    for seat in existing_layout_seats:
        pair = (str(seat.row_label or "").upper(), str(seat.seat_number or ""))
        if pair in desired_pairs:
            continue
        if _seat_has_layout_mutation_lock(seat):
            mutation_conflicts["deletion_locked"].append(
                _join_seat_label(seat.row_label, seat.seat_number)
            )
            continue
        seat.delete()

    show = _resolve_show_for_vendor(vendor, payload)
    showtime = _find_showtime_for_context(show, hall) if show else None
    locked_category_seats = sorted(
        set(mutation_conflicts["category_locked"]), key=_seat_sort_key
    )
    locked_deletion_seats = sorted(
        set(mutation_conflicts["deletion_locked"]), key=_seat_sort_key
    )
    protected_count = len(locked_category_seats) + len(locked_deletion_seats)
    message = "Seat layout saved."
    if protected_count:
        message = (
            f"Seat layout saved. {protected_count} seat(s) were protected because they are already booked or actively locked."
        )

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "category_rows": category_counts,
            "category_prices": _serialize_category_prices(category_prices),
            "locked_category_seats": locked_category_seats,
            "locked_deletion_seats": locked_deletion_seats,
            "message": message,
        }
    )
    return layout_payload, status.HTTP_200_OK


def update_vendor_seat_status(request: Any) -> tuple[dict[str, Any], int]:
    """Update per-show seat status for vendor seats."""
    payload = get_payload(request)
    vendor, error_payload, status_code = _resolve_vendor_for_payload(request, payload)
    if error_payload:
        return error_payload, status_code

    show = _resolve_show_for_vendor(vendor, payload)
    if not show:
        return {"message": "show_id or valid show context is required."}, status.HTTP_400_BAD_REQUEST

    target_status = str(coalesce(payload, "status", "seat_status") or "").strip().lower()
    if target_status not in (
        SEAT_STATUS_AVAILABLE.lower(),
        SEAT_STATUS_UNAVAILABLE.lower(),
    ):
        return {"message": "status must be Available or Unavailable."}, status.HTTP_400_BAD_REQUEST

    status_label = (
        SEAT_STATUS_UNAVAILABLE
        if target_status == SEAT_STATUS_UNAVAILABLE.lower()
        else SEAT_STATUS_AVAILABLE
    )
    seat_labels = _normalize_seat_labels(
        coalesce(payload, "seat_labels", "seatLabels", "selected_seats", "selectedSeats", "seats")
    )
    if not seat_labels:
        return {"message": "seat_labels are required."}, status.HTTP_400_BAD_REQUEST

    hall = str(
        coalesce(payload, "hall", "cinema_hall", "cinemaHall", default=show.hall) or ""
    ).strip()
    screen, showtime = _get_or_create_showtime_for_context(show, hall or None)

    conflicts = {"booked": [], "invalid": []}
    updated = []
    with transaction.atomic():
        for label in seat_labels:
            row_label, seat_number = _split_seat_label(label)
            if not seat_number:
                conflicts["invalid"].append(label)
                continue

            seat = Seat.objects.filter(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            ).first()
            if not seat:
                conflicts["invalid"].append(label)
                continue

            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                conflicts["booked"].append(label)
                continue

            availability.seat_status = status_label
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])
            updated.append(label)

    if not updated and conflicts["invalid"] and not conflicts["booked"]:
        return {
            "message": "Selected seats are not part of this hall layout.",
            "conflicts": {
                "booked": sorted(conflicts["booked"], key=_seat_sort_key),
                "invalid": sorted(conflicts["invalid"], key=_seat_sort_key),
            },
        }, status.HTTP_400_BAD_REQUEST

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "vendor_id": vendor.id,
            "vendor_name": vendor.name,
            "updated_seats": sorted(updated, key=_seat_sort_key),
            "conflicts": {
                "booked": sorted(conflicts["booked"], key=_seat_sort_key),
                "invalid": sorted(conflicts["invalid"], key=_seat_sort_key),
            },
            "message": "Seat status updated.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def list_booking_seat_layout(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return booking seat layout with category rows and seat statuses."""
    context = _resolve_booking_context(payload)
    show = _resolve_show_for_context(context)
    if not show:
        fallback = _build_default_layout_payload()
        fallback.update({"show_id": None, "showtime_id": None})
        return fallback, status.HTTP_200_OK

    show_booking_error, _ = _ensure_show_is_bookable(show)
    if show_booking_error:
        fallback = _build_default_layout_payload()
        fallback.update(
            {
                "show_id": show.id,
                "showtime_id": None,
                "booking_enabled": False,
                "message": show_booking_error.get("message"),
                "booking_close_at": show_booking_error.get("booking_close_at"),
            }
        )
        return fallback, status.HTTP_200_OK

    hall = str(context.get("hall") or show.hall or "").strip()
    screen = None
    if hall:
        screen = Screen.objects.filter(vendor_id=show.vendor_id, screen_number__iexact=hall).first()
    if not screen:
        screen = Screen.objects.filter(vendor_id=show.vendor_id).order_by("id").first()

    showtime = _find_showtime_for_context(show, hall or None)
    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "show_id": show.id,
            "hall": hall or layout_payload.get("hall"),
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "date": show.show_date.isoformat() if show.show_date else None,
            "time": show.start_time.strftime("%H:%M") if show.start_time else None,
            "reservedSeats": layout_payload.get("reserved_seats") or [],
        }
    )
    return layout_payload, status.HTTP_200_OK


def reserve_booking_seats(request: Any) -> tuple[dict[str, Any], int]:
    """Reserve seats temporarily for a booking context."""
    payload = get_payload(request)
    context = _resolve_booking_context(payload)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND
    show_booking_error, show_booking_status = _ensure_show_is_bookable(show)
    if show_booking_error:
        return show_booking_error, int(show_booking_status)

    hall = context.get("hall") or show.hall
    screen, showtime = _get_or_create_showtime_for_context(show, hall)
    _prune_expired_reservations(showtime)

    now = timezone.now()
    lock_until = now + timedelta(minutes=RESERVE_HOLD_MINUTES)
    conflicts = {"sold": [], "unavailable": [], "reserved": [], "invalid": []}
    updated = []

    with transaction.atomic():
        for label in selected_seats:
            row_label, seat_number = _split_seat_label(label)
            if not seat_number:
                conflicts["invalid"].append(label)
                continue

            seat = Seat.objects.filter(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            ).first()
            if not seat:
                conflicts["invalid"].append(label)
                continue

            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                conflicts["sold"].append(label)
                continue
            if current_status == SEAT_STATUS_UNAVAILABLE.lower():
                conflicts["unavailable"].append(label)
                continue
            if availability.locked_until and availability.locked_until > now:
                conflicts["reserved"].append(label)
                continue

            availability.seat_status = SEAT_STATUS_AVAILABLE
            availability.locked_until = lock_until
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])
            updated.append(label)

    if not updated and conflicts["invalid"] and not (
        conflicts["sold"] or conflicts["unavailable"] or conflicts["reserved"]
    ):
        return {
            "message": "Selected seats are not part of this hall layout.",
            "conflicts": {
                "sold": sorted(conflicts["sold"], key=_seat_sort_key),
                "unavailable": sorted(conflicts["unavailable"], key=_seat_sort_key),
                "reserved": sorted(conflicts["reserved"], key=_seat_sort_key),
                "invalid": sorted(conflicts["invalid"], key=_seat_sort_key),
            },
        }, status.HTTP_400_BAD_REQUEST

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "show_id": show.id,
            "hall": hall or layout_payload.get("hall"),
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "date": show.show_date.isoformat() if show.show_date else None,
            "time": show.start_time.strftime("%H:%M") if show.start_time else None,
            "updated_seats": sorted(updated, key=_seat_sort_key),
            "conflicts": {
                "sold": sorted(conflicts["sold"], key=_seat_sort_key),
                "unavailable": sorted(conflicts["unavailable"], key=_seat_sort_key),
                "reserved": sorted(conflicts["reserved"], key=_seat_sort_key),
                "invalid": sorted(conflicts["invalid"], key=_seat_sort_key),
            },
            "message": "Seats reserved.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def release_booking_seats(request: Any) -> tuple[dict[str, Any], int]:
    """Release reserved seats for a booking context."""
    payload = get_payload(request)
    context = _resolve_booking_context(payload)
    selected_seats = context.get("selected_seats") or []
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND

    hall = context.get("hall") or show.hall
    screen, showtime = _get_or_create_showtime_for_context(show, hall)
    _prune_expired_reservations(showtime)

    released = []
    invalid = []
    with transaction.atomic():
        for label in selected_seats:
            row_label, seat_number = _split_seat_label(label)
            if not seat_number:
                invalid.append(label)
                continue
            seat = Seat.objects.filter(
                screen=screen,
                row_label=row_label or None,
                seat_number=seat_number,
            ).first()
            if not seat:
                invalid.append(label)
                continue
            availability = (
                SeatAvailability.objects.select_for_update()
                .filter(seat=seat, showtime=showtime)
                .first()
            )
            if not availability:
                continue
            current_status = str(availability.seat_status or "").strip().lower()
            if current_status in BOOKED_STATUSES:
                continue
            if current_status == SEAT_STATUS_UNAVAILABLE.lower():
                continue
            if availability.locked_until:
                availability.locked_until = None
                availability.save(update_fields=["locked_until", "last_updated"])
                released.append(label)

    track_dropoff = parse_bool(
        coalesce(payload, "track_dropoff", "trackDropoff"),
        default=False,
    )
    dropoff_stage = str(
        coalesce(payload, "dropoff_stage", "dropoffStage", default="") or ""
    ).strip().upper()
    if track_dropoff and dropoff_stage == BookingDropoffEvent.STAGE_BOOKING:
        try:
            customer = resolve_customer(request)
        except Exception:
            customer = None
        requested_reason = str(
            coalesce(payload, "dropoff_reason", "dropoffReason", default="") or ""
        ).strip().upper()
        _record_booking_dropoff_event(
            stage=BookingDropoffEvent.STAGE_BOOKING,
            reason=(
                requested_reason
                if requested_reason
                else BookingDropoffEvent.REASON_LEFT_BOOKING_PROCESS
            ),
            seat_count=len(selected_seats),
            user=customer,
            vendor=show.vendor,
            show=show,
            metadata={
                "show_id": show.id,
                "hall": hall,
                "released_seats": sorted(released, key=_seat_sort_key),
                "requested_seats": sorted(selected_seats, key=_seat_sort_key),
            },
        )

    layout_payload = _build_screen_layout_payload(screen, showtime=showtime, show=show)
    layout_payload.update(
        {
            "show_id": show.id,
            "hall": hall or layout_payload.get("hall"),
            "vendor_id": show.vendor_id,
            "movie_id": show.movie_id,
            "date": show.show_date.isoformat() if show.show_date else None,
            "time": show.start_time.strftime("%H:%M") if show.start_time else None,
            "released_seats": sorted(released, key=_seat_sort_key),
            "invalid_seats": sorted(invalid, key=_seat_sort_key),
            "message": "Seats released.",
        }
    )
    return layout_payload, status.HTTP_200_OK


def create_booking_resume_notification(request: Any) -> tuple[dict[str, Any], int]:
    """Create or refresh a customer notification to continue a held booking flow."""
    customer = resolve_customer(request)
    if not customer:
        return {"message": AUTH_REQUIRED_MESSAGE}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    context = _resolve_booking_context(payload)
    selected_seats = _normalize_seat_labels(
        coalesce(
            context,
            "selected_seats",
            default=coalesce(payload, "selected_seats", "selectedSeats", "seats"),
        )
    )
    if not selected_seats:
        return {"message": "selected_seats are required."}, status.HTTP_400_BAD_REQUEST

    if not context.get("movie_id") or not context.get("cinema_id") or not context.get("show_date") or not context.get("show_time"):
        return {
            "message": "Booking context is incomplete. Provide cinema, movie, date, time, and selected seats.",
        }, status.HTTP_400_BAD_REQUEST

    show = _resolve_show_for_context(context)
    if not show:
        return {"message": "Selected show was not found."}, status.HTTP_404_NOT_FOUND
    show_booking_error, show_booking_status = _ensure_show_is_bookable(show)
    if show_booking_error:
        return show_booking_error, int(show_booking_status)

    hall = context.get("hall") or show.hall
    screen, showtime = _get_or_create_showtime_for_context(show, hall)
    _prune_expired_reservations(showtime)

    now = timezone.now()
    active_seats: list[str] = []
    lock_deadlines: list[Any] = []
    for label in selected_seats:
        row_label, seat_number = _split_seat_label(label)
        if not seat_number:
            continue

        seat = Seat.objects.filter(
            screen=screen,
            row_label=row_label or None,
            seat_number=seat_number,
        ).first()
        if not seat:
            continue

        availability = SeatAvailability.objects.filter(seat=seat, showtime=showtime).first()
        if not availability:
            continue

        current_status = str(availability.seat_status or "").strip().lower()
        if current_status in BOOKED_STATUSES:
            continue
        if current_status == SEAT_STATUS_UNAVAILABLE.lower():
            continue
        if availability.locked_until and availability.locked_until > now:
            active_seats.append(label)
            lock_deadlines.append(availability.locked_until)

    if not active_seats:
        return {
            "message": "No active seat hold found to continue.",
        }, status.HTTP_400_BAD_REQUEST

    expires_at = (
        min(lock_deadlines)
        if lock_deadlines
        else now + timedelta(minutes=BOOKING_RESUME_NOTICE_WINDOW_MINUTES)
    )

    show_date_text = (
        show.show_date.isoformat() if show.show_date else str(context.get("show_date") or "")
    )
    show_time_text = (
        show.start_time.strftime("%H:%M") if show.start_time else str(context.get("show_time") or "")
    )

    sorted_seats = sorted(active_seats, key=_seat_sort_key)
    resume_context = {
        "movie_id": show.movie_id,
        "movie_title": show.movie.title if show.movie else None,
        "cinema_id": show.vendor_id,
        "cinema_name": show.vendor.name if show.vendor else None,
        "show_id": show.id,
        "hall": hall or "",
        "date": show_date_text,
        "time": show_time_text,
        "selected_seats": sorted_seats,
    }
    notice_key = (
        f"RESUME_BOOKING:{customer.id}:{show.id}:{showtime.id}:"
        f"{','.join(sorted_seats)}"
    )

    metadata = {
        "notice_key": notice_key,
        "request_status": "PENDING",
        "expires_at": expires_at.isoformat(),
        "hold_minutes": BOOKING_RESUME_NOTICE_WINDOW_MINUTES,
        "resume_path": "/booking",
        "resume_context": resume_context,
        "movie_title": resume_context.get("movie_title"),
        "vendor_name": resume_context.get("cinema_name"),
        "show_date": show_date_text,
        "show_time": show_time_text,
        "seat_count": len(sorted_seats),
        "seats": sorted_seats,
    }

    title = "Continue your booking"
    message = (
        f"{len(sorted_seats)} seat(s) are on hold for "
        f"{resume_context.get('movie_title') or 'your movie'}. Continue within 10 minutes."
    )

    existing = (
        Notification.objects.filter(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=customer.id,
            event_type=Notification.EVENT_BOOKING_RESUME_PENDING,
            metadata__notice_key=notice_key,
            metadata__request_status="PENDING",
        )
        .order_by("-created_at", "-id")
        .first()
    )

    if existing:
        existing.title = title
        existing.message = message
        existing.metadata = metadata
        existing.is_read = False
        existing.read_at = None
        existing.save(update_fields=["title", "message", "metadata", "is_read", "read_at"])
        notification = existing
    else:
        notification = _create_notification(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=customer.id,
            recipient_email=customer.email,
            event_type=Notification.EVENT_BOOKING_RESUME_PENDING,
            title=title,
            message=message,
            metadata=metadata,
            send_email_too=False,
        )

    return {
        "message": "Resume notification created.",
        "notification_id": notification.id,
        "expires_at": metadata["expires_at"],
        "resume_context": resume_context,
    }, status.HTTP_200_OK


def bulk_assign_booking_seats(request: Any, booking: Booking) -> tuple[dict[str, Any], int]:
    """Assign bulk corporate seats to an existing booking based on seat category counts."""
    payload = get_payload(request)
    category_payload = coalesce(
        payload,
        "seat_category_counts",
        "seatCategoryCounts",
        "category_counts",
        "categoryCounts",
    )
    if not isinstance(category_payload, dict):
        return {
            "message": "seat_category_counts must be an object with categories and quantities.",
        }, status.HTTP_400_BAD_REQUEST

    requested_categories: dict[str, int] = {}
    for raw_category, raw_quantity in category_payload.items():
        normalized_category = _normalize_seat_category(raw_category)
        if normalized_category not in SEAT_CATEGORY_ORDER:
            return {
                "message": f"Invalid seat category: {raw_category}",
            }, status.HTTP_400_BAD_REQUEST
        category_key = SEAT_CATEGORY_KEYS.get(normalized_category, "normal")
        quantity = _parse_positive_int(raw_quantity, default=0, minimum=0, maximum=10000)
        if quantity > 0:
            requested_categories[category_key] = requested_categories.get(category_key, 0) + quantity

    total_requested = sum(requested_categories.values())
    if total_requested <= 0:
        return {
            "message": "At least one seat category count must be greater than zero.",
        }, status.HTTP_400_BAD_REQUEST

    if booking.booking_status and str(booking.booking_status).strip().lower() == "cancelled":
        return {"message": "Cannot assign seats to a cancelled booking."}, status.HTTP_409_CONFLICT

    showtime = booking.showtime
    screen = getattr(showtime, "screen", None)
    if not showtime or not screen:
        return {
            "message": "Booking showtime or screen context is invalid.",
        }, status.HTTP_400_BAD_REQUEST

    show = Show.objects.filter(
        vendor_id=screen.vendor_id,
        movie_id=showtime.movie_id,
        show_date=showtime.start_time.date(),
        start_time=showtime.start_time.time(),
        hall=screen.screen_number,
    ).first()

    if not show:
        # Use fallback info from showtime when exact Show row is unavailable.
        class _FallbackShow:
            pass

        fallback = _FallbackShow()
        fallback.movie_id = showtime.movie_id
        fallback.show_date = showtime.start_time.date()
        fallback.price = showtime.price
        show = fallback

    available_seats = _available_target_seats_for_showtime(showtime, screen)
    seats_by_category: dict[str, list[Seat]] = {
        "normal": [],
        "executive": [],
        "premium": [],
        "vip": [],
    }
    for seat in available_seats:
        cat_key = _seat_category_key(seat.seat_type)
        seats_by_category.setdefault(cat_key, []).append(seat)

    chosen_seats: list[Seat] = []
    insufficient: dict[str, dict[str, int]] = {}
    for category_key, needed in requested_categories.items():
        available_for_category = seats_by_category.get(category_key, [])
        if len(available_for_category) < needed:
            insufficient[category_key] = {
                "requested": needed,
                "available": len(available_for_category),
            }
        else:
            chosen_seats.extend(available_for_category[:needed])

    if insufficient:
        return {
            "message": "Not enough available seats in one or more requested categories.",
            "insufficient": insufficient,
        }, status.HTTP_409_CONFLICT

    now = timezone.now()
    assigned_labels: list[str] = []
    total_amount = booking.total_amount or Decimal("0.00")
    with transaction.atomic():
        for seat in chosen_seats:
            availability, _ = SeatAvailability.objects.select_for_update().get_or_create(
                seat=seat,
                showtime=showtime,
                defaults={"seat_status": SEAT_STATUS_AVAILABLE},
            )
            status_value = str(availability.seat_status or "").strip().lower()
            if status_value in BOOKED_STATUSES:
                return {"message": "Some seats are no longer available."}, status.HTTP_409_CONFLICT
            if status_value == SEAT_STATUS_UNAVAILABLE.lower():
                return {"message": "Some seats are unavailable."}, status.HTTP_409_CONFLICT
            if availability.locked_until and availability.locked_until > now:
                return {"message": "Some seats are currently reserved."}, status.HTTP_409_CONFLICT

            availability.seat_status = SEAT_STATUS_BOOKED
            availability.locked_until = None
            availability.save(update_fields=["seat_status", "locked_until", "last_updated"])

            seat_price, _ = _resolve_dynamic_seat_price(
                show=show,
                showtime=showtime,
                screen=screen,
                seat_type=seat.seat_type,
                event_name="",
            )
            seat_price = seat_price or Decimal("0.00")
            BookingSeat.objects.create(
                booking=booking,
                showtime=showtime,
                seat=seat,
                seat_price=seat_price,
            )
            assigned_labels.append(_join_seat_label(seat.row_label, seat.seat_number))
            total_amount += seat_price

        booking.total_amount = total_amount
        booking.save(update_fields=["total_amount"])

    return {
        "message": "Corporate seats assigned successfully.",
        "booking_id": booking.id,
        "assigned_seats": sorted(assigned_labels, key=_seat_sort_key),
        "assigned_count": len(assigned_labels),
        "total_amount": float(total_amount),
    }, status.HTTP_200_OK


def _clamp_text(value: Any, limit: int = 44) -> str:
    """Clamp text to a fixed character limit."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def _load_font(size: int, bold: bool = False) -> Any:
    """Load the configured font or fall back to a default."""
    candidates = []
    if bold:
        candidates = [
            "arialbd.ttf",
            "Arial Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "arial.ttf",
            "Arial.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "DejaVuSans.ttf",
        ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _normalize_items(items: Any) -> list[dict[str, Any]]:
    """Normalize ticket line items from incoming payloads."""
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        qty = int(item.get("qty") or 0)
        price = _safe_number(item.get("price"))
        normalized.append({"name": name, "qty": qty, "price": price})
    return normalized


def _ensure_timezone_aware(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetimes into aware UTC values for backend consistency."""
    return ensure_utc_datetime(value)


def _combine_local_date_time(show_date: Any, show_time: Any) -> Optional[datetime]:
    """Combine a date and time into an aware UTC datetime when available."""
    if not show_date or not show_time:
        return None
    return combine_date_time_utc(show_date, show_time)


def _seat_summary_for_booking(booking: Optional[Booking], fallback: Any = None) -> Optional[str]:
    """Return a compact seat label string for display/validation payloads."""
    if booking:
        seat_labels = []
        booking_seats = booking.booking_seats.select_related("seat").all()
        for booking_seat in booking_seats:
            if booking_seat.seat:
                seat_labels.append(_seat_label(booking_seat.seat))
        if seat_labels:
            return ", ".join(seat_labels)

    if isinstance(fallback, list):
        labels = [str(label).strip() for label in fallback if str(label).strip()]
        return ", ".join(labels) if labels else None

    raw = str(fallback or "").strip()
    return raw or None


def _resolve_show_for_booking_ticket(booking: Optional[Booking]) -> Optional[Show]:
    """Resolve app.Show row from a booking's showtime context."""
    if not booking or not booking.showtime_id:
        return None
    showtime = booking.showtime
    if not showtime or not showtime.screen_id:
        return None
    return Show.objects.filter(
        vendor_id=showtime.screen.vendor_id,
        movie_id=showtime.movie_id,
        show_date=showtime.start_time.date(),
        start_time=showtime.start_time.time(),
    ).first()


def compute_ticket_validation_window(
    show_datetime: Optional[datetime],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Compute allowed scan window: 2 hours before show until 15 minutes after."""
    TICKET_VALIDATION_OPEN_WINDOW_HOURS = 2
    show_dt = _ensure_timezone_aware(show_datetime)
    if not show_dt:
        return None, None
    return (
        show_dt - timedelta(hours=TICKET_VALIDATION_OPEN_WINDOW_HOURS),
        show_dt + timedelta(minutes=TICKET_VALIDATION_GRACE_MINUTES),
    )


def resolve_ticket_token_expiry(show_datetime: Optional[datetime]) -> datetime:
    """Resolve token expiry from showtime, with fallback validity for legacy data."""
    _, window_end = compute_ticket_validation_window(show_datetime)
    if window_end:
        return window_end
    return timezone.now() + timedelta(hours=TICKET_QR_FALLBACK_VALIDITY_HOURS)


def build_ticket_security_fields(
    *,
    booking: Optional[Booking] = None,
    show: Optional[Show] = None,
    user: Optional[User] = None,
    seats: Any = None,
    show_datetime: Optional[datetime] = None,
    payment_status: Optional[str] = None,
) -> dict[str, Any]:
    """Build persistent secure ticket metadata from booking/show context."""
    resolved_show = show or _resolve_show_for_booking_ticket(booking)
    resolved_user = user or (booking.user if booking else None)

    resolved_show_datetime = _ensure_timezone_aware(show_datetime)
    if not resolved_show_datetime and booking and booking.showtime and booking.showtime.start_time:
        resolved_show_datetime = _ensure_timezone_aware(booking.showtime.start_time)
    if not resolved_show_datetime and resolved_show:
        resolved_show_datetime = _ensure_timezone_aware(resolved_show.start_datetime)
    if not resolved_show_datetime and resolved_show:
        resolved_show_datetime = _combine_local_date_time(resolved_show.show_date, resolved_show.start_time)

    normalized_payment_status = Ticket.normalize_payment_status(payment_status)

    return {
        "user": resolved_user,
        "show": resolved_show,
        "seats": _seat_summary_for_booking(booking, seats),
        "show_datetime": resolved_show_datetime,
        "payment_status": normalized_payment_status,
        "token_expires_at": resolve_ticket_token_expiry(resolved_show_datetime),
    }


def _ensure_ticket_security_defaults(ticket: Ticket, *, save: bool) -> Ticket:
    """Ensure required secure ticket fields are populated for old/new rows."""
    update_fields: list[str] = []

    if not ticket.ticket_id:
        ticket.ticket_id = uuid.uuid4()
        update_fields.append("ticket_id")

    if not ticket.show_datetime:
        candidate_show_datetime = None
        if ticket.show:
            candidate_show_datetime = ticket.show.start_datetime or _combine_local_date_time(
                ticket.show.show_date,
                ticket.show.start_time,
            )
        ticket.show_datetime = _ensure_timezone_aware(candidate_show_datetime)
        if ticket.show_datetime:
            update_fields.append("show_datetime")

    if not ticket.token_expires_at:
        ticket.token_expires_at = resolve_ticket_token_expiry(ticket.show_datetime)
        update_fields.append("token_expires_at")

    if not ticket.payment_status:
        ticket.payment_status = TICKET_PAYMENT_STATUS_PENDING
        update_fields.append("payment_status")

    if save and update_fields:
        ticket.save(update_fields=update_fields)

    return ticket


def generate_ticket_qr_token(ticket: Ticket) -> str:
    """Generate a signed token containing ticket identity + expiry."""
    ticket = _ensure_ticket_security_defaults(ticket, save=True)
    expiry = _ensure_timezone_aware(ticket.token_expires_at) or resolve_ticket_token_expiry(ticket.show_datetime)
    payload = {
        "ticket_id": str(ticket.ticket_id),
        "reference": str(ticket.reference or ""),
        "exp": int(expiry.timestamp()),
    }
    return signing.dumps(payload, salt=TICKET_QR_SIGNING_SALT, compress=True)


def build_ticket_qr_payload(ticket: Ticket) -> dict[str, Any]:
    """Build secure QR payload with UUID + signed token."""
    payload = ticket.payload if isinstance(ticket.payload, dict) else {}
    stored_payload = payload.get("qr_payload") if isinstance(payload, dict) else None
    if isinstance(stored_payload, dict):
        stored_token = str(stored_payload.get("token") or "").strip()
        stored_ticket_id = str(stored_payload.get("ticket_id") or "").strip()
        if stored_token and stored_ticket_id == str(ticket.ticket_id):
            return {
                "ticket_id": stored_ticket_id,
                "token": stored_token,
            }

    token = generate_ticket_qr_token(ticket)
    return {
        "ticket_id": str(ticket.ticket_id),
        "token": token,
    }


def persist_ticket_render_artifacts(ticket: Ticket) -> dict[str, Any]:
    """Persist ticket QR payload/image so all clients receive stable artifacts."""
    payload = dict(ticket.payload) if isinstance(ticket.payload, dict) else {}
    changed = False

    qr_payload = build_ticket_qr_payload(ticket)
    if payload.get("qr_payload") != qr_payload:
        payload["qr_payload"] = qr_payload
        changed = True

    if not str(payload.get("ticket_id") or "").strip():
        payload["ticket_id"] = str(ticket.ticket_id)
        changed = True

    qr_code = str(payload.get("qr_code") or "").strip()
    if not qr_code:
        qr_image = _build_qr_image(json.dumps(qr_payload, separators=(",", ":")))
        if qr_image is not None:
            payload["qr_code"] = _image_to_data_url(qr_image)
            changed = True

    if changed:
        ticket.payload = payload
        ticket.save(update_fields=["payload"])

    return payload


def build_ticket_qr_data(ticket: Ticket) -> str:
    """Return compact JSON payload string to embed into the QR image."""
    return json.dumps(build_ticket_qr_payload(ticket), separators=(",", ":"))


def verify_ticket_qr_token(
    ticket: Ticket,
    token: Any,
    *,
    now: Optional[datetime] = None,
) -> tuple[bool, Optional[str]]:
    """Verify signed token integrity, ticket match, and token expiry."""
    raw_token = str(token or "").strip()
    if not raw_token:
        return False, "missing"

    _ensure_ticket_security_defaults(ticket, save=False)

    try:
        decoded = signing.loads(raw_token, salt=TICKET_QR_SIGNING_SALT)
    except signing.BadSignature:
        return False, "invalid"

    if not isinstance(decoded, dict):
        return False, "invalid"

    token_ticket_id = str(decoded.get("ticket_id") or decoded.get("tid") or "").strip()
    token_reference = str(decoded.get("reference") or "").strip()
    if token_ticket_id != str(ticket.ticket_id):
        if not token_reference or token_reference.lower() != str(ticket.reference or "").strip().lower():
            return False, "invalid"

    exp_value = decoded.get("exp")
    try:
        exp_epoch = int(exp_value)
    except (TypeError, ValueError):
        return False, "invalid"

    current = _ensure_timezone_aware(now or timezone.now()) or timezone.now()
    if int(current.timestamp()) > exp_epoch:
        return False, "expired"

    stored_expiry = _ensure_timezone_aware(ticket.token_expires_at)
    if stored_expiry and current > stored_expiry:
        return False, "expired"

    return True, None


def _build_ticket_payload(order: dict[str, Any], reference: str, request: Any) -> dict[str, Any]:
    """Build the ticket payload that is persisted in the database."""
    if not isinstance(order, dict):
        order = {}
    movie = order.get("movie") if isinstance(order.get("movie"), dict) else {}
    booking_context = _resolve_booking_context(order)
    selected_seats = booking_context.get("selected_seats") or []
    booking_data = order.get("booking") if isinstance(order.get("booking"), dict) else {}
    user_id = (
        booking_context.get("user_id")
        or _coerce_int(coalesce(booking_data, "user_id", "userId"))
    )
    user_payload = None
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            full_name = " ".join(
                [part for part in [user.first_name, user.middle_name, user.last_name] if part]
            ).strip()
            user_payload = {
                "id": user.id,
                "name": full_name or user.email or str(user.id),
                "email": user.email,
                "phone": user.phone_number,
            }

    venue_raw = movie.get("venue") or ""
    venue_parts = [part.strip() for part in str(venue_raw).split(",") if part.strip()]
    venue_name = venue_parts[0] if venue_parts else str(venue_raw)
    venue_location = str(movie.get("cinemaLocation") or movie.get("location") or "").strip()
    explicit_cinema_name = str(movie.get("cinemaName") or "").strip()
    if explicit_cinema_name:
        venue_name = explicit_cinema_name
    show_date = venue_parts[1] if len(venue_parts) > 1 else ""
    show_time = venue_parts[2] if len(venue_parts) > 2 else ""
    if movie.get("showDate"):
        show_date = str(movie.get("showDate"))
    if movie.get("showTime"):
        show_time = str(movie.get("showTime"))
    if booking_context.get("show_date"):
        show_date = booking_context["show_date"].isoformat()
    if booking_context.get("show_time"):
        show_time = booking_context["show_time"].strftime("%I:%M %p")

    seat_label = str(movie.get("seat") or "").strip()
    if selected_seats:
        seat_label = f"Seat No: {', '.join(selected_seats)}"

    theater = (
        booking_context.get("hall")
        or movie.get("theater")
        or movie.get("screen")
        or movie.get("hall")
    )
    if not theater:
        match = re.search(r"\b(\d{1,2})\b", venue_name)
        theater = match.group(1).zfill(2) if match else "03"

    ticket_total = _safe_number(order.get("ticketTotal"))
    food_total = _safe_number(order.get("foodTotal"))
    total = _safe_number(order.get("total") or (ticket_total + food_total))
    payload = {
        "reference": reference,
        "movie": {
            "title": str(movie.get("title") or ""),
            "seat": seat_label,
            "venue": str(venue_raw),
            "venue_name": str(venue_name),
            "venue_location": venue_location,
            "show_date": str(show_date),
            "show_time": str(show_time),
            "theater": str(theater),
            "language": str(movie.get("language") or ""),
            "runtime": str(movie.get("runtime") or ""),
            "movie_id": booking_context.get("movie_id"),
            "cinema_id": booking_context.get("cinema_id"),
            "show_id": booking_context.get("show_id"),
        },
        "selected_seats": selected_seats,
        "ticket_total": ticket_total,
        "food_total": food_total,
        "total": total,
        "items": _normalize_items(order.get("items")),
        "user": user_payload,
        "created_at": timezone.now().isoformat(),
    }
    payload["details_url"] = request.build_absolute_uri(
        f"/api/ticket/{reference}/details/"
    )
    return payload


def _build_qr_image(data: str) -> Optional[Any]:
    """Build a QR image from the supplied data."""
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _image_to_data_url(image: Any) -> str:
    """Convert a PIL image into a data URL string."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _text_size(draw: Any, text: str, font: Any) -> tuple[int, int]:
    """Return text dimensions for the given font."""
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _draw_perforations(
    draw: Any, rect: tuple[int, int, int, int], bg_color: str, radius: int = 7, step: int = 22
) -> None:
    """Draw perforation holes around a rectangle."""
    left, top, right, bottom = rect
    for x in range(left + radius, right - radius + 1, step):
        draw.ellipse(
            (x - radius, top - radius, x + radius, top + radius), fill=bg_color
        )
        draw.ellipse(
            (x - radius, bottom - radius, x + radius, bottom + radius), fill=bg_color
        )
    for y in range(top + radius, bottom - radius + 1, step):
        draw.ellipse(
            (left - radius, y - radius, left + radius, y + radius), fill=bg_color
        )
        draw.ellipse(
            (right - radius, y - radius, right + radius, y + radius), fill=bg_color
        )


def _draw_barcode(
    draw: Any, box: tuple[int, int, int, int], seed_value: str, color: str = "#1f2933"
) -> None:
    """Draw a fake barcode pattern for styling."""
    rng = random.Random(seed_value)
    x0, y0, x1, y1 = box
    x = x0
    while x < x1:
        bar_width = rng.choice([1, 1, 2, 2, 3])
        gap = rng.choice([1, 1, 2])
        bar_end = min(x + bar_width, x1)
        draw.rectangle((x, y0, bar_end, y1), fill=color)
        x = bar_end + gap


def _render_ticket_image(payload: dict[str, Any], qr_image: Any) -> Any:
    """Render a ticket image for download and QR display."""
    width, height = 1100, 380
    bg_color = "#3f3f44"
    paper_color = "#ffffff"
    border_color = "#d7d7d7"
    text_color = "#1f2937"
    muted_color = "#6b7280"
    accent_color = "#e11d48"

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    margin = 24
    ticket_rect = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(
        ticket_rect, radius=18, fill=paper_color, outline=border_color, width=2
    )
    _draw_perforations(draw, ticket_rect, bg_color, radius=8, step=24)

    ticket_width = ticket_rect[2] - ticket_rect[0]
    separator_x = ticket_rect[0] + int(ticket_width * 0.7)
    dash_y = ticket_rect[1] + 18
    while dash_y < ticket_rect[3] - 18:
        draw.line(
            (separator_x, dash_y, separator_x, dash_y + 10),
            fill=border_color,
            width=2,
        )
        dash_y += 18

    brand_font = _load_font(22, bold=True)
    title_font = _load_font(30, bold=True)
    label_font = _load_font(12, bold=True)
    value_font = _load_font(16, bold=False)
    small_font = _load_font(13, bold=False)

    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    title = str(movie.get("title") or "")
    venue_name = str(movie.get("venue_name") or movie.get("venue") or "")
    seat_raw = str(movie.get("seat") or "")
    seat_value = re.sub(r"(?i)seat\s*no\s*[:#-]?", "", seat_raw).strip() or "-"
    theater = str(movie.get("theater") or "03")
    show_date = str(movie.get("show_date") or "")
    show_time = str(movie.get("show_time") or "")
    reference = str(payload.get("reference") or "")
    ticket_total = payload.get("ticket_total")
    if ticket_total is None:
        ticket_total = payload.get("total")
    food_total = payload.get("food_total")
    total_value = payload.get("total")
    ticket_value = int(_safe_number(ticket_total))
    food_value = int(_safe_number(food_total))
    total_value = int(_safe_number(total_value))

    left_barcode_box = (
        ticket_rect[0] + 12,
        ticket_rect[1] + 18,
        ticket_rect[0] + 48,
        ticket_rect[3] - 18,
    )
    _draw_barcode(draw, left_barcode_box, reference + "left", color=text_color)

    left_x = left_barcode_box[2] + 18
    left_y = ticket_rect[1] + 18

    brand_text = "MERO TICKET"
    brand_w, brand_h = _text_size(draw, brand_text, brand_font)
    brand_rect = (left_x, left_y, left_x + brand_w + 18, left_y + brand_h + 10)
    draw.rounded_rectangle(brand_rect, radius=10, fill=accent_color)
    draw.text((left_x + 9, left_y + 5), brand_text, fill="#ffffff", font=brand_font)

    left_y = brand_rect[3] + 12
    movie_title = _clamp_text(title.upper(), 22)
    draw.text((left_x, left_y), movie_title, fill=accent_color, font=title_font)
    left_y += 36

    def draw_line(label, value, current_y):
        line = f"{label} : {value or '-'}"
        draw.text(
            (left_x, current_y),
            _clamp_text(line, 40),
            fill=text_color,
            font=value_font,
        )
        return current_y + 22

    left_y = draw_line("CINEMA", venue_name, left_y)
    left_y = draw_line("THEATER", theater, left_y)
    left_y = draw_line("SEAT", seat_value, left_y)
    left_y = draw_line("DATE", show_date, left_y)
    left_y = draw_line("TIME", show_time, left_y)
    left_y = draw_line("TICKET", f"NPR {ticket_value}", left_y)
    left_y = draw_line("FOOD", f"NPR {food_value}", left_y)
    left_y = draw_line("TOTAL", f"NPR {total_value}", left_y)

    draw.text(
        (left_x, ticket_rect[3] - 28),
        _clamp_text(f"REF : {reference}", 26),
        fill=muted_color,
        font=small_font,
    )

    right_x = separator_x + 18
    right_y = ticket_rect[1] + 20
    draw.text((right_x, right_y), "ADMIT ONE", fill=text_color, font=label_font)
    right_y += 20
    draw.text((right_x, right_y), "STANDARD 3D", fill=muted_color, font=label_font)
    right_y += 22
    draw.text(
        (right_x, right_y),
        _clamp_text(f"THEATER : {theater}", 22),
        fill=muted_color,
        font=small_font,
    )
    right_y += 18
    draw.text(
        (right_x, right_y),
        _clamp_text(f"SEAT : {seat_value}", 22),
        fill=muted_color,
        font=small_font,
    )
    right_y += 18

    if show_date or show_time:
        show_line = " ".join([value for value in [show_date, show_time] if value]).strip()
        draw.text(
            (right_x, right_y),
            _clamp_text(show_line, 22),
            fill=muted_color,
            font=small_font,
        )
        right_y += 18

    right_limit = ticket_rect[2] - 18
    if qr_image:
        qr_size = min(130, right_limit - right_x)
        if qr_size >= 90:
            qr_resized = qr_image.resize((qr_size, qr_size))
            img.paste(qr_resized, (right_x, right_y))
            right_y += qr_size + 12

    ticket_id_text = str(payload.get("ticket_id") or payload.get("reference") or "-")
    draw.text(
        (right_x, ticket_rect[3] - 56),
        _clamp_text(f"TICKET ID : {ticket_id_text}", 30),
        fill=text_color,
        font=small_font,
    )

    return img


def get_vendor_analytics(vendor: Vendor, request: Any) -> dict[str, Any]:
    """Build comprehensive analytics payload for a vendor dashboard."""
    cache_key = _dashboard_cache_key("vendor-analytics", vendor.id)
    cached_payload = cache.get(cache_key)
    if cached_payload is not None:
        return cached_payload
    try:
        # Get bookings for this vendor through their shows
        vendor_bookings = Booking.objects.filter(
            showtime__screen__vendor=vendor
        ).select_related('user', 'showtime', 'showtime__movie', 'showtime__screen')
        
        # Get all payments related to vendor bookings
        vendor_payments = Payment.objects.filter(
            booking__in=vendor_bookings
        )
        
        # Get vendor shows
        vendor_shows = Show.objects.filter(vendor=vendor)
        
        # Get vendor food items and their bookings
        vendor_food_items = FoodItem.objects.filter(vendor=vendor)
        vendor_food_bookings = BookingFoodItem.objects.filter(
            booking__in=vendor_bookings
        )
        
        # Get booking seats
        vendor_booking_seats = BookingSeat.objects.filter(booking__in=vendor_bookings)
        
        # Calculate key metrics
        fraud_review_threshold = _booking_fraud_review_threshold()
        booking_summary = vendor_bookings.aggregate(
            total_bookings=Count('id'),
            confirmed_bookings=Count('id', filter=Q(booking_status='Confirmed')),
            completed_bookings=Count('id', filter=Q(booking_status='Completed')),
            pending_bookings=Count('id', filter=Q(booking_status='Pending')),
            cancelled_bookings=Count('id', filter=Q(booking_status='Cancelled')),
            high_risk_bookings=Count('id', filter=Q(fraud_score__gte=fraud_review_threshold)),
            critical_risk_bookings=Count('id', filter=Q(fraud_score__gte=90)),
            avg_score=Avg('fraud_score'),
            max_score=Max('fraud_score'),
            avg_value=Avg('total_amount'),
            max_value=Max('total_amount'),
            min_value=Min('total_amount'),
        )
        fraud_level_counts = {
            Booking.FRAUD_LEVEL_LOW: 0,
            Booking.FRAUD_LEVEL_MEDIUM: 0,
            Booking.FRAUD_LEVEL_HIGH: 0,
            Booking.FRAUD_LEVEL_CRITICAL: 0,
        }
        for row in vendor_bookings.values('fraud_level').annotate(total=Count('id')):
            level_key = str(row.get('fraud_level') or Booking.FRAUD_LEVEL_LOW).upper()
            if level_key not in fraud_level_counts:
                level_key = Booking.FRAUD_LEVEL_LOW
            fraud_level_counts[level_key] += int(row.get('total') or 0)

        fraud_score_stats = {
            'avg_score': booking_summary.get('avg_score'),
            'max_score': booking_summary.get('max_score'),
        }
        high_risk_bookings = int(booking_summary.get('high_risk_bookings') or 0)
        critical_risk_bookings = int(booking_summary.get('critical_risk_bookings') or 0)

        successful_payments = vendor_payments.filter(payment_status='Success')
        payment_summary = successful_payments.aggregate(total=Sum('amount'), count=Count('id'))
        total_revenue = float(payment_summary.get('total') or 0)

        total_bookings = int(booking_summary.get('total_bookings') or 0)
        confirmed_bookings = int(booking_summary.get('confirmed_bookings') or 0)
        completed_bookings = int(booking_summary.get('completed_bookings') or 0)
        pending_bookings = int(booking_summary.get('pending_bookings') or 0)
        cancelled_bookings = int(booking_summary.get('cancelled_bookings') or 0)
        total_booking_rows = total_bookings
        cancelled_booking_rows = cancelled_bookings
        refund_booking_rows = vendor_bookings.filter(
            Q(payments__refunds__refund_status__iexact=Refund.Status.COMPLETED)
            | Q(payments__payment_status__iexact=PAYMENT_STATUS_REFUNDED)
            | Q(payments__payment_status__iexact=PAYMENT_STATUS_PARTIALLY_REFUNDED)
        ).distinct().count()
        refund_total_amount = _quantize_money(
            vendor_bookings.filter(payments__refunds__refund_status__iexact=Refund.Status.COMPLETED).aggregate(
                total=Sum('payments__refunds__refund_amount')
            ).get('total') or Decimal('0')
        )
        wallet = _wallet_for_vendor(vendor)
        pending_payout_amount = _pending_withdrawal_total(wallet)
        
        total_seats_booked = vendor_booking_seats.count()
        total_shows = vendor_shows.count()
        
        # Revenue breakdown
        payment_methods = {}
        for payment in successful_payments:
            method = payment.payment_method or 'Unknown'
            if method not in payment_methods:
                payment_methods[method] = {'count': 0, 'total': 0}
            payment_methods[method]['count'] += 1
            payment_methods[method]['total'] += float(payment.amount or 0)
        
        # Booking status breakdown
        booking_status_breakdown = {
            'Pending': pending_bookings,
            'Confirmed': confirmed_bookings,
            'Completed': completed_bookings,
            'Cancelled': cancelled_bookings,
        }
        
        # Top selling food items
        top_food_items = vendor_food_bookings.values(
            'food_item__item_name',
            'food_item__category'
        ).annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-quantity')[:5]
        
        # Convert Decimal to float for JSON serialization
        top_food_list = [
            {
                'name': item['food_item__item_name'],
                'category': item['food_item__category'],
                'quantity': item['quantity'],
                'revenue': float(item['revenue'] or 0)
            }
            for item in top_food_items
        ]
        
        # Get recent bookings
        recent_bookings = vendor_bookings.order_by('-booking_date')[:5]
        recent_bookings_list = [
            {
                'id': booking.id,
                'user': booking.user.first_name + ' ' + booking.user.last_name,
                'status': booking.booking_status,
                'total': float(booking.total_amount or 0),
                'date': booking.booking_date.isoformat(),
                'seats': booking.booking_seats.count(),
                'fraud_score': int(booking.fraud_score or 0),
                'fraud_level': str(booking.fraud_level or Booking.FRAUD_LEVEL_LOW),
                'requires_manual_review': int(booking.fraud_score or 0) >= fraud_review_threshold,
            }
            for booking in recent_bookings
        ]
        
        # Seat utilization
        total_available_seats = Seat.objects.filter(
            screen__vendor=vendor
        ).count()
        seat_utilization_percentage = (
            (total_seats_booked / total_available_seats * 100) 
            if total_available_seats > 0 else 0
        )
        
        # Monthly booking trend (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        monthly_bookings = vendor_bookings.filter(
            booking_date__gte=thirty_days_ago
        ).extra(
            select={'date': 'DATE(booking_date)'}
        ).values('date').annotate(
            count=Count('id'),
            revenue=Sum('payments__amount'),
            avg_fraud_score=Avg('fraud_score'),
            high_risk_count=Count('id', filter=Q(fraud_score__gte=fraud_review_threshold)),
        ).order_by('date')
        
        monthly_trend = [
            {
                'date': str(item['date']),
                'bookings': item['count'],
                'revenue': float(item['revenue'] or 0),
                'avg_fraud_score': round(float(item.get('avg_fraud_score') or 0), 2),
                'high_risk_bookings': int(item.get('high_risk_count') or 0),
            }
            for item in monthly_bookings
        ]

        recent_risky_bookings = vendor_bookings.filter(
            fraud_score__gte=fraud_review_threshold,
        ).order_by('-booking_date', '-id')[:10]
        risky_bookings = [
            {
                'id': booking.id,
                'user': " ".join(
                    part for part in [booking.user.first_name, booking.user.last_name] if part
                ).strip() or booking.user.email,
                'status': booking.booking_status,
                'fraud_score': int(booking.fraud_score or 0),
                'fraud_level': str(booking.fraud_level or Booking.FRAUD_LEVEL_LOW),
                'date': booking.booking_date.isoformat() if booking.booking_date else None,
            }
            for booking in recent_risky_bookings
        ]
        
        # Top shows
        top_shows = vendor_bookings.values(
            'showtime__movie__title'
        ).annotate(
            bookings=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('-bookings')[:5]
        
        top_shows_list = [
            {
                'title': show['showtime__movie__title'],
                'bookings': show['bookings'],
                'revenue': float(show['revenue'] or 0)
            }
            for show in top_shows
        ]
        
        # Food category distribution
        food_by_category = vendor_food_bookings.values(
            'food_item__category'
        ).annotate(
            quantity=Sum('quantity'),
            revenue=Sum('total_price')
        ).order_by('-quantity')
        
        food_category_list = [
            {
                'name': item['food_item__category'] or 'Uncategorized',
                'quantity': item['quantity'],
                'revenue': float(item['revenue'] or 0)
            }
            for item in food_by_category
        ]
        
        # Bookings by day of week
        weekly_distribution = vendor_bookings.annotate(
            day_of_week=ExtractWeekDay('booking_date')
        ).values('day_of_week').annotate(
            count=Count('id')
        ).order_by('day_of_week')
        
        days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        weekly_bookings = []
        for day_num in range(1, 8):
            day_data = next((item for item in weekly_distribution if item['day_of_week'] == day_num), None)
            weekly_bookings.append({
                'day': days[day_num - 1],
                'bookings': day_data['count'] if day_data else 0
            })
        
        # Average booking value trend
        booking_value_stats = vendor_bookings.aggregate(
            avg_value=Avg('total_amount'),
            max_value=Max('total_amount'),
            min_value=Min('total_amount')
        )
        
        # Revenue per show
        revenue_per_show = vendor_bookings.values(
            'showtime__movie__title'
        ).annotate(
            count=Count('id'),
            total_revenue=Sum('total_amount')
        ).order_by('-total_revenue')[:10]
        
        revenue_per_show_list = [
            {
                'show': item.get('showtime__movie__title', 'Unknown'),
                'bookings': item['count'],
                'revenue': float(item['total_revenue'] or 0)
            }
            for item in revenue_per_show
        ]

        occupancy_rows = list(
            vendor_bookings.values(
                "showtime__id",
                "showtime__start_time",
                "showtime__movie__title",
                "showtime__screen__screen_number",
                "showtime__screen_id",
            ).annotate(
                tickets_sold=Count("booking_seats__id"),
            ).order_by("showtime__start_time")
        )
        screen_ids = [row.get("showtime__screen_id") for row in occupancy_rows if row.get("showtime__screen_id")]
        capacity_rows = Seat.objects.filter(screen_id__in=screen_ids).values("screen_id").annotate(total=Count("id"))
        screen_capacity_map = {row["screen_id"]: int(row["total"] or 0) for row in capacity_rows}
        occupancy_by_slot = []
        for row in occupancy_rows:
            screen_id = row.get("showtime__screen_id")
            capacity = int(screen_capacity_map.get(screen_id) or 0)
            sold = int(row.get("tickets_sold") or 0)
            occupancy_percent = (sold / capacity * 100) if capacity > 0 else 0
            start_time = row.get("showtime__start_time")
            occupancy_by_slot.append(
                {
                    "showtime_id": row.get("showtime__id"),
                    "movie_title": row.get("showtime__movie__title") or "Unknown",
                    "slot_label": start_time.strftime("%Y-%m-%d %H:%M") if start_time else "",
                    "hall": row.get("showtime__screen__screen_number") or "-",
                    "capacity": capacity,
                    "tickets_sold": sold,
                    "occupancy_percent": round(occupancy_percent, 2),
                }
            )

        cancellation_rate = (cancelled_booking_rows / total_booking_rows * 100) if total_booking_rows > 0 else 0
        refund_rate = (refund_booking_rows / total_booking_rows * 100) if total_booking_rows > 0 else 0

        dropoff_payload = _build_dropoff_analytics_payload(
            BookingDropoffEvent.objects.filter(vendor_id=vendor.id),
            days=14,
        )
        
        payload = {
            'vendor_id': vendor.id,
            'vendor_name': vendor.name,
            'summary': {
                'total_bookings': total_bookings,
                'confirmed_bookings': confirmed_bookings,
                'completed_bookings': completed_bookings,
                'total_revenue': total_revenue,
                'total_seats_booked': total_seats_booked,
                'total_shows': total_shows,
                'seat_utilization_percentage': round(seat_utilization_percentage, 2),
                'cancellation_rate': round(cancellation_rate, 2),
                'refund_rate': round(refund_rate, 2),
                'payout_pending': float(pending_payout_amount),
                'refund_total_amount': float(refund_total_amount),
                'total_food_items_sold': vendor_food_bookings.aggregate(
                    total=Sum('quantity')
                )['total'] or 0,
                'average_fraud_score': round(float(fraud_score_stats.get('avg_score') or 0), 2),
                'high_risk_bookings': high_risk_bookings,
                'critical_risk_bookings': critical_risk_bookings,
            },
            'fraud_summary': {
                'review_threshold': fraud_review_threshold,
                'average_score': round(float(fraud_score_stats.get('avg_score') or 0), 2),
                'max_score': int(fraud_score_stats.get('max_score') or 0),
                'high_risk_bookings': high_risk_bookings,
                'critical_risk_bookings': critical_risk_bookings,
                'levels': {
                    'low': int(fraud_level_counts[Booking.FRAUD_LEVEL_LOW]),
                    'medium': int(fraud_level_counts[Booking.FRAUD_LEVEL_MEDIUM]),
                    'high': int(fraud_level_counts[Booking.FRAUD_LEVEL_HIGH]),
                    'critical': int(fraud_level_counts[Booking.FRAUD_LEVEL_CRITICAL]),
                },
            },
            'risky_bookings': risky_bookings,
            'payment_methods': payment_methods,
            'booking_status_breakdown': booking_status_breakdown,
            'top_food_items': top_food_list,
            'top_shows': top_shows_list,
            'recent_bookings': recent_bookings_list,
            'monthly_trend': monthly_trend,
            'food_by_category': food_category_list,
            'weekly_bookings': weekly_bookings,
            'booking_value_stats': booking_value_stats,
            'revenue_per_show': revenue_per_show_list,
            'occupancy_by_slot': occupancy_by_slot,
            'dropoff_summary': dropoff_payload['summary'],
            'dropoff_trend': dropoff_payload['trend'],
            'message': 'Analytics data retrieved successfully'
        }
        cache.set(cache_key, payload, ANALYTICS_VENDOR_CACHE_TTL_SECONDS)
        return payload
    except Exception as e:
        logger.error(f"Error building vendor analytics: {str(e)}")
        return {
            'error': str(e),
            'message': 'Failed to retrieve analytics data'
        }


def _render_food_slip_image(payload: dict[str, Any]) -> Any:
    """Render a food slip image for download."""
    width = 820
    bg_color = "#3f3f44"
    paper_color = "#ffffff"
    border_color = "#d7d7d7"
    text_color = "#1f2937"
    muted_color = "#6b7280"
    accent_color = "#f59e0b"

    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    title = str(movie.get("title") or "")
    reference = str(payload.get("reference") or "")
    show_date = str(movie.get("show_date") or "")
    show_time = str(movie.get("show_time") or "")
    food_total = int(_safe_number(payload.get("food_total")))
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    item_lines = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        qty = int(item.get("qty") or 0)
        line = f"{_clamp_text(name, 28)} x{qty}" if qty else _clamp_text(name, 28)
        item_lines.append(line)
    if not item_lines:
        item_lines = ["No food items"]

    line_height = 18
    extra_meta = 20 if show_date or show_time else 0
    height = 230 + extra_meta + len(item_lines) * line_height
    height = max(height, 260)

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    margin = 22
    slip_rect = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(
        slip_rect, radius=16, fill=paper_color, outline=border_color, width=2
    )
    _draw_perforations(draw, slip_rect, bg_color, radius=7, step=22)

    brand_font = _load_font(16, bold=True)
    title_font = _load_font(24, bold=True)
    body_font = _load_font(16, bold=False)
    small_font = _load_font(12, bold=False)
    label_font = _load_font(12, bold=True)

    x = slip_rect[0] + 18
    y = slip_rect[1] + 16
    draw.text((x, y), "MERO TICKET", fill=text_color, font=brand_font)
    y += 22

    slip_text = "FOOD SLIP"
    slip_w, slip_h = _text_size(draw, slip_text, title_font)
    slip_rect_box = (x, y, x + slip_w + 18, y + slip_h + 10)
    draw.rounded_rectangle(slip_rect_box, radius=8, fill=accent_color)
    draw.text((x + 9, y + 5), slip_text, fill="#1f2937", font=title_font)
    y = slip_rect_box[3] + 12

    if title:
        draw.text((x, y), _clamp_text(title, 34), fill=muted_color, font=body_font)
        y += 20

    if show_date or show_time:
        show_line = " ".join([value for value in [show_date, show_time] if value]).strip()
        draw.text((x, y), _clamp_text(show_line, 34), fill=muted_color, font=body_font)
        y += 20

    draw.text((x, y), "ITEMS", fill=muted_color, font=label_font)
    y += 18
    for line in item_lines:
        draw.text((x, y), line, fill=text_color, font=body_font)
        y += line_height

    y += 8
    amount_text = f"BILL AMOUNT : NPR {food_total}"
    draw.text((x, y), amount_text, fill=text_color, font=title_font)

    draw.text(
        (x, slip_rect[3] - 24),
        _clamp_text(f"REF : {reference}", 28),
        fill=muted_color,
        font=small_font,
    )

    return img


def _render_ticket_bundle_image(payload: dict[str, Any], qr_image: Any) -> Any:
    """Render the combined ticket + food slip bundle image."""
    bg_color = "#3f3f44"
    ticket_image = _render_ticket_image(payload, qr_image)
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    has_food_item = any(str(item.get("name") or "").strip() for item in items if isinstance(item, dict))
    has_food_total = _safe_number(payload.get("food_total")) > 0
    if not has_food_item and not has_food_total:
        return ticket_image

    food_image = _render_food_slip_image(payload)
    margin = 24
    spacing = 20
    width = max(ticket_image.width, food_image.width) + margin * 2
    height = ticket_image.height + food_image.height + spacing + margin * 2
    img = Image.new("RGB", (width, height), bg_color)
    ticket_x = (width - ticket_image.width) // 2
    food_x = (width - food_image.width) // 2
    img.paste(ticket_image, (ticket_x, margin))
    img.paste(food_image, (food_x, margin + ticket_image.height + spacing))
    return img


def create_payment_qr(request: Any) -> tuple[dict[str, Any], int]:
    """Create a payment QR preview without persisting a ticket before payment verification."""
    payload = get_payload(request)
    order = payload.get("order", {}) if isinstance(payload, dict) else {}
    if not order:
        return {"message": "Order data is required"}, status.HTTP_400_BAD_REQUEST

    reference = uuid.uuid4().hex[:10].upper()
    ticket_payload = _build_ticket_payload(order, reference, request)
    payment_total = _safe_number(order.get("total") or order.get("ticketTotal") or order.get("ticket_total"))
    initiated_at = timezone.now().isoformat()
    ticket_payload["payment"] = {
        "provider": "QR",
        "status": "PENDING",
        "total_amount": payment_total,
        "initiated_at": initiated_at,
        "verified_at": None,
    }

    qr_payload = {
        "reference": reference,
        "status": "PENDING",
        "amount": payment_total,
        "initiated_at": initiated_at,
    }
    qr_image = _build_qr_image(json.dumps(qr_payload, separators=(",", ":")))
    if not qr_image:
        return {
            "message": "QR code library not installed. Please install qrcode."
        }, status.HTTP_500_INTERNAL_SERVER_ERROR

    render_payload = dict(ticket_payload)
    render_payload["ticket_id"] = "PENDING"
    ticket_image = _render_ticket_bundle_image(render_payload, qr_image)
    return {
        "message": "Payment initiated. Ticket will be generated after payment verification.",
        "reference": reference,
        "ticket_id": None,
        "token": None,
        "booking": None,
        "payment_status": "PENDING",
        "qr_code": _image_to_data_url(qr_image),
        "ticket_image": _image_to_data_url(ticket_image),
        "download_url": None,
        "details_url": None,
        "qr_payload": qr_payload,
    }, status.HTTP_200_OK


def build_ticket_download(reference: str) -> Optional[bytes]:
    """Return a rendered ticket PNG for download."""
    ticket = get_ticket(reference)
    if not ticket:
        return None

    payload = persist_ticket_render_artifacts(ticket)
    qr_image = None
    qr_payload = payload.get("qr_payload") if isinstance(payload.get("qr_payload"), dict) else None
    if qr_payload:
        qr_image = _build_qr_image(json.dumps(qr_payload, separators=(",", ":")))
    if qr_image is None:
        qr_image = _build_qr_image(build_ticket_qr_data(ticket))
    render_payload = dict(payload)
    render_payload["ticket_id"] = str(ticket.ticket_id)
    ticket_image = _render_ticket_image(render_payload, qr_image)
    buffer = io.BytesIO()
    ticket_image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.read()


def build_ticket_pdf(reference: str) -> Optional[bytes]:
    """Return a rendered ticket PDF for download or email attachment."""
    ticket = get_ticket(reference)
    if not ticket:
        return None

    payload = persist_ticket_render_artifacts(ticket)
    qr_image = None
    qr_payload = payload.get("qr_payload") if isinstance(payload.get("qr_payload"), dict) else None
    if qr_payload:
        qr_image = _build_qr_image(json.dumps(qr_payload, separators=(",", ":")))
    if qr_image is None:
        qr_image = _build_qr_image(build_ticket_qr_data(ticket))
    render_payload = dict(payload)
    render_payload["ticket_id"] = str(ticket.ticket_id)
    ticket_image = _render_ticket_bundle_image(render_payload, qr_image)
    if ticket_image.mode != "RGB":
        ticket_image = ticket_image.convert("RGB")

    buffer = io.BytesIO()
    ticket_image.save(buffer, format="PDF")
    buffer.seek(0)
    return buffer.read()


def send_ticket_confirmation_email(ticket: Ticket) -> bool:
    """Email a booking confirmation with the ticket PDF attached."""
    if not ticket:
        return False

    payload = ticket.payload or {}
    user_payload = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    recipient_email = str(
        (ticket.user.email if ticket.user else None)
        or user_payload.get("email")
        or ""
    ).strip()
    if not recipient_email:
        return False

    reference = str(ticket.reference or "").strip()
    pdf_bytes = build_ticket_pdf(reference)
    if not pdf_bytes:
        logger.warning("Ticket PDF could not be generated for reference %s", reference)
        return False

    movie = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}
    movie_title = str(movie.get("title") or "your booking").strip() or "your booking"
    subject = f"Mero Ticket booking confirmed - {reference}"
    message = (
        f"Your booking for {movie_title} has been confirmed. "
        f"Your ticket PDF is attached.")
    if payload.get("details_url"):
        message += f"\n\nTicket details: {payload.get('details_url')}"

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@meroticket.local"
    email_message = EmailMessage(
        subject=subject,
        body=message,
        from_email=from_email,
        to=[recipient_email],
    )
    filename = f"ticket-{reference or str(ticket.ticket_id)}.pdf"
    email_message.attach(filename, pdf_bytes, "application/pdf")

    try:
        email_message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send ticket confirmation email to %s", recipient_email)
        return False


def build_ticket_details_html(reference: str) -> Optional[str]:
    """Return an HTML receipt for a ticket reference."""
    ticket = get_ticket(reference)
    if not ticket:
        return None

    payload = ticket.payload or {}
    ticket_id_text = str(ticket.ticket_id or reference)
    movie = payload.get("movie", {}) if isinstance(payload.get("movie"), dict) else {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    user = payload.get("user", {}) if isinstance(payload.get("user"), dict) else {}
    venue_name = movie.get("venue_name") or movie.get("venue") or ""
    venue_location = movie.get("venue_location") or ""
    show_date = movie.get("show_date") or ""
    show_time = movie.get("show_time") or ""
    theater = movie.get("theater") or ""
    ticket_total = int(_safe_number(payload.get("ticket_total")))
    food_total = int(_safe_number(payload.get("food_total")))
    grand_total = int(_safe_number(payload.get("total")))

    items_html = ""
    if items:
        rows = []
        for item in items:
            name = escape(str(item.get("name", "")))
            qty_value = int(item.get("qty") or 0)
            unit_price = int(_safe_number(item.get("price")))
            line_total = unit_price * qty_value
            qty_label = f"{qty_value}" if qty_value else "-"
            rows.append(
                f"""
                <div class=\"item-row\">
                  <div>
                    <div class=\"item-name\">{name or '-'}</div>
                    <div class=\"item-meta\">Qty {escape(qty_label)} | NPR {escape(str(unit_price))}</div>
                  </div>
                  <div class=\"item-total\">NPR {escape(str(line_total))}</div>
                </div>
                """
            )
        items_html = "<div class=\"items\">" + "".join(rows) + "</div>"

    location_html = ""
    if venue_location:
        location_html = f"""
            <div class="row">
              <div class="label">Location</div>
              <div class="value">{escape(str(venue_location))}</div>
            </div>
        """

    user_html = ""
    if user:
        name_value = escape(str(user.get("name") or ""))
        email_value = escape(str(user.get("email") or ""))
        phone_value = escape(str(user.get("phone") or ""))
        rows = []
        if name_value:
            rows.append(
                f"""
                <div class="row">
                  <div class="label">Customer</div>
                  <div class="value">{name_value}</div>
                </div>
                """
            )
        if email_value:
            rows.append(
                f"""
                <div class="row">
                  <div class="label">Email</div>
                  <div class="value">{email_value}</div>
                </div>
                """
            )
        if phone_value:
            rows.append(
                f"""
                <div class="row">
                  <div class="label">Phone</div>
                  <div class="value">{phone_value}</div>
                </div>
                """
            )
        if rows:
            user_html = (
                '<div class="section"><div class="section-title">Customer</div>'
                + "".join(rows)
                + "</div>"
            )

    html = f"""
    <html>
      <head>
        <title>Ticket {escape(reference)}</title>
        <style>
          :root {{
            --paper: #fff9f2;
            --ink: #1f2937;
            --muted: #6b7280;
            --accent: #111827;
            --line: #e5e7eb;
          }}
          body {{
            font-family: Arial, sans-serif;
            background: #0f1116;
            color: var(--ink);
            padding: 24px;
          }}
          .receipt {{
            background: var(--paper);
            border-radius: 18px;
            padding: 22px 20px;
            width: min(420px, 100%);
            margin: 0 auto;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
            border: 1px solid #e7e0d6;
          }}
          .receipt-header {{
            text-align: center;
            padding-bottom: 12px;
            border-bottom: 1px dashed #d6d3d1;
            margin-bottom: 14px;
          }}
          .brand {{
            font-size: 13px;
            letter-spacing: 0.28em;
            text-transform: uppercase;
            font-weight: 800;
            color: var(--accent);
          }}
          .title {{
            font-size: 18px;
            font-weight: 800;
            margin: 8px 0 4px;
          }}
          .meta {{
            color: var(--muted);
            font-size: 12px;
          }}
          .section {{
            padding: 10px 0;
            border-bottom: 1px dashed #d6d3d1;
          }}
          .section:last-child {{
            border-bottom: none;
          }}
          .section-title {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            color: var(--muted);
            margin-bottom: 8px;
          }}
          .row {{
            display: grid;
            gap: 4px;
            padding: 6px 0;
          }}
          .label {{
            color: var(--muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.1em;
          }}
          .value {{
            font-size: 15px;
            font-weight: 700;
          }}
          .items {{
            display: grid;
            gap: 10px;
            font-weight: 400;
          }}
          .item-row {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            padding: 8px 0;
            border-top: 1px dotted var(--line);
          }}
          .item-row:first-child {{
            border-top: none;
            padding-top: 0;
          }}
          .item-name {{
            font-weight: 700;
            font-size: 14px;
          }}
          .item-meta {{
            font-size: 12px;
            color: var(--muted);
            margin-top: 2px;
            font-weight: 400;
          }}
          .item-total {{
            font-weight: 800;
            font-size: 14px;
            white-space: nowrap;
          }}
          .total-row {{
            display: flex;
            justify-content: space-between;
            gap: 10px;
            font-size: 14px;
            padding: 6px 0;
          }}
          .total-row strong {{
            font-size: 16px;
          }}
        </style>
      </head>
      <body>
        <div class="receipt">
          <div class="receipt-header">
            <div class="brand">Mero Ticket</div>
            <div class="title">Ticket & Food Bill</div>
                        <div class="meta">Ticket ID: {escape(ticket_id_text)}</div>
          </div>

          <div class="section">
            <div class="section-title">Ticket Details</div>
                        <div class="row">
                            <div class="label">Ticket ID</div>
                            <div class="value">{escape(ticket_id_text)}</div>
                        </div>
            <div class="row">
              <div class="label">Movie</div>
              <div class="value">{escape(movie.get("title", ""))}</div>
            </div>
            <div class="row">
              <div class="label">Cinema Hall</div>
              <div class="value">{escape(str(venue_name))}</div>
            </div>
            {location_html}
            <div class="row">
              <div class="label">Theater</div>
              <div class="value">{escape(str(theater))}</div>
            </div>
            <div class="row">
              <div class="label">Seat</div>
              <div class="value">{escape(movie.get("seat", ""))}</div>
            </div>
            <div class="row">
              <div class="label">Date</div>
              <div class="value">{escape(str(show_date))}</div>
            </div>
            <div class="row">
              <div class="label">Time</div>
              <div class="value">{escape(str(show_time))}</div>
            </div>
          </div>

          {user_html}

          <div class="section">
            <div class="section-title">Food Items</div>
            <div class="row">
              <div class="label">Food Items</div>
              <div class="value">{items_html or "No food items"}</div>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Totals</div>
            <div class="row">
              <div class="label">Ticket Total</div>
              <div class="value">NPR {escape(str(ticket_total))}</div>
            </div>
            <div class="row">
              <div class="label">Food Total</div>
              <div class="value">NPR {escape(str(food_total))}</div>
            </div>
            <div class="row">
              <div class="label">Grand Total</div>
              <div class="value">NPR {escape(str(grand_total))}</div>
            </div>
          </div>
        </div>
      </body>
    </html>
    """
    return html
