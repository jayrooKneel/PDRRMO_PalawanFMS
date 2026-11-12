document.addEventListener("DOMContentLoaded", () => {
    const formBody = document.getElementById("operatorRegistrationForm");
    if (!formBody) return;

    const operatorType = formBody.querySelector("[name='operator_type']");
    const documentInput = formBody.querySelector("[data-operator-documents]");
    const documentLabel = formBody.querySelector("[data-operator-document-label]");

    formBody.querySelectorAll("[data-operator-document-action]").forEach((button) => {
        button.addEventListener("click", () => {
            if (button.dataset.operatorDocumentAction === "camera") {
                documentInput.setAttribute("capture", "environment");
            } else {
                documentInput.removeAttribute("capture");
            }
            documentInput.click();
        });
    });

    function setStatus(message, isError = false) {
        const status = formBody.querySelector("[data-operator-ocr-status]");
        status.textContent = message;
        status.classList.toggle("text-danger", isError);
        status.classList.toggle("text-success", !isError && Boolean(message));
    }

    function updateDocumentLabel() {
        documentLabel.textContent = operatorType.value === "SEA"
            ? "MARINA license / certificate image(s)"
            : "LTO driver's license image(s)";
    }

    operatorType.addEventListener("change", updateDocumentLabel);
    updateDocumentLabel();

    documentInput.addEventListener("change", async () => {
        const files = Array.from(documentInput.files || []);
        if (!files.length) return;
        if (files.length > 5) {
            documentInput.value = "";
            setStatus("Select no more than five document images.", true);
            return;
        }
        if (!operatorType.value) {
            documentInput.value = "";
            setStatus("Choose the operator type before scanning the document.", true);
            return;
        }

        const requestId = String(Number(formBody.dataset.ocrRequestId || 0) + 1);
        formBody.dataset.ocrRequestId = requestId;
        formBody.dataset.ocrInProgress = "true";
        const form = formBody.closest("form");
        const body = new FormData();
        body.append("operator_type", operatorType.value);
        files.forEach((file) => body.append("documents", file));
        setStatus("Reading the document locally on this server…");

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
            if (formBody.dataset.ocrRequestId !== requestId) return;
            if (!response.ok) {
                throw new Error(result.error || "Could not read the document.");
            }

            const fields = result.fields || {};
            const suggestions = Object.entries(fields).filter(([, value]) => value);
            let filledCount = 0;
            ["name", "license_number", "license_class", "license_expiry"].forEach((name) => {
                const field = formBody.querySelector(`[name='${name}']`);
                if (!field || !fields[name] || field.value) return;
                field.value = fields[name];
                field.dispatchEvent(new Event("input", { bubbles: true }));
                field.dispatchEvent(new Event("change", { bubbles: true }));
                filledCount += 1;
            });

            let message = result.message;
            if (filledCount) {
                message = `${filledCount} suggested field(s) filled. Review them before saving. The uploaded image was discarded.`;
            } else if (suggestions.length) {
                message = "License details were recognized, but existing values were kept. Clear a field to use its suggestion.";
            }
            setStatus(message);
        } catch (error) {
            if (formBody.dataset.ocrRequestId === requestId) {
                setStatus(error.message, true);
            }
        } finally {
            if (formBody.dataset.ocrRequestId === requestId) {
                documentInput.value = "";
                delete formBody.dataset.ocrInProgress;
            }
        }
    });

    formBody.closest("form").addEventListener("submit", (event) => {
        if (formBody.dataset.ocrInProgress !== "true") return;
        event.preventDefault();
        setStatus("Wait for document scanning to finish before saving.", true);
    });
});
