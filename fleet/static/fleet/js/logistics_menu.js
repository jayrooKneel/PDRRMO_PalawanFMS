(() => {
    const manageAssetsModal = document.getElementById("manageAssetsModal");
    const assetForm = document.getElementById("editFleetAssetForm");
    const assetModal = document.getElementById("editVehicleModal");
    let pendingAssetEdit = null;

    function openAssetEdit() {
        if (!pendingAssetEdit || !assetForm || !assetModal) {
            throw new Error("The selected fleet asset could not be opened for editing.");
        }
        assetForm.reset();
        assetForm.querySelector("[data-edit-vehicle-id]").value = pendingAssetEdit.id;
        Object.entries(pendingAssetEdit).forEach(([name, value]) => {
            const field = assetForm.querySelector(`[name="edit-asset-${name}"]`);
            if (field && field.type !== "file") field.value = value;
        });
        window.bootstrap.Modal.getOrCreateInstance(assetModal).show();
        pendingAssetEdit = null;
    }

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        const button = event.target.closest("[data-edit-asset]");
        if (!button) return;

        const assetsElement = document.getElementById("fleet-assets-json");
        if (!assetsElement || !manageAssetsModal) {
            throw new Error("Fleet asset editing controls were not found.");
        }
        const assets = JSON.parse(assetsElement.textContent || "[]");
        pendingAssetEdit = assets.find((asset) => String(asset.id) === button.dataset.assetId);
        if (!pendingAssetEdit) {
            throw new Error(`Fleet asset ${button.dataset.assetId} was not found.`);
        }

        if (!manageAssetsModal.classList.contains("show")) {
            openAssetEdit();
            return;
        }
        manageAssetsModal.addEventListener("hidden.bs.modal", openAssetEdit, { once: true });
        window.bootstrap.Modal.getOrCreateInstance(manageAssetsModal).hide();
    });

    const menuDrawer = document.getElementById("logisticsMenuDrawer");
    if (!menuDrawer) return;

    const assetRows = document.querySelector("[data-dashboard-refresh-content='logistics-asset-rows']");
    const statusFilter = document.querySelector("[data-fleet-management-filter='status']");
    const categoryFilter = document.querySelector("[data-fleet-management-filter='category']");
    if (assetRows && statusFilter && categoryFilter) {
        const applyAssetFilters = () => {
            const selectedStatus = statusFilter.value;
            const selectedCategory = categoryFilter.value.trim().toLowerCase();
            assetRows.querySelectorAll("[data-fleet-management-row]").forEach((row) => {
                const status = row.dataset.vehicleStatus;
                const category = row.dataset.vehicleCategory.trim().toLowerCase();
                const isArchived = status === "ARCHIVED" || status === "DISPOSED";
                const matchesStatus = selectedStatus === "all"
                    || (selectedStatus === "active" && !isArchived)
                    || (selectedStatus === "ARCHIVED" && isArchived)
                    || (selectedStatus === "MAINTENANCE" && (status === "MAINTENANCE" || status === "PENDING_DISPOSAL"))
                    || status === selectedStatus;
                row.hidden = !matchesStatus || (selectedCategory !== "" && category !== selectedCategory);
            });
        };
        statusFilter.addEventListener("change", applyAssetFilters);
        categoryFilter.addEventListener("change", applyAssetFilters);
        new MutationObserver(applyAssetFilters).observe(assetRows, { childList: true, subtree: true });
        applyAssetFilters();
    }

    function showModal(id) {
        const modal = document.getElementById(id);
        if (!modal) {
            throw new Error(`Logistics menu target #${id} was not found.`);
        }
        window.bootstrap.Modal.getOrCreateInstance(modal).show();
    }

    const operatorModal = document.getElementById("addOperatorModal");
    const operatorForm = operatorModal?.querySelector("form");
    let pendingOperatorEdit = null;
    let openOperatorAfterManagerClose = false;

    function prepareOperatorForm(operator = null) {
        if (!operatorModal || !operatorForm) {
            throw new Error("The driver/operator form was not found.");
        }
        const operatorEntries = document.getElementById("operatorRegistrationEntries");
        const firstEntry = operatorEntries?.querySelector("[data-operator-entry]");
        if (!operatorEntries || !firstEntry) {
            throw new Error("The driver/operator registration fields were not found.");
        }
        operatorEntries.querySelectorAll("[data-operator-entry]").forEach((entry) => {
            if (entry !== firstEntry) entry.remove();
        });
        operatorForm.reset();
        document.getElementById("operatorCount").value = "1";
        document.getElementById("addOperatorEntry").hidden = Boolean(operator);
        operatorForm.querySelector("[data-operator-action]").value =
            operator ? "update_operator" : "add_operator";
        operatorForm.querySelector("[data-operator-id]").value = operator?.id || "";
        document.getElementById("addOperatorModalLabel").textContent = operator
            ? "Edit Driver / Operator"
            : "Add Driver / Operator Details";
        operatorForm.querySelector("button[type='submit']").innerHTML = operator
            ? '<i class="fa-solid fa-floppy-disk me-1"></i>Update Operator'
            : '<i class="fa-solid fa-floppy-disk me-1"></i>Save Operator';

        const documentInput = firstEntry.querySelector("[data-operator-documents]");
        if (documentInput) documentInput.removeAttribute("capture");
        firstEntry.dataset.replaceLicenseFieldsOnScan =
            operator?.replaceLicenseFieldsOnScan ? "true" : "false";
        if (!operator) return;

        firstEntry.querySelector("[name$='-operator_type']").value =
            operator.type === "MARINA" || operator.type === "SEA" ? "SEA" : "LAND";
        firstEntry.querySelector("[name$='-operator_type']").dispatchEvent(
            new Event("change", { bubbles: true }),
        );
        firstEntry.querySelector("[name$='-name']").value = operator.name || "";
        firstEntry.querySelector("[name$='-license_number']").value = operator.license || "";
        firstEntry.querySelector("[name$='-license_class']").value = operator.licenseClass || "";
        firstEntry.querySelector("[name$='-license_type']").value = operator.licenseType || "";
        firstEntry.querySelector("[name$='-license_restrictions']").value = operator.licenseRestrictions || "";
        firstEntry.querySelector("[name$='-emergency_contact_name']").value =
            operator.emergencyContactName || "";
        firstEntry.querySelector("[name$='-emergency_contact_number']").value =
            operator.emergencyContactNumber || "";
        firstEntry.querySelector("[name$='-license_expiry']").value = operator.expiry || "";
        firstEntry.querySelector("[name$='-phone_number']").value = operator.phone || "";
        firstEntry.querySelector("[data-operator-ocr-status]").textContent =
            operator.replaceLicenseFieldsOnScan
                ? "Scan or upload the renewed license to replace its number, class, type, restrictions, and expiry; review them before saving."
                : "Select replacement license images to scan and store them; otherwise the saved images are kept.";
    }

    const manageOperatorsModal = document.getElementById("manageOperatorsModal");
    manageOperatorsModal?.addEventListener("hidden.bs.modal", () => {
        if (!pendingOperatorEdit && !openOperatorAfterManagerClose) return;
        prepareOperatorForm(pendingOperatorEdit);
        pendingOperatorEdit = null;
        openOperatorAfterManagerClose = false;
        showModal("addOperatorModal");
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        const editButton = event.target.closest("[data-edit-operator]");
        if (editButton) {
            event.preventDefault();
            const operator = {
                id: editButton.dataset.driverId,
                type: editButton.dataset.driverType,
                name: editButton.dataset.driverName,
                license: editButton.dataset.driverLicense,
                licenseClass: editButton.dataset.driverClass,
                licenseType: editButton.dataset.driverLicenseType,
                licenseRestrictions: editButton.dataset.driverRestrictions,
                emergencyContactName: editButton.dataset.driverEmergencyContactName,
                emergencyContactNumber: editButton.dataset.driverEmergencyContactNumber,
                expiry: editButton.dataset.driverExpiry,
                phone: editButton.dataset.driverPhone,
                replaceLicenseFieldsOnScan: editButton.dataset.licenseRefresh === "true",
            };
            if (manageOperatorsModal?.classList.contains("show")) {
                pendingOperatorEdit = operator;
                window.bootstrap.Modal.getOrCreateInstance(manageOperatorsModal).hide();
            } else {
                prepareOperatorForm(operator);
                showModal("addOperatorModal");
            }
            return;
        }
        if (event.target.closest("[data-open-add-operator]")) {
            openOperatorAfterManagerClose = true;
        }
    }, true);

    function runAction(action) {
        if (action === "print") {
            window.print();
        } else if (action === "view-incidents") {
            const reports = document.getElementById("filedIncidentReports");
            if (!reports) throw new Error("Filed incident reports section was not found.");
            reports.scrollIntoView({ behavior: "smooth" });
        } else if (action === "manage-operators") {
            showModal("manageOperatorsModal");
        } else if (action === "add-operator") {
            prepareOperatorForm();
            showModal("addOperatorModal");
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
        } else if (action === "fleet-report") {
            const reportKind = document.getElementById("report-kind");
            const reportVehicle = document.getElementById("report-vehicle");
            const fleetWideInput = document.getElementById("report-fleet-wide");
            if (!reportKind || !reportVehicle || !fleetWideInput) {
                throw new Error("Fleet-wide report controls were not found.");
            }
            fleetWideInput.dataset.fleetWideShortcut = "true";
            reportKind.value = "activity";
            reportKind.dispatchEvent(new Event("change", { bubbles: true }));
            reportVehicle.value = "";
            fleetWideInput.value = "true";
            showModal("generateReportModal");
        } else if (action === "inventory-report") {
            const reportKind = document.getElementById("report-kind");
            const reportVehicle = document.getElementById("report-vehicle");
            const fleetWideInput = document.getElementById("report-fleet-wide");
            if (!reportKind || !reportVehicle || !fleetWideInput) {
                throw new Error("Fleet inventory report controls were not found.");
            }
            fleetWideInput.dataset.fleetWideShortcut = "true";
            reportKind.value = "inventory";
            reportKind.dispatchEvent(new Event("change", { bubbles: true }));
            reportVehicle.value = "";
            fleetWideInput.value = "true";
            showModal("generateReportModal");
        } else if (action === "driver-report") {
            const reportKind = document.getElementById("report-kind");
            if (!reportKind) throw new Error("Report selection was not found.");
            reportKind.value = "drivers";
            reportKind.dispatchEvent(new Event("change", { bubbles: true }));
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

        const action = button.dataset.menuAction;
        if (action === "add-asset") {
            try {
                runAction(action);
                window.bootstrap.Offcanvas.getOrCreateInstance(menuDrawer).hide();
            } catch (error) {
                console.error(`Could not run logistics menu action "${action}".`, error);
                window.alert("This menu action could not be opened. Please refresh the page and try again.");
            }
            return;
        }

        menuDrawer.dataset.pendingAction = action;
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
        const openAction = () => {
            try {
                if (action === "maintenance-report") {
                    const reportKind = document.getElementById("report-kind");
                    if (!reportKind) throw new Error("Report selection was not found.");
                    reportKind.value = "maintenance";
                    reportKind.dispatchEvent(new Event("change", { bubbles: true }));
                    showModal("generateReportModal");
                    return;
                }
                runAction(action);
            } catch (error) {
                console.error(`Could not run dashboard action "${action}".`, error);
                window.alert("This dashboard action could not be opened. Please refresh the page and try again.");
            }
        };
        const parentModal = button.closest(".modal.show");
        if (parentModal && button.getAttribute("data-bs-dismiss") === "modal") {
            parentModal.addEventListener("hidden.bs.modal", openAction, { once: true });
            return;
        }
        openAction();
    });
})();
