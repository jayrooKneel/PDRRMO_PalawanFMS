from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0022_vehicle_maintenance_priority'),
    ]

    operations = [
        migrations.AlterField(
            model_name='vehicle',
            name='scheduled_maintenance_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('OIL', 'Oil replacement'),
                    ('TIRES', 'Tire replacement'),
                    ('BRAKES', 'Brake inspection / replacement'),
                    ('BATTERY', 'Battery service / replacement'),
                    ('ENGINE_COOLANT', 'Engine coolant service'),
                    ('AIR_FILTER', 'Air filter replacement'),
                    ('TRANSMISSION', 'Transmission service'),
                    ('BELTS_HOSES', 'Belts and hoses inspection / replacement'),
                    ('REGISTRATION_INSPECTION', 'Registration / safety inspection'),
                    ('ENGINE_SERVICE', 'Marine engine service'),
                    ('PROPELLER', 'Propeller inspection / replacement'),
                    ('HULL', 'Hull inspection / maintenance'),
                    ('BILGE_PUMP', 'Bilge pump inspection / service'),
                    ('FUEL_SYSTEM', 'Fuel system inspection / service'),
                    ('SAFETY_EQUIPMENT', 'Marine safety equipment inspection'),
                    ('COOLING_SYSTEM', 'Cooling system service'),
                    ('OTHER', 'Other maintenance'),
                ],
                max_length=32,
            ),
        ),
    ]
