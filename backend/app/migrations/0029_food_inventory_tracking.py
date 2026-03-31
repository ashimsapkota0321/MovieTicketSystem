from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0028_private_screening_and_bulk_tickets"),
    ]

    operations = [
        migrations.AddField(
            model_name="fooditem",
            name="track_inventory",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="fooditem",
            name="stock_quantity",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="fooditem",
            name="sold_out_threshold",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="fooditem",
            name="sold_out_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
