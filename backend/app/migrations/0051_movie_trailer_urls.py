from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0050_fooditem_diet_and_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="movie",
            name="trailer_urls",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
