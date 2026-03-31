# Generated manually for vendor cancellation policy support.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0031_vendor_campaigns_and_promo_codes"),
    ]

    operations = [
        migrations.CreateModel(
            name="VendorCancellationPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("allow_customer_cancellation", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("refund_percent_2h_plus", models.DecimalField(decimal_places=2, default=100, max_digits=5)),
                ("refund_percent_1_to_2h", models.DecimalField(decimal_places=2, default=70, max_digits=5)),
                ("refund_percent_less_than_1h", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("note", models.CharField(blank=True, max_length=255, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "screen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cancellation_policies",
                        to="app.screen",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cancellation_policies",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "vendor_cancellation_policies",
                "ordering": ["screen_id", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="vendorcancellationpolicy",
            constraint=models.UniqueConstraint(
                fields=("vendor", "screen"),
                name="unique_vendor_screen_cancellation_policy",
            ),
        ),
    ]
