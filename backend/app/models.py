"""Database models for the application."""

from __future__ import annotations

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
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
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="shows")
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="shows")
    hall = models.CharField(max_length=80, blank=True, null=True)
    slot = models.CharField(max_length=20, blank=True, null=True)
    screen_type = models.CharField(max_length=40, blank=True, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=20, default="Open")
    listing_status = models.CharField(max_length=20, default="Now Showing")
    show_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shows"

    def __str__(self):
        return f"{self.movie.title} ({self.show_date} {self.start_time})"


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


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    showtime = models.ForeignKey(Showtime, on_delete=models.CASCADE, related_name="bookings")
    booking_date = models.DateTimeField(auto_now_add=True)
    booking_status = models.CharField(max_length=20, default="Pending")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        db_table = "bookings"

    def __str__(self):
        return f"Booking {self.pk} ({self.booking_status})"


class BookingSeat(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="booking_seats")
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE, related_name="booking_seats")
    seat_price = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    discount_applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_seats"
        unique_together = ("booking", "seat")

    def __str__(self):
        return f"{self.booking_id} - {self.seat_id}"


class FoodItem(models.Model):
    item_name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, blank=True, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    is_available = models.BooleanField(default=True)

    class Meta:
        db_table = "food_items"

    def __str__(self):
        return self.item_name


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
