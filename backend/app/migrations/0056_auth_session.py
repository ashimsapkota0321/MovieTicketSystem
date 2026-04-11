import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0055_movie_is_approved"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuthSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("role", models.CharField(choices=[("admin", "Admin"), ("vendor", "Vendor"), ("customer", "Customer")], max_length=20)),
                ("user_id", models.PositiveIntegerField(db_index=True)),
                ("staff_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("staff_role", models.CharField(blank=True, max_length=40, null=True)),
                ("refresh_token_hash", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("access_expires_at", models.DateTimeField(db_index=True)),
                ("refresh_expires_at", models.DateTimeField(db_index=True)),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("revoked_reason", models.CharField(blank=True, max_length=100, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "auth_sessions",
                "indexes": [
                    models.Index(fields=["role", "user_id"], name="app_authses_role_0f7fa6_idx"),
                    models.Index(fields=["role", "revoked_at", "refresh_expires_at"], name="app_authses_role_8b2185_idx"),
                ],
            },
        ),
    ]