from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0021_seat_category_prices_and_booking_guards"),
    ]

    operations = [
        migrations.CreateModel(
            name="PricingRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("hall", models.CharField(blank=True, max_length=80, null=True)),
                (
                    "seat_category",
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
                (
                    "day_type",
                    models.CharField(
                        choices=[
                            ("ALL", "All Days"),
                            ("WEEKDAY", "Weekday"),
                            ("WEEKEND", "Weekend"),
                        ],
                        default="ALL",
                        max_length=20,
                    ),
                ),
                ("is_festival_pricing", models.BooleanField(default=False)),
                ("festival_name", models.CharField(blank=True, max_length=80, null=True)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                (
                    "adjustment_type",
                    models.CharField(
                        choices=[
                            ("FIXED", "Set Fixed Price"),
                            ("INCREMENT", "Add Amount"),
                            ("PERCENT", "Percent Change"),
                            ("MULTIPLIER", "Multiply"),
                        ],
                        default="INCREMENT",
                        max_length=20,
                    ),
                ),
                ("adjustment_value", models.DecimalField(decimal_places=2, max_digits=10)),
                ("priority", models.PositiveIntegerField(default=100)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "movie",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pricing_rules",
                        to="app.movie",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pricing_rules",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "pricing_rules",
                "ordering": ["priority", "id"],
            },
        ),
    ]
