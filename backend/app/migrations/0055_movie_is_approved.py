from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0054_payment_transaction_uuid_and_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="movie",
            name="is_approved",
            field=models.BooleanField(default=True),
        ),
    ]