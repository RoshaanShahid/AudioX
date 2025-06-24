/**
 * AudioX Creator Earnings Dashboard - Interactive Components Handler
 *
 * This script manages client-side interactions for the Creator Earnings Dashboard,
 * including Alpine.js component state management, loading states, and filter interactions.
 *
 * Features handled:
 * - Main content loading state management
 * - Book list loading state management
 * - Alpine.js component communication
 * - Error handling and logging
 */

document.addEventListener("DOMContentLoaded", () => {
  // ============================================================================
  // CONSTANTS AND CONFIGURATION
  // ============================================================================

  const COMPONENT_SELECTORS = {
    MAIN_CONTENT: '[x-data*="mainContentLoading"]',
    BOOK_LIST: '[x-data*="bookListLoadingState"]',
  }

  const LOADING_STATES = {
    MAIN_CONTENT: "mainContentLoading",
    BOOK_LIST: "bookListLoadingState",
  }

  // ============================================================================
  // UTILITY FUNCTIONS
  // ============================================================================

  /**
   * Find and return Alpine.js component by selector
   * @param {string} selector - CSS selector for the component
   * @returns {Object|null} Alpine component or null if not found
   */
  function findAlpineComponent(selector) {
    const element = document.querySelector(selector)
    if (element && element.__x) {
      return element.__x
    }
    return null
  }

  /**
   * Update Alpine.js component data property safely
   * @param {string} selector - CSS selector for the component
   * @param {string} property - Property name to update
   * @param {*} value - New value for the property
   */
  function updateAlpineData(selector, property, value) {
    const component = findAlpineComponent(selector)
    if (component && component.$data) {
      component.$data[property] = value
    } else {
      console.warn(`Alpine.js component not found or not initialized: ${selector}`)
    }
  }

  // ============================================================================
  // EVENT LISTENERS
  // ============================================================================

  /**
   * Handle main content loading state changes
   * Updates the Alpine.js component that controls the main content loading overlay
   */
  window.addEventListener("setmainloading", (event) => {
    try {
      updateAlpineData(COMPONENT_SELECTORS.MAIN_CONTENT, LOADING_STATES.MAIN_CONTENT, event.detail)
    } catch (error) {
      console.error("Error updating main content loading state:", error)
    }
  })

  /**
   * Handle book list loading state changes
   * Updates the Alpine.js component that controls the book list loading overlay
   */
  window.addEventListener("setbooklistloading", (event) => {
    try {
      updateAlpineData(COMPONENT_SELECTORS.MAIN_CONTENT, LOADING_STATES.BOOK_LIST, event.detail)
    } catch (error) {
      console.error("Error updating book list loading state:", error)
    }
  })

  // ============================================================================
  // INITIALIZATION
  // ============================================================================

  /**
   * Initialize dashboard components and verify Alpine.js is working
   */
  function initializeDashboard() {
    // Verify Alpine.js components are available
    const mainComponent = findAlpineComponent(COMPONENT_SELECTORS.MAIN_CONTENT)

    if (mainComponent) {
      console.log("✅ Earnings dashboard initialized successfully")
    } else {
      console.warn("⚠️ Alpine.js components may not be fully initialized yet")
    }

    // Set up any additional dashboard-specific functionality here
    setupFilterInteractions()
    setupPerformanceMonitoring()
  }

  /**
   * Setup filter interaction enhancements
   */
  function setupFilterInteractions() {
    // Add smooth scrolling to expanded audiobook sections
    document.addEventListener("click", (event) => {
      const expandButton = event.target.closest('[role="button"][aria-expanded]')
      if (expandButton) {
        setTimeout(() => {
          const isExpanded = expandButton.getAttribute("aria-expanded") === "true"
          if (isExpanded) {
            expandButton.scrollIntoView({
              behavior: "smooth",
              block: "nearest",
            })
          }
        }, 300) // Wait for Alpine.js collapse animation
      }
    })
  }

  /**
   * Setup performance monitoring for loading states
   */
  function setupPerformanceMonitoring() {
    let loadingStartTime = null

    // Monitor loading start
    window.addEventListener("setmainloading", (event) => {
      if (event.detail === true) {
        loadingStartTime = performance.now()
      } else if (event.detail === false && loadingStartTime) {
        const loadingDuration = performance.now() - loadingStartTime
        console.log(`📊 Main content loaded in ${loadingDuration.toFixed(2)}ms`)
        loadingStartTime = null
      }
    })

    // Monitor book list loading
    window.addEventListener("setbooklistloading", (event) => {
      if (event.detail === true) {
        console.log("📚 Loading book list data...")
      } else if (event.detail === false) {
        console.log("✅ Book list data loaded")
      }
    })
  }

  // ============================================================================
  // ERROR HANDLING
  // ============================================================================

  /**
   * Global error handler for dashboard-specific errors
   */
  window.addEventListener("error", (event) => {
    if (event.filename && event.filename.includes("creator_myearnings")) {
      console.error("Dashboard Error:", {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      })
    }
  })

  // ============================================================================
  // INITIALIZATION CALL
  // ============================================================================

  // Initialize dashboard after a short delay to ensure Alpine.js is ready
  setTimeout(initializeDashboard, 100)

  console.log("🚀 Creator earnings dashboard script loaded")
})
