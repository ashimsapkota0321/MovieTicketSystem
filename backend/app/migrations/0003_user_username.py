# Generated migration for username field on User model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0002_otpverification"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="username",
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
    ]
