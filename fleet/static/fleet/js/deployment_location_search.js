document.addEventListener("DOMContentLoaded", function () {
    const inputs = document.querySelectorAll("input[data-locations-url]");

    inputs.forEach(function (input, inputIndex) {
        const suggestionsId = input.getAttribute("aria-controls");
        let suggestions = suggestionsId
            ? document.getElementById(suggestionsId)
            : null;

        if (!suggestions) {
            suggestions = document.createElement("div");
            suggestions.id = "location-suggestions-" + inputIndex;
            suggestions.className =
                "list-group position-absolute top-100 start-0 w-100 shadow d-none";
            suggestions.setAttribute("role", "listbox");
            suggestions.style.position = "absolute";
            suggestions.style.top = "100%";
            suggestions.style.left = "0";
            suggestions.style.width = "100%";
            suggestions.style.zIndex = "1060";
            suggestions.style.backgroundColor = "#fff";
            suggestions.style.border = "1px solid #ced4da";
            suggestions.style.borderRadius = "0.375rem";
            suggestions.style.boxShadow = "0 0.5rem 1rem rgba(0, 0, 0, 0.15)";
            suggestions.style.maxHeight = "16rem";
            suggestions.style.overflowY = "auto";
            suggestions.style.display = "none";
            suggestions.dataset.locationSearchGenerated = "true";

            const wrapper = document.createElement("div");
            wrapper.className = "position-relative";
            wrapper.style.position = "relative";
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);
            wrapper.appendChild(suggestions);
            input.setAttribute("aria-controls", suggestions.id);
        }

        input.setAttribute("aria-expanded", "false");

        const form = input.closest("form");
        const requiresListedLocation =
            input.dataset.locationRestricted === "true";
        let locations = [];
        let locationsLoaded = false;
        let matchingLocations = [];
        let activeIndex = -1;

        function hideSuggestions() {
            suggestions.replaceChildren();
            suggestions.classList.add("d-none");
            if (suggestions.dataset.locationSearchGenerated === "true") {
                suggestions.style.display = "none";
            }
            input.setAttribute("aria-expanded", "false");
            input.removeAttribute("aria-activedescendant");
            activeIndex = -1;
        }

        function selectLocation(location) {
            input.value = location.label;
            input.setCustomValidity("");
            hideSuggestions();
        }

        function updateActiveOption() {
            const options = suggestions.querySelectorAll("[role='option']");
            options.forEach(function (option, index) {
                const isActive = index === activeIndex;
                option.setAttribute("aria-selected", String(isActive));
                option.classList.toggle("active", isActive);
            });
            if (activeIndex >= 0 && options[activeIndex]) {
                input.setAttribute("aria-activedescendant", options[activeIndex].id);
                options[activeIndex].scrollIntoView({ block: "nearest" });
            } else {
                input.removeAttribute("aria-activedescendant");
            }
        }

        function showSuggestions() {
            const query = input.value.trim().toLocaleLowerCase();
            matchingLocations = query
                ? locations.filter(function (location) {
                    return location.label.toLocaleLowerCase().includes(query);
                }).slice(0, 12)
                : [];
            suggestions.replaceChildren();
            activeIndex = -1;

            matchingLocations.forEach(function (location, index) {
                const option = document.createElement("button");
                option.type = "button";
                option.id = suggestions.id + "-option-" + index;
                option.className = "list-group-item list-group-item-action text-start";
                option.setAttribute("role", "option");
                option.setAttribute("aria-selected", "false");
                option.textContent = location.label;
                option.style.display = "block";
                option.style.width = "100%";
                option.style.padding = "0.5rem 0.75rem";
                option.style.border = "0";
                option.style.borderBottom = "1px solid #dee2e6";
                option.style.backgroundColor = "#fff";
                option.style.color = "#212529";
                option.style.textAlign = "left";
                option.style.cursor = "pointer";
                option.addEventListener("mouseenter", function () {
                    option.style.backgroundColor = "#e9ecef";
                });
                option.addEventListener("mouseleave", function () {
                    option.style.backgroundColor = "#fff";
                });
                option.addEventListener("mousedown", function (event) {
                    event.preventDefault();
                    selectLocation(location);
                });
                suggestions.appendChild(option);
            });

            if (query && matchingLocations.length === 0) {
                const message = document.createElement("div");
                message.className = "list-group-item small text-muted";
                message.textContent =
                    "No Puerto Princesa or Palawan barangays found.";
                suggestions.appendChild(message);
            }

            suggestions.classList.toggle("d-none", !query);
            if (suggestions.dataset.locationSearchGenerated === "true") {
                suggestions.style.display = query ? "block" : "none";
            }
            input.setAttribute("aria-expanded", String(Boolean(query)));
        }

        input.addEventListener("input", function () {
            input.setCustomValidity("");
            showSuggestions();
        });

        input.addEventListener("keydown", function (event) {
            if (event.key === "ArrowDown" && matchingLocations.length) {
                event.preventDefault();
                activeIndex = (activeIndex + 1) % matchingLocations.length;
                updateActiveOption();
            } else if (event.key === "ArrowUp" && matchingLocations.length) {
                event.preventDefault();
                activeIndex = activeIndex <= 0
                    ? matchingLocations.length - 1
                    : activeIndex - 1;
                updateActiveOption();
            } else if (event.key === "Enter" && activeIndex >= 0) {
                event.preventDefault();
                selectLocation(matchingLocations[activeIndex]);
            } else if (event.key === "Escape") {
                hideSuggestions();
            }
        });

        input.addEventListener("blur", function () {
            window.setTimeout(hideSuggestions, 100);
        });

        if (form) {
            form.addEventListener("submit", function (event) {
                const validListedLocation = locations.some(function (location) {
                    return location.label === input.value.trim();
                });
                if (!locationsLoaded) {
                    input.setCustomValidity(
                        "Location suggestions could not be loaded. Refresh and try again."
                    );
                    input.reportValidity();
                    event.preventDefault();
                } else if (requiresListedLocation && !validListedLocation) {
                    input.setCustomValidity(
                        "Choose a location from Puerto Princesa City or the Palawan barangay suggestions."
                    );
                    input.reportValidity();
                    event.preventDefault();
                } else {
                    input.setCustomValidity("");
                }
            });
        }

        fetch(input.dataset.locationsUrl)
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Unable to load deployment locations.");
                }
                return response.json();
            })
            .then(function (data) {
                if (!data || !Array.isArray(data.locations)) {
                    throw new Error("Deployment location data is malformed.");
                }
                locations = data.locations;
                locationsLoaded = true;
                if (input.value.trim()) {
                    showSuggestions();
                }
            })
            .catch(function (error) {
                console.error(error);
                input.setCustomValidity(
                    "Location suggestions could not be loaded. Refresh and try again."
                );
            });
    });
});
