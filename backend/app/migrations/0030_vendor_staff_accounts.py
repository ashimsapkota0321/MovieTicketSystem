from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0029_food_inventory_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="VendorStaff",
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
                ("full_name", models.CharField(max_length=120)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("phone_number", models.CharField(blank=True, max_length=13, null=True)),
                ("username", models.CharField(blank=True, max_length=50, null=True, unique=True)),
                (
                    "role",
                    models.CharField(
                        choices=[("CASHIER", "Cashier"), ("MANAGER", "Manager")],
                        default="CASHIER",
                        max_length=20,
                    ),
                ),
                ("password", models.CharField(max_length=256)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_accounts",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "vendor_staff_accounts",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
