from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0025_driver_license_classification'),
    ]

    operations = [
        migrations.AddField(
            model_name='driver',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='driver',
            name='emergency_contact_number',
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
