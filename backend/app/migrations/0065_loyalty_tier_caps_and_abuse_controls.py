from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0064_usersubscription_pause_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="loyaltyprogramconfig",
            name="tier_points_window_months",
            field=models.PositiveIntegerField(default=12),
        ),
        migrations.AddField(
            model_name="loyaltyprogramconfig",
            name="daily_redemption_points_cap",
            field=models.PositiveIntegerField(default=2000),
        ),
        migrations.AddField(
            model_name="loyaltyprogramconfig",
            name="daily_redemption_count_cap",
            field=models.PositiveIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="loyaltyprogramconfig",
            name="reward_redeem_cooldown_minutes",
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name="loyaltyprogramconfig",
            name="max_redemption_attempts_per_hour",
            field=models.PositiveIntegerField(default=15),
        ),
    ]
