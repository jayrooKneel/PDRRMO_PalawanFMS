(() => {
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
            document.querySelectorAll("[data-assigned-vehicle-id]").forEach((label) => {
                const assignedVehicleId = label.dataset.assignedVehicleId;
                if (assignedVehicleId !== vehicleId && assignedVehicleId !== releasedVehicleId) return;
                const isAssigned = assignedVehicleId === vehicleId && result.driver_name;
                label.replaceChildren(document.createTextNode(
                    isAssigned ? result.driver_name : "Standby / Unassigned",
                ));
                label.classList.toggle("text-muted", !isAssigned);
            });
            document.querySelectorAll(".btn-deploy-trigger[data-vehicle-id]").forEach((button) => {
                if (button.dataset.vehicleId === vehicleId) {
                    button.dataset.assignedDriverId = currentDriverId;
                }
            });
            const seaVehiclesElement = document.getElementById("sea-vehicles-json");
            if (seaVehiclesElement) {
                const seaVehicles = JSON.parse(seaVehiclesElement.textContent || "[]");
                seaVehicles.forEach((vehicle) => {
                    if (String(vehicle.id) === vehicleId) vehicle.driver_id = currentDriverId;
                    if (releasedVehicleId && String(vehicle.id) === releasedVehicleId) vehicle.driver_id = "";
                });
                seaVehiclesElement.textContent = JSON.stringify(seaVehicles);
            }
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
})();
