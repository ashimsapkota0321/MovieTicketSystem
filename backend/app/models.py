from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class User(models.Model):
    phone_number = models.CharField(max_length=13, unique=True)
    email = models.EmailField(unique=True)
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
        return check_password(raw_password, self.password)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class OTPVerification(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = "otp_verifications"

    def __str__(self):
        return f"OTP for {self.email} - {self.otp} ({'verified' if self.is_verified else 'pending'})"
