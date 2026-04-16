from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0068_alter_notification_event_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="authsession",
            name="session_id",
            field=models.CharField(
                db_index=True,
                default=uuid.uuid4,
                editable=False,
                max_length=36,
                unique=True,
            ),
        ),
    ]
