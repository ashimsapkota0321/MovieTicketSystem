from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0015_banner_simplify"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="photo_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.RenameField(
            model_name="moviecredit",
            old_name="credit_type",
            new_name="role_type",
        ),
        migrations.RenameField(
            model_name="moviecredit",
            old_name="role_name",
            new_name="character_name",
        ),
        migrations.RenameField(
            model_name="moviecredit",
            old_name="department",
            new_name="job_title",
        ),
        migrations.RenameField(
            model_name="moviecredit",
            old_name="display_order",
            new_name="position",
        ),
        migrations.AlterField(
            model_name="moviecredit",
            name="job_title",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AlterModelOptions(
            name="moviecredit",
            options={"db_table": "movie_credits", "ordering": ["position", "id"]},
        ),
    ]
