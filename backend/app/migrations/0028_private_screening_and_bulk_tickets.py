from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0027_ticket_validation_scan"),
    ]

    operations = [
        migrations.CreateModel(
            name="BulkTicketBatch",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("corporate_name", models.CharField(max_length=160)),
                ("contact_person", models.CharField(blank=True, max_length=120, null=True)),
                ("contact_email", models.EmailField(blank=True, max_length=254, null=True)),
                ("movie_title", models.CharField(blank=True, max_length=200, null=True)),
                ("hall", models.CharField(blank=True, max_length=80, null=True)),
                ("show_date", models.DateField(blank=True, null=True)),
                ("show_time", models.TimeField(blank=True, null=True)),
                ("valid_until", models.DateField(blank=True, null=True)),
                ("unit_price", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("DRAFT", "Draft"),
                            ("GENERATED", "Generated"),
                            ("EXPORTED", "Exported"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="GENERATED",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bulk_ticket_batches",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "bulk_ticket_batches",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="PrivateScreeningRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("requester_type", models.CharField(blank=True, max_length=30, null=True)),
                ("organization_name", models.CharField(max_length=160)),
                ("contact_person", models.CharField(max_length=120)),
                ("contact_email", models.EmailField(max_length=254)),
                ("contact_phone", models.CharField(blank=True, max_length=20, null=True)),
                ("preferred_date", models.DateField(blank=True, null=True)),
                ("preferred_start_time", models.TimeField(blank=True, null=True)),
                ("attendee_count", models.PositiveIntegerField(default=1)),
                ("preferred_movie_title", models.CharField(blank=True, max_length=200, null=True)),
                ("hall_preference", models.CharField(blank=True, max_length=80, null=True)),
                ("special_requirements", models.TextField(blank=True, null=True)),
                (
                    "estimated_budget",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("REVIEWED", "Reviewed"),
                            ("COUNTERED", "Counter Offered"),
                            ("ACCEPTED", "Accepted"),
                            ("REJECTED", "Rejected"),
                            ("INVOICED", "Invoiced"),
                            ("COMPLETED", "Completed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("vendor_notes", models.TextField(blank=True, null=True)),
                (
                    "quoted_amount",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
                ),
                (
                    "counter_offer_amount",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
                ),
                ("invoice_number", models.CharField(blank=True, max_length=40, null=True)),
                ("invoice_notes", models.TextField(blank=True, null=True)),
                ("invoiced_at", models.DateTimeField(blank=True, null=True)),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "vendor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="private_screening_requests",
                        to="app.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "private_screening_requests",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="BulkTicketItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("employee_code", models.CharField(blank=True, max_length=80, null=True)),
                ("recipient_name", models.CharField(blank=True, max_length=120, null=True)),
                ("recipient_email", models.EmailField(blank=True, max_length=254, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Active"),
                            ("REDEEMED", "Redeemed"),
                            ("VOID", "Void"),
                        ],
                        default="ACTIVE",
                        max_length=20,
                    ),
                ),
                ("redeemed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tickets",
                        to="app.bulkticketbatch",
                    ),
                ),
                (
                    "ticket",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bulk_ticket_item",
                        to="app.ticket",
                    ),
                ),
            ],
            options={
                "db_table": "bulk_ticket_items",
                "ordering": ["id"],
            },
        ),
    ]
