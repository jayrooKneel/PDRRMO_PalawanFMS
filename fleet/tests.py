import json
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
import pytesseract
from io import StringIO

from .models import (
    Driver,
    FleetIncident,
    Vehicle,
    VehicleRegistrationDocument,
    VehicleType,
)
from .vehicle_document_ocr import (
    extract_driver_fields_from_text,
    extract_fields_from_text,
)


class SeedDriverDemoDataTests(TestCase):
    def test_seed_replaces_drivers_and_clears_vehicle_assignments(self):
        vehicle_type = VehicleType.objects.create(name='TRUCK')
        old_driver = Driver.objects.create(
            name='Old Demo Driver',
            license_number='OLD-001',
        )
        vehicle = Vehicle.objects.create(
            model_name='Assigned Demo Truck',
            plate_number='DEMO-TRUCK-01',
            vehicle_type=vehicle_type,
            assigned_driver=old_driver,
        )

        call_command(
            'seed_driver_demo_data',
            replace=True,
            stdout=StringIO(),
        )

        today = timezone.localdate()
        self.assertEqual(Driver.objects.count(), 100)
        self.assertEqual(Driver.objects.filter(license_authority='LTO').count(), 50)
        self.assertEqual(Driver.objects.filter(license_authority='MARINA').count(), 50)
        self.assertEqual(Driver.objects.filter(license_expiry__lt=today).count(), 50)
        self.assertEqual(Driver.objects.filter(license_expiry__gte=today).count(), 50)
        self.assertEqual(
            Driver.objects.filter(
                license_expiry__gte=today,
                license_expiry__lte=today + timedelta(days=30),
            ).count(),
            20,
        )
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.assigned_driver)

    def test_seed_requires_confirmation_and_dry_run_does_not_replace_data(self):
        old_driver = Driver.objects.create(
            name='Preserved Demo Driver',
            license_number='KEEP-001',
        )

        with self.assertRaises(CommandError):
            call_command('seed_driver_demo_data', stdout=StringIO())

        call_command('seed_driver_demo_data', dry_run=True, stdout=StringIO())

        self.assertEqual(list(Driver.objects.all()), [old_driver])


