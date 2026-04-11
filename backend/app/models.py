"""Database models for the application."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .utils import combine_date_time_utc


def _unique_slugify(
    instance: models.Model, value: str, slug_field: str = "slug", max_length: int = 220
) -> str:
    """Generate a unique slug for the given model instance."""
    base = slugify(value)[:max_length] or "item"
    slug = base
    suffix = 1
    model_cls = instance.__class__
    while (
        model_cls.objects.filter(**{slug_field: slug})
        .exclude(pk=instance.pk)
        .exists()
    ):
        suffix += 1
        trimmed = base[: max_length - len(str(suffix)) - 1]
        slug = f"{trimmed}-{suffix}"
    return slug


def _generate_transaction_uuid() -> str:
    return uuid.uuid4().hex


def _normalize_choice_value(
    value: str | None,
    default: str,
    allowed_values: set[str],
    aliases: dict[str, str] | None = None,
) -> str:
    normalized = str(value or default).strip().upper()
    if aliases:
        normalized = aliases.get(normalized, normalized)
    if normalized in allowed_values:
        return normalized
    return default


def _validate_status_transition(
    model_name: str,
    field_name: str,
    current_value: str | None,
    new_value: str,
    allowed_transitions: dict[str, set[str]],
) -> None:
    if current_value is None or current_value == new_value:
        return
    allowed_next_values = allowed_transitions.get(current_value)
    if allowed_next_values is None or new_value not in allowed_next_values:
        raise ValidationError(
            {field_name: f"{model_name} {field_name} cannot transition from {current_value} to {new_value}."}
        )


class User(models.Model):
    phone_number = models.CharField(max_length=13, unique=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    referral_code = models.CharField(max_length=20, unique=True, blank=True, null=True, db_index=True)
    signup_ip_address = models.CharField(max_length=45, blank=True, null=True)
    signup_user_agent = models.CharField(max_length=255, blank=True, null=True)
    signup_device_fingerprint = models.CharField(max_length=128, blank=True, null=True)
    profile_image = models.ImageField(upload_to="profile_images/", blank=True, null=True)
    dob = models.DateField()
    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True, null=True)
    last_name = models.CharField(max_length=50)
    password = models.CharField(max_length=256)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"

    def set_password(self, raw_password: str) -> None:
        """Hash and store a password."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify a password and migrate legacy plaintext if needed."""
        try:
            identify_hasher(self.password)
        except Exception:
            if raw_password == self.password:
                self.set_password(raw_password)
                self.save(update_fields=["password"])
                return True
            return False
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        """Ensure password is hashed before saving."""
        if self.password:
            try:
                identify_hasher(self.password)
            except Exception:
                self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class Admin(models.Model):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=13, unique=True, blank=True, null=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    full_name = models.CharField(max_length=100, blank=True, null=True)
    profile_image = models.ImageField(upload_to="admin_profiles/", blank=True, null=True)
    password = models.CharField(max_length=256)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "admins"

    def set_password(self, raw_password: str) -> None:
        """Hash and store a password."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify a password and migrate legacy plaintext if needed."""
        try:
            identify_hasher(self.password)
        except Exception:
            if raw_password == self.password:
                self.set_password(raw_password)
                self.save(update_fields=["password"])
                return True
            return False
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        """Ensure password is hashed before saving."""
        if self.password:
            try:
                identify_hasher(self.password)
            except Exception:
                self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name or self.username or self.email


class Vendor(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=13, unique=True, blank=True, null=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    profile_image = models.ImageField(upload_to="vendor_profiles/", blank=True, null=True)
    theatre = models.CharField(max_length=120, blank=True, null=True)
    city = models.CharField(max_length=80, blank=True, null=True)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, default="Active")
    password = models.CharField(max_length=256)
    must_change_password = models.BooleanField(default=False)
    temp_password_created_at = models.DateTimeField(blank=True, null=True)
    temp_password_expires_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendors"

    def set_password(self, raw_password: str) -> None:
        """Hash and store a password."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify a password and migrate legacy plaintext if needed."""
        try:
            identify_hasher(self.password)
        except Exception:
            if raw_password == self.password:
                self.set_password(raw_password)
                self.save(update_fields=["password"])
                return True
            return False
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        """Ensure password is hashed before saving."""
        if self.password:
            try:
                identify_hasher(self.password)
            except Exception:
                self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or self.username or self.email


class VendorLoyaltyRule(models.Model):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name="loyalty_rule")
    points_per_currency_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Currency amount required to earn one point for this vendor.",
    )
    first_booking_bonus = models.PositiveIntegerField(blank=True, null=True)
    bonus_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendor_loyalty_rules"
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return f"Loyalty Rule {self.vendor_id}"


class VendorStaff(models.Model):
    ROLE_CASHIER = "CASHIER"
    ROLE_MANAGER = "MANAGER"
    ROLE_CHOICES = [
        (ROLE_CASHIER, "Cashier"),
        (ROLE_MANAGER, "Manager"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="staff_accounts")
    full_name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=13, blank=True, null=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CASHIER)
    password = models.CharField(max_length=256)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendor_staff_accounts"
        ordering = ["-created_at", "-id"]

    def set_password(self, raw_password: str) -> None:
        """Hash and store a password."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verify a password and migrate legacy plaintext if needed."""
        try:
            identify_hasher(self.password)
        except Exception:
            if raw_password == self.password:
                self.set_password(raw_password)
                self.save(update_fields=["password"])
                return True
            return False
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        """Ensure password is hashed before saving."""
        if self.password:
            try:
                identify_hasher(self.password)
            except Exception:
                self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.role})"


class LoginAttempt(models.Model):
    identifier = models.CharField(max_length=255)
    ip_address = models.CharField(max_length=45)
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(blank=True, null=True)
    locked_until = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "login_attempts"
        unique_together = ("identifier", "ip_address")

    def __str__(self):
        return f"{self.identifier} ({self.ip_address})"


class AuthSession(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_VENDOR = "vendor"
    ROLE_CUSTOMER = "customer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_VENDOR, "Vendor"),
        (ROLE_CUSTOMER, "Customer"),
    ]

    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    user_id = models.PositiveIntegerField(db_index=True)
    staff_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    staff_role = models.CharField(max_length=40, blank=True, null=True)
    refresh_token_hash = models.CharField(max_length=64, unique=True, blank=True, null=True)
    access_expires_at = models.DateTimeField(db_index=True)
    refresh_expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(blank=True, null=True, db_index=True)
    revoked_reason = models.CharField(max_length=100, blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "auth_sessions"
        indexes = [
            models.Index(fields=["role", "user_id"]),
            models.Index(fields=["role", "revoked_at", "refresh_expires_at"]),
        ]

    def __str__(self):
        return f"{self.role}:{self.user_id} ({self.session_id})"


class Movie(models.Model):
    STATUS_NOW_SHOWING = "NOW_SHOWING"
    STATUS_COMING_SOON = "COMING_SOON"
    STATUS_CHOICES = [
        (STATUS_NOW_SHOWING, "Now Showing"),
        (STATUS_COMING_SOON, "Coming Soon"),
    ]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True, null=True)
    short_description = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    long_description = models.TextField(blank=True, null=True)
    language = models.CharField(max_length=50, blank=True, null=True)
    genre = models.CharField(max_length=80, blank=True, null=True)
    genres = models.ManyToManyField(
        "MovieGenre", through="MovieMovieGenre", related_name="movies", blank=True
    )
    duration = models.CharField(max_length=50, blank=True, null=True)
    duration_minutes = models.PositiveIntegerField(blank=True, null=True)
    rating = models.CharField(max_length=20, blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)
    poster_image = models.ImageField(upload_to="movie_posters/", blank=True, null=True)
    banner_image = models.ImageField(upload_to="movie_banners/", blank=True, null=True)
    poster_url = models.URLField(blank=True, null=True)
    trailer_url = models.URLField(blank=True, null=True)
    trailer_urls = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_COMING_SOON
    )
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)
    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
    )
    approval_reason = models.CharField(max_length=255, blank=True, null=True)
    approval_metadata = models.JSONField(default=dict, blank=True)
    approved_by = models.ForeignKey(
        "Admin",
        on_delete=models.SET_NULL,
        related_name="approved_movies",
        blank=True,
        null=True,
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "movies"
        indexes = [
            models.Index(fields=["approval_status", "created_at"]),
            models.Index(fields=["is_approved", "created_at"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """Generate a slug for the movie if missing."""
        if self.title and not self.slug:
            self.slug = _unique_slugify(self, self.title, "slug", 220)
        approval_status = str(self.approval_status or self.ApprovalStatus.APPROVED).strip().upper()
        if approval_status not in self.ApprovalStatus.values:
            approval_status = self.ApprovalStatus.APPROVED
        self.approval_status = approval_status
        self.is_approved = approval_status == self.ApprovalStatus.APPROVED
        super().save(*args, **kwargs)


class Show(models.Model):
    STATUS_UPCOMING = "upcoming"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_UPCOMING, "Upcoming"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
    ]
    BOOKING_CLOSE_BEFORE_START_MINUTES = 30

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="shows")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="shows")
    hall = models.CharField(max_length=80, blank=True, null=True)
    slot = models.CharField(max_length=20, blank=True, null=True)
    screen_type = models.CharField(max_length=40, blank=True, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UPCOMING)
    listing_status = models.CharField(max_length=20, default="Now Showing")
    show_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shows"
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "hall", "show_date", "start_time"],
                name="unique_show_per_vendor_hall_start",
            )
        ]

    def __str__(self):
        return f"{self.movie.title} ({self.show_date} {self.start_time})"

    def _combine_local_datetime(self, when_time):
        if not self.show_date or not when_time:
            return None
        return combine_date_time_utc(self.show_date, when_time)

    @property
    def start_datetime(self):
        return self._combine_local_datetime(self.start_time)

    @property
    def end_datetime(self):
        return self._combine_local_datetime(self.end_time or self.start_time)

    def booking_closes_at(self):
        start_dt = self.start_datetime
        if not start_dt:
            return None
        return start_dt - timedelta(minutes=self.BOOKING_CLOSE_BEFORE_START_MINUTES)

    def is_booking_open(self, now=None):
        now = now or timezone.now()
        closes_at = self.booking_closes_at()
        starts_at = self.start_datetime
        if not closes_at or not starts_at:
            return False
        return now < closes_at and now < starts_at


