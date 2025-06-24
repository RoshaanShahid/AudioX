/**
 * AudioX Creator Profile Management - Interactive Form Handler
 *
 * This script manages the creator profile update form with features including:
 * - Profile picture upload, preview, and removal
 * - Form validation and submission handling
 * - Name change confirmation modal with 60-day lock policy
 * - File upload validation (size, type)
 * - Dynamic UI updates and transitions
 * - Error handling and user feedback
 */

document.addEventListener("DOMContentLoaded", () => {
  // ============================================================================
  // CONSTANTS AND CONFIGURATION
  // ============================================================================

  const FILE_CONSTRAINTS = {
    MAX_SIZE: 2 * 1024 * 1024, // 2MB in bytes
    ALLOWED_TYPES: ["image/jpeg", "image/jpg", "image/png"],
    ALLOWED_EXTENSIONS: [".jpg", ".jpeg", ".png"],
  }

  const MODAL_TRANSITION_DURATION = 300 // milliseconds
  const FORM_SUBMIT_DELAY = 50 // milliseconds

  // ============================================================================
  // DOM ELEMENT REFERENCES
  // ============================================================================

  // Form and core elements
  const form = document.getElementById("update-profile-form")
  const fileInput = document.getElementById("creator_profile_pic_input")
  const profilePicPreview = document.getElementById("profile-pic-preview")
  const profilePicPlaceholder = document.getElementById("profile-pic-placeholder")
  const removePicInput = document.getElementById("remove_profile_pic")
  const previewContainer = document.getElementById("profile-pic-preview-container")

  // Name input fields and their initial values
  const creatorNameInput = document.getElementById("creator_name")
  const uniqueNameInput = document.getElementById("creator_unique_name")
  const initialCreatorName = creatorNameInput?.dataset.initialValue || ""
  const initialUniqueName = uniqueNameInput?.dataset.initialValue || ""

  // Modal elements
  const modal = document.getElementById("confirmation-modal")
  const modalPanel = modal?.querySelector(".relative")
  const modalMessage = document.getElementById("modal-message")
  const confirmButton = document.getElementById("confirm-button")
  const cancelButton = document.getElementById("cancel-button")

  // State management
  let removePicBtn = document.getElementById("remove-pic-btn")
  let nameChangeConfirmed = false

  // ============================================================================
  // UTILITY FUNCTIONS
  // ============================================================================

  /**
   * Validate file type and size
   * @param {File} file - The file to validate
   * @returns {Object} Validation result with isValid and error message
   */
  function validateFile(file) {
    if (!file) {
      return { isValid: false, error: "No file selected" }
    }

    // Check file type
    if (!FILE_CONSTRAINTS.ALLOWED_TYPES.includes(file.type)) {
      return {
        isValid: false,
        error: `Invalid file type. Please select a ${FILE_CONSTRAINTS.ALLOWED_EXTENSIONS.join(", ")} file.`,
      }
    }

    // Check file size
    if (file.size > FILE_CONSTRAINTS.MAX_SIZE) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(2)
      return {
        isValid: false,
        error: `File size (${sizeMB}MB) exceeds the 2MB limit.`,
      }
    }

    return { isValid: true, error: null }
  }

  /**
   * Show user-friendly error message
   * @param {string} message - Error message to display
   */
  function showErrorMessage(message) {
    // Create a temporary error notification
    const errorDiv = document.createElement("div")
    errorDiv.className =
      "fixed top-4 right-4 bg-red-50 border-2 border-red-200 text-red-800 px-6 py-4 rounded-2xl shadow-xl z-50 max-w-md"
    errorDiv.innerHTML = `
            <div class="flex items-start gap-3">
                <div class="w-6 h-6 bg-red-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-exclamation-circle text-red-600 text-xs"></i>
                </div>
                <div>
                    <p class="font-semibold text-sm">Upload Error</p>
                    <p class="text-sm mt-1">${message}</p>
                </div>
            </div>
        `

    document.body.appendChild(errorDiv)

    // Remove after 5 seconds
    setTimeout(() => {
      if (errorDiv.parentNode) {
        errorDiv.remove()
      }
    }, 5000)
  }

  /**
   * Update submit button state
   * @param {boolean} isLoading - Whether to show loading state
   */
  function updateSubmitButton(isLoading) {
    const submitButton = form?.querySelector('button[type="submit"]')
    if (!submitButton) return

    if (isLoading) {
      submitButton.innerHTML = '<i class="fas fa-spinner fa-spin text-lg mr-3"></i>Saving Changes...'
      submitButton.disabled = true
      submitButton.classList.add("opacity-75", "cursor-not-allowed")
    } else {
      submitButton.innerHTML = '<i class="fas fa-save text-lg mr-3"></i>Save Changes'
      submitButton.disabled = false
      submitButton.classList.remove("opacity-75", "cursor-not-allowed")
    }
  }

  // ============================================================================
  // MODAL MANAGEMENT FUNCTIONS
  // ============================================================================

  /**
   * Show the confirmation modal with smooth transition
   */
  function showModal() {
    if (!modal || !modalPanel) return

    modal.classList.remove("hidden")
    modal.classList.add("flex")

    // Force reflow to ensure transition plays
    void modalPanel.offsetWidth
    modalPanel.dataset.active = "true"
  }

  /**
   * Hide the confirmation modal with smooth transition
   */
  function hideModal() {
    if (!modal || !modalPanel) return

    delete modalPanel.dataset.active

    // Fallback timeout in case transitionend doesn't fire
    const timeoutId = setTimeout(() => {
      if (!modal.classList.contains("hidden")) {
        modal.classList.add("hidden")
        modal.classList.remove("flex")
      }
    }, MODAL_TRANSITION_DURATION + 50)

    // Listen for transition end
    modalPanel.addEventListener(
      "transitionend",
      () => {
        clearTimeout(timeoutId)
        if (!modalPanel.dataset.active) {
          modal.classList.add("hidden")
          modal.classList.remove("flex")
        }
      },
      { once: true },
    )
  }

  // ============================================================================
  // PROFILE PICTURE MANAGEMENT
  // ============================================================================

  /**
   * Update the visibility of the remove picture button
   */
  function updateRemoveButtonVisibility() {
    removePicBtn = document.getElementById("remove-pic-btn")
    if (!removePicBtn) return

    const hasImage =
      profilePicPreview &&
      !profilePicPreview.classList.contains("hidden") &&
      profilePicPreview.src &&
      !profilePicPreview.src.endsWith("/")

    removePicBtn.classList.toggle("hidden", !hasImage)
  }

  /**
   * Handle profile picture file selection
   */
  function handleFileSelection(event) {
    const file = event.target.files[0]

    if (!file) {
      return
    }

    const validation = validateFile(file)
    if (!validation.isValid) {
      showErrorMessage(validation.error)
      fileInput.value = ""
      return
    }

    const reader = new FileReader()
    reader.onload = (e) => {
      // Update preview image
      if (profilePicPreview) {
        profilePicPreview.src = e.target.result
        profilePicPreview.classList.remove("hidden")
      }

      // Hide placeholder
      if (profilePicPlaceholder) {
        profilePicPlaceholder.classList.add("hidden")
      }

      // Update form state
      if (removePicInput) {
        removePicInput.value = "0"
      }

      updateRemoveButtonVisibility()
      addRemoveListener()
    }

    reader.onerror = () => {
      showErrorMessage("Failed to read the selected file. Please try again.")
      fileInput.value = ""
    }

    reader.readAsDataURL(file)
  }

  /**
   * Add event listener to the remove picture button
   * Clones the button to remove any existing listeners
   */
  function addRemoveListener() {
    removePicBtn = document.getElementById("remove-pic-btn")
    if (!removePicBtn) return

    // Clone button to remove old listeners
    const newBtn = removePicBtn.cloneNode(true)
    removePicBtn.parentNode.replaceChild(newBtn, removePicBtn)
    removePicBtn = newBtn

    removePicBtn.addEventListener("click", () => {
      // Clear preview image
      if (profilePicPreview) {
        profilePicPreview.src = ""
        profilePicPreview.classList.add("hidden")
      }

      // Show placeholder
      if (profilePicPlaceholder) {
        profilePicPlaceholder.classList.remove("hidden")
      }

      // Clear file input and set removal flag
      if (fileInput) fileInput.value = ""
      if (removePicInput) removePicInput.value = "1"

      updateRemoveButtonVisibility()
    })
  }

  // ============================================================================
  // FORM SUBMISSION HANDLING
  // ============================================================================

  /**
   * Generate modal message for name changes
   * @param {boolean} nameChanged - Whether display name changed
   * @param {boolean} uniqueNameChanged - Whether unique name changed
   * @param {string} currentCreatorName - New display name
   * @param {string} currentUniqueName - New unique name
   * @returns {string} HTML message for modal
   */
  function generateModalMessage(nameChanged, uniqueNameChanged, currentCreatorName, currentUniqueName) {
    let message = `
            <div class="mb-4">
                <h4 class="font-bold text-slate-900 mb-3">Please confirm the following changes:</h4>
            </div>
            <div class="space-y-4">
        `

    if (nameChanged) {
      message += `
                <div class="bg-slate-50 border-2 border-slate-200 rounded-xl p-4">
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                            <i class="fas fa-user text-blue-600"></i>
                        </div>
                        <div class="flex-grow">
                            <p class="font-semibold text-slate-900 mb-2">Display Name Change</p>
                            <div class="text-sm">
                                <p class="text-slate-600">From: <span class="font-mono bg-slate-200 px-2 py-1 rounded">${initialCreatorName || "(empty)"}</span></p>
                                <p class="text-slate-600 mt-1">To: <span class="font-mono bg-[#091e65] text-white px-2 py-1 rounded font-semibold">${currentCreatorName}</span></p>
                            </div>
                        </div>
                    </div>
                </div>
            `
    }

    if (uniqueNameChanged) {
      message += `
                <div class="bg-slate-50 border-2 border-slate-200 rounded-xl p-4">
                    <div class="flex items-start gap-3">
                        <div class="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center flex-shrink-0">
                            <i class="fas fa-at text-purple-600"></i>
                        </div>
                        <div class="flex-grow">
                            <p class="font-semibold text-slate-900 mb-2">Unique Handle Change</p>
                            <div class="text-sm">
                                <p class="text-slate-600">From: <span class="font-mono bg-slate-200 px-2 py-1 rounded">@${initialUniqueName || "(empty)"}</span></p>
                                <p class="text-slate-600 mt-1">To: <span class="font-mono bg-[#091e65] text-white px-2 py-1 rounded font-semibold">@${currentUniqueName}</span></p>
                            </div>
                        </div>
                    </div>
                </div>
            `
    }

    message += "</div>"
    return message
  }

  /**
   * Handle form submission with name change validation
   */
  function handleFormSubmission(event) {
    if (!creatorNameInput || !uniqueNameInput) return

    const currentCreatorName = creatorNameInput.value.trim()
    const currentUniqueName = uniqueNameInput.value.trim()

    // Check for changes
    const nameChanged = initialCreatorName !== currentCreatorName && !creatorNameInput.readOnly
    const uniqueNameChanged = initialUniqueName !== currentUniqueName && !uniqueNameInput.readOnly

    // If changes detected and not yet confirmed, show modal
    if ((nameChanged || uniqueNameChanged) && !nameChangeConfirmed) {
      event.preventDefault()

      const message = generateModalMessage(nameChanged, uniqueNameChanged, currentCreatorName, currentUniqueName)

      if (modalMessage) {
        modalMessage.innerHTML = message
      }

      showModal()
    } else {
      // Proceed with submission
      nameChangeConfirmed = false
      updateSubmitButton(true)
    }
  }

  // ============================================================================
  // EVENT LISTENERS SETUP
  // ============================================================================

  /**
   * Initialize all event listeners
   */
  function initializeEventListeners() {
    // Profile picture file input
    if (fileInput) {
      fileInput.addEventListener("change", handleFileSelection)
    }

    // Form submission
    if (form) {
      form.addEventListener("submit", handleFormSubmission)
    }

    // Modal confirm button
    if (confirmButton) {
      confirmButton.addEventListener("click", () => {
        nameChangeConfirmed = true
        hideModal()
        updateSubmitButton(true)

        // Submit form after short delay for UI updates
        setTimeout(() => {
          if (form) form.submit()
        }, FORM_SUBMIT_DELAY)
      })
    }

    // Modal cancel button
    if (cancelButton) {
      cancelButton.addEventListener("click", () => {
        hideModal()
        nameChangeConfirmed = false
      })
    }

    // Modal backdrop click
    if (modal) {
      modal.addEventListener("click", (event) => {
        if (event.target === modal) {
          hideModal()
          nameChangeConfirmed = false
        }
      })
    }

    // Escape key to close modal
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && modal && !modal.classList.contains("hidden")) {
        hideModal()
        nameChangeConfirmed = false
      }
    })
  }

  // ============================================================================
  // INITIALIZATION
  // ============================================================================

  /**
   * Initialize the profile management system
   */
  function initializeProfile() {
    // Setup initial state
    updateRemoveButtonVisibility()
    addRemoveListener()

    // Initialize event listeners
    initializeEventListeners()

    console.log("✅ Creator profile management initialized successfully")
  }

  // ============================================================================
  // ERROR HANDLING
  // ============================================================================

  /**
   * Global error handler for profile-specific errors
   */
  window.addEventListener("error", (event) => {
    if (event.filename && event.filename.includes("creator_profile")) {
      console.error("Profile Management Error:", {
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

  // Initialize profile management
  initializeProfile()

  console.log("🚀 Creator profile script loaded")
})
