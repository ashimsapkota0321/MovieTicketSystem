from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0011_booking_fooditem_moviegenre_payment_screen_seat_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Banner",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=200)),
                ("subtitle", models.CharField(blank=True, max_length=200, null=True)),
                ("description", models.TextField(blank=True, null=True)),
                ("meta_info", models.CharField(blank=True, max_length=200, null=True)),
                ("badge_text", models.CharField(blank=True, max_length=50, null=True)),
                (
                    "badge_type",
                    models.CharField(
                        choices=[
                            ("NOW_SHOWING", "Now Showing"),
                            ("QFX", "QFX"),
                            ("ESEWA_OFFER", "eSewa Offer"),
                            ("COLLAB", "Collaboration"),
                            ("COMING_SOON", "Coming Soon"),
                            ("OTHER", "Other"),
                        ],
                        default="OTHER",
                        max_length=20,
                    ),
                ),
                (
                    "background_image",
                    models.ImageField(upload_to="banners/backgrounds/"),
                ),
                (
                    "poster_image",
                    models.ImageField(
                        blank=True, null=True, upload_to="banners/posters/"
                    ),
                ),
                ("button_text", models.CharField(blank=True, max_length=50, null=True)),
                ("button_link", models.CharField(blank=True, max_length=300, null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "display_on",
                    models.CharField(
                        choices=[("HOME", "Home"), ("MOVIES", "Movies"), ("BOTH", "Both")],
                        default="BOTH",
                        max_length=10,
                    ),
                ),
                (
                    "priority",
                    models.IntegerField(
                        default=0,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("start_date", models.DateTimeField(blank=True, null=True)),
                ("end_date", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "banners",
                "ordering": ["priority", "-created_at"],
            },
        ),
    ]