class PricingRule(models.Model):
    DAY_OF_WEEK_ALL = "ALL"
    DAY_OF_WEEK_WEEKDAY = "WEEKDAY"
    DAY_OF_WEEK_WEEKEND = "WEEKEND"
    DAY_OF_WEEK_MON = "MON"
    DAY_OF_WEEK_TUE = "TUE"
    DAY_OF_WEEK_WED = "WED"
    DAY_OF_WEEK_THU = "THU"
    DAY_OF_WEEK_FRI = "FRI"
    DAY_OF_WEEK_SAT = "SAT"
    DAY_OF_WEEK_SUN = "SUN"
    DAY_OF_WEEK_CHOICES = [
        (DAY_OF_WEEK_ALL, "All Days"),
        (DAY_OF_WEEK_WEEKDAY, "Weekday"),
        (DAY_OF_WEEK_WEEKEND, "Weekend"),
        (DAY_OF_WEEK_MON, "Monday"),
        (DAY_OF_WEEK_TUE, "Tuesday"),
        (DAY_OF_WEEK_WED, "Wednesday"),
        (DAY_OF_WEEK_THU, "Thursday"),
        (DAY_OF_WEEK_FRI, "Friday"),
        (DAY_OF_WEEK_SAT, "Saturday"),
        (DAY_OF_WEEK_SUN, "Sunday"),
    ]

    DAY_TYPE_ALL = "ALL"
    DAY_TYPE_WEEKDAY = "WEEKDAY"
    DAY_TYPE_WEEKEND = "WEEKEND"
    DAY_TYPE_CHOICES = [
        (DAY_TYPE_ALL, "All Days"),
        (DAY_TYPE_WEEKDAY, "Weekday"),
        (DAY_TYPE_WEEKEND, "Weekend"),
    ]

    SEAT_CATEGORY_ALL = "ALL"
    SEAT_CATEGORY_NORMAL = "NORMAL"
    SEAT_CATEGORY_EXECUTIVE = "EXECUTIVE"
    SEAT_CATEGORY_PREMIUM = "PREMIUM"
    SEAT_CATEGORY_VIP = "VIP"
    SEAT_CATEGORY_SILVER = "SILVER"
    SEAT_CATEGORY_GOLD = "GOLD"
    SEAT_CATEGORY_PLATINUM = "PLATINUM"
    SEAT_CATEGORY_CHOICES = [
        (SEAT_CATEGORY_ALL, "All Categories"),
        (SEAT_CATEGORY_NORMAL, "Normal"),
        (SEAT_CATEGORY_EXECUTIVE, "Executive"),
        (SEAT_CATEGORY_PREMIUM, "Premium"),
        (SEAT_CATEGORY_VIP, "VIP"),
        (SEAT_CATEGORY_SILVER, "Silver"),
        (SEAT_CATEGORY_GOLD, "Gold"),
        (SEAT_CATEGORY_PLATINUM, "Platinum"),
    ]

    ADJUSTMENT_FIXED = "FIXED"
    ADJUSTMENT_INCREMENT = "INCREMENT"
    ADJUSTMENT_PERCENT = "PERCENT"
    ADJUSTMENT_MULTIPLIER = "MULTIPLIER"
    ADJUSTMENT_TYPE_CHOICES = [
        (ADJUSTMENT_FIXED, "Set Fixed Price"),
        (ADJUSTMENT_INCREMENT, "Add Amount"),
        (ADJUSTMENT_PERCENT, "Percent Change"),
        (ADJUSTMENT_MULTIPLIER, "Multiply"),
    ]

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="pricing_rules",
        blank=True,
        null=True,
    )
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="pricing_rules", blank=True, null=True)
    name = models.CharField(max_length=120)
    hall = models.CharField(max_length=80, blank=True, null=True)
    day_of_week = models.CharField(max_length=20, choices=DAY_OF_WEEK_CHOICES, default=DAY_OF_WEEK_ALL)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    seat_category = models.CharField(max_length=20, choices=SEAT_CATEGORY_CHOICES, default=SEAT_CATEGORY_ALL)
    day_type = models.CharField(max_length=20, choices=DAY_TYPE_CHOICES, default=DAY_TYPE_ALL)
    occupancy_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    price_multiplier = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        blank=True,
        null=True,
        validators=[MinValueValidator(0.01)],
    )
    flat_adjustment = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_festival_pricing = models.BooleanField(default=False)
    festival_name = models.CharField(max_length=80, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE_CHOICES, default=ADJUSTMENT_INCREMENT)
    adjustment_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_price_cap = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    max_price_cap = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pricing_rules"
        ordering = ["priority", "id"]
        indexes = [
            models.Index(fields=["vendor", "is_active", "priority"]),
            models.Index(fields=["is_active", "day_of_week", "seat_category"]),
            models.Index(fields=["movie", "hall"]),
        ]

    def clean(self):
        errors = {}
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors["end_date"] = "end_date must be on or after start_date."
        if (
            self.min_price_cap is not None
            and self.max_price_cap is not None
            and self.min_price_cap > self.max_price_cap
        ):
            errors["max_price_cap"] = "max_price_cap must be >= min_price_cap."
        if self.min_price_cap is not None and self.min_price_cap < 0:
            errors["min_price_cap"] = "min_price_cap must be non-negative."
        if self.max_price_cap is not None and self.max_price_cap < 0:
            errors["max_price_cap"] = "max_price_cap must be non-negative."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        owner = f"vendor {self.vendor_id}" if self.vendor_id else "global"
        return f"{owner} - {self.name}"


class ShowBasePrice(models.Model):
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="base_prices")
    seat_category = models.CharField(
        max_length=20,
        choices=PricingRule.SEAT_CATEGORY_CHOICES,
        default=PricingRule.SEAT_CATEGORY_NORMAL,
    )
    base_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "show_base_prices"
        constraints = [
            models.UniqueConstraint(
                fields=["show", "seat_category"],
                name="unique_show_seat_category_base_price",
            )
        ]
        indexes = [
            models.Index(fields=["show", "is_active"]),
            models.Index(fields=["seat_category", "is_active"]),
        ]
        ordering = ["show_id", "seat_category", "id"]

    def __str__(self):
        return f"Show {self.show_id} {self.seat_category} - {self.base_price}"


class VendorCancellationPolicy(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="cancellation_policies")
    screen = models.ForeignKey(
        "Screen",
        on_delete=models.CASCADE,
        related_name="cancellation_policies",
        blank=True,
        null=True,
    )
    allow_customer_cancellation = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    refund_percent_2h_plus = models.DecimalField(max_digits=5, decimal_places=2, default=100)
    refund_percent_1_to_2h = models.DecimalField(max_digits=5, decimal_places=2, default=70)
    refund_percent_less_than_1h = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    note = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendor_cancellation_policies"
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "screen"],
                name="unique_vendor_screen_cancellation_policy",
            )
        ]
        ordering = ["screen_id", "id"]

    def __str__(self):
        scope = f"screen {self.screen_id}" if self.screen_id else "default"
        return f"Cancellation Policy {self.vendor_id} ({scope})"


