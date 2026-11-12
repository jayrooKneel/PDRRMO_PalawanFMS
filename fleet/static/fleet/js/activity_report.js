document.addEventListener('DOMContentLoaded', function () {
    const reportKind = document.getElementById('report-kind');
    const maintenanceCategoryField = document.getElementById('maintenance-category-field');
    const reportVehicleField = document.getElementById('report-vehicle-field');
    const reportVehicle = document.getElementById('report-vehicle');
    if (reportKind && maintenanceCategoryField && reportVehicleField && reportVehicle) {
        const updateMaintenanceCategory = () => {
            maintenanceCategoryField.classList.toggle('d-none', reportKind.value !== 'maintenance');
            reportVehicleField.classList.toggle('d-none', reportKind.value !== 'maintenance');
            reportVehicle.disabled = reportKind.value !== 'maintenance';
        };
        reportKind.addEventListener('change', updateMaintenanceCategory);
        updateMaintenanceCategory();
    }

    const reportModal = document.getElementById('generateReportModal');
    const incidentModal = document.getElementById('fleetIncidentModal');
    const openIncidentButton = document.querySelector('[data-open-incident-report]');
    if (reportModal && incidentModal && openIncidentButton) {
        openIncidentButton.addEventListener('click', function () {
            reportModal.addEventListener('hidden.bs.modal', function () {
                bootstrap.Modal.getOrCreateInstance(incidentModal).show();
            }, { once: true });
            bootstrap.Modal.getOrCreateInstance(reportModal).hide();
        });
    }

    const reportPeriod = document.getElementById('report-period');
    if (!reportPeriod) {
        return;
    }

    const updateReportDateFields = () => {
        document.querySelectorAll('.report-date-field').forEach(field => {
            const active = field.dataset.period === reportPeriod.value;
            field.classList.toggle('d-none', !active);
            field.querySelectorAll('input').forEach(input => {
                input.disabled = !active;
                input.required = active;
            });
        });
    };

    reportPeriod.addEventListener('change', updateReportDateFields);
    updateReportDateFields();
});
