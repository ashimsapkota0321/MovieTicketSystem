# Practical Django Multi-App Refactoring Guide
## Implementation Scripts & Code Templates

This document provides copy-paste ready code and scripts to accelerate your refactoring.

---

## Part 1: Core App Setup

### 1.1 Create core/models.py

```python
"""
Core abstract models and base classes.
All apps should inherit from these to ensure consistency.
"""

from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    """
    Abstract model providing created_at and updated_at timestamps.
    Automatically tracks when objects are created and modified.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        abstract = True


class BaseModel(TimestampedModel):
    """
    Extended base model with common fields.
    Includes is_active for soft-delete patterns.
    """
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        """Mark as inactive instead of hard deletion."""
        self.is_active = False
        self.save(update_fields=['is_active'])

    def restore(self):
        """Reactivate a soft-deleted object."""
        self.is_active = True
        self.save(update_fields=['is_active'])
```

### 1.2 Create core/permissions.py

Move your existing permissions here:

```python
"""
Core permissions and decorators for role-based access control.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework import status
from functools import wraps


class AdminRequired(BasePermission):
    """
    Allows access only to admin users.
    """
    message = "Only admins can access this endpoint."

    def has_permission(self, request, view):
        # Adjust based on your actual admin check logic
        return hasattr(request, 'user') and request.user.is_admin


class VendorOrAdminRequired(BasePermission):
    """
    Allows access to vendor users or admins.
    """
    message = "Only vendors or admins can access this endpoint."

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        return hasattr(user, 'vendor') or getattr(user, 'is_admin', False)


# Decorator convenience
def admin_required(function):
    """
    Decorator for views that require admin user.
    Usage:
        @admin_required
        def my_view(request):
            ...
    """
    @wraps(function)
    def decorated_function(request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if not (hasattr(user, 'is_admin') and user.is_admin):
            return Response(
                {'error': 'Admin access required'},
                status=status.HTTP_403_FORBIDDEN
            )
        return function(request, *args, **kwargs)
    return decorated_function
```

### 1.3 Create core/exceptions.py

```python
"""
Custom exceptions for business logic errors.
Used across multiple apps.
"""

class AppException(Exception):
    """Base exception for application errors."""
    def __init__(self, message, code=None, status_code=400):
        self.message = message
        self.code = code or self.__class__.__name__
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(AppException):
    """Raised when business logic validation fails."""
    def __init__(self, message, field=None):
        self.field = field
        super().__init__(message, 'VALIDATION_ERROR', 400)


class NotFoundError(AppException):
    """Raised when resource doesn't exist."""
    def __init__(self, message):
        super().__init__(message, 'NOT_FOUND', 404)


class PermissionDeniedError(AppException):
    """Raised when user lacks permission."""
    def __init__(self, message):
        super().__init__(message, 'PERMISSION_DENIED', 403)


class ConflictError(AppException):
    """Raised when resource state conflicts with operation."""
    def __init__(self, message):
        super().__init__(message, 'CONFLICT', 409)


class InsufficientFundsError(AppException):
    """Raised when wallet/balance insufficient."""
    def __init__(self, message=None):
        super().__init__(
            message or 'Insufficient funds',
            'INSUFFICIENT_FUNDS',
            402
        )


# Example: Usage in service layer
# from apps.core.exceptions import InsufficientFundsError
# raise InsufficientFundsError("Wallet balance insufficient for booking")
```

### 1.4 Create core/selectors.py

```python
"""
Database query helpers (selectors pattern).
Centralizes database access logic to DRY up views and services.
"""

from django.db.models import QuerySet, Q
from typing import Optional


def get_user_by_email(email: str):
    """Fetch user by email or raise NotFound."""
    from apps.auth.models import User
    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        from apps.core.exceptions import NotFoundError
        raise NotFoundError(f"User with email '{email}' not found")


def get_active_bookings_for_user(user_id: int) -> QuerySet:
    """Get all non-canceled bookings for a user."""
    from apps.bookings.models import Booking
    return Booking.objects.filter(
        user_id=user_id,
        status__in=['CONFIRMED', 'PENDING']
    ).order_by('-created_at')


def get_vendor_wallet(vendor_id: int):
    """Get vendor's wallet, creating if doesn't exist."""
    from apps.finance.models import Wallet
    wallet, created = Wallet.objects.get_or_create(
        vendor_id=vendor_id,
        defaults={'balance': 0}
    )
    return wallet


def get_available_seats_for_show(show_id: int) -> QuerySet:
    """Get all available (unbookedseats for a show."""
    from apps.venues.models import Seat
    return Seat.objects.filter(
        screen__show_id=show_id,
        booked_by__isnull=True
    )
```

