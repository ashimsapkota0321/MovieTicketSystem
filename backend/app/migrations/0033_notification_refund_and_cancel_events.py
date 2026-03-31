# Generated manually for expanded notification event choices.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0032_vendor_cancellation_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("NEW_BOOKING", "New Booking"),
                    ("PAYMENT_SUCCESS", "Payment Success"),
                    ("SHOW_UPDATE", "Show Update"),
                    ("MARKETING_CAMPAIGN", "Marketing Campaign"),
                    ("BOOKING_CANCEL_REQUEST", "Booking Cancel Request"),
                    ("BOOKING_CANCELLED", "Booking Cancelled"),
                    ("REFUND_PROCESSED", "Refund Processed"),
                ],
                max_length=30,
            ),
        ),
    ]
