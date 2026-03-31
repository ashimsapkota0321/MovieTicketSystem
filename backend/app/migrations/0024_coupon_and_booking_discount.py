from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0023_wallet_and_transaction"),
    ]

    operations = [
        migrations.CreateModel(
            name="Coupon",
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
                ("code", models.CharField(max_length=50, unique=True)),
                (
                    "discount_type",
                    models.CharField(
                        choices=[("PERCENTAGE", "Percentage"), ("FIXED", "Fixed")],
                        max_length=20,
                    ),
                ),
                ("discount_value", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "min_booking_amount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                ("expiry_date", models.DateTimeField(blank=True, null=True)),
                ("usage_limit", models.PositiveIntegerField(blank=True, null=True)),
                ("usage_count", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "coupons",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddField(
            model_name="booking",
            name="coupon",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bookings",
                to="app.coupon",
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="discount_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
