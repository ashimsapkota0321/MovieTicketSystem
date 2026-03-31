from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0024_coupon_and_booking_discount"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "recipient_role",
                    models.CharField(
                        choices=[
                            ("admin", "Admin"),
                            ("vendor", "Vendor"),
                            ("customer", "Customer"),
                        ],
                        max_length=20,
                    ),
                ),
                ("recipient_id", models.PositiveIntegerField()),
                ("recipient_email", models.EmailField(blank=True, max_length=254, null=True)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("NEW_BOOKING", "New Booking"),
                            ("PAYMENT_SUCCESS", "Payment Success"),
                            ("SHOW_UPDATE", "Show Update"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "channel",
                    models.CharField(
                        choices=[
                            ("IN_APP", "In App"),
                            ("EMAIL", "Email"),
                            ("BOTH", "In App + Email"),
                        ],
                        default="IN_APP",
                        max_length=20,
                    ),
                ),
                ("title", models.CharField(max_length=180)),
                ("message", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("is_read", models.BooleanField(default=False)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "notifications",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
