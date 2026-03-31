from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0017_user_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="fooditem",
            name="hall",
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.AddField(
            model_name="fooditem",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="food_items",
                to="app.vendor",
            ),
        ),
    ]
