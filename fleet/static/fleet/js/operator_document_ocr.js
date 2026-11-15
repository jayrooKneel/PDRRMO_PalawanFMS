document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("#addOperatorModal form");
    const formBody = document.getElementById("operatorRegistrationForm");
    const entries = document.getElementById("operatorRegistrationEntries");
    const operatorCount = document.getElementById("operatorCount");
    const addEntryButton = document.getElementById("addOperatorEntry");
    if (!form || !formBody || !entries || !operatorCount || !addEntryButton) return;

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
                message = `${filledCount} suggested field(s) filled. Review them before saving. All selected images will be stored with this operator record.`;
            } else if (suggestions.length) {
                message = "License details were recognized, but existing values were kept. Clear a field to use its suggestion.";
            }
            setStatus(entry, message);
        } catch (error) {
            if (entry.dataset.ocrRequestId === requestId) {
                setStatus(entry, error.message, true);
            }
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
