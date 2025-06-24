/**
 * ============================================================================
 * AUDIOX CREATOR WITHDRAWAL REQUEST - JAVASCRIPT MODULE
 * ============================================================================
 *
 * This module handles all frontend functionality for withdrawal requests:
 * - Form validation for withdrawal amounts and account selection
 * - Confirmation dialogs using SweetAlert2
 * - Real-time validation feedback
 * - Loading states and user feedback
 * - Error handling and display
 *
 * Dependencies:
 * - SweetAlert2 for notifications and confirmations
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
// DOCUMENT READY INITIALIZATION
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  console.log("🚀 AudioX Creator Withdrawal Request - Initializing...")

  // Initialize all components
  initializeWithdrawalForm()
  initializeFormValidation()
  initializeKeyboardShortcuts()

  console.log("✅ AudioX Creator Withdrawal Request - Initialization complete")
})

// ============================================================================
// WITHDRAWAL FORM INITIALIZATION
// ============================================================================

/**
 * Initializes the withdrawal request form
 */
function initializeWithdrawalForm() {
  const withdrawalForm = document.getElementById("requestWithdrawalForm")

  if (!withdrawalForm) {
    console.log("ℹ️ Withdrawal form not found - user may not have permission to request withdrawals")
    return
  }

  // Add form submission handler
  withdrawalForm.addEventListener("submit", handleFormSubmission)

  // Add real-time validation
  const amountInput = document.getElementById("amount")
  const accountSelect = document.getElementById("withdrawal_account_id")

  if (amountInput) {
    amountInput.addEventListener("input", validateAmountInput)
    amountInput.addEventListener("blur", validateAmountInput)
  }

  if (accountSelect) {
    accountSelect.addEventListener("change", validateAccountSelection)
  }

  console.log("📝 Withdrawal form initialized")
}

// ============================================================================
// FORM VALIDATION
// ============================================================================

/**
 * Initializes form validation helpers
 */
function initializeFormValidation() {
  // Clear any existing errors on page load
  clearAllErrors()
}

/**
 * Handles form submission with validation and confirmation
 * @param {Event} event - Form submission event
 */
function handleFormSubmission(event) {
  event.preventDefault()

  if (isProcessing) {
    showNotification("Please wait for the current request to complete", "warning")
    return
  }

  // Clear previous errors
  clearAllErrors()

  // Validate form
  if (!validateForm()) {
    return
  }

  // Show confirmation dialog
  showWithdrawalConfirmation()
}

/**
 * Validates the entire form
 * @returns {boolean} True if form is valid
 */
function validateForm() {
  const amountInput = document.getElementById("amount")
  const accountSelect = document.getElementById("withdrawal_account_id")

  let isValid = true
  let amountErrors = []
  const accountErrors = []

  // Validate amount
  const amountValidation = validateAmount(amountInput.value)
  if (!amountValidation.isValid) {
    amountErrors = amountValidation.errors
    isValid = false
  }

  // Validate account selection
  if (!accountSelect.value) {
    accountErrors.push("Please select a payout account.")
    isValid = false
  }

  // Display errors
  if (amountErrors.length > 0) {
    showFieldError("amount", amountErrors)
    amountInput.focus()
  }

  if (accountErrors.length > 0) {
    showFieldError("account", accountErrors)
    if (amountErrors.length === 0) {
      accountSelect.focus()
    }
  }

  return isValid
}

/**
 * Validates withdrawal amount
 * @param {string} value - Amount value to validate
 * @returns {object} Validation result with isValid and errors
 */
function validateAmount(value) {
  const errors = []
  const amount = Number.parseFloat(value)

  // Check if amount is provided and valid
  if (!value || isNaN(amount) || amount <= 0) {
    errors.push("Please enter a valid withdrawal amount.")
    return { isValid: false, errors }
  }

  // Check minimum amount
  if (
    typeof DJANGO_MIN_WITHDRAWAL_AMOUNT !== "undefined" &&
    DJANGO_MIN_WITHDRAWAL_AMOUNT > 0 &&
    amount < DJANGO_MIN_WITHDRAWAL_AMOUNT
  ) {
    errors.push(`Withdrawal amount must be at least Rs. ${DJANGO_MIN_WITHDRAWAL_AMOUNT.toFixed(2)}.`)
  }

  // Check maximum amount (available balance)
  if (
    typeof DJANGO_AVAILABLE_BALANCE !== "undefined" &&
    DJANGO_AVAILABLE_BALANCE >= 0 &&
    amount > DJANGO_AVAILABLE_BALANCE
  ) {
    errors.push(`Withdrawal amount cannot exceed your available balance of Rs. ${DJANGO_AVAILABLE_BALANCE.toFixed(2)}.`)
  }

  return { isValid: errors.length === 0, errors }
}

