from django.db import migrations


def drop_banner_columns_if_exists(apps, schema_editor):
    table_name = "banners"
    vendor = schema_editor.connection.vendor
    if vendor == "sqlite":
        # SQLite drop column support is limited; skip and rely on state-only removal.
        return
    with schema_editor.connection.cursor() as cursor:
        columns = [
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        ]
    table = schema_editor.quote_name(table_name)
    for column in ("display_on", "end_date", "link_url", "priority", "start_date"):
        if column in columns:
            schema_editor.execute(
                f"ALTER TABLE {table} DROP COLUMN {schema_editor.quote_name(column)}"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0014_movie_cast_review"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(drop_banner_columns_if_exists, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AlterModelOptions(
                    name="banner",
                    options={"db_table": "banners", "ordering": ["-created_at"]},
                ),
                migrations.RemoveField(model_name="banner", name="display_on"),
                migrations.RemoveField(model_name="banner", name="end_date"),
                migrations.RemoveField(model_name="banner", name="priority"),
                migrations.RemoveField(model_name="banner", name="start_date"),
            ],
        ),
    ]
