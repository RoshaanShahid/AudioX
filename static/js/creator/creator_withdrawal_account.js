/**
 * ============================================================================
 * AUDIOX CREATOR WITHDRAWAL ACCOUNT - JAVASCRIPT MODULE
 * ============================================================================
 *
 * This module handles all frontend functionality for the payout methods management:
 * - Form validation for adding new payout methods
 * - Confirmation dialogs for account operations
 * - Dynamic form behavior based on account type selection
 * - Error handling and user feedback
 * - Loading states and UI interactions
 *
 * Dependencies:
 * - SweetAlert2 for notifications and confirmations
 * - Alpine.js for reactive form behavior
 * - Font Awesome for icons
 * - Django CSRF token handling
 *
 * Author: AudioX Development Team
 * Last Updated: 2024
 * ============================================================================
 */

// ============================================================================
// GLOBAL VARIABLES AND CONFIGURATION
// ============================================================================

let isProcessing = false
let isFormSubmitting = false // New flag to track form submissions

// ============================================================================
// SWEETALERT2 CONFIGURATION
// ============================================================================

/**
 * Configuration for SweetAlert2 modals with AudioX branding
 * @param {string} iconColorParam - The color for the icon
 * @returns {object} SweetAlert2 configuration object
 */
const swalAudioXConfig = (iconColorParam) => {
  const iconColor = iconColorParam || "#6b7280" // Default neutral gray
  let confirmBgColor = "bg-audiox-blue" // Default confirm button background
  let confirmRingColor = "focus-visible:ring-audiox-blue" // Default confirm button ring

  // Adjust confirm button color for specific actions
  if (iconColor === "#ef4444") {
    // Red for danger actions
    confirmBgColor = "bg-red-600"
    confirmRingColor = "focus-visible:ring-red-600"
  } else if (iconColor === "#f59e0b") {
    // Amber for warnings
    confirmBgColor = "bg-audiox-blue" // Keep theme color
  }

  return {
    iconColor: iconColor,
    buttonsStyling: false, // Use custom Tailwind classes
    showClass: {
      popup: "animate__animated animate__fadeIn animate__faster",
    },
    hideClass: {
      popup: "animate__animated animate__fadeOut animate__faster",
    },
    background: "#ffffff",
    customClass: {
      popup: "bg-white text-gray-700 rounded-2xl border border-gray-200 shadow-2xl",
      title: "text-gray-900 text-xl font-bold mb-2",
      htmlContainer: "text-gray-600 text-sm leading-relaxed",
      confirmButton: `${confirmBgColor} text-white rounded-xl px-6 py-3 text-sm font-semibold transition-all duration-150 ease-in-out shadow-lg ${confirmRingColor} hover:opacity-90 transform hover:scale-105`,
      cancelButton:
        "bg-white text-gray-700 border border-gray-300 rounded-xl px-6 py-3 text-sm font-semibold transition-all duration-150 ease-in-out shadow-md hover:bg-gray-50 transform hover:scale-105",
      actions: "space-x-4 mt-6",
      icon: "mt-2 mb-4 scale-110",
    },
  }
}

// ============================================================================
// PAYOUT METHOD DELETION
// ============================================================================

/**
 * Handles the deletion of a payout method with confirmation dialog
 * @param {Event} event - The form submission event
 * @param {HTMLFormElement} formElement - The form being submitted
 * @param {string} accountDetails - Description of the account to be deleted
 */
function handleDelete(event, formElement, accountDetails) {
  event.preventDefault()

  if (isProcessing) {
    showNotification("Please wait for the current operation to complete", "warning")
    return
  }

  Swal.fire({
    ...swalAudioXConfig("#ef4444"), // Red icon for danger
    title: "Delete Payout Method?",
    html: `
           <div class="text-center">
               <p class="mb-4">Are you sure you want to delete the <strong class="text-audiox-blue">${accountDetails}</strong>?</p>
               <div class="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
                   <div class="flex items-center justify-center mb-2">
                       <i class="fas fa-exclamation-triangle text-red-500 mr-2"></i>
                       <span class="font-semibold text-red-800">This action cannot be undone</span>
                   </div>
                   <ul class="text-sm text-red-700 text-left space-y-1">
                       <li>• The payout method will be permanently removed</li>
                       <li>• You won't be able to receive payments to this account</li>
                       <li>• Any pending transactions may be affected</li>
                   </ul>
               </div>
           </div>
       `,
    icon: "warning",
    showCancelButton: true,
    confirmButtonText: '<i class="fas fa-trash mr-2"></i>Yes, Delete It',
    cancelButtonText: '<i class="fas fa-times mr-2"></i>Cancel',
    reverseButtons: true,
  }).then((result) => {
    if (result.isConfirmed) {
      isProcessing = true
      isFormSubmitting = true // Set form submission flag
      showLoadingOverlay("Deleting payout method...")

      // Add loading state to the form
      const submitBtn = formElement.querySelector('button[type="submit"]')
      if (submitBtn) {
        submitBtn.disabled = true
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Deleting...'
      }

      formElement.submit()
    }
  })
}

