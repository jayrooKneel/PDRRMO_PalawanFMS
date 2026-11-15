from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0027_remove_driver_license_conditions'),
    ]

    operations = [
        migrations.CreateModel(
            name='DriverLicenseImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.ImageField(upload_to='driver_licenses/')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('driver', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='additional_license_images',
                    to='fleet.driver',
                )),
            ],
        ),
    ]
