from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0019_remove_banner_background_image_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="show",
            constraint=models.UniqueConstraint(
                fields=("vendor", "hall", "show_date", "start_time"),
                name="unique_show_per_vendor_hall_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="showtime",
            constraint=models.UniqueConstraint(
                fields=("screen", "start_time"),
                name="unique_showtime_per_screen_start",
            ),
        ),
    ]
