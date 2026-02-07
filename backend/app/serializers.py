from rest_framework import serializers
from .models import User
import re
import logging

logger = logging.getLogger(__name__)
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        required=True,
    )
    confirm_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        required=True,
    )

    class Meta:
        model = User
        fields = [
            "phone_number",
            "email",
            "dob",
            "first_name",
            "middle_name",
            "last_name",
            "password",
            "confirm_password",
        ]
        extra_kwargs = {
            "email": {"required": True},
            "phone_number": {"required": True},
            "first_name": {"required": True},
            "last_name": {"required": True},
            "dob": {"required": True},
        }

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Email already exists")
        return email

    def validate_phone_number(self, value):
        phone = value.strip()
        if not re.match(r"^\+?[0-9]{10,13}$", phone):
            raise serializers.ValidationError("Invalid phone number format")
        if User.objects.filter(phone_number=phone).exists():
            raise serializers.ValidationError("Phone number already exists")
        return phone

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match"}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        logger.info(f"Creating user with data: {validated_data}")

        user = User(
            phone_number=validated_data["phone_number"],
            email=validated_data["email"],
            dob=validated_data["dob"],
            first_name=validated_data["first_name"].strip(),
            middle_name=validated_data.get("middle_name", "").strip() or None,
            last_name=validated_data["last_name"].strip(),
        )
        # Hash password using model helper
        user.set_password(validated_data["password"])
        user.save()
        logger.info(f"User saved to database with ID: {user.id}")
        return user


class UserLoginSerializer(serializers.Serializer):
    email_or_phone = serializers.CharField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )
