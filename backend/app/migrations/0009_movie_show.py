# Generated manually for Movie and Show models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0008_admin_vendor_profile_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="Movie",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, null=True)),
                ("language", models.CharField(blank=True, max_length=50, null=True)),
                ("genre", models.CharField(blank=True, max_length=80, null=True)),
                ("duration", models.CharField(blank=True, max_length=50, null=True)),
                ("rating", models.CharField(blank=True, max_length=20, null=True)),
                ("release_date", models.DateField(blank=True, null=True)),
                ("poster_url", models.URLField(blank=True, null=True)),
                ("trailer_url", models.URLField(blank=True, null=True)),
                ("status", models.CharField(default="Coming Soon", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "movies",
            },
        ),
        migrations.CreateModel(
            name="Show",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hall", models.CharField(blank=True, max_length=80, null=True)),
                ("slot", models.CharField(blank=True, max_length=20, null=True)),
                ("screen_type", models.CharField(blank=True, max_length=40, null=True)),
                ("price", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ("status", models.CharField(default="Open", max_length=20)),
                ("listing_status", models.CharField(default="Now Showing", max_length=20)),
                ("show_date", models.DateField()),
                ("start_time", models.TimeField()),
                ("end_time", models.TimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "movie",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shows",
                        to="app.movie",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shows",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "shows",
            },
        ),
    ]
