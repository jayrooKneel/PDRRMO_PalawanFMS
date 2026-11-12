from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0020_driver_license_details'),
    ]

    operations = [
        migrations.AddField(
            model_name='driver',
            name='license_document',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to='driver_licenses/',
            ),
        ),
    ]
