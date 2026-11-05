document.addEventListener("DOMContentLoaded", function () {
    const input = document.getElementById("deployment_location_input");
    const suggestions = document.getElementById("deployment-location-suggestions");
    if (!input || !suggestions) return;

    const form = input.closest("form");
    let locations = [];
    let matchingLocations = [];
    let activeIndex = -1;

    function hideSuggestions() {
        suggestions.replaceChildren();
        suggestions.classList.add("d-none");
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
            option.id = "deployment-location-option-" + index;
            option.className = "list-group-item list-group-item-action text-start";
            option.setAttribute("role", "option");
            option.setAttribute("aria-selected", "false");
            option.textContent = location.label;
            option.addEventListener("mousedown", function (event) {
                event.preventDefault();
                selectLocation(location);
            });
            suggestions.appendChild(option);
        });

        const noResults = query && matchingLocations.length === 0;
        if (noResults) {
            const message = document.createElement("div");
            message.className = "list-group-item small text-muted";
            message.textContent = "No Puerto Princesa or Palawan barangays found.";
            suggestions.appendChild(message);
        }

        suggestions.classList.toggle("d-none", !query);
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
            activeIndex = activeIndex <= 0 ? matchingLocations.length - 1 : activeIndex - 1;
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
            const validLocation = locations.some(function (location) {
                return location.label === input.value.trim();
            });
            if (!validLocation) {
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
            if (!response.ok) throw new Error("Unable to load deployment locations.");
            return response.json();
        })
        .then(function (data) {
            locations = data.locations || [];
        })
        .catch(function (error) {
            console.error(error);
            input.setCustomValidity("Deployment locations could not be loaded. Refresh and try again.");
        });
});
