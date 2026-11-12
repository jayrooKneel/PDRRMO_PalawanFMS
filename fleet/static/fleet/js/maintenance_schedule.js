document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-maintenance-schedule-form]').forEach(function (form) {
        const typeField = form.querySelector('[name$="-maintenance_type"]');
        const dateField = form.querySelector('[data-maintenance-date-field]');
        const intervalField = form.querySelector('[data-oil-interval-field]');

        if (!typeField || !dateField || !intervalField) {
            return;
        }

        function updateScheduleFields() {
            const isOil = typeField.value === 'OIL';
            dateField.hidden = isOil;
            intervalField.hidden = !isOil;
            const dateInput = dateField.querySelector('input');
            const intervalInput = intervalField.querySelector('select');
            if (dateInput) {
                dateInput.required = !isOil;
            }
            if (intervalInput) {
                intervalInput.required = isOil;
            }
        }

        typeField.addEventListener('change', updateScheduleFields);
        updateScheduleFields();
    });
});
