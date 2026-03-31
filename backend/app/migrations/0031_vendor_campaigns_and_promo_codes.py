# Generated manually for vendor campaigns and promo code engine.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0030_vendor_staff_accounts"),
    ]

    operations = [
        migrations.CreateModel(
            name="VendorPromoCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50, unique=True)),
                ("title", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, null=True)),
                (
                    "discount_type",
                    models.CharField(
                        choices=[("PERCENTAGE", "Percentage"), ("FIXED", "Fixed"), ("BOGO", "BOGO")],
                        max_length=20,
                    ),
                ),
                ("discount_value", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("min_booking_amount", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("max_discount_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("usage_limit", models.PositiveIntegerField(blank=True, null=True)),
                ("usage_count", models.PositiveIntegerField(default=0)),
                ("per_user_limit", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "seat_category_scope",
                    models.CharField(
                        choices=[
                            ("ALL", "All Categories"),
                            ("NORMAL", "Normal"),
                            ("EXECUTIVE", "Executive"),
                            ("PREMIUM", "Premium"),
                            ("VIP", "VIP"),
                        ],
                        default="ALL",
                        max_length=20,
                    ),
                ),
                ("requires_student", models.BooleanField(default=False)),
                ("allowed_weekdays", models.CharField(blank=True, max_length=64, null=True)),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("is_flash_sale", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "vendor",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="promo_codes", to="app.vendor"),
                ),
            ],
            options={
                "db_table": "vendor_promo_codes",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="VendorCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=140)),
                ("message_template", models.TextField()),
                (
                    "delivery_channel",
                    models.CharField(
                        choices=[("PUSH", "Push"), ("SMS", "SMS"), ("BOTH", "Push + SMS")],
                        default="BOTH",
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("SCHEDULED", "Scheduled"),
                            ("RUNNING", "Running"),
                            ("COMPLETED", "Completed"),
                        ],
                        default="DRAFT",
                        max_length=20,
                    ),
                ),
                ("include_past_attendees_only", models.BooleanField(default=True)),
                ("min_days_since_booking", models.PositiveIntegerField(default=0)),
                ("scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("sent_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "promo_code",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="campaigns",
                        to="app.vendorpromocode",
                    ),
                ),
                (
                    "recommended_movie",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="campaigns_recommending_movie",
                        to="app.movie",
                    ),
                ),
                (
                    "target_movie",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="campaigns_targeting_movie",
                        to="app.movie",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="campaigns", to="app.vendor"),
                ),
            ],
            options={
                "db_table": "vendor_campaigns",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="VendorCampaignDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "channel",
                    models.CharField(choices=[("PUSH", "Push"), ("SMS", "SMS")], max_length=10),
                ),
                ("contact", models.CharField(blank=True, max_length=120, null=True)),
                ("message", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[("SENT", "Sent"), ("FAILED", "Failed")],
                        default="SENT",
                        max_length=20,
                    ),
                ),
                ("error_message", models.CharField(blank=True, max_length=255, null=True)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dispatches", to="app.vendorcampaign"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="campaign_dispatches",
                        to="app.user",
                    ),
                ),
            ],
            options={
                "db_table": "vendor_campaign_dispatches",
                "ordering": ["-sent_at", "-id"],
            },
        ),
        migrations.AlterField(
            model_name="notification",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("NEW_BOOKING", "New Booking"),
                    ("PAYMENT_SUCCESS", "Payment Success"),
                    ("SHOW_UPDATE", "Show Update"),
                    ("MARKETING_CAMPAIGN", "Marketing Campaign"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="vendor_promo_code",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="app.vendorpromocode",
            ),
        ),
    ]