// ============================================================================
// SET PRIMARY PAYOUT METHOD
// ============================================================================

/**
 * Handles setting a payout method as primary with confirmation dialog
 * @param {Event} event - The form submission event
 * @param {HTMLFormElement} formElement - The form being submitted
 * @param {string} accountDetails - Description of the account to be set as primary
 */
function handleSetPrimary(event, formElement, accountDetails) {
  event.preventDefault()

  if (isProcessing) {
    showNotification("Please wait for the current operation to complete", "warning")
    return
  }

  Swal.fire({
    ...swalAudioXConfig("#091e65"), // AudioX blue for confirmation
    title: "Set as Primary Method?",
    html: `
           <div class="text-center">
               <p class="mb-4">Set <strong class="text-audiox-blue">${accountDetails}</strong> as your primary payout method?</p>
               <div class="bg-blue-50 border border-blue-200 rounded-xl p-4">
                   <div class="flex items-center justify-center mb-2">
                       <i class="fas fa-star text-yellow-500 mr-2"></i>
                       <span class="font-semibold text-blue-800">Primary Method Benefits</span>
                   </div>
                   <ul class="text-sm text-blue-700 text-left space-y-1">
                       <li>• Default destination for all payouts</li>
                       <li>• Faster processing for earnings</li>
                       <li>• Priority in payment scheduling</li>
                   </ul>
               </div>
           </div>
       `,
    icon: "question",
    showCancelButton: true,
    confirmButtonText: '<i class="fas fa-star mr-2"></i>Set as Primary',
    cancelButtonText: '<i class="fas fa-times mr-2"></i>Cancel',
    reverseButtons: true,
  }).then((result) => {
    if (result.isConfirmed) {
      isProcessing = true
      isFormSubmitting = true // Set form submission flag
      showLoadingOverlay("Setting as primary method...")

      // Add loading state to the form
      const submitBtn = formElement.querySelector('button[type="submit"]')
      if (submitBtn) {
        submitBtn.disabled = true
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Setting...'
      }

      formElement.submit()
    }
  })
}

// ============================================================================
// ADD NEW PAYOUT ACCOUNT
// ============================================================================

/**
 * Handles adding a new payout account with validation and confirmation
 * @param {Event} event - The form submission event
 * @param {HTMLFormElement} formElement - The form being submitted
 */
function handleAddAccount(event, formElement) {
  event.preventDefault()

  if (isProcessing) {
    showNotification("Please wait for the current operation to complete", "warning")
    return
  }

  // Clear previous validation errors
  clearFormErrors(formElement)

  // Validate form
  if (!validateAddAccountForm(formElement)) {
    return
  }

  // Gather form data for confirmation
  const formData = new FormData(formElement)
  const confirmationData = gatherConfirmationData(formElement, formData)

  // Show confirmation dialog
  showAddAccountConfirmation(formElement, confirmationData)
}

/**
 * Clears all form validation errors
 * @param {HTMLFormElement} formElement - The form element
 */
function clearFormErrors(formElement) {
  // Remove error styling from inputs
  formElement.querySelectorAll(".border-red-500").forEach((el) => {
    el.classList.remove("border-red-500", "ring-red-500", "ring-2", "focus:ring-red-500")
    el.classList.add("border-gray-300", "focus:ring-audiox-blue", "focus:border-audiox-blue")
  })

  // Clear error messages
  formElement.querySelectorAll('p[id^="error_"]').forEach((el) => (el.textContent = ""))

  // Clear non-field errors
  const nonFieldErrorsContainer = formElement.querySelector("#non_field_errors_container")
  if (nonFieldErrorsContainer) {
    nonFieldErrorsContainer.innerHTML = ""
  }
}

