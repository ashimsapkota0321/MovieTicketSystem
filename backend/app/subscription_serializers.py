"""DRF serializers for subscription and membership APIs."""

from __future__ import annotations

from rest_framework import serializers

from .models import SubscriptionPlan


class SubscriptionPlanWriteSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=40, required=True)
    name = serializers.CharField(max_length=120, required=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tier = serializers.ChoiceField(choices=SubscriptionPlan.TIER_CHOICES, required=False)
    duration_days = serializers.IntegerField(min_value=1, required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    currency = serializers.CharField(max_length=10, required=False)
    discount_type = serializers.ChoiceField(choices=SubscriptionPlan.DISCOUNT_TYPE_CHOICES, required=False)
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    max_discount_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
    )
    free_tickets_total = serializers.IntegerField(min_value=0, required=False)
    early_access_hours = serializers.IntegerField(min_value=0, required=False)
    special_pricing_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=100,
        required=False,
        allow_null=True,
    )
    subscription_only_access = serializers.BooleanField(required=False)
    allow_multiple_active = serializers.BooleanField(required=False)
    is_stackable_with_coupon = serializers.BooleanField(required=False)
    is_stackable_with_loyalty = serializers.BooleanField(required=False)
    is_stackable_with_referral_wallet = serializers.BooleanField(required=False)
    is_public = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
    priority = serializers.IntegerField(min_value=1, required=False)
    valid_from = serializers.DateTimeField(required=False, allow_null=True)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        discount_type = attrs.get("discount_type")
        discount_value = attrs.get("discount_value")

        if discount_type == SubscriptionPlan.DISCOUNT_TYPE_PERCENTAGE and discount_value is not None:
            if discount_value > 100:
                raise serializers.ValidationError(
                    {"discount_value": "Percentage discount cannot exceed 100."}
                )

        valid_from = attrs.get("valid_from")
        valid_until = attrs.get("valid_until")
        if valid_from and valid_until and valid_from > valid_until:
            raise serializers.ValidationError(
                {"valid_until": "valid_until must be after valid_from."}
            )

        code = attrs.get("code")
        if code is not None:
            attrs["code"] = str(code).strip().upper()

        currency = attrs.get("currency")
        if currency is not None:
            attrs["currency"] = str(currency).strip().upper()[:10]

        return attrs


class SubscriptionSubscribeSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(min_value=1, required=True)
    payment_method = serializers.CharField(max_length=30, required=False, allow_blank=True)
    payment_status = serializers.ChoiceField(
        choices=["SUCCESS", "FAILED"],
        required=False,
    )
    simulate_failure = serializers.BooleanField(required=False)


class SubscriptionUpgradeSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(min_value=1, required=True)
    payment_method = serializers.CharField(max_length=30, required=False, allow_blank=True)
    payment_status = serializers.ChoiceField(
        choices=["SUCCESS", "FAILED"],
        required=False,
    )
    simulate_failure = serializers.BooleanField(required=False)


class SubscriptionCancelSerializer(serializers.Serializer):
    immediate = serializers.BooleanField(required=False)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class SubscriptionCheckoutPreviewSerializer(serializers.Serializer):
    user_subscription_id = serializers.IntegerField(min_value=1, required=False)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=True)
    vendor_id = serializers.IntegerField(min_value=1, required=False)
    seat_count = serializers.IntegerField(min_value=1, required=False)
    use_free_ticket = serializers.BooleanField(required=False)
    requested_free_tickets = serializers.IntegerField(min_value=0, required=False)
    coupon_applied = serializers.BooleanField(required=False)
    loyalty_applied = serializers.BooleanField(required=False)
    referral_wallet_applied = serializers.BooleanField(required=False)
