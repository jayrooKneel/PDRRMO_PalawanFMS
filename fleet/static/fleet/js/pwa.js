(() => {
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/service-worker.js").catch((error) => {
                console.error("PDRRMO app service worker registration failed.", error);
            });
        });
    }

    let installPrompt;
    let installButton;

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        installPrompt = event;

        if (!installButton) {
            installButton = document.createElement("button");
            installButton.className = "pwa-install-button";
            installButton.type = "button";
            installButton.textContent = "Install app";
            installButton.addEventListener("click", async () => {
                if (!installPrompt) return;
                await installPrompt.prompt();
                installPrompt = null;
                installButton.remove();
                installButton = null;
            });
            document.body.append(installButton);
        }
    });

    window.addEventListener("appinstalled", () => {
        installButton?.remove();
        installButton = null;
        installPrompt = null;
    });
})();