/**
 * Validates the add account form
 * @param {HTMLFormElement} formElement - The form element
 * @returns {boolean} True if form is valid
 */
function validateAddAccountForm(formElement) {
  let isValid = true
  const requiredInputs = formElement.querySelectorAll("[required]")

  requiredInputs.forEach((input) => {
    const errorElement = formElement.querySelector(`#error_${input.name}`)

    // Check if input is visible and not disabled
    if (!input.disabled && input.offsetParent !== null && !input.value.trim()) {
      isValid = false

      // Add error styling
      input.classList.remove("border-gray-300", "focus:ring-audiox-blue", "focus:border-audiox-blue")
      input.classList.add("border-red-500", "ring-red-500", "ring-2", "focus:ring-red-500")

      // Show error message
      if (errorElement) {
        errorElement.textContent = "This field is required."
      }
    }
  })

  // Additional validation for specific fields
  if (!validateAccountIdentifier(formElement)) {
    isValid = false
  }

  if (!isValid) {
    showNotification("Please fill out all required fields correctly", "error")

    // Scroll to first error
    const firstError = formElement.querySelector(".border-red-500")
    if (firstError) {
      firstError.scrollIntoView({ behavior: "smooth", block: "center" })
      firstError.focus()
    }
  }

  return isValid
}

/**
 * Validates account identifier based on account type
 * @param {HTMLFormElement} formElement - The form element
 * @returns {boolean} True if identifier is valid
 */
function validateAccountIdentifier(formElement) {
  const accountTypeSelect = formElement.querySelector('select[name="account_type"]')
  const identifierInput = formElement.querySelector('input[name="account_identifier"]')
  const errorElement = formElement.querySelector("#error_account_identifier")

  if (!accountTypeSelect || !identifierInput) return true

  const accountType = accountTypeSelect.value
  const identifier = identifierInput.value.trim()

  let isValid = true
  let errorMessage = ""

  if (accountType === "bank") {
    // IBAN validation for Pakistan (24 characters, starts with PK)
    const ibanPattern = /^PK\d{22}$/
    if (!ibanPattern.test(identifier)) {
      isValid = false
      errorMessage = "Please enter a valid Pakistani IBAN (24 characters starting with PK)"
    }
  } else {
    // Mobile number validation for digital wallets
    const mobilePattern = /^03\d{9}$/
    if (!mobilePattern.test(identifier)) {
      isValid = false
      errorMessage = "Please enter a valid mobile number (11 digits starting with 03)"
    }
  }

  if (!isValid) {
    identifierInput.classList.remove("border-gray-300", "focus:ring-audiox-blue", "focus:border-audiox-blue")
    identifierInput.classList.add("border-red-500", "ring-red-500", "ring-2", "focus:ring-red-500")

    if (errorElement) {
      errorElement.textContent = errorMessage
    }
  }

  return isValid
}

/**
 * Gathers form data for confirmation dialog
 * @param {HTMLFormElement} formElement - The form element
 * @param {FormData} formData - The form data
 * @returns {object} Confirmation data object
 */
function gatherConfirmationData(formElement, formData) {
  const accountTypeSelect = formElement.querySelector('select[name="account_type"]')
  const bankNameSelect = formElement.querySelector('select[name="bank_name"]')

  const data = {
    accountType: accountTypeSelect.options[accountTypeSelect.selectedIndex].text,
    accountTitle: formData.get("account_title"),
    accountIdentifier: formData.get("account_identifier"),
    bankName: null,
    isPrimary: formElement.querySelector('input[name="is_primary"]').checked,
  }

  // Add bank name if it's a bank account
  if (formData.get("account_type") === "bank" && !bankNameSelect.disabled && bankNameSelect.value) {
    data.bankName = bankNameSelect.options[bankNameSelect.selectedIndex].text
  }

  return data
}

/**
 * Shows confirmation dialog for adding account
 * @param {HTMLFormElement} formElement - The form element
 * @param {object} data - Confirmation data
 */