class HomeSlide(models.Model):
    SLIDE_MOVIE = "MOVIE"
    SLIDE_COLLAB = "COLLAB"
    SLIDE_TYPES = [
        (SLIDE_MOVIE, "Movie"),
        (SLIDE_COLLAB, "Collaboration"),
    ]

    CTA_MOVIE_DETAIL = "MOVIE_DETAIL"
    CTA_BOOK_NOW = "BOOK_NOW"
    CTA_EXTERNAL = "EXTERNAL_LINK"
    CTA_TYPES = [
        (CTA_MOVIE_DETAIL, "Movie Detail"),
        (CTA_BOOK_NOW, "Book Now"),
        (CTA_EXTERNAL, "External Link"),
    ]

    slide_type = models.CharField(max_length=10, choices=SLIDE_TYPES, default=SLIDE_MOVIE)
    movie = models.ForeignKey(
        "Movie", on_delete=models.SET_NULL, related_name="home_slides", null=True, blank=True
    )
    title_override = models.CharField(max_length=200, blank=True, null=True)
    badge_text = models.CharField(max_length=50, blank=True, null=True)
    subtitle = models.CharField(max_length=200, blank=True, null=True)
    description_override = models.TextField(blank=True, null=True)
    background_image = models.ImageField(upload_to="home_slides/", blank=True, null=True)
    cta_text = models.CharField(max_length=50, blank=True, null=True)
    cta_type = models.CharField(max_length=20, choices=CTA_TYPES, default=CTA_MOVIE_DETAIL)
    external_url = models.URLField(blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "home_slides"
        ordering = ["sort_order", "-created_at"]

    def __str__(self):
        label = self.title_override or (self.movie.title if self.movie else "")
        return label or f"Slide {self.pk}"


class Banner(models.Model):
    class BannerType(models.TextChoices):
        MOVIE = "MOVIE", "Movie"
        PROMO = "PROMO", "Promo"

    banner_type = models.CharField(
        max_length=10, choices=BannerType.choices, default=BannerType.PROMO
    )
    movie = models.ForeignKey(
        Movie, on_delete=models.SET_NULL, related_name="banners", null=True, blank=True
    )
    image = models.ImageField(upload_to="banners/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "banners"
        ordering = ["-created_at"]

    def clean(self):
        """Validate banner constraints based on banner type."""
        errors = {}
        if not self.image:
            errors["image"] = "Image is required."
        if self.banner_type == self.BannerType.MOVIE:
            if not self.movie:
                errors["movie"] = "Movie is required for movie banners."
        if self.banner_type == self.BannerType.PROMO and self.movie:
            errors["movie"] = "Movie must be empty for promo banners."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        if self.banner_type == self.BannerType.MOVIE and self.movie:
            return f"{self.movie.title} Banner"
        return f"Banner {self.pk}"


class CollabDetails(models.Model):
    slide = models.OneToOneField(
        HomeSlide, related_name="collab_details", on_delete=models.CASCADE
    )
    partner_name = models.CharField(max_length=100)
    partner_logo = models.ImageField(upload_to="collab_logos/")
    partner_logo_2 = models.ImageField(upload_to="collab_logos/", blank=True, null=True)
    headline = models.CharField(max_length=200)
    offer_text = models.CharField(max_length=200)
    promo_code_label = models.CharField(max_length=100)
    promo_code = models.CharField(max_length=50)
    terms_text = models.CharField(max_length=200)
    primary_color = models.CharField(max_length=20, blank=True, null=True)
    secondary_color = models.CharField(max_length=20, blank=True, null=True)
    right_badge_text = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "collab_details"

    def __str__(self):
        return self.partner_name


class Collaborator(models.Model):
    name = models.CharField(max_length=100)
    logo = models.ImageField(upload_to="collaborators/")
    website_url = models.URLField(blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "collaborators"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

class OTPVerification(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = "otp_verifications"

    def __str__(self):
        return f"OTP for {self.email} - {self.otp} ({'verified' if self.is_verified else 'pending'})"


class Ticket(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    LEGACY_PAYMENT_STATUS_ALIASES = {
        "SUCCESS": PaymentStatus.PAID,
        "COMPLETED": PaymentStatus.PAID,
        "CONFIRMED": PaymentStatus.PAID,
    }

    PAYMENT_STATUS_TRANSITIONS = {
        PaymentStatus.PENDING: {PaymentStatus.PAID, PaymentStatus.FAILED},
        PaymentStatus.PAID: {PaymentStatus.REFUNDED},
        PaymentStatus.FAILED: set(),
        PaymentStatus.REFUNDED: set(),
    }

    ticket_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    reference = models.CharField(max_length=20, unique=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="tickets",
        blank=True,
        null=True,
    )
    show = models.ForeignKey(
        Show,
        on_delete=models.SET_NULL,
        related_name="tickets",
        blank=True,
        null=True,
    )
    seats = models.CharField(max_length=255, blank=True, null=True)
    show_datetime = models.DateTimeField(blank=True, null=True)
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    token_expires_at = models.DateTimeField(blank=True, null=True)
    is_used = models.BooleanField(default=False)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tickets"

    @classmethod
    def normalize_payment_status(cls, value: str | None) -> str:
        return _normalize_choice_value(
            value,
            cls.PaymentStatus.PENDING,
            set(cls.PaymentStatus.values),
            cls.LEGACY_PAYMENT_STATUS_ALIASES,
        )

    def save(self, *args, **kwargs):
        normalized_status = self.normalize_payment_status(self.payment_status)
        if self.pk:
            current_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("payment_status", flat=True)
                .first()
            )
            _validate_status_transition(
                self.__class__.__name__,
                "payment_status",
                self.normalize_payment_status(current_status),
                normalized_status,
                self.PAYMENT_STATUS_TRANSITIONS,
            )
        self.payment_status = normalized_status
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket {self.reference}"


class TicketValidationScan(models.Model):
    STATUS_VALID = "VALID"
    STATUS_DUPLICATE = "DUPLICATE"
    STATUS_INVALID = "INVALID"
    STATUS_FRAUD = "FRAUD"
    STATUS_CHOICES = [
        (STATUS_VALID, "Valid"),
        (STATUS_DUPLICATE, "Duplicate"),
        (STATUS_INVALID, "Invalid"),
        (STATUS_FRAUD, "Fraud Suspected"),
    ]

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.SET_NULL,
        related_name="validation_scans",
        blank=True,
        null=True,
    )
    booking = models.ForeignKey(
        "Booking",
        on_delete=models.SET_NULL,
        related_name="ticket_validation_scans",
        blank=True,
        null=True,
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="ticket_validation_scans",
    )
    scanned_by = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        related_name="performed_ticket_scans",
        blank=True,
        null=True,
    )
    vendor_staff = models.ForeignKey(
        "VendorStaff",
        on_delete=models.SET_NULL,
        related_name="ticket_validation_scans",
        blank=True,
        null=True,
    )
    reference = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    reason = models.CharField(max_length=255, blank=True, null=True)
    fraud_score = models.PositiveIntegerField(default=0)
    source_ip = models.CharField(max_length=45, blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_validation_scans"
        ordering = ["-scanned_at", "-id"]

    def __str__(self):
        return f"{self.reference} ({self.status})"


class MovieGenre(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "movie_genres"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Generate a slug for the genre if missing."""
        if self.name and not self.slug:
            self.slug = _unique_slugify(self, self.name, "slug", 100)
        super().save(*args, **kwargs)


class MovieMovieGenre(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="movie_genres")
    genre = models.ForeignKey(MovieGenre, on_delete=models.CASCADE, related_name="movie_assignments")
    assigned_date = models.DateTimeField(blank=True, null=True)
    assigned_by = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, default="Active")

    class Meta:
        db_table = "movie_movie_genres"
        unique_together = ("movie", "genre")

    def __str__(self):
        return f"{self.movie.title} - {self.genre.name}"


class Person(models.Model):
    full_name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=180, unique=True, blank=True, null=True)
    photo = models.ImageField(upload_to="people/", blank=True, null=True)
    photo_url = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    nationality = models.CharField(max_length=80, blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)
    imdb = models.URLField(blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "people"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        """Generate a slug for the person if missing."""
        if self.full_name and not self.slug:
            self.slug = _unique_slugify(self, self.full_name, "slug", 180)
        super().save(*args, **kwargs)


class MovieCredit(models.Model):
    ROLE_CAST = "CAST"
    ROLE_CREW = "CREW"
    ROLE_CHOICES = [
        (ROLE_CAST, "Cast"),
        (ROLE_CREW, "Crew"),
    ]

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="credits")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="credits")
    role_type = models.CharField(max_length=10, choices=ROLE_CHOICES)
    character_name = models.CharField(max_length=120, blank=True, null=True)
    job_title = models.CharField(max_length=120, blank=True, null=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "movie_credits"
        ordering = ["position", "id"]

    def __str__(self):
        label = self.character_name or self.job_title or self.role_type
        return f"{self.movie.title} - {self.person.full_name} ({label})"


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True, null=True)
    is_approved = models.BooleanField(default=True)
    review_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reviews"
        constraints = [
            models.UniqueConstraint(fields=["movie", "user"], name="unique_movie_review")
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.movie_id} ({self.rating})"


class Screen(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="screens")
    screen_number = models.CharField(max_length=20)
    screen_type = models.CharField(max_length=40, blank=True, null=True)
    capacity = models.PositiveIntegerField(blank=True, null=True)
    normal_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    executive_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    premium_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    vip_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, default="Active")

    class Meta:
        db_table = "screens"
        unique_together = ("vendor", "screen_number")

    def __str__(self):
        return f"{self.vendor.name} - {self.screen_number}"


class Seat(models.Model):
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name="seats")
    seat_number = models.CharField(max_length=10)
    row_label = models.CharField(max_length=10, blank=True, null=True)
    seat_type = models.CharField(max_length=30, blank=True, null=True)
    is_accessible = models.BooleanField(default=False)

    class Meta:
        db_table = "seats"
        unique_together = ("screen", "row_label", "seat_number")

    def __str__(self):
        label = f"{self.row_label}{self.seat_number}" if self.row_label else self.seat_number
        return f"{self.screen_id} - {label}"


class Showtime(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="showtimes")
    screen = models.ForeignKey(Screen, on_delete=models.CASCADE, related_name="showtimes")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(blank=True, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)

    class Meta:
        db_table = "showtimes"
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "start_time"],
                name="unique_showtime_per_screen_start",
            )
        ]

    def __str__(self):
        return f"{self.movie.title} ({self.start_time})"


class SeatAvailability(models.Model):
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name="availabilities")
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="seat_availability")
    seat_status = models.CharField(max_length=20, default="Available")
    last_updated = models.DateTimeField(auto_now=True)
    locked_until = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "seat_availability"
        unique_together = ("seat", "showtime")

    def __str__(self):
        return f"{self.seat_id} @ {self.showtime_id} ({self.seat_status})"


class Coupon(models.Model):
    DISCOUNT_TYPE_PERCENTAGE = "PERCENTAGE"
    DISCOUNT_TYPE_FIXED = "FIXED"
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_TYPE_PERCENTAGE, "Percentage"),
        (DISCOUNT_TYPE_FIXED, "Fixed"),
    ]

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_booking_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    expiry_date = models.DateTimeField(blank=True, null=True)
    usage_limit = models.PositiveIntegerField(blank=True, null=True)
    usage_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "coupons"
        ordering = ["-created_at", "-id"]

    def clean(self):
        errors = {}
        if self.discount_value is None or self.discount_value < 0:
            errors["discount_value"] = "Discount value must be non-negative."
        if (
            self.discount_type == self.DISCOUNT_TYPE_PERCENTAGE
            and self.discount_value is not None
            and self.discount_value > 100
        ):
            errors["discount_value"] = "Percentage discount cannot exceed 100."
        if self.usage_limit is not None and self.usage_count > self.usage_limit:
            errors["usage_limit"] = "Usage count cannot be greater than usage limit."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.code:
            self.code = str(self.code).strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class Reward(models.Model):
    TYPE_DISCOUNT = "DISCOUNT"
    TYPE_FREE_TICKET = "FREE_TICKET"
    TYPE_CASHBACK = "CASHBACK"
    TYPE_CHOICES = [
        (TYPE_DISCOUNT, "Discount"),
        (TYPE_FREE_TICKET, "Free Ticket"),
        (TYPE_CASHBACK, "Cashback"),
    ]

    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, null=True)
    points_required = models.PositiveIntegerField(default=0)
    reward_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_DISCOUNT)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        related_name="rewards",
        blank=True,
        null=True,
    )
    stock_limit = models.PositiveIntegerField(blank=True, null=True)
    redeemed_count = models.PositiveIntegerField(default=0)
    expiry_date = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_stackable_with_coupon = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rewards"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["is_active", "expiry_date"]),
            models.Index(fields=["vendor", "is_active"]),
            models.Index(fields=["points_required"]),
        ]

    def __str__(self):
        return self.title


class SubscriptionPlan(models.Model):
    TIER_SILVER = "SILVER"
    TIER_GOLD = "GOLD"
    TIER_PLATINUM = "PLATINUM"
    TIER_CHOICES = [
        (TIER_SILVER, "Silver"),
        (TIER_GOLD, "Gold"),
        (TIER_PLATINUM, "Platinum"),
    ]

    DISCOUNT_TYPE_NONE = "NONE"
    DISCOUNT_TYPE_PERCENTAGE = "PERCENTAGE"
    DISCOUNT_TYPE_FIXED = "FIXED"
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_TYPE_NONE, "None"),
        (DISCOUNT_TYPE_PERCENTAGE, "Percentage"),
        (DISCOUNT_TYPE_FIXED, "Fixed"),
    ]

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="subscription_plans",
        blank=True,
        null=True,
    )
    code = models.CharField(max_length=40, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default=TIER_SILVER)
    duration_days = models.PositiveIntegerField(default=30)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="NPR")
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default=DISCOUNT_TYPE_NONE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    free_tickets_total = models.PositiveIntegerField(default=0)
    early_access_hours = models.PositiveIntegerField(default=0)
    special_pricing_percent = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    subscription_only_access = models.BooleanField(default=False)
    allow_multiple_active = models.BooleanField(default=False)
    is_stackable_with_coupon = models.BooleanField(default=True)
    is_stackable_with_loyalty = models.BooleanField(default=True)
    is_stackable_with_referral_wallet = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    valid_from = models.DateTimeField(blank=True, null=True)
    valid_until = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_plans"
        ordering = ["priority", "-created_at", "-id"]
        indexes = [
            models.Index(fields=["vendor", "is_active"]),
            models.Index(fields=["tier", "is_active"]),
            models.Index(fields=["is_public", "is_active"]),
            models.Index(fields=["valid_from", "valid_until"]),
        ]

    def clean(self):
        errors = {}
        if self.discount_value is None or self.discount_value < 0:
            errors["discount_value"] = "Discount value must be non-negative."
        if (
            self.discount_type == self.DISCOUNT_TYPE_PERCENTAGE
            and self.discount_value is not None
            and self.discount_value > 100
        ):
            errors["discount_value"] = "Percentage discount cannot exceed 100."
        if self.max_discount_amount is not None and self.max_discount_amount < 0:
            errors["max_discount_amount"] = "Max discount amount must be non-negative."
        if self.special_pricing_percent is not None and self.special_pricing_percent < 0:
            errors["special_pricing_percent"] = "Special pricing percent must be non-negative."
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            errors["valid_until"] = "valid_until must be after valid_from."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.code:
            self.code = str(self.code).strip().upper()
        if self.currency:
            self.currency = str(self.currency).strip().upper()[:10]
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        scope = f"Vendor:{self.vendor_id}" if self.vendor_id else "Global"
        return f"{self.name} ({scope})"


class UserSubscription(models.Model):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_PENDING_PAYMENT = "PENDING_PAYMENT"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_PENDING_PAYMENT, "Pending Payment"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        related_name="user_subscriptions",
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        related_name="user_subscriptions",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    start_at = models.DateTimeField(default=timezone.now)
    end_at = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    upgraded_from = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="upgraded_children",
        blank=True,
        null=True,
    )
    remaining_free_tickets = models.PositiveIntegerField(default=0)
    used_free_tickets = models.PositiveIntegerField(default=0)
    total_discount_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_subscriptions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status", "end_at"]),
            models.Index(fields=["vendor", "status", "end_at"]),
            models.Index(fields=["plan", "status"]),
            models.Index(fields=["status", "end_at"]),
        ]

    def __str__(self):
        return f"UserSubscription {self.id} ({self.status})"


class SubscriptionTransaction(models.Model):
    TYPE_PURCHASE = "PURCHASE"
    TYPE_RENEWAL = "RENEWAL"
    TYPE_UPGRADE = "UPGRADE"
    TYPE_PRORATION = "PRORATION"
    TYPE_DISCOUNT_APPLIED = "DISCOUNT_APPLIED"
    TYPE_FREE_TICKET_APPLIED = "FREE_TICKET_APPLIED"
    TYPE_REFUND = "REFUND"
    TYPE_CANCEL = "CANCEL"
    TYPE_EXPIRE = "EXPIRE"
    TYPE_CHOICES = [
        (TYPE_PURCHASE, "Purchase"),
        (TYPE_RENEWAL, "Renewal"),
        (TYPE_UPGRADE, "Upgrade"),
        (TYPE_PRORATION, "Proration"),
        (TYPE_DISCOUNT_APPLIED, "Discount Applied"),
        (TYPE_FREE_TICKET_APPLIED, "Free Ticket Applied"),
        (TYPE_REFUND, "Refund"),
        (TYPE_CANCEL, "Cancel"),
        (TYPE_EXPIRE, "Expire"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscription_transactions")
    subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        related_name="transactions",
        blank=True,
        null=True,
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        related_name="transactions",
        blank=True,
        null=True,
    )
    booking = models.ForeignKey(
        "Booking",
        on_delete=models.SET_NULL,
        related_name="subscription_transactions",
        blank=True,
        null=True,
    )
    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_tickets_used = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=10, default="NPR")
    reference_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscription_transactions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["subscription", "created_at"]),
            models.Index(fields=["booking", "transaction_type"]),
            models.Index(fields=["transaction_type", "status"]),
        ]

    def save(self, *args, **kwargs):
        if self.currency:
            self.currency = str(self.currency).strip().upper()[:10]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"SubscriptionTransaction {self.id} ({self.transaction_type})"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"

    LEGACY_STATUS_ALIASES = {
        "PENDING": Status.PENDING,
        "CONFIRMED": Status.CONFIRMED,
        "CANCELLED": Status.CANCELLED,
        "CANCELED": Status.CANCELLED,
    }

    FRAUD_LEVEL_LOW = "LOW"
    FRAUD_LEVEL_MEDIUM = "MEDIUM"
    FRAUD_LEVEL_HIGH = "HIGH"
    FRAUD_LEVEL_CRITICAL = "CRITICAL"
    FRAUD_LEVEL_CHOICES = [
        (FRAUD_LEVEL_LOW, "Low"),
        (FRAUD_LEVEL_MEDIUM, "Medium"),
        (FRAUD_LEVEL_HIGH, "High"),
        (FRAUD_LEVEL_CRITICAL, "Critical"),
    ]

    STATUS_TRANSITIONS = {
        Status.PENDING: {Status.CONFIRMED, Status.CANCELLED},
        Status.CONFIRMED: {Status.CANCELLED},
        Status.CANCELLED: set(),
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="bookings")
    booking_date = models.DateTimeField(auto_now_add=True)
    booking_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    admin_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vendor_earning = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_percent_applied = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        related_name="bookings",
        blank=True,
        null=True,
    )
    vendor_promo_code = models.ForeignKey(
        "VendorPromoCode",
        on_delete=models.SET_NULL,
        related_name="bookings",
        blank=True,
        null=True,
    )
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loyalty_points_redeemed = models.PositiveIntegerField(default=0)
    loyalty_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subscription_plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        related_name="bookings",
        blank=True,
        null=True,
    )
    user_subscription = models.ForeignKey(
        UserSubscription,
        on_delete=models.SET_NULL,
        related_name="bookings",
        blank=True,
        null=True,
    )
    subscription_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subscription_free_tickets_used = models.PositiveIntegerField(default=0)
    referral_wallet_used_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    referral_wallet_refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fraud_score = models.PositiveIntegerField(default=0)
    fraud_level = models.CharField(max_length=12, choices=FRAUD_LEVEL_CHOICES, default=FRAUD_LEVEL_LOW)
    fraud_signals = models.JSONField(default=list, blank=True)
    source_ip = models.CharField(max_length=45, blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    reward_redemption = models.ForeignKey(
        "RewardRedemption",
        on_delete=models.SET_NULL,
        related_name="booking_reward_redemptions",
        blank=True,
        null=True,
    )

    class Meta:
        db_table = "bookings"
        indexes = [
            models.Index(fields=["booking_date"]),
            models.Index(fields=["booking_status", "booking_date"]),
        ]

    @classmethod
    def normalize_booking_status(cls, value: str | None) -> str:
        return _normalize_choice_value(
            value,
            cls.Status.PENDING,
            set(cls.Status.values),
            cls.LEGACY_STATUS_ALIASES,
        )

    def save(self, *args, **kwargs):
        normalized_status = self.normalize_booking_status(self.booking_status)
        if self.pk:
            current_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("booking_status", flat=True)
                .first()
            )
            _validate_status_transition(
                self.__class__.__name__,
                "booking_status",
                self.normalize_booking_status(current_status),
                normalized_status,
                self.STATUS_TRANSITIONS,
            )
        self.booking_status = normalized_status
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Booking {self.pk} ({self.booking_status})"


class GroupBookingSession(models.Model):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_PARTIALLY_PAID = "PARTIALLY_PAID"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_PARTIALLY_PAID, "Partially Paid"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
    ]

    SPLIT_EQUAL = "EQUAL"
    SPLIT_MANUAL = "MANUAL"
    SPLIT_SEAT_BASED = "SEAT_BASED"
    SPLIT_MODE_CHOICES = [
        (SPLIT_EQUAL, "Equal Split"),
        (SPLIT_MANUAL, "Manual Split"),
        (SPLIT_SEAT_BASED, "Seat Based"),
    ]

    host = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="group_booking_sessions_hosted",
    )
    show = models.ForeignKey(
        Show,
        on_delete=models.CASCADE,
        related_name="group_booking_sessions",
    )
    showtime = models.ForeignKey(
        Showtime,
        on_delete=models.CASCADE,
        related_name="group_booking_sessions",
    )
    invite_code = models.CharField(max_length=24, unique=True, db_index=True)
    split_mode = models.CharField(
        max_length=20,
        choices=SPLIT_MODE_CHOICES,
        default=SPLIT_EQUAL,
    )
    selected_seats = models.JSONField(default=list, blank=True)
    seat_price_map = models.JSONField(default=dict, blank=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    expires_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "group_booking_sessions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["host", "status"]),
            models.Index(fields=["showtime", "status"]),
        ]

    def __str__(self):
        return f"GroupBookingSession {self.id} ({self.status})"


class GroupParticipant(models.Model):
    PAYMENT_PENDING = "PENDING"
    PAYMENT_PAID = "PAID"
    PAYMENT_FAILED = "FAILED"
    PAYMENT_LEFT = "LEFT"
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_FAILED, "Failed"),
        (PAYMENT_LEFT, "Left"),
    ]

    session = models.ForeignKey(
        GroupBookingSession,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="group_booking_participations",
    )
    is_host = models.BooleanField(default=False)
    selected_seats = models.JSONField(default=list, blank=True)
    amount_to_pay = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PENDING,
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    left_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "group_booking_participants"
        ordering = ["joined_at", "id"]
        unique_together = ("session", "user")
        indexes = [
            models.Index(fields=["session", "payment_status"]),
            models.Index(fields=["user", "payment_status"]),
        ]

    def __str__(self):
        return f"GroupParticipant {self.session_id}:{self.user_id}"


class GroupPayment(models.Model):
    STATUS_INITIATED = "INITIATED"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_INITIATED, "Initiated"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    session = models.ForeignKey(
        GroupBookingSession,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    participant = models.ForeignKey(
        GroupParticipant,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="group_payments",
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="group_payments",
        blank=True,
        null=True,
    )
    payment_method = models.CharField(max_length=30, default="ESEWA")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INITIATED)
    transaction_id = models.CharField(max_length=120, unique=True, blank=True, null=True)
    provider_reference = models.CharField(max_length=120, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "group_payments"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["session", "status"]),
            models.Index(fields=["participant", "status"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"GroupPayment {self.id} ({self.status})"


class Referral(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_REWARDED = "REWARDED"
    STATUS_REJECTED = "REJECTED"
    STATUS_REVERSED = "REVERSED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_REWARDED, "Rewarded"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_REVERSED, "Reversed"),
        (STATUS_EXPIRED, "Expired"),
    ]

    referrer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="referrals_sent",
    )
    referred_user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="referral",
    )
    referral_code = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    rejection_reason = models.CharField(max_length=255, blank=True, null=True)
    reversal_reason = models.CharField(max_length=255, blank=True, null=True)
    signup_ip_address = models.CharField(max_length=45, blank=True, null=True)
    signup_user_agent = models.CharField(max_length=255, blank=True, null=True)
    signup_device_fingerprint = models.CharField(max_length=128, blank=True, null=True)
    reward_trigger_booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="triggered_referrals",
        blank=True,
        null=True,
    )
    rewarded_at = models.DateTimeField(blank=True, null=True)
    reversed_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "referrals"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["referral_code"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["referrer", "status"]),
            models.Index(fields=["referred_user", "status"]),
            models.Index(fields=["expires_at", "status"]),
        ]

    def __str__(self):
        return f"Referral {self.id} ({self.status})"


class RewardRedemption(models.Model):
    STATUS_USED = "USED"
    STATUS_UNUSED = "UNUSED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_USED, "Used"),
        (STATUS_UNUSED, "Unused"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reward_redemptions")
    reward = models.ForeignKey(Reward, on_delete=models.CASCADE, related_name="redemptions")
    points_used = models.PositiveIntegerField(default=0)
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="reward_redemptions",
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNUSED)
    redemption_code = models.CharField(max_length=40, unique=True, blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    used_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reward_redemptions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["reward", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self.redemption_code:
            self.redemption_code = uuid.uuid4().hex[:16].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"RewardRedemption {self.id} ({self.status})"


class BookingSeat(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="booking_seats")
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="booking_seats")
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name="booking_seats")
    seat_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    discount_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_seats"
        unique_together = ("booking", "seat")
        constraints = [
            models.UniqueConstraint(
                fields=["showtime", "seat"],
                name="unique_bookingseat_per_showtime_seat",
            )
        ]

    def __str__(self):
        return f"{self.booking_id} - {self.seat_id}"


class BookingItem(BookingSeat):
    """Compatibility alias for seat-level booking items."""

    class Meta:
        proxy = True
        verbose_name = "Booking Item"
        verbose_name_plural = "Booking Items"


class FoodItem(models.Model):
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="food_items",
        null=True,
        blank=True,
    )
    hall = models.CharField(max_length=80, blank=True, null=True)
    item_name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, blank=True, null=True)
    is_veg = models.BooleanField(default=True)
    item_image = models.ImageField(upload_to="food_items/", blank=True, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    track_inventory = models.BooleanField(default=False)
    stock_quantity = models.PositiveIntegerField(default=0)
    sold_out_threshold = models.PositiveIntegerField(default=0)
    sold_out_at = models.DateTimeField(blank=True, null=True)
    is_available = models.BooleanField(default=True)

    class Meta:
        db_table = "food_items"

    def __str__(self):
        return self.item_name


class Combo(models.Model):
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="combos",
    )
    hall = models.CharField(max_length=80, blank=True, null=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    combo_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "combos"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.name


class ComboItem(models.Model):
    combo = models.ForeignKey(Combo, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="combo_items")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "combo_items"
        unique_together = ("combo", "food_item")

    def __str__(self):
        return f"{self.combo_id} - {self.food_item_id}"


class Order(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="orders")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="food_orders")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="food_orders")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Order {self.id} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    food_item = models.ForeignKey(
        FoodItem,
        on_delete=models.SET_NULL,
        related_name="order_items",
        blank=True,
        null=True,
    )
    combo = models.ForeignKey(
        Combo,
        on_delete=models.SET_NULL,
        related_name="order_items",
        blank=True,
        null=True,
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "order_items"

    def __str__(self):
        return f"OrderItem {self.id} -> {self.order_id}"


class BookingFoodItem(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="food_items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="booking_items")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "booking_food_items"
        unique_together = ("booking", "food_item")

    def __str__(self):
        return f"{self.booking_id} - {self.food_item_id}"


class PrivateScreeningRequest(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_REVIEWED = "REVIEWED"
    STATUS_COUNTERED = "COUNTERED"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_REJECTED = "REJECTED"
    STATUS_INVOICED = "INVOICED"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_COUNTERED, "Counter Offered"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_INVOICED, "Invoiced"),
        (STATUS_COMPLETED, "Completed"),
    ]

    requester_type = models.CharField(max_length=30, blank=True, null=True)
    organization_name = models.CharField(max_length=160)
    contact_person = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    preferred_date = models.DateField(blank=True, null=True)
    preferred_start_time = models.TimeField(blank=True, null=True)
    attendee_count = models.PositiveIntegerField(default=1)
    preferred_movie_title = models.CharField(max_length=200, blank=True, null=True)
    hall_preference = models.CharField(max_length=80, blank=True, null=True)
    special_requirements = models.TextField(blank=True, null=True)
    estimated_budget = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="private_screening_requests",
        blank=True,
        null=True,
    )
    vendor_notes = models.TextField(blank=True, null=True)
    quoted_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    counter_offer_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    invoice_number = models.CharField(max_length=40, blank=True, null=True)
    invoice_notes = models.TextField(blank=True, null=True)
    invoiced_at = models.DateTimeField(blank=True, null=True)
    finalized_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "private_screening_requests"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.organization_name} ({self.status})"


class BulkTicketBatch(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_GENERATED = "GENERATED"
    STATUS_EXPORTED = "EXPORTED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_GENERATED, "Generated"),
        (STATUS_EXPORTED, "Exported"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="bulk_ticket_batches")
    corporate_name = models.CharField(max_length=160)
    contact_person = models.CharField(max_length=120, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    movie_title = models.CharField(max_length=200, blank=True, null=True)
    hall = models.CharField(max_length=80, blank=True, null=True)
    show_date = models.DateField(blank=True, null=True)
    show_time = models.TimeField(blank=True, null=True)
    valid_until = models.DateField(blank=True, null=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_GENERATED)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bulk_ticket_batches"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.corporate_name} ({self.status})"


class BulkTicketItem(models.Model):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_REDEEMED = "REDEEMED"
    STATUS_VOID = "VOID"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_REDEEMED, "Redeemed"),
        (STATUS_VOID, "Void"),
    ]

    batch = models.ForeignKey(BulkTicketBatch, on_delete=models.CASCADE, related_name="tickets")
    ticket = models.OneToOneField(
        Ticket,
        on_delete=models.CASCADE,
        related_name="bulk_ticket_item",
    )
    employee_code = models.CharField(max_length=80, blank=True, null=True)
    recipient_name = models.CharField(max_length=120, blank=True, null=True)
    recipient_email = models.EmailField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    redeemed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bulk_ticket_items"
        ordering = ["id"]

    def __str__(self):
        return f"{self.batch_id} - {self.ticket.reference}"


class VendorPromoCode(models.Model):
    DISCOUNT_TYPE_PERCENTAGE = "PERCENTAGE"
    DISCOUNT_TYPE_FIXED = "FIXED"
    DISCOUNT_TYPE_BOGO = "BOGO"
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_TYPE_PERCENTAGE, "Percentage"),
        (DISCOUNT_TYPE_FIXED, "Fixed"),
        (DISCOUNT_TYPE_BOGO, "BOGO"),
    ]

    SEAT_CATEGORY_ALL = "ALL"
    SEAT_CATEGORY_NORMAL = "NORMAL"
    SEAT_CATEGORY_EXECUTIVE = "EXECUTIVE"
    SEAT_CATEGORY_PREMIUM = "PREMIUM"
    SEAT_CATEGORY_VIP = "VIP"
    SEAT_CATEGORY_CHOICES = [
        (SEAT_CATEGORY_ALL, "All Categories"),
        (SEAT_CATEGORY_NORMAL, "Normal"),
        (SEAT_CATEGORY_EXECUTIVE, "Executive"),
        (SEAT_CATEGORY_PREMIUM, "Premium"),
        (SEAT_CATEGORY_VIP, "VIP"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="promo_codes")
    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True, null=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_booking_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    usage_limit = models.PositiveIntegerField(blank=True, null=True)
    usage_count = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveIntegerField(blank=True, null=True)
    seat_category_scope = models.CharField(
        max_length=20,
        choices=SEAT_CATEGORY_CHOICES,
        default=SEAT_CATEGORY_ALL,
    )
    requires_student = models.BooleanField(default=False)
    allowed_weekdays = models.CharField(max_length=64, blank=True, null=True)
    valid_from = models.DateTimeField(blank=True, null=True)
    valid_until = models.DateTimeField(blank=True, null=True)
    is_flash_sale = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendor_promo_codes"
        ordering = ["-created_at", "-id"]

    def clean(self):
        errors = {}
        if self.discount_value is None or self.discount_value < 0:
            errors["discount_value"] = "Discount value must be non-negative."
        if self.discount_type == self.DISCOUNT_TYPE_PERCENTAGE and self.discount_value > 100:
            errors["discount_value"] = "Percentage discount cannot exceed 100."
        if self.usage_limit is not None and self.usage_count > self.usage_limit:
            errors["usage_limit"] = "Usage count cannot exceed usage limit."
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            errors["valid_until"] = "valid_until must be after valid_from."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.code:
            self.code = str(self.code).strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} ({self.vendor_id})"


class VendorOffer(models.Model):
    OFFER_TYPE_PROMO = "PROMO"
    OFFER_TYPE_BUNDLE = "BUNDLE"
    OFFER_TYPE_PERK = "PERK"
    OFFER_TYPE_LOYALTY = "LOYALTY"
    OFFER_TYPE_CHOICES = [
        (OFFER_TYPE_PROMO, "Promo"),
        (OFFER_TYPE_BUNDLE, "Bundle"),
        (OFFER_TYPE_PERK, "Perk"),
        (OFFER_TYPE_LOYALTY, "Loyalty"),
    ]

    DISCOUNT_TYPE_NONE = "NONE"
    DISCOUNT_TYPE_PERCENTAGE = "PERCENTAGE"
    DISCOUNT_TYPE_FIXED = "FIXED"
    DISCOUNT_TYPE_CHOICES = [
        (DISCOUNT_TYPE_NONE, "None"),
        (DISCOUNT_TYPE_PERCENTAGE, "Percentage"),
        (DISCOUNT_TYPE_FIXED, "Fixed"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="offers")
    title = models.CharField(max_length=140)
    code = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    offer_type = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES, default=OFFER_TYPE_PROMO)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default=DISCOUNT_TYPE_NONE)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_booking_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    allow_loyalty_redemption = models.BooleanField(default=True)
    subscriber_perk_text = models.CharField(max_length=200, blank=True, null=True)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendor_offers"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["vendor", "is_active"]),
            models.Index(fields=["offer_type", "is_active"]),
            models.Index(fields=["starts_at", "ends_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "code"],
                condition=models.Q(code__isnull=False),
                name="unique_vendor_offer_code_when_present",
            )
        ]

    def clean(self):
        errors = {}
        if self.discount_value is None or self.discount_value < 0:
            errors["discount_value"] = "Discount value must be non-negative."
        if self.min_booking_amount is not None and self.min_booking_amount < 0:
            errors["min_booking_amount"] = "Minimum booking amount must be non-negative."
        if (
            self.discount_type == self.DISCOUNT_TYPE_PERCENTAGE
            and self.discount_value is not None
            and self.discount_value > 100
        ):
            errors["discount_value"] = "Percentage discount cannot exceed 100."
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            errors["ends_at"] = "ends_at must be after starts_at."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.code:
            self.code = str(self.code).strip().upper()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.vendor_id})"


class VendorCampaign(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_SCHEDULED = "SCHEDULED"
    STATUS_RUNNING = "RUNNING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
    ]

    CHANNEL_PUSH = "PUSH"
    CHANNEL_SMS = "SMS"
    CHANNEL_BOTH = "BOTH"
    CHANNEL_CHOICES = [
        (CHANNEL_PUSH, "Push"),
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_BOTH, "Push + SMS"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField(max_length=140)
    message_template = models.TextField()
    delivery_channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default=CHANNEL_BOTH)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    target_movie = models.ForeignKey(
        Movie,
        on_delete=models.SET_NULL,
        related_name="campaigns_targeting_movie",
        blank=True,
        null=True,
    )
    recommended_movie = models.ForeignKey(
        Movie,
        on_delete=models.SET_NULL,
        related_name="campaigns_recommending_movie",
        blank=True,
        null=True,
    )
    promo_code = models.ForeignKey(
        VendorPromoCode,
        on_delete=models.SET_NULL,
        related_name="campaigns",
        blank=True,
        null=True,
    )
    include_past_attendees_only = models.BooleanField(default=True)
    min_days_since_booking = models.PositiveIntegerField(default=0)
    scheduled_at = models.DateTimeField(blank=True, null=True)
    last_run_at = models.DateTimeField(blank=True, null=True)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vendor_campaigns"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.name} ({self.vendor_id})"


class VendorCampaignDispatch(models.Model):
    STATUS_SENT = "SENT"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    CHANNEL_PUSH = "PUSH"
    CHANNEL_SMS = "SMS"
    CHANNEL_CHOICES = [
        (CHANNEL_PUSH, "Push"),
        (CHANNEL_SMS, "SMS"),
    ]

    campaign = models.ForeignKey(VendorCampaign, on_delete=models.CASCADE, related_name="dispatches")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name="campaign_dispatches")
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    contact = models.CharField(max_length=120, blank=True, null=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SENT)
    error_message = models.CharField(max_length=255, blank=True, null=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vendor_campaign_dispatches"
        ordering = ["-sent_at", "-id"]

    def __str__(self):
        return f"{self.campaign_id} - {self.channel} - {self.status}"


class Notification(models.Model):
    CHANNEL_IN_APP = "IN_APP"
    CHANNEL_EMAIL = "EMAIL"
    CHANNEL_BOTH = "BOTH"
    CHANNEL_CHOICES = [
        (CHANNEL_IN_APP, "In App"),
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_BOTH, "In App + Email"),
    ]

    EVENT_NEW_BOOKING = "NEW_BOOKING"
    EVENT_PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    EVENT_SHOW_UPDATE = "SHOW_UPDATE"
    EVENT_MARKETING_CAMPAIGN = "MARKETING_CAMPAIGN"
    EVENT_BOOKING_CANCEL_REQUEST = "BOOKING_CANCEL_REQUEST"
    EVENT_BOOKING_RESUME_PENDING = "BOOKING_RESUME_PENDING"
    EVENT_BOOKING_CANCELLED = "BOOKING_CANCELLED"
    EVENT_REFUND_PROCESSED = "REFUND_PROCESSED"
    EVENT_SUBSCRIPTION_EXPIRING = "SUBSCRIPTION_EXPIRING"
    EVENT_SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED"
    EVENT_CHOICES = [
        (EVENT_NEW_BOOKING, "New Booking"),
        (EVENT_PAYMENT_SUCCESS, "Payment Success"),
        (EVENT_SHOW_UPDATE, "Show Update"),
        (EVENT_MARKETING_CAMPAIGN, "Marketing Campaign"),
        (EVENT_BOOKING_CANCEL_REQUEST, "Booking Cancel Request"),
        (EVENT_BOOKING_RESUME_PENDING, "Booking Resume Pending"),
        (EVENT_BOOKING_CANCELLED, "Booking Cancelled"),
        (EVENT_REFUND_PROCESSED, "Refund Processed"),
        (EVENT_SUBSCRIPTION_EXPIRING, "Subscription Expiring"),
        (EVENT_SUBSCRIPTION_EXPIRED, "Subscription Expired"),
    ]

    ROLE_ADMIN = "admin"
    ROLE_VENDOR = "vendor"
    ROLE_CUSTOMER = "customer"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_VENDOR, "Vendor"),
        (ROLE_CUSTOMER, "Customer"),
    ]

    recipient_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    recipient_id = models.PositiveIntegerField()
    recipient_email = models.EmailField(blank=True, null=True)
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_IN_APP)
    title = models.CharField(max_length=180)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.recipient_role}:{self.recipient_id} - {self.event_type}"


class BackgroundJob(models.Model):
    TYPE_NOTIFICATION_EMAIL = "NOTIFICATION_EMAIL"
    TYPE_NOTIFICATION_EMAIL_RETRY = "NOTIFICATION_EMAIL_RETRY"
    TYPE_ANALYTICS_MONITOR_EXPORT = "ANALYTICS_MONITOR_EXPORT"
    TYPE_GATEWAY_STATUS_CHECK = "GATEWAY_STATUS_CHECK"
    TYPE_FINANCIAL_SUMMARY_ROLLUP = "FINANCIAL_SUMMARY_ROLLUP"
    TYPE_WITHDRAWAL_SETTLEMENT = "WITHDRAWAL_SETTLEMENT"
    TYPE_CHOICES = [
        (TYPE_NOTIFICATION_EMAIL, "Notification Email"),
        (TYPE_NOTIFICATION_EMAIL_RETRY, "Notification Email Retry"),
        (TYPE_ANALYTICS_MONITOR_EXPORT, "Analytics Monitor Export"),
        (TYPE_GATEWAY_STATUS_CHECK, "Gateway Status Check"),
        (TYPE_FINANCIAL_SUMMARY_ROLLUP, "Financial Summary Rollup"),
        (TYPE_WITHDRAWAL_SETTLEMENT, "Withdrawal Settlement"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    job_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payload = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=255, blank=True, null=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    available_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "background_jobs"
        ordering = ["available_at", "id"]
        indexes = [
            models.Index(fields=["status", "available_at"]),
            models.Index(fields=["job_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.job_type}:{self.status}#{self.id}"


class BookingDropoffEvent(models.Model):
    STAGE_BOOKING = "BOOKING"
    STAGE_PAYMENT = "PAYMENT"
    STAGE_CHOICES = [
        (STAGE_BOOKING, "Booking Process"),
        (STAGE_PAYMENT, "Payment Process"),
    ]

    REASON_LEFT_BOOKING_PROCESS = "LEFT_BOOKING_PROCESS"
    REASON_PAYMENT_NOT_COMPLETED = "PAYMENT_NOT_COMPLETED"
    REASON_PAYMENT_EXPIRED = "PAYMENT_EXPIRED"
    REASON_CHOICES = [
        (REASON_LEFT_BOOKING_PROCESS, "Left Booking Process"),
        (REASON_PAYMENT_NOT_COMPLETED, "Payment Not Completed"),
        (REASON_PAYMENT_EXPIRED, "Payment Session Expired"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="booking_dropoff_events",
        blank=True,
        null=True,
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        related_name="booking_dropoff_events",
        blank=True,
        null=True,
    )
    show = models.ForeignKey(
        Show,
        on_delete=models.SET_NULL,
        related_name="dropoff_events",
        blank=True,
        null=True,
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="dropoff_events",
        blank=True,
        null=True,
    )
    payment = models.ForeignKey(
        "Payment",
        on_delete=models.SET_NULL,
        related_name="dropoff_events",
        blank=True,
        null=True,
    )
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    reason = models.CharField(max_length=40, choices=REASON_CHOICES)
    seat_count = models.PositiveIntegerField(default=0)
    transaction_uuid = models.CharField(max_length=80, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_dropoff_events"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["stage", "created_at"]),
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["transaction_uuid"]),
        ]

    def __str__(self):
        return f"{self.stage}:{self.reason} ({self.transaction_uuid or self.id})"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"
        PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", "Partially Refunded"

    LEGACY_STATUS_ALIASES = {
        "PENDING": Status.PENDING,
        "SUCCESS": Status.SUCCESS,
        "PAID": Status.SUCCESS,
        "COMPLETED": Status.SUCCESS,
        "CONFIRMED": Status.SUCCESS,
        "FAILED": Status.FAILED,
        "DECLINED": Status.FAILED,
        "REFUNDED": Status.REFUNDED,
        "PARTIALLY REFUNDED": Status.PARTIALLY_REFUNDED,
        "PARTIALLY_REFUNDED": Status.PARTIALLY_REFUNDED,
    }

    STATUS_TRANSITIONS = {
        Status.PENDING: {Status.SUCCESS, Status.FAILED},
        Status.SUCCESS: {Status.REFUNDED, Status.PARTIALLY_REFUNDED},
        Status.FAILED: set(),
        Status.REFUNDED: set(),
        Status.PARTIALLY_REFUNDED: {Status.REFUNDED},
    }

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.CharField(max_length=30)
    transaction_uuid = models.CharField(max_length=80, blank=True, null=True, unique=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    payment_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"
        indexes = [
            models.Index(fields=["payment_status", "payment_date"]),
            models.Index(fields=["booking", "payment_date"]),
        ]

    @classmethod
    def normalize_payment_status(cls, value: str | None) -> str:
        return _normalize_choice_value(
            value,
            cls.Status.PENDING,
            set(cls.Status.values),
            cls.LEGACY_STATUS_ALIASES,
        )

    def save(self, *args, **kwargs):
        normalized_status = self.normalize_payment_status(self.payment_status)
        if self.transaction_uuid:
            normalized_transaction_uuid = str(self.transaction_uuid).strip() or None
            if normalized_transaction_uuid:
                existing_payment = type(self).objects.filter(
                    transaction_uuid=normalized_transaction_uuid,
                )
                if self.pk:
                    existing_payment = existing_payment.exclude(pk=self.pk)
                if existing_payment.exists():
                    raise ValidationError(
                        {"transaction_uuid": "Payment transaction UUID must be unique."}
                    )
            self.transaction_uuid = normalized_transaction_uuid
        if self.pk:
            current_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("payment_status", flat=True)
                .first()
            )
            _validate_status_transition(
                self.__class__.__name__,
                "payment_status",
                self.normalize_payment_status(current_status),
                normalized_status,
                self.STATUS_TRANSITIONS,
            )
        self.payment_status = normalized_status
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment {self.pk} ({self.payment_status})"


class Refund(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    LEGACY_STATUS_ALIASES = {
        "PENDING": Status.PENDING,
        "REFUNDED": Status.COMPLETED,
        "SUCCESS": Status.COMPLETED,
        "COMPLETED": Status.COMPLETED,
        "FAILED": Status.FAILED,
    }

    STATUS_TRANSITIONS = {
        Status.PENDING: {Status.COMPLETED, Status.FAILED},
        Status.COMPLETED: set(),
        Status.FAILED: set(),
    }

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    refund_date = models.DateTimeField(auto_now_add=True)
    refund_reason = models.CharField(max_length=255, blank=True, null=True)
    refund_status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    class Meta:
        db_table = "refunds"

    @classmethod
    def normalize_refund_status(cls, value: str | None) -> str:
        return _normalize_choice_value(
            value,
            cls.Status.PENDING,
            set(cls.Status.values),
            cls.LEGACY_STATUS_ALIASES,
        )

    def save(self, *args, **kwargs):
        normalized_status = self.normalize_refund_status(self.refund_status)
        if self.pk:
            current_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("refund_status", flat=True)
                .first()
            )
            _validate_status_transition(
                self.__class__.__name__,
                "refund_status",
                self.normalize_refund_status(current_status),
                normalized_status,
                self.STATUS_TRANSITIONS,
            )
        self.refund_status = normalized_status
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Refund {self.pk} ({self.refund_status})"


class Wallet(models.Model):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallets"

    def __str__(self):
        return f"Wallet {self.vendor_id}"


class VendorWallet(Wallet):
    """Compatibility alias for vendor wallet naming used by APIs/dashboards."""

    class Meta:
        proxy = True
        verbose_name = "Vendor Wallet"
        verbose_name_plural = "Vendor Wallets"


class PlatformRevenueConfig(models.Model):
    key = models.CharField(max_length=20, unique=True, default="default")
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=10,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        related_name="updated_revenue_configs",
        blank=True,
        null=True,
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_revenue_configs"

    def save(self, *args, **kwargs):
        self.key = "default"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Revenue Config ({self.commission_percent}%)"


class AdminWallet(models.Model):
    key = models.CharField(max_length=20, unique=True, default="primary")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_commission_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_commission_reversed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "admin_wallets"

    def save(self, *args, **kwargs):
        self.key = "primary"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"AdminWallet {self.key}"


class AdminWalletTransaction(models.Model):
    TYPE_COMMISSION_CREDIT = "COMMISSION_CREDIT"
    TYPE_COMMISSION_REVERSAL = "COMMISSION_REVERSAL"
    TYPE_ADJUSTMENT = "ADJUSTMENT"
    TYPE_CHOICES = [
        (TYPE_COMMISSION_CREDIT, "Commission Credit"),
        (TYPE_COMMISSION_REVERSAL, "Commission Reversal"),
        (TYPE_ADJUSTMENT, "Adjustment"),
    ]

    STATUS_COMPLETED = "COMPLETED"
    STATUS_REVERSED = "REVERSED"
    STATUS_CHOICES = [
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REVERSED, "Reversed"),
    ]

    STATUS_TRANSITIONS = {
        STATUS_COMPLETED: {STATUS_REVERSED},
        STATUS_REVERSED: set(),
    }

    wallet = models.ForeignKey(AdminWallet, on_delete=models.CASCADE, related_name="transactions")
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="admin_wallet_transactions",
        blank=True,
        null=True,
    )
    payment = models.ForeignKey(
        "Payment",
        on_delete=models.SET_NULL,
        related_name="admin_wallet_transactions",
        blank=True,
        null=True,
    )
    refund = models.ForeignKey(
        "Refund",
        on_delete=models.SET_NULL,
        related_name="admin_wallet_transactions",
        blank=True,
        null=True,
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        related_name="admin_wallet_transactions",
        blank=True,
        null=True,
    )
    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    description = models.CharField(max_length=255, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "admin_wallet_transactions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["transaction_type", "created_at"]),
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        normalized_status = _normalize_choice_value(
            self.status,
            self.STATUS_COMPLETED,
            {choice for choice, _ in self.STATUS_CHOICES},
        )
        if self.pk:
            current_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            _validate_status_transition(
                self.__class__.__name__,
                "status",
                _normalize_choice_value(
                    current_status,
                    self.STATUS_COMPLETED,
                    {choice for choice, _ in self.STATUS_CHOICES},
                ),
                normalized_status,
                self.STATUS_TRANSITIONS,
            )
        self.status = normalized_status
        super().save(*args, **kwargs)

    def __str__(self):
        return f"AdminWalletTx {self.id} ({self.transaction_type})"


class ReferralWallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="referral_wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_credited = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_debited = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_expired = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "referral_wallets"

    def __str__(self):
        return f"ReferralWallet {self.user_id}"


class UserWallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cash_wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_credited = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_debited = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_wallets"
        ordering = ["-updated_at", "-id"]

    def __str__(self):
        return f"UserWallet {self.user_id}"


class UserWalletTransaction(models.Model):
    TYPE_TOPUP = "TOPUP"
    TYPE_DEBIT = "DEBIT"
    TYPE_REFUND = "REFUND"
    TYPE_ADJUSTMENT = "ADJUSTMENT"
    TYPE_CHOICES = [
        (TYPE_TOPUP, "Top Up"),
        (TYPE_DEBIT, "Debit"),
        (TYPE_REFUND, "Refund"),
        (TYPE_ADJUSTMENT, "Adjustment"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_REVERSED = "REVERSED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REVERSED, "Reversed"),
    ]

    STATUS_TRANSITIONS = {
        STATUS_PENDING: {STATUS_COMPLETED, STATUS_FAILED, STATUS_REVERSED},
        STATUS_COMPLETED: {STATUS_REVERSED},
        STATUS_FAILED: set(),
        STATUS_REVERSED: set(),
    }

    wallet = models.ForeignKey(UserWallet, on_delete=models.CASCADE, related_name="transactions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_wallet_transactions")
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="user_wallet_transactions",
        blank=True,
        null=True,
    )
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    provider = models.CharField(max_length=20, default="SYSTEM")
    metadata = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_wallet_transactions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status", "created_at"]),
            models.Index(fields=["reference_id"]),
            models.Index(fields=["transaction_type", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def save(self, *args, **kwargs):
        normalized_status = _normalize_choice_value(
            self.status,
            self.STATUS_COMPLETED,
            {choice for choice, _ in self.STATUS_CHOICES},
        )
        if self.pk:
            current_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            _validate_status_transition(
                self.__class__.__name__,
                "status",
                _normalize_choice_value(
                    current_status,
                    self.STATUS_COMPLETED,
                    {choice for choice, _ in self.STATUS_CHOICES},
                ),
                normalized_status,
                self.STATUS_TRANSITIONS,
            )
        self.status = normalized_status
        if self.provider:
            self.provider = str(self.provider).strip().upper()[:20]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"UserWalletTx {self.id} ({self.transaction_type})"


class ReferralTransaction(models.Model):
    TYPE_CREDIT = "CREDIT"
    TYPE_DEBIT = "DEBIT"
    TYPE_EXPIRE = "EXPIRE"
    TYPE_REVERSAL = "REVERSAL"
    TYPE_CHOICES = [
        (TYPE_CREDIT, "Credit"),
        (TYPE_DEBIT, "Debit"),
        (TYPE_EXPIRE, "Expire"),
        (TYPE_REVERSAL, "Reversal"),
    ]

    STATUS_COMPLETED = "COMPLETED"
    STATUS_REVERSED = "REVERSED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REVERSED, "Reversed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REJECTED, "Rejected"),
    ]

    REASON_REFERRER_REWARD = "REFERRER_REWARD"
    REASON_REFERRED_REWARD = "REFERRED_REWARD"
    REASON_BOOKING_WALLET_USE = "BOOKING_WALLET_USE"
    REASON_BOOKING_WALLET_REFUND = "BOOKING_WALLET_REFUND"
    REASON_REFERRAL_CANCELLATION_REVERSAL = "REFERRAL_CANCELLATION_REVERSAL"
    REASON_EXPIRY = "EXPIRY"
    REASON_ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"
    REASON_CHOICES = [
        (REASON_REFERRER_REWARD, "Referrer Reward"),
        (REASON_REFERRED_REWARD, "Referred User Reward"),
        (REASON_BOOKING_WALLET_USE, "Booking Wallet Use"),
        (REASON_BOOKING_WALLET_REFUND, "Booking Wallet Refund"),
        (REASON_REFERRAL_CANCELLATION_REVERSAL, "Referral Cancellation Reversal"),
        (REASON_EXPIRY, "Expiry"),
        (REASON_ADMIN_ADJUSTMENT, "Admin Adjustment"),
    ]

    wallet = models.ForeignKey(ReferralWallet, on_delete=models.CASCADE, related_name="transactions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="referral_transactions")
    referral = models.ForeignKey(
        Referral,
        on_delete=models.SET_NULL,
        related_name="transactions",
        blank=True,
        null=True,
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="referral_wallet_transactions",
        blank=True,
        null=True,
    )
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    reason = models.CharField(max_length=40, choices=REASON_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expires_at = models.DateTimeField(blank=True, null=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "referral_transactions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "status", "created_at"]),
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["referral", "status"]),
            models.Index(fields=["expires_at", "status"]),
            models.Index(fields=["reason", "created_at"]),
        ]

    def __str__(self):
        return f"ReferralTx {self.id} {self.transaction_type} {self.amount}"


class ReferralPolicy(models.Model):
    key = models.CharField(max_length=20, unique=True, default="default")
    referrer_reward_amount = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    referred_reward_amount = models.DecimalField(max_digits=12, decimal_places=2, default=50)
    reward_expiry_days = models.PositiveIntegerField(default=90)
    wallet_cap_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    max_signups_per_ip_per_day = models.PositiveIntegerField(default=3)
    max_signups_per_device_per_day = models.PositiveIntegerField(default=2)
    auto_approve_rewards = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "referral_policies"

    def save(self, *args, **kwargs):
        self.key = "default"
        super().save(*args, **kwargs)

    def __str__(self):
        return "Referral Policy"


class Transaction(models.Model):
    TYPE_BOOKING_EARNING = "BOOKING_EARNING"
    TYPE_BOOKING_REVERSAL = "BOOKING_REVERSAL"
    TYPE_PLATFORM_COMMISSION = "PLATFORM_COMMISSION"
    TYPE_PLATFORM_COMMISSION_REVERSAL = "PLATFORM_COMMISSION_REVERSAL"
    TYPE_WITHDRAWAL_REQUEST = "WITHDRAWAL_REQUEST"
    TYPE_WITHDRAWAL_APPROVED = "WITHDRAWAL_APPROVED"
    TYPE_WITHDRAWAL_REJECTED = "WITHDRAWAL_REJECTED"
    TYPE_CHOICES = [
        (TYPE_BOOKING_EARNING, "Booking Earning"),
        (TYPE_BOOKING_REVERSAL, "Booking Earning Reversal"),
        (TYPE_PLATFORM_COMMISSION, "Platform Commission"),
        (TYPE_PLATFORM_COMMISSION_REVERSAL, "Platform Commission Reversal"),
        (TYPE_WITHDRAWAL_REQUEST, "Withdrawal Request"),
        (TYPE_WITHDRAWAL_APPROVED, "Withdrawal Approved"),
        (TYPE_WITHDRAWAL_REJECTED, "Withdrawal Rejected"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REJECTED, "Rejected"),
    ]

    STATUS_TRANSITIONS = {
        STATUS_PENDING: {STATUS_COMPLETED, STATUS_REJECTED},
        STATUS_COMPLETED: set(),
        STATUS_REJECTED: set(),
    }

    STATUS_REQUESTED = STATUS_PENDING
    STATUS_APPROVED = STATUS_COMPLETED
    STATUS_REJECTED = STATUS_REJECTED

    transaction_uuid = models.CharField(
        max_length=80,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
    )

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="transactions")
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        related_name="wallet_transactions",
        blank=True,
        null=True,
    )
    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    description = models.CharField(max_length=255, blank=True, null=True)
    decision_metadata = models.JSONField(default=dict, blank=True)
    decision_reason = models.CharField(max_length=255, blank=True, null=True)
    decision_by = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        related_name="decided_vendor_transactions",
        blank=True,
        null=True,
    )
    decision_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["transaction_uuid"]),
        ]

    @classmethod
    def normalize_status(cls, value: str | None) -> str:
        return _normalize_choice_value(
            value,
            cls.STATUS_COMPLETED,
            {choice for choice, _ in cls.STATUS_CHOICES},
        )

    def save(self, *args, **kwargs):
        normalized_status = self.normalize_status(self.status)
        if self.transaction_uuid:
            normalized_transaction_uuid = str(self.transaction_uuid).strip() or None
            if normalized_transaction_uuid:
                existing = type(self).objects.filter(transaction_uuid=normalized_transaction_uuid)
                if self.pk:
                    existing = existing.exclude(pk=self.pk)
                if existing.exists():
                    raise ValidationError({"transaction_uuid": "Transaction UUID must be unique."})
            self.transaction_uuid = normalized_transaction_uuid
        else:
            self.transaction_uuid = _generate_transaction_uuid()
        if self.pk:
            current_status = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            _validate_status_transition(
                self.__class__.__name__,
                "status",
                self.normalize_status(current_status),
                normalized_status,
                self.STATUS_TRANSITIONS,
            )
        self.status = normalized_status
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_type} {self.amount} ({self.status})"


class FinancialLedgerEntry(models.Model):
    transaction_uuid = models.CharField(
        max_length=80,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
    )
    reference_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metadata = models.JSONField(default=dict, blank=True)
    decision_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.transaction_uuid:
            normalized_transaction_uuid = str(self.transaction_uuid).strip() or None
            if normalized_transaction_uuid:
                existing = type(self).objects.filter(transaction_uuid=normalized_transaction_uuid)
                if self.pk:
                    existing = existing.exclude(pk=self.pk)
                if existing.exists():
                    raise ValidationError({"transaction_uuid": "Transaction UUID must be unique."})
            self.transaction_uuid = normalized_transaction_uuid
        else:
            self.transaction_uuid = _generate_transaction_uuid()
        super().save(*args, **kwargs)


class VendorCommissionLedger(FinancialLedgerEntry):
    ENTRY_EARNED = "EARNED"
    ENTRY_REVERSED = "REVERSED"
    ENTRY_CHOICES = [
        (ENTRY_EARNED, "Earned"),
        (ENTRY_REVERSED, "Reversed"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="commission_ledger_entries")
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="commission_ledger_entries")
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, related_name="commission_ledger_entries", blank=True, null=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, related_name="commission_ledger_entries", blank=True, null=True)
    entry_type = models.CharField(max_length=20, choices=ENTRY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "vendor_commission_ledger_entries"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["payment", "created_at"]),
            models.Index(fields=["entry_type", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class RefundLedger(FinancialLedgerEntry):
    STATUS_PENDING = "PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refund_ledger_entries")
    refund = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name="ledger_entries")
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="refund_ledger_entries")
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="refund_ledger_entries")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    refund_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "refund_ledger_entries"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["payment", "created_at"]),
            models.Index(fields=["refund", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class ReversalLedger(FinancialLedgerEntry):
    TYPE_BOOKING_EARNING = "BOOKING_EARNING"
    TYPE_PLATFORM_COMMISSION = "PLATFORM_COMMISSION"
    TYPE_REFUND = "REFUND"
    TYPE_WITHDRAWAL = "WITHDRAWAL"
    TYPE_CHOICES = [
        (TYPE_BOOKING_EARNING, "Booking Earning"),
        (TYPE_PLATFORM_COMMISSION, "Platform Commission"),
        (TYPE_REFUND, "Refund"),
        (TYPE_WITHDRAWAL, "Withdrawal"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="reversal_ledger_entries")
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="reversal_ledger_entries")
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, related_name="reversal_ledger_entries", blank=True, null=True)
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, related_name="reversal_ledger_entries", blank=True, null=True)
    refund = models.ForeignKey(Refund, on_delete=models.SET_NULL, related_name="reversal_ledger_entries", blank=True, null=True)
    reversal_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETED)
    reversal_reason = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "reversal_ledger_entries"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["payment", "created_at"]),
            models.Index(fields=["refund", "created_at"]),
            models.Index(fields=["reversal_type", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class WithdrawalLedger(FinancialLedgerEntry):
    STATUS_REQUESTED = "REQUESTED"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_PAID = "PAID"
    STATUS_FAILED = "FAILED"
    STATUS_REVERSED = "REVERSED"
    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REVERSED, "Reversed"),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="withdrawal_ledger_entries")
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="withdrawal_ledger_entries")
    withdrawal_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="withdrawal_ledger_entries",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    payout_reference = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    decision_reason = models.CharField(max_length=255, blank=True, null=True)
    decision_by = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        related_name="withdrawal_ledger_decisions",
        blank=True,
        null=True,
    )
    decision_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "withdrawal_ledger_entries"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["withdrawal_transaction", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["payout_reference"]),
        ]


class LoyaltyProgramConfig(models.Model):
    key = models.CharField(max_length=20, unique=True, default="default")
    points_per_currency_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=10,
        help_text="Currency amount required to earn one point.",
    )
    redemption_value_per_point = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Monetary value of one redeemed point.",
    )
    first_booking_bonus = models.PositiveIntegerField(default=50)
    points_expiry_months = models.PositiveIntegerField(default=12)
    tier_silver_threshold = models.PositiveIntegerField(default=0)
    tier_gold_threshold = models.PositiveIntegerField(default=1500)
    tier_platinum_threshold = models.PositiveIntegerField(default=5000)
    referral_bonus_points = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "loyalty_program_configs"

    def save(self, *args, **kwargs):
        self.key = "default"
        super().save(*args, **kwargs)

    def __str__(self):
        return "Loyalty Program Config"


class LoyaltyRule(LoyaltyProgramConfig):
    class Meta:
        proxy = True
        verbose_name = "Loyalty Rule"
        verbose_name_plural = "Loyalty Rules"


class UserLoyaltyWallet(models.Model):
    TIER_SILVER = "SILVER"
    TIER_GOLD = "GOLD"
    TIER_PLATINUM = "PLATINUM"
    TIER_CHOICES = [
        (TIER_SILVER, "Silver"),
        (TIER_GOLD, "Gold"),
        (TIER_PLATINUM, "Platinum"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="loyalty_wallet")
    total_points = models.PositiveIntegerField(default=0)
    available_points = models.PositiveIntegerField(default=0)
    lifetime_points = models.PositiveIntegerField(default=0)
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default=TIER_SILVER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_loyalty_wallets"
        ordering = ["-updated_at", "-id"]
        indexes = [models.Index(fields=["tier"])]

    def __str__(self):
        return f"LoyaltyWallet {self.user_id} ({self.available_points})"


class LoyaltyPromotion(models.Model):
    PROMO_TYPE_FESTIVAL = "FESTIVAL"
    PROMO_TYPE_DAILY = "DAILY"
    PROMO_TYPE_WEEKLY = "WEEKLY"
    PROMO_TYPE_REFERRAL = "REFERRAL"
    PROMO_TYPE_CHOICES = [
        (PROMO_TYPE_FESTIVAL, "Festival"),
        (PROMO_TYPE_DAILY, "Daily"),
        (PROMO_TYPE_WEEKLY, "Weekly"),
        (PROMO_TYPE_REFERRAL, "Referral"),
    ]

    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, null=True)
    promo_type = models.CharField(max_length=20, choices=PROMO_TYPE_CHOICES, default=PROMO_TYPE_FESTIVAL)
    trigger_code = models.CharField(max_length=50, blank=True, null=True)
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.SET_NULL,
        related_name="loyalty_promotions",
        blank=True,
        null=True,
    )
    bonus_multiplier = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    bonus_flat_points = models.PositiveIntegerField(default=0)
    stackable = models.BooleanField(default=False)
    starts_at = models.DateTimeField(blank=True, null=True)
    ends_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "loyalty_promotions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
            models.Index(fields=["vendor", "is_active"]),
            models.Index(fields=["trigger_code"]),
        ]

    def __str__(self):
        return self.title


class LoyaltyTransaction(models.Model):
    TYPE_EARN = "EARN"
    TYPE_REDEEM = "REDEEM"
    TYPE_EXPIRE = "EXPIRE"
    TYPE_REVERSE_EARN = "REVERSE_EARN"
    TYPE_RESTORE = "RESTORE"
    TYPE_ADJUST = "ADJUST"
    TYPE_CHOICES = [
        (TYPE_EARN, "Earn"),
        (TYPE_REDEEM, "Redeem"),
        (TYPE_EXPIRE, "Expire"),
        (TYPE_REVERSE_EARN, "Reverse Earn"),
        (TYPE_RESTORE, "Restore"),
        (TYPE_ADJUST, "Adjust"),
    ]

    REFERENCE_BOOKING = "BOOKING"
    REFERENCE_REWARD = "REWARD"
    REFERENCE_PROMOTION = "PROMOTION"
    REFERENCE_REFERRAL = "REFERRAL"
    REFERENCE_SYSTEM = "SYSTEM"
    REFERENCE_CHOICES = [
        (REFERENCE_BOOKING, "Booking"),
        (REFERENCE_REWARD, "Reward"),
        (REFERENCE_PROMOTION, "Promotion"),
        (REFERENCE_REFERRAL, "Referral"),
        (REFERENCE_SYSTEM, "System"),
    ]

    wallet = models.ForeignKey(UserLoyaltyWallet, on_delete=models.CASCADE, related_name="transactions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="loyalty_transactions")
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    points = models.PositiveIntegerField(default=0)
    reference_type = models.CharField(max_length=20, choices=REFERENCE_CHOICES, default=REFERENCE_SYSTEM)
    reference_id = models.CharField(max_length=80, blank=True, null=True)
    idempotency_key = models.CharField(max_length=120, unique=True, blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    is_expired = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "loyalty_transactions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "transaction_type", "created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["expires_at", "is_expired"]),
        ]

    def __str__(self):
        return f"{self.transaction_type} {self.points} ({self.user_id})"