### 1.5 Create apps/core/apps.py

```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'
    
    def ready(self):
        """
        Import signals here to register them.
        """
        # Example:
        # from . import signals
        pass
```

---

## Part 2: Auth App Template

### 2.1 apps/auth/models.py

```python
"""
Authentication and user management models.
"""

from django.db import models
from django.contrib.auth.hashers import make_password, check_password, identify_hasher
from django.core.exceptions import ValidationError
from apps.core.models import TimestampedModel


class User(TimestampedModel):
    """
    Customer user account.
    
    Note: This uses custom authentication (not Django's auth system)
    for flexibility with phone-based login.
    """
    phone_number = models.CharField(max_length=13, unique=True, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        db_index=True
    )
    profile_image = models.ImageField(
        upload_to='profile_images/',
        blank=True,
        null=True
    )
    dob = models.DateField()
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50)
    password = models.CharField(max_length=256)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "users"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['phone_number']),
        ]

    def set_password(self, raw_password: str) -> None:
        """Hash and store a password."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify a password."""
        try:
            identify_hasher(self.password)
            return check_password(raw_password, self.password)
        except Exception:
            # Handle legacy plaintext passwords
            if raw_password == self.password:
                self.set_password(raw_password)
                self.save(update_fields=['password'])
                return True
            return False

    def save(self, *args, **kwargs):
        """Ensure password is hashed before saving."""
        if self.password and not self.password.startswith('pbkdf2_'):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class Admin(TimestampedModel):
    """Admin user account for system management."""
    
    email = models.EmailField(unique=True, db_index=True)
    phone_number = models.CharField(
        max_length=13,
        unique=True,
        blank=True,
        null=True
    )
    username = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        db_index=True
    )
    full_name = models.CharField(max_length=100, blank=True, null=True)
    profile_image = models.ImageField(
        upload_to='admin_profiles/',
        blank=True,
        null=True
    )
    password = models.CharField(max_length=256)
    is_active = models.BooleanField(default=True)
    role = models.CharField(
        max_length=20,
        choices=[
            ('SUPER_ADMIN', 'Super Admin'),
            ('ADMIN', 'Admin'),
            ('FINANCE', 'Finance'),
            ('SUPPORT', 'Support'),
        ],
        default='ADMIN'
    )

    class Meta:
        db_table = "admins"
        ordering = ['-created_at']

    def set_password(self, raw_password: str) -> None:
        """Hash and store a password."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify a password."""
        try:
            identify_hasher(self.password)
            return check_password(raw_password, self.password)
        except Exception:
            if raw_password == self.password:
                self.set_password(raw_password)
                self.save(update_fields=['password'])
                return True
            return False

    def __str__(self):
        return f"{self.full_name or self.email}"


class OTPVerification(models.Model):
    """
    One-time password verification storage.
    Used for phone/email verification during registration.
    """
    phone_number = models.CharField(max_length=13, db_index=True)
    otp_code = models.CharField(max_length=6)
    attempts = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "otp_verifications"
        ordering = ['-created_at']

    def is_expired(self) -> bool:
        """Check if OTP has expired."""
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.phone_number}"


class LoginAttempt(models.Model):
    """Track login attempts for security."""
    user_email = models.CharField(max_length=255, db_index=True)
    ip_address = models.GenericIPAddressField()
    success = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "login_attempts"
        indexes = [
            models.Index(fields=['user_email', '-created_at']),
        ]
```

### 2.2 apps/auth/serializers.py

