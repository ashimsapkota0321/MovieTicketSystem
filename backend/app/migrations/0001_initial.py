# Generated migration for initial User model

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(max_length=13, unique=True)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('dob', models.DateField()),
                ('first_name', models.CharField(max_length=50)),
                ('middle_name', models.CharField(blank=True, max_length=50, null=True)),
                ('last_name', models.CharField(max_length=50)),
                ('password', models.CharField(max_length=256)),
                ('date_joined', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'users',
            },
        ),
    ]
