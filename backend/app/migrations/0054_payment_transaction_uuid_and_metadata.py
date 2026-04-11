from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0053_normalize_booking_payment_refund_ticket_states"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="transaction_uuid",
            field=models.CharField(blank=True, db_index=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="payment",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
