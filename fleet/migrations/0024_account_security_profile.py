from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0023_vehicle_scheduled_maintenance_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountSecurityProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('failed_login_attempts', models.PositiveSmallIntegerField(default=0)),
                ('locked_until', models.DateTimeField(blank=True, null=True)),
                ('security_question', models.CharField(blank=True, max_length=255)),
                ('security_answer_hash', models.CharField(blank=True, max_length=128)),
                ('failed_recovery_attempts', models.PositiveSmallIntegerField(default=0)),
                ('recovery_locked_until', models.DateTimeField(blank=True, null=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='account_security_profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
    ]
