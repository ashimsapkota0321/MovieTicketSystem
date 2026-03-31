"""Database models for the application."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


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


class User(models.Model):
    phone_number = models.CharField(max_length=13, unique=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
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
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_COMING_SOON
    )
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    review_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "movies"

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """Generate a slug for the movie if missing."""
        if self.title and not self.slug:
            self.slug = _unique_slugify(self, self.title, "slug", 220)
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
        combined = datetime.combine(self.show_date, when_time)
        now = timezone.now()
        if timezone.is_aware(now):
            return timezone.make_aware(combined, timezone.get_current_timezone())
        return combined

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
    SEAT_CATEGORY_CHOICES = [
        (SEAT_CATEGORY_ALL, "All Categories"),
        (SEAT_CATEGORY_NORMAL, "Normal"),
        (SEAT_CATEGORY_EXECUTIVE, "Executive"),
        (SEAT_CATEGORY_PREMIUM, "Premium"),
        (SEAT_CATEGORY_VIP, "VIP"),
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

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="pricing_rules")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="pricing_rules", blank=True, null=True)
    name = models.CharField(max_length=120)
    hall = models.CharField(max_length=80, blank=True, null=True)
    seat_category = models.CharField(max_length=20, choices=SEAT_CATEGORY_CHOICES, default=SEAT_CATEGORY_ALL)
    day_type = models.CharField(max_length=20, choices=DAY_TYPE_CHOICES, default=DAY_TYPE_ALL)
    is_festival_pricing = models.BooleanField(default=False)
    festival_name = models.CharField(max_length=80, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE_CHOICES, default=ADJUSTMENT_INCREMENT)
    adjustment_value = models.DecimalField(max_digits=10, decimal_places=2)
    priority = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "pricing_rules"
        ordering = ["priority", "id"]

    def __str__(self):
        return f"{self.vendor_id} - {self.name}"


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
    reference = models.CharField(max_length=20, unique=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tickets"

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


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="bookings")
    booking_date = models.DateTimeField(auto_now_add=True)
    booking_status = models.CharField(max_length=20, default="Pending")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
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

    class Meta:
        db_table = "bookings"

    def __str__(self):
        return f"Booking {self.pk} ({self.booking_status})"


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
    EVENT_CHOICES = [
        (EVENT_NEW_BOOKING, "New Booking"),
        (EVENT_PAYMENT_SUCCESS, "Payment Success"),
        (EVENT_SHOW_UPDATE, "Show Update"),
        (EVENT_MARKETING_CAMPAIGN, "Marketing Campaign"),
        (EVENT_BOOKING_CANCEL_REQUEST, "Booking Cancel Request"),
        (EVENT_BOOKING_RESUME_PENDING, "Booking Resume Pending"),
        (EVENT_BOOKING_CANCELLED, "Booking Cancelled"),
        (EVENT_REFUND_PROCESSED, "Refund Processed"),
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


class Payment(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.CharField(max_length=30)
    payment_status = models.CharField(max_length=20, default="Pending")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"

    def __str__(self):
        return f"Payment {self.pk} ({self.payment_status})"


class Refund(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    refund_date = models.DateTimeField(auto_now_add=True)
    refund_reason = models.CharField(max_length=255, blank=True, null=True)
    refund_status = models.CharField(max_length=20, default="Pending")

    class Meta:
        db_table = "refunds"

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.transaction_type} {self.amount} ({self.status})"
