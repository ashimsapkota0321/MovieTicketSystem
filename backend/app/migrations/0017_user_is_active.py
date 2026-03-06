# Generated migration for is_active field on User model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0016_person_photo_url_movie_credit_rename"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
