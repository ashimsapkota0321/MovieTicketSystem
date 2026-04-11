from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0056_auth_session"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="transaction_uuid",
            field=models.CharField(blank=True, db_index=True, max_length=80, null=True, unique=True),
        ),
    ]
