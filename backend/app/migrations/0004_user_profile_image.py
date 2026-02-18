# Generated migration for profile_image field on User model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0003_user_username"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile_image",
            field=models.ImageField(blank=True, null=True, upload_to="profile_images/"),
        ),
    ]
