document.addEventListener('DOMContentLoaded', function () {
    const reportKind = document.getElementById('report-kind');
    const maintenanceCategoryField = document.getElementById('maintenance-category-field');
    const reportVehicleField = document.getElementById('report-vehicle-field');
    const reportVehicle = document.getElementById('report-vehicle');
    const driverReportFilters = document.getElementById('driver-report-filters');
    const reportPeriodControls = document.getElementById('report-period-controls');
    const reportPeriod = document.getElementById('report-period');
    const updateReportKindFields = () => {
        if (!reportKind) return;
        const isDriverReport = reportKind.value === 'drivers';
        maintenanceCategoryField?.classList.toggle(
            'd-none',
            isDriverReport || reportKind.value !== 'maintenance',
        );
        reportVehicleField?.classList.toggle(
            'd-none',
            isDriverReport || reportKind.value !== 'maintenance',
        );
        if (reportVehicle) reportVehicle.disabled = isDriverReport || reportKind.value !== 'maintenance';
        driverReportFilters?.classList.toggle('d-none', !isDriverReport);
        driverReportFilters?.querySelectorAll('input, select').forEach((field) => {
            field.disabled = !isDriverReport;
        });
        reportPeriodControls?.classList.toggle('d-none', isDriverReport);
        if (reportPeriod) {
            reportPeriod.disabled = isDriverReport;
            reportPeriod.required = !isDriverReport;
        }
        document.querySelectorAll('.report-date-field input').forEach((field) => {
            if (isDriverReport) {
                field.disabled = true;
                field.required = false;
            }
        });
        if (!isDriverReport) updateReportDateFields();
    };
    if (reportKind && maintenanceCategoryField && reportVehicleField && reportVehicle) {
        reportKind.addEventListener('change', updateReportKindFields);
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

    function updateReportDateFields() {
        if (!reportPeriod || reportKind?.value === 'drivers') return;
        document.querySelectorAll('.report-date-field').forEach(field => {
            const active = field.dataset.period === reportPeriod.value;
            field.classList.toggle('d-none', !active);
            field.querySelectorAll('input').forEach(input => {
                input.disabled = !active;
                input.required = active;
            });
        });
    }

    reportPeriod?.addEventListener('change', updateReportDateFields);
    updateReportKindFields();
    updateReportDateFields();
});
