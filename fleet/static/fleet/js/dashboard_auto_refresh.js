(() => {
    const formSelector = "form[data-logistics-ajax-form]";
    const contentSelector = "[data-dashboard-refresh-content]";
    const textSelector = "[data-dashboard-refresh-text]";
    let activeRequest = false;

    function findByDataKey(root, selector, attribute, key) {
        return Array.from(root.querySelectorAll(selector))
            .find((element) => element.getAttribute(attribute) === key);
    }

    function refreshDashboardData(responseDocument, excludedContentKeys = []) {
        const currentRoot = document.querySelector("[data-logistics-dashboard]");
        const responseRoot = responseDocument.querySelector("[data-logistics-dashboard]");
        if (!currentRoot || !responseRoot) {
            throw new Error("The dashboard response was incomplete. Refresh the page and try again.");
        }

        const excludedKeys = new Set(excludedContentKeys);
        const contentUpdates = Array.from(document.querySelectorAll(contentSelector))
            .filter((current) => !excludedKeys.has(current.dataset.dashboardRefreshContent))
            .map((current) => {
                const key = current.dataset.dashboardRefreshContent;
                const incoming = findByDataKey(
                    responseDocument,
                    contentSelector,
                    "data-dashboard-refresh-content",
                    key,
                );
                if (!incoming) {
                    throw new Error(`Updated dashboard section "${key}" was missing from the response.`);
                }
                return { current, incoming };
            });

        const textUpdates = Array.from(document.querySelectorAll(textSelector)).map((current) => {
            const key = current.dataset.dashboardRefreshText;
            const incoming = findByDataKey(
                responseDocument,
                textSelector,
                "data-dashboard-refresh-text",
                key,
            );
            if (!incoming) {
                throw new Error(`Updated dashboard data "${key}" was missing from the response.`);
            }
            if (current instanceof HTMLScriptElement && current.type === "application/json") {
                JSON.parse(incoming.textContent || "null");
            }
            return { current, incoming };
        });

        const activeTabs = new Map();
        contentUpdates.forEach(({ current }) => {
            const group = current.dataset.dashboardRefreshTabGroup;
            if (!group) return;
            const activeTab = document.querySelector(`#${group} .nav-link.active`);
            if (activeTab) activeTabs.set(group, activeTab.id);
        });

        contentUpdates.forEach(({ current, incoming }) => {
            current.innerHTML = incoming.innerHTML;
        });
        textUpdates.forEach(({ current, incoming }) => {
            current.textContent = incoming.textContent;
        });

        activeTabs.forEach((tabId, groupId) => {
            const trigger = document.getElementById(tabId);
            if (trigger && window.bootstrap?.Tab) {
                window.bootstrap.Tab.getOrCreateInstance(trigger).show();
            }
        });
    }

    function showRequestError(message) {
        const container = document.getElementById("floating-alert-container");
        if (!container) {
            console.error(message);
            return;
        }
        const alert = document.createElement("div");
        alert.className = "alert alert-danger alert-dismissible fade show shadow-lg";
        alert.setAttribute("role", "alert");
        alert.append(document.createTextNode(message));
        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "btn-close";
        closeButton.setAttribute("data-bs-dismiss", "alert");
        closeButton.setAttribute("aria-label", "Close");
        alert.append(closeButton);
        container.replaceChildren(alert);
    }

    window.refreshLogisticsDashboardData = async (excludedContentKeys = []) => {
        try {
            const response = await fetch(window.location.href, {
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    "Accept": "text/html",
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            const responseText = await response.text();
            if (!response.ok) {
                throw new Error(`Dashboard data could not be refreshed (HTTP ${response.status}).`);
            }
            const responseDocument = new DOMParser().parseFromString(responseText, "text/html");
            refreshDashboardData(responseDocument, excludedContentKeys);
            return true;
        } catch (error) {
            console.error("Logistics dashboard data refresh failed.", error);
            showRequestError(error instanceof Error ? error.message : "Dashboard data could not be refreshed.");
            return false;
        }
    };

    document.addEventListener("submit", async (event) => {
        const form = event.target;
        if (
            event.defaultPrevented
            || !(form instanceof HTMLFormElement)
            || !form.matches(formSelector)
        ) {
            return;
        }

        event.preventDefault();
        if (activeRequest) {
            showRequestError("Another dashboard update is still saving. Please retry in a moment.");
            return;
        }

        const formData = new FormData(form);
        const csrfToken = formData.get("csrfmiddlewaretoken");
        const submitButtons = Array.from(form.querySelectorAll(
            'button[type="submit"], input[type="submit"]',
        ));
        const previousDisabledState = submitButtons.map((button) => button.disabled);
        activeRequest = true;
        submitButtons.forEach((button) => {
            button.disabled = true;
        });
        form.setAttribute("aria-busy", "true");

        try {
            const response = await fetch(form.action || window.location.href, {
                method: form.method || "POST",
                body: formData,
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    "Accept": "text/html",
                    "X-Requested-With": "XMLHttpRequest",
                    ...(csrfToken ? { "X-CSRFToken": csrfToken } : {}),
                },
            });
            const responseText = await response.text();
            if (!response.ok) {
                throw new Error(`The update failed (HTTP ${response.status}). Please try again.`);
            }
            if (response.redirected && new URL(response.url).origin !== window.location.origin) {
                throw new Error("Your session may have expired. Sign in again, then retry the update.");
            }

            const responseDocument = new DOMParser().parseFromString(responseText, "text/html");
            refreshDashboardData(responseDocument);

            const successMessage = responseDocument.querySelector(
                '#floating-alert-container [data-message-tags~="success"]',
            );
            if (successMessage) {
                const modal = form.closest(".modal");
                if (modal && window.bootstrap?.Modal) {
                    window.bootstrap.Modal.getOrCreateInstance(modal).hide();
                }
            }
        } catch (error) {
            console.error("Logistics dashboard data update failed.", error);
            showRequestError(error instanceof Error ? error.message : "The update failed. Please try again.");
        } finally {
            activeRequest = false;
            form.removeAttribute("aria-busy");
            submitButtons.forEach((button, index) => {
                button.disabled = previousDisabledState[index];
            });
        }
    });
})();