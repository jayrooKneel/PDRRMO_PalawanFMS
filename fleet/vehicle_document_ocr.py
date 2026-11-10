import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pytesseract
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError
from pytesseract import TesseractError, TesseractNotFoundError


MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_IMAGE_COUNT = 5
MAX_IMAGE_PIXELS = 40_000_000
OCR_TIMEOUT_SECONDS = 20


class RegistrationImageError(ValueError):
    pass


class RegistrationOcrUnavailable(RuntimeError):
    pass


class RegistrationOcrError(RuntimeError):
    pass


LAND_FIELDS = {
    'model_name',
    'plate_number',
    'make',
    'chassis_number',
    'engine_number',
    'mv_file_number',
    'vehicle_category',
    'body_type',
    'vehicle_classification',
    'aircon_type',
    'engine_displacement_cc',
    'model_year',
    'color',
    'engine_details',
    'engine_power_hp',
    'fuel_type',
    'passenger_capacity',
    'gross_vehicle_weight',
    'net_capacity',
    'registration_date',
    'registration_expiry',
    'inspection_expiry',
}
SEA_FIELDS = {
    'model_name',
    'plate_number',
    'make',
    'chassis_number',
    'engine_number',
    'home_port',
    'model_year',
    'color',
    'hull_type',
    'length_m',
    'gross_tonnage',
    'net_tonnage',
    'engine_details',
    'engine_power_hp',
    'fuel_type',
    'passenger_capacity',
    'registration_date',
    'registration_expiry',
    'inspection_expiry',
}

FIELD_LABELS = {
    'plate_number': (
        r'plate\s*(?:no\.?|number|#)',
        r'plate',
        r'official\s*(?:no\.?|number)',
        r'official\s*(?:registration\s*)?(?:no\.?|number)',
        r'registration\s*(?:no\.?|number)',
    ),
    'model_name': (
        r'vessel\s*name',
        r'name\s*of\s*vessel',
        r'vehicle\s*series',
        r'vehicle\s*model',
        r'series',
        r'model(?!\s*year)',
    ),
    'make': (r'make(?:\s*/\s*series)?', r'manufacturer'),
    'chassis_number': (
        r'chassis\s*(?:no\.?|number)',
        r'hull\s*(?:no\.?|number|id)',
        r'serial\s*(?:no\.?|number)',
    ),
    'engine_number': (r'engine\s*(?:no\.?|number)',),
    'mv_file_number': (
        r'm\.?\s*v\.?\s*file\s*(?:no\.?|number)?',
        r'motor\s*vehicle\s*file\s*(?:no\.?|number)',
    ),
    'vehicle_category': (r'vehicle\s*category',),
    'body_type': (r'body\s*(?:type|style)',),
    'vehicle_classification': (r'(?:vehicle\s*)?classification',),
    'aircon_type': (r'air\s*con(?:dition(?:er|ing)?)?\s*type', r'a\s*/\s*c\s*type'),
    'home_port': (r'port\s*of\s*registry', r'home\s*port', r'port\s*of\s*registration'),
    'model_year': (
        r'year\s*(?:model|built|of\s*construction)',
        r'year\s*of\s*manufacture',
        r'model\s*year',
        r'year\s*built',
    ),
    'color': (r'colou?r',),
    'engine_details': (
        r'engine\s*(?:make|model|type)',
        r'engine(?!\s*(?:no\.?|number))',
    ),
    'engine_displacement_cc': (
        r'piston\s*displacement',
        r'engine\s*displacement',
        r'displacement',
    ),
    'engine_power_hp': (
        r'horse\s*power',
        r'horsepower',
        r'engine\s*power',
    ),
    'fuel_type': (r'fuel(?:\s*type)?',),
    'passenger_capacity': (
        r'(?:passenger|seating)\s*capacity',
        r'pax\s*capacity',
        r'no\.?\s*of\s*passengers',
        r'authorized\s*persons',
    ),
    'gross_vehicle_weight': (r'gross\s*(?:vehicle\s*)?weight',),
    'net_capacity': (r'net\s*(?:vehicle\s*)?(?:weight|capacity)',),
    'registration_date': (
        r'date\s*of\s*initial\s*registration',
        r'initial\s*registration\s*date',
        r'date\s*of\s*registration',
        r'date\s*registered',
    ),
    'registration_expiry': (
        r'registration\s*(?:expiry|expiration|expires)',
        r'expiry\s*date',
        r'expiration\s*date',
        r'valid\s*(?:until|thru|through)',
    ),
    'inspection_expiry': (
        r'inspection\s*(?:expiry|expiration|expires)',
        r'inspection\s*valid\s*(?:until|thru|through)',
    ),
    'hull_type': (r'hull\s*type', r'vessel\s*type', r'type\s*of\s*vessel'),
    'length_m': (r'length\s*(?:overall)?',),
    'gross_tonnage': (r'gross\s*tonnage',),
    'net_tonnage': (r'net\s*tonnage',),
}

