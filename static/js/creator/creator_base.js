/**
 * ============================================================================
 * AUDIOX CREATOR BASE - JAVASCRIPT MODULE
 * ============================================================================
 * Handles creator interface interactions including mode switching and
 * navigation highlighting with clean, simple functionality.
 *
 * Features:
 * - Mode switching with loading overlay
 * - Active navigation link highlighting
 * - Mobile menu management
 * - Clean, minimal interactions
 *
 * Author: AudioX Development Team
 * Version: 2.0
 * Last Updated: 2024
 * ============================================================================
 */

document.addEventListener("DOMContentLoaded", () => {
  console.log("🎵 AudioX Creator Base JavaScript initialized")

  // ============================================================================
  // DOM ELEMENT REFERENCES
  // ============================================================================

  const modeSwitchLoader = document.getElementById("mode-switch-loader")
  const headerSwitchBtn = document.getElementById("header-switch-normal-btn")
  const mobileSwitchBtn = document.getElementById("mobile-switch-normal-btn")
  const mobileMenuDiv = document.getElementById("mobile-menu")

  // Navigation elements
  const topNavLinks = document.querySelectorAll("nav .top-nav-link")
  const mobileNavLinks = document.querySelectorAll("#mobile-menu a.mobile-nav-link")

  // Current page information
  const currentPath = window.location.pathname

  // ============================================================================
  // URL PATTERNS FOR NAVIGATION MATCHING
  // ============================================================================

  const urlPatterns = {
    dashboard: "/creator/dashboard/",
    myAudiobooks: "/creator/my-audiobooks/",
    uploadAudiobook: "/creator/upload-audiobook/",
    myEarnings: "/creator/my-earnings/",
    withdrawalList: "/creator/request-withdrawal-list/",
    withdrawalAccounts: "/creator/manage-withdrawal-accounts/",
    profileUpdate: "/creator/profile/update/",
    manageAudiobookPattern: /^\/creator\/manage-upload\/[\w-]+?\/?$/,
  }

  // ============================================================================
  // MODE SWITCHING FUNCTIONALITY
  // ============================================================================

  /**
   * Handles switching to user mode with loading overlay
   */
  function handleSwitchToUserMode() {
    console.log("🔄 Switching to user mode...")

    // Find target URL for redirection
    const myProfileLink = document.querySelector('a[href*="/my-profile/"]')
    const targetUrl = myProfileLink ? myProfileLink.href : "/"

    // Show loading overlay
    if (modeSwitchLoader) {
      modeSwitchLoader.classList.remove("hidden")
      console.log("📱 Mode switch loader displayed")
    }

    // Redirect after delay
    setTimeout(() => {
      console.log("🚀 Redirecting to: " + targetUrl)
      window.location.href = targetUrl
    }, 1500)
  }

  // Event listener for the header switch button
  if (headerSwitchBtn) {
    headerSwitchBtn.addEventListener("click", handleSwitchToUserMode)
    console.log("🖥️ Header switch button listener attached")
  }

  // Event listener for the mobile switch button
  if (mobileSwitchBtn) {
    mobileSwitchBtn.addEventListener("click", handleSwitchToUserMode)
    console.log("📱 Mobile switch button listener attached")
  }

  // ============================================================================
  // NAVIGATION LINK HIGHLIGHTING
  // ============================================================================

  /**
   * Determines if a navigation link should be active
   * @param {string} linkHref - The href attribute of the navigation link
   * @param {string} currentPath - The current window pathname
   * @returns {boolean} True if the link should be active
   */
  function isLinkActive(linkHref, currentPath) {
    // Direct path match
    if (linkHref === currentPath) {
      return true
    }

    // Special handling for grouped URLs
    if (
      linkHref === urlPatterns.withdrawalList &&
      (currentPath === urlPatterns.withdrawalAccounts || currentPath.startsWith(urlPatterns.withdrawalList))
    ) {
      return true
    }

    if (
      linkHref === urlPatterns.myAudiobooks &&
      (currentPath === urlPatterns.myAudiobooks ||
        urlPatterns.manageAudiobookPattern.test(currentPath) ||
        currentPath === urlPatterns.uploadAudiobook)
    ) {
      return true
    }

    return false
  }

  /**
   * Highlights the active navigation link based on current path
   */
  function highlightActiveNavigation() {
    console.log("🧭 Highlighting navigation for path: " + currentPath)

    let activeSet = false

    // Process desktop navigation links
    topNavLinks.forEach((link) => {
      const linkHref = link.getAttribute("href")

      // Remove active styles - keep text white for inactive links
      link.classList.remove("bg-white/20", "font-semibold", "shadow-lg")
      link.classList.add("text-white", "font-medium")

      if (isLinkActive(linkHref, currentPath)) {
        // Add active styles
        link.classList.remove("font-medium")
        link.classList.add("bg-white/20", "font-semibold", "shadow-lg")
        activeSet = true
        console.log("✅ Desktop link activated: " + linkHref)
      }
    })

    // Process mobile navigation links
    mobileNavLinks.forEach((link) => {
      const linkHref = link.getAttribute("href")

      // Remove active styles - keep text white for inactive links
      link.classList.remove("bg-white/20", "font-semibold")
      link.classList.add("text-white", "font-medium")

      if (isLinkActive(linkHref, currentPath)) {
        // Add active styles
        link.classList.remove("font-medium")
        link.classList.add("bg-white/20", "font-semibold")
        console.log("✅ Mobile link activated: " + linkHref)
      }
    })

    // Default to Dashboard if no other link is active
    if (!activeSet && currentPath === urlPatterns.dashboard) {
      const dashboardLinkDesktop = document.querySelector('nav .top-nav-link[href="' + urlPatterns.dashboard + '"]')
      const dashboardLinkMobile = document.querySelector(
        '#mobile-menu a.mobile-nav-link[href="' + urlPatterns.dashboard + '"]',
      )

      if (dashboardLinkDesktop) {
        dashboardLinkDesktop.classList.remove("font-medium")
        dashboardLinkDesktop.classList.add("bg-white/20", "font-semibold", "shadow-lg")
        console.log("✅ Dashboard link activated (default)")
      }
      if (dashboardLinkMobile) {
        dashboardLinkMobile.classList.remove("font-medium")
        dashboardLinkMobile.classList.add("bg-white/20", "font-semibold")
      }
    }
  }

  // ============================================================================
  // MOBILE MENU SETUP
  // ============================================================================

  /**
   * Ensures proper mobile menu setup for Alpine.js
   */
  function setupMobileMenu() {
    if (mobileMenuDiv && !mobileMenuDiv.hasAttribute("x-cloak")) {
      mobileMenuDiv.setAttribute("x-cloak", "")
      console.log("📱 Mobile menu x-cloak attribute added")
    }
  }

  // ============================================================================
  // EVENT LISTENERS SETUP
  // ============================================================================

  /**
   * Sets up all event listeners
   */
  function setupEventListeners() {
    // Mode switching event listeners
    if (headerSwitchBtn) {
      headerSwitchBtn.addEventListener("click", handleSwitchToUserMode)
      console.log("🖥️ Header switch button listener attached")
    }

    if (mobileSwitchBtn) {
      mobileSwitchBtn.addEventListener("click", handleSwitchToUserMode)
      console.log("📱 Mobile switch button listener attached")
    }

    console.log("🎯 All event listeners attached successfully")
  }

  // ============================================================================
  // INITIALIZATION
  // ============================================================================

  /**
   * Initialize all creator base functionality
   */
  function initialize() {
    console.log("🚀 Initializing creator base functionality...")

    try {
      setupEventListeners()
      highlightActiveNavigation()
      setupMobileMenu()

      console.log("✅ Creator base initialization complete")
    } catch (error) {
      console.error("❌ Error during creator base initialization:", error)
    }
  }

  // Start initialization
  initialize()

  // ============================================================================
  // UTILITY FUNCTIONS
  // ============================================================================

  /**
   * Adds smooth scroll behavior to internal links.
   */
  function addSmoothScrolling() {
    const internalLinks = document.querySelectorAll('a[href^="#"]')
    internalLinks.forEach((link) => {
      link.addEventListener("click", function (e) {
        e.preventDefault()
        const target = document.querySelector(this.getAttribute("href"))
        if (target) {
          target.scrollIntoView({
            behavior: "smooth",
            block: "start",
          })
        }
      })
    })
  }

  /**
   * Adds loading states to form submissions.
   */
  function addFormLoadingStates() {
    const forms = document.querySelectorAll("form")
    forms.forEach((form) => {
      form.addEventListener("submit", function () {
        const submitBtn = this.querySelector('button[type="submit"]')
        if (submitBtn) {
          submitBtn.disabled = true
          submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...'
        }
      })
    })
  }

  // Initialize additional features
  addSmoothScrolling()
  addFormLoadingStates()

  console.log("🎉 AudioX Creator Base fully loaded and ready!")
})

/**
 * ============================================================================
 * END OF CREATOR BASE JAVASCRIPT MODULE
 * ============================================================================
 */
