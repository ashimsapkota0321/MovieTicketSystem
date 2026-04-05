from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0043_ticketvalidationscan_vendor_staff"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackgroundJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "job_type",
                    models.CharField(
                        choices=[
                            ("NOTIFICATION_EMAIL", "Notification Email"),
                            ("ANALYTICS_MONITOR_EXPORT", "Analytics Monitor Export"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("PROCESSING", "Processing"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error_message", models.CharField(blank=True, max_length=255, null=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveIntegerField(default=3)),
                ("available_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "background_jobs",
                "ordering": ["available_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="backgroundjob",
            index=models.Index(fields=["status", "available_at"], name="bg_job_status_avail_idx"),
        ),
        migrations.AddIndex(
            model_name="backgroundjob",
            index=models.Index(fields=["job_type", "created_at"], name="bg_job_type_created_idx"),
        ),
    ]