```python
"""
DRF serializers for auth endpoints.
"""

from rest_framework import serializers
from .models import User, Admin, OTPVerification


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile endpoints."""
    
    class Meta:
        model = User
        fields = [
            'id', 'phone_number', 'email', 'username', 'first_name',
            'middle_name', 'last_name', 'profile_image', 'dob', 'is_active',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'password': {'write_only': True},
        }

    def create(self, validated_data):
        """Hash password on creation."""
        user = User(**validated_data)
        user.set_password(validated_data.get('password', ''))
        user.save()
        return user


class AdminSerializer(serializers.ModelSerializer):
    """Serializer for admin profile."""
    
    class Meta:
        model = Admin
        fields = [
            'id', 'email', 'phone_number', 'full_name', 'profile_image',
            'role', 'is_active', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class OTPVerificationSerializer(serializers.ModelSerializer):
    """Serializer for OTP endpoints."""
    
    class Meta:
        model = OTPVerification
        fields = ['phone_number', 'otp_code', 'is_verified']
        read_only_fields = ['is_verified']
```

### 2.3 apps/auth/services.py

```python
"""
Auth business logic layer.
Separated from views for easier testing and reuse.
"""

from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import random
import string

from apps.core.exceptions import ValidationError, NotFoundError, PermissionDeniedError
from .models import User, Admin, OTPVerification, LoginAttempt


def register_user(phone_number: str, email: str, password: str, **kwargs):
    """
    Register a new user account.
    
    Args:
        phone_number: User's phone number (unique)
        email: User's email (unique)
        password: Raw password (will be hashed)
        **kwargs: Additional fields (first_name, last_name, dob, etc.)
        
    Returns:
        User instance
        
    Raises:
        ValidationError: If email/phone already exists or validation fails
    """
    if User.objects.filter(email=email).exists():
        raise ValidationError("Email already registered", field='email')
    
    if User.objects.filter(phone_number=phone_number).exists():
        raise ValidationError("Phone number already registered", field='phone_number')
    
    user = User(
        phone_number=phone_number,
        email=email,
        **kwargs
    )
    user.set_password(password)
    user.save()
    
    return user


def authenticate_user(identifier: str, password: str, ip_address: str = None):
    """
    Authenticate user by email/phone and password.
    
    Args:
        identifier: Email or phone number
        password: Raw password to check
        ip_address: IP for login attempt logging
        
    Returns:
        User instance
        
    Raises:
        ValidationError: If credentials invalid
    """
    try:
        if '@' in identifier:
            user = User.objects.get(email=identifier)
        else:
            user = User.objects.get(phone_number=identifier)
    except User.DoesNotExist:
        raise ValidationError("Invalid credentials")
    
    if not user.check_password(password):
        if ip_address:
            LoginAttempt.objects.create(
                user_email=identifier,
                ip_address=ip_address,
                success=False
            )
        raise ValidationError("Invalid credentials")
    
    if not user.is_active:
        raise ValidationError("User account is inactive")
    
    if ip_address:
        LoginAttempt.objects.create(
            user_email=identifier,
            ip_address=ip_address,
            success=True
        )
    
    return user


def send_otp(phone_number: str, expires_minutes: int = 5) -> str:
    """
    Generate and store OTP for phone verification.
    
    Returns:
        OTP code (in production, send via SMS service)
    """
    otp_code = ''.join(random.choices(string.digits, k=6))
    
    OTPVerification.objects.update_or_create(
        phone_number=phone_number,
        defaults={
            'otp_code': otp_code,
            'expires_at': timezone.now() + timedelta(minutes=expires_minutes),
            'attempts': 0,
            'is_verified': False
        }
    )
    
    # In production, call SMS API here
    # send_sms(phone_number, f"Your OTP is {otp_code}")
    
    return otp_code


def verify_otp(phone_number: str, otp_code: str, max_attempts: int = 5) -> bool:
    """
    Verify OTP code.
    
    Returns:
        True if valid, raises ValidationError otherwise
        
    Raises:
        ValidationError: If OTP invalid/expired/attempts exceeded
    """
    try:
        otp = OTPVerification.objects.get(phone_number=phone_number)
    except OTPVerification.DoesNotExist:
        raise ValidationError("No OTP found for this phone number")
    
    if otp.is_expired():
        raise ValidationError("OTP has expired")
    
    if otp.attempts >= max_attempts:
        raise ValidationError("Too many failed attempts")
    
    if otp.otp_code != otp_code:
        otp.attempts += 1
        otp.save(update_fields=['attempts'])
        raise ValidationError("Invalid OTP code")
    
    otp.is_verified = True
    otp.save(update_fields=['is_verified'])
    
    return True
```