NON_TECHNICAL_LABELS = (
    r'registered\s*(?:owner|proprietor)',
    r'(?:name|signature)\s*of\s*(?:the\s*)?(?:registered\s*)?owner',
    r'owner(?:\'s)?\s*(?:name|address)',
    r'address(?:\s*of\s*(?:the\s*)?(?:registered\s*)?owner)?',
    r'residing\s*(?:at|address)',
    r'date\s*of\s*birth',
)

COMMON_MAKES = (
    'Mitsubishi', 'Mercedes-Benz', 'Land Rover', 'Volkswagen', 'Chevrolet',
    'Hyundai', 'Kawasaki', 'Isuzu', 'Nissan', 'Suzuki', 'Toyota', 'Honda',
    'Yamaha', 'Ford', 'Kia', 'Mazda', 'Subaru', 'Volvo', 'Hino', 'Fuso',
    'Mercury', 'Sea-Doo',
)


def _find_line_labels(line):
    candidates = []
    for field_name, patterns in FIELD_LABELS.items():
        for pattern in patterns:
            for match in re.finditer(
                rf'(?<![A-Z0-9])(?:{pattern})(?![A-Z0-9])',
                line,
                re.IGNORECASE,
            ):
                candidates.append((match.start(), match.end(), field_name))
    for pattern in NON_TECHNICAL_LABELS:
        for match in re.finditer(
            rf'(?<![A-Z0-9])(?:{pattern})(?![A-Z0-9])',
            line,
            re.IGNORECASE,
        ):
            candidates.append((match.start(), match.end(), None))

    labels = []
    for candidate in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        if labels and candidate[0] < labels[-1][1]:
            continue
        labels.append(candidate)
    return labels


def _read_label_values(lines):
    values = {}
    for line_index, line in enumerate(lines):
        labels = _find_line_labels(line)
        for label_index, (start, end, field_name) in enumerate(labels):
            if field_name is None:
                continue
            next_start = labels[label_index + 1][0] if label_index + 1 < len(labels) else len(line)
            value = line[end:next_start].strip(' \t:;#.-_/')
            if not value and line_index + 1 < len(lines):
                next_line = lines[line_index + 1]
                next_labels = _find_line_labels(next_line)
                continuation_end = next_labels[0][0] if next_labels else len(next_line)
                value = next_line[:continuation_end].strip(' \t:;#.-_/')
            if value:
                values.setdefault(field_name, value)
    return values


def _split_make_series(value):
    folded = value.casefold()
    for make in COMMON_MAKES:
        if folded.startswith(make.casefold()):
            series = value[len(make):].strip(' -:/')
            return make, series
    return value, ''


def _decimal(value):
    cleaned = re.sub(r'[^0-9.,]', '', value).replace(',', '')
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return ''
    return format(number, 'f')