/**
 * Real-time validation for amount input
 */
function validateAmountInput() {
  const amountInput = document.getElementById("amount")
  const validation = validateAmount(amountInput.value)

  if (amountInput.value && !validation.isValid) {
    showFieldError("amount", validation.errors)
  } else {
    clearFieldError("amount")
  }
}

/**
 * Validation for account selection
 */
function validateAccountSelection() {
  const accountSelect = document.getElementById("withdrawal_account_id")

  if (accountSelect.value) {
    clearFieldError("account")
  }
}

// ============================================================================
// ERROR HANDLING AND DISPLAY
// ============================================================================

/**
 * Shows field-specific error messages
 * @param {string} fieldType - Type of field ('amount' or 'account')
 * @param {Array} errors - Array of error messages
 */
function showFieldError(fieldType, errors) {
  const errorDiv = document.getElementById(`${fieldType}Error`)
  const inputElement =
    fieldType === "amount" ? document.getElementById("amount") : document.getElementById("withdrawal_account_id")

  if (!errorDiv || !inputElement) return

  // Show error messages
  if (errors && errors.length > 0) {
    errorDiv.innerHTML =
      '<ul class="list-none p-0 m-0">' +
      errors
        .map(
          (msg) =>
            `<li class="mb-1 last:mb-0 flex items-start"><i class="fas fa-exclamation-circle mr-2 mt-0.5 text-red-500"></i>${msg}</li>`,
        )
        .join("") +
      "</ul>"
    errorDiv.classList.remove("hidden")

    // Add error styling to input
    inputElement.classList.remove("border-gray-300", "focus:border-audiox-blue", "focus:ring-audiox-blue")
    inputElement.classList.add("border-red-500", "focus:border-red-500", "focus:ring-red-500")
  }
}

/**
 * Clears field-specific error messages
 * @param {string} fieldType - Type of field ('amount' or 'account')
 */
function clearFieldError(fieldType) {
  const errorDiv = document.getElementById(`${fieldType}Error`)
  const inputElement =
    fieldType === "amount" ? document.getElementById("amount") : document.getElementById("withdrawal_account_id")

  if (!errorDiv || !inputElement) return

  // Hide error messages
  errorDiv.innerHTML = ""
  errorDiv.classList.add("hidden")

  // Remove error styling from input
  inputElement.classList.remove("border-red-500", "focus:border-red-500", "focus:ring-red-500")
  inputElement.classList.add("border-gray-300", "focus:border-audiox-blue", "focus:ring-audiox-blue")
}

/**
 * Clears all form errors
 */
function clearAllErrors() {
  clearFieldError("amount")
  clearFieldError("account")
}

// ============================================================================
// CONFIRMATION DIALOG
// ============================================================================

/**
 * Shows withdrawal confirmation dialog
 */
