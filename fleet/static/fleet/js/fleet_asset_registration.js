document.addEventListener("DOMContentLoaded", function () {
    const assetEntries = document.getElementById("assetRegistrationEntries");
    const assetCount = document.getElementById("assetCount");
    if (!assetEntries || !assetCount) return;

    const makes = {
        land: ["Ford", "Honda", "Hyundai", "Isuzu", "Kia", "Mitsubishi", "Nissan", "Suzuki", "Toyota"],
        sea: ["Honda Marine", "Kawasaki", "Mercury", "Sea-Doo", "Suzuki Marine", "Yamaha Marine"],
    };

    function updateAssetEntry(entry) {
        const typeSelect = entry.querySelector("[data-vehicle-type]");
        const selectedType = typeSelect.options[typeSelect.selectedIndex]?.text.trim().toLowerCase();
        const seaAsset = ["marine", "maritime"].includes(selectedType);
        const identifierLabel = entry.querySelector("[data-identifier-label]");
        identifierLabel.textContent = seaAsset ? "Official number / hull ID" : "Plate / registration number";

        entry.querySelectorAll("[data-asset-fields]").forEach((group) => {
            const active = group.dataset.assetFields === (seaAsset ? "sea" : "land");
            group.hidden = !active;
            group.querySelectorAll("input, select, textarea").forEach((field) => {
                field.disabled = !active;
            });
        });

        const makeInput = entry.querySelector("[data-make-input]");
        const makeList = entry.querySelector("datalist");
        if (makeInput && makeList) {
            makeList.replaceChildren(...(seaAsset ? makes.sea : makes.land).map((make) => {
                const option = document.createElement("option");
                option.value = make;
                return option;
            }));
        }

        const documentInput = entry.querySelector("[data-registration-documents]");
        documentInput.dataset.ocrReady = String(Boolean(typeSelect.value));
    }

    function setOcrStatus(entry, text, isError) {
        const status = entry.querySelector("[data-ocr-status]");
        status.textContent = text;
        status.classList.toggle("text-danger", Boolean(isError));
        status.classList.toggle("text-success", !isError && Boolean(text));
    }

    async function readRegistrationDocuments(entry, input) {
        const requestId = String(Number(entry.dataset.ocrRequestId || 0) + 1);
        entry.dataset.ocrRequestId = requestId;
        delete entry.dataset.ocrInProgress;
        const files = Array.from(input.files || []);
        if (!files.length) return;
        if (files.length > 5) {
            input.value = "";
            setOcrStatus(entry, "Select no more than five OR/CR images.", true);
            return;
        }

        const vehicleType = entry.querySelector("[data-vehicle-type]");
        if (!vehicleType.value) {
            input.value = "";
            setOcrStatus(entry, "Choose the vehicle or vessel type before uploading OR/CR images.", true);
            return;
        }

        const form = entry.closest("form");
        const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]').value;
        const body = new FormData();
        body.append("vehicle_type", vehicleType.value);
        files.forEach((file) => body.append("documents", file));
        entry.dataset.ocrInProgress = "true";
        setOcrStatus(entry, "Reading OR/CR locally on this server…", false);

        try {
            const response = await fetch(entry.dataset.ocrUrl, {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken },
                body,
                credentials: "same-origin",
            });
            const result = await response.json();
            if (entry.dataset.ocrRequestId !== requestId) return;
            if (!response.ok) {
                throw new Error(result.error || "Could not read the uploaded OR/CR.");
            }

            const suggestions = Object.entries(result.fields || {}).filter(([, value]) => value);
            let filledCount = 0;
            suggestions.forEach(([name, value]) => {
                const matchingFields = Array.from(entry.querySelectorAll("[data-ocr-field]"))
                    .filter((candidate) => candidate.dataset.ocrField === name);
                const field = matchingFields.find((candidate) => !candidate.disabled);
                if (!field || field.value) return;
                field.value = value;
                field.dispatchEvent(new Event("input", { bubbles: true }));
                field.dispatchEvent(new Event("change", { bubbles: true }));
                filledCount += 1;
            });

            let status = result.message;
            if (filledCount) {
                status = `${filledCount} suggested field(s) filled. Check and correct them before saving.`;
            } else if (suggestions.length) {
                status = "Details were recognized, but existing values were kept. Clear a field to use its suggestion.";
            }
            setOcrStatus(entry, status, false);
        } catch (error) {
            if (entry.dataset.ocrRequestId === requestId) {
                setOcrStatus(entry, error.message, true);
            }
        } finally {
            if (entry.dataset.ocrRequestId === requestId) {
                delete entry.dataset.ocrInProgress;
            }
        }
    }

    function renumberEntries() {
        const entries = assetEntries.querySelectorAll("[data-asset-entry]");
        entries.forEach((entry, index) => {
            entry.querySelectorAll("[name], [id], label[for], [list]").forEach((element) => {
                ["name", "id", "for", "list"].forEach((attribute) => {
                    const value = element.getAttribute(attribute);
                    if (value) {
                        element.setAttribute(attribute, value.replace(/asset-\d+/, "asset-" + index));
                    }
                });
            });
            entry.querySelector("[data-entry-title]").textContent = "Asset " + (index + 1);
            entry.querySelector("[data-remove-asset]").hidden = entries.length === 1;
            updateAssetEntry(entry);
        });
        assetCount.value = entries.length;
    }

    assetEntries.addEventListener("change", (event) => {
        if (event.target.matches("[data-vehicle-type]")) {
            updateAssetEntry(event.target.closest("[data-asset-entry]"));
        } else if (event.target.matches("[data-registration-documents]")) {
            readRegistrationDocuments(event.target.closest("[data-asset-entry]"), event.target);
        }
    });

    document.getElementById("addAssetEntry").addEventListener("click", () => {
        const entries = assetEntries.querySelectorAll("[data-asset-entry]");
        if (entries.length >= 20) return;
        const clone = entries[entries.length - 1].cloneNode(true);
        clone.querySelectorAll("input, select, textarea").forEach((field) => {
            if (field.type === "checkbox" || field.type === "radio") {
                field.checked = false;
            } else {
                field.value = "";
            }
        });
        setOcrStatus(clone, "", false);
        assetEntries.appendChild(clone);
        renumberEntries();
    });

    assetEntries.addEventListener("click", (event) => {
        const removeButton = event.target.closest("[data-remove-asset]");
        if (removeButton) {
            removeButton.closest("[data-asset-entry]").remove();
            renumberEntries();
        }
    });

    assetEntries.closest("form").addEventListener("submit", (event) => {
        const pendingEntry = Array.from(assetEntries.querySelectorAll("[data-asset-entry]"))
            .find((entry) => entry.dataset.ocrInProgress === "true");
        if (pendingEntry) {
            event.preventDefault();
            setOcrStatus(pendingEntry, "Wait for local OCR to finish before registering.", true);
        }
    });

    renumberEntries();
});
