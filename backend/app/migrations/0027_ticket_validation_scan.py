from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0026_food_combo_order_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="TicketValidationScan",
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
                ("reference", models.CharField(max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("VALID", "Valid"),
                            ("DUPLICATE", "Duplicate"),
                            ("INVALID", "Invalid"),
                            ("FRAUD", "Fraud Suspected"),
                        ],
                        max_length=20,
                    ),
                ),
                ("reason", models.CharField(blank=True, max_length=255, null=True)),
                ("fraud_score", models.PositiveIntegerField(default=0)),
                ("source_ip", models.CharField(blank=True, max_length=45, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=255, null=True)),
                ("scanned_at", models.DateTimeField(auto_now_add=True)),
                (
                    "booking",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ticket_validation_scans",
                        to="app.booking",
                    ),
                ),
                (
                    "scanned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="performed_ticket_scans",
                        to="app.vendor",
                    ),
                ),
                (
                    "ticket",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="validation_scans",
                        to="app.ticket",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ticket_validation_scans",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "ticket_validation_scans",
                "ordering": ["-scanned_at", "-id"],
            },
        ),
    ]
