from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0067_alter_backgroundjob_job_type"),
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
                    ("BOOKING_RESUME_PENDING", "Booking Resume Pending"),
                    ("BOOKING_CANCELLED", "Booking Cancelled"),
                    ("REFUND_PROCESSED", "Refund Processed"),
                    ("CUSTOM_MESSAGE", "Custom Message"),
                    ("USER_FEEDBACK", "User Feedback"),
                    ("SUBSCRIPTION_EXPIRING", "Subscription Expiring"),
                    ("SUBSCRIPTION_EXPIRED", "Subscription Expired"),
                ],
                max_length=30,
            ),
        ),
    ]
