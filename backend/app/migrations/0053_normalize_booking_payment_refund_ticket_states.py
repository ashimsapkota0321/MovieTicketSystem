from django.db import migrations, models


def _normalize_booking_status(value):
    normalized = str(value or "PENDING").strip().upper()
    aliases = {
        "PENDING": "PENDING",
        "CONFIRMED": "CONFIRMED",
        "CANCELLED": "CANCELLED",
        "CANCELED": "CANCELLED",
    }
    return aliases.get(normalized, "PENDING")


def _normalize_payment_status(value):
    normalized = str(value or "PENDING").strip().upper()
    aliases = {
        "PENDING": "PENDING",
        "SUCCESS": "SUCCESS",
        "PAID": "SUCCESS",
        "COMPLETED": "SUCCESS",
        "CONFIRMED": "SUCCESS",
        "FAILED": "FAILED",
        "DECLINED": "FAILED",
        "REFUNDED": "REFUNDED",
        "PARTIALLY REFUNDED": "PARTIALLY_REFUNDED",
        "PARTIALLY_REFUNDED": "PARTIALLY_REFUNDED",
    }
    return aliases.get(normalized, "PENDING")


def _normalize_refund_status(value):
    normalized = str(value or "PENDING").strip().upper()
    aliases = {
        "PENDING": "PENDING",
        "REFUNDED": "COMPLETED",
        "SUCCESS": "COMPLETED",
        "COMPLETED": "COMPLETED",
        "FAILED": "FAILED",
    }
    return aliases.get(normalized, "PENDING")


def _normalize_ticket_payment_status(value):
    normalized = str(value or "PENDING").strip().upper()
    aliases = {
        "PENDING": "PENDING",
        "SUCCESS": "PAID",
        "COMPLETED": "PAID",
        "CONFIRMED": "PAID",
        "PAID": "PAID",
        "FAILED": "FAILED",
        "REFUNDED": "REFUNDED",
    }
    return aliases.get(normalized, "PENDING")


def normalize_states_forward(apps, schema_editor):
    Booking = apps.get_model("app", "Booking")
    Payment = apps.get_model("app", "Payment")
    Refund = apps.get_model("app", "Refund")
    Ticket = apps.get_model("app", "Ticket")

    for booking in Booking.objects.only("id", "booking_status").iterator(chunk_size=1000):
        normalized = _normalize_booking_status(booking.booking_status)
        if booking.booking_status != normalized:
            Booking.objects.filter(pk=booking.pk).update(booking_status=normalized)

    for payment in Payment.objects.only("id", "payment_status").iterator(chunk_size=1000):
        normalized = _normalize_payment_status(payment.payment_status)
        if payment.payment_status != normalized:
            Payment.objects.filter(pk=payment.pk).update(payment_status=normalized)

    for refund in Refund.objects.only("id", "refund_status").iterator(chunk_size=1000):
        normalized = _normalize_refund_status(refund.refund_status)
        if refund.refund_status != normalized:
            Refund.objects.filter(pk=refund.pk).update(refund_status=normalized)

    for ticket in Ticket.objects.only("id", "payment_status").iterator(chunk_size=1000):
        normalized = _normalize_ticket_payment_status(ticket.payment_status)
        if ticket.payment_status != normalized:
            Ticket.objects.filter(pk=ticket.pk).update(payment_status=normalized)


def normalize_states_backward(apps, schema_editor):
    # Keep canonical values on rollback to avoid reintroducing ambiguous states.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0052_revenue_distribution_wallets"),
    ]

    operations = [
        migrations.AlterField(
            model_name="booking",
            name="booking_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("CONFIRMED", "Confirmed"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("SUCCESS", "Success"),
                    ("FAILED", "Failed"),
                    ("REFUNDED", "Refunded"),
                    ("PARTIALLY_REFUNDED", "Partially Refunded"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="refund",
            name="refund_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("COMPLETED", "Completed"),
                    ("FAILED", "Failed"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="ticket",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("PAID", "Paid"),
                    ("FAILED", "Failed"),
                    ("REFUNDED", "Refunded"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.RunPython(normalize_states_forward, normalize_states_backward),
    ]
