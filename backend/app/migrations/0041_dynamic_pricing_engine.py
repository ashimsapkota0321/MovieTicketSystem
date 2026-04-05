from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


DAY_OF_WEEK_MAP = {
    "ALL": "ALL",
    "WEEKDAY": "WEEKDAY",
    "WEEKEND": "WEEKEND",
}


def backfill_pricing_rule_fields(apps, schema_editor):
    PricingRule = apps.get_model("app", "PricingRule")
    for rule in PricingRule.objects.all().iterator():
        changed_fields = []

        day_of_week = str(getattr(rule, "day_of_week", "") or "").strip().upper()
        if not day_of_week:
            day_of_week = DAY_OF_WEEK_MAP.get(str(rule.day_type or "").strip().upper(), "ALL")
            rule.day_of_week = day_of_week
            changed_fields.append("day_of_week")

        has_new_adjustment = (
            getattr(rule, "price_multiplier", None) is not None
            or getattr(rule, "flat_adjustment", None) is not None
        )
        if not has_new_adjustment:
            adjustment_type = str(rule.adjustment_type or "").strip().upper()
            adjustment_value = rule.adjustment_value if rule.adjustment_value is not None else Decimal("0")

            if adjustment_type == "MULTIPLIER":
                rule.price_multiplier = adjustment_value
                changed_fields.append("price_multiplier")
            elif adjustment_type == "INCREMENT":
                rule.flat_adjustment = adjustment_value
                changed_fields.append("flat_adjustment")
            elif adjustment_type == "PERCENT":
                rule.price_multiplier = Decimal("1") + (adjustment_value / Decimal("100"))
                changed_fields.append("price_multiplier")

        if changed_fields:
            rule.save(update_fields=changed_fields)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0040_subscriptionplan_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pricingrule",
            name="seat_category",
            field=models.CharField(
                choices=[
                    ("ALL", "All Categories"),
                    ("NORMAL", "Normal"),
                    ("EXECUTIVE", "Executive"),
                    ("PREMIUM", "Premium"),
                    ("VIP", "VIP"),
                    ("SILVER", "Silver"),
                    ("GOLD", "Gold"),
                    ("PLATINUM", "Platinum"),
                ],
                default="ALL",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="pricingrule",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pricing_rules",
                to="app.vendor",
            ),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="day_of_week",
            field=models.CharField(
                choices=[
                    ("ALL", "All Days"),
                    ("WEEKDAY", "Weekday"),
                    ("WEEKEND", "Weekend"),
                    ("MON", "Monday"),
                    ("TUE", "Tuesday"),
                    ("WED", "Wednesday"),
                    ("THU", "Thursday"),
                    ("FRI", "Friday"),
                    ("SAT", "Saturday"),
                    ("SUN", "Sunday"),
                ],
                default="ALL",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="end_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="flat_adjustment",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="max_price_cap",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="min_price_cap",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="occupancy_threshold",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="price_multiplier",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=8,
                null=True,
                validators=[MinValueValidator(0.01)],
            ),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="start_time",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="pricingrule",
            index=models.Index(fields=["vendor", "is_active", "priority"], name="pricing_rul_vendor__cab3e4_idx"),
        ),
        migrations.AddIndex(
            model_name="pricingrule",
            index=models.Index(fields=["is_active", "day_of_week", "seat_category"], name="pricing_rul_is_acti_608570_idx"),
        ),
        migrations.AddIndex(
            model_name="pricingrule",
            index=models.Index(fields=["movie", "hall"], name="pricing_rul_movie_i_2da287_idx"),
        ),
        migrations.CreateModel(
            name="ShowBasePrice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "seat_category",
                    models.CharField(
                        choices=[
                            ("ALL", "All Categories"),
                            ("NORMAL", "Normal"),
                            ("EXECUTIVE", "Executive"),
                            ("PREMIUM", "Premium"),
                            ("VIP", "VIP"),
                            ("SILVER", "Silver"),
                            ("GOLD", "Gold"),
                            ("PLATINUM", "Platinum"),
                        ],
                        default="NORMAL",
                        max_length=20,
                    ),
                ),
                (
                    "base_price",
                    models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(0)]),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "show",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="base_prices",
                        to="app.show",
                    ),
                ),
            ],
            options={
                "db_table": "show_base_prices",
                "ordering": ["show_id", "seat_category", "id"],
                "indexes": [
                    models.Index(fields=["show", "is_active"], name="show_base_p_show_id_73ab50_idx"),
                    models.Index(fields=["seat_category", "is_active"], name="show_base_p_seat_ca_a4dcae_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("show", "seat_category"),
                        name="unique_show_seat_category_base_price",
                    )
                ],
            },
        ),
        migrations.RunPython(backfill_pricing_rule_fields, reverse_code=noop_reverse),
    ]
