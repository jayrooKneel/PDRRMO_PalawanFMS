import json

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType


def snapshot_vehicle_details(vehicle):
    snapshot = {}
    for field in vehicle._meta.concrete_fields:
        if field.primary_key:
            continue
        raw_value = field.value_from_object(vehicle)
        display_value = raw_value
        if raw_value is None or raw_value == '':
            display_value = 'Not set'
        else:
            display_method = getattr(vehicle, f'get_{field.name}_display', None)
            if display_method:
                display_value = display_method()
            elif field.is_relation:
                related_object = getattr(vehicle, field.name, None)
                display_value = str(related_object) if related_object else 'Not set'
            elif hasattr(raw_value, 'isoformat'):
                display_value = raw_value.isoformat()
            else:
                display_value = str(raw_value)
        snapshot[field.name] = (raw_value, str(display_value))
    return snapshot


def _format_audit_value(value):
    return json.dumps(value, ensure_ascii=False)


def describe_vehicle_details(vehicle):
    snapshot = snapshot_vehicle_details(vehicle)
    details = []
    for field in vehicle._meta.concrete_fields:
        if field.primary_key:
            continue
        raw_value, display_value = snapshot[field.name]
        if raw_value is None or raw_value == '':
            continue
        label = str(field.verbose_name).capitalize()
        details.append(f'{label}: {_format_audit_value(display_value)}')
    return '; '.join(details)


def describe_vehicle_changes(before, vehicle):
    after = snapshot_vehicle_details(vehicle)
    changes = []
    for field in vehicle._meta.concrete_fields:
        if field.primary_key:
            continue
        old_raw, old_display = before[field.name]
        new_raw, new_display = after[field.name]
        if old_raw == new_raw:
            continue
        label = str(field.verbose_name).capitalize()
        changes.append(
            f'{label}: {_format_audit_value(old_display)} -> '
            f'{_format_audit_value(new_display)}'
        )
    return '; '.join(changes)


def log_vehicle_audit(
    request,
    vehicle,
    action_flag,
    summary,
    before=None,
    added_document_count=0,
):
    if before is None:
        details = describe_vehicle_details(vehicle)
        message = f'{summary} Initial details: {details}' if details else summary
    else:
        changes = describe_vehicle_changes(before, vehicle)
        message = (
            f'{summary} Changes: {changes}'
            if changes else f'{summary} No fleet detail fields changed.'
        )

    if added_document_count:
        message += f' OR/CR attachments added: {added_document_count}.'

    return LogEntry.objects.create(
        user=request.user,
        content_type=ContentType.objects.get_for_model(vehicle),
        object_id=str(vehicle.pk),
        object_repr=str(vehicle),
        action_flag=action_flag,
        change_message=message,
    )
