from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0009_movie_show"),
    ]

    operations = [
        migrations.AddField(
            model_name="movie",
            name="duration_minutes",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="banner_image",
            field=models.ImageField(blank=True, null=True, upload_to="movie_banners/"),
        ),
        migrations.CreateModel(
            name="HomeSlide",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slide_type", models.CharField(choices=[("MOVIE", "Movie"), ("COLLAB", "Collaboration")], default="MOVIE", max_length=10)),
                ("title_override", models.CharField(blank=True, max_length=200, null=True)),
                ("badge_text", models.CharField(blank=True, max_length=50, null=True)),
                ("subtitle", models.CharField(blank=True, max_length=200, null=True)),
                ("description_override", models.TextField(blank=True, null=True)),
                ("background_image", models.ImageField(blank=True, null=True, upload_to="home_slides/")),
                ("cta_text", models.CharField(blank=True, max_length=50, null=True)),
                ("cta_type", models.CharField(choices=[("MOVIE_DETAIL", "Movie Detail"), ("BOOK_NOW", "Book Now"), ("EXTERNAL_LINK", "External Link")], default="MOVIE_DETAIL", max_length=20)),
                ("external_url", models.URLField(blank=True, null=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("start_at", models.DateTimeField(blank=True, null=True)),
                ("end_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("movie", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="home_slides", to="app.movie")),
            ],
            options={
                "db_table": "home_slides",
                "ordering": ["sort_order", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Collaborator",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("logo", models.ImageField(upload_to="collaborators/")),
                ("website_url", models.URLField(blank=True, null=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "collaborators",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.CreateModel(
            name="CollabDetails",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("partner_name", models.CharField(max_length=100)),
                ("partner_logo", models.ImageField(upload_to="collab_logos/")),
                ("partner_logo_2", models.ImageField(blank=True, null=True, upload_to="collab_logos/")),
                ("headline", models.CharField(max_length=200)),
                ("offer_text", models.CharField(max_length=200)),
                ("promo_code_label", models.CharField(max_length=100)),
                ("promo_code", models.CharField(max_length=50)),
                ("terms_text", models.CharField(max_length=200)),
                ("primary_color", models.CharField(blank=True, max_length=20, null=True)),
                ("secondary_color", models.CharField(blank=True, max_length=20, null=True)),
                ("right_badge_text", models.CharField(blank=True, max_length=100, null=True)),
                ("slide", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="collab_details", to="app.homeslide")),
            ],
            options={
                "db_table": "collab_details",
            },
        ),
    ]

