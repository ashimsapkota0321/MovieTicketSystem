from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0042_rename_pricing_rul_vendor__cab3e4_idx_pricing_rul_vendor__9bcb8f_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketvalidationscan",
            name="vendor_staff",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ticket_validation_scans",
                to="app.vendorstaff",
            ),
        ),
    ]