function showAddAccountConfirmation(formElement, data) {
  let confirmationHtml = `
       <div class="text-center">
           <p class="mb-6 text-gray-600">Please review the details before adding this payout method:</p>
           <div class="bg-gray-50 border border-gray-200 rounded-xl p-6 text-left">
               <div class="space-y-4">
                   <div class="flex justify-between items-center py-2 border-b border-gray-200">
                       <span class="font-semibold text-gray-700">
                           <i class="fas fa-tag mr-2 text-audiox-blue"></i>Type:
                       </span>
                       <span class="text-gray-900 font-medium">${data.accountType}</span>
                   </div>
                   <div class="flex justify-between items-center py-2 border-b border-gray-200">
                       <span class="font-semibold text-gray-700">
                           <i class="fas fa-user mr-2 text-audiox-blue"></i>Title:
                       </span>
                       <span class="text-gray-900 font-medium">${data.accountTitle}</span>
                   </div>
                   <div class="flex justify-between items-center py-2 border-b border-gray-200">
                       <span class="font-semibold text-gray-700">
                           <i class="fas fa-id-card mr-2 text-audiox-blue"></i>Identifier:
                       </span>
                       <span class="text-gray-900 font-mono text-sm bg-white px-2 py-1 rounded border">${data.accountIdentifier}</span>
                   </div>
   `

  if (data.bankName) {
    confirmationHtml += `
                   <div class="flex justify-between items-center py-2 border-b border-gray-200">
                       <span class="font-semibold text-gray-700">
                           <i class="fas fa-university mr-2 text-audiox-blue"></i>Bank:
                       </span>
                       <span class="text-gray-900 font-medium">${data.bankName}</span>
                   </div>
       `
  }

  confirmationHtml += `
                   <div class="flex justify-between items-center py-2">
                       <span class="font-semibold text-gray-700">
                           <i class="fas fa-star mr-2 text-yellow-500"></i>Primary Method:
                       </span>
                       <span class="text-gray-900 font-medium">
                           ${
                             data.isPrimary
                               ? '<span class="text-green-600"><i class="fas fa-check mr-1"></i>Yes</span>'
                               : '<span class="text-gray-500"><i class="fas fa-times mr-1"></i>No</span>'
                           }
                       </span>
                   </div>
               </div>
           </div>
       </div>
   `

  Swal.fire({
    ...swalAudioXConfig("#091e65"),
    title: "Confirm Payout Method",
    html: confirmationHtml,
    icon: "info",
    showCancelButton: true,
    confirmButtonText: '<i class="fas fa-plus mr-2"></i>Add Method',
    cancelButtonText: '<i class="fas fa-edit mr-2"></i>Edit Details',
    reverseButtons: true,
    customClass: {
      ...swalAudioXConfig("#091e65").customClass,
      htmlContainer: "text-sm mb-4",
    },
  }).then((result) => {
    if (result.isConfirmed) {
      isProcessing = true
      isFormSubmitting = true // Set form submission flag
      showLoadingOverlay("Adding payout method...")

      // Add loading state to submit button
      const submitButton = formElement.querySelector('button[type="submit"]')
      if (submitButton) {
        submitButton.disabled = true
        submitButton.innerHTML = `
                   <svg class="animate-spin h-4 w-4 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                       <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                       <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 714 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                   </svg>
                   Adding...
               `
      }

      formElement.submit()
    }
  })
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

/**
 * Shows loading overlay with message
 * @param {string} message - Loading message
 */
function showLoadingOverlay(message = "Processing...") {
  const overlay = document.getElementById("loadingOverlay")
  const messageElement = document.getElementById("loaderMessage")

  if (overlay) {
    if (messageElement) {
      messageElement.textContent = message
    }
    overlay.classList.remove("hidden")
  }
}

/**
 * Hides loading overlay
 */
function hideLoadingOverlay() {
  const overlay = document.getElementById("loadingOverlay")
  if (overlay) {
    overlay.classList.add("hidden")
  }
}

/**
 * Shows notification using SweetAlert2
 * @param {string} message - Notification message
 * @param {string} type - Notification type (success, error, warning, info)
 */
function showNotification(message, type = "info") {
  const config = {
    text: message,
    timer: 5000,
    timerProgressBar: true,
    showConfirmButton: false,
    toast: true,
    position: "top-end",
    showClass: {
      popup: "animate__animated animate__fadeInRight",
    },
    hideClass: {
      popup: "animate__animated animate__fadeOutRight",
    },
  }

  switch (type) {
    case "success":
      config.icon = "success"
      config.iconColor = "#091e65"
      config.background = "#f0fdf4"
      config.color = "#15803d"
      break
    case "error":
      config.icon = "error"
      config.iconColor = "#E53E3E"
      config.background = "#fef2f2"
      config.color = "#b91c1c"
      break
    case "warning":
      config.icon = "warning"
      config.iconColor = "#f97316"
      config.background = "#fffbeb"
      config.color = "#d97706"
      break
    default:
      config.icon = "info"
      config.iconColor = "#091e65"
      config.background = "#eff6ff"
      config.color = "#1d4ed8"
  }

  Swal.fire(config)
}

/**
 * Gets CSRF token from the page
 * @returns {string} CSRF token
 */
function getCsrfToken() {
  const csrfInput = document.querySelector("[name=csrfmiddlewaretoken]")
  if (csrfInput) {
    return csrfInput.value
  }

  // Fallback: try to get from meta tag
  const csrfMeta = document.querySelector('meta[name="csrf-token"]')
  if (csrfMeta) {
    return csrfMeta.getAttribute("content")
  }

  console.warn("⚠️ CSRF token not found")
  return ""
}

// ============================================================================
// EVENT LISTENERS AND INITIALIZATION
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  console.log("🚀 AudioX Creator Withdrawal Account - Initializing...")

  // Initialize form validation helpers
  initializeFormHelpers()

  // Initialize keyboard shortcuts
  initializeKeyboardShortcuts()

  console.log("✅ AudioX Creator Withdrawal Account - Initialization complete")
})

