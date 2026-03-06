from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def populate_slugs(apps, schema_editor):
    Movie = apps.get_model("app", "Movie")
    MovieGenre = apps.get_model("app", "MovieGenre")
    from django.utils.text import slugify

    def unique_slug(model, value, slug_field, pk):
        base = slugify(value) or "item"
        slug = base
        counter = 1
        while model.objects.filter(**{slug_field: slug}).exclude(pk=pk).exists():
            counter += 1
            slug = f"{base}-{counter}"
        return slug

    for movie in Movie.objects.all():
        if not getattr(movie, "slug", None) and getattr(movie, "title", None):
            movie.slug = unique_slug(Movie, movie.title, "slug", movie.pk)
            movie.save(update_fields=["slug"])

    for genre in MovieGenre.objects.all():
        if not getattr(genre, "slug", None) and getattr(genre, "name", None):
            genre.slug = unique_slug(MovieGenre, genre.name, "slug", genre.pk)
            genre.save(update_fields=["slug"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0013_banner_movie_and_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="movie",
            name="slug",
            field=models.SlugField(blank=True, max_length=220, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="short_description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="long_description",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="poster_image",
            field=models.ImageField(
                blank=True, null=True, upload_to="movie_posters/"
            ),
        ),
        migrations.AddField(
            model_name="movie",
            name="average_rating",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=3),
        ),
        migrations.AddField(
            model_name="movie",
            name="review_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="movie",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="movie",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="movie",
            name="status",
            field=models.CharField(
                choices=[("NOW_SHOWING", "Now Showing"), ("COMING_SOON", "Coming Soon")],
                default="COMING_SOON",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="movie",
            name="genres",
            field=models.ManyToManyField(
                blank=True,
                related_name="movies",
                through="app.MovieMovieGenre",
                to="app.moviegenre",
            ),
        ),
        migrations.AddField(
            model_name="moviegenre",
            name="slug",
            field=models.SlugField(blank=True, max_length=100, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="Person",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("full_name", models.CharField(max_length=150)),
                (
                    "slug",
                    models.SlugField(blank=True, max_length=180, null=True, unique=True),
                ),
                ("photo", models.ImageField(blank=True, null=True, upload_to="people/")),
                ("bio", models.TextField(blank=True, null=True)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                ("nationality", models.CharField(blank=True, max_length=80, null=True)),
                ("instagram", models.URLField(blank=True, null=True)),
                ("imdb", models.URLField(blank=True, null=True)),
                ("facebook", models.URLField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "people",
                "ordering": ["full_name"],
            },
        ),
        migrations.CreateModel(
            name="MovieCredit",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "credit_type",
                    models.CharField(
                        choices=[("CAST", "Cast"), ("CREW", "Crew")], max_length=10
                    ),
                ),
                ("role_name", models.CharField(blank=True, max_length=120, null=True)),
                ("department", models.CharField(blank=True, max_length=80, null=True)),
                ("display_order", models.PositiveIntegerField(default=0)),
                (
                    "movie",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credits",
                        to="app.movie",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="credits",
                        to="app.person",
                    ),
                ),
            ],
            options={
                "db_table": "movie_credits",
                "ordering": ["display_order", "id"],
            },
        ),
        migrations.AddField(
            model_name="review",
            name="is_approved",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="review",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AddField(
            model_name="review",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddConstraint(
            model_name="review",
            constraint=models.UniqueConstraint(
                fields=("movie", "user"), name="unique_movie_review"
            ),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
    ]
