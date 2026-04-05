import uuid

from django.db import migrations, models
import django.db.models.deletion


def populate_ticket_ids(apps, schema_editor):
    Ticket = apps.get_model("app", "Ticket")
    for ticket in Ticket.objects.filter(ticket_id__isnull=True).iterator():
        ticket.ticket_id = uuid.uuid4()
        ticket.save(update_fields=["ticket_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0035_booking_dropoff_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="is_used",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="ticket",
            name="payment_status",
            field=models.CharField(default="PENDING", max_length=20),
        ),
        migrations.AddField(
            model_name="ticket",
            name="seats",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="show_datetime",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="ticket_id",
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="token_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="show",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tickets", to="app.show"),
        ),
        migrations.AddField(
            model_name="ticket",
            name="user",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tickets", to="app.user"),
        ),
        migrations.RunPython(populate_ticket_ids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ticket",
            name="ticket_id",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
