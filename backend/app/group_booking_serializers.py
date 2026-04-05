"""Serializers for group booking and split payment workflows."""

from __future__ import annotations

import re
from decimal import Decimal

from rest_framework import serializers

from .models import GroupBookingSession


SEAT_LABEL_RE = re.compile(r"^[A-Z]*\d+[A-Z]?$")


def _normalize_seat_label(value: object) -> str:
    label = re.sub(r"\s+", "", str(value or "")).upper()
    if not label or not SEAT_LABEL_RE.match(label):
        raise serializers.ValidationError("Seat labels must look like A1, B12, or 10.")
    return label


class GroupBookingCreateSerializer(serializers.Serializer):
    show_id = serializers.IntegerField(required=False)
    movie_id = serializers.IntegerField(required=False)
    cinema_id = serializers.IntegerField(required=False)
    date = serializers.DateField(required=False)
    time = serializers.TimeField(required=False)
    hall = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    selected_seats = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=False,
    )
    split_mode = serializers.ChoiceField(
        choices=[
            GroupBookingSession.SPLIT_EQUAL,
            GroupBookingSession.SPLIT_MANUAL,
            GroupBookingSession.SPLIT_SEAT_BASED,
        ],
        default=GroupBookingSession.SPLIT_EQUAL,
    )
    expiry_minutes = serializers.IntegerField(required=False, min_value=5, max_value=30, default=12)

    def validate_selected_seats(self, value):
        normalized = []
        seen = set()
        for raw in value:
            seat = _normalize_seat_label(raw)
            if seat in seen:
                continue
            normalized.append(seat)
            seen.add(seat)
        if len(normalized) > 20:
            raise serializers.ValidationError("A group booking session supports up to 20 seats.")
        return normalized

    def validate(self, attrs):
        show_id = attrs.get("show_id")
        if not show_id:
            required_keys = ["movie_id", "cinema_id", "date", "time"]
            missing = [key for key in required_keys if not attrs.get(key)]
            if missing:
                raise serializers.ValidationError(
                    {
                        "message": (
                            "Either show_id or complete context (movie_id, cinema_id, date, time) is required."
                        )
                    }
                )
        return attrs


class GroupJoinSessionSerializer(serializers.Serializer):
    pass


class GroupSeatSelectionSerializer(serializers.Serializer):
    selected_seats = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        allow_empty=False,
    )

    def validate_selected_seats(self, value):
        normalized = []
        seen = set()
        for raw in value:
            seat = _normalize_seat_label(raw)
            if seat in seen:
                continue
            normalized.append(seat)
            seen.add(seat)
        return normalized


class GroupManualSplitEntrySerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.00"))


class GroupManualSplitSerializer(serializers.Serializer):
    allocations = GroupManualSplitEntrySerializer(many=True, required=True, allow_empty=False)

    def validate_allocations(self, value):
        seen = set()
        for item in value:
            user_id = int(item["user_id"])
            if user_id in seen:
                raise serializers.ValidationError("Each user can appear only once in allocations.")
            seen.add(user_id)
        return value


class GroupPaymentInitiateSerializer(serializers.Serializer):
    payment_method = serializers.CharField(required=False, allow_blank=True, default="ESEWA")


class GroupPaymentCompletionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["SUCCESS", "FAILED"])
    transaction_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider_reference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    metadata = serializers.JSONField(required=False)


class GroupParticipantDropSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class GroupSessionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
