from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0012_banner"),
    ]

    operations = [
        migrations.AddField(
            model_name="banner",
            name="movie",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="banners",
                to="app.movie",
            ),
        ),
        migrations.AlterField(
            model_name="banner",
            name="title",
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AlterField(
            model_name="banner",
            name="background_image",
            field=models.ImageField(
                blank=True, null=True, upload_to="banners/backgrounds/"
            ),
        ),
    ]
