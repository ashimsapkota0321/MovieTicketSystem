from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0062_referralholdperiod_referraltransaction_available_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="privatescreeningrequest",
            name="invoice_total_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="privatescreeningrequest",
            name="amount_paid",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="privatescreeningrequest",
            name="settlement_status",
            field=models.CharField(default="UNSETTLED", max_length=20),
        ),
        migrations.AddField(
            model_name="bulkticketbatch",
            name="seat_hold_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="bulkticketbatch",
            name="seat_hold_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="bulkticketbatch",
            name="invoice_number",
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
        migrations.AddField(
            model_name="bulkticketbatch",
            name="invoice_total_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="bulkticketbatch",
            name="amount_paid",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="bulkticketbatch",
            name="settlement_status",
            field=models.CharField(default="UNSETTLED", max_length=20),
        ),
    ]