### 2.4 apps/auth/urls.py

```python
"""URL routing for auth endpoints."""

from django.urls import path
from . import views

app_name = 'auth'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('send-otp/', views.send_otp, name='send-otp'),
    path('verify-otp/', views.verify_otp, name='verify-otp'),
    path('profile/', views.get_profile, name='profile'),
    path('profile/update/', views.update_profile, name='update-profile'),
    path('change-password/', views.change_password, name='change-password'),
]
```

---

## Part 3: Migration Safety Script

### 3.1 Pre-migration Backup Script

Create `scripts/backup_database.py`:

```python
#!/usr/bin/env python
"""
Backup database before multi-app refactoring.
Run this before any migrations.
"""

import os
import json
import subprocess
from datetime import datetime

os.chdir('../backend')

# Create backup directory if needed
os.makedirs('backups', exist_ok=True)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup_file = f'backups/backup_{timestamp}.json'

print(f"Creating backup: {backup_file}")

# Dump all data
subprocess.run([
    'python', 'manage.py', 'dumpdata',
    '--indent', '2',
    '--output', backup_file
])

print(f"✓ Backup created successfully")

# Create list of all tables
print("\nDatabase tables summary:")
subprocess.run(['python', 'manage.py', 'dbshell'], input="""
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'YOUR_DB_NAME' 
AND table_type = 'BASE TABLE'
ORDER BY table_name;
""")
```

Run before migrations:
```bash
python scripts/backup_database.py
```

### 3.2 Migration Validation Script

Create `scripts/validate_migrations.py`:

```python
#!/usr/bin/env python
"""
Validate all migrations are correct before applying.
"""

import os
import subprocess

os.chdir('../backend')

print("Checking migration status...")
result = subprocess.run(['python', 'manage.py', 'showmigrations'], 
                       capture_output=True, text=True)
print(result.stdout)

print("\nDry-running migrations...")
result = subprocess.run(['python', 'manage.py', 'migrate', '--plan'], 
                       capture_output=True, text=True)
print(result.stdout)

if result.returncode != 0:
    print("❌ Migration plan failed!")
    print(result.stderr)
else:
    print("✓ All migrations validated successfully")
```

---

## Part 4: Import Update Script

### 4.1 Automated Find-and-Replace

Create `scripts/update_imports.py`:

```python
#!/usr/bin/env python
"""
Update imports from monolithic app to multi-app architecture.
BACKUP YOUR CODE FIRST!
"""

import os
import re
from pathlib import Path

# Mapping of old import patterns to new
IMPORT_MAPPINGS = [
    # (old_pattern, new_import)
    (r'from app\.models import User', 'from apps.auth.models import User'),
    (r'from app\.models import Admin', 'from apps.auth.models import Admin'),
    (r'from app\.models import Movie', 'from apps.catalog.models import Movie'),
    (r'from app\.models import Booking', 'from apps.bookings.models import Booking'),
    (r'from app\.models import Vendors', 'from apps.venues.models import Vendor'),
    (r'from app\.serializers import', 'from apps.APPNAME.serializers import'),
    (r'from app\.services import', 'from apps.APPNAME.services import'),
]

def update_imports_in_file(file_path: str) -> bool:
    """Update imports in a single Python file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        original_content = f.read()
    
    updated_content = original_content
    
    for old_pattern, new_import in IMPORT_MAPPINGS:
        updated_content = re.sub(old_pattern, new_import, updated_content)
    
    if updated_content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        return True
    
    return False

def main():
    backend_dir = Path('../backend')
    
    # Files to process
    python_files = list(backend_dir.rglob('*.py'))
    
    updated_count = 0
    for py_file in python_files:
        if update_imports_in_file(str(py_file)):
            print(f"✓ Updated: {py_file}")
            updated_count += 1
    
    print(f"\n✓ Total files updated: {updated_count}")

if __name__ == '__main__':
    main()
```

Run after creating all apps:
```bash
python scripts/update_imports.py
```

