"""Serializers for revenue distribution analytics and config APIs."""

from __future__ import annotations

from rest_framework import serializers


class RevenueConfigUpdateSerializer(serializers.Serializer):
    commission_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)
    is_active = serializers.BooleanField(required=False, default=True)


class RevenueFilterSerializer(serializers.Serializer):
    range = serializers.ChoiceField(
        choices=["last_7_days", "last_30_days", "yearly", "custom"],
        required=False,
    )
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    group = serializers.ChoiceField(choices=["daily", "weekly", "monthly"], required=False)
