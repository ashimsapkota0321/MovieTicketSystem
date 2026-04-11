"""Loyalty points and rewards business logic."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Optional

from django.core.cache import cache
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status

from .models import (
    Booking,
    LoyaltyProgramConfig,
    LoyaltyPromotion,
    LoyaltyTransaction,
    Reward,
    RewardRedemption,
    User,
    UserLoyaltyWallet,
    Vendor,
)
from .permissions import resolve_customer
from .utils import coalesce, get_payload, parse_bool, parse_datetime_utc

LOYALTY_CACHE_KEY_PREFIX = "mt:loyalty:wallet:"
LOYALTY_CACHE_TTL_SECONDS = 60 * 5
DEFAULT_REWARD_HOLD_DAYS = 30


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _quantize_money(value: Any) -> Decimal:
    return _to_decimal(value).quantize(Decimal("0.01"))


def _wallet_cache_key(user_id: int) -> str:
    return f"{LOYALTY_CACHE_KEY_PREFIX}{int(user_id)}"


def clear_wallet_cache(user_id: int) -> None:
    cache.delete(_wallet_cache_key(user_id))


def get_program_config() -> LoyaltyProgramConfig:
    config, _ = LoyaltyProgramConfig.objects.get_or_create(
        key="default",
        defaults={
            "points_per_currency_unit": Decimal("10.00"),
            "redemption_value_per_point": Decimal("1.00"),
            "first_booking_bonus": 50,
            "points_expiry_months": 12,
            "tier_silver_threshold": 0,
            "tier_gold_threshold": 1500,
            "tier_platinum_threshold": 5000,
            "referral_bonus_points": 100,
            "is_active": True,
        },
    )
    return config


def _resolve_wallet_tier(lifetime_points: int, config: LoyaltyProgramConfig) -> str:
    if lifetime_points >= int(config.tier_platinum_threshold or 0):
        return UserLoyaltyWallet.TIER_PLATINUM
    if lifetime_points >= int(config.tier_gold_threshold or 0):
        return UserLoyaltyWallet.TIER_GOLD
    return UserLoyaltyWallet.TIER_SILVER


def _tier_multiplier(tier: str) -> Decimal:
    normalized = str(tier or "").strip().upper()
    if normalized == UserLoyaltyWallet.TIER_PLATINUM:
        return Decimal("1.25")
    if normalized == UserLoyaltyWallet.TIER_GOLD:
        return Decimal("1.10")
    return Decimal("1.00")


def _ensure_wallet(user: User) -> UserLoyaltyWallet:
    wallet, _ = UserLoyaltyWallet.objects.get_or_create(user=user)
    return wallet


def _wallet_payload(wallet: UserLoyaltyWallet) -> dict[str, Any]:
    return {
        "user_id": wallet.user_id,
        "total_points": int(wallet.total_points or 0),
        "available_points": int(wallet.available_points or 0),
        "lifetime_points": int(wallet.lifetime_points or 0),
        "tier": wallet.tier,
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
    }


def get_wallet_snapshot(user: User, *, use_cache: bool = True) -> dict[str, Any]:
    if not user or not user.id:
        return {
            "user_id": None,
            "total_points": 0,
            "available_points": 0,
            "lifetime_points": 0,
            "tier": UserLoyaltyWallet.TIER_SILVER,
            "updated_at": None,
        }

    cache_key = _wallet_cache_key(user.id)
    if use_cache:
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    wallet = _ensure_wallet(user)
    payload = _wallet_payload(wallet)
    cache.set(cache_key, payload, timeout=LOYALTY_CACHE_TTL_SECONDS)
    return payload


def _points_for_amount(amount: Decimal, per_currency_unit: Decimal) -> int:
    if per_currency_unit <= Decimal("0"):
        return 0
    if amount <= Decimal("0"):
        return 0
    return int((amount / per_currency_unit).to_integral_value(rounding=ROUND_DOWN))


def _active_promotions(vendor: Optional[Vendor], *, trigger_code: str = "") -> list[LoyaltyPromotion]:
    now = timezone.now()
    queryset = LoyaltyPromotion.objects.filter(is_active=True, vendor__isnull=True).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now),
        Q(ends_at__isnull=True) | Q(ends_at__gte=now),
    )

    normalized_trigger = str(trigger_code or "").strip().upper()
    if normalized_trigger:
        queryset = queryset.filter(
            Q(trigger_code__isnull=True)
            | Q(trigger_code="")
            | Q(trigger_code__iexact=normalized_trigger)
        )
    else:
        queryset = queryset.filter(Q(trigger_code__isnull=True) | Q(trigger_code=""))

    return list(queryset.order_by("-stackable", "-bonus_multiplier", "-bonus_flat_points", "id"))


def _promotion_effect(promotions: list[LoyaltyPromotion]) -> tuple[Decimal, int, list[int]]:
    if not promotions:
        return Decimal("1.00"), 0, []

    stackable = [item for item in promotions if item.stackable]
    non_stackable = [item for item in promotions if not item.stackable]

    multiplier = Decimal("1.00")
    flat_points = 0
    applied_ids: list[int] = []

    for promo in stackable:
        multiplier *= _to_decimal(promo.bonus_multiplier, Decimal("1.00"))
        flat_points += max(int(promo.bonus_flat_points or 0), 0)
        applied_ids.append(promo.id)

    if non_stackable:
        best = sorted(
            non_stackable,
            key=lambda item: (
                _to_decimal(item.bonus_multiplier, Decimal("1.00")),
                int(item.bonus_flat_points or 0),
            ),
            reverse=True,
        )[0]
        multiplier *= _to_decimal(best.bonus_multiplier, Decimal("1.00"))
        flat_points += max(int(best.bonus_flat_points or 0), 0)
        applied_ids.append(best.id)

    if multiplier < Decimal("1.00"):
        multiplier = Decimal("1.00")

    return multiplier, flat_points, applied_ids


def _update_wallet_totals(
    wallet: UserLoyaltyWallet,
    *,
    available_delta: int = 0,
    lifetime_delta: int = 0,
    config: Optional[LoyaltyProgramConfig] = None,
) -> None:
    cfg = config or get_program_config()
    next_available = int(wallet.available_points or 0) + int(available_delta or 0)
    next_lifetime = int(wallet.lifetime_points or 0) + int(lifetime_delta or 0)

    if next_available < 0:
        next_available = 0
    if next_lifetime < 0:
        next_lifetime = 0

    wallet.available_points = next_available
    wallet.total_points = next_available
    wallet.lifetime_points = next_lifetime
    wallet.tier = _resolve_wallet_tier(next_lifetime, cfg)
    wallet.save(update_fields=["available_points", "total_points", "lifetime_points", "tier", "updated_at"])
    clear_wallet_cache(wallet.user_id)


def _create_loyalty_transaction(
    *,
    wallet: UserLoyaltyWallet,
    user: User,
    transaction_type: str,
    points: int,
    reference_type: str,
    reference_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    expires_at: Optional[Any] = None,
    is_expired: bool = False,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[LoyaltyTransaction]:
    safe_points = int(points or 0)
    if safe_points <= 0:
        return None

    if idempotency_key:
        existing = LoyaltyTransaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    return LoyaltyTransaction.objects.create(
        wallet=wallet,
        user=user,
        transaction_type=transaction_type,
        points=safe_points,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id is not None else None,
        idempotency_key=idempotency_key,
        expires_at=expires_at,
        is_expired=bool(is_expired),
        metadata=metadata or {},
    )


def _parse_reward_discount(reward: Reward, subtotal: Decimal) -> Decimal:
    safe_subtotal = _quantize_money(subtotal)
    if safe_subtotal <= Decimal("0"):
        return Decimal("0.00")

    if reward.reward_type == Reward.TYPE_FREE_TICKET:
        return safe_subtotal

    fixed_discount = _quantize_money(reward.discount_amount or Decimal("0"))
    percent = _to_decimal(reward.discount_percent, Decimal("0"))
    discount = fixed_discount

    if percent > Decimal("0"):
        discount = _quantize_money((safe_subtotal * percent) / Decimal("100"))

    max_discount = _to_decimal(reward.max_discount_amount)
    if max_discount > Decimal("0"):
        discount = min(discount, _quantize_money(max_discount))

    if discount > safe_subtotal:
        discount = safe_subtotal
    if discount < Decimal("0"):
        discount = Decimal("0.00")
    return discount


def _reward_is_available(reward: Reward) -> bool:
    if not reward or not reward.is_active:
        return False
    now = timezone.now()
    if reward.expiry_date and reward.expiry_date < now:
        return False
    if reward.stock_limit is not None and int(reward.redeemed_count or 0) >= int(reward.stock_limit):
        return False
    return True


def preview_checkout_redemption(
    user: User,
    payload: dict[str, Any],
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]], int]:
    if not user or not user.id:
        return None, {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    subtotal = _quantize_money(
        coalesce(payload, "subtotal", "ticket_total", "ticketTotal", "amount", default="0")
    )
    if subtotal <= Decimal("0"):
        return None, {"message": "A valid subtotal amount is required."}, status.HTTP_400_BAD_REQUEST

    config = get_program_config()
    wallet_snapshot = get_wallet_snapshot(user)
    available_points = int(wallet_snapshot.get("available_points") or 0)

    reward_id = _coerce_int(coalesce(payload, "reward_id", "rewardId"), 0)
    points_to_redeem = _coerce_int(coalesce(payload, "points", "points_to_redeem", "pointsToRedeem"), 0)
    if points_to_redeem < 0:
        return None, {"message": "points_to_redeem cannot be negative."}, status.HTTP_400_BAD_REQUEST

    vendor_id = _coerce_int(coalesce(payload, "vendor_id", "vendorId"), 0)

    reward: Optional[Reward] = None
    reward_discount = Decimal("0.00")
    reward_points_cost = 0
    reward_payload: Optional[dict[str, Any]] = None

    if reward_id:
        reward = Reward.objects.filter(id=reward_id).first()
        if not reward:
            return None, {"message": "Selected reward was not found."}, status.HTTP_404_NOT_FOUND
        if vendor_id and reward.vendor_id and reward.vendor_id != vendor_id:
            return None, {"message": "Selected reward is not available for this vendor."}, status.HTTP_400_BAD_REQUEST
        if not _reward_is_available(reward):
            return None, {"message": "Selected reward is inactive or expired."}, status.HTTP_400_BAD_REQUEST
        reward_discount = _parse_reward_discount(reward, subtotal)
        reward_points_cost = int(reward.points_required or 0)
        reward_payload = {
            "id": reward.id,
            "title": reward.title,
            "reward_type": reward.reward_type,
            "points_required": reward_points_cost,
            "discount_amount": float(reward_discount),
            "vendor_id": reward.vendor_id,
        }

    remaining_after_reward = subtotal - reward_discount
    if remaining_after_reward < Decimal("0"):
        remaining_after_reward = Decimal("0.00")

    redemption_value = _to_decimal(config.redemption_value_per_point, Decimal("1.00"))
    if redemption_value <= Decimal("0"):
        redemption_value = Decimal("1.00")

    direct_discount_capacity = _quantize_money(points_to_redeem * redemption_value)
    direct_discount = min(remaining_after_reward, direct_discount_capacity)
    direct_points_used = 0
    if redemption_value > Decimal("0") and direct_discount > Decimal("0"):
        direct_points_used = int((direct_discount / redemption_value).to_integral_value(rounding=ROUND_DOWN))

    total_points_to_use = reward_points_cost + direct_points_used
    if total_points_to_use > available_points:
        return None, {
            "message": "Insufficient loyalty points for selected redemption.",
            "available_points": available_points,
            "required_points": total_points_to_use,
        }, status.HTTP_400_BAD_REQUEST

    total_discount = _quantize_money(reward_discount + direct_discount)
    final_total = subtotal - total_discount
    if final_total < Decimal("0"):
        final_total = Decimal("0.00")

    preview = {
        "subtotal": float(subtotal),
        "reward": reward_payload,
        "points_requested": points_to_redeem,
        "points_value_per_point": float(redemption_value),
        "direct_points_used": direct_points_used,
        "reward_points_used": reward_points_cost,
        "total_points_to_use": total_points_to_use,
        "reward_discount": float(reward_discount),
        "direct_points_discount": float(direct_discount),
        "total_discount": float(total_discount),
        "final_total": float(final_total),
        "available_points": available_points,
        "is_valid": True,
    }
    return preview, None, status.HTTP_200_OK


def consume_checkout_redemption(
    *,
    user: User,
    booking: Booking,
    preview: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    total_points_to_use = int(preview.get("total_points_to_use") or 0)
    total_discount = _quantize_money(preview.get("total_discount") or Decimal("0"))
    reward_data = preview.get("reward") if isinstance(preview.get("reward"), dict) else None
    reward_id = _coerce_int((reward_data or {}).get("id"), 0)

    if total_points_to_use <= 0 and not reward_id:
        return {
            "points_used": 0,
            "discount_amount": 0.0,
            "reward_redemption_id": None,
        }, status.HTTP_200_OK

    with transaction.atomic():
        wallet = UserLoyaltyWallet.objects.select_for_update().filter(user_id=user.id).first()
        if not wallet:
            wallet = UserLoyaltyWallet.objects.create(user=user)

        available_points = int(wallet.available_points or 0)
        if total_points_to_use > available_points:
            return {
                "message": "Insufficient loyalty points.",
                "available_points": available_points,
                "required_points": total_points_to_use,
            }, status.HTTP_400_BAD_REQUEST

        reward_obj: Optional[Reward] = None
        redemption: Optional[RewardRedemption] = None
        if reward_id:
            reward_obj = Reward.objects.select_for_update().filter(id=reward_id).first()
            if not reward_obj or not _reward_is_available(reward_obj):
                return {"message": "Selected reward is no longer available."}, status.HTTP_400_BAD_REQUEST

            redemption = RewardRedemption.objects.create(
                user=user,
                reward=reward_obj,
                points_used=int(preview.get("reward_points_used") or 0),
                booking=booking,
                status=RewardRedemption.STATUS_USED,
                used_at=timezone.now(),
                expires_at=reward_obj.expiry_date,
                metadata={"source": "checkout"},
            )
            reward_obj.redeemed_count = int(reward_obj.redeemed_count or 0) + 1
            reward_obj.save(update_fields=["redeemed_count", "updated_at"])

        if total_points_to_use > 0:
            wallet.available_points = available_points - total_points_to_use
            wallet.total_points = wallet.available_points
            wallet.save(update_fields=["available_points", "total_points", "updated_at"])
            _create_loyalty_transaction(
                wallet=wallet,
                user=user,
                transaction_type=LoyaltyTransaction.TYPE_REDEEM,
                points=total_points_to_use,
                reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
                reference_id=str(booking.id),
                idempotency_key=f"loyalty-redeem-booking-{booking.id}",
                metadata={
                    "reward_id": reward_id or None,
                    "discount_amount": float(total_discount),
                    "direct_points_used": int(preview.get("direct_points_used") or 0),
                },
            )

        booking.loyalty_points_redeemed = total_points_to_use
        booking.loyalty_discount_amount = total_discount
        booking.reward_redemption = redemption
        booking.save(
            update_fields=[
                "loyalty_points_redeemed",
                "loyalty_discount_amount",
                "reward_redemption",
            ]
        )

        clear_wallet_cache(user.id)

    return {
        "points_used": total_points_to_use,
        "discount_amount": float(total_discount),
        "reward_redemption_id": redemption.id if redemption else None,
    }, status.HTTP_200_OK


def award_booking_points(booking: Booking, *, event_name: str = "") -> int:
    if not booking or not booking.id or not booking.user_id:
        return 0
    if str(booking.booking_status or "").strip().lower() == "cancelled":
        return 0

    with transaction.atomic():
        wallet = UserLoyaltyWallet.objects.select_for_update().filter(user_id=booking.user_id).first()
        if not wallet:
            wallet = UserLoyaltyWallet.objects.create(user=booking.user)

        idempotency_key = f"loyalty-earn-booking-{booking.id}"
        already = LoyaltyTransaction.objects.filter(idempotency_key=idempotency_key).exists()
        if already:
            return 0

        config = get_program_config()
        amount = _quantize_money(booking.total_amount or Decimal("0"))

        points_ratio = _to_decimal(config.points_per_currency_unit, Decimal("10.00"))

        base_points = _points_for_amount(amount, points_ratio)

        first_bonus = 0
        if not Booking.objects.filter(user_id=booking.user_id).exclude(id=booking.id).exclude(booking_status__iexact="Cancelled").exists():
            first_bonus = int(config.first_booking_bonus or 0)

        promotions = _active_promotions(None, trigger_code=event_name)
        promo_multiplier, promo_flat, promo_ids = _promotion_effect(promotions)
        tier_multiplier = _tier_multiplier(wallet.tier)

        gross_points = Decimal(base_points + first_bonus + promo_flat)
        gross_points *= promo_multiplier
        gross_points *= tier_multiplier

        earned_points = int(gross_points.to_integral_value(rounding=ROUND_DOWN))
        if earned_points <= 0:
            return 0

        expires_at = timezone.now() + timedelta(days=max(int(config.points_expiry_months or 0), 1) * 30)
        _update_wallet_totals(
            wallet,
            available_delta=earned_points,
            lifetime_delta=earned_points,
            config=config,
        )

        _create_loyalty_transaction(
            wallet=wallet,
            user=booking.user,
            transaction_type=LoyaltyTransaction.TYPE_EARN,
            points=earned_points,
            reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
            reference_id=str(booking.id),
            idempotency_key=idempotency_key,
            expires_at=expires_at,
            metadata={
                "base_points": base_points,
                "first_booking_bonus": first_bonus,
                "promotion_ids": promo_ids,
                "promotion_multiplier": float(promo_multiplier),
                "tier": wallet.tier,
                "tier_multiplier": float(tier_multiplier),
                "admin_managed_rule": True,
                "event_name": str(event_name or ""),
            },
        )

    return earned_points


def reverse_booking_points(booking: Booking, *, reason: str = "") -> dict[str, Any]:
    if not booking or not booking.id or not booking.user_id:
        return {"reversed_points": 0, "restored_points": 0}

    reversed_points = 0
    restored_points = 0

    with transaction.atomic():
        wallet = UserLoyaltyWallet.objects.select_for_update().filter(user_id=booking.user_id).first()
        if not wallet:
            wallet = UserLoyaltyWallet.objects.create(user=booking.user)

        earn_tx = (
            LoyaltyTransaction.objects.select_for_update()
            .filter(
                user_id=booking.user_id,
                transaction_type=LoyaltyTransaction.TYPE_EARN,
                reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
                reference_id=str(booking.id),
            )
            .order_by("-created_at", "-id")
            .first()
        )

        reverse_key = f"loyalty-reverse-booking-{booking.id}"
        if earn_tx and not LoyaltyTransaction.objects.filter(idempotency_key=reverse_key).exists():
            eligible_reverse = min(int(earn_tx.points or 0), int(wallet.available_points or 0))
            if eligible_reverse > 0:
                _update_wallet_totals(wallet, available_delta=-eligible_reverse, lifetime_delta=0)
                _create_loyalty_transaction(
                    wallet=wallet,
                    user=booking.user,
                    transaction_type=LoyaltyTransaction.TYPE_REVERSE_EARN,
                    points=eligible_reverse,
                    reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
                    reference_id=str(booking.id),
                    idempotency_key=reverse_key,
                    metadata={"reason": str(reason or "")},
                )
                reversed_points = eligible_reverse

        restore_points = int(booking.loyalty_points_redeemed or 0)
        restore_key = f"loyalty-restore-booking-{booking.id}"
        if restore_points > 0 and not LoyaltyTransaction.objects.filter(idempotency_key=restore_key).exists():
            _update_wallet_totals(wallet, available_delta=restore_points, lifetime_delta=0)
            _create_loyalty_transaction(
                wallet=wallet,
                user=booking.user,
                transaction_type=LoyaltyTransaction.TYPE_RESTORE,
                points=restore_points,
                reference_type=LoyaltyTransaction.REFERENCE_BOOKING,
                reference_id=str(booking.id),
                idempotency_key=restore_key,
                metadata={"reason": str(reason or ""), "source": "booking_cancellation"},
            )
            restored_points = restore_points

        redemption = booking.reward_redemption
        if redemption and redemption.status != RewardRedemption.STATUS_CANCELLED:
            redemption.status = RewardRedemption.STATUS_CANCELLED
            redemption.save(update_fields=["status"])
            reward = redemption.reward
            if reward and int(reward.redeemed_count or 0) > 0:
                reward.redeemed_count = int(reward.redeemed_count or 0) - 1
                reward.save(update_fields=["redeemed_count", "updated_at"])

    return {
        "reversed_points": reversed_points,
        "restored_points": restored_points,
    }


def expire_points(*, now: Optional[Any] = None, user_id: Optional[int] = None) -> dict[str, Any]:
    effective_now = now or timezone.now()
    queryset = LoyaltyTransaction.objects.filter(
        transaction_type=LoyaltyTransaction.TYPE_EARN,
        is_expired=False,
        expires_at__isnull=False,
        expires_at__lte=effective_now,
    ).order_by("expires_at", "id")
    if user_id:
        queryset = queryset.filter(user_id=user_id)

    expired_transactions = 0
    expired_points = 0

    for earn_tx in queryset.select_related("user", "wallet"):
        with transaction.atomic():
            locked_tx = LoyaltyTransaction.objects.select_for_update().filter(id=earn_tx.id, is_expired=False).first()
            if not locked_tx:
                continue

            wallet = UserLoyaltyWallet.objects.select_for_update().filter(id=locked_tx.wallet_id).first()
            if not wallet:
                locked_tx.is_expired = True
                locked_tx.save(update_fields=["is_expired"])
                continue

            points_to_expire = min(int(locked_tx.points or 0), int(wallet.available_points or 0))
            if points_to_expire > 0:
                _update_wallet_totals(wallet, available_delta=-points_to_expire, lifetime_delta=0)
                _create_loyalty_transaction(
                    wallet=wallet,
                    user=wallet.user,
                    transaction_type=LoyaltyTransaction.TYPE_EXPIRE,
                    points=points_to_expire,
                    reference_type=LoyaltyTransaction.REFERENCE_SYSTEM,
                    reference_id=str(locked_tx.id),
                    idempotency_key=f"loyalty-expire-{locked_tx.id}",
                    is_expired=True,
                    metadata={"source_transaction_id": locked_tx.id},
                )
                expired_points += points_to_expire

            locked_tx.is_expired = True
            locked_tx.save(update_fields=["is_expired"])
            expired_transactions += 1

    return {
        "expired_transactions": expired_transactions,
        "expired_points": expired_points,
        "run_at": effective_now.isoformat(),
    }


def get_customer_dashboard(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    wallet = get_wallet_snapshot(customer)
    aggregates = LoyaltyTransaction.objects.filter(user_id=customer.id).values("transaction_type").annotate(
        points=Sum("points")
    )
    summary = {item["transaction_type"]: int(item.get("points") or 0) for item in aggregates}

    recent_transactions = (
        LoyaltyTransaction.objects.filter(user_id=customer.id)
        .order_by("-created_at", "-id")[:20]
    )

    recent = [
        {
            "id": tx.id,
            "type": tx.transaction_type,
            "points": int(tx.points or 0),
            "reference_type": tx.reference_type,
            "reference_id": tx.reference_id,
            "expires_at": tx.expires_at.isoformat() if tx.expires_at else None,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
            "metadata": tx.metadata or {},
        }
        for tx in recent_transactions
    ]

    pending_redemptions = RewardRedemption.objects.filter(
        user_id=customer.id,
        status=RewardRedemption.STATUS_UNUSED,
    ).count()

    return {
        "wallet": wallet,
        "summary": {
            "earned": summary.get(LoyaltyTransaction.TYPE_EARN, 0),
            "redeemed": summary.get(LoyaltyTransaction.TYPE_REDEEM, 0),
            "expired": summary.get(LoyaltyTransaction.TYPE_EXPIRE, 0),
            "reversed": summary.get(LoyaltyTransaction.TYPE_REVERSE_EARN, 0),
            "restored": summary.get(LoyaltyTransaction.TYPE_RESTORE, 0),
            "pending_redemptions": pending_redemptions,
        },
        "transactions": recent,
    }, status.HTTP_200_OK


def list_customer_transactions(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    tx_type = str(coalesce(request.query_params, "type", "transaction_type", default="") or "").strip().upper()
    limit = max(1, min(_coerce_int(request.query_params.get("limit"), 100), 500))

    queryset = LoyaltyTransaction.objects.filter(user_id=customer.id).order_by("-created_at", "-id")
    if tx_type:
        queryset = queryset.filter(transaction_type=tx_type)

    transactions = [
        {
            "id": tx.id,
            "type": tx.transaction_type,
            "points": int(tx.points or 0),
            "reference_type": tx.reference_type,
            "reference_id": tx.reference_id,
            "is_expired": bool(tx.is_expired),
            "expires_at": tx.expires_at.isoformat() if tx.expires_at else None,
            "metadata": tx.metadata or {},
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx in queryset[:limit]
    ]

    return {"transactions": transactions, "count": len(transactions)}, status.HTTP_200_OK


def list_rewards_for_customer(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    wallet = get_wallet_snapshot(customer)
    available_points = int(wallet.get("available_points") or 0)

    vendor_id = _coerce_int(coalesce(request.query_params, "vendor_id", "vendorId"), 0)
    reward_type = str(coalesce(request.query_params, "reward_type", "rewardType", default="") or "").strip().upper()
    min_points = _coerce_int(coalesce(request.query_params, "min_points", "minPoints"), 0)

    now = timezone.now()
    queryset = Reward.objects.filter(is_active=True, vendor__isnull=True).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=now)
    )
    if vendor_id:
        pass
    if reward_type:
        queryset = queryset.filter(reward_type=reward_type)
    if min_points > 0:
        queryset = queryset.filter(points_required__gte=min_points)

    rewards = []
    for reward in queryset.order_by("points_required", "id")[:500]:
        rewards.append(
            {
                "id": reward.id,
                "title": reward.title,
                "description": reward.description,
                "reward_type": reward.reward_type,
                "points_required": int(reward.points_required or 0),
                "discount_amount": float(_quantize_money(reward.discount_amount or 0)),
                "discount_percent": float(_to_decimal(reward.discount_percent)),
                "max_discount_amount": float(_to_decimal(reward.max_discount_amount)),
                "vendor_id": reward.vendor_id,
                "vendor_name": reward.vendor.name if reward.vendor else None,
                "expiry_date": reward.expiry_date.isoformat() if reward.expiry_date else None,
                "is_active": bool(reward.is_active),
                "is_stackable_with_coupon": bool(reward.is_stackable_with_coupon),
                "can_redeem": available_points >= int(reward.points_required or 0),
                "stock_remaining": (
                    None
                    if reward.stock_limit is None
                    else max(int(reward.stock_limit or 0) - int(reward.redeemed_count or 0), 0)
                ),
            }
        )

    return {
        "wallet": wallet,
        "rewards": rewards,
        "count": len(rewards),
    }, status.HTTP_200_OK


def preview_checkout_for_customer(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    preview, error, status_code = preview_checkout_redemption(customer, payload)
    if error:
        return error, status_code
    return {
        "message": "Loyalty redemption preview generated.",
        "preview": preview,
    }, status.HTTP_200_OK


def redeem_reward_for_customer(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    reward_id = _coerce_int(coalesce(payload, "reward_id", "rewardId"), 0)
    if reward_id <= 0:
        return {"message": "reward_id is required."}, status.HTTP_400_BAD_REQUEST

    reward = Reward.objects.filter(id=reward_id).first()
    if not reward:
        return {"message": "Reward not found."}, status.HTTP_404_NOT_FOUND
    if not _reward_is_available(reward):
        return {"message": "Reward is inactive or expired."}, status.HTTP_400_BAD_REQUEST

    with transaction.atomic():
        wallet = UserLoyaltyWallet.objects.select_for_update().filter(user_id=customer.id).first()
        if not wallet:
            wallet = UserLoyaltyWallet.objects.create(user=customer)

        required_points = int(reward.points_required or 0)
        available_points = int(wallet.available_points or 0)
        if required_points > available_points:
            return {
                "message": "Insufficient loyalty points.",
                "available_points": available_points,
                "required_points": required_points,
            }, status.HTTP_400_BAD_REQUEST

        if reward.stock_limit is not None and int(reward.redeemed_count or 0) >= int(reward.stock_limit):
            return {"message": "Reward stock is exhausted."}, status.HTTP_400_BAD_REQUEST

        hold_until = timezone.now() + timedelta(days=DEFAULT_REWARD_HOLD_DAYS)
        if reward.expiry_date and reward.expiry_date < hold_until:
            hold_until = reward.expiry_date

        redemption = RewardRedemption.objects.create(
            user=customer,
            reward=reward,
            points_used=required_points,
            status=RewardRedemption.STATUS_UNUSED,
            expires_at=hold_until,
            metadata={"source": "manual_redeem"},
        )

        _update_wallet_totals(wallet, available_delta=-required_points, lifetime_delta=0)
        _create_loyalty_transaction(
            wallet=wallet,
            user=customer,
            transaction_type=LoyaltyTransaction.TYPE_REDEEM,
            points=required_points,
            reference_type=LoyaltyTransaction.REFERENCE_REWARD,
            reference_id=str(reward.id),
            idempotency_key=f"loyalty-manual-redeem-{redemption.id}",
            metadata={"redemption_id": redemption.id},
        )

        reward.redeemed_count = int(reward.redeemed_count or 0) + 1
        reward.save(update_fields=["redeemed_count", "updated_at"])

    return {
        "message": "Reward redeemed successfully.",
        "redemption": {
            "id": redemption.id,
            "reward_id": redemption.reward_id,
            "reward_title": redemption.reward.title,
            "points_used": int(redemption.points_used or 0),
            "status": redemption.status,
            "redemption_code": redemption.redemption_code,
            "expires_at": redemption.expires_at.isoformat() if redemption.expires_at else None,
            "created_at": redemption.created_at.isoformat() if redemption.created_at else None,
        },
        "wallet": get_wallet_snapshot(customer, use_cache=False),
    }, status.HTTP_201_CREATED


def list_customer_redemptions(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    status_filter = str(coalesce(request.query_params, "status", default="") or "").strip().upper()
    limit = max(1, min(_coerce_int(request.query_params.get("limit"), 100), 500))

    queryset = RewardRedemption.objects.select_related("reward", "booking").filter(user_id=customer.id).order_by(
        "-created_at", "-id"
    )
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    redemptions = [
        {
            "id": item.id,
            "reward_id": item.reward_id,
            "reward_title": item.reward.title if item.reward else None,
            "reward_type": item.reward.reward_type if item.reward else None,
            "points_used": int(item.points_used or 0),
            "status": item.status,
            "booking_id": item.booking_id,
            "redemption_code": item.redemption_code,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "used_at": item.used_at.isoformat() if item.used_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in queryset[:limit]
    ]

    return {"redemptions": redemptions, "count": len(redemptions)}, status.HTTP_200_OK


def apply_referral_bonus(request: Any) -> tuple[dict[str, Any], int]:
    customer = resolve_customer(request)
    if not customer:
        return {"message": "Authentication required."}, status.HTTP_401_UNAUTHORIZED

    payload = get_payload(request)
    referral_code = str(coalesce(payload, "referral_code", "referralCode", default="") or "").strip().upper()
    if not referral_code:
        return {"message": "referral_code is required."}, status.HTTP_400_BAD_REQUEST

    own_referral_code = str(getattr(customer, "referral_code", "") or "").strip().upper()
    if own_referral_code and referral_code == own_referral_code:
        return {"message": "You cannot use your own referral code."}, status.HTTP_400_BAD_REQUEST

    config = get_program_config()
    bonus_points = int(config.referral_bonus_points or 0)
    if bonus_points <= 0:
        return {"message": "Referral bonus is not configured."}, status.HTTP_400_BAD_REQUEST

    idempotency_key = f"loyalty-referral-{customer.id}-{referral_code}"
    if LoyaltyTransaction.objects.filter(idempotency_key=idempotency_key).exists():
        return {
            "message": "Referral bonus already claimed for this code.",
            "wallet": get_wallet_snapshot(customer),
        }, status.HTTP_200_OK

    with transaction.atomic():
        wallet = UserLoyaltyWallet.objects.select_for_update().filter(user_id=customer.id).first()
        if not wallet:
            wallet = UserLoyaltyWallet.objects.create(user=customer)

        _update_wallet_totals(wallet, available_delta=bonus_points, lifetime_delta=bonus_points)
        _create_loyalty_transaction(
            wallet=wallet,
            user=customer,
            transaction_type=LoyaltyTransaction.TYPE_EARN,
            points=bonus_points,
            reference_type=LoyaltyTransaction.REFERENCE_REFERRAL,
            reference_id=referral_code,
            idempotency_key=idempotency_key,
            metadata={"source": "referral_bonus"},
        )

    return {
        "message": "Referral bonus credited.",
        "wallet": get_wallet_snapshot(customer, use_cache=False),
    }, status.HTTP_200_OK


def _vendor_global_control_blocked() -> tuple[dict[str, Any], int]:
    return {
        "message": "Global loyalty and subscription controls are managed by super admin.",
        "hint": "Use /api/vendor/offers/ for vendor-specific offers and perks.",
    }, status.HTTP_403_FORBIDDEN


def get_vendor_rule(request: Any) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def update_vendor_rule(request: Any) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def list_vendor_rewards(request: Any) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def _normalize_reward_payload(payload: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    title = str(payload.get("title") or "").strip()
    if not title:
        return None, "title is required."

    reward_type = str(coalesce(payload, "reward_type", "rewardType") or Reward.TYPE_DISCOUNT).strip().upper()
    if reward_type not in {Reward.TYPE_DISCOUNT, Reward.TYPE_FREE_TICKET, Reward.TYPE_CASHBACK}:
        return None, "reward_type is invalid."

    points_required = _coerce_int(coalesce(payload, "points_required", "pointsRequired"), -1)
    if points_required < 0:
        return None, "points_required must be zero or more."

    discount_amount = _quantize_money(coalesce(payload, "discount_amount", "discountAmount", default=0))
    discount_percent = _to_decimal(coalesce(payload, "discount_percent", "discountPercent"), Decimal("0"))
    max_discount_amount = _to_decimal(coalesce(payload, "max_discount_amount", "maxDiscountAmount"), Decimal("0"))

    stock_raw = coalesce(payload, "stock_limit", "stockLimit")
    if stock_raw in (None, ""):
        stock_limit = None
    else:
        stock_limit = _coerce_int(stock_raw, -1)
        if stock_limit < 0:
            return None, "stock_limit must be a positive integer or empty."

    expiry_input = coalesce(payload, "expiry_date", "expiryDate")
    expiry_date = None
    if expiry_input:
        parsed = parse_datetime_utc(expiry_input)
        if not parsed:
            return None, "expiry_date is invalid."
        expiry_date = parsed

    normalized = {
        "title": title,
        "description": str(payload.get("description") or "").strip() or None,
        "reward_type": reward_type,
        "points_required": points_required,
        "discount_amount": discount_amount,
        "discount_percent": discount_percent if discount_percent > Decimal("0") else None,
        "max_discount_amount": max_discount_amount if max_discount_amount > Decimal("0") else None,
        "stock_limit": stock_limit,
        "expiry_date": expiry_date,
        "is_active": parse_bool(coalesce(payload, "is_active", "isActive"), default=True),
        "is_stackable_with_coupon": parse_bool(
            coalesce(payload, "is_stackable_with_coupon", "isStackableWithCoupon"),
            default=True,
        ),
    }
    return normalized, None


def create_vendor_reward(request: Any) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def update_vendor_reward(request: Any, reward: Reward) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def delete_vendor_reward(reward: Reward) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def list_vendor_promotions(request: Any) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def _normalize_promotion_payload(payload: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    title = str(payload.get("title") or "").strip()
    if not title:
        return None, "title is required."

    promo_type = str(coalesce(payload, "promo_type", "promoType") or LoyaltyPromotion.PROMO_TYPE_FESTIVAL).strip().upper()
    if promo_type not in {
        LoyaltyPromotion.PROMO_TYPE_FESTIVAL,
        LoyaltyPromotion.PROMO_TYPE_DAILY,
        LoyaltyPromotion.PROMO_TYPE_WEEKLY,
        LoyaltyPromotion.PROMO_TYPE_REFERRAL,
    }:
        return None, "promo_type is invalid."

    starts_at_input = coalesce(payload, "starts_at", "startsAt")
    ends_at_input = coalesce(payload, "ends_at", "endsAt")

    def parse_dt(value: Any) -> Optional[Any]:
        if not value:
            return None
        return parse_datetime_utc(value)

    starts_at = parse_dt(starts_at_input)
    ends_at = parse_dt(ends_at_input)
    if starts_at_input and not starts_at:
        return None, "starts_at is invalid."
    if ends_at_input and not ends_at:
        return None, "ends_at is invalid."
    if starts_at and ends_at and starts_at > ends_at:
        return None, "ends_at must be after starts_at."

    multiplier = _to_decimal(coalesce(payload, "bonus_multiplier", "bonusMultiplier"), Decimal("1"))
    if multiplier < Decimal("1"):
        return None, "bonus_multiplier must be at least 1."

    bonus_flat = _coerce_int(coalesce(payload, "bonus_flat_points", "bonusFlatPoints"), -1)
    if bonus_flat < 0:
        return None, "bonus_flat_points must be zero or more."

    return {
        "title": title,
        "description": str(payload.get("description") or "").strip() or None,
        "promo_type": promo_type,
        "trigger_code": str(coalesce(payload, "trigger_code", "triggerCode", default="") or "").strip().upper() or None,
        "bonus_multiplier": multiplier,
        "bonus_flat_points": bonus_flat,
        "stackable": parse_bool(payload.get("stackable"), default=False),
        "starts_at": starts_at,
        "ends_at": ends_at,
        "is_active": parse_bool(coalesce(payload, "is_active", "isActive"), default=True),
    }, None


def create_vendor_promotion(request: Any) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def update_vendor_promotion(request: Any, promotion: LoyaltyPromotion) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def delete_vendor_promotion(promotion: LoyaltyPromotion) -> tuple[dict[str, Any], int]:
    return _vendor_global_control_blocked()


def _serialize_reward_item(item: Reward) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "reward_type": item.reward_type,
        "points_required": int(item.points_required or 0),
        "discount_amount": float(_quantize_money(item.discount_amount or 0)),
        "discount_percent": float(_to_decimal(item.discount_percent)),
        "max_discount_amount": float(_to_decimal(item.max_discount_amount)),
        "stock_limit": item.stock_limit,
        "redeemed_count": int(item.redeemed_count or 0),
        "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
        "is_active": bool(item.is_active),
        "is_stackable_with_coupon": bool(item.is_stackable_with_coupon),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_promotion_item(item: LoyaltyPromotion) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "promo_type": item.promo_type,
        "trigger_code": item.trigger_code,
        "bonus_multiplier": float(_to_decimal(item.bonus_multiplier, Decimal("1"))),
        "bonus_flat_points": int(item.bonus_flat_points or 0),
        "stackable": bool(item.stackable),
        "starts_at": item.starts_at.isoformat() if item.starts_at else None,
        "ends_at": item.ends_at.isoformat() if item.ends_at else None,
        "is_active": bool(item.is_active),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_program_config(config: LoyaltyProgramConfig) -> dict[str, Any]:
    return {
        "key": config.key,
        "points_per_currency_unit": float(_to_decimal(config.points_per_currency_unit, Decimal("10"))),
        "redemption_value_per_point": float(_to_decimal(config.redemption_value_per_point, Decimal("1"))),
        "first_booking_bonus": int(config.first_booking_bonus or 0),
        "points_expiry_months": int(config.points_expiry_months or 0),
        "tier_silver_threshold": int(config.tier_silver_threshold or 0),
        "tier_gold_threshold": int(config.tier_gold_threshold or 0),
        "tier_platinum_threshold": int(config.tier_platinum_threshold or 0),
        "referral_bonus_points": int(config.referral_bonus_points or 0),
        "is_active": bool(config.is_active),
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def list_admin_loyalty_rules() -> tuple[dict[str, Any], int]:
    config = get_program_config()
    rewards = Reward.objects.filter(vendor__isnull=True).order_by("-created_at", "-id")
    promotions = LoyaltyPromotion.objects.filter(vendor__isnull=True).order_by("-created_at", "-id")
    return {
        "rule": _serialize_program_config(config),
        "rewards": [_serialize_reward_item(item) for item in rewards],
        "promotions": [_serialize_promotion_item(item) for item in promotions],
    }, status.HTTP_200_OK


def update_admin_loyalty_rule(request: Any) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    config = get_program_config()

    if "is_active" in payload:
        config.is_active = parse_bool(payload.get("is_active"), default=config.is_active)

    if "points_per_currency_unit" in payload:
        value = _to_decimal(payload.get("points_per_currency_unit"))
        if value <= Decimal("0"):
            return {"message": "points_per_currency_unit must be positive."}, status.HTTP_400_BAD_REQUEST
        config.points_per_currency_unit = value

    if "redemption_value_per_point" in payload:
        value = _to_decimal(payload.get("redemption_value_per_point"))
        if value <= Decimal("0"):
            return {"message": "redemption_value_per_point must be positive."}, status.HTTP_400_BAD_REQUEST
        config.redemption_value_per_point = value

    for field in [
        "first_booking_bonus",
        "points_expiry_months",
        "tier_silver_threshold",
        "tier_gold_threshold",
        "tier_platinum_threshold",
        "referral_bonus_points",
    ]:
        if field in payload:
            value = _coerce_int(payload.get(field), -1)
            if value < 0:
                return {"message": f"{field} must be zero or more."}, status.HTTP_400_BAD_REQUEST
            setattr(config, field, value)

    if int(config.tier_gold_threshold or 0) < int(config.tier_silver_threshold or 0):
        return {
            "message": "tier_gold_threshold must be greater than or equal to tier_silver_threshold.",
        }, status.HTTP_400_BAD_REQUEST

    if int(config.tier_platinum_threshold or 0) < int(config.tier_gold_threshold or 0):
        return {
            "message": "tier_platinum_threshold must be greater than or equal to tier_gold_threshold.",
        }, status.HTTP_400_BAD_REQUEST

    config.save()
    return {"message": "Loyalty rule updated.", "rule": _serialize_program_config(config)}, status.HTTP_200_OK


def list_admin_rewards() -> tuple[dict[str, Any], int]:
    rewards = Reward.objects.filter(vendor__isnull=True).order_by("-created_at", "-id")
    return {
        "rewards": [_serialize_reward_item(item) for item in rewards],
        "count": len(rewards),
    }, status.HTTP_200_OK


def create_admin_reward(request: Any) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    normalized, error = _normalize_reward_payload(payload)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    reward = Reward.objects.create(vendor=None, **(normalized or {}))
    return {"message": "Reward created.", "reward": _serialize_reward_item(reward)}, status.HTTP_201_CREATED


def update_admin_reward(request: Any, reward: Reward) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    normalized, error = _normalize_reward_payload(payload)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    for key, value in (normalized or {}).items():
        setattr(reward, key, value)
    reward.vendor = None
    reward.save()
    return {"message": "Reward updated.", "reward": _serialize_reward_item(reward)}, status.HTTP_200_OK


def delete_admin_reward(reward: Reward) -> tuple[dict[str, Any], int]:
    reward.delete()
    return {"message": "Reward deleted."}, status.HTTP_200_OK


def list_admin_promotions() -> tuple[dict[str, Any], int]:
    promotions = LoyaltyPromotion.objects.filter(vendor__isnull=True).order_by("-created_at", "-id")
    return {
        "promotions": [_serialize_promotion_item(item) for item in promotions],
        "count": len(promotions),
    }, status.HTTP_200_OK


def create_admin_promotion(request: Any) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    normalized, error = _normalize_promotion_payload(payload)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    promotion = LoyaltyPromotion.objects.create(vendor=None, **(normalized or {}))
    return {
        "message": "Promotion created.",
        "promotion": _serialize_promotion_item(promotion),
    }, status.HTTP_201_CREATED


def update_admin_promotion(request: Any, promotion: LoyaltyPromotion) -> tuple[dict[str, Any], int]:
    payload = get_payload(request)
    normalized, error = _normalize_promotion_payload(payload)
    if error:
        return {"message": error}, status.HTTP_400_BAD_REQUEST

    for key, value in (normalized or {}).items():
        setattr(promotion, key, value)
    promotion.vendor = None
    promotion.save()
    return {
        "message": "Promotion updated.",
        "promotion": _serialize_promotion_item(promotion),
    }, status.HTTP_200_OK


def delete_admin_promotion(promotion: LoyaltyPromotion) -> tuple[dict[str, Any], int]:
    promotion.delete()
    return {"message": "Promotion deleted."}, status.HTTP_200_OK
