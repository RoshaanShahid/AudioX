/**
 * ==================== SERVICE WORKER INITIALIZATION ====================
 *
 * This file handles the registration of the service worker for AudioX
 * to enable offline functionality and caching.
 *
 * Author: AudioX Development Team
 * Version: 1.0
 * Last Updated: 2024
 */

// Service Worker Registration
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/service_worker.js", { scope: "/" })
      .then((registration) => {
        console.log("Service Worker: Registered successfully")
        console.log("SW registered: ", registration)
      })
      .catch((error) => {
        console.error("Service Worker: Registration failed: ", error)
      })
  })
}