function showWithdrawalConfirmation() {
  const amountInput = document.getElementById("amount")
  const accountSelect = document.getElementById("withdrawal_account_id")

  const amount = Number.parseFloat(amountInput.value).toFixed(2)
  const accountText = accountSelect.options[accountSelect.selectedIndex].text

  const confirmationHtml = `
       <div class="text-center">
           <div class="mb-6">
               <div class="mx-auto w-16 h-16 bg-audiox-blue/10 rounded-full flex items-center justify-center mb-4">
                   <i class="fas fa-money-bill-wave text-2xl text-audiox-blue"></i>
               </div>
               <p class="text-lg text-gray-700 mb-4">
                   You are about to request a withdrawal of 
                   <strong class="text-audiox-blue font-bold text-xl">Rs. ${Number.parseFloat(amount).toLocaleString()}</strong>
               </p>
           </div>
           
           <div class="bg-gray-50 border border-gray-200 rounded-xl p-4 mb-6 text-left">
               <h4 class="font-semibold text-gray-800 mb-3 flex items-center">
                   <i class="fas fa-info-circle mr-2 text-audiox-blue"></i>
                   Withdrawal Details
               </h4>
               <div class="space-y-2 text-sm">
                   <div class="flex justify-between">
                       <span class="text-gray-600">Amount:</span>
                       <span class="font-semibold text-gray-900">Rs. ${Number.parseFloat(amount).toLocaleString()}</span>
                   </div>
                   <div class="flex justify-between">
                       <span class="text-gray-600">Payout to:</span>
                       <span class="font-medium text-gray-900 text-right max-w-xs truncate">${accountText}</span>
                   </div>
               </div>
           </div>
           
           <div class="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-left">
               <div class="flex items-start">
                   <i class="fas fa-exclamation-triangle text-yellow-600 mr-2 mt-0.5"></i>
                   <div class="text-sm text-yellow-800">
                       <p class="font-semibold mb-1">Important Notice:</p>
                       <ul class="text-xs space-y-1">
                           <li>• This action cannot be undone once submitted</li>
                           <li>• Processing may take 1-3 business days</li>
                           <li>• Ensure your account details are correct</li>
                       </ul>
                   </div>
               </div>
           </div>
       </div>
   `

  if (typeof Swal !== "undefined") {
    Swal.fire({
      title: "Confirm Withdrawal Request",
      html: confirmationHtml,
      icon: "question",
      iconColor: "#091e65",
      showCancelButton: true,
      confirmButtonText: '<i class="fas fa-paper-plane mr-2"></i>Submit Request',
      cancelButtonText: '<i class="fas fa-times mr-2"></i>Cancel',
      reverseButtons: true,
      customClass: {
        popup: "bg-white text-gray-700 rounded-2xl border border-gray-200 shadow-2xl",
        title: "text-gray-900 text-xl font-bold mb-4",
        htmlContainer: "text-sm mb-6",
        confirmButton:
          "bg-audiox-blue text-white rounded-xl px-6 py-3 text-sm font-semibold transition-all duration-150 ease-in-out shadow-lg hover:bg-audiox-blue/90 transform hover:scale-105",
        cancelButton:
          "bg-white text-gray-700 border border-gray-300 rounded-xl px-6 py-3 text-sm font-semibold transition-all duration-150 ease-in-out shadow-md hover:bg-gray-50 transform hover:scale-105",
        actions: "space-x-4 mt-6",
      },
      buttonsStyling: false,
    }).then((result) => {
      if (result.isConfirmed) {
        submitWithdrawalRequest()
      }
    })
  } else {
    console.error("SweetAlert2 is not loaded.")
  }
}

// ============================================================================
// FORM SUBMISSION
// ============================================================================

/**
 * Submits the withdrawal request
 */
function submitWithdrawalRequest() {
  const form = document.getElementById("requestWithdrawalForm")
  const submitButton = document.getElementById("submitWithdrawalBtn")

  if (!form) return

  isProcessing = true
  isFormSubmitting = true // Set form submission flag

  // Show loading state
  showLoadingOverlay("Processing withdrawal request...")

  // Update submit button
  if (submitButton) {
    submitButton.disabled = true
    submitButton.innerHTML = `
           <svg class="animate-spin h-5 w-5 mr-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
               <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
               <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 714 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
           </svg>
           Processing Request...
       `
  }

  // Submit form
  form.submit()
}

// ============================================================================
// KEYBOARD SHORTCUTS
// ============================================================================

/**
 * Initializes keyboard shortcuts
 */
function initializeKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Escape key to close any open modals
    if (e.key === "Escape" && Swal.isVisible()) {
      Swal.close()
    }

    // Ctrl/Cmd + Enter to submit form (if valid)
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      const form = document.getElementById("requestWithdrawalForm")
      if (form && !isProcessing) {
        e.preventDefault()
        form.dispatchEvent(new Event("submit"))
      }
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

  console.warn("⚠️ CSRF token not found")
  return ""
}

// ============================================================================
// ERROR HANDLING AND CLEANUP
// ============================================================================

// FIXED: Modified beforeunload event to not interfere with form submissions
window.addEventListener("beforeunload", (e) => {
  // Only show warning if processing but NOT submitting a form
  if (isProcessing && !isFormSubmitting) {
    e.preventDefault()
    e.returnValue = "A withdrawal request is being processed. Are you sure you want to leave?"
    return e.returnValue
  }
})

// Handle page visibility changes
document.addEventListener("visibilitychange", () => {
  if (document.hidden && isProcessing) {
    console.log("⚠️ Page hidden during withdrawal processing")
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

    // Reset submit button
    const submitButton = document.getElementById("submitWithdrawalBtn")
    if (submitButton) {
      submitButton.disabled = false
      submitButton.innerHTML = `
               <i class="fas fa-paper-plane text-lg"></i>
               Submit Withdrawal Request
           `
    }
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

console.log("💰 AudioX Creator Withdrawal Request - JavaScript loaded successfully")
