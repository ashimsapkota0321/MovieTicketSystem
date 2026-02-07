from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from .models import User, OTPVerification
from .serializers import UserRegistrationSerializer, UserLoginSerializer
import logging
import random
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

logger = logging.getLogger(__name__)


@api_view(["GET", "POST"])
def register(request):
    if request.method == "GET":
        return Response(
            {
                "message": "Registration endpoint",
                "method": "POST",
                "required_fields": [
                    "first_name",
                    "last_name",
                    "email",
                    "phone_number",
                    "dob",
                    "password",
                    "confirm_password",
                ],
            },
            status=status.HTTP_200_OK,
        )

    serializer = UserRegistrationSerializer(data=request.data)
    if serializer.is_valid():
        try:
            user = serializer.save()
            return Response(
                {
                    "message": "Registration successful",
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "phone_number": user.phone_number,
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("Error saving user")
            return Response(
                {"message": "Failed to create user", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    return Response(
        {"message": "Registration failed", "errors": serializer.errors},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET", "POST"])
def login(request):
    if request.method == "GET":
        return Response(
            {
                "message": "Login endpoint",
                "method": "POST",
                "required_fields": ["email_or_phone", "password"],
            },
            status=status.HTTP_200_OK,
        )

    serializer = UserLoginSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"message": "Invalid input", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    email_or_phone = serializer.validated_data["email_or_phone"].strip()
    password = serializer.validated_data["password"]

    try:
        user = User.objects.filter(
            Q(email__iexact=email_or_phone) | Q(phone_number=email_or_phone)
        ).first()

        if not user:
            return Response(
                {"message": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Use secure password check (handles hashed passwords)
        if not user.check_password(password):
            return Response(
                {"message": "Incorrect password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "message": f"Login successful. Welcome {user.first_name}!",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "phone_number": user.phone_number,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("Login error")
        return Response(
            {"message": "An error occurred during login", "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def forgot_password(request):
    """Request an OTP for password reset. Expects { email } in body."""
    email = request.data.get("email", "").strip()
    if not email:
        return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # generate 6-digit OTP
        otp = f"{random.randint(100000, 999999)}"
        # save OTP record
        OTPVerification.objects.create(email=email, otp=otp)

        # In production you would send OTP by email; for now we log it (and return generic message)
        logger.info(f"Generated OTP for {email}: {otp}")
        # Also print to terminal for easy debugging when DEBUG=True
        if getattr(settings, "DEBUG", False):
            print(f"DEBUG OTP for {email}: {otp}")

        return Response({"message": "OTP sent to your email"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("forgot_password error")
        return Response({"message": "Failed to send OTP", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def verify_otp(request):
    """Verify OTP. Expects { email, otp } in body."""
    email = request.data.get("email", "").strip()
    otp = request.data.get("otp", "").strip()
    if not email or not otp:
        return Response({"message": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # only consider OTPs created within last 10 minutes
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(email__iexact=email, otp=otp, created_at__gte=cutoff)
            .order_by("-created_at")
            .first()
        )
        if not record:
            return Response({"message": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

        record.is_verified = True
        record.save()

        return Response({"message": "OTP verified"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("verify_otp error")
        return Response({"message": "Failed to verify OTP", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def reset_password(request):
    """Reset password using verified OTP. Expects { email, otp, new_password }."""
    email = request.data.get("email", "").strip()
    otp = request.data.get("otp", "").strip()
    new_password = request.data.get("new_password", "")

    if not email or not otp or not new_password:
        return Response({"message": "Email, OTP and new_password are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # check verified OTP in last 10 minutes
        cutoff = timezone.now() - timedelta(minutes=10)
        record = (
            OTPVerification.objects.filter(email__iexact=email, otp=otp, created_at__gte=cutoff, is_verified=True)
            .order_by("-created_at")
            .first()
        )
        if not record:
            return Response({"message": "Invalid or unverified OTP"}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        user.set_password(new_password)
        user.save()

        # Invalidate OTP record
        record.is_verified = False
        record.save()

        return Response({"message": "Password reset successful"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("reset_password error")
        return Response({"message": "Failed to reset password", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def debug_get_otp(request):
    """Debug helper (DEBUG only): GET /api/auth/debug-otp/?email=... returns { otp, created_at, is_verified }
    Only available when settings.DEBUG is True."""
    if not getattr(settings, "DEBUG", False):
        return Response({"message": "Not available"}, status=status.HTTP_403_FORBIDDEN)

    email = request.query_params.get("email") or request.GET.get("email")
    if not email:
        return Response({"message": "Email query param is required"}, status=status.HTTP_400_BAD_REQUEST)

    record = (
        OTPVerification.objects.filter(email__iexact=email).order_by("-created_at").first()
    )
    if not record:
        return Response({"message": "No OTP found for this email"}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        "email": record.email,
        "otp": record.otp,
        "created_at": record.created_at,
        "is_verified": record.is_verified,
    }, status=status.HTTP_200_OK)
