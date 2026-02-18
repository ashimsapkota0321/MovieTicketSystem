from django.db import models
from django.contrib.auth.hashers import make_password, check_password, identify_hasher


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
    date_joined = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
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

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
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

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
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
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    language = models.CharField(max_length=50, blank=True, null=True)
    genre = models.CharField(max_length=80, blank=True, null=True)
    duration = models.CharField(max_length=50, blank=True, null=True)
    duration_minutes = models.PositiveIntegerField(blank=True, null=True)
    rating = models.CharField(max_length=20, blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)
    banner_image = models.ImageField(upload_to="movie_banners/", blank=True, null=True)
    poster_url = models.URLField(blank=True, null=True)
    trailer_url = models.URLField(blank=True, null=True)
    status = models.CharField(max_length=20, default="Coming Soon")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "movies"

    def __str__(self):
        return self.title


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
