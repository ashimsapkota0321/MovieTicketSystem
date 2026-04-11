from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0051_movie_trailer_urls"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="admin_commission",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="booking",
            name="commission_percent_applied",
            field=models.DecimalField(decimal_places=2, default=10, max_digits=5),
        ),
        migrations.AddField(
            model_name="booking",
            name="vendor_earning",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.CreateModel(
            name="AdminWallet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="primary", max_length=20, unique=True)),
                ("balance", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_commission_earned", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("total_commission_reversed", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "admin_wallets",
            },
        ),
        migrations.CreateModel(
            name="PlatformRevenueConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="default", max_length=20, unique=True)),
                ("commission_percent", models.DecimalField(decimal_places=2, default=10, max_digits=5)),
                ("is_active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_revenue_configs",
                        to="app.admin",
                    ),
                ),
            ],
            options={
                "db_table": "platform_revenue_configs",
            },
        ),
        migrations.CreateModel(
            name="AdminWalletTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[
                            ("COMMISSION_CREDIT", "Commission Credit"),
                            ("COMMISSION_REVERSAL", "Commission Reversal"),
                            ("ADJUSTMENT", "Adjustment"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("COMPLETED", "Completed"), ("REVERSED", "Reversed")],
                        default="COMPLETED",
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("gross_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("commission_percent", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("description", models.CharField(blank=True, max_length=255, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "booking",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="admin_wallet_transactions",
                        to="app.booking",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="admin_wallet_transactions",
                        to="app.payment",
                    ),
                ),
                (
                    "refund",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="admin_wallet_transactions",
                        to="app.refund",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="admin_wallet_transactions",
                        to="app.vendor",
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="app.adminwallet",
                    ),
                ),
            ],
            options={
                "db_table": "admin_wallet_transactions",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="adminwallettransaction",
            index=models.Index(fields=["transaction_type", "created_at"], name="admin_walle_transac_4b08e2_idx"),
        ),
        migrations.AddIndex(
            model_name="adminwallettransaction",
            index=models.Index(fields=["vendor", "created_at"], name="admin_walle_vendor__f4202c_idx"),
        ),
        migrations.AddIndex(
            model_name="adminwallettransaction",
            index=models.Index(fields=["booking", "created_at"], name="admin_walle_booking_8fb1c6_idx"),
        ),
    ]