/**
 * Initializes form helper functionality
 */
function initializeFormHelpers() {
  // Add real-time validation for account identifier
  const identifierInput = document.querySelector('input[name="account_identifier"]')
  if (identifierInput) {
    identifierInput.addEventListener("input", function () {
      // Clear previous errors on input
      this.classList.remove("border-red-500", "ring-red-500", "ring-2", "focus:ring-red-500")
      this.classList.add("border-gray-300", "focus:ring-audiox-blue", "focus:border-audiox-blue")

      const errorElement = document.querySelector("#error_account_identifier")
      if (errorElement) {
        errorElement.textContent = ""
      }
    })
  }

  // Add formatting for IBAN input
  const accountTypeSelect = document.querySelector('select[name="account_type"]')
  if (accountTypeSelect && identifierInput) {
    accountTypeSelect.addEventListener("change", function () {
      if (this.value === "bank") {
        identifierInput.placeholder = "e.g., PK12ABCD0123456789012345"
        identifierInput.maxLength = 24
      } else {
        identifierInput.placeholder = "e.g., 03001234567"
        identifierInput.maxLength = 11
      }
      identifierInput.value = "" // Clear on type change
    })
  }
}

/**
 * Initializes keyboard shortcuts
 */
function initializeKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Escape key to close modals
    if (e.key === "Escape" && Swal.isVisible()) {
      Swal.close()
    }

    // Ctrl/Cmd + Enter to submit form
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      const addForm = document.getElementById("add-account-form")
      if (addForm && !isProcessing) {
        e.preventDefault()
        addForm.dispatchEvent(new Event("submit"))
      }
    }
  })
}

// ============================================================================
// ERROR HANDLING AND CLEANUP
// ============================================================================

// FIXED: Modified beforeunload event to not interfere with form submissions
window.addEventListener("beforeunload", (e) => {
  // Only show warning if processing but NOT submitting a form
  if (isProcessing && !isFormSubmitting) {
    e.preventDefault()
    e.returnValue = "A payout method operation is in progress. Are you sure you want to leave?"
    return e.returnValue
  }
})

// Handle page visibility changes
document.addEventListener("visibilitychange", () => {
  if (document.hidden && isProcessing) {
    console.log("⚠️ Page hidden during processing operation")
  }
})

// Global error handler
window.addEventListener("error", (e) => {
  console.error("💥 Global error caught:", e.error)

  if (isProcessing) {
    showNotification("An unexpected error occurred. Please try again.", "error")
    isProcessing = false
    isFormSubmitting = false // Reset form submission flag
    hideLoadingOverlay()
  }
})

// Handle network status
window.addEventListener("online", () => {
  console.log("🌐 Network connection restored")
})

window.addEventListener("offline", () => {
  console.log("📡 Network connection lost")
  showNotification("Network connection lost. Please check your internet connection.", "warning")
})

// Reset flags when page loads (in case of redirect back)
window.addEventListener("pageshow", () => {
  isProcessing = false
  isFormSubmitting = false
  hideLoadingOverlay()
})

console.log("💳 AudioX Creator Withdrawal Account - JavaScript loaded successfully")