class LoginViewTests(TestCase):
    def test_login_page_renders_without_authenticating_on_get(self):
        response = self.client.get(reverse('dashboard_portal:login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fleet Operations Center')
        self.assertNotContains(response, 'ACCESS DENIED: Invalid Username or Password.')

    def test_login_page_shows_error_for_invalid_credentials(self):
        response = self.client.post(
            reverse('dashboard_portal:login'),
            {'username': 'unknown-user', 'password': 'wrong-password'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ACCESS DENIED: Invalid Username or Password.')

    def test_successful_login_and_logout_are_audited(self):
        user = User.objects.create_user(username='audited_user', password='SecurePass123!')

        self.client.post(
            reverse('dashboard_portal:login'),
            {'username': user.username, 'password': 'SecurePass123!'},
        )
        self.client.post(reverse('dashboard_portal:custom_logout'))

        self.assertTrue(LogEntry.objects.filter(user=user, change_message='User logged in successfully.').exists())
        self.assertTrue(LogEntry.objects.filter(user=user, change_message='User logged out.').exists())


class ProgressiveWebAppTests(TestCase):
    def test_manifest_is_served_with_web_app_metadata(self):
        response = self.client.get(reverse('dashboard_portal:pwa_manifest'))
        manifest = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/manifest+json')
        self.assertEqual(manifest['display'], 'standalone')
        self.assertEqual(manifest['scope'], '/')
        self.assertTrue(manifest['icons'])
        png_icon_sizes = {
            icon['sizes']
            for icon in manifest['icons']
            if icon['type'] == 'image/png'
        }
        self.assertEqual(png_icon_sizes, {'192x192', '512x512'})

    def test_service_worker_is_served_with_root_scope_permission(self):
        response = self.client.get(reverse('dashboard_portal:pwa_service_worker'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertContains(response, 'pdrrmo-fms-shell-v11')
        self.assertContains(response, 'requestUrl.pathname.startsWith("/static/")')


class SystemConsoleTests(TestCase):
    def test_vehicle_admin_location_fields_load_palawan_autocomplete(self):
        admin_user = User.objects.create_superuser(
            username='location_admin',
            email='location-admin@example.com',
            password='SecurePass123!',
        )
        vehicle_type = VehicleType.objects.create(name='LAND')
        vehicle = Vehicle.objects.create(
            model_name='Admin Location Vehicle',
            plate_number='ADMIN-LOCATION-01',
            vehicle_type=vehicle_type,
        )
        self.client.force_login(admin_user)

        response = self.client.get(
            reverse('admin:fleet_vehicle_change', args=[vehicle.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="deployment_location"')
        self.assertContains(response, 'name="deployment_destination"')
        self.assertContains(response, 'data-locations-url="/static/fleet/data/palawan_deployment_locations.json"')
        self.assertContains(response, 'src="/static/fleet/js/deployment_location_search.js"')

    def test_console_shows_actions_from_multiple_users(self):
        admin_user = User.objects.create_superuser(
            username='console_admin', email='console@example.com', password='SecurePass123!'
        )
        operator = User.objects.create_user(username='console_operator')
        content_type = ContentType.objects.get_for_model(User)
        for user, message in (
            (admin_user, 'Admin action'),
            (operator, 'Operator action'),
        ):
            LogEntry.objects.create(
                user=user,
                content_type=content_type,
                object_id=str(user.pk),
                object_repr=user.username,
                action_flag=CHANGE,
                change_message=message,
            )

        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin_system_console'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'console_admin')
        self.assertContains(response, 'console_operator')
        self.assertContains(response, 'Operator action')

    def test_console_requires_staff_access(self):
        user = User.objects.create_user(username='non_staff')
        self.client.force_login(user)

        response = self.client.get(reverse('admin_system_console'))

        self.assertEqual(response.status_code, 302)

    def test_console_requires_log_entry_view_permission(self):
        user = User.objects.create_user(username='staff_without_log_permission', is_staff=True)
        self.client.force_login(user)

        response = self.client.get(reverse('admin_system_console'))

        self.assertEqual(response.status_code, 403)

    def test_logistics_dashboard_allows_non_staff_user_in_logistics_group(self):
        group = Group.objects.create(name='Logistics Officers')
        user = User.objects.create_user(username='logistics_user', password='SecurePass123!')
        user.groups.add(group)
        Driver.objects.create(
            name='Management Page Operator',
            license_number='MANAGEMENT-001',
        )
        user.is_staff = False
        user.save()

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="logisticsMenuDrawer"')
        self.assertContains(response, 'data-menu-action="operators"')
        self.assertContains(response, 'data-menu-action="add-operator"')
        self.assertContains(response, 'data-menu-action="manage-operators"')
        self.assertContains(response, 'id="manageOperatorsModal"')
        self.assertContains(response, 'data-edit-operator')
        self.assertContains(response, 'value="archive_operator"')
        self.assertContains(response, 'data-menu-action="add-asset"')
        self.assertContains(response, 'data-menu-action="manage-assets"')
        self.assertContains(response, 'id="manageAssetsModal"')
        self.assertContains(response, 'data-menu-action="print"')
        self.assertContains(response, 'data-menu-action="view-incidents"')
        self.assertNotContains(response, 'id_license_authority')
        self.assertContains(response, 'first selected image is saved to the operator record')
        self.assertContains(response, 'data-operator-documents')
        self.assertContains(response, 'data-operator-document-action="camera"')
        self.assertContains(response, 'data-operator-document-action="upload"')
        self.assertContains(response, 'capture="environment"')
        self.assertContains(response, 'License class / seafarer rank')
        self.assertContains(response, 'License expiry date')
        self.assertContains(response, 'fleet/js/operator_document_ocr.js')
        self.assertContains(response, 'license authority: ${authority} (automatic).')
        self.assertContains(response, 'data-menu-action="generate-report"')
        self.assertContains(response, 'Generate Fleet Report')
        self.assertContains(response, 'src="/static/fleet/js/logistics_menu.js"')
        self.assertContains(response, 'id="fleetIncidentModal"')
        drawer_order = (
            'data-menu-action="add-asset"',
            'data-menu-action="manage-assets"',
            'data-menu-action="operators"',
            'data-menu-action="add-operator"',
            'data-menu-action="file-incident"',
            'data-menu-action="print-incident"',
            'data-menu-action="generate-report"',
            'data-menu-action="print"',
        )
        drawer_positions = [response.content.index(action.encode()) for action in drawer_order]
        self.assertEqual(drawer_positions, sorted(drawer_positions))
        self.assertEqual(response.content.count(b'class="asset-grid logistics-asset-grid"'), 6)
        self.assertContains(response, 'Add a fleet asset')
        self.assertContains(response, 'Plate No. / Official No.')
        self.assertContains(response, 'Choose an asset type')
        self.assertContains(response, 'name="asset-0-registration_documents"')
        self.assertContains(response, 'Land Asset Details — LTO Form 3')
        self.assertContains(response, 'data-ocr-field="engine_number"')
        self.assertContains(response, 'data-ocr-field="vehicle_category"')
        self.assertContains(response, 'data-ocr-field="aircon_type"')
        self.assertContains(response, 'fleet/js/fleet_asset_registration.js')
        lto_field_order = (
            'plate_number',
            'engine_number',
            'chassis_number',
            'mv_file_number',
            'vehicle_category',
            'passenger_capacity',
            'color',
            'fuel_type',
            'vehicle_classification',
            'make',
            'model_name',
            'gross_vehicle_weight',
            'net_capacity',
            'body_type',
            'model_year',
            'engine_displacement_cc',
            'aircon_type',
        )
        field_positions = [
            response.content.index(f'name="asset-0-{field}"'.encode())
            for field in lto_field_order
        ]
        self.assertEqual(field_positions, sorted(field_positions))
        for field_name in (
            'make',
            'model_year',
            'color',
            'engine_details',
            'engine_number',
            'chassis_number',
            'mv_file_number',
            'body_type',
            'gross_vehicle_weight',
            'net_capacity',
            'fuel_type',
            'passenger_capacity',
            'odometer_km',
        ):
            self.assertContains(response, f'name="asset-0-{field_name}"')
        type_position = response.content.index(b'name="asset-0-vehicle_type"')
        document_position = response.content.index(b'name="asset-0-registration_documents"')
        details_position = response.content.index(b'name="asset-0-model_name"')
        self.assertLess(type_position, document_position)
        self.assertLess(document_position, details_position)
        self.assertContains(response, 'Add another asset')
        self.assertContains(response, 'Register assets')

    def test_logistics_can_register_multiple_land_assets_at_once(self):
        group = Group.objects.create(name='Logistics Officers')
        user = User.objects.create_user(username='multi_asset_logistics')
        user.groups.add(group)
        land_type = VehicleType.objects.create(name='LAND')
        self.client.force_login(user)
        payload = {
            'action': 'add_vehicle',
            'asset_count': '2',
        }
        for index, (name, plate) in enumerate((
            ('Rescue Unit One', 'LAND-BULK-01'),
            ('Rescue Unit Two', 'LAND-BULK-02'),
        )):
            prefix = f'asset-{index}-'
            payload.update({
                prefix + 'model_name': name,
                prefix + 'plate_number': plate,
                prefix + 'vehicle_type': str(land_type.pk),
                prefix + 'make': 'Toyota',
                prefix + 'model_year': '2024',
                prefix + 'odometer_km': '0',
            })

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            payload,
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        self.assertContains(response, '2 fleet assets have been registered.')
        self.assertEqual(Vehicle.objects.filter(plate_number__startswith='LAND-BULK-').count(), 2)

    def test_logistics_bulk_registration_is_all_or_nothing_for_duplicate_ids(self):
        group = Group.objects.create(name='Logistics Officers')
        user = User.objects.create_user(username='multi_asset_duplicate')
        user.groups.add(group)
        land_type = VehicleType.objects.create(name='LAND')
        self.client.force_login(user)
        payload = {'action': 'add_vehicle', 'asset_count': '2'}
        for index, name in enumerate(('Rescue Unit One', 'Rescue Unit Two')):
            prefix = f'asset-{index}-'
            payload.update({
                prefix + 'model_name': name,
                prefix + 'plate_number': 'LAND-BULK-DUP',
                prefix + 'vehicle_type': str(land_type.pk),
            })

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            payload,
            follow=True,
        )

        self.assertContains(response, 'Each asset must have a different plate number or hull ID.')
        self.assertFalse(Vehicle.objects.filter(plate_number='LAND-BULK-DUP').exists())

    def test_logistics_registers_land_asset_details_and_displays_them(self):
        group = Group.objects.create(name='Logistics Officers')
        user = User.objects.create_user(username='land_asset_logistics')
        user.groups.add(group)
        land_type = VehicleType.objects.create(name='LAND')
        self.client.force_login(user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'add_vehicle',
                'model_name': 'Land Rescue Unit',
                'plate_number': 'LAND-SPECS-01',
                'vehicle_type': land_type.pk,
                'make': 'Toyota',
                'model_year': '2024',
                'color': 'White',
                'engine_details': '2.8L diesel',
                'fuel_type': 'Diesel',
                'passenger_capacity': '8',
                'odometer_km': '12450.5',
                'registration_expiry': '2027-04-30',
                'inspection_expiry': '2027-03-31',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        vehicle = Vehicle.objects.get(plate_number='LAND-SPECS-01')
        self.assertEqual(vehicle.make, 'Toyota')
        self.assertEqual(vehicle.model_year, 2024)
        self.assertEqual(vehicle.color, 'White')
        self.assertEqual(vehicle.engine_details, '2.8L diesel')
        self.assertEqual(vehicle.fuel_type, 'Diesel')
        self.assertEqual(vehicle.passenger_capacity, 8)
        self.assertEqual(vehicle.odometer_km, Decimal('12450.5'))
        self.assertEqual(vehicle.registration_expiry.isoformat(), '2027-04-30')
        self.assertEqual(vehicle.inspection_expiry.isoformat(), '2027-03-31')
        self.assertContains(response, 'Toyota')
        self.assertContains(response, '12450.5 km')
        self.assertContains(response, 'Registration due Apr 2027')

    def test_logistics_land_asset_registration_rejects_future_model_year(self):
        group = Group.objects.create(name='Logistics Officers')
        user = User.objects.create_user(username='land_asset_validation')
        user.groups.add(group)
        land_type = VehicleType.objects.create(name='LAND')
        self.client.force_login(user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'add_vehicle',
                'model_name': 'Future Model Vehicle',
                'plate_number': 'LAND-FUTURE-01',
                'vehicle_type': land_type.pk,
                'model_year': str(timezone.localdate().year + 1),
            },
            follow=True,
        )

        self.assertContains(response, 'Enter a valid year from 1900 through this year.')
        self.assertFalse(Vehicle.objects.filter(plate_number='LAND-FUTURE-01').exists())

    def test_asset_onboarding_rejects_missing_or_duplicate_details_with_friendly_message(self):
        group = Group.objects.create(name='Logistics Officers')
        user = User.objects.create_user(username='asset_logistics', password='SecurePass123!')
        user.groups.add(group)
        vehicle_type = VehicleType.objects.create(name='LAND')
        existing_vehicle = Vehicle.objects.create(
            model_name='Existing Fleet Vehicle',
            plate_number='PDR-ALS-02',
            vehicle_type=vehicle_type,
        )
        self.client.force_login(user)

        missing_fields_response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {'action': 'add_vehicle', 'model_name': 'New ambulance'},
            follow=True,
        )
        duplicate_identifier_response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'add_vehicle',
                'model_name': 'Replacement ambulance',
                'plate_number': existing_vehicle.plate_number,
                'vehicle_type': vehicle_type.pk,
            },
            follow=True,
        )

        self.assertContains(
            missing_fields_response,
            'Please enter the asset name, plate number or hull ID, and asset type.',
        )
        self.assertContains(
            duplicate_identifier_response,
            "An asset with plate number or hull ID &#x27;PDR-ALS-02&#x27; is already registered.",
        )


class RegistrationOcrTests(TestCase):
    LAND_TEXT = """\
PLATE NO: ABC1234
MAKE/SERIES: TOYOTA INNOVA
YEAR MODEL: 2020
ENGINE NO: 2GD-12345
CHASSIS NO: MHF-98765
MV FILE NO: 1234-567890
VEHICLE CATEGORY: PASSENGER CAR M1
BODY TYPE: WAGON
CLASSIFICATION: GOVERNMENT
FUEL TYPE: DIESEL
AIRCON TYPE: R134A
COLOR: WHITE
PASSENGER CAPACITY: 8
GROSS VEHICLE WEIGHT: 2500
NET WEIGHT: 1000
PISTON DISPLACEMENT: 2755 CC
DATE OF INITIAL REGISTRATION: 2020-05-10
REGISTRATION EXPIRY: 2026-03-22
"""
    SEA_TEXT = """\
VESSEL NAME: M/B RESCUE
OFFICIAL NO: MAR-12345
MAKE: YAMAHA
YEAR BUILT: 2019
ENGINE NO: YAM-987
HULL NO: H-456
VESSEL TYPE: RESCUE BOAT
PORT OF REGISTRY: PUERTO PRINCESA
LENGTH: 12.5 M
GROSS TONNAGE: 8.25
NET TONNAGE: 4.10
HORSEPOWER: 90 HP
"""
    DRIVER_TEXT = """\
LAST NAME: DELA CRUZ
FIRST NAME: JUAN
MIDDLE NAME: SANTOS
LICENSE NO: N01-23-456789
DL CODES: A, B, B1
DATE OF BIRTH: 01/02/1990
ADDRESS: PUERTO PRINCESA, PALAWAN
EXPIRY DATE: 2030/06/19
"""
    MARINA_OPERATOR_TEXT = """\
NAME OF LICENSEE: MARIA SANTOS
CERTIFICATE NO: MRA-9876
SEAFARER RANK: DECK OFFICER
DATE OF BIRTH: 01/02/1990
ADDRESS: PUERTO PRINCESA PALAWAN
VALID UNTIL: 2028-04-30
"""

    def setUp(self):
        import tempfile

        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=self.media_directory.name))
        group = Group.objects.create(name='Logistics Officers')
        self.user = User.objects.create_user(username='ocr_logistics')
        self.user.groups.add(group)
        self.land_type = VehicleType.objects.create(name='LAND')

    @staticmethod
    def uploaded_image(name='orcr.png'):
        image_buffer = BytesIO()
        Image.new('RGB', (160, 80), 'white').save(image_buffer, format='PNG')
        return SimpleUploadedFile(name, image_buffer.getvalue(), content_type='image/png')

    def test_extracts_lto_vehicle_technical_fields_without_owner_data(self):
        fields = extract_fields_from_text(self.LAND_TEXT)

        self.assertEqual(fields['plate_number'], 'ABC1234')
        self.assertEqual(fields['make'], 'Toyota')
        self.assertEqual(fields['model_name'], 'INNOVA')
        self.assertEqual(fields['model_year'], '2020')
        self.assertEqual(fields['engine_number'], '2GD-12345')
        self.assertEqual(fields['chassis_number'], 'MHF-98765')
        self.assertEqual(fields['mv_file_number'], '1234-567890')
        self.assertEqual(fields['vehicle_category'], 'PASSENGER CAR M1')
        self.assertEqual(fields['vehicle_classification'], 'GOVERNMENT')
        self.assertEqual(fields['aircon_type'], 'R134A')
        self.assertEqual(fields['gross_vehicle_weight'], '2500')
        self.assertEqual(fields['net_capacity'], '1000')
        self.assertEqual(fields['engine_displacement_cc'], '2755')
        self.assertEqual(fields['registration_date'], '2020-05-10')
        self.assertEqual(fields['registration_expiry'], '2026-03-22')
        self.assertNotIn('registered_owner', fields)
        self.assertNotIn('address', fields)
        ambiguous_date_fields = extract_fields_from_text(
            'DATE OF INITIAL REGISTRATION: 01/02/2020'
        )
        self.assertNotIn('registration_date', ambiguous_date_fields)

    def test_extracts_adjacent_and_multiline_orcr_labels(self):
        text = """\
PLATE NO. ABC 1234 MAKE / SERIES TOYOTA INNOVA
YEAR MODEL 2020 COLOR WHITE
ENGINE NO.
2GD-12345 CHASSIS NO. MHF-98765
PAX CAPACITY 8 GROSS VEHICLE WEIGHT 2500 KG
REGISTERED OWNER
Maria Example
"""

        fields = extract_fields_from_text(text)

        self.assertEqual(fields['plate_number'], 'ABC 1234')
        self.assertEqual(fields['make'], 'Toyota')
        self.assertEqual(fields['model_name'], 'INNOVA')
        self.assertEqual(fields['model_year'], '2020')
        self.assertEqual(fields['color'], 'WHITE')
        self.assertEqual(fields['engine_number'], '2GD-12345')
        self.assertEqual(fields['chassis_number'], 'MHF-98765')
        self.assertEqual(fields['passenger_capacity'], '8')
        self.assertEqual(fields['gross_vehicle_weight'], '2500')
        self.assertNotIn('Maria Example', fields.values())

    def test_extracts_marina_vessel_fields(self):
        fields = extract_fields_from_text(self.SEA_TEXT, is_seacraft=True)

        self.assertEqual(fields['model_name'], 'M/B RESCUE')
        self.assertEqual(fields['plate_number'], 'MAR-12345')
        self.assertEqual(fields['chassis_number'], 'H-456')
        self.assertEqual(fields['hull_type'], 'RESCUE BOAT')
        self.assertEqual(fields['home_port'], 'PUERTO PRINCESA')
        self.assertEqual(fields['length_m'], '12.5')
        self.assertEqual(fields['gross_tonnage'], '8.25')
        self.assertEqual(fields['net_tonnage'], '4.10')
        self.assertEqual(fields['engine_power_hp'], '90')
        self.assertNotIn('mv_file_number', fields)

    def test_extracts_driver_license_fields_without_birth_date_or_address(self):
        fields = extract_driver_fields_from_text(self.DRIVER_TEXT)

        self.assertEqual(fields, {
            'name': 'JUAN SANTOS DELA CRUZ',
            'license_number': 'N01-23-456789',
            'license_class': 'A, B, B1',
            'license_expiry': '2030-06-19',
        })

    def test_extracts_marina_operator_certificate_and_expiry(self):
        fields = extract_driver_fields_from_text(self.MARINA_OPERATOR_TEXT)

        self.assertEqual(fields, {
            'name': 'MARIA SANTOS',
            'license_number': 'MRA-9876',
            'license_class': 'DECK OFFICER',
            'license_expiry': '2028-04-30',
        })

    def test_driver_document_ocr_endpoint_returns_only_suggested_fields(self):
        self.client.force_login(self.user)
        with patch(
            'fleet.vehicle_document_ocr.pytesseract.image_to_string',
            return_value=self.DRIVER_TEXT,
        ):
            response = self.client.post(
                reverse('dashboard_portal:logistics_operator_document_ocr'),
                {
                    'operator_type': 'LAND',
                    'documents': self.uploaded_image('license.png'),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response.json()['fields']['name'], 'JUAN SANTOS DELA CRUZ')
        self.assertEqual(response.json()['fields']['license_expiry'], '2030-06-19')
        self.assertEqual(
            set(response.json()['fields']),
            {'name', 'license_number', 'license_class', 'license_expiry'},
        )
        self.assertIn('image was not saved', response.json()['message'])
        self.assertFalse(Driver.objects.exists())

        unrelated_user = User.objects.create_user(username='other_operator_ocr_user')
        self.client.force_login(unrelated_user)
        denied = self.client.post(
            reverse('dashboard_portal:logistics_operator_document_ocr'),
            {'operator_type': 'SEA', 'documents': self.uploaded_image()},
        )
        self.assertEqual(denied.status_code, 403)

    def test_ocr_endpoint_returns_lto_suggestions_and_requires_logistics_access(self):
        self.client.force_login(self.user)
        with patch(
            'fleet.vehicle_document_ocr.pytesseract.image_to_string',
            return_value=self.LAND_TEXT,
        ):
            response = self.client.post(
                reverse('dashboard_portal:logistics_registration_ocr'),
                {
                    'vehicle_type': self.land_type.pk,
                    'documents': self.uploaded_image(),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertEqual(response.json()['fields']['plate_number'], 'ABC1234')
        self.assertEqual(response.json()['fields']['make'], 'Toyota')
        self.assertNotIn('registered_owner', response.json()['fields'])

        unrelated_user = User.objects.create_user(username='other_ocr_user')
        self.client.force_login(unrelated_user)
        denied = self.client.post(
            reverse('dashboard_portal:logistics_registration_ocr'),
            {'vehicle_type': self.land_type.pk},
        )
        self.assertEqual(denied.status_code, 403)

    def test_ocr_endpoint_reports_missing_tesseract_and_rejects_invalid_images(self):
        self.client.force_login(self.user)
        with patch(
            'fleet.vehicle_document_ocr.pytesseract.image_to_string',
            side_effect=pytesseract.TesseractNotFoundError(),
        ):
            unavailable = self.client.post(
                reverse('dashboard_portal:logistics_registration_ocr'),
                {
                    'vehicle_type': self.land_type.pk,
                    'documents': self.uploaded_image(),
                },
            )
        invalid = self.client.post(
            reverse('dashboard_portal:logistics_registration_ocr'),
            {
                'vehicle_type': self.land_type.pk,
                'documents': SimpleUploadedFile('not-image.png', b'not an image'),
            },
        )

        self.assertEqual(unavailable.status_code, 503)
        self.assertContains(
            unavailable,
            'Local Tesseract OCR is not installed or configured',
            status_code=503,
        )
        self.assertEqual(invalid.status_code, 400)

    def test_asset_registration_saves_orcr_image_as_private_attachment(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'add_vehicle',
                'asset_count': '1',
                'asset-0-model_name': 'OCR Rescue Unit',
                'asset-0-plate_number': 'OCR-123',
                'asset-0-vehicle_type': self.land_type.pk,
                'asset-0-make': 'Toyota',
                'asset-0-engine_number': 'ENGINE-123',
                'asset-0-chassis_number': 'CHASSIS-123',
                'asset-0-mv_file_number': 'MV-123',
                'asset-0-vehicle_category': 'PASSENGER CAR M1',
                'asset-0-aircon_type': 'R134A',
                'asset-0-registration_documents': self.uploaded_image('lto-cr.png'),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        vehicle = Vehicle.objects.get(plate_number='OCR-123')
        self.assertEqual(vehicle.engine_number, 'ENGINE-123')
        self.assertEqual(vehicle.chassis_number, 'CHASSIS-123')
        self.assertEqual(vehicle.vehicle_category, 'PASSENGER CAR M1')
        self.assertEqual(vehicle.aircon_type, 'R134A')
        document = VehicleRegistrationDocument.objects.get(vehicle=vehicle)
        self.assertTrue(document.file.storage.exists(document.file.name))
        self.assertContains(response, 'OR/CR attachments:')

        download = self.client.get(
            reverse('dashboard_portal:logistics_registration_document', args=[document.pk])
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Cache-Control'], 'private, no-store')
        self.assertEqual(download['X-Content-Type-Options'], 'nosniff')
        download.close()

    def test_asset_registration_preserves_marina_fields(self):
        self.client.force_login(self.user)
        sea_type = VehicleType.objects.create(name='MARINE')
        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'add_vehicle',
                'asset_count': '1',
                'asset-0-model_name': 'M/B Rescue',
                'asset-0-plate_number': 'MAR-456',
                'asset-0-vehicle_type': sea_type.pk,
                'asset-0-make': 'Yamaha',
                'asset-0-model_year': '2019',
                'asset-0-color': 'White',
                'asset-0-engine_number': 'ENG-456',
                'asset-0-chassis_number': 'HULL-456',
                'asset-0-home_port': 'Puerto Princesa',
                'asset-0-hull_type': 'Rescue boat',
                'asset-0-length_m': '12.5',
                'asset-0-gross_tonnage': '8.25',
                'asset-0-net_tonnage': '4.10',
                'asset-0-engine_power_hp': '90',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        vessel = Vehicle.objects.get(plate_number='MAR-456')
        self.assertEqual(vessel.make, 'Yamaha')
        self.assertEqual(vessel.model_year, 2019)
        self.assertEqual(vessel.color, 'White')
        self.assertEqual(vessel.engine_power_hp, Decimal('90'))
        self.assertEqual(vessel.home_port, 'Puerto Princesa')
        self.assertContains(response, 'Gross tonnage: 8.25')


class LogisticsReportExportTests(TestCase):
    def setUp(self):
        group = Group.objects.create(name='Logistics Officers')
        self.user = User.objects.create_user(username='report_logistics', password='SecurePass123!')
        self.user.groups.add(group)
        self.client.force_login(self.user)
        self.land_type = VehicleType.objects.create(name='LAND')
        self.vehicle = Vehicle.objects.create(
            model_name='Report Land Vehicle',
            plate_number='LAND-REPORT-01',
            vehicle_type=self.land_type,
        )
        content_type = ContentType.objects.get_for_model(Vehicle)
        self.event = LogEntry.objects.create(
            user=self.user,
            content_type=content_type,
            object_id=str(self.vehicle.pk),
            object_repr=str(self.vehicle),
            action_flag=CHANGE,
            change_message='Deployed asset unit to Puerto Princesa for Search and Rescue.',
        )
        today = timezone.localdate()
        LogEntry.objects.filter(pk=self.event.pk).update(
            action_time=timezone.make_aware(
                datetime.combine(today, datetime.min.time()),
                timezone.get_current_timezone(),
            )
        )

    def test_dashboard_exposes_asset_edit_and_selected_maintenance_controls(self):
        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="editFleetAssetForm"')
        self.assertContains(response, 'name="edit-asset-model_name"')
        self.assertContains(response, 'data-edit-asset')
        self.assertContains(response, 'data-open-maintenance-report=')
        self.assertContains(response, 'id="report-vehicle"')
        self.assertContains(response, 'All vehicles and seacraft')

    def test_asset_forms_offer_dropdown_suggestions_for_common_details(self):
        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertEqual(response.status_code, 200)
        for suggestion_kind in (
            'make',
            'model-year',
            'lto-classification',
            'fuel-type',
            'gross-weight',
            'engine-model',
        ):
            self.assertContains(response, f'data-suggestion-kind="{suggestion_kind}"')
        self.assertContains(response, 'Choose a suggestion or enter a custom value.')
        self.assertContains(response, 'Dropdown suggestions are available for common values')

    def test_update_vehicle_action_modifies_existing_asset(self):
        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'update_vehicle',
                'vehicle_id': self.vehicle.pk,
                'edit-asset-model_name': 'Updated Report Vehicle',
                'edit-asset-plate_number': self.vehicle.plate_number,
                'edit-asset-vehicle_type': self.land_type.pk,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.model_name, 'Updated Report Vehicle')

    def test_selected_maintenance_report_only_includes_selected_asset(self):
        other_vehicle = Vehicle.objects.create(
            model_name='Other Report Vehicle',
            plate_number='LAND-REPORT-02',
            vehicle_type=self.land_type,
        )
        content_type = ContentType.objects.get_for_model(Vehicle)
        for vehicle, description in (
            (self.vehicle, 'Selected asset maintenance record.'),
            (other_vehicle, 'Other asset maintenance record.'),
        ):
            LogEntry.objects.create(
                user=self.user,
                content_type=content_type,
                object_id=str(vehicle.pk),
                object_repr=str(vehicle),
                action_flag=CHANGE,
                change_message=f'Reported maintenance fault for {vehicle.model_name}: {description}',
            )

        response = self.client.get(
            reverse('dashboard_portal:fleet_activity_report'),
            {
                'report_kind': 'maintenance',
                'format': 'csv',
                'period': 'day',
                'day': timezone.localdate().isoformat(),
                'vehicle_id': self.vehicle.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Selected asset maintenance record.', response.content)
        self.assertNotIn(b'Other asset maintenance record.', response.content)

    def test_logistics_can_edit_incident_report_filed_by_another_user(self):
        reporter = User.objects.create_user(username='other_incident_reporter')
        incident = FleetIncident.objects.create(
            vehicle=self.vehicle,
            incident_type='DAMAGE',
            occurred_at=timezone.now(),
            location='Puerto Princesa',
            description='Reported by another user.',
            reported_by=reporter,
        )

        response = self.client.get(
            reverse('dashboard_portal:fleet_edit_incident', args=[incident.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reported by another user.')

    def test_menu_report_form_offers_periods_and_export_formats(self):
        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))
        rendered = response.content.decode()

        self.assertContains(response, 'data-menu-action="generate-report"')
        self.assertContains(response, 'value="month">Monthly')
        self.assertContains(
            response,
            f'id="report-month" name="month" class="form-control" value="{timezone.localdate():%Y-%m}"',
        )
        self.assertContains(response, 'value="week">Weekly')
        self.assertContains(response, 'value="day">Daily')
        self.assertContains(response, 'value="custom">Custom date range')
        self.assertContains(response, 'name="report_kind"')
        self.assertContains(response, 'name="maintenance_category"')
        self.assertContains(response, 'value="damage">Damage and fault reports')
        self.assertContains(response, 'value="incident">Incident reports')
        self.assertContains(response, 'Report a fleet incident')
        self.assertContains(response, 'name="injury_status"')
        self.assertContains(response, 'name="witnesses"')
        self.assertContains(response, 'name="actions_taken"')
        self.assertContains(response, 'name="follow_up_recommendations"')
        self.assertContains(response, 'value="csv"')
        self.assertContains(response, 'value="xlsx"')
        self.assertContains(response, 'value="pdf"')
        self.assertContains(response, 'action="/fleet/reports/activity/"')
        self.assertContains(response, 'data-menu-action="file-incident"')
        self.assertContains(response, 'data-menu-action="print-incident"')
        self.assertLess(
            rendered.index('</form>', rendered.index('id="generateReportForm"')),
            rendered.index('action="/fleet/reports/incidents/"'),
        )

    def test_logistics_dashboard_lists_filed_incidents_with_per_report_actions(self):
        incident = FleetIncident.objects.create(
            vehicle=self.vehicle,
            incident_type='DAMAGE',
            occurred_at=timezone.now(),
            location='Puerto Princesa',
            description='Front bumper damaged during response.',
            damage_details='Front bumper cracked.',
            injury_status='NO',
            witnesses='Response team',
            actions_taken='Vehicle secured.',
            follow_up_recommendations='Schedule repair.',
            last_assigned_driver='Assigned Land Driver',
            reported_by=self.user,
        )

        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['incident_records']), [incident])
        self.assertContains(response, 'id="filedIncidentReports"')
        self.assertContains(response, 'IR-')
        self.assertContains(response, 'Front bumper damaged during response.')
        self.assertContains(response, 'Assigned Land Driver')
        self.assertContains(response, 'Puerto Princesa')
        self.assertContains(response, 'View report')
        self.assertNotContains(response, 'View, Export or Print')
        self.assertNotContains(response, 'js-open-incident-exports')
        self.assertContains(response, 'title="Print incident report"')
        self.assertContains(response, 'title="Export incident report as PDF"')
        self.assertContains(response, f'incident_id={incident.pk}&amp;format=print')
        self.assertContains(response, f'incident_id={incident.pk}&amp;format=pdf')
        self.assertContains(response, 'value="csv"')
        self.assertContains(response, 'value="xlsx"')
        self.assertContains(response, 'value="pdf"')

        other_incident = FleetIncident.objects.create(
            vehicle=self.vehicle,
            incident_type='BREAKDOWN',
            occurred_at=timezone.now(),
            location='Other location',
            description='Another filed report.',
            reported_by=self.user,
        )
        report_url = reverse('dashboard_portal:fleet_activity_report')
        report_params = {
            'report_kind': 'incident',
            'period': 'day',
            'day': timezone.localtime(incident.occurred_at).date().isoformat(),
            'incident_id': incident.pk,
        }
        printable_report = self.client.get(
            report_url,
            {**report_params, 'format': 'print'},
        )
        self.assertEqual(printable_report.status_code, 200)
        self.assertContains(printable_report, incident.description)
        self.assertNotContains(printable_report, other_incident.description)

        exported_report = self.client.get(
            report_url,
            {**report_params, 'format': 'pdf'},
        )
        self.assertEqual(exported_report.status_code, 200)
        self.assertEqual(exported_report['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', exported_report['Content-Disposition'])
        self.assertTrue(exported_report.content.startswith(b'%PDF'))

    def test_incident_reporting_is_available_on_every_fleet_dashboard(self):
        dashboards = (
            ('Seacraft Dispatch', 'seacraft_dispatch'),
            ('Technicians', 'repairman_dashboard'),
            ('Maritime_Tech', 'seacraft_dashboard'),
        )
        for group_name, dashboard_name in dashboards:
            with self.subTest(dashboard=dashboard_name):
                user = User.objects.create_user(username=f'{dashboard_name}_incident_user')
                user.groups.add(Group.objects.create(name=group_name))
                self.client.force_login(user)

                response = self.client.get(reverse(f'dashboard_portal:{dashboard_name}'))

                self.assertContains(response, 'Report a fleet incident')
                self.assertContains(response, 'action="/fleet/reports/incidents/"')
                self.assertContains(response, 'data-menu-action="file-incident"')
                self.assertContains(response, 'data-menu-action="print-incident"')
                self.assertContains(response, 'name="location"')
                self.assertContains(response, 'palawan_deployment_locations.json')
                self.assertContains(response, 'src="/static/fleet/js/deployment_location_search.js"')
                self.assertContains(response, 'aria-controls="incident-location-suggestions"')
                self.assertContains(response, 'id="incident-location-suggestions"')

        self.client.force_login(self.user)

    def test_dispatch_and_mechanics_can_file_and_print_incident_reports(self):
        sea_type = VehicleType.objects.create(name='MARINE')
        role_assets = (
            ('Seacraft Dispatch', 'dispatch_incident', sea_type, 'SEA-DISPATCH-INCIDENT'),
            ('Technicians', 'land_mechanic_incident', self.land_type, 'LAND-MECHANIC-INCIDENT'),
            ('Maritime_Tech', 'sea_mechanic_incident', sea_type, 'SEA-MECHANIC-INCIDENT'),
        )
        incident_time = timezone.localtime().replace(second=0, microsecond=0)

        for group_name, username, vehicle_type, plate_number in role_assets:
            with self.subTest(role=group_name):
                user = User.objects.create_user(username=username)
                user.groups.add(Group.objects.create(name=group_name))
                vehicle = Vehicle.objects.create(
                    model_name=f'{username} asset',
                    plate_number=plate_number,
                    vehicle_type=vehicle_type,
                )
                self.client.force_login(user)

                submission = self.client.post(
                    reverse('dashboard_portal:fleet_report_incident'),
                    {
                        'vehicle': vehicle.pk,
                        'incident_type': 'DAMAGE',
                        'occurred_at': incident_time.strftime('%Y-%m-%dT%H:%M'),
                        'location': 'Incident test location',
                        'description': 'Incident filed by dashboard role.',
                        'damage_details': 'Test damage details.',
                        'injury_status': 'NO',
                        'witnesses': 'Dispatcher on duty',
                        'actions_taken': 'Asset removed from service.',
                        'follow_up_recommendations': 'Inspect before next deployment.',
                    },
                    follow=True,
                )
                self.assertContains(
                    submission,
                    'Incident report saved and added to fleet incident reports.',
                )

                printed_report = self.client.get(
                    reverse('dashboard_portal:fleet_activity_report'),
                    {
                        'report_kind': 'incident',
                        'period': 'day',
                        'day': timezone.localdate().isoformat(),
                        'format': 'print',
                    },
                )

                self.assertEqual(printed_report.status_code, 200)
                self.assertContains(printed_report, 'Incident Report')
                self.assertContains(printed_report, plate_number)
                self.assertContains(printed_report, 'window.print()')

        self.client.force_login(self.user)

    def test_report_prints_and_exports_csv_xlsx_and_pdf(self):
        today = timezone.localdate()
        iso_year, iso_week, _ = today.isocalendar()
        requests = (
            ('print', {'period': 'day', 'day': today.isoformat()}),
            ('csv', {'period': 'day', 'day': today.isoformat()}),
            ('xlsx', {'period': 'week', 'week': f'{iso_year}-W{iso_week:02d}'}),
            ('pdf', {'period': 'month', 'month': today.strftime('%Y-%m')}),
            ('csv', {
                'period': 'custom',
                'start_date': today.isoformat(),
                'end_date': today.isoformat(),
            }),
        )
        for export_format, params in requests:
            with self.subTest(export_format=export_format, period=params['period']):
                response = self.client.get(
                    reverse('dashboard_portal:logistics_generate_report'),
                    {**params, 'format': export_format},
                )
                self.assertEqual(response.status_code, 200)
                if export_format == 'print':
                    self.assertContains(response, 'Deployment Activity Report')
                    self.assertContains(response, 'window.print()')
                else:
                    self.assertIn('attachment;', response['Content-Disposition'])
                if export_format == 'csv':
                    self.assertIn('text/csv', response['Content-Type'])
                    self.assertIn(b'Report Land Vehicle', response.content)
                elif export_format == 'xlsx':
                    self.assertIn(
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        response['Content-Type'],
                    )
                    from openpyxl import load_workbook

                    workbook = load_workbook(BytesIO(response.content), read_only=True)
                    self.assertEqual(workbook.active['A3'].value, today.strftime('%Y-%m-%d 00:00'))
                    self.assertIn('Report Land Vehicle', workbook.active['D3'].value)
                elif export_format == 'pdf':
                    self.assertEqual(response['Content-Type'], 'application/pdf')
                    self.assertTrue(response.content.startswith(b'%PDF'))

    def test_report_rejects_invalid_range_and_unsupported_format(self):
        reverse_url = reverse('dashboard_portal:logistics_generate_report')
        invalid_range = self.client.get(
            reverse_url,
            {'format': 'csv', 'period': 'custom', 'start_date': '2026-10-09', 'end_date': '2026-10-01'},
        )
        unsupported_format = self.client.get(
            reverse_url,
            {'format': 'doc', 'period': 'day', 'day': timezone.localdate().isoformat()},
        )

        self.assertEqual(invalid_range.status_code, 400)
        self.assertContains(unsupported_format, 'Choose Print, CSV, Excel, or PDF', status_code=400)

    def test_report_requires_logistics_access(self):
        self.client.force_login(User.objects.create_user(username='unauthorized_report_user'))

        response = self.client.get(
            reverse('dashboard_portal:logistics_generate_report'),
            {'format': 'csv', 'period': 'day', 'day': timezone.localdate().isoformat()},
        )

        self.assertRedirects(response, reverse('dashboard_portal:homepage'))

    def test_seacraft_dispatch_can_generate_seacraft_activity_report(self):
        sea_group = Group.objects.create(name='Seacraft Dispatch')
        dispatch_user = User.objects.create_user(username='dispatch_report_user')
        dispatch_user.groups.add(sea_group)
        sea_type = VehicleType.objects.create(name='MARINE')
        sea_vehicle = Vehicle.objects.create(
            model_name='Report Seacraft',
            plate_number='SEA-REPORT-01',
            vehicle_type=sea_type,
        )
        LogEntry.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(Vehicle),
            object_id=str(sea_vehicle.pk),
            object_repr=str(sea_vehicle),
            action_flag=CHANGE,
            change_message='Deployed asset unit to Honda Bay for Search and Rescue.',
        )
        self.client.force_login(dispatch_user)

        response = self.client.get(
            reverse('dashboard_portal:fleet_activity_report'),
            {'format': 'csv', 'period': 'day', 'day': timezone.localdate().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Report Seacraft', response.content)
        self.assertNotIn(b'Report Land Vehicle', response.content)

    def test_logistics_can_submit_and_export_fleet_incident_report(self):
        assigned_driver = Driver.objects.create(
            name='Last Assigned Land Driver',
            license_number='LAND-LAST-001',
        )
        self.vehicle.assigned_driver = assigned_driver
        self.vehicle.save(update_fields=['assigned_driver'])
        sea_vehicle = Vehicle.objects.create(
            model_name='Report Seacraft Incident',
            plate_number='SEA-INCIDENT-01',
            vehicle_type=VehicleType.objects.create(name='MARINE'),
        )
        LogEntry.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(Vehicle),
            object_id=str(sea_vehicle.pk),
            object_repr=str(sea_vehicle),
            action_flag=CHANGE,
            change_message=(
                'Deployed asset unit to Honda Bay for Search and Rescue '
                'with operator Last Assigned Sea Operator.'
            ),
        )
        incident_time = timezone.localtime().replace(second=0, microsecond=0)
        for vehicle, location, description in (
            (self.vehicle, 'Puerto Princesa', 'Vehicle struck debris during response.'),
            (sea_vehicle, 'Honda Bay', 'Vessel equipment was damaged during response.'),
        ):
            response = self.client.post(
                reverse('dashboard_portal:fleet_report_incident'),
                {
                    'vehicle': vehicle.pk,
                    'incident_type': 'DAMAGE',
                    'occurred_at': incident_time.strftime('%Y-%m-%dT%H:%M'),
                    'location': location,
                    'description': description,
                    'damage_details': 'Equipment damage recorded.',
                    'injury_status': 'YES',
                    'injury_details': 'Operator assessed by the medical response team.',
                    'witnesses': 'Response team lead',
                    'actions_taken': 'Asset secured and supervisor notified.',
                    'follow_up_recommendations': 'Complete maintenance inspection.',
                },
                follow=True,
            )
            self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
            self.assertContains(response, 'Incident report saved and added to fleet incident reports.')

        incidents = {
            incident.vehicle_id: incident
            for incident in FleetIncident.objects.select_related('vehicle')
        }
        self.assertEqual(len(incidents), 2)
        self.assertEqual(incidents[self.vehicle.pk].reported_by, self.user)
        self.assertEqual(incidents[self.vehicle.pk].last_assigned_driver, 'Last Assigned Land Driver')
        self.assertEqual(incidents[sea_vehicle.pk].last_assigned_driver, 'Last Assigned Sea Operator')
        self.assertEqual(
            incidents[self.vehicle.pk].injury_details,
            'Operator assessed by the medical response team.',
        )
        self.assertEqual(incidents[self.vehicle.pk].witnesses, 'Response team lead')
        self.assertEqual(
            incidents[self.vehicle.pk].actions_taken,
            'Asset secured and supervisor notified.',
        )
        self.assertEqual(
            incidents[self.vehicle.pk].follow_up_recommendations,
            'Complete maintenance inspection.',
        )

        report_url = reverse('dashboard_portal:fleet_activity_report')
        report_params = {
            'report_kind': 'incident',
            'period': 'day',
            'day': timezone.localdate().isoformat(),
        }
        for report_format in ('print', 'csv', 'xlsx', 'pdf'):
            with self.subTest(format=report_format):
                report = self.client.get(
                    report_url,
                    {**report_params, 'format': report_format},
                )
                self.assertEqual(report.status_code, 200)
                if report_format == 'print':
                    self.assertContains(report, 'Incident Report')
                    self.assertContains(report, 'Puerto Princesa')
                    self.assertContains(report, 'Last Assigned Land Driver')
                    self.assertContains(report, 'Last Assigned Sea Operator')
                    self.assertContains(report, 'Provincial Disaster Risk Reduction and Management Office')
                    self.assertContains(report, 'Prepared by / Date')
                    self.assertContains(report, 'onclick="window.history.back()"')
                    self.assertContains(report, 'Return</button>')
                    self.assertContains(report, 'Print Incident Report')
                    self.assertContains(report, 'Witnesses')
                    self.assertContains(report, 'Response team lead')
                    self.assertContains(report, 'Operator assessed by the medical response team.')
                    self.assertContains(report, 'Asset secured and supervisor notified.')
                    self.assertContains(report, 'Complete maintenance inspection.')
                elif report_format == 'csv':
                    self.assertIn(b'Incident Report', report.content)
                    self.assertIn(b'Puerto Princesa', report.content)
                    self.assertIn(b'Last Assigned Land Driver', report.content)
                    self.assertIn(b'Last Assigned Sea Operator', report.content)
                    self.assertIn(
                        b'Injury / medical details: Operator assessed by the medical response team.',
                        report.content,
                    )
                    self.assertIn(b'Witnesses: Response team lead', report.content)
                    self.assertIn(b'Immediate actions: Asset secured and supervisor notified.', report.content)
                    self.assertIn(b'Follow-up recommendations: Complete maintenance inspection.', report.content)
                elif report_format == 'xlsx':
                    self.assertIn(
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        report['Content-Type'],
                    )
                    self.assertIn('fleet-incident-', report['Content-Disposition'])
                    from openpyxl import load_workbook

                    workbook = load_workbook(BytesIO(report.content), read_only=True)
                    report_details = (
                        workbook.active['E3'].value,
                        workbook.active['E4'].value,
                    )
                    self.assertTrue(any('Puerto Princesa' in value for value in report_details))
                    self.assertEqual(workbook.active['G3'].value, 'Last Assigned Sea Operator')
                    self.assertEqual(workbook.active['G4'].value, 'Last Assigned Land Driver')
                    self.assertIn('Witnesses: Response team lead', workbook.active['E4'].value)
                    self.assertIn(
                        'Operator assessed by the medical response team.',
                        workbook.active['E4'].value,
                    )
                    self.assertIn(
                        'Immediate actions: Asset secured and supervisor notified.',
                        workbook.active['E4'].value,
                    )
                else:
                    self.assertEqual(report['Content-Type'], 'application/pdf')
                    self.assertTrue(report.content.startswith(b'%PDF'))
                    self.assertIn('fleet-incident-', report['Content-Disposition'])

    def test_incident_form_requires_details_when_injuries_are_reported(self):
        response = self.client.post(
            reverse('dashboard_portal:fleet_report_incident'),
            {
                'vehicle': self.vehicle.pk,
                'incident_type': 'ACCIDENT',
                'occurred_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
                'location': 'Test location',
                'description': 'Incident requiring injury details.',
                'injury_status': 'YES',
                'injury_details': '',
            },
            follow=True,
        )

        self.assertContains(
            response,
            'Describe the injuries or medical assistance required.',
        )
        self.assertFalse(FleetIncident.objects.exists())

    def test_damage_report_includes_logged_mechanic_faults(self):
        LogEntry.objects.create(
            user=self.user,
            content_type=ContentType.objects.get_for_model(Vehicle),
            object_id=str(self.vehicle.pk),
            object_repr=str(self.vehicle),
            action_flag=CHANGE,
            change_message='Reported maintenance fault for Report Land Vehicle: Body / onboard equipment: Door damaged.',
        )

        response = self.client.get(
            reverse('dashboard_portal:fleet_activity_report'),
            {
                'report_kind': 'damage',
                'period': 'day',
                'day': timezone.localdate().isoformat(),
                'format': 'csv',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Damage / fault reported', response.content)
        self.assertIn(b'Door damaged', response.content)

    def test_seacraft_technician_cannot_report_incident_for_land_asset(self):
        maritime_group = Group.objects.create(name='Maritime_Tech')
        maritime_user = User.objects.create_user(username='incident_sea_tech')
        maritime_user.groups.add(maritime_group)
        self.client.force_login(maritime_user)

        response = self.client.post(
            reverse('dashboard_portal:fleet_report_incident'),
            {
                'vehicle': self.vehicle.pk,
                'incident_type': 'DAMAGE',
                'occurred_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
                'location': 'Test location',
                'description': 'Unauthorized land asset incident.',
                'damage_details': '',
                'injury_status': 'NO',
            },
            follow=True,
        )

        self.assertFalse(FleetIncident.objects.exists())
        self.assertContains(response, 'Fleet asset: Select a valid choice')

    def test_unauthorized_user_cannot_submit_incident_report(self):
        self.client.force_login(User.objects.create_user(username='blocked_incident_reporter'))

        response = self.client.post(
            reverse('dashboard_portal:fleet_report_incident'),
            {
                'vehicle': self.vehicle.pk,
                'incident_type': 'DAMAGE',
                'occurred_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
                'location': 'Test location',
                'description': 'Unauthorized incident.',
                'injury_status': 'NO',
            },
        )

        self.assertRedirects(response, reverse('dashboard_portal:homepage'))
        self.assertFalse(FleetIncident.objects.exists())


class DispatchDashboardAlignmentTests(TestCase):
    def setUp(self):
        self.marine_type = VehicleType.objects.create(name='MARINE')
        self.maritime_type = VehicleType.objects.create(name='MARITIME')
        self.land_type = VehicleType.objects.create(name='LAND')
        self.seacraft_user = User.objects.create_user(
            username='maritime_dispatcher',
            password='SecurePass123!',
        )
        logistics_group = Group.objects.create(name='Logistics Officers')
        self.logistics_user = User.objects.create_user(
            username='fleet_logistics',
            password='SecurePass123!',
        )
        self.logistics_user.groups.add(logistics_group)
        self.operator = Driver.objects.create(
            name='Qualified Maritime Operator',
            license_number='MAR-001',
        )

    def test_deployment_locations_are_scoped_and_reject_custom_values(self):
        land_vehicle = self.create_vehicle(
            model_name='Scoped Location Land Unit',
            plate_number='LAND-LOCATION-01',
            vehicle_type=self.land_type,
        )
        land_driver = Driver.objects.create(
            name='Scoped Location Land Driver',
            license_number='LTO-LOCATION-01',
        )
        sea_vehicle = self.create_vehicle(
            model_name='Scoped Location Sea Unit',
            plate_number='SEA-LOCATION-01',
            vehicle_type=self.maritime_type,
        )

        self.client.force_login(self.logistics_user)
        logistics_response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))
        self.assertContains(logistics_response, 'Open Admin Data')
        self.assertContains(logistics_response, 'palawan_deployment_locations.json')
        self.assertContains(logistics_response, 'src="/static/fleet/js/deployment_location_search.js"')
        self.assertNotContains(logistics_response, 'maps.googleapis.com')
        land_response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': land_vehicle.pk,
                'driver_id': land_driver.pk,
                'deployment_location': 'Honda Bay',
                'deployment_purpose': 'Logistics Support',
                'deployment_time': '2030-01-02T10:30',
            },
            follow=True,
        )
        self.assertContains(land_response, 'Select a deployment location')
        land_vehicle.refresh_from_db()
        self.assertEqual(land_vehicle.status, 'OPERATIONAL')

        self.client.force_login(self.seacraft_user)
        seacraft_response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))
        self.assertContains(seacraft_response, 'Open Admin Data')
        self.assertContains(seacraft_response, 'palawan_deployment_locations.json')
        self.assertContains(seacraft_response, 'src="/static/fleet/js/deployment_location_search.js"')
        self.assertNotContains(seacraft_response, 'maps.googleapis.com')
        sea_response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': sea_vehicle.pk,
                'driver_id': self.operator.pk,
                'deployment_location': 'Coron Bay',
                'deployment_purpose': 'Search and Rescue',
                'deployment_time': '2030-01-02T10:30',
            },
            follow=True,
        )
        self.assertContains(sea_response, 'Select a deployment location')
        sea_vehicle.refresh_from_db()
        self.assertEqual(sea_vehicle.status, 'OPERATIONAL')

    def test_logistics_deployment_modal_receives_active_land_operator_data(self):
        Driver.objects.create(
            name='Available Land Deployment Driver',
            license_number='LTO-DEPLOY-AVAILABLE',
            license_expiry=timezone.localdate() + timedelta(days=60),
        )
        Driver.objects.create(
            name='Expired Land Deployment Driver',
            license_number='LTO-DEPLOY-EXPIRED',
            license_expiry=timezone.localdate() - timedelta(days=1),
        )
        self.create_vehicle(
            model_name='Deployment Operator Test Vehicle',
            plate_number='LAND-DEPLOY-OPERATORS',
            vehicle_type=self.land_type,
        )
        self.client.force_login(self.logistics_user)

        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'src="/static/fleet/js/logistics_deployment.js"')
        self.assertContains(response, '"name": "Available Land Deployment Driver"')
        self.assertContains(response, '"name": "Expired Land Deployment Driver"')
        self.assertContains(response, '"license_expired": true')

    def create_vehicle(self, *, model_name, plate_number, vehicle_type, **kwargs):
        return Vehicle.objects.create(
            model_name=model_name,
            plate_number=plate_number,
            vehicle_type=vehicle_type,
            **kwargs,
        )

    def test_public_active_deployments_are_ordered_newest_first_across_divisions(self):
        older_land = self.create_vehicle(
            model_name='Older Land Deployment',
            plate_number='LAND-OLDER-01',
            vehicle_type=self.land_type,
            status='DEPLOYED',
            deployment_time=timezone.make_aware(datetime(2030, 1, 2, 10, 30)),
        )
        newest_seacraft = self.create_vehicle(
            model_name='Newest Sea Deployment',
            plate_number='SEA-NEWEST-01',
            vehicle_type=self.maritime_type,
            status='DEPLOYED',
            deployment_time=timezone.make_aware(datetime(2030, 1, 3, 10, 30)),
        )
        undated_land = self.create_vehicle(
            model_name='Undated Land Deployment',
            plate_number='LAND-UNDATED-01',
            vehicle_type=self.land_type,
            status='DEPLOYED',
        )

        response = self.client.get(reverse('dashboard_portal:homepage'))

        self.assertEqual(response.status_code, 200)
        active_deployments = response.content.decode().split('ACTIVE FIELD DEPLOYMENTS', 1)[1]
        active_deployments = active_deployments.split('</table>', 1)[0]
        newest_position = active_deployments.index(newest_seacraft.plate_number)
        older_position = active_deployments.index(older_land.plate_number)
        undated_position = active_deployments.index(undated_land.plate_number)
        self.assertLess(newest_position, older_position)
        self.assertLess(older_position, undated_position)

    def test_public_homepage_shows_vehicle_type_and_available_operator_totals(self):
        truck_type = VehicleType.objects.create(name='Truck')
        equipment_type = VehicleType.objects.create(name='Heavy Equipment')
        self.create_vehicle(
            model_name='Public Dashboard Truck',
            plate_number='PUBLIC-TRUCK-01',
            vehicle_type=truck_type,
            status='OPERATIONAL',
        )
        self.create_vehicle(
            model_name='Public Dashboard Equipment',
            plate_number='PUBLIC-EQUIPMENT-01',
            vehicle_type=equipment_type,
            status='DEPLOYED',
        )
        self.create_vehicle(
            model_name='Public Dashboard Seacraft',
            plate_number='PUBLIC-SEACRAFT-01',
            vehicle_type=self.marine_type,
            status='MAINTENANCE',
        )
        Driver.objects.create(name='Available Land Driver')
        Driver.objects.create(name='Inactive Land Driver', is_active=False)
        Driver.objects.create(
            name='Inactive Seacraft Operator',
            license_number='MAR-002',
            is_active=False,
        )

        response = self.client.get(reverse('dashboard_portal:homepage'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['available_land_driver_count'], 1)
        self.assertEqual(response.context['available_seacraft_operator_count'], 1)
        self.assertEqual(
            response.context['operational_type_breakdown'],
            [{'name': 'Truck', 'count': 1}],
        )
        self.assertEqual(
            response.context['deployed_type_breakdown'],
            [{'name': 'Heavy Equipment', 'count': 1}],
        )
        self.assertEqual(
            response.context['maintenance_type_breakdown'],
            [{'name': 'MARINE', 'count': 1}],
        )
        self.assertContains(response, 'Land Drivers')
        self.assertContains(response, 'Seacraft Operators')
        self.assertContains(response, 'Heavy Equipment:')

    def test_logistics_can_add_land_drivers_and_seacraft_operators(self):
        self.client.force_login(self.logistics_user)
        for name, operator_type, license_number, expected_authority in (
            ('New Land Driver', 'LAND', 'N01-23-456789', 'LTO'),
            ('New Sea Operator', 'SEA', 'MRA-100', 'MARINA'),
        ):
            with self.subTest(operator=name):
                response = self.client.post(
                    reverse('dashboard_portal:logistics_dashboard'),
                    {
                        'action': 'add_operator',
                        'operator_type': operator_type,
                        'name': name,
                        'license_number': license_number,
                        'license_class': 'A, B',
                        'license_expiry': '2030-06-19',
                        'phone_number': '555-0100',
                    },
                )
                self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
                operator = Driver.objects.get(name=name)
                self.assertEqual(operator.license_authority, expected_authority)
                self.assertEqual(operator.license_number, license_number)
                self.assertEqual(operator.license_class, 'A, B')
                self.assertEqual(operator.license_expiry.isoformat(), '2030-06-19')
                self.assertEqual(operator.phone_number, '555-0100')

    def test_driver_license_image_is_saved_viewable_editable_and_archivable(self):
        image_bytes = BytesIO()
        Image.new('RGB', (12, 12), color='blue').save(image_bytes, format='PNG')
        image_file = SimpleUploadedFile(
            'license.png',
            image_bytes.getvalue(),
            content_type='image/png',
        )
        self.client.force_login(self.logistics_user)
        dashboard_url = reverse('dashboard_portal:logistics_dashboard')

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                create_response = self.client.post(
                    dashboard_url,
                    {
                        'action': 'add_operator',
                        'operator_type': 'LAND',
                        'name': 'Stored License Operator',
                        'license_number': 'LTO-STORE-001',
                        'license_class': 'A, B',
                        'license_expiry': '2032-05-01',
                        'phone_number': '09170000000',
                        'license_scan_complete': 'true',
                        'license_document_images': image_file,
                    },
                )
                self.assertRedirects(create_response, dashboard_url)
                operator = Driver.objects.get(name='Stored License Operator')
                self.assertTrue(operator.license_document.name.startswith('driver_licenses/'))
                license_response = self.client.get(
                    reverse(
                        'dashboard_portal:logistics_driver_license_document',
                        args=[operator.pk],
                    )
                )
                self.assertEqual(license_response.status_code, 200)
                self.assertEqual(license_response['Content-Type'], 'image/png')
                self.assertEqual(license_response['Cache-Control'], 'private, no-store')
                license_response.close()

                update_response = self.client.post(
                    dashboard_url,
                    {
                        'action': 'update_operator',
                        'driver_id': operator.pk,
                        'operator_type': 'LAND',
                        'name': 'Updated License Operator',
                        'license_number': 'LTO-STORE-002',
                        'license_class': 'A, B, C',
                        'license_expiry': '2033-05-01',
                        'phone_number': '09170000001',
                    },
                )
                self.assertRedirects(update_response, dashboard_url)
                operator.refresh_from_db()
                self.assertEqual(operator.name, 'Updated License Operator')
                self.assertTrue(operator.license_document)

                vehicle = self.create_vehicle(
                    model_name='Operator Archive Test Vehicle',
                    plate_number='LAND-ARCHIVE-01',
                    vehicle_type=self.land_type,
                    assigned_driver=operator,
                )
                archive_response = self.client.post(
                    dashboard_url,
                    {
                        'action': 'archive_operator',
                        'driver_id': operator.pk,
                    },
                    follow=True,
                )
                self.assertRedirects(archive_response, dashboard_url)
                operator.refresh_from_db()
                vehicle.refresh_from_db()
                self.assertFalse(operator.is_active)
                self.assertIsNone(vehicle.assigned_driver)
                self.assertTrue(operator.license_document)

    def test_driver_license_view_requires_logistics_access(self):
        image_bytes = BytesIO()
        Image.new('RGB', (12, 12), color='blue').save(image_bytes, format='PNG')
        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                driver = Driver.objects.create(
                    name='Private License Operator',
                    license_number='LTO-PRIVATE-001',
                )
                driver.license_document.save(
                    'private-license.png',
                    SimpleUploadedFile(
                        'private-license.png',
                        image_bytes.getvalue(),
                        content_type='image/png',
                    ),
                )
                self.client.force_login(
                    User.objects.create_user(username='unauthorized_license_viewer')
                )
                response = self.client.get(
                    reverse(
                        'dashboard_portal:logistics_driver_license_document',
                        args=[driver.pk],
                    )
                )

        self.assertEqual(response.status_code, 403)

    def test_driver_scan_image_must_be_processed_before_submitting_and_is_not_saved(self):
        self.client.force_login(self.logistics_user)
        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'add_operator',
                'operator_type': 'LAND',
                'name': 'Unscanned License Operator',
                'license_number': 'ABC-12345',
                'license_document_images': SimpleUploadedFile(
                    'license.png',
                    b'not persisted',
                    content_type='image/png',
                ),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        self.assertFalse(Driver.objects.filter(name='Unscanned License Operator').exists())
        self.assertContains(response, 'Scan the selected license image and wait for OCR to finish before saving.')

    def test_logistics_sets_authority_from_operator_type_without_user_input(self):
        self.client.force_login(self.logistics_user)
        for operator_type, name, authority in (
            ('SEA', 'Automatically Maritime Authority', 'MARINA'),
            ('LAND', 'Automatically Land Authority', 'LTO'),
        ):
            with self.subTest(operator_type=operator_type):
                response = self.client.post(
                    reverse('dashboard_portal:logistics_dashboard'),
                    {
                        'action': 'add_operator',
                        'operator_type': operator_type,
                        'name': name,
                        'license_number': 'TEST-123456',
                        'license_authority': 'LTO' if operator_type == 'SEA' else 'MARINA',
                    },
                )

                self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
                operator = Driver.objects.get(name=name)
                self.assertEqual(operator.license_authority, authority)

    def test_logistics_preserves_license_number_as_entered(self):
        self.client.force_login(self.logistics_user)
        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'add_operator',
                'operator_type': 'SEA',
                'name': 'Marina License Operator',
                'license_number': 'MRA-601',
            },
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        operator = Driver.objects.get(name='Marina License Operator')
        self.assertEqual(operator.license_authority, 'MARINA')
        self.assertEqual(operator.license_number, 'MRA-601')

    def test_logistics_assignment_drawer_saves_on_dropdown_change(self):
        vehicle = self.create_vehicle(
            model_name='Assignment Drawer Test Vehicle',
            plate_number='LAND-DRAWER-01',
            vehicle_type=self.land_type,
        )
        self.client.force_login(self.logistics_user)
        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertNotContains(response, 'Save All Operator Assignments')
        self.assertContains(response, 'data-driver-assignment-form')
        self.assertContains(response, 'data-assignment-status')
        self.assertNotContains(response, 'onchange="this.form.submit()"')
        self.assertNotContains(response, 'name="action" value="set_driver"')
        self.assertContains(
            response,
            reverse('dashboard_portal:logistics_assign_driver', args=[vehicle.pk]),
        )

    def test_driver_assignment_lists_are_alphabetical_across_statuses(self):
        land_zulu = Driver.objects.create(
            name='Zulu Expired Driver',
            license_number='LAND-ALPHA-03',
            license_expiry=timezone.localdate() - timedelta(days=1),
        )
        land_assigned = Driver.objects.create(
            name='Bravo Assigned Driver',
            license_number='LAND-ALPHA-02',
        )
        Driver.objects.create(
            name='Alpha Available Driver',
            license_number='LAND-ALPHA-01',
        )
        self.create_vehicle(
            model_name='Already Assigned Vehicle',
            plate_number='LAND-ALPHA-VEHICLE',
            vehicle_type=self.land_type,
            assigned_driver=land_assigned,
        )
        self.create_vehicle(
            model_name='Expired Assignment Vehicle',
            plate_number='LAND-ALPHA-EXPIRED',
            vehicle_type=self.land_type,
            assigned_driver=land_zulu,
        )

        sea_assigned = Driver.objects.create(
            name='Sierra Assigned Operator',
            license_number='MAR-ALPHA-02',
        )
        Driver.objects.create(
            name='Charlie Available Operator',
            license_number='MAR-ALPHA-01',
        )
        self.create_vehicle(
            model_name='Assigned Seacraft',
            plate_number='SEA-ALPHA-01',
            vehicle_type=self.marine_type,
            assigned_driver=sea_assigned,
        )

        self.client.force_login(self.logistics_user)
        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertEqual(
            [driver.name for driver in response.context['land_drivers']],
            ['Alpha Available Driver', 'Bravo Assigned Driver', 'Zulu Expired Driver'],
        )
        self.assertEqual(
            [driver.name for driver in response.context['sea_drivers']],
            ['Charlie Available Operator', 'Qualified Maritime Operator', 'Sierra Assigned Operator'],
        )

    def test_seacraft_dispatch_assignment_operators_are_alphabetical(self):
        Driver.objects.create(name='Zulu Marina Operator', license_number='MAR-ZULU')
        Driver.objects.create(name='Alpha Marina Operator', license_number='MAR-ALPHA')

        self.client.force_login(self.seacraft_user)
        response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [driver.name for driver in response.context['drivers']],
            ['Alpha Marina Operator', 'Qualified Maritime Operator', 'Zulu Marina Operator'],
        )

    def test_ajax_driver_assignment_keeps_drawer_open_and_returns_json(self):
        driver = Driver.objects.create(
            name='AJAX Assignment Driver',
            license_number='LAND-AJAX-01',
        )
        vehicle = self.create_vehicle(
            model_name='AJAX Assignment Vehicle',
            plate_number='LAND-AJAX-01',
            vehicle_type=self.land_type,
        )
        self.client.force_login(self.logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'set_driver',
                'vehicle_id': vehicle.pk,
                'driver_id': driver.pk,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            HTTP_ACCEPT='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json()['driver_id'], driver.pk)
        self.assertEqual(response.json()['vehicle_id'], vehicle.pk)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.assigned_driver, driver)

    def test_logistics_driver_assignment_endpoint_saves_assignment(self):
        driver = Driver.objects.create(
            name='Dedicated Endpoint Driver',
            license_number='LAND-ENDPOINT-01',
        )
        vehicle = self.create_vehicle(
            model_name='Dedicated Endpoint Vehicle',
            plate_number='LAND-ENDPOINT-01',
            vehicle_type=self.land_type,
        )
        self.client.force_login(self.logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_assign_driver', args=[vehicle.pk]),
            {'driver_id': driver.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['vehicle_id'], vehicle.pk)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.assigned_driver, driver)

    def test_logistics_driver_assignment_endpoint_returns_json_for_missing_vehicle(self):
        self.client.force_login(self.logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_assign_driver', args=[999999]),
            {'driver_id': ''},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()['ok'])
        self.assertIn('no longer exists', response.json()['message'])

    def test_logistics_driver_assignment_endpoint_reports_assignment_conflict(self):
        driver = Driver.objects.create(
            name='Already Assigned Endpoint Driver',
            license_number='LAND-ENDPOINT-02',
        )
        self.create_vehicle(
            model_name='Existing Assigned Endpoint Vehicle',
            plate_number='LAND-ENDPOINT-EXISTING',
            vehicle_type=self.land_type,
            assigned_driver=driver,
        )
        target_vehicle = self.create_vehicle(
            model_name='Target Endpoint Vehicle',
            plate_number='LAND-ENDPOINT-TARGET',
            vehicle_type=self.land_type,
        )
        self.client.force_login(self.logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_assign_driver', args=[target_vehicle.pk]),
            {'driver_id': driver.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()['ok'])
        self.assertIn('already assigned', response.json()['message'])
        target_vehicle.refresh_from_db()
        self.assertIsNone(target_vehicle.assigned_driver)

    def test_ajax_driver_assignment_returns_validation_errors_without_redirect(self):
        expired_driver = Driver.objects.create(
            name='AJAX Expired Driver',
            license_number='LAND-AJAX-EXPIRED',
            license_expiry=timezone.localdate() - timedelta(days=1),
        )
        vehicle = self.create_vehicle(
            model_name='AJAX Expired Assignment Vehicle',
            plate_number='LAND-AJAX-EXPIRED',
            vehicle_type=self.land_type,
        )
        self.client.force_login(self.logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'set_driver',
                'vehicle_id': vehicle.pk,
                'driver_id': expired_driver.pk,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertIn('Assignment denied', response.json()['message'])
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.assigned_driver)

    def test_expired_assigned_operator_is_red_disabled_and_alerted(self):
        today = timezone.localdate()
        expired_driver = Driver.objects.create(
            name='Expired Land Operator',
            license_number='LAND-EXPIRED-01',
            license_expiry=today - timedelta(days=1),
        )
        expiring_driver = Driver.objects.create(
            name='Expiring Land Operator',
            license_number='LAND-EXPIRING-01',
            license_expiry=today + timedelta(days=30),
        )
        expired_vehicle = self.create_vehicle(
            model_name='Expired License Assignment Vehicle',
            plate_number='LAND-EXPIRED-01',
            vehicle_type=self.land_type,
            assigned_driver=expired_driver,
        )
        expiring_vehicle = self.create_vehicle(
            model_name='Expiring License Assignment Vehicle',
            plate_number='LAND-EXPIRING-01',
            vehicle_type=self.land_type,
            assigned_driver=expiring_driver,
        )
        self.client.force_login(self.logistics_user)

        response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['driver'] for item in response.context['expired_assigned_drivers']],
            [expired_driver],
        )
        self.assertEqual(
            [item['driver'] for item in response.context['expiring_assigned_drivers']],
            [expiring_driver],
        )
        self.assertContains(response, 'Expired operator licenses')
        self.assertContains(response, 'License expiry reminders')
        self.assertContains(response, 'id="expired-license-alert"')
        self.assertContains(response, 'id="expiring-license-alert"')
        self.assertContains(response, 'data-bs-dismiss="alert"')
        self.assertEqual(response.content.count(b'data-license-refresh="true">Fix now!</button>'), 2)
        self.assertContains(response, 'Expired Land Operator')
        self.assertContains(response, 'Expiring Land Operator')
        self.assertContains(
            response,
            'class="text-danger fw-bold" style="color: #dc3545; font-weight: 700;" disabled selected',
        )

    def test_expired_operator_cannot_be_assigned_or_dispatched(self):
        expired_driver = Driver.objects.create(
            name='Expired Dispatch Operator',
            license_number='LAND-EXPIRED-02',
            license_expiry=timezone.localdate() - timedelta(days=1),
        )
        vehicle = self.create_vehicle(
            model_name='Expired Dispatch Test Vehicle',
            plate_number='LAND-EXPIRED-02',
            vehicle_type=self.land_type,
        )
        self.client.force_login(self.logistics_user)
        dashboard_url = reverse('dashboard_portal:logistics_dashboard')

        assignment_response = self.client.post(
            dashboard_url,
            {
                'action': 'set_driver',
                'vehicle_id': vehicle.pk,
                'driver_id': expired_driver.pk,
            },
            follow=True,
        )
        self.assertContains(assignment_response, 'Assignment denied')
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.assigned_driver)

        dispatch_response = self.client.post(
            dashboard_url,
            {
                'action': 'deploy_vehicle',
                'vehicle_id': vehicle.pk,
                'driver_id': expired_driver.pk,
                'deployment_location': 'Bancao-bancao, Puerto Princesa City, Palawan',
                'deployment_purpose': 'Search and Rescue',
                'deployment_time': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            },
            follow=True,
        )
        self.assertContains(dispatch_response, 'DISPATCH DENIED')
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.status, 'OPERATIONAL')
        self.assertIsNone(vehicle.assigned_driver)

    def test_logistics_dropdown_changes_save_land_and_seacraft_assignments(self):
        land_operator = Driver.objects.create(
            name='Bulk Land Operator',
            license_number='LAND-500',
        )
        land_vehicle = self.create_vehicle(
            model_name='Bulk Assigned Land Vehicle',
            plate_number='LAND-BULK-01',
            vehicle_type=self.land_type,
        )
        seacraft = self.create_vehicle(
            model_name='Bulk Assigned Seacraft',
            plate_number='SEA-BULK-01',
            vehicle_type=self.marine_type,
        )
        self.client.force_login(self.logistics_user)

        land_response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'set_driver',
                'vehicle_id': land_vehicle.pk,
                'driver_id': land_operator.pk,
            },
        )
        sea_response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'set_driver',
                'vehicle_id': seacraft.pk,
                'driver_id': self.operator.pk,
            },
        )

        self.assertRedirects(land_response, reverse('dashboard_portal:logistics_dashboard'))
        self.assertRedirects(sea_response, reverse('dashboard_portal:logistics_dashboard'))
        land_vehicle.refresh_from_db()
        seacraft.refresh_from_db()
        self.assertEqual(land_vehicle.assigned_driver, land_operator)
        self.assertEqual(seacraft.assigned_driver, self.operator)

    def test_logistics_dropdown_rejects_operator_already_assigned_elsewhere(self):
        first_vehicle = self.create_vehicle(
            model_name='First Bulk Land Vehicle',
            plate_number='LAND-BULK-02',
            vehicle_type=self.land_type,
        )
        second_vehicle = self.create_vehicle(
            model_name='Second Bulk Land Vehicle',
            plate_number='LAND-BULK-03',
            vehicle_type=self.land_type,
        )
        land_operator = Driver.objects.create(
            name='Duplicate Bulk Land Operator',
            license_number='LAND-501',
        )
        self.client.force_login(self.logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'set_driver',
                'vehicle_id': first_vehicle.pk,
                'driver_id': land_operator.pk,
            },
        )
        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'set_driver',
                'vehicle_id': second_vehicle.pk,
                'driver_id': land_operator.pk,
            },
            follow=True,
        )

        self.assertContains(response, 'already assigned to active fleet asset')
        first_vehicle.refresh_from_db()
        second_vehicle.refresh_from_db()
        self.assertEqual(first_vehicle.assigned_driver, land_operator)
        self.assertIsNone(second_vehicle.assigned_driver)

    def test_seacraft_dispatch_can_add_only_maritime_operators(self):
        self.client.force_login(self.seacraft_user)
        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'add_operator',
                'name': 'Dispatch Added Operator',
                'license_number': 'MRA-300',
                'phone_number': '555-0300',
            },
        )

        self.assertRedirects(response, reverse('dashboard_portal:seacraft_dispatch'))
        operator = Driver.objects.get(name='Dispatch Added Operator')
        self.assertEqual(operator.license_authority, 'MARINA')
        self.assertEqual(operator.license_number, 'MRA-300')

    def test_seacraft_dispatch_lists_only_seacraft_incidents_with_row_actions(self):
        seacraft = self.create_vehicle(
            model_name='Incident Test Vessel',
            plate_number='SEA-INCIDENT-01',
            vehicle_type=self.marine_type,
        )
        land_vehicle = self.create_vehicle(
            model_name='Incident Test Land Vehicle',
            plate_number='LAND-INCIDENT-01',
            vehicle_type=self.land_type,
        )
        incident = FleetIncident.objects.create(
            vehicle=seacraft,
            incident_type='BREAKDOWN',
            occurred_at=timezone.now(),
            location='Honda Bay',
            description='Engine stopped during patrol.',
            damage_details='Fuel line inspection required.',
            injury_status='NO',
            last_assigned_driver='Seacraft Test Operator',
            reported_by=self.seacraft_user,
        )
        land_incident = FleetIncident.objects.create(
            vehicle=land_vehicle,
            incident_type='DAMAGE',
            occurred_at=timezone.now(),
            location='Puerto Princesa',
            description='Land vehicle report should not appear.',
        )
        self.client.force_login(self.seacraft_user)

        response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['incident_records']), [incident])
        self.assertContains(response, 'Filed Seacraft Incident Reports')
        self.assertContains(response, 'Engine stopped during patrol.')
        self.assertContains(response, 'Fuel line inspection required.')
        self.assertContains(response, 'Seacraft Test Operator')
        self.assertContains(response, 'title="Print incident report"')
        self.assertContains(response, 'title="Export incident report as PDF"')
        self.assertContains(response, f'incident_id={incident.pk}&amp;format=print')
        self.assertContains(response, f'incident_id={incident.pk}&amp;format=pdf')
        self.assertContains(response, 'data-menu-action="view-incidents"')
        self.assertNotContains(response, land_incident.description)

        report_params = {
            'report_kind': 'incident',
            'period': 'day',
            'day': timezone.localtime(incident.occurred_at).date().isoformat(),
            'incident_id': incident.pk,
        }
        printable_report = self.client.get(
            reverse('dashboard_portal:fleet_activity_report'),
            {**report_params, 'format': 'print'},
        )
        self.assertEqual(printable_report.status_code, 200)
        self.assertContains(printable_report, incident.description)
        self.assertNotContains(printable_report, land_incident.description)

        exported_report = self.client.get(
            reverse('dashboard_portal:fleet_activity_report'),
            {**report_params, 'format': 'pdf'},
        )
        self.assertEqual(exported_report.status_code, 200)
        self.assertEqual(exported_report['Content-Type'], 'application/pdf')
        self.assertTrue(exported_report.content.startswith(b'%PDF'))

    def test_seacraft_dispatch_can_register_seacraft_from_menu(self):
        self.client.force_login(self.seacraft_user)
        dashboard = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertContains(dashboard, 'data-menu-action="add-seacraft"')
        self.assertContains(dashboard, 'id="addSeacraftModal"')
        self.assertContains(dashboard, 'modal-dialog-centered modal-dialog-scrollable')
        self.assertContains(dashboard, '#addSeacraftModal .modal-content > form > .modal-body')
        drawer_order = (
            'data-menu-action="add-seacraft"',
            'data-menu-action="add-operator"',
            'data-menu-action="file-incident"',
            'data-menu-action="print-incident"',
            'data-menu-action="generate-report"',
            'data-menu-action="print"',
        )
        drawer_positions = [dashboard.content.index(action.encode()) for action in drawer_order]
        self.assertEqual(drawer_positions, sorted(drawer_positions))
        self.assertContains(dashboard, f'value="{self.marine_type.pk}">MARINE</option>')
        self.assertNotContains(dashboard, f'value="{self.land_type.pk}">LAND</option>')
        for field_name in (
            'hull_type',
            'length_m',
            'passenger_capacity',
            'engine_details',
            'fuel_type',
            'registration_expiry',
            'inspection_expiry',
        ):
            self.assertContains(dashboard, f'name="craft-0-{field_name}"')
        self.assertContains(dashboard, 'Add another seacraft')

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'add_seacraft',
                'model_name': 'New Dispatch Vessel',
                'plate_number': 'SEA-NEW-01',
                'vehicle_type': self.marine_type.pk,
                'hull_type': 'Rigid-hulled inflatable boat',
                'length_m': '7.25',
                'passenger_capacity': '12',
                'engine_details': 'Yamaha 150 HP',
                'fuel_type': 'Gasoline',
                'registration_expiry': '2027-06-30',
                'inspection_expiry': '2027-04-15',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:seacraft_dispatch'))
        self.assertContains(response, "Seacraft &#x27;New Dispatch Vessel&#x27; registered.")
        craft = Vehicle.objects.get(plate_number='SEA-NEW-01')
        self.assertEqual(craft.model_name, 'New Dispatch Vessel')
        self.assertEqual(craft.vehicle_type, self.marine_type)
        self.assertEqual(craft.status, 'OPERATIONAL')
        self.assertEqual(craft.hull_type, 'Rigid-hulled inflatable boat')
        self.assertEqual(craft.length_m, Decimal('7.25'))
        self.assertEqual(craft.passenger_capacity, 12)
        self.assertEqual(craft.engine_details, 'Yamaha 150 HP')
        self.assertEqual(craft.fuel_type, 'Gasoline')
        self.assertEqual(craft.registration_expiry.isoformat(), '2027-06-30')
        self.assertEqual(craft.inspection_expiry.isoformat(), '2027-04-15')
        self.assertContains(response, 'Rigid-hulled inflatable boat')
        self.assertContains(response, 'Yamaha 150 HP')
        self.assertContains(response, '12 passengers')
        self.assertTrue(
            LogEntry.objects.filter(
                content_type=ContentType.objects.get_for_model(Vehicle),
                object_id=str(craft.pk),
                action_flag=ADDITION,
            ).exists()
        )

    def test_seacraft_dispatch_can_register_multiple_seacrafts_at_once(self):
        self.client.force_login(self.seacraft_user)
        payload = {'action': 'add_seacraft', 'craft_count': '2'}
        for index, (name, hull_id) in enumerate((
            ('Dispatch Vessel One', 'SEA-BULK-01'),
            ('Dispatch Vessel Two', 'SEA-BULK-02'),
        )):
            prefix = f'craft-{index}-'
            payload.update({
                prefix + 'model_name': name,
                prefix + 'plate_number': hull_id,
                prefix + 'vehicle_type': str(self.marine_type.pk),
                prefix + 'hull_type': 'Patrol boat',
                prefix + 'length_m': '8.5',
            })

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            payload,
            follow=True,
        )

        self.assertRedirects(response, reverse('dashboard_portal:seacraft_dispatch'))
        self.assertContains(response, '2 seacrafts registered.')
        self.assertEqual(
            Vehicle.objects.filter(plate_number__startswith='SEA-BULK-').count(),
            2,
        )

    def test_seacraft_dispatch_rejects_land_type_when_registering_craft(self):
        self.client.force_login(self.seacraft_user)

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'add_seacraft',
                'model_name': 'Invalid Land Entry',
                'plate_number': 'SEA-INVALID-01',
                'vehicle_type': self.land_type.pk,
            },
            follow=True,
        )

        self.assertContains(response, 'Choose a valid seacraft type.')
        self.assertFalse(Vehicle.objects.filter(plate_number='SEA-INVALID-01').exists())

    def test_seacraft_dispatch_rejects_duplicate_hull_id(self):
        self.create_vehicle(
            model_name='Existing Seacraft',
            plate_number='SEA-DUPLICATE-01',
            vehicle_type=self.marine_type,
        )
        self.client.force_login(self.seacraft_user)

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'add_seacraft',
                'model_name': 'Duplicate Seacraft',
                'plate_number': 'SEA-DUPLICATE-01',
                'vehicle_type': self.maritime_type.pk,
            },
            follow=True,
        )

        self.assertContains(response, 'Hull ID: This hull ID is already registered.')
        self.assertEqual(Vehicle.objects.filter(plate_number='SEA-DUPLICATE-01').count(), 1)

    def test_seacraft_dispatch_assigns_marina_authority_automatically(self):
        self.client.force_login(self.seacraft_user)
        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'add_operator',
                'name': 'Automatically Maritime Authority',
                'license_number': 'MRA-301',
                'license_authority': 'LTO',
            },
        )

        self.assertRedirects(response, reverse('dashboard_portal:seacraft_dispatch'))
        operator = Driver.objects.get(name='Automatically Maritime Authority')
        self.assertEqual(operator.license_authority, 'MARINA')

    def test_maritime_asset_classification_matches_across_dashboards(self):
        marine_craft = self.create_vehicle(
            model_name='Marine Name Craft',
            plate_number='SEA-MARINE-01',
            vehicle_type=self.marine_type,
        )
        maritime_craft = self.create_vehicle(
            model_name='Maritime Name Craft',
            plate_number='SEA-MARITIME-01',
            vehicle_type=self.maritime_type,
        )
        land_vehicle = self.create_vehicle(
            model_name='Land Name Vehicle',
            plate_number='LAND-01',
            vehicle_type=self.land_type,
        )

        self.client.force_login(self.logistics_user)
        logistics_response = self.client.get(reverse('dashboard_portal:logistics_dashboard'))
        self.assertEqual(logistics_response.status_code, 200)
        self.assertEqual(
            {craft.id for craft in logistics_response.context['sea_crafts']},
            {marine_craft.id, maritime_craft.id},
        )
        self.assertEqual(
            {vehicle.id for vehicle in logistics_response.context['land_vehicles']},
            {land_vehicle.id},
        )

        self.client.force_login(self.seacraft_user)
        dispatch_response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))
        self.assertEqual(dispatch_response.status_code, 200)
        for craft in (marine_craft, maritime_craft):
            self.assertContains(dispatch_response, craft.model_name)
        self.assertNotContains(dispatch_response, land_vehicle.model_name)

    def test_public_homepage_links_to_deployment_activity_log(self):
        response = self.client.get(reverse('dashboard_portal:homepage'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('dashboard_portal:deployment_activity_log'))
        self.assertContains(response, 'Deployment Activity Log')

    def test_public_homepage_maintenance_queue_shows_last_assigned_driver(self):
        for vehicle_type, plate_number, driver_name in (
            (self.land_type, 'LAND-MAINT-DRIVER', 'Last Land Maintenance Driver'),
            (self.marine_type, 'SEA-MAINT-DRIVER', 'Last Sea Maintenance Driver'),
        ):
            with self.subTest(plate_number=plate_number):
                driver = Driver.objects.create(name=driver_name)
                vehicle = self.create_vehicle(
                    model_name=f'Maintenance Unit {plate_number}',
                    plate_number=plate_number,
                    vehicle_type=vehicle_type,
                    assigned_driver=driver,
                )
                vehicle.status = 'MAINTENANCE'
                vehicle.save()
                vehicle.assigned_driver = None
                vehicle.save()

        response = self.client.get(reverse('dashboard_portal:homepage'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Last Assigned Driver')
        self.assertContains(response, 'Last Land Maintenance Driver')
        self.assertContains(response, 'Last Sea Maintenance Driver')
        self.assertNotContains(response, 'Linked:')

    def test_public_deployment_activity_log_shows_deployment_and_return(self):
        craft = self.create_vehicle(
            model_name='Deployment History Craft',
            plate_number='SEA-HISTORY-01',
            vehicle_type=self.marine_type,
        )
        self.client.force_login(self.seacraft_user)
        deploy_response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': craft.pk,
                'driver_id': self.operator.pk,
                'deployment_location': 'Bancao-bancao, Puerto Princesa City, Palawan',
                'deployment_purpose': 'Search and Rescue',
                'deployment_time': '2030-01-02T10:30',
            },
        )
        self.assertRedirects(deploy_response, reverse('dashboard_portal:seacraft_dispatch'))

        return_response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {'action': 'return_vehicle', 'vehicle_id': craft.pk},
        )
        self.assertRedirects(return_response, reverse('dashboard_portal:seacraft_dispatch'))
        self.client.logout()

        response = self.client.get(reverse('dashboard_portal:deployment_activity_log'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Deployment Activity Log')
        self.assertContains(response, 'Deployment History Craft')
        self.assertContains(response, 'Bancao-bancao, Puerto Princesa City, Palawan')
        self.assertContains(response, 'Search and Rescue')
        self.assertContains(response, 'RETURNED')
        self.assertContains(response, 'fa-ship text-info')
        self.assertContains(response, 'fa-arrow-up-right-from-square text-primary')
        self.assertContains(response, 'fa-arrow-rotate-left text-success')
        self.assertEqual(response.context['deployment_event_count'], 2)

    def test_deployment_log_refresh_returns_partial_updates_without_page_reload(self):
        land_vehicle = self.create_vehicle(
            model_name='Deployment Refresh Land Asset',
            plate_number='LAND-REFRESH-01',
            vehicle_type=self.land_type,
        )
        land_driver = Driver.objects.create(
            name='Deployment Refresh Driver',
            license_number='LTO-123',
        )
        self.client.force_login(self.logistics_user)
        self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': land_vehicle.pk,
                'driver_id': land_driver.pk,
                'deployment_location': 'Puerto Princesa City, Palawan',
                'deployment_purpose': 'Logistics Support',
                'deployment_time': '2030-01-02T10:30',
            },
        )

        response = self.client.get(
            reverse('dashboard_portal:deployment_activity_log'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['count'], 1)
        self.assertIn('Deployment Refresh Land Asset', payload['rows'])
        self.assertIn('fa-truck text-warning', payload['rows'])
        self.assertIn('fa-arrow-up-right-from-square text-primary', payload['rows'])
        page_response = self.client.get(reverse('dashboard_portal:deployment_activity_log'))
        self.assertContains(page_response, 'setInterval(refreshDeploymentActivity, 30000)')
        self.assertContains(page_response, 'rows.dataset.signature !== data.signature')
        self.assertContains(page_response, 'if (refreshInProgress || document.hidden) return')

    def test_seacraft_dispatch_uses_logistics_status_tabs(self):
        operational = self.create_vehicle(
            model_name='Tabbed Operational Craft',
            plate_number='SEA-TAB-01',
            vehicle_type=self.marine_type,
        )
        deployed = self.create_vehicle(
            model_name='Tabbed Deployed Craft',
            plate_number='SEA-TAB-02',
            vehicle_type=self.marine_type,
            status='DEPLOYED',
        )
        maintenance = self.create_vehicle(
            model_name='Tabbed Maintenance Craft',
            plate_number='SEA-TAB-03',
            vehicle_type=self.marine_type,
            status='MAINTENANCE',
        )
        pending_disposal = self.create_vehicle(
            model_name='Tabbed Disposal Craft',
            plate_number='SEA-TAB-04',
            vehicle_type=self.marine_type,
            status='PENDING_DISPOSAL',
        )

        self.client.force_login(self.seacraft_user)
        response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['sea_standby'], [operational])
        self.assertEqual(response.context['sea_deployed'], [deployed])
        self.assertEqual(
            response.context['sea_maintenance'],
            [maintenance, pending_disposal],
        )
        self.assertContains(response, 'Standby &amp; Operational (1)')
        self.assertContains(response, 'Active Deployments (1)')
        self.assertContains(response, 'Maintenance &amp; Disposal (2)')
        self.assertEqual(response.content.count(b'data-horizontal-card-scroll="true"'), 3)
        self.assertNotContains(response, 'data-vertical-card-scroll="true"')

    def test_seacraft_dispatch_colors_scheduled_maintenance_and_faults_differently(self):
        regular_maintenance = self.create_vehicle(
            model_name='Scheduled Service Craft',
            plate_number='SEA-COLOR-01',
            vehicle_type=self.marine_type,
            status='MAINTENANCE',
            maintenance_problem='Scheduled Oil change is due.',
        )
        fault_repair = self.create_vehicle(
            model_name='Fault Repair Craft',
            plate_number='SEA-COLOR-02',
            vehicle_type=self.marine_type,
            status='MAINTENANCE',
            maintenance_problem='Engine: Starter is not working.',
        )

        self.client.force_login(self.seacraft_user)
        response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'REGULAR MAINTENANCE')
        self.assertContains(response, 'bg-info-subtle border border-info text-info-emphasis')
        self.assertContains(response, 'FAULT REPAIR')
        self.assertContains(response, 'bg-danger')
        self.assertContains(response, regular_maintenance.maintenance_problem)
        self.assertContains(response, fault_repair.maintenance_problem)

    def test_seacraft_dispatch_persists_selected_tab_and_page_scroll(self):
        self.client.force_login(self.seacraft_user)

        response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "seacraft_dispatch_active_tab")
        self.assertContains(response, "seacraft_dispatch_scroll")
        self.assertContains(response, "shown.bs.tab")
        self.assertContains(response, "window.scrollTo(0, scrollPosition)")
        self.assertContains(response, "form.addEventListener('submit'")

    def test_seacraft_dispatch_header_actions_are_in_menu_drawer(self):
        self.create_vehicle(
            model_name='Assignment Drawer Seacraft',
            plate_number='SEA-DRAWER-01',
            vehicle_type=self.marine_type,
        )
        self.client.force_login(self.seacraft_user)

        response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="seacraftMenuDrawer"')
        self.assertContains(response, 'data-menu-action="operators"')
        self.assertContains(response, 'data-menu-action="print"')
        self.assertContains(response, 'data-menu-action="add-operator"')
        self.assertContains(response, 'id="seacraftOperatorAssignmentDrawer"')
        self.assertContains(response, 'name="action" value="set_driver"')
        self.assertContains(response, 'Confirm operator assignment change')
        self.assertNotContains(response, 'RESET</button>')
        self.assertContains(response, 'Connected to Dispatch Server')
        self.assertContains(response, 'Log Out')
        self.assertContains(response, 'aria-label="Open seacraft dispatch menu"')
        self.assertContains(response, 'data-menu-action="generate-report"')
        self.assertContains(response, 'Generate Fleet Report')

    def test_seacraft_dispatch_can_reassign_operator_between_operational_vessels(self):
        source_craft = self.create_vehicle(
            model_name='Current Operator Vessel',
            plate_number='SEA-REASSIGN-01',
            vehicle_type=self.marine_type,
            assigned_driver=self.operator,
        )
        target_craft = self.create_vehicle(
            model_name='New Operator Vessel',
            plate_number='SEA-REASSIGN-02',
            vehicle_type=self.maritime_type,
        )
        self.client.force_login(self.seacraft_user)

        assignment_response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))
        self.assertContains(
            assignment_response,
            '[Reassign from Current Operator Vessel]',
        )

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'set_driver',
                'vehicle_id': target_craft.pk,
                'driver_id': self.operator.pk,
            },
            follow=True,
        )

        self.assertContains(response, 'Operator reassigned from Current Operator Vessel to New Operator Vessel')
        source_craft.refresh_from_db()
        target_craft.refresh_from_db()
        self.assertIsNone(source_craft.assigned_driver)
        self.assertEqual(target_craft.assigned_driver, self.operator)

    def test_seacraft_dispatch_does_not_reassign_operator_from_deployed_vessel(self):
        source_craft = self.create_vehicle(
            model_name='Deployed Operator Vessel',
            plate_number='SEA-DEPLOYED-OP-01',
            vehicle_type=self.marine_type,
            assigned_driver=self.operator,
            status='DEPLOYED',
        )
        target_craft = self.create_vehicle(
            model_name='Requested Operator Vessel',
            plate_number='SEA-DEPLOYED-OP-02',
            vehicle_type=self.maritime_type,
        )
        self.client.force_login(self.seacraft_user)

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'set_driver',
                'vehicle_id': target_craft.pk,
                'driver_id': self.operator.pk,
            },
            follow=True,
        )

        self.assertContains(response, 'is assigned to active fleet asset')
        source_craft.refresh_from_db()
        target_craft.refresh_from_db()
        self.assertEqual(source_craft.assigned_driver, self.operator)
        self.assertIsNone(target_craft.assigned_driver)

    def test_unauthorized_seacraft_dispatch_user_redirects_to_homepage(self):
        unauthorized_user = User.objects.create_user(username='unauthorized_dispatch')
        self.client.force_login(unauthorized_user)

        response = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))

        self.assertRedirects(response, reverse('dashboard_portal:homepage'))

    def test_dispatch_deployment_details_are_visible_in_logistics_dashboard(self):
        craft = self.create_vehicle(
            model_name='Shared Dispatch Craft',
            plate_number='SEA-SHARED-01',
            vehicle_type=self.maritime_type,
        )
        self.client.force_login(self.seacraft_user)

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': craft.id,
                'driver_id': self.operator.id,
                'deployment_location': 'Bancao-bancao, Puerto Princesa City, Palawan',
                'deployment_purpose': 'Emergency Search & Rescue',
                'deployment_time': '2030-01-02T10:30',
            },
        )

        self.assertRedirects(response, reverse('dashboard_portal:seacraft_dispatch'))
        craft.refresh_from_db()
        self.assertEqual(craft.status, 'DEPLOYED')
        self.assertEqual(craft.assigned_driver, self.operator)
        self.assertEqual(craft.deployment_location, 'Bancao-bancao, Puerto Princesa City, Palawan')
        self.assertEqual(craft.deployment_purpose, 'Emergency Search & Rescue')
        self.assertIsNotNone(craft.deployment_time)

        self.client.force_login(self.logistics_user)
        dashboard = self.client.get(reverse('dashboard_portal:logistics_dashboard'))
        self.assertContains(dashboard, 'Shared Dispatch Craft')
        self.assertContains(dashboard, 'Bancao-bancao, Puerto Princesa City, Palawan')
        self.assertContains(dashboard, 'Emergency Search &amp; Rescue')
        self.assertContains(dashboard, 'Qualified Maritime Operator')

    def test_logistics_deployment_details_are_visible_in_seacraft_dispatch(self):
        craft = self.create_vehicle(
            model_name='Logistics Deployed Craft',
            plate_number='SEA-LOGISTICS-01',
            vehicle_type=self.marine_type,
        )
        self.client.force_login(self.logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': craft.id,
                'driver_id': self.operator.id,
                'deployment_location': 'Bancao-bancao, Puerto Princesa City, Palawan',
                'deployment_purpose': 'Coastal & Sea Patrol / Reconnaissance',
                'deployment_time': '2030-01-03T08:15',
            },
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        craft.refresh_from_db()
        self.assertEqual(craft.status, 'DEPLOYED')
        self.assertEqual(craft.assigned_driver, self.operator)
        self.assertEqual(craft.deployment_location, 'Bancao-bancao, Puerto Princesa City, Palawan')
        self.assertEqual(craft.deployment_purpose, 'Coastal & Sea Patrol / Reconnaissance')
        self.assertIsNotNone(craft.deployment_time)

        self.client.force_login(self.seacraft_user)
        dispatch_dashboard = self.client.get(reverse('dashboard_portal:seacraft_dispatch'))
        self.assertContains(dispatch_dashboard, 'Logistics Deployed Craft')
        self.assertContains(dispatch_dashboard, 'Bancao-bancao, Puerto Princesa City, Palawan')
        self.assertContains(dispatch_dashboard, 'Coastal &amp; Sea Patrol / Reconnaissance')

    def test_dispatch_rejects_nonoperational_craft_and_unqualified_operator(self):
        craft = self.create_vehicle(
            model_name='Blocked Dispatch Craft',
            plate_number='SEA-BLOCKED-01',
            vehicle_type=self.marine_type,
            status='MAINTENANCE',
        )
        land_operator = Driver.objects.create(
            name='Land Driver',
            license_number='LAND-001',
        )
        self.client.force_login(self.seacraft_user)

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': craft.id,
                'driver_id': self.operator.id,
                'deployment_location': 'Bancao-bancao, Puerto Princesa City, Palawan',
                'deployment_purpose': 'Emergency Search & Rescue',
                'deployment_time': '2030-01-02T10:30',
            },
            follow=True,
        )
        self.assertContains(response, 'must be operational')
        craft.refresh_from_db()
        self.assertEqual(craft.status, 'MAINTENANCE')

        craft.status = 'OPERATIONAL'
        craft.save(update_fields=['status'])
        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': craft.id,
                'driver_id': land_operator.id,
                'deployment_location': 'Bancao-bancao, Puerto Princesa City, Palawan',
                'deployment_purpose': 'Emergency Search & Rescue',
                'deployment_time': '2030-01-02T10:30',
            },
            follow=True,
        )
        self.assertContains(response, 'qualified seacraft operator')
        craft.refresh_from_db()
        self.assertEqual(craft.status, 'OPERATIONAL')

    def test_operator_can_be_reassigned_from_maintenance_and_return_clears_deployment(self):
        repair_craft = self.create_vehicle(
            model_name='Maintenance Craft',
            plate_number='SEA-MAINT-01',
            vehicle_type=self.marine_type,
            status='MAINTENANCE',
            assigned_driver=self.operator,
        )
        operational_craft = self.create_vehicle(
            model_name='Ready Craft',
            plate_number='SEA-READY-01',
            vehicle_type=self.maritime_type,
        )
        self.client.force_login(self.seacraft_user)

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': operational_craft.id,
                'driver_id': self.operator.id,
                'deployment_location': 'Bancao-bancao, Puerto Princesa City, Palawan',
                'deployment_purpose': 'Emergency Search & Rescue',
                'deployment_time': '2030-01-02T10:30',
            },
        )
        self.assertRedirects(response, reverse('dashboard_portal:seacraft_dispatch'))
        repair_craft.refresh_from_db()
        operational_craft.refresh_from_db()
        self.assertIsNone(repair_craft.assigned_driver)
        self.assertEqual(operational_craft.assigned_driver, self.operator)

        response = self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {'action': 'return_vehicle', 'vehicle_id': operational_craft.id},
        )
        self.assertRedirects(response, reverse('dashboard_portal:seacraft_dispatch'))
        operational_craft.refresh_from_db()
        self.assertEqual(operational_craft.status, 'OPERATIONAL')
        self.assertIsNone(operational_craft.deployment_location)
        self.assertIsNone(operational_craft.deployment_purpose)
        self.assertIsNone(operational_craft.deployment_time)