---

## Part 5: Testing Template

### 5.1 Test Factory for Seeding

Create `tests/factories.py`:

```python
"""
Factory Boy factories for test data generation.
"""

from factory import django, Faker, SubFactory
from apps.auth.models import User, Admin
from apps.catalog.models import Movie
from apps.venues.models import Vendor, Show
from apps.bookings.models import Booking


class UserFactory(django.DjangoModelFactory):
    class Meta:
        model = User
    
    phone_number = Faker('phone_number')
    email = Faker('email')
    first_name = Faker('first_name')
    last_name = Faker('last_name')
    dob = Faker('date_of_birth', minimum_age=18, maximum_age=70)
    
    @classmethod
    def create(cls, **kwargs):
        user = super().create(**kwargs)
        user.set_password('testpass123')
        user.save()
        return user


class AdminFactory(django.DjangoModelFactory):
    class Meta:
        model = Admin
    
    email = Faker('email')
    full_name = Faker('name')
    role = 'ADMIN'


class MovieFactory(django.DjangoModelFactory):
    class Meta:
        model = Movie
    
    title = Faker('sentence', nb_words=3)
    description = Faker('text')
    rating = 8.5


class VendorFactory(django.DjangoModelFactory):
    class Meta:
        model = Vendor
    
    name = Faker('company')
    email = Faker('email')


class BookingFactory(django.DjangoModelFactory):
    class Meta:
        model = Booking
    
    user = SubFactory(UserFactory)
    vendor = SubFactory(VendorFactory)
    movie = SubFactory(MovieFactory)
    total_price = 500.00
```

### 5.2 Integration Test Example

Create `tests/bookings/test_integration.py`:

```python
"""
Integration tests for booking workflow.
"""

from django.test import TestCase
from django.contrib.auth.models import User as DjangoUser

from apps.bookings.models import Booking
from apps.finance.models import Wallet
from apps.bookings.services import create_booking
from tests.factories import UserFactory, VendorFactory, MovieFactory


class BookingIntegrationTest(TestCase):
    """Test complete booking workflow across apps."""
    
    def setUp(self):
        self.user = UserFactory()
        self.vendor = VendorFactory()
        self.movie = MovieFactory()
    
    def test_booking_creates_transaction_records(self):
        """Test that creating booking also creates finance transactions."""
        wallet = Wallet.objects.create(vendor=self.vendor, balance=1000)
        
        booking = create_booking({
            'user': self.user,
            'vendor': self.vendor,
            'movie': self.movie,
            'total_price': 500
        })
        
        self.assertIsNotNone(booking.id)
        
        # Verify wallet was debited
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 500)  # 1000 - 500
    
    def test_booking_cancellation_refunds(self):
        """Test that booking cancellation triggers refund workflow."""
        wallet = Wallet.objects.create(vendor=self.vendor, balance=500)
        
        booking = Booking.objects.create(
            user=self.user,
            vendor=self.vendor,
            movie=self.movie,
            total_price=500,
            status='CONFIRMED'
        )
        
        # Cancel booking
        booking.status = 'CANCELLED'
        booking.save()
        
        # Verify refund
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 1000)  # Refunded
```

---

## Commands Quick Reference

```bash
# Backup before starting
python manage.py dumpdata > backup_before_refactor.json

# Create all new apps
for app in core auth catalog venues bookings finance concessions campaigns notifications; do
    python manage.py startapp $app apps/$app
done

# Make migrations for each app
python manage.py makemigrations

# Review before applying
python manage.py migrate --plan

# Apply migrations
python manage.py migrate

# Run tests
python manage.py test tests/

# Run specific app tests
python manage.py test apps.auth

# Database shell to check tables
python manage.py dbshell

# Rebuild cache (if using Django cache)
python manage.py clear_cache
```

---

**Next Steps:**
1. Create the `apps/` directory in backend
2. Follow the models.py templates for each app
3. Run `python manage.py startapp` for each
4. Copy model classes with `db_table` preserved
5. Run `python manage.py makemigrations`
6. Validate with `python manage.py migrate --plan`
7. Apply migrations: `python manage.py migrate`
8. Update all imports using the script
9. Run tests to verify everything works