def _date(value):
    numeric_date = re.search(
        r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b',
        value,
    )
    if numeric_date:
        first, second, year = (int(part) for part in numeric_date.groups())
        if first <= 12 and second <= 12:
            return ''
        date_format = '%d/%m/%Y' if first > 12 else '%m/%d/%Y'
        normalized = numeric_date.group().replace('-', '/')
        try:
            return datetime.strptime(normalized, date_format).date().isoformat()
        except ValueError:
            return ''

    candidates = re.findall(
        r'\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|'
        r'\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b',
        value,
    )
    formats = (
        '%Y-%m-%d', '%Y/%m/%d', '%d %B %Y', '%d %b %Y',
        '%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y',
    )
    for candidate in candidates:
        for date_format in formats:
            try:
                return datetime.strptime(candidate, date_format).date().isoformat()
            except ValueError:
                continue
    return ''


def extract_fields_from_text(text, is_seacraft=False):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    values = _read_label_values(lines)
    for field_name, value in tuple(values.items()):
        if not value:
            continue
        if field_name in {'registration_date', 'registration_expiry', 'inspection_expiry'}:
            value = _date(value)
        elif field_name in {
            'gross_vehicle_weight',
            'net_capacity',
            'engine_displacement_cc',
            'engine_power_hp',
            'length_m',
            'gross_tonnage',
            'net_tonnage',
        }:
            value = _decimal(value)
        elif field_name in {'model_year', 'passenger_capacity'}:
            match = re.search(r'\d{1,4}', value.replace(',', ''))
            value = match.group() if match else ''
        else:
            value = re.sub(r'\s+', ' ', value).strip(' \t:;#.-_')
        if value:
            values[field_name] = value
        else:
            values.pop(field_name)

    if values.get('make'):
        make, series = _split_make_series(values['make'])
        values['make'] = make[:100]
        if series and not values.get('model_name'):
            values['model_name'] = series

    allowed_fields = SEA_FIELDS if is_seacraft else LAND_FIELDS
    return {
        field: str(value)[:200]
        for field, value in values.items()
        if field in allowed_fields and value
    }


def _read_image(uploaded_file):
    if uploaded_file.size > MAX_IMAGE_SIZE:
        raise RegistrationImageError('Each OR/CR image must be 10 MB or smaller.')
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        if image.format not in {'JPEG', 'PNG', 'WEBP'}:
            raise RegistrationImageError('Upload OR/CR images as JPEG, PNG, or WebP.')
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise RegistrationImageError('The OR/CR image dimensions are too large to process.')
        image = ImageOps.exif_transpose(image).convert('L')
        if image.width < 1800:
            scale = min(3, 1800 / image.width)
            image = image.resize(
                (int(image.width * scale), int(image.height * scale)),
                Image.Resampling.LANCZOS,
            )
        return ImageOps.autocontrast(image)
    except RegistrationImageError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise RegistrationImageError('The uploaded file is not a readable image.') from error
    finally:
        uploaded_file.seek(0)


def extract_registration_document_fields(uploaded_files, is_seacraft=False):
    files = list(uploaded_files)
    if not files:
        raise RegistrationImageError('Choose at least one OR/CR image.')
    if len(files) > MAX_IMAGE_COUNT:
        raise RegistrationImageError('Upload no more than five OR/CR images at once.')

    configured_command = getattr(settings, 'TESSERACT_CMD', '')
    if configured_command:
        pytesseract.pytesseract.tesseract_cmd = configured_command

    extracted = {}
    for uploaded_file in files:
        image = _read_image(uploaded_file)
        try:
            text = pytesseract.image_to_string(
                image,
                lang='eng',
                config='--oem 3 --psm 6',
                timeout=OCR_TIMEOUT_SECONDS,
            )
        except TesseractNotFoundError as error:
            raise RegistrationOcrUnavailable(
                'Local Tesseract OCR is not installed or configured on the application server.'
            ) from error
        except (TesseractError, RuntimeError) as error:
            raise RegistrationOcrError(
                'Tesseract could not read this image. Try a sharper, well-lit photo.'
            ) from error

        for field, value in extract_fields_from_text(text, is_seacraft).items():
            extracted.setdefault(field, value)
    return extracted