class MechanicMaintenanceWorkflowTests(TestCase):
    def setUp(self):
        self.land_type = VehicleType.objects.create(name='LAND')
        self.marine_type = VehicleType.objects.create(name='MARINE')
        technician_group = Group.objects.create(name='Technicians')
        maritime_group = Group.objects.create(name='Maritime_Tech')
        self.land_mechanic = User.objects.create_user(
            username='land_mechanic',
            password='SecurePass123!',
        )
        self.land_mechanic.groups.add(technician_group)
        self.sea_mechanic = User.objects.create_user(
            username='sea_mechanic',
            password='SecurePass123!',
        )
        self.sea_mechanic.groups.add(maritime_group)
        self.land_vehicle = Vehicle.objects.create(
            model_name='Land Work Vehicle',
            plate_number='LAND-WORK-01',
            vehicle_type=self.land_type,
        )
        self.seacraft = Vehicle.objects.create(
            model_name='Sea Work Vessel',
            plate_number='SEA-WORK-01',
            vehicle_type=self.marine_type,
        )

    def test_mechanic_dashboards_list_only_own_incidents_with_print_export_and_edit(self):
        land_incident = FleetIncident.objects.create(
            vehicle=self.land_vehicle,
            incident_type='DAMAGE',
            occurred_at=timezone.now(),
            location='Land response site',
            description='Land mechanic own report.',
            injury_status='NO',
            last_assigned_driver='Land operator snapshot',
            reported_by=self.land_mechanic,
        )
        other_land_incident = FleetIncident.objects.create(
            vehicle=self.land_vehicle,
            incident_type='ACCIDENT',
            occurred_at=timezone.now(),
            location='Other land site',
            description='Another user land report.',
            injury_status='NO',
            reported_by=self.sea_mechanic,
        )
        sea_incident = FleetIncident.objects.create(
            vehicle=self.seacraft,
            incident_type='BREAKDOWN',
            occurred_at=timezone.now(),
            location='Seacraft response site',
            description='Seacraft mechanic own report.',
            injury_status='NO',
            last_assigned_driver='Sea operator snapshot',
            reported_by=self.sea_mechanic,
        )
        other_sea_incident = FleetIncident.objects.create(
            vehicle=self.seacraft,
            incident_type='SAFETY',
            occurred_at=timezone.now(),
            location='Other seacraft site',
            description='Another user seacraft report.',
            injury_status='NO',
            reported_by=self.land_mechanic,
        )

        for user, dashboard, own_incident, hidden_incident in (
            (
                self.land_mechanic,
                'dashboard_portal:repairman_dashboard',
                land_incident,
                other_land_incident,
            ),
            (
                self.sea_mechanic,
                'dashboard_portal:seacraft_dashboard',
                sea_incident,
                other_sea_incident,
            ),
        ):
            with self.subTest(dashboard=dashboard):
                self.client.force_login(user)
                response = self.client.get(reverse(dashboard))

                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(response.context['incident_records']), [own_incident])
                self.assertContains(response, own_incident.description)
                self.assertContains(response, 'title="Print incident report"')
                self.assertContains(response, 'title="Export incident report as PDF"')
                self.assertContains(response, 'title="Edit incident report"')
                self.assertContains(response, f'incident_id={own_incident.pk}&amp;format=print')
                self.assertContains(response, f'incident_id={own_incident.pk}&amp;format=pdf')
                self.assertNotContains(response, hidden_incident.description)
                self.assertContains(response, 'data-menu-action="view-incidents"')

    def test_mechanic_can_edit_own_incident_but_not_another_users_report(self):
        incident = FleetIncident.objects.create(
            vehicle=self.land_vehicle,
            incident_type='DAMAGE',
            occurred_at=timezone.now(),
            location='Original location',
            description='Original incident description.',
            injury_status='NO',
            last_assigned_driver='Original operator snapshot',
            reported_by=self.land_mechanic,
        )
        edit_url = reverse(
            'dashboard_portal:fleet_edit_incident',
            args=[incident.pk],
        )
        self.client.force_login(self.land_mechanic)

        edit_page = self.client.get(edit_url)
        self.assertEqual(edit_page.status_code, 200)
        self.assertContains(edit_page, 'Original incident description.')
        self.assertContains(edit_page, 'palawan_deployment_locations.json')
        self.assertContains(edit_page, 'src="/static/fleet/js/deployment_location_search.js"')
        self.assertContains(edit_page, 'aria-controls="incident-location-suggestions"')
        self.assertContains(edit_page, 'id="incident-location-suggestions"')

        response = self.client.post(
            edit_url,
            {
                'vehicle': self.land_vehicle.pk,
                'incident_type': 'ACCIDENT',
                'occurred_at': timezone.localtime(incident.occurred_at).strftime('%Y-%m-%dT%H:%M'),
                'location': 'Updated location',
                'description': 'Updated incident description.',
                'damage_details': 'Updated damage details.',
                'injury_status': 'NO',
                'injury_details': '',
                'witnesses': 'Updated witnesses.',
                'actions_taken': 'Updated actions.',
                'follow_up_recommendations': 'Updated follow-up.',
            },
            follow=True,
        )
        self.assertRedirects(response, reverse('dashboard_portal:repairman_dashboard'))
        incident.refresh_from_db()
        self.assertEqual(incident.description, 'Updated incident description.')
        self.assertEqual(incident.location, 'Updated location')
        self.assertEqual(incident.reported_by, self.land_mechanic)
        self.assertEqual(incident.last_assigned_driver, 'Original operator snapshot')

        another_users_report = FleetIncident.objects.create(
            vehicle=self.land_vehicle,
            incident_type='DAMAGE',
            occurred_at=timezone.now(),
            location='Private report',
            description='Not editable by this user.',
            injury_status='NO',
            reported_by=self.sea_mechanic,
        )
        denied = self.client.get(
            reverse('dashboard_portal:fleet_edit_incident', args=[another_users_report.pk]),
        )
        self.assertEqual(denied.status_code, 404)

    def test_maintenance_work_orders_are_sorted_first_come_first_served(self):
        for vehicle, is_seacraft, vehicle_type, dashboard in (
            (
                self.land_vehicle,
                False,
                self.land_type,
                'dashboard_portal:repairman_dashboard',
            ),
            (
                self.seacraft,
                True,
                self.marine_type,
                'dashboard_portal:seacraft_dashboard',
            ),
        ):
            with self.subTest(dashboard=dashboard):
                vehicle.status = 'MAINTENANCE'
                vehicle.maintenance_problem = 'Engine: Reported fault.'
                vehicle.save()
                first_arrival = vehicle.maintenance_started_at

                later_vehicle = Vehicle.objects.create(
                    model_name='A Newer Work Order',
                    plate_number=f'FIFO-{vehicle_type.pk}-02',
                    vehicle_type=vehicle_type,
                    status='MAINTENANCE',
                    maintenance_problem='Engine: Later fault.',
                )
                Vehicle.objects.filter(pk=vehicle.pk).update(
                    maintenance_started_at=first_arrival - timedelta(minutes=1),
                )

                self.client.force_login(
                    self.sea_mechanic if is_seacraft else self.land_mechanic
                )
                response = self.client.get(reverse(dashboard))

                self.assertEqual(response.status_code, 200)
                maintenance_orders = [
                    item.pk
                    for item in response.context['vehicles']
                    if item.status == 'MAINTENANCE'
                ]
                self.assertEqual(maintenance_orders, [vehicle.pk, later_vehicle.pk])

    def test_maintenance_queue_timestamp_survives_disposal_review_and_resets_after_repair(self):
        previous_driver = Driver.objects.create(name='Previous Land Driver')
        self.land_vehicle.assigned_driver = previous_driver
        self.land_vehicle.save()
        self.land_vehicle.status = 'MAINTENANCE'
        self.land_vehicle.save()
        first_arrival = self.land_vehicle.maintenance_started_at
        self.assertEqual(
            self.land_vehicle.maintenance_last_assigned_driver,
            previous_driver.name,
        )

        self.land_vehicle.status = 'PENDING_DISPOSAL'
        self.land_vehicle.save()
        self.assertEqual(self.land_vehicle.maintenance_started_at, first_arrival)
        self.assertEqual(
            self.land_vehicle.maintenance_last_assigned_driver,
            previous_driver.name,
        )

        self.land_vehicle.status = 'MAINTENANCE'
        self.land_vehicle.save()
        self.assertEqual(self.land_vehicle.maintenance_started_at, first_arrival)

        self.land_vehicle.status = 'OPERATIONAL'
        self.land_vehicle.save()
        self.assertIsNone(self.land_vehicle.maintenance_started_at)
        self.assertEqual(self.land_vehicle.maintenance_last_assigned_driver, '')

        self.land_vehicle.status = 'MAINTENANCE'
        self.land_vehicle.save()
        self.assertGreater(self.land_vehicle.maintenance_started_at, first_arrival)

    def test_mechanic_dashboards_show_last_assigned_driver_during_maintenance(self):
        for vehicle, is_seacraft, dashboard, driver_name in (
            (
                self.land_vehicle,
                False,
                'dashboard_portal:repairman_dashboard',
                'Previous Land Fleet Driver',
            ),
            (
                self.seacraft,
                True,
                'dashboard_portal:seacraft_dashboard',
                'Previous Seacraft Operator',
            ),
        ):
            with self.subTest(dashboard=dashboard):
                driver = Driver.objects.create(name=driver_name)
                vehicle.assigned_driver = driver
                vehicle.save()
                vehicle.status = 'MAINTENANCE'
                vehicle.maintenance_problem = 'Engine: Reported fault.'
                vehicle.assigned_driver = None
                vehicle.save()

                self.client.force_login(
                    self.sea_mechanic if is_seacraft else self.land_mechanic
                )
                response = self.client.get(reverse(dashboard))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Last assigned driver:')
                self.assertContains(response, driver_name)

    def post_as_mechanic(self, vehicle, action, *, is_seacraft=False, **data):
        user = self.sea_mechanic if is_seacraft else self.land_mechanic
        url_name = 'dashboard_portal:seacraft_dashboard' if is_seacraft else 'dashboard_portal:repairman_dashboard'
        if action == 'REPORT_FAULT' and 'fault_description' in data:
            data[f'fault-{vehicle.pk}-fault_description'] = data.pop('fault_description')
            data[f'fault-{vehicle.pk}-fault_type'] = data.pop('fault_type', 'engine')
        if action == 'COMPLETE_MAINTENANCE' and 'maintenance_checklist' in data:
            data[f'checklist-{vehicle.pk}-maintenance_checklist'] = data.pop('maintenance_checklist')
        if action == 'SCHEDULE_MAINTENANCE':
            data[f'schedule-{vehicle.pk}-maintenance_type'] = data.pop('maintenance_type', 'TIRES')
            data[f'schedule-{vehicle.pk}-due_date'] = data.pop('due_date')
            if 'description' in data:
                data[f'schedule-{vehicle.pk}-description'] = data.pop('description')
        self.client.force_login(user)
        return self.client.post(
            reverse(url_name),
            {'vehicle_id': vehicle.id, 'action_type': action, **data},
        )

    def test_mechanic_dashboards_offer_report_generation(self):
        for user, dashboard in (
            (self.land_mechanic, 'dashboard_portal:repairman_dashboard'),
            (self.sea_mechanic, 'dashboard_portal:seacraft_dashboard'),
        ):
            with self.subTest(dashboard=dashboard):
                self.client.force_login(user)
                response = self.client.get(reverse(dashboard))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="mechanicMenuDrawer"')
                self.assertContains(response, 'aria-label="Open mechanic menu"')
                self.assertContains(response, 'Maintenance Menu')
                self.assertContains(response, 'Maintenance Workbench')
                self.assertContains(response, 'data-menu-action="print"')
                self.assertContains(response, 'data-menu-action="generate-report"')
                drawer_order = (
                    'data-menu-action="file-incident"',
                    'data-menu-action="print-incident"',
                    'data-menu-action="generate-report"',
                    'data-menu-action="print"',
                )
                drawer_positions = [response.content.index(action.encode()) for action in drawer_order]
                self.assertEqual(drawer_positions, sorted(drawer_positions))
                self.assertContains(response, 'Log Out')
                self.assertContains(response, 'Generate Fleet Report')
                self.assertContains(response, 'value="custom">Custom date range')
                self.assertContains(response, 'value="xlsx"')
                self.assertContains(response, 'Regular maintenance (tires and oil)')

    def test_unauthorized_mechanic_users_redirect_to_homepage(self):
        unauthorized_user = User.objects.create_user(username='blocked_user')
        self.client.force_login(unauthorized_user)

        for dashboard in (
            'dashboard_portal:repairman_dashboard',
            'dashboard_portal:seacraft_dashboard',
        ):
            with self.subTest(dashboard=dashboard):
                response = self.client.get(reverse(dashboard))
                self.assertRedirects(response, reverse('dashboard_portal:homepage'))

    def test_mechanic_report_is_limited_to_its_asset_division(self):
        content_type = ContentType.objects.get_for_model(Vehicle)
        LogEntry.objects.create(
            user=self.land_mechanic,
            content_type=content_type,
            object_id=str(self.land_vehicle.pk),
            object_repr=str(self.land_vehicle),
            action_flag=CHANGE,
            change_message='Deployed asset unit to Puerto Princesa for Search and Rescue.',
        )
        LogEntry.objects.create(
            user=self.sea_mechanic,
            content_type=content_type,
            object_id=str(self.seacraft.pk),
            object_repr=str(self.seacraft),
            action_flag=CHANGE,
            change_message='Deployed asset unit to Honda Bay for Search and Rescue.',
        )
        report_url = reverse('dashboard_portal:fleet_activity_report')
        params = {
            'format': 'csv',
            'period': 'day',
            'day': timezone.localdate().isoformat(),
        }

        for user, included_asset, excluded_asset in (
            (self.land_mechanic, b'Land Work Vehicle', b'Sea Work Vessel'),
            (self.sea_mechanic, b'Sea Work Vessel', b'Land Work Vehicle'),
        ):
            with self.subTest(username=user.username):
                self.client.force_login(user)
                response = self.client.get(report_url, params)

                self.assertEqual(response.status_code, 200)
                self.assertIn(included_asset, response.content)
                self.assertNotIn(excluded_asset, response.content)

    def test_maintenance_reports_include_regular_and_other_work_types(self):
        content_type = ContentType.objects.get_for_model(Vehicle)
        events = (
            (self.land_vehicle, 'Scheduled Tire replacement for 2026-10-09: Replace front tires.'),
            (self.land_vehicle, 'Scheduled Oil replacement for 2026-10-09: Replace engine oil.'),
            (self.land_vehicle, 'Scheduled Other maintenance for 2026-10-09: Repair body panel.'),
            (self.land_vehicle, 'Reported maintenance fault for Land Work Vehicle: Engine: Belt noise'),
            (self.land_vehicle, 'Completed maintenance checklist and returned Land Work Vehicle to operational status.'),
            (self.seacraft, 'Scheduled Tire replacement for 2026-10-09: Replace trailer tires.'),
        )
        for vehicle, message in events:
            LogEntry.objects.create(
                user=self.land_mechanic,
                content_type=content_type,
                object_id=str(vehicle.pk),
                object_repr=str(vehicle),
                action_flag=CHANGE,
                change_message=message,
            )
        report_url = reverse('dashboard_portal:fleet_activity_report')
        base_params = {
            'report_kind': 'maintenance',
            'format': 'csv',
            'period': 'day',
            'day': timezone.localdate().isoformat(),
        }

        self.client.force_login(self.land_mechanic)
        regular_report = self.client.get(
            report_url,
            {**base_params, 'maintenance_category': 'regular'},
        )
        other_report = self.client.get(
            report_url,
            {**base_params, 'maintenance_category': 'other'},
        )
        all_report = self.client.get(
            report_url,
            {**base_params, 'maintenance_category': 'all'},
        )

        self.assertEqual(regular_report.status_code, 200)
        self.assertIn(b'Regular maintenance', regular_report.content)
        self.assertIn(b'Tire replacement', regular_report.content)
        self.assertIn(b'Oil replacement', regular_report.content)
        self.assertNotIn(b'body panel', regular_report.content)
        self.assertNotIn(b'Sea Work Vessel', regular_report.content)
        self.assertEqual(other_report.status_code, 200)
        self.assertIn(b'body panel', other_report.content)
        self.assertIn(b'Belt noise', other_report.content)
        self.assertIn(b'Completed maintenance checklist', other_report.content)
        self.assertNotIn(b'Tire replacement', other_report.content)
        self.assertEqual(all_report.status_code, 200)
        self.assertIn(b'Tire replacement', all_report.content)
        self.assertIn(b'body panel', all_report.content)

    def test_maintenance_report_supports_print_and_file_exports(self):
        LogEntry.objects.create(
            user=self.land_mechanic,
            content_type=ContentType.objects.get_for_model(Vehicle),
            object_id=str(self.land_vehicle.pk),
            object_repr=str(self.land_vehicle),
            action_flag=CHANGE,
            change_message='Reported maintenance fault for Land Work Vehicle: Engine: Belt noise',
        )
        report_url = reverse('dashboard_portal:fleet_activity_report')
        params = {
            'report_kind': 'maintenance',
            'maintenance_category': 'other',
            'period': 'day',
            'day': timezone.localdate().isoformat(),
        }

        self.client.force_login(self.land_mechanic)
        for export_format in ('print', 'csv', 'xlsx', 'pdf'):
            with self.subTest(format=export_format):
                response = self.client.get(
                    report_url,
                    {**params, 'format': export_format},
                )
                self.assertEqual(response.status_code, 200)
                if export_format == 'print':
                    self.assertContains(response, 'Other maintenance and repairs Report')
                    self.assertContains(response, 'Belt noise')
                elif export_format == 'pdf':
                    self.assertEqual(response['Content-Type'], 'application/pdf')
                    self.assertTrue(response.content.startswith(b'%PDF'))
                    self.assertIn('fleet-maintenance-', response['Content-Disposition'])
                elif export_format == 'xlsx':
                    self.assertIn(
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        response['Content-Type'],
                    )
                    self.assertIn('fleet-maintenance-', response['Content-Disposition'])
                else:
                    self.assertIn(b'Other maintenance and repairs', response.content)
                    self.assertIn(b'Belt noise', response.content)

    def test_fault_description_is_required_before_maintenance(self):
        for vehicle, is_seacraft in (
            (self.land_vehicle, False),
            (self.seacraft, True),
        ):
            with self.subTest(asset=vehicle.model_name):
                self.post_as_mechanic(vehicle, 'REPORT_FAULT', is_seacraft=is_seacraft, fault_description='   ')
                vehicle.refresh_from_db()
                self.assertEqual(vehicle.status, 'OPERATIONAL')
                self.assertEqual(vehicle.maintenance_problem, '')

    def test_fault_report_moves_asset_to_maintenance_and_persists_fault(self):
        for vehicle, is_seacraft in (
            (self.land_vehicle, False),
            (self.seacraft, True),
        ):
            with self.subTest(asset=vehicle.model_name):
                self.post_as_mechanic(
                    vehicle,
                    'REPORT_FAULT',
                    is_seacraft=is_seacraft,
                    fault_description='Engine makes a loud grinding noise.',
                )
                vehicle.refresh_from_db()
                self.assertEqual(vehicle.status, 'MAINTENANCE')
                self.assertEqual(
                    vehicle.maintenance_problem,
                    'Engine: Engine makes a loud grinding noise.',
                )

    def test_fault_report_requires_a_valid_issue_type(self):
        self.post_as_mechanic(
            self.land_vehicle,
            'REPORT_FAULT',
            fault_type='unsupported',
            fault_description='A fault was reported.',
        )

        self.land_vehicle.refresh_from_db()
        self.assertEqual(self.land_vehicle.status, 'OPERATIONAL')
        self.assertEqual(self.land_vehicle.maintenance_problem, '')

    def test_mechanic_dashboards_show_seven_day_schedule_reminders_and_regular_maintenance_tabs(self):
        today = timezone.localdate()
        scheduled_assets = (
            (
                self.land_vehicle,
                self.land_mechanic,
                'dashboard_portal:repairman_dashboard',
                'data-land-fleet-tab="regular-maintenance"',
            ),
            (
                self.seacraft,
                self.sea_mechanic,
                'dashboard_portal:seacraft_dashboard',
                'data-sea-fleet-tab="regular-maintenance"',
            ),
        )
        for asset, _, _, _ in scheduled_assets:
            asset.scheduled_maintenance_type = 'OIL'
            asset.scheduled_maintenance_date = today + timedelta(days=7)
            asset.scheduled_maintenance_description = 'Scheduled service details.'
            asset.save(update_fields=[
                'scheduled_maintenance_type',
                'scheduled_maintenance_date',
                'scheduled_maintenance_description',
            ])

        beyond_window = Vehicle.objects.create(
            model_name='Land Service Beyond Reminder Window',
            plate_number='LAND-SCHEDULE-08',
            vehicle_type=self.land_type,
            scheduled_maintenance_type='TIRES',
            scheduled_maintenance_date=today + timedelta(days=8),
        )
        beyond_sea_window = Vehicle.objects.create(
            model_name='Sea Service Beyond Reminder Window',
            plate_number='SEA-SCHEDULE-08',
            vehicle_type=self.marine_type,
            scheduled_maintenance_type='TIRES',
            scheduled_maintenance_date=today + timedelta(days=8),
        )

        for asset, user, dashboard, schedule_tab in scheduled_assets:
            with self.subTest(dashboard=dashboard):
                self.client.force_login(user)
                response = self.client.get(reverse(dashboard))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, schedule_tab)
                self.assertContains(response, 'Regular maintenance due within 7 days')
                self.assertContains(response, asset.model_name)
                self.assertContains(response, 'alert alert-info')
                self.assertContains(response, 'Scheduled Regular Maintenance')
                self.assertEqual(
                    [vehicle.pk for vehicle in response.context['scheduled_maintenance_vehicles']],
                    [asset.pk, beyond_window.pk if asset == self.land_vehicle else beyond_sea_window.pk],
                )
                self.assertEqual(
                    [vehicle.pk for vehicle in response.context['upcoming_scheduled_maintenance_vehicles']],
                    [asset.pk],
                )

    def test_mechanic_can_schedule_future_preventive_maintenance(self):
        due_date = timezone.localdate() + timedelta(days=30)
        response = self.post_as_mechanic(
            self.land_vehicle,
            'SCHEDULE_MAINTENANCE',
            maintenance_type='OIL',
            due_date=due_date.isoformat(),
            description='Use the approved engine oil.',
        )

        self.assertRedirects(response, reverse('dashboard_portal:repairman_dashboard'))
        self.land_vehicle.refresh_from_db()
        self.assertEqual(self.land_vehicle.status, 'OPERATIONAL')
        self.assertEqual(self.land_vehicle.scheduled_maintenance_type, 'OIL')
        self.assertEqual(self.land_vehicle.scheduled_maintenance_date, due_date)
        self.assertEqual(
            self.land_vehicle.scheduled_maintenance_description,
            'Use the approved engine oil.',
        )

    def test_overdue_scheduled_maintenance_moves_vehicle_to_maintenance(self):
        driver = Driver.objects.create(name='Scheduled Service Driver')
        self.land_vehicle.status = 'DEPLOYED'
        self.land_vehicle.assigned_driver = driver
        self.land_vehicle.deployment_location = 'Test location'
        self.land_vehicle.deployment_purpose = 'Test deployment'
        self.land_vehicle.scheduled_maintenance_type = 'TIRES'
        self.land_vehicle.scheduled_maintenance_date = timezone.localdate() - timedelta(days=1)
        self.land_vehicle.scheduled_maintenance_description = 'Replace front tires.'
        self.land_vehicle.save()
        self.client.force_login(self.land_mechanic)

        response = self.client.get(reverse('dashboard_portal:repairman_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.land_vehicle.refresh_from_db()
        self.assertEqual(self.land_vehicle.status, 'MAINTENANCE')
        self.assertEqual(
            self.land_vehicle.maintenance_problem,
            'Scheduled Tire replacement is due. Replace front tires.',
        )
        self.assertIsNone(self.land_vehicle.assigned_driver)
        self.assertIsNone(self.land_vehicle.deployment_location)
        self.assertIsNone(self.land_vehicle.scheduled_maintenance_date)

    def test_overdue_vehicle_cannot_be_deployed_from_logistics(self):
        logistics_group = Group.objects.create(name='Logistics Officers')
        logistics_user = User.objects.create_user(
            username='fleet_logistics',
            password='SecurePass123!',
        )
        logistics_user.groups.add(logistics_group)
        self.land_vehicle.scheduled_maintenance_type = 'OIL'
        self.land_vehicle.scheduled_maintenance_date = timezone.localdate()
        self.land_vehicle.save()
        self.client.force_login(logistics_user)

        response = self.client.post(
            reverse('dashboard_portal:logistics_dashboard'),
            {
                'action': 'deploy_vehicle',
                'vehicle_id': self.land_vehicle.id,
            },
        )

        self.assertRedirects(response, reverse('dashboard_portal:logistics_dashboard'))
        self.land_vehicle.refresh_from_db()
        self.assertEqual(self.land_vehicle.status, 'MAINTENANCE')

    def test_past_maintenance_schedule_date_is_rejected(self):
        self.post_as_mechanic(
            self.land_vehicle,
            'SCHEDULE_MAINTENANCE',
            maintenance_type='OIL',
            due_date=(timezone.localdate() - timedelta(days=1)).isoformat(),
        )

        self.land_vehicle.refresh_from_db()
        self.assertEqual(self.land_vehicle.status, 'OPERATIONAL')
        self.assertIsNone(self.land_vehicle.scheduled_maintenance_date)

    def test_seacraft_mechanic_can_schedule_and_trigger_due_maintenance(self):
        due_date = timezone.localdate() + timedelta(days=1)
        self.post_as_mechanic(
            self.seacraft,
            'SCHEDULE_MAINTENANCE',
            is_seacraft=True,
            maintenance_type='OTHER',
            due_date=due_date.isoformat(),
            description='Inspect bilge pump.',
        )

        self.seacraft.refresh_from_db()
        self.assertEqual(self.seacraft.status, 'OPERATIONAL')
        self.assertEqual(self.seacraft.scheduled_maintenance_type, 'OTHER')
        self.assertEqual(self.seacraft.scheduled_maintenance_date, due_date)

        self.seacraft.scheduled_maintenance_date = timezone.localdate()
        self.seacraft.save(update_fields=['scheduled_maintenance_date'])
        self.client.force_login(self.sea_mechanic)
        response = self.client.get(reverse('dashboard_portal:seacraft_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.seacraft.refresh_from_db()
        self.assertEqual(self.seacraft.status, 'MAINTENANCE')
        self.assertEqual(
            self.seacraft.maintenance_problem,
            'Scheduled Other maintenance is due. Inspect bilge pump.',
        )

    def test_deployed_assets_show_mission_location_and_click_to_call_driver(self):
        for vehicle, is_seacraft, phone_number in (
            (self.land_vehicle, False, '+639171234567'),
            (self.seacraft, True, '+639189876543'),
        ):
            with self.subTest(asset=vehicle.model_name):
                driver = Driver.objects.create(
                    name=f'{vehicle.model_name} Operator',
                    phone_number=phone_number,
                    license_number='MAR-100' if is_seacraft else 'LAND-100',
                )
                vehicle.status = 'DEPLOYED'
                vehicle.assigned_driver = driver
                vehicle.deployment_location = 'Honda Bay'
                vehicle.deployment_purpose = 'Emergency Search & Rescue'
                vehicle.save()

                user = self.sea_mechanic if is_seacraft else self.land_mechanic
                dashboard = (
                    'dashboard_portal:seacraft_dashboard'
                    if is_seacraft else 'dashboard_portal:repairman_dashboard'
                )
                self.client.force_login(user)
                response = self.client.get(reverse(dashboard))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Location:')
                self.assertContains(response, 'Honda Bay')
                self.assertContains(response, 'Mission detail:')
                self.assertContains(response, 'Emergency Search &amp; Rescue')
                self.assertContains(response, f'Driver: {driver.name}')
                self.assertContains(response, f'href="tel:{phone_number}"')
                self.assertContains(response, phone_number)

    def test_seacraft_operational_fleet_shows_assigned_operator(self):
        operator = Driver.objects.create(
            name='Operational Seacraft Operator',
            license_number='MAR-OP-100',
        )
        self.seacraft.assigned_driver = operator
        self.seacraft.save(update_fields=['assigned_driver'])
        self.client.force_login(self.sea_mechanic)

        response = self.client.get(reverse('dashboard_portal:seacraft_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned operator:')
        self.assertContains(response, 'Operational Seacraft Operator')

    def test_land_operational_fleet_shows_assigned_operator(self):
        operator = Driver.objects.create(
            name='Operational Land Operator',
            license_number='LAND-OP-100',
        )
        self.land_vehicle.assigned_driver = operator
        self.land_vehicle.save(update_fields=['assigned_driver'])
        self.client.force_login(self.land_mechanic)

        response = self.client.get(reverse('dashboard_portal:repairman_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Assigned operator:')
        self.assertContains(response, 'Operational Land Operator')

    def test_reporting_a_deployed_fault_clears_dispatch_assignment(self):
        driver = Driver.objects.create(name='Assigned Land Operator')
        self.land_vehicle.status = 'DEPLOYED'
        self.land_vehicle.assigned_driver = driver
        self.land_vehicle.deployment_location = 'Test location'
        self.land_vehicle.deployment_purpose = 'Test deployment'
        self.land_vehicle.save()

        self.post_as_mechanic(
            self.land_vehicle,
            'REPORT_FAULT',
            fault_description='The brakes make a grinding noise.',
        )

        self.land_vehicle.refresh_from_db()
        self.assertEqual(self.land_vehicle.status, 'MAINTENANCE')
        self.assertIsNone(self.land_vehicle.assigned_driver)
        self.assertIsNone(self.land_vehicle.deployment_location)
        self.assertIsNone(self.land_vehicle.deployment_purpose)

    def test_every_asset_specific_checklist_item_is_required(self):
        for vehicle, is_seacraft in (
            (self.land_vehicle, False),
            (self.seacraft, True),
        ):
            with self.subTest(asset=vehicle.model_name):
                vehicle.status = 'MAINTENANCE'
                vehicle.maintenance_problem = 'User reported a fault.'
                vehicle.save()
                self.post_as_mechanic(
                    vehicle,
                    'COMPLETE_MAINTENANCE',
                    is_seacraft=is_seacraft,
                    maintenance_checklist=['repairs_complete'],
                )
                vehicle.refresh_from_db()
                self.assertEqual(vehicle.status, 'MAINTENANCE')
                self.assertEqual(vehicle.maintenance_problem, 'User reported a fault.')

    def test_complete_checklist_returns_land_and_sea_assets_to_service(self):
        for vehicle, is_seacraft in (
            (self.land_vehicle, False),
            (self.seacraft, True),
        ):
            with self.subTest(asset=vehicle.model_name):
                vehicle.status = 'MAINTENANCE'
                vehicle.maintenance_problem = 'User reported a fault.'
                vehicle.save()
                self.post_as_mechanic(
                    vehicle,
                    'COMPLETE_MAINTENANCE',
                    is_seacraft=is_seacraft,
                    maintenance_checklist=[
                        'repairs_complete',
                        'safety_systems_checked',
                        'test_run_passed',
                        'no_unresolved_issues',
                        'propulsion_fuel_hull_checked' if is_seacraft else 'fluids_battery_tires_checked',
                    ],
                )
                vehicle.refresh_from_db()
                self.assertEqual(vehicle.status, 'OPERATIONAL')
                self.assertEqual(vehicle.maintenance_problem, '')

    def test_legacy_status_toggle_cannot_bypass_mechanic_workflow(self):
        for vehicle, is_seacraft in (
            (self.land_vehicle, False),
            (self.seacraft, True),
        ):
            with self.subTest(asset=vehicle.model_name):
                self.post_as_mechanic(
                    vehicle,
                    'STATUS_TOGGLE',
                    is_seacraft=is_seacraft,
                    status='MAINTENANCE',
                )
                vehicle.refresh_from_db()
                self.assertEqual(vehicle.status, 'OPERATIONAL')

    def test_seacraft_dispatch_cannot_bypass_maintenance_checklist(self):
        self.seacraft.status = 'MAINTENANCE'
        self.seacraft.maintenance_problem = 'User reported a fault.'
        self.seacraft.save()
        self.client.force_login(self.sea_mechanic)

        self.client.post(
            reverse('dashboard_portal:seacraft_dispatch'),
            {
                'vehicle_id': self.seacraft.id,
                'action': 'STATUS_TOGGLE',
                'status': 'OPERATIONAL',
            },
        )

        self.seacraft.refresh_from_db()
        self.assertEqual(self.seacraft.status, 'MAINTENANCE')
        self.assertEqual(self.seacraft.maintenance_problem, 'User reported a fault.')

    def test_mechanic_pages_show_fault_prompt_and_no_status_toggles(self):
        for user, vehicle, url_name, is_seacraft in (
            (self.land_mechanic, self.land_vehicle, 'dashboard_portal:repairman_dashboard', False),
            (self.sea_mechanic, self.seacraft, 'dashboard_portal:seacraft_dashboard', True),
        ):
            with self.subTest(asset=vehicle.model_name):
                self.client.force_login(user)
                response = self.client.get(reverse(url_name))
                self.assertContains(response, 'Description of issue')
                if not is_seacraft:
                    self.assertContains(response, 'Operational Fleet')
                    self.assertContains(response, 'Maintenance')
                    self.assertContains(response, 'Issue type')
                    self.assertContains(response, 'Driver:')
                    self.assertContains(response, 'data-land-fleet-tab="maintenance"')
                    self.assertContains(response, 'data-land-fleet-group="operational" hidden')
                else:
                    self.assertContains(response, 'data-sea-fleet-tab="maintenance"')
                    self.assertContains(response, 'data-sea-fleet-group="operational" hidden')
                    self.assertContains(response, 'Schedule other maintenance')
                    self.assertContains(response, 'Issue type')
                    self.assertContains(response, 'Driver: Unassigned')
                if not is_seacraft:
                    self.assertContains(response, f'data-bs-target="#landMaintenanceModal{vehicle.id}"')
                    self.assertContains(response, 'modal-dialog modal-dialog-centered modal-lg')
                else:
                    self.assertContains(response, f'data-bs-target="#seaMaintenanceModal{vehicle.id}"')
                    self.assertContains(response, 'modal-dialog modal-dialog-centered modal-lg')
                vehicle.status = 'MAINTENANCE'
                vehicle.maintenance_problem = 'User-reported test fault.'
                vehicle.save()
                response = self.client.get(reverse(url_name))
                self.assertContains(response, 'Return-to-service checklist')
                self.assertContains(response, 'User-reported test fault.')
                self.assertContains(response, 'FAULT REPAIR')
                if not is_seacraft:
                    self.assertContains(response, 'data-land-fleet-group="maintenance">')
                else:
                    self.assertContains(response, 'data-sea-fleet-group="maintenance">')
                self.assertContains(response, 'class="maintenance-checklist"')
                self.assertNotContains(response, 'STATUS_TOGGLE')
                vehicle.maintenance_problem = 'Scheduled Tire replacement is due.'
                vehicle.save(update_fields=['maintenance_problem'])
                response = self.client.get(reverse(url_name))
                self.assertContains(response, 'REGULAR MAINTENANCE')
                self.assertContains(response, 'bg-sky-50' if is_seacraft else 'bg-info-subtle')
