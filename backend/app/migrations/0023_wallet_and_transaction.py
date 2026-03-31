from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0022_pricingrule"),
    ]

    operations = [
        migrations.CreateModel(
            name="Wallet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_earnings", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_commission", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_withdrawn", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "vendor",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wallet",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "wallets",
            },
        ),
        migrations.CreateModel(
            name="Transaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            ("BOOKING_EARNING", "Booking Earning"),
                            ("WITHDRAWAL_REQUEST", "Withdrawal Request"),
                            ("WITHDRAWAL_APPROVED", "Withdrawal Approved"),
                            ("WITHDRAWAL_REJECTED", "Withdrawal Rejected"),
                        ],
                        max_length=30,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("commission_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("gross_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("COMPLETED", "Completed"),
                            ("REJECTED", "Rejected"),
                        ],
                        default="COMPLETED",
                        max_length=20,
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=255, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "booking",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wallet_transactions",
                        to="app.booking",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="app.vendor",
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="app.wallet",
                    ),
                ),
            ],
            options={
                "db_table": "transactions",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
