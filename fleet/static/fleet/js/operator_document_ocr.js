document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("#addOperatorModal form");
    const formBody = document.getElementById("operatorRegistrationForm");
    const entries = document.getElementById("operatorRegistrationEntries");
    const operatorCount = document.getElementById("operatorCount");
    const addEntryButton = document.getElementById("addOperatorEntry");
    const bulkLicenseInput = document.querySelector("[data-bulk-operator-licenses]");
    const bulkLicenseStatus = document.querySelector("[data-bulk-license-status]");
    if (!form || !formBody || !entries || !operatorCount || !addEntryButton
        || !bulkLicenseInput || !bulkLicenseStatus) return;

    function setBulkStatus(message, isError = false) {
        bulkLicenseStatus.textContent = message;
        bulkLicenseStatus.classList.toggle("text-danger", isError);
        bulkLicenseStatus.classList.toggle("text-success", !isError && Boolean(message));
    }

    function setStatus(entry, message, isError = false) {
        const status = entry.querySelector("[data-operator-ocr-status]");
        status.textContent = message;
        status.classList.toggle("text-danger", isError);
        status.classList.toggle("text-success", !isError && Boolean(message));
    }

    function updateOperatorEntry(entry) {
        const operatorType = entry.querySelector("[name$='-operator_type']");
        const type = operatorType.value;
        entry.querySelector("[data-operator-document-label]").textContent = type === "SEA"
            ? "MARINA license / certificate image(s)"
            : "LTO driver's license image(s)";
        entry.querySelector("[data-license-class-label]").textContent =
            type === "SEA" ? "Seafarer rank" : "DL Codes";
        entry.querySelectorAll("[data-lto-license-field]").forEach((field) => {
            field.hidden = type === "SEA";
        });
        const authorityHint = entry.querySelector("[data-operator-authority-hint]");
        authorityHint.textContent = type === "SEA"
            ? "Seacraft operator license authority: MARINA (automatic)."
            : "Land vehicle driver license authority: LTO (automatic).";
    }

    function renumberEntries() {
        const operatorEntries = entries.querySelectorAll("[data-operator-entry]");
        operatorEntries.forEach((entry, index) => {
            entry.querySelectorAll("[name], [id], label[for]").forEach((element) => {
                ["name", "id", "for"].forEach((attribute) => {
                    const value = element.getAttribute(attribute);
                    if (value) {
                        element.setAttribute(attribute, value.replace(/operator-\d+/, `operator-${index}`));
                    }
                });
            });
            entry.querySelector("[data-operator-entry-title]").textContent =
                `Driver / Operator ${index + 1}`;
            entry.querySelector("[data-remove-operator]").hidden = operatorEntries.length === 1;
            updateOperatorEntry(entry);
        });
        operatorCount.value = operatorEntries.length;
        addEntryButton.disabled = operatorEntries.length >= 20;
    }

    function isBlankEntry(entry) {
        const hasEnteredValue = Array.from(entry.querySelectorAll("input, select, textarea"))
            .some((field) => {
                if (field.type === "file" || field.type === "hidden") return false;
                if (field.matches("[name$='-operator_type']")) return field.value !== "LAND";
                return Boolean(field.value.trim());
            });
        const hasSelectedFiles = Array.from(entry.querySelectorAll("input[type='file']"))
            .some((field) => field.files.length > 0);
        return !hasEnteredValue && !hasSelectedFiles;
    }

    function createOperatorEntry() {
        const operatorEntries = entries.querySelectorAll("[data-operator-entry]");
        const clone = operatorEntries[operatorEntries.length - 1].cloneNode(true);
        clone.querySelectorAll("input, select, textarea").forEach((field) => {
            if (field.type === "checkbox" || field.type === "radio") {
                field.checked = false;
            } else {
                field.value = "";
            }
        });
        clone.querySelector("[name$='-operator_type']").value = "LAND";
        clone.querySelector("[data-license-scan-complete]").value = "false";
        delete clone.dataset.ocrRequestId;
        delete clone.dataset.ocrInProgress;
        delete clone.dataset.replaceLicenseFieldsOnScan;
        setStatus(clone, "");
        entries.appendChild(clone);
        renumberEntries();
        return clone;
    }

    async function readOperatorDocument(entry, input) {
        const files = Array.from(input.files || []);
        if (!files.length) return;
        const scanComplete = entry.querySelector("[data-license-scan-complete]");
        scanComplete.value = "false";
        if (files.length > 5) {
            input.value = "";
            setStatus(entry, "Select no more than five document images.", true);
            return;
        }

        const operatorType = entry.querySelector("[name$='-operator_type']");
        if (!operatorType.value) {
            input.value = "";
            setStatus(entry, "Choose the operator type before scanning the document.", true);
            return;
        }

        const requestId = String(Number(entry.dataset.ocrRequestId || 0) + 1);
        entry.dataset.ocrRequestId = requestId;
        entry.dataset.ocrInProgress = "true";
        const body = new FormData();
        body.append("operator_type", operatorType.value);
        files.forEach((file) => body.append("documents", file));
        setStatus(entry, "Reading the document locally on this server…");

        try {
            const response = await fetch(formBody.dataset.ocrUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": form.querySelector("[name='csrfmiddlewaretoken']").value,
                },
                body,
                credentials: "same-origin",
            });
            const result = await response.json();
            if (entry.dataset.ocrRequestId !== requestId) return;
            if (!response.ok) {
                throw new Error(result.error || "Could not read the document.");
            }
            scanComplete.value = "true";

            const fields = result.fields || {};
            const suggestions = Object.entries(fields).filter(([, value]) => value);
            const replaceLicenseFields = entry.dataset.replaceLicenseFieldsOnScan === "true";
            let filledCount = 0;
            [
                "name",
                "license_number",
                "license_class",
                "license_type",
                "license_restrictions",
                "emergency_contact_name",
                "emergency_contact_number",
                "license_expiry",
            ].forEach((name) => {
                const field = entry.querySelector(`[name$='-${name}']`);
                const replaceValue = replaceLicenseFields
                    && name !== "name";
                if (!field || !fields[name] || (field.value && !replaceValue)) return;
                field.value = fields[name];
                field.dispatchEvent(new Event("input", { bubbles: true }));
                field.dispatchEvent(new Event("change", { bubbles: true }));
                filledCount += 1;
            });

            let message = result.message;
            if (filledCount) {
                message = `${filledCount} suggested field(s) filled. Review them before saving. The first selected image will be stored with this operator record.`;
            } else if (suggestions.length) {
                message = "License details were recognized, but existing values were kept. Clear a field to use its suggestion.";
            }
            setStatus(entry, message);
            return true;
        } catch (error) {
            if (entry.dataset.ocrRequestId === requestId) {
                setStatus(entry, error.message, true);
            }
            return false;
        } finally {
            if (entry.dataset.ocrRequestId === requestId) {
                delete entry.dataset.ocrInProgress;
            }
        }
    }

    entries.addEventListener("change", (event) => {
        const entry = event.target.closest("[data-operator-entry]");
        if (!entry) return;
        if (event.target.matches("[name$='-operator_type']")) {
            updateOperatorEntry(entry);
        } else if (event.target.matches("[data-operator-documents]")) {
            readOperatorDocument(entry, event.target);
        }
    });

    entries.addEventListener("click", (event) => {
        const entry = event.target.closest("[data-operator-entry]");
        if (!entry) return;
        if (event.target.closest("[data-operator-document-action]")) {
            const button = event.target.closest("[data-operator-document-action]");
            const input = entry.querySelector("[data-operator-documents]");
            if (button.dataset.operatorDocumentAction === "camera") {
                input.setAttribute("capture", "environment");
            } else {
                input.removeAttribute("capture");
            }
            input.click();
        } else if (event.target.closest("[data-remove-operator]")) {
            entry.remove();
            renumberEntries();
        }
    });

    addEntryButton.addEventListener("click", () => {
        const operatorEntries = entries.querySelectorAll("[data-operator-entry]");
        if (operatorEntries.length >= 20) return;
        createOperatorEntry();
    });

    bulkLicenseInput.addEventListener("change", async () => {
        const files = Array.from(bulkLicenseInput.files || []);
        if (!files.length) return;
        const operatorEntries = Array.from(entries.querySelectorAll("[data-operator-entry]"));
        const blankEntries = operatorEntries.filter(isBlankEntry);
        const availableSlots = 20 - operatorEntries.length + blankEntries.length;
        if (files.length > availableSlots) {
            bulkLicenseInput.value = "";
            setBulkStatus(`You can add ${availableSlots} more driver license(s); remove an entry or upload fewer files.`, true);
            return;
        }

        bulkLicenseInput.disabled = true;
        addEntryButton.disabled = true;
        let nextBlankEntry = blankEntries.shift();
        let failedScans = 0;
        try {
            for (const [index, file] of files.entries()) {
                const entry = nextBlankEntry || createOperatorEntry();
                nextBlankEntry = null;
                const input = entry.querySelector("[data-operator-documents]");
                const transfer = new DataTransfer();
                transfer.items.add(file);
                input.files = transfer.files;
                setBulkStatus(`Scanning license ${index + 1} of ${files.length}…`);
                if (!await readOperatorDocument(entry, input)) failedScans += 1;
            }
            setBulkStatus(
                failedScans
                    ? `${files.length} driver entry/entries added; ${failedScans} scan(s) failed. Review each entry and rescan failed licenses before saving.`
                    : `${files.length} driver license image(s) added as separate entries. Review each entry before saving.`,
                failedScans > 0,
            );
        } catch (error) {
            setBulkStatus(error instanceof Error ? error.message : "Could not add the selected licenses.", true);
        } finally {
            bulkLicenseInput.value = "";
            bulkLicenseInput.disabled = false;
            renumberEntries();
        }
    });

    form.addEventListener("submit", (event) => {
        const pendingEntry = Array.from(entries.querySelectorAll("[data-operator-entry]"))
            .find((entry) => entry.dataset.ocrInProgress === "true");
        if (!pendingEntry) return;
        event.preventDefault();
        setStatus(pendingEntry, "Wait for document scanning to finish before saving.", true);
    });

    form.addEventListener("reset", () => {
        window.setTimeout(renumberEntries, 0);
    });

    renumberEntries();
});
