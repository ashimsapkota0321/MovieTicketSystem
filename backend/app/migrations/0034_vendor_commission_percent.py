from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0033_notification_refund_and_cancel_events"),
    ]

    operations = [
        migrations.AddField(
            model_name="vendor",
            name="commission_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional vendor-specific commission percent override.",
                max_digits=5,
                null=True,
            ),
        ),
    ]
