from django.db import migrations, models


def populate_bookingseat_showtime(apps, schema_editor):
    BookingSeat = apps.get_model("app", "BookingSeat")
    for booking_seat in BookingSeat.objects.select_related("booking").all().iterator(chunk_size=1000):
        booking_id = getattr(booking_seat, "booking_id", None)
        if not booking_id:
            continue
        booking = getattr(booking_seat, "booking", None)
        if booking is None:
            continue
        booking_seat.showtime_id = getattr(booking, "showtime_id", None)
        booking_seat.save(update_fields=["showtime"])


def deduplicate_bookingseat_showtime_seat(apps, schema_editor):
    BookingSeat = apps.get_model("app", "BookingSeat")
    duplicate_keys = (
        BookingSeat.objects.values("showtime_id", "seat_id")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)
    )
    for key in duplicate_keys.iterator(chunk_size=500):
        showtime_id = key.get("showtime_id")
        seat_id = key.get("seat_id")
        if not showtime_id or not seat_id:
            continue
        rows = BookingSeat.objects.filter(showtime_id=showtime_id, seat_id=seat_id).order_by("id")
        keep = rows.first()
        if not keep:
            continue
        rows.exclude(id=keep.id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0020_prevent_duplicate_screen_timings"),
    ]

    operations = [
        migrations.AddField(
            model_name="screen",
            name="executive_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="screen",
            name="normal_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="screen",
            name="premium_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="screen",
            name="vip_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="bookingseat",
            name="showtime",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="booking_seats",
                to="app.showtime",
            ),
        ),
        migrations.RunPython(populate_bookingseat_showtime, migrations.RunPython.noop),
        migrations.RunPython(deduplicate_bookingseat_showtime_seat, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="bookingseat",
            name="showtime",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="booking_seats",
                to="app.showtime",
            ),
        ),
        migrations.AddConstraint(
            model_name="bookingseat",
            constraint=models.UniqueConstraint(
                fields=("showtime", "seat"),
                name="unique_bookingseat_per_showtime_seat",
            ),
        ),
    ]
