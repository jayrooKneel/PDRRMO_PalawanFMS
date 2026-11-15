from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0025_driver_license_classification'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=[
                        'ALTER TABLE fleet_driver ADD COLUMN emergency_contact_name varchar(100) NOT NULL DEFAULT \'\';',
                        'ALTER TABLE fleet_driver ADD COLUMN emergency_contact_number varchar(20) NOT NULL DEFAULT \'\';',
                    ],
                    reverse_sql=[
                        'ALTER TABLE fleet_driver DROP COLUMN emergency_contact_number;',
                        'ALTER TABLE fleet_driver DROP COLUMN emergency_contact_name;',
                    ],
                ),
            ],
            state_operations=[
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
            ],
        ),
    ]
