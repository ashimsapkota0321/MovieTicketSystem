"""Service helpers for subscription and membership lifecycle."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Optional

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from .models import (
    Booking,
    Notification,
    SubscriptionPlan,
    SubscriptionTransaction,
    UserSubscription,
)
from .permissions import resolve_customer
from .permissions import ADMIN_REQUIRED_MESSAGE, is_admin_request
from .subscription_serializers import (
    SubscriptionCancelSerializer,
    SubscriptionCheckoutPreviewSerializer,
    SubscriptionPlanWriteSerializer,
    SubscriptionSubscribeSerializer,
    SubscriptionUpgradeSerializer,
)
from .utils import coalesce, get_payload, parse_bool

MONEY_QUANTIZER = Decimal("0.01")
SUBSCRIPTION_ACTIVE_CACHE_PREFIX = "mt:subscription:active:"
SUBSCRIPTION_ACTIVE_CACHE_TTL_SECONDS = 60 * 3
DEFAULT_EXPIRY_NOTIFY_HOURS = 48


def _quantize_money(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(MONEY_QUANTIZER)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _parse_money(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    return _quantize_money(value)


def _coerce_int(value: Any, *, default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _active_cache_key(user_id: int, vendor_id: Optional[int] = None) -> str:
    vendor_token = str(int(vendor_id)) if vendor_id else "any"
    return f"{SUBSCRIPTION_ACTIVE_CACHE_PREFIX}{int(user_id)}:{vendor_token}"


def _clear_user_active_subscription_cache(user_id: int) -> None:
    cache.delete(_active_cache_key(user_id, None))
    vendor_ids = (
        UserSubscription.objects.filter(user_id=user_id)
        .values_list("vendor_id", flat=True)
        .distinct()
    )
    for vendor_id in vendor_ids:
        cache.delete(_active_cache_key(user_id, vendor_id))


def _plan_is_live(plan: SubscriptionPlan, *, now: Optional[Any] = None) -> bool:
    current = now or timezone.now()
    if plan.valid_from and plan.valid_from > current:
        return False
    if plan.valid_until and plan.valid_until < current:
        return False
    return True


def _serialize_plan(plan: SubscriptionPlan, *, now: Optional[Any] = None) -> dict[str, Any]:
    current = now or timezone.now()
    return {
        "id": plan.id,
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "tier": plan.tier,
        "vendor_id": plan.vendor_id,
        "vendor_name": getattr(plan.vendor, "name", None),
        "scope": "VENDOR" if plan.vendor_id else "GLOBAL",
        "duration_days": int(plan.duration_days or 0),
        "price": float(_quantize_money(plan.price)),
        "currency": plan.currency,
        "discount_type": plan.discount_type,
        "discount_value": float(_quantize_money(plan.discount_value)),
        "max_discount_amount": (
            float(_quantize_money(plan.max_discount_amount))
            if plan.max_discount_amount is not None
            else None
        ),
        "free_tickets_total": int(plan.free_tickets_total or 0),
        "early_access_hours": int(plan.early_access_hours or 0),
        "special_pricing_percent": (
            float(_quantize_money(plan.special_pricing_percent))
            if plan.special_pricing_percent is not None
            else None
        ),
        "subscription_only_access": bool(plan.subscription_only_access),
        "allow_multiple_active": bool(plan.allow_multiple_active),
        "is_stackable_with_coupon": bool(plan.is_stackable_with_coupon),
        "is_stackable_with_loyalty": bool(plan.is_stackable_with_loyalty),
        "is_stackable_with_referral_wallet": bool(plan.is_stackable_with_referral_wallet),
        "is_public": bool(plan.is_public),
        "is_active": bool(plan.is_active),
        "priority": int(plan.priority or 0),
        "valid_from": plan.valid_from.isoformat() if plan.valid_from else None,
        "valid_until": plan.valid_until.isoformat() if plan.valid_until else None,
        "is_live": _plan_is_live(plan, now=current),
        "metadata": plan.metadata if isinstance(plan.metadata, dict) else {},
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def _serialize_user_subscription(item: UserSubscription, *, now: Optional[Any] = None) -> dict[str, Any]:
    current = now or timezone.now()
    remaining_seconds = 0
    if item.end_at:
        remaining_seconds = max(int((item.end_at - current).total_seconds()), 0)
    days_remaining = remaining_seconds // (60 * 60 * 24)

    return {
        "id": item.id,
        "user_id": item.user_id,
        "plan_id": item.plan_id,
        "plan_name": getattr(item.plan, "name", None),
        "tier": getattr(item.plan, "tier", None),
        "vendor_id": item.vendor_id,
        "vendor_name": getattr(item.vendor, "name", None),
        "status": item.status,
        "start_at": item.start_at.isoformat() if item.start_at else None,
        "end_at": item.end_at.isoformat() if item.end_at else None,
        "cancel_at_period_end": bool(item.cancel_at_period_end),
        "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
        "remaining_free_tickets": int(item.remaining_free_tickets or 0),
        "used_free_tickets": int(item.used_free_tickets or 0),
        "total_discount_used": float(_quantize_money(item.total_discount_used)),
        "days_remaining": int(days_remaining),
        "is_active": bool(
            item.status == UserSubscription.STATUS_ACTIVE
            and item.end_at
            and item.end_at > current
        ),
        "metadata": item.metadata if isinstance(item.metadata, dict) else {},
        "plan": _serialize_plan(item.plan, now=current) if item.plan else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_transaction(row: SubscriptionTransaction) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "subscription_id": row.subscription_id,
        "plan_id": row.plan_id,
        "booking_id": row.booking_id,
        "transaction_type": row.transaction_type,
        "status": row.status,
        "amount": float(_quantize_money(row.amount)),
        "discount_amount": float(_quantize_money(row.discount_amount)),
        "free_tickets_used": int(row.free_tickets_used or 0),
        "currency": row.currency,
        "reference_id": row.reference_id,
        "metadata": row.metadata if isinstance(row.metadata, dict) else {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _active_subscriptions_for_user(
    *,
    user_id: int,
    vendor_id: Optional[int] = None,
    lock_for_update: bool = False,
    now: Optional[Any] = None,
):
    current = now or timezone.now()
    queryset = UserSubscription.objects.select_related("plan", "vendor").filter(
        user_id=user_id,
        status=UserSubscription.STATUS_ACTIVE,
        end_at__gt=current,
    )
    if vendor_id:
        queryset = queryset.filter(Q(vendor_id=vendor_id) | Q(vendor_id__isnull=True))
    if lock_for_update:
        queryset = queryset.select_for_update()
    return queryset


def _pick_best_subscription(
    subscriptions: list[UserSubscription],
    *,
    vendor_id: Optional[int] = None,
) -> Optional[UserSubscription]:
    if not subscriptions:
        return None

    def _sort_key(item: UserSubscription):
        vendor_rank = 0 if vendor_id and item.vendor_id == vendor_id else 1
        end_rank = -(int(item.end_at.timestamp()) if item.end_at else 0)
        return (vendor_rank, end_rank, -int(item.id or 0))

    ordered = sorted(subscriptions, key=_sort_key)
    return ordered[0] if ordered else None


def get_active_subscription_for_user(
    user_id: int,
    *,
    vendor_id: Optional[int] = None,
    use_cache: bool = True,
    lock_for_update: bool = False,
) -> Optional[UserSubscription]:
    if not user_id:
        return None

    current = timezone.now()
    cache_key = _active_cache_key(user_id, vendor_id)

    if use_cache and not lock_for_update:
        cached_subscription_id = _coerce_int(cache.get(cache_key))
        if cached_subscription_id:
            cached = (
                UserSubscription.objects.select_related("plan", "vendor")
                .filter(
                    id=cached_subscription_id,
                    user_id=user_id,
                    status=UserSubscription.STATUS_ACTIVE,
                    end_at__gt=current,
                )
                .first()
            )
            if cached and (not vendor_id or cached.vendor_id in {None, vendor_id}):
                return cached

    rows = list(
        _active_subscriptions_for_user(
            user_id=user_id,
            vendor_id=vendor_id,
            lock_for_update=lock_for_update,
            now=current,
        )
    )
    selected = _pick_best_subscription(rows, vendor_id=vendor_id)
    if use_cache and not lock_for_update:
        cache.set(cache_key, int(selected.id) if selected else 0, SUBSCRIPTION_ACTIVE_CACHE_TTL_SECONDS)
    return selected


def expire_subscriptions(*, user_id: Optional[int] = None, now: Optional[Any] = None) -> dict[str, Any]:
    current = now or timezone.now()
    queryset = UserSubscription.objects.filter(
        status=UserSubscription.STATUS_ACTIVE,
        end_at__lte=current,
    )
    if user_id:
        queryset = queryset.filter(user_id=user_id)

    expired_count = 0
    for subscription_id in queryset.values_list("id", flat=True):
        with transaction.atomic():
            row = (
                UserSubscription.objects.select_for_update()
                .select_related("user", "plan", "vendor")
                .filter(id=subscription_id)
                .first()
            )
            if not row:
                continue
            if row.status != UserSubscription.STATUS_ACTIVE:
                continue
            if not row.end_at or row.end_at > current:
                continue

            row.status = UserSubscription.STATUS_EXPIRED
            row.cancel_at_period_end = False
            row.save(update_fields=["status", "cancel_at_period_end", "updated_at"])

            SubscriptionTransaction.objects.create(
                user_id=row.user_id,
                subscription=row,
                plan=row.plan,
                transaction_type=SubscriptionTransaction.TYPE_EXPIRE,
                status=SubscriptionTransaction.STATUS_SUCCESS,
                amount=Decimal("0.00"),
                metadata={
                    "expired_at": current.isoformat(),
                },
            )

            Notification.objects.create(
                recipient_role=Notification.ROLE_CUSTOMER,
                recipient_id=row.user_id,
                recipient_email=getattr(row.user, "email", None),
                event_type=Notification.EVENT_SUBSCRIPTION_EXPIRED,
                channel=Notification.CHANNEL_IN_APP,
                title="Subscription expired",
                message=f"Your subscription {row.plan.name if row.plan else row.id} has expired.",
                metadata={
                    "subscription_id": row.id,
                    "plan_id": row.plan_id,
                    "vendor_id": row.vendor_id,
                    "expired_at": current.isoformat(),
                },
            )

            _clear_user_active_subscription_cache(row.user_id)
            expired_count += 1

    return {
        "expired_subscriptions": expired_count,
    }


def notify_expiring_subscriptions(
    *,
    notify_hours: int = DEFAULT_EXPIRY_NOTIFY_HOURS,
    user_id: Optional[int] = None,
    now: Optional[Any] = None,
) -> dict[str, Any]:
    current = now or timezone.now()
    horizon = current + timedelta(hours=max(int(notify_hours or 1), 1))

    queryset = UserSubscription.objects.select_related("user", "plan").filter(
        status=UserSubscription.STATUS_ACTIVE,
        end_at__gt=current,
        end_at__lte=horizon,
    )
    if user_id:
        queryset = queryset.filter(user_id=user_id)

    notified = 0
    for row in queryset:
        exists = Notification.objects.filter(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=row.user_id,
            event_type=Notification.EVENT_SUBSCRIPTION_EXPIRING,
            metadata__subscription_id=row.id,
            metadata__notify_hours=max(int(notify_hours or 1), 1),
        ).exists()
        if exists:
            continue

        Notification.objects.create(
            recipient_role=Notification.ROLE_CUSTOMER,
            recipient_id=row.user_id,
            recipient_email=getattr(row.user, "email", None),
            event_type=Notification.EVENT_SUBSCRIPTION_EXPIRING,
            channel=Notification.CHANNEL_IN_APP,
            title="Subscription expiring soon",
            message=(
                f"Your subscription {row.plan.name if row.plan else row.id} "
                f"will expire on {row.end_at.strftime('%Y-%m-%d %H:%M')}"
            ),
            metadata={
                "subscription_id": row.id,
                "plan_id": row.plan_id,
                "end_at": row.end_at.isoformat() if row.end_at else None,
                "notify_hours": max(int(notify_hours or 1), 1),
            },
        )
        notified += 1

    return {
        "expiring_notifications": notified,
        "notify_hours": max(int(notify_hours or 1), 1),
    }


def _plan_queryset_for_customer(*, vendor_id: Optional[int], tier: str) -> Any:
    queryset = SubscriptionPlan.objects.select_related("vendor").filter(
        is_active=True,
        is_public=True,
    )
    if vendor_id:
        queryset = queryset.filter(Q(vendor_id=vendor_id) | Q(vendor_id__isnull=True))
    if tier:
        queryset = queryset.filter(tier=tier)

    now = timezone.now()
    queryset = queryset.filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now),
        Q(valid_until__isnull=True) | Q(valid_until__gte=now),
    )
    return queryset.order_by("priority", "price", "id")


def list_plans_for_customer(request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    vendor_id = _coerce_int(coalesce(request.query_params, "vendor_id", "vendorId"))
    tier = str(coalesce(request.query_params, "tier", default="") or "").strip().upper()
    if tier and tier not in {item[0] for item in SubscriptionPlan.TIER_CHOICES}:
        return {"message": "tier is invalid."}, status.HTTP_400_BAD_REQUEST

    if user:
        expire_subscriptions(user_id=user.id)

    plans = list(_plan_queryset_for_customer(vendor_id=vendor_id, tier=tier))
    active_subscription = (
        get_active_subscription_for_user(
            user.id,
            vendor_id=vendor_id,
            use_cache=True,
        )
        if user
        else None
    )

    return {
        "plans": [_serialize_plan(item) for item in plans],
        "active_subscription": (
            _serialize_user_subscription(active_subscription)
            if active_subscription
            else None
        ),
    }, status.HTTP_200_OK


def get_plan_detail_for_customer(plan_id: int, request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    vendor_id = _coerce_int(coalesce(request.query_params, "vendor_id", "vendorId"))

    plan = SubscriptionPlan.objects.select_related("vendor").filter(id=plan_id).first()
    if not plan:
        return {"message": "Plan not found."}, status.HTTP_404_NOT_FOUND
    if not plan.is_public or not plan.is_active or not _plan_is_live(plan):
        return {"message": "Plan is not available."}, status.HTTP_400_BAD_REQUEST
    if vendor_id and plan.vendor_id and plan.vendor_id != vendor_id:
        return {"message": "Plan is not available for this vendor."}, status.HTTP_400_BAD_REQUEST

    if user:
        expire_subscriptions(user_id=user.id)

    active_subscription = (
        get_active_subscription_for_user(user.id, vendor_id=vendor_id, use_cache=True)
        if user
        else None
    )

    return {
        "plan": _serialize_plan(plan),
        "active_subscription": (
            _serialize_user_subscription(active_subscription)
            if active_subscription
            else None
        ),
    }, status.HTTP_200_OK


def list_vendor_plans(request: Any) -> tuple[dict[str, Any], int]:
    return {
        "message": "Vendor subscription plan control is disabled. Use vendor offers endpoints instead.",
    }, status.HTTP_403_FORBIDDEN


def create_vendor_plan(request: Any) -> tuple[dict[str, Any], int]:
    return {
        "message": "Vendor subscription plan control is disabled. Use vendor offers endpoints instead.",
    }, status.HTTP_403_FORBIDDEN


def update_vendor_plan(request: Any, plan: SubscriptionPlan) -> tuple[dict[str, Any], int]:
    return {
        "message": "Vendor subscription plan control is disabled. Use vendor offers endpoints instead.",
    }, status.HTTP_403_FORBIDDEN


def delete_vendor_plan(plan: SubscriptionPlan) -> tuple[dict[str, Any], int]:
    return {
        "message": "Vendor subscription plan control is disabled. Use vendor offers endpoints instead.",
    }, status.HTTP_403_FORBIDDEN


def list_admin_plans(request: Any) -> tuple[dict[str, Any], int]:
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    queryset = SubscriptionPlan.objects.select_related("vendor").filter(vendor__isnull=True)
    include_inactive = parse_bool(
        coalesce(request.query_params, "include_inactive", "includeInactive"),
        default=False,
    )
    if not include_inactive:
        queryset = queryset.filter(is_active=True)

    plans = queryset.order_by("priority", "price", "id")
    return {
        "plans": [_serialize_plan(item) for item in plans],
        "count": len(plans),
    }, status.HTTP_200_OK


def create_admin_plan(request: Any) -> tuple[dict[str, Any], int]:
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    serializer = SubscriptionPlanWriteSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid plan payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    data = dict(serializer.validated_data)
    data["vendor"] = None

    try:
        plan = SubscriptionPlan.objects.create(**data)
    except ValidationError as exc:
        return {
            "message": "Invalid plan payload.",
            "errors": exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)},
        }, status.HTTP_400_BAD_REQUEST

    return {
        "message": "Subscription plan created.",
        "plan": _serialize_plan(plan),
    }, status.HTTP_201_CREATED


def update_admin_plan(request: Any, plan: SubscriptionPlan) -> tuple[dict[str, Any], int]:
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    payload = get_payload(request)
    serializer = SubscriptionPlanWriteSerializer(data=payload, partial=True)
    if not serializer.is_valid():
        return {
            "message": "Invalid plan payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    for key, value in serializer.validated_data.items():
        setattr(plan, key, value)
    plan.vendor = None

    try:
        plan.save()
    except ValidationError as exc:
        return {
            "message": "Unable to update plan.",
            "errors": exc.message_dict if hasattr(exc, "message_dict") else {"detail": str(exc)},
        }, status.HTTP_400_BAD_REQUEST

    return {
        "message": "Subscription plan updated.",
        "plan": _serialize_plan(plan),
    }, status.HTTP_200_OK


def delete_admin_plan(request: Any, plan: SubscriptionPlan) -> tuple[dict[str, Any], int]:
    if not is_admin_request(request):
        return {"message": ADMIN_REQUIRED_MESSAGE}, status.HTTP_403_FORBIDDEN

    hard_delete = parse_bool(
        coalesce(get_payload(request), "hard_delete", "hardDelete"),
        default=False,
    )
    if hard_delete:
        plan.delete()
        return {"message": "Subscription plan deleted."}, status.HTTP_200_OK

    plan.is_active = False
    plan.is_public = False
    plan.save(update_fields=["is_active", "is_public", "updated_at"])
    return {"message": "Subscription plan disabled."}, status.HTTP_200_OK


def get_customer_dashboard(request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    if not user:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    vendor_id = _coerce_int(coalesce(request.query_params, "vendor_id", "vendorId"))
    expire_subscriptions(user_id=user.id)

    active_subscription = get_active_subscription_for_user(
        user.id,
        vendor_id=vendor_id,
        use_cache=False,
    )

    subscriptions = (
        UserSubscription.objects.select_related("plan", "vendor")
        .filter(user_id=user.id)
        .order_by("-created_at", "-id")[:25]
    )
    transactions = (
        SubscriptionTransaction.objects.select_related("plan", "subscription")
        .filter(user_id=user.id)
        .order_by("-created_at", "-id")[:80]
    )

    return {
        "active_subscription": (
            _serialize_user_subscription(active_subscription)
            if active_subscription
            else None
        ),
        "subscriptions": [_serialize_user_subscription(item) for item in subscriptions],
        "transactions": [_serialize_transaction(item) for item in transactions],
    }, status.HTTP_200_OK


def get_active_subscription_payload(request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    if not user:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    vendor_id = _coerce_int(coalesce(request.query_params, "vendor_id", "vendorId"))
    expire_subscriptions(user_id=user.id)
    active_subscription = get_active_subscription_for_user(
        user.id,
        vendor_id=vendor_id,
        use_cache=False,
    )
    return {
        "subscription": (
            _serialize_user_subscription(active_subscription)
            if active_subscription
            else None
        )
    }, status.HTTP_200_OK


def _payment_failed(payload: dict[str, Any]) -> bool:
    status_value = str(coalesce(payload, "payment_status", "paymentStatus") or "SUCCESS").strip().upper()
    if status_value == "FAILED":
        return True
    return parse_bool(coalesce(payload, "simulate_failure", "simulateFailure"), default=False)


def _payment_method(payload: dict[str, Any]) -> str:
    return str(coalesce(payload, "payment_method", "paymentMethod", default="ESEWA") or "ESEWA").strip().upper()[:30]


def _create_subscription_record(*, user_id: int, plan: SubscriptionPlan, start_at: Any, upgraded_from: Optional[UserSubscription] = None) -> UserSubscription:
    end_at = start_at + timedelta(days=max(int(plan.duration_days or 1), 1))
    return UserSubscription.objects.create(
        user_id=user_id,
        plan=plan,
        vendor=plan.vendor,
        status=UserSubscription.STATUS_ACTIVE,
        start_at=start_at,
        end_at=end_at,
        remaining_free_tickets=int(plan.free_tickets_total or 0),
        used_free_tickets=0,
        total_discount_used=Decimal("0.00"),
        upgraded_from=upgraded_from,
    )


def subscribe_customer(request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    if not user:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    serializer = SubscriptionSubscribeSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid subscribe payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    plan_id = serializer.validated_data["plan_id"]
    plan = SubscriptionPlan.objects.select_related("vendor").filter(id=plan_id).first()
    if not plan:
        return {"message": "Plan not found."}, status.HTTP_404_NOT_FOUND
    if not plan.is_active or not plan.is_public or not _plan_is_live(plan):
        return {"message": "Selected plan is not available."}, status.HTTP_400_BAD_REQUEST

    method = _payment_method(payload)
    fail_payment = _payment_failed(payload)
    now = timezone.now()

    with transaction.atomic():
        expire_subscriptions(user_id=user.id, now=now)

        active_subscriptions = list(
            _active_subscriptions_for_user(
                user_id=user.id,
                lock_for_update=True,
                now=now,
            )
        )

        if not plan.allow_multiple_active:
            conflicting = next(
                (
                    row
                    for row in active_subscriptions
                    if row.plan and not row.plan.allow_multiple_active
                ),
                None,
            )
            if conflicting:
                return {
                    "message": "An active subscription already exists.",
                    "active_subscription": _serialize_user_subscription(conflicting, now=now),
                }, status.HTTP_409_CONFLICT

        if fail_payment:
            tx = SubscriptionTransaction.objects.create(
                user_id=user.id,
                plan=plan,
                transaction_type=SubscriptionTransaction.TYPE_PURCHASE,
                status=SubscriptionTransaction.STATUS_FAILED,
                amount=_quantize_money(plan.price),
                currency=plan.currency,
                metadata={
                    "payment_method": method,
                    "failure_reason": "PAYMENT_FAILED",
                },
            )
            return {
                "message": "Subscription purchase failed.",
                "transaction": _serialize_transaction(tx),
            }, status.HTTP_402_PAYMENT_REQUIRED

        subscription = _create_subscription_record(user_id=user.id, plan=plan, start_at=now)
        tx = SubscriptionTransaction.objects.create(
            user_id=user.id,
            subscription=subscription,
            plan=plan,
            transaction_type=SubscriptionTransaction.TYPE_PURCHASE,
            status=SubscriptionTransaction.STATUS_SUCCESS,
            amount=_quantize_money(plan.price),
            currency=plan.currency,
            metadata={
                "payment_method": method,
            },
        )

    _clear_user_active_subscription_cache(user.id)
    return {
        "message": "Subscription activated.",
        "subscription": _serialize_user_subscription(subscription),
        "transaction": _serialize_transaction(tx),
    }, status.HTTP_201_CREATED


def upgrade_customer(request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    if not user:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    serializer = SubscriptionUpgradeSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid upgrade payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    plan_id = serializer.validated_data["plan_id"]
    next_plan = SubscriptionPlan.objects.select_related("vendor").filter(id=plan_id).first()
    if not next_plan:
        return {"message": "Plan not found."}, status.HTTP_404_NOT_FOUND
    if not next_plan.is_active or not next_plan.is_public or not _plan_is_live(next_plan):
        return {"message": "Selected plan is not available."}, status.HTTP_400_BAD_REQUEST

    method = _payment_method(payload)
    fail_payment = _payment_failed(payload)
    now = timezone.now()

    with transaction.atomic():
        expire_subscriptions(user_id=user.id, now=now)

        current_subscription = get_active_subscription_for_user(
            user.id,
            use_cache=False,
            lock_for_update=True,
        )
        if not current_subscription:
            return {
                "message": "No active subscription to upgrade.",
            }, status.HTTP_404_NOT_FOUND

        if current_subscription.plan_id == next_plan.id:
            return {
                "message": "You are already on this plan.",
            }, status.HTTP_400_BAD_REQUEST

        total_seconds = max(
            int((current_subscription.end_at - current_subscription.start_at).total_seconds()),
            1,
        )
        remaining_seconds = max(int((current_subscription.end_at - now).total_seconds()), 0)

        prorated_credit = _quantize_money(
            _quantize_money(current_subscription.plan.price)
            * (Decimal(str(remaining_seconds)) / Decimal(str(total_seconds)))
        )
        upgrade_charge = _quantize_money(_quantize_money(next_plan.price) - prorated_credit)
        if upgrade_charge < Decimal("0"):
            upgrade_charge = Decimal("0.00")

        if fail_payment:
            tx = SubscriptionTransaction.objects.create(
                user_id=user.id,
                subscription=current_subscription,
                plan=next_plan,
                transaction_type=SubscriptionTransaction.TYPE_UPGRADE,
                status=SubscriptionTransaction.STATUS_FAILED,
                amount=upgrade_charge,
                currency=next_plan.currency,
                metadata={
                    "payment_method": method,
                    "prorated_credit": float(prorated_credit),
                    "failure_reason": "PAYMENT_FAILED",
                },
            )
            return {
                "message": "Subscription upgrade failed.",
                "transaction": _serialize_transaction(tx),
                "prorated_credit": float(prorated_credit),
                "upgrade_charge": float(upgrade_charge),
            }, status.HTTP_402_PAYMENT_REQUIRED

        current_meta = dict(current_subscription.metadata or {})
        current_meta["upgrade_to_plan_id"] = next_plan.id
        current_meta["upgraded_at"] = now.isoformat()
        current_subscription.status = UserSubscription.STATUS_CANCELLED
        current_subscription.cancelled_at = now
        current_subscription.end_at = now
        current_subscription.cancel_at_period_end = False
        current_subscription.metadata = current_meta
        current_subscription.save(
            update_fields=[
                "status",
                "cancelled_at",
                "end_at",
                "cancel_at_period_end",
                "metadata",
                "updated_at",
            ]
        )

        new_subscription = _create_subscription_record(
            user_id=user.id,
            plan=next_plan,
            start_at=now,
            upgraded_from=current_subscription,
        )

        tx = SubscriptionTransaction.objects.create(
            user_id=user.id,
            subscription=new_subscription,
            plan=next_plan,
            transaction_type=SubscriptionTransaction.TYPE_UPGRADE,
            status=SubscriptionTransaction.STATUS_SUCCESS,
            amount=upgrade_charge,
            currency=next_plan.currency,
            metadata={
                "payment_method": method,
                "previous_subscription_id": current_subscription.id,
                "prorated_credit": float(prorated_credit),
            },
        )

    _clear_user_active_subscription_cache(user.id)
    return {
        "message": "Subscription upgraded.",
        "subscription": _serialize_user_subscription(new_subscription),
        "transaction": _serialize_transaction(tx),
        "prorated_credit": float(prorated_credit),
        "upgrade_charge": float(upgrade_charge),
    }, status.HTTP_200_OK


def cancel_customer_subscription(request: Any) -> tuple[dict[str, Any], int]:
    user = resolve_customer(request)
    if not user:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    serializer = SubscriptionCancelSerializer(data=payload)
    if not serializer.is_valid():
        return {
            "message": "Invalid cancellation payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    immediate = bool(serializer.validated_data.get("immediate"))
    reason = str(serializer.validated_data.get("reason") or "").strip()
    now = timezone.now()

    with transaction.atomic():
        expire_subscriptions(user_id=user.id, now=now)
        current = get_active_subscription_for_user(
            user.id,
            use_cache=False,
            lock_for_update=True,
        )
        if not current:
            return {
                "message": "No active subscription found.",
            }, status.HTTP_404_NOT_FOUND

        if immediate:
            total_seconds = max(int((current.end_at - current.start_at).total_seconds()), 1)
            remaining_seconds = max(int((current.end_at - now).total_seconds()), 0)
            refund_amount = _quantize_money(
                _quantize_money(current.plan.price)
                * (Decimal(str(remaining_seconds)) / Decimal(str(total_seconds)))
            )

            current.status = UserSubscription.STATUS_CANCELLED
            current.cancelled_at = now
            current.end_at = now
            current.cancel_at_period_end = False
            current.metadata = {
                **(current.metadata or {}),
                "cancel_reason": reason,
                "cancelled_by": "customer",
            }
            current.save(
                update_fields=[
                    "status",
                    "cancelled_at",
                    "end_at",
                    "cancel_at_period_end",
                    "metadata",
                    "updated_at",
                ]
            )

            SubscriptionTransaction.objects.create(
                user_id=user.id,
                subscription=current,
                plan=current.plan,
                transaction_type=SubscriptionTransaction.TYPE_CANCEL,
                status=SubscriptionTransaction.STATUS_SUCCESS,
                amount=Decimal("0.00"),
                currency=current.plan.currency,
                metadata={
                    "reason": reason,
                    "immediate": True,
                },
            )

            refund_tx = None
            if refund_amount > Decimal("0"):
                refund_tx = SubscriptionTransaction.objects.create(
                    user_id=user.id,
                    subscription=current,
                    plan=current.plan,
                    transaction_type=SubscriptionTransaction.TYPE_REFUND,
                    status=SubscriptionTransaction.STATUS_SUCCESS,
                    amount=refund_amount,
                    currency=current.plan.currency,
                    metadata={
                        "reason": reason,
                        "refund_type": "PRORATED",
                    },
                )

            _clear_user_active_subscription_cache(user.id)
            return {
                "message": "Subscription cancelled immediately.",
                "subscription": _serialize_user_subscription(current),
                "refund_transaction": _serialize_transaction(refund_tx) if refund_tx else None,
            }, status.HTTP_200_OK

        current.cancel_at_period_end = True
        current.metadata = {
            **(current.metadata or {}),
            "cancel_reason": reason,
            "cancel_at_period_end_requested_at": now.isoformat(),
        }
        current.save(update_fields=["cancel_at_period_end", "metadata", "updated_at"])

        SubscriptionTransaction.objects.create(
            user_id=user.id,
            subscription=current,
            plan=current.plan,
            transaction_type=SubscriptionTransaction.TYPE_CANCEL,
            status=SubscriptionTransaction.STATUS_SUCCESS,
            amount=Decimal("0.00"),
            currency=current.plan.currency,
            metadata={
                "reason": reason,
                "immediate": False,
            },
        )

    _clear_user_active_subscription_cache(user.id)
    return {
        "message": "Subscription will be cancelled at period end.",
        "subscription": _serialize_user_subscription(current),
    }, status.HTTP_200_OK


def preview_checkout_subscription(
    user_id: int,
    payload: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    serializer = SubscriptionCheckoutPreviewSerializer(data=payload)
    if not serializer.is_valid():
        return None, {
            "message": "Invalid subscription checkout payload.",
            "errors": serializer.errors,
        }, status.HTTP_400_BAD_REQUEST

    data = serializer.validated_data
    subtotal = _quantize_money(data.get("subtotal") or Decimal("0.00"))
    vendor_id = data.get("vendor_id")
    use_free_ticket = bool(data.get("use_free_ticket"))
    requested_free_tickets = max(int(data.get("requested_free_tickets") or 1), 0)
    seat_count = max(int(data.get("seat_count") or 1), 1)

    subscription_id = data.get("user_subscription_id")
    if subscription_id:
        subscription = (
            UserSubscription.objects.select_related("plan", "vendor")
            .filter(
                id=subscription_id,
                user_id=user_id,
                status=UserSubscription.STATUS_ACTIVE,
                end_at__gt=timezone.now(),
            )
            .first()
        )
    else:
        subscription = get_active_subscription_for_user(
            user_id,
            vendor_id=vendor_id,
            use_cache=True,
        )

    if not subscription:
        return None, {
            "message": "No active subscription found.",
        }, status.HTTP_404_NOT_FOUND

    plan = subscription.plan
    if not plan or not plan.is_active or not _plan_is_live(plan):
        return None, {
            "message": "Subscription plan is inactive or expired.",
        }, status.HTTP_400_BAD_REQUEST

    if vendor_id and plan.vendor_id and plan.vendor_id != vendor_id:
        return None, {
            "message": "This subscription is not valid for the selected vendor.",
        }, status.HTTP_400_BAD_REQUEST

    coupon_applied = bool(data.get("coupon_applied"))
    loyalty_applied = bool(data.get("loyalty_applied"))
    referral_wallet_applied = bool(data.get("referral_wallet_applied"))

    if coupon_applied and not plan.is_stackable_with_coupon:
        return None, {
            "message": "This subscription cannot be combined with coupon discounts.",
        }, status.HTTP_400_BAD_REQUEST
    if loyalty_applied and not plan.is_stackable_with_loyalty:
        return None, {
            "message": "This subscription cannot be combined with loyalty redemption.",
        }, status.HTTP_400_BAD_REQUEST
    if referral_wallet_applied and not plan.is_stackable_with_referral_wallet:
        return None, {
            "message": "This subscription cannot be combined with referral wallet credits.",
        }, status.HTTP_400_BAD_REQUEST

    discount_amount = Decimal("0.00")
    if plan.discount_type == SubscriptionPlan.DISCOUNT_TYPE_PERCENTAGE:
        discount_amount = _quantize_money(
            subtotal * _quantize_money(plan.discount_value) / Decimal("100")
        )
    elif plan.discount_type == SubscriptionPlan.DISCOUNT_TYPE_FIXED:
        discount_amount = _quantize_money(plan.discount_value)

    if discount_amount > subtotal:
        discount_amount = subtotal

    cap_amount = _quantize_money(plan.max_discount_amount) if plan.max_discount_amount is not None else None
    if cap_amount is not None and discount_amount > cap_amount:
        discount_amount = cap_amount

    free_tickets_to_use = 0
    free_ticket_discount = Decimal("0.00")
    if use_free_ticket and int(subscription.remaining_free_tickets or 0) > 0 and seat_count > 0:
        free_tickets_to_use = min(
            requested_free_tickets,
            int(subscription.remaining_free_tickets or 0),
            seat_count,
        )
        if free_tickets_to_use > 0:
            per_ticket_amount = _quantize_money(subtotal / Decimal(str(seat_count)))
            if per_ticket_amount > Decimal("0"):
                free_ticket_discount = _quantize_money(
                    per_ticket_amount * Decimal(str(free_tickets_to_use))
                )

    if cap_amount is not None:
        cap_remaining = cap_amount - discount_amount
        if cap_remaining < Decimal("0"):
            cap_remaining = Decimal("0.00")
        if free_ticket_discount > cap_remaining:
            per_ticket_amount = _quantize_money(subtotal / Decimal(str(seat_count)))
            if per_ticket_amount > Decimal("0"):
                max_tickets_by_cap = int(
                    (cap_remaining / per_ticket_amount).to_integral_value(rounding=ROUND_DOWN)
                )
                free_tickets_to_use = min(free_tickets_to_use, max_tickets_by_cap)
                free_ticket_discount = _quantize_money(
                    per_ticket_amount * Decimal(str(free_tickets_to_use))
                )
            else:
                free_tickets_to_use = 0
                free_ticket_discount = Decimal("0.00")

    total_discount = _quantize_money(discount_amount + free_ticket_discount)
    if total_discount > subtotal:
        total_discount = subtotal

    final_total = _quantize_money(subtotal - total_discount)
    if final_total < Decimal("0"):
        final_total = Decimal("0.00")

    preview = {
        "user_subscription_id": subscription.id,
        "plan_id": plan.id,
        "discount_amount": float(discount_amount),
        "free_ticket_discount_amount": float(free_ticket_discount),
        "free_tickets_to_use": int(free_tickets_to_use),
        "total_discount": float(total_discount),
        "subtotal": float(subtotal),
        "final_total": float(final_total),
        "remaining_free_tickets_before": int(subscription.remaining_free_tickets or 0),
        "remaining_free_tickets_after": max(
            int(subscription.remaining_free_tickets or 0) - int(free_tickets_to_use),
            0,
        ),
        "plan": _serialize_plan(plan),
        "subscription": _serialize_user_subscription(subscription),
    }
    return preview, None, status.HTTP_200_OK


def preview_checkout_for_customer(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Customer not found."}, status.HTTP_404_NOT_FOUND

    payload = get_payload(request)
    preview, error, status_code = preview_checkout_subscription(customer.id, payload)
    if error:
        return error, status_code
    return {
        "preview": preview,
    }, status.HTTP_200_OK


def consume_checkout_subscription(
    *,
    user_id: int,
    booking: Booking,
    preview: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    subscription_id = _coerce_int(coalesce(preview, "user_subscription_id", "subscription_id"))
    if not subscription_id:
        return {"message": "Subscription preview is missing user_subscription_id."}, status.HTTP_400_BAD_REQUEST

    with transaction.atomic():
        locked_booking = Booking.objects.select_for_update().filter(id=booking.id).first()
        if not locked_booking:
            return {"message": "Booking not found for subscription consumption."}, status.HTTP_404_NOT_FOUND
        if locked_booking.user_id != user_id:
            return {"message": "Subscription does not match booking customer."}, status.HTTP_400_BAD_REQUEST

        if locked_booking.user_subscription_id:
            return {
                "message": "Subscription benefit already applied.",
                "subscription_discount": float(_quantize_money(locked_booking.subscription_discount_amount)),
                "free_tickets_used": int(locked_booking.subscription_free_tickets_used or 0),
                "user_subscription_id": locked_booking.user_subscription_id,
            }, status.HTTP_200_OK

        subscription = (
            UserSubscription.objects.select_for_update()
            .select_related("plan")
            .filter(
                id=subscription_id,
                user_id=user_id,
                status=UserSubscription.STATUS_ACTIVE,
                end_at__gt=timezone.now(),
            )
            .first()
        )
        if not subscription:
            return {"message": "Active subscription was not found."}, status.HTTP_404_NOT_FOUND

        total_discount = _parse_money(coalesce(preview, "total_discount", "discount_amount"))
        free_tickets_to_use = max(_coerce_int(preview.get("free_tickets_to_use"), default=0) or 0, 0)

        if free_tickets_to_use > int(subscription.remaining_free_tickets or 0):
            return {
                "message": "Free ticket balance changed. Please retry checkout preview.",
                "remaining_free_tickets": int(subscription.remaining_free_tickets or 0),
            }, status.HTTP_409_CONFLICT

        subscription.remaining_free_tickets = max(
            int(subscription.remaining_free_tickets or 0) - free_tickets_to_use,
            0,
        )
        subscription.used_free_tickets = int(subscription.used_free_tickets or 0) + free_tickets_to_use
        subscription.total_discount_used = _quantize_money(
            _quantize_money(subscription.total_discount_used) + total_discount
        )
        subscription.save(
            update_fields=[
                "remaining_free_tickets",
                "used_free_tickets",
                "total_discount_used",
                "updated_at",
            ]
        )

        locked_booking.subscription_plan = subscription.plan
        locked_booking.user_subscription = subscription
        locked_booking.subscription_discount_amount = total_discount
        locked_booking.subscription_free_tickets_used = free_tickets_to_use
        locked_booking.save(
            update_fields=[
                "subscription_plan",
                "user_subscription",
                "subscription_discount_amount",
                "subscription_free_tickets_used",
            ]
        )

        if total_discount > Decimal("0"):
            SubscriptionTransaction.objects.create(
                user_id=user_id,
                subscription=subscription,
                plan=subscription.plan,
                booking=locked_booking,
                transaction_type=SubscriptionTransaction.TYPE_DISCOUNT_APPLIED,
                status=SubscriptionTransaction.STATUS_SUCCESS,
                amount=Decimal("0.00"),
                discount_amount=total_discount,
                currency=subscription.plan.currency,
                metadata={
                    "booking_id": locked_booking.id,
                },
            )

        if free_tickets_to_use > 0:
            SubscriptionTransaction.objects.create(
                user_id=user_id,
                subscription=subscription,
                plan=subscription.plan,
                booking=locked_booking,
                transaction_type=SubscriptionTransaction.TYPE_FREE_TICKET_APPLIED,
                status=SubscriptionTransaction.STATUS_SUCCESS,
                amount=Decimal("0.00"),
                free_tickets_used=free_tickets_to_use,
                currency=subscription.plan.currency,
                metadata={
                    "booking_id": locked_booking.id,
                },
            )

    _clear_user_active_subscription_cache(user_id)
    return {
        "message": "Subscription benefits applied.",
        "user_subscription_id": subscription.id,
        "subscription_discount": float(total_discount),
        "free_tickets_used": int(free_tickets_to_use),
    }, status.HTTP_200_OK


def reverse_booking_subscription_effects(booking: Booking, *, reason: str = "") -> dict[str, Any]:
    result = {
        "discount_refund_amount": 0.0,
        "free_tickets_restored": 0,
        "transaction_id": None,
    }

    with transaction.atomic():
        locked_booking = (
            Booking.objects.select_for_update()
            .select_related("user_subscription__plan", "user")
            .filter(id=booking.id)
            .first()
        )
        if not locked_booking:
            return result

        applied_discount = _quantize_money(locked_booking.subscription_discount_amount)
        applied_free_tickets = int(locked_booking.subscription_free_tickets_used or 0)
        if applied_discount <= Decimal("0") and applied_free_tickets <= 0:
            return result

        already_reversed = SubscriptionTransaction.objects.filter(
            booking_id=locked_booking.id,
            transaction_type=SubscriptionTransaction.TYPE_REFUND,
            status=SubscriptionTransaction.STATUS_SUCCESS,
        ).exists()
        if already_reversed:
            return result

        subscription = None
        if locked_booking.user_subscription_id:
            subscription = (
                UserSubscription.objects.select_for_update()
                .select_related("plan")
                .filter(id=locked_booking.user_subscription_id)
                .first()
            )

        if subscription:
            subscription.remaining_free_tickets = int(subscription.remaining_free_tickets or 0) + applied_free_tickets
            if subscription.plan:
                max_free_tickets = int(subscription.plan.free_tickets_total or 0)
                if max_free_tickets >= 0:
                    subscription.remaining_free_tickets = min(subscription.remaining_free_tickets, max_free_tickets)
            subscription.used_free_tickets = max(int(subscription.used_free_tickets or 0) - applied_free_tickets, 0)
            subscription.total_discount_used = _quantize_money(
                _quantize_money(subscription.total_discount_used) - applied_discount
            )
            if subscription.total_discount_used < Decimal("0"):
                subscription.total_discount_used = Decimal("0.00")
            subscription.save(
                update_fields=[
                    "remaining_free_tickets",
                    "used_free_tickets",
                    "total_discount_used",
                    "updated_at",
                ]
            )

            _clear_user_active_subscription_cache(subscription.user_id)

        tx = SubscriptionTransaction.objects.create(
            user_id=locked_booking.user_id,
            subscription=subscription,
            plan=subscription.plan if subscription else locked_booking.subscription_plan,
            booking=locked_booking,
            transaction_type=SubscriptionTransaction.TYPE_REFUND,
            status=SubscriptionTransaction.STATUS_SUCCESS,
            amount=Decimal("0.00"),
            discount_amount=applied_discount,
            free_tickets_used=applied_free_tickets,
            currency=(subscription.plan.currency if subscription and subscription.plan else "NPR"),
            metadata={
                "reason": reason,
            },
        )

        result["discount_refund_amount"] = float(applied_discount)
        result["free_tickets_restored"] = int(applied_free_tickets)
        result["transaction_id"] = tx.id

    return result
