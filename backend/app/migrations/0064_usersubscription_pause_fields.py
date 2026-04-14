from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0063_corporate_billing_and_batch_hold_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="usersubscription",
            name="paused_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="usersubscription",
            name="paused_remaining_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
