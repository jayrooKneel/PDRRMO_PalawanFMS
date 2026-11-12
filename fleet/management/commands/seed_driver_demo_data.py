from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from fleet.models import Driver


LAND_FIRST_NAMES = (
    'Juan', 'Jose', 'Antonio', 'Ramon', 'Carlos',
    'Miguel', 'Roberto', 'Andres', 'Eduardo', 'Manuel',
)
LAND_SURNAMES = ('Dela Cruz', 'Santos', 'Reyes', 'Garcia', 'Mendoza')
SEA_FIRST_NAMES = (
    'Maria', 'Ana', 'Rosa', 'Luz', 'Carmen',
    'Josefina', 'Elena', 'Teresa', 'Gloria', 'Lourdes',
)
SEA_SURNAMES = ('Bautista', 'Aquino', 'Ramos', 'Castillo', 'Navarro')


def build_driver_records(today):
    records = []
    operator_groups = (
        (
            'LTO',
            LAND_FIRST_NAMES,
            LAND_SURNAMES,
            'DEMO-LTO',
            'A, B, B1',
        ),
        (
            'MARINA',
            SEA_FIRST_NAMES,
            SEA_SURNAMES,
            'MAR-DEMO',
            'MARINA Seafarer Permit',
        ),
    )

    for authority, first_names, surnames, license_prefix, license_class in operator_groups:
        index = 0
        for first_name in first_names:
            for surname in surnames:
                if index < 25:
                    expiry = today - timedelta(days=1 + index)
                elif index < 35:
                    expiry = today + timedelta(days=index - 24)
                else:
                    expiry = today + timedelta(days=365 + index - 35)
                index += 1
                records.append(Driver(
                    name=f'{first_name} {surname}',
                    license_authority=authority,
                    license_number=f'{license_prefix}-{index:04d}',
                    license_class=license_class,
                    license_expiry=expiry,
                    is_active=True,
                ))

    return records


class Command(BaseCommand):
    help = (
        'Replace all driver records with 50 synthetic land drivers and '
        '50 synthetic seacraft operators for demonstration.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing driver records and clear their vehicle assignments.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show the records/status totals without changing the database.',
        )

    def handle(self, *args, **options):
        if not options['replace'] and not options['dry_run']:
            raise CommandError(
                'This operation replaces driver records. Re-run with --replace '
                'to confirm, or use --dry-run to preview.'
            )

        records = build_driver_records(timezone.localdate())
        if len(records) != 100:
            raise CommandError(f'Expected 100 demo operators; generated {len(records)}.')

        today = timezone.localdate()
        expired_count = sum(driver.license_expiry < today for driver in records)
        expiring_count = sum(
            today <= driver.license_expiry <= today + timedelta(days=30)
            for driver in records
        )
        valid_count = len(records) - expired_count

        self.stdout.write(
            f'Prepared {len(records)} synthetic operators: '
            f'50 LTO drivers and 50 MARINA operators; '
            f'{expired_count} expired, {valid_count} valid '
            f'({expiring_count} expire within 30 days).'
        )

        if options['dry_run']:
            self.stdout.write(
                f'Dry run: {Driver.objects.count()} existing driver records '
                'would be replaced; no data was changed.'
            )
            return

        with transaction.atomic():
            Driver.objects.all().delete()
            Driver.objects.bulk_create(records)

        self.stdout.write(self.style.SUCCESS(
            "Replaced existing drivers; deleted drivers' vehicle assignments "
            'were cleared by the foreign-key rule.'
        ))
