(() => {
    const modal = document.getElementById("deployVehicleModal");
    if (!modal) return;

    const parseJson = (id) => {
        const element = document.getElementById(id);
        if (!element) throw new Error(`Deployment data #${id} was not found.`);
        return JSON.parse(element.textContent || "[]");
    };

    modal.addEventListener("show.bs.modal", (event) => {
        const button = event.relatedTarget;
        if (!(button instanceof HTMLElement) || !button.matches(".btn-deploy-trigger")) return;

        const vehicleId = button.dataset.vehicleId;
        const modelName = button.dataset.modelName || "";
        const category = button.dataset.vehicleCategory;
        const currentDriverId = button.dataset.assignedDriverId || "";
        const landDrivers = parseJson("land-drivers-json");
        const seaDrivers = parseJson("sea-drivers-json");
        const landVehicles = parseJson("land-vehicles-json");
        const seaVehicles = parseJson("sea-vehicles-json");

        document.getElementById("deploy_vehicle_id_input").value = vehicleId;
        document.getElementById("deployModalHeaderTitle").textContent = `Deploy Fleet Unit — ${modelName}`;
        document.getElementById("deployment_location_input").value = "";
        document.getElementById("deployment_purpose_input").selectedIndex = 0;

        const now = new Date();
        now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
        document.getElementById("deploy_time_input").value = now.toISOString().slice(0, 16);

        const driverSelect = document.getElementById("deploy_driver_select");
        driverSelect.replaceChildren(new Option("-- Select Personnel Operator --", "", true, true));

        const drivers = category === "SEA" ? seaDrivers : landDrivers;
        const vehicles = category === "SEA" ? seaVehicles : landVehicles;
        const driverVehicleMap = new Map(
            vehicles
                .filter((vehicle) => vehicle.driver_id)
                .map((vehicle) => [String(vehicle.driver_id), vehicle]),
        );
        let availableCount = 0;

        drivers.forEach((driver) => {
            const option = new Option("", driver.id);
            const assignedVehicle = driverVehicleMap.get(String(driver.id));

            if (driver.license_expired) {
                option.textContent = `⚠ ${driver.name} [LICENSE EXPIRED]`;
                option.classList.add("text-danger", "fw-bold");
                option.disabled = true;
            } else if (currentDriverId && String(driver.id) === String(currentDriverId)) {
                option.textContent = `👤 ${driver.name} [Assigned to this Fleet]`;
                option.selected = true;
                option.style.color = "#8a6d00";
                option.style.fontWeight = "700";
                availableCount += 1;
            } else if (!assignedVehicle) {
                option.textContent = `👤 ${driver.name} [Standby & Available]`;
                availableCount += 1;
            } else if (
                assignedVehicle.status === "MAINTENANCE"
                || assignedVehicle.status === "PENDING_DISPOSAL"
            ) {
                option.textContent = `👤 ${driver.name} [Assigned to ${assignedVehicle.model_name} (Under Maintenance) - Reassignable]`;
                option.style.color = "#8a6d00";
                option.style.fontWeight = "700";
                availableCount += 1;
            } else {
                option.textContent = `👤 ${driver.name} [Assigned to ${assignedVehicle.model_name} (${assignedVehicle.status})]`;
                option.disabled = true;
                option.style.color = "#8a6d00";
                option.style.fontWeight = "700";
            }

            driverSelect.appendChild(option);
        });

        if (availableCount === 0) {
            driverSelect.options[0].textContent = "No eligible personnel available — manage driver records";
        }
    });
})();
