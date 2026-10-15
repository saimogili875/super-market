/**
 * Delivery Location Geolocation & Form Gate
 *
 * Uses free HTML5 Geolocation API (navigator.geolocation) to populate hidden lat/lng inputs.
 * Enforces client-side rule: submit is disabled until lat+lng OR street address is provided.
 * CSP-Safe: pure event listeners, no inline script, no eval().
 */
(function() {
    "use strict";

    document.addEventListener("DOMContentLoaded", function() {
        const btnGeolocate = document.getElementById("btn-geolocate");
        const latInput = document.getElementById("lat");
        const lngInput = document.getElementById("lng");
        const addressInput = document.getElementById("address");
        const statusDiv = document.getElementById("location-status");
        const previewDiv = document.getElementById("location-preview");
        const submitBtn = document.getElementById("btn-submit-order");
        const submitError = document.getElementById("submit-error");
        const checkoutForm = document.querySelector("form[action*='checkout']");

        if (!latInput || !lngInput || !addressInput) {
            return;
        }

        function hasValidCoords() {
            return latInput.value.trim() !== "" && lngInput.value.trim() !== "";
        }

        function hasAddress() {
            return addressInput.value.trim() !== "";
        }

        function updateFormState() {
            const isValid = hasValidCoords() || hasAddress();
            if (submitBtn) {
                submitBtn.disabled = !isValid;
            }
            if (submitError) {
                submitError.style.display = isValid ? "none" : "block";
            }
        }

        // Initialize state on load
        if (hasValidCoords() && statusDiv) {
            statusDiv.textContent = "Location captured ✓";
            statusDiv.style.color = "var(--color-success)";
            if (previewDiv) {
                const mapsUrl = "https://www.google.com/maps/dir/?api=1&destination=" + encodeURIComponent(latInput.value.trim()) + "," + encodeURIComponent(lngInput.value.trim());
                previewDiv.innerHTML = '<a href="' + mapsUrl + '" target="_blank" rel="noopener noreferrer" style="color: var(--color-primary); text-decoration: underline;">Preview in Google Maps</a>';
                previewDiv.style.display = "block";
            }
        } else if (hasAddress() && statusDiv) {
            statusDiv.textContent = "Address entered ✓";
            statusDiv.style.color = "var(--color-success)";
        }
        updateFormState();

        // Listen for address typing
        addressInput.addEventListener("input", function() {
            if (hasAddress()) {
                if (!hasValidCoords() && statusDiv) {
                    statusDiv.textContent = "Address entered ✓";
                    statusDiv.style.color = "var(--color-success)";
                }
            } else if (!hasValidCoords() && statusDiv) {
                statusDiv.textContent = "Location needed — share location or enter address";
                statusDiv.style.color = "var(--text-secondary)";
                if (previewDiv) previewDiv.style.display = "none";
            }
            updateFormState();
        });

        // Geolocation button click
        if (btnGeolocate) {
            btnGeolocate.addEventListener("click", function() {
                if (!navigator.geolocation) {
                    if (statusDiv) {
                        statusDiv.textContent = "Geolocation is not supported by your browser — please enter your address";
                        statusDiv.style.color = "var(--color-danger)";
                    }
                    updateFormState();
                    return;
                }

                if (statusDiv) {
                    statusDiv.textContent = "Locating... ⏳";
                    statusDiv.style.color = "var(--text-secondary)";
                }
                btnGeolocate.disabled = true;

                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        btnGeolocate.disabled = false;
                        const lat = position.coords.latitude.toFixed(6);
                        const lng = position.coords.longitude.toFixed(6);

                        latInput.value = lat;
                        lngInput.value = lng;

                        if (statusDiv) {
                            statusDiv.textContent = "Location captured ✓";
                            statusDiv.style.color = "var(--color-success)";
                        }
                        if (previewDiv) {
                            const mapsUrl = "https://www.google.com/maps/dir/?api=1&destination=" + encodeURIComponent(lat) + "," + encodeURIComponent(lng);
                            previewDiv.innerHTML = '<a href="' + mapsUrl + '" target="_blank" rel="noopener noreferrer" style="color: var(--color-primary); text-decoration: underline;">Preview in Google Maps</a>';
                            previewDiv.style.display = "block";
                        }
                        updateFormState();
                    },
                    function(error) {
                        btnGeolocate.disabled = false;
                        if (statusDiv) {
                            statusDiv.textContent = "Couldn't get your location — please enter your address";
                            statusDiv.style.color = "var(--color-danger)";
                        }
                        updateFormState();
                    },
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
                );
            });
        }

        // Final client-side guard on form submit
        if (checkoutForm) {
            checkoutForm.addEventListener("submit", function(e) {
                if (!hasValidCoords() && !hasAddress()) {
                    e.preventDefault();
                    if (statusDiv) {
                        statusDiv.textContent = "A delivery location is required — share your location or enter an address.";
                        statusDiv.style.color = "var(--color-danger)";
                    }
                    if (submitError) {
                        submitError.style.display = "block";
                    }
                }
            });
        }
    });
})();
