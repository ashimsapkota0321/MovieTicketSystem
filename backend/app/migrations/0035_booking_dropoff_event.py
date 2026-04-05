from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0034_vendor_commission_percent"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingDropoffEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "stage",
                    models.CharField(
                        choices=[("BOOKING", "Booking Process"), ("PAYMENT", "Payment Process")],
                        max_length=20,
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("LEFT_BOOKING_PROCESS", "Left Booking Process"),
                            ("PAYMENT_NOT_COMPLETED", "Payment Not Completed"),
                            ("PAYMENT_EXPIRED", "Payment Session Expired"),
                        ],
                        max_length=40,
                    ),
                ),
                ("seat_count", models.PositiveIntegerField(default=0)),
                ("transaction_uuid", models.CharField(blank=True, max_length=80, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "booking",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dropoff_events",
                        to="app.booking",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dropoff_events",
                        to="app.payment",
                    ),
                ),
                (
                    "show",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dropoff_events",
                        to="app.show",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="booking_dropoff_events",
                        to="app.user",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="booking_dropoff_events",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "booking_dropoff_events",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="bookingdropoffevent",
            index=models.Index(fields=["stage", "created_at"], name="booking_drop_stage_58e8ef_idx"),
        ),
        migrations.AddIndex(
            model_name="bookingdropoffevent",
            index=models.Index(fields=["vendor", "created_at"], name="booking_drop_vendor__ef02ee_idx"),
        ),
        migrations.AddIndex(
            model_name="bookingdropoffevent",
            index=models.Index(fields=["transaction_uuid"], name="booking_drop_transac_3dd915_idx"),
        ),
    ]
