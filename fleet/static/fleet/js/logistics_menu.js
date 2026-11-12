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

    const operatorModal = document.getElementById("addOperatorModal");
    const operatorForm = operatorModal?.querySelector("form");
    let pendingOperatorEdit = null;
    let openOperatorAfterManagerClose = false;

    function prepareOperatorForm(operator = null) {
        if (!operatorModal || !operatorForm) {
            throw new Error("The driver/operator form was not found.");
        }
        operatorForm.reset();
        operatorForm.querySelector("[data-operator-action]").value =
            operator ? "update_operator" : "add_operator";
        operatorForm.querySelector("[data-operator-id]").value = operator?.id || "";
        document.getElementById("addOperatorModalLabel").textContent = operator
            ? "Edit Driver / Operator"
            : "Add Driver / Operator Details";
        operatorForm.querySelector("button[type='submit']").innerHTML = operator
            ? '<i class="fa-solid fa-floppy-disk me-1"></i>Update Operator'
            : '<i class="fa-solid fa-floppy-disk me-1"></i>Save Operator';

        const documentInput = operatorForm.querySelector("[data-operator-documents]");
        if (documentInput) documentInput.removeAttribute("capture");
        operatorForm.dataset.replaceLicenseFieldsOnScan =
            operator?.replaceLicenseFieldsOnScan ? "true" : "false";
        if (!operator) return;

        operatorForm.querySelector("[name='operator_type']").value =
            operator.type === "MARINA" || operator.type === "SEA" ? "SEA" : "LAND";
        operatorForm.querySelector("[name='name']").value = operator.name || "";
        operatorForm.querySelector("[name='license_number']").value = operator.license || "";
        operatorForm.querySelector("[name='license_class']").value = operator.licenseClass || "";
        operatorForm.querySelector("[name='license_expiry']").value = operator.expiry || "";
        operatorForm.querySelector("[name='phone_number']").value = operator.phone || "";
        operatorModal.querySelector("[data-operator-ocr-status]").textContent =
            operator.replaceLicenseFieldsOnScan
                ? "Scan or upload the renewed license to replace its number, class, and expiry date; otherwise review and update them manually."
                : "Select a replacement license image to scan and store it; otherwise the saved image is kept.";
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
            const operator = {
                id: editButton.dataset.driverId,
                type: editButton.dataset.driverType,
                name: editButton.dataset.driverName,
                license: editButton.dataset.driverLicense,
                licenseClass: editButton.dataset.driverClass,
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

    document.addEventListener("change", (event) => {
        if (!(event.target instanceof HTMLSelectElement)) return;
        const select = event.target;
        const form = select.closest("form[data-driver-assignment-form]");
        if (!form) return;
        form.requestSubmit();
    });

    document.addEventListener("submit", async (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.matches("[data-driver-assignment-form]")) return;
        event.preventDefault();

        const select = form.querySelector('select[name="driver_id"]');
        const status = form.closest("[data-driver-assignment-row]")?.querySelector("[data-assignment-status]")
            || form.parentElement.querySelector("[data-assignment-status]");
        if (!select || !status) {
            throw new Error("Driver assignment controls are incomplete.");
        }

        const previousValue = select.dataset.currentDriver || "";
        const wasDisabled = select.disabled;
        const formData = new FormData(form);
        const csrfToken = formData.get("csrfmiddlewaretoken");
        select.disabled = true;
        status.textContent = "Saving driver assignment…";
        status.classList.remove("text-danger", "text-success");
        try {
            const response = await fetch(form.getAttribute("action"), {
                method: "POST",
                body: formData,
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
                },
            });
            const responseText = await response.text();
            let result;
            try {
                result = JSON.parse(responseText);
            } catch (error) {
                console.error("Driver assignment returned a non-JSON response.", {
                    status: response.status,
                    redirected: response.redirected,
                    body: responseText.slice(0, 1000),
                    error,
                });
                if (response.redirected) {
                    throw new Error("Your session may have expired. Sign in again, then retry the assignment.");
                }
                throw new Error(`The assignment request failed (HTTP ${response.status}). Refresh the page and retry.`);
            }
            if (!response.ok || !result.ok) {
                throw new Error(result.message || "The assignment could not be saved.");
            }

            const vehicleId = String(result.vehicle_id);
            const previousDriverId = String(result.previous_driver_id || "");
            const releasedVehicleId = String(result.released_vehicle_id || "");
            const currentDriverId = String(result.driver_id || "");
            document.querySelectorAll("form[data-driver-assignment-form]").forEach((assignmentForm) => {
                const assignmentSelect = assignmentForm.querySelector('select[name="driver_id"]');
                const assignedVehicleId = assignmentForm.querySelector('[name="vehicle_id"]')?.value;
                if (!assignmentSelect) return;
                Array.from(assignmentSelect.options).forEach((option) => {
                    const optionDriverId = option.dataset.driverId;
                    if (optionDriverId !== previousDriverId && optionDriverId !== currentDriverId) return;
                    const expired = option.dataset.licenseExpired === "true";
                    option.disabled = expired
                        || Boolean(currentDriverId && optionDriverId === currentDriverId && assignedVehicleId !== vehicleId);
                });
                if (assignedVehicleId === vehicleId) {
                    assignmentSelect.value = currentDriverId;
                    assignmentSelect.dataset.currentDriver = currentDriverId;
                } else if (releasedVehicleId && assignedVehicleId === releasedVehicleId) {
                    assignmentSelect.value = "";
                    assignmentSelect.dataset.currentDriver = "";
                }
                if (assignedVehicleId === vehicleId || (releasedVehicleId && assignedVehicleId === releasedVehicleId)) {
                    const label = assignmentForm.closest("[data-driver-assignment-row]")
                        ?.querySelector("[data-assigned-driver-label]");
                    if (label) {
                        label.replaceChildren(document.createTextNode(
                            assignedVehicleId === vehicleId && result.driver_name
                                ? `Assigned: ${result.driver_name}`
                                : "Unassigned",
                        ));
                        label.classList.remove("text-danger", "fw-bold");
                        label.classList.toggle("text-muted", !(
                            assignedVehicleId === vehicleId && result.driver_name
                        ));
                    }
                }
            });
            status.textContent = result.message;
            status.classList.add("text-success");
            if (typeof window.refreshLogisticsDashboardData === "function") {
                await window.refreshLogisticsDashboardData([
                    "logistics-land-assignments",
                    "logistics-sea-assignments",
                    "logistics-asset-rows",
                ]);
            }
        } catch (error) {
            select.value = previousValue;
            status.textContent = error.message;
            status.classList.add("text-danger");
        } finally {
            select.disabled = wasDisabled;
        }
    });

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
