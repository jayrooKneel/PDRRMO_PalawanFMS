(() => {
    const menuDrawer = document.getElementById("logisticsMenuDrawer");
    if (!menuDrawer) return;

    function showModal(id) {
        const modal = document.getElementById(id);
        if (!modal) {
            throw new Error(`Logistics menu target #${id} was not found.`);
        }
        window.bootstrap.Modal.getOrCreateInstance(modal).show();
    }

    function runAction(action) {
        if (action === "print") {
            window.print();
        } else if (action === "view-incidents") {
            const reports = document.getElementById("filedIncidentReports");
            if (!reports) throw new Error("Filed incident reports section was not found.");
            reports.scrollIntoView({ behavior: "smooth" });
        } else if (action === "add-operator") {
            showModal("addOperatorModal");
        } else if (action === "manage-operators") {
            showModal("manageOperatorsModal");
        } else if (action === "manage-assets") {
            showModal("manageAssetsModal");
        } else if (action === "maintenance-report") {
            const reportKind = document.getElementById("report-kind");
            if (!reportKind) throw new Error("Report selection was not found.");
            reportKind.value = "maintenance";
            reportKind.dispatchEvent(new Event("change", { bubbles: true }));
            showModal("generateReportModal");
        } else if (action === "add-asset") {
            showModal("addVehicleModal");
        } else if (action === "generate-report") {
            showModal("generateReportModal");
        } else if (action === "file-incident") {
            showModal("fleetIncidentModal");
        } else if (action === "print-incident") {
            const reportKind = document.getElementById("report-kind");
            if (!reportKind) throw new Error("Incident report selection was not found.");
            reportKind.value = "incident";
            reportKind.dispatchEvent(new Event("change", { bubbles: true }));
            showModal("generateReportModal");
        } else if (action === "operators") {
            const assignmentDrawer = document.getElementById("operatorAssignmentDrawer");
            if (!assignmentDrawer) {
                throw new Error("Personnel operator assignment panel was not found.");
            }
            window.bootstrap.Offcanvas.getOrCreateInstance(assignmentDrawer).show();
        }
    }

    menuDrawer.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        const button = event.target.closest("[data-menu-action]");
        if (!button || !menuDrawer.contains(button)) return;

        menuDrawer.dataset.pendingAction = button.dataset.menuAction;
        window.bootstrap.Offcanvas.getOrCreateInstance(menuDrawer).hide();
    });

    menuDrawer.addEventListener("hidden.bs.offcanvas", () => {
        const action = menuDrawer.dataset.pendingAction;
        delete menuDrawer.dataset.pendingAction;
        if (!action) return;

        try {
            runAction(action);
        } catch (error) {
            console.error(`Could not run logistics menu action "${action}".`, error);
            window.alert("This menu action could not be opened. Please refresh the page and try again.");
        }
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        const maintenanceButton = event.target.closest("[data-open-maintenance-report]");
        if (maintenanceButton) {
            const reportKind = document.getElementById("report-kind");
            const reportVehicle = document.getElementById("report-vehicle");
            if (!reportKind || !reportVehicle) {
                throw new Error("Maintenance report selection was not found.");
            }
            reportKind.value = "maintenance";
            reportKind.dispatchEvent(new Event("change", { bubbles: true }));
            reportVehicle.value = maintenanceButton.dataset.openMaintenanceReport;
            const parentModal = maintenanceButton.closest(".modal");
            if (parentModal && parentModal.classList.contains("show")) {
                parentModal.addEventListener("hidden.bs.modal", () => showModal("generateReportModal"), { once: true });
                window.bootstrap.Modal.getOrCreateInstance(parentModal).hide();
            } else {
                showModal("generateReportModal");
            }
            return;
        }
        const button = event.target.closest("[data-dashboard-action]");
        if (!button) return;
        const action = button.dataset.dashboardAction;
        if (action === "maintenance-report") {
            const reportKind = document.getElementById("report-kind");
            if (!reportKind) throw new Error("Report selection was not found.");
            reportKind.value = "maintenance";
            reportKind.dispatchEvent(new Event("change", { bubbles: true }));
            showModal("generateReportModal");
            return;
        }
        try {
            runAction(action);
        } catch (error) {
            console.error(`Could not run dashboard action "${action}".`, error);
            window.alert("This dashboard action could not be opened. Please refresh the page and try again.");
        }
    });
})();
