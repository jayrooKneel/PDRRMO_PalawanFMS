from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0026_driver_emergency_contact'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE fleet_driver DROP COLUMN license_conditions;',
                    reverse_sql=(
                        'ALTER TABLE fleet_driver ADD COLUMN '
                        "license_conditions text NOT NULL DEFAULT '';"
                    ),
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='driver',
                    name='license_conditions',
                ),
            ],
        ),
    ]
