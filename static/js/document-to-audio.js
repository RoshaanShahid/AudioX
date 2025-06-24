/**
 * ============================================================================
 * DOCUMENT TO AUDIO FEATURE - JAVASCRIPT MODULE
 * ============================================================================
 * Handles frontend interactions for document-to-audio conversion including:
 * - File upload and validation
 * - Form submission and AJAX handling
 * - Audio preview and download functionality
 * - UI state management and error handling
 *
 * Author: AudioX Development Team
 * Version: 2.0
 * Last Updated: 2024
 * ============================================================================
 */

// ============================================================================
// MODULE INITIALIZATION
// ============================================================================
document.addEventListener("DOMContentLoaded", () => {
  console.log("🎵 Document to Audio feature initialized")

  // ============================================================================
  // DOM ELEMENT REFERENCES
  // ============================================================================

  // Form elements
  const uploadForm = document.getElementById("uploadForm")
  const fileInput = document.querySelector('input[type="file"]')
  const fileUploadArea = document.getElementById("fileUploadArea")
  const languageSelect = document.querySelector('select[name="language"]')
  const narratorGenderSelect = document.querySelector('select[name="narrator_gender"]')
  const convertButton = document.getElementById("convertButton")

  // File selection elements
  const fileSelectionDisplay = document.getElementById("fileSelectionDisplay")
  const selectedFileName = document.getElementById("selectedFileName")
  const selectedFileSize = document.getElementById("selectedFileSize")
  const removeFileBtn = document.getElementById("removeFileBtn")

  // Language/gender control elements
  const narratorGenderContainer = document.getElementById("narratorGenderContainer")
  const narratorGenderRequiredAsterisk = document.getElementById("narratorGenderRequiredAsterisk")

  // Audio preview elements
  const audioPreviewSection = document.getElementById("audioPreviewSection")
  const audioPlayer = document.getElementById("audioPlayer")
  const customFilename = document.getElementById("customFilename")
  const downloadAudioBtn = document.getElementById("downloadAudioBtn")
  const generateAnotherBtn = document.getElementById("generateAnotherBtn")

  // Error handling elements
  const generalErrorMessage = document.getElementById("generalErrorMessage")
  const generalErrorTextContent = document.getElementById("generalErrorTextContent")

  // ============================================================================
  // APPLICATION STATE
  // ============================================================================

  let currentAudioData = null
  let originalFilename = ""

  // Configuration constants
  const LANGUAGES_REQUIRING_GENDER = ["English", "Urdu"]
  const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
  const ALLOWED_FILE_TYPES = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/jpg",
    "image/png",
  ]
  const ALLOWED_EXTENSIONS = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"]

  // ============================================================================
  // UTILITY FUNCTIONS
  // ============================================================================

  /**
   * Formats file size in human-readable format
   * @param {number} bytes - File size in bytes
   * @returns {string} Formatted file size
   */
  function formatFileSize(bytes) {
    if (bytes === 0) return "0 Bytes"
    const k = 1024
    const sizes = ["Bytes", "KB", "MB", "GB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return Number.parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i]
  }

  /**
   * Converts base64 string to Blob object
   * @param {string} base64 - Base64 encoded data
   * @param {string} mimeType - MIME type for the blob
   * @returns {Blob} Blob object
   */
  function base64ToBlob(base64, mimeType) {
    const byteCharacters = atob(base64)
    const byteNumbers = new Array(byteCharacters.length)

    for (let i = 0; i < byteCharacters.length; i++) {
      byteNumbers[i] = byteCharacters.charCodeAt(i)
    }

    const byteArray = new Uint8Array(byteNumbers)
    return new Blob([byteArray], { type: mimeType })
  }

  /**
   * Validates uploaded file type and size
   * @param {File} file - File object to validate
   * @returns {Object} Validation result with success flag and error message
   */
  function validateFile(file) {
    // Check file type
    const fileExtension = file.name.toLowerCase().substring(file.name.lastIndexOf("."))

    if (!ALLOWED_FILE_TYPES.includes(file.type) && !ALLOWED_EXTENSIONS.includes(fileExtension)) {
      return {
        success: false,
        error: `Unsupported file type: ${file.type || "unknown"}. Please upload PDF, DOC, DOCX, or image files.`,
      }
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE) {
      return {
        success: false,
        error: `File too large: ${formatFileSize(file.size)}. Maximum size is 10MB.`,
      }
    }

    return { success: true }
  }

  // ============================================================================
  // UI STATE MANAGEMENT FUNCTIONS
  // ============================================================================

  /**
   * Shows file selection information in the UI
   * @param {File} file - Selected file object
   */
  function showFileSelection(file) {
    if (selectedFileName && selectedFileSize && fileSelectionDisplay) {
      selectedFileName.textContent = file.name
      selectedFileSize.textContent = formatFileSize(file.size)
      fileSelectionDisplay.classList.remove("hidden")

      if (fileUploadArea) {
        fileUploadArea.style.display = "none"
      }
    }
  }

  /**
   * Hides file selection information from the UI
   */
  function hideFileSelection() {
    if (fileSelectionDisplay && fileUploadArea) {
      fileSelectionDisplay.classList.add("hidden")
      fileUploadArea.style.display = "block"
    }

    if (selectedFileName && selectedFileSize) {
      selectedFileName.textContent = "-"
      selectedFileSize.textContent = "-"
    }
  }

  /**
   * Toggles narrator gender field visibility based on selected language
   */
  function toggleNarratorGenderField() {
    if (!languageSelect || !narratorGenderContainer) {
      console.error("❌ Language select or narrator container not found")
      return
    }

    const selectedLanguage = languageSelect.value
    const requiresGender = LANGUAGES_REQUIRING_GENDER.includes(selectedLanguage)

    console.log(`🔄 Language changed to: ${selectedLanguage} | Requires gender: ${requiresGender}`)

    if (requiresGender) {
      console.log("👤 Showing narrator gender field")
      narratorGenderContainer.classList.remove("hidden")

      if (narratorGenderRequiredAsterisk) {
        narratorGenderRequiredAsterisk.classList.remove("hidden")
      }

      if (narratorGenderSelect) {
        narratorGenderSelect.setAttribute("required", "required")
      }
    } else {
      console.log("🚫 Hiding narrator gender field")
      narratorGenderContainer.classList.add("hidden")

      if (narratorGenderRequiredAsterisk) {
        narratorGenderRequiredAsterisk.classList.add("hidden")
      }

      if (narratorGenderSelect) {
        narratorGenderSelect.removeAttribute("required")
        narratorGenderSelect.value = "" // Clear selection
      }
    }
  }

  /**
   * Shows error message in the UI
   * @param {string} message - Error message to display
   */
  function showError(message) {
    if (generalErrorMessage && generalErrorTextContent) {
      generalErrorTextContent.textContent = message
      generalErrorMessage.classList.remove("hidden")
      generalErrorMessage.scrollIntoView({ behavior: "smooth", block: "center" })
    }
    console.error("❌ Error:", message)
  }

  /**
   * Hides error message from the UI
   */
  function hideError() {
    if (generalErrorMessage) {
      generalErrorMessage.classList.add("hidden")
    }
  }

  /**
   * Shows audio preview section with generated audio
   * @param {string} audioData - Base64 encoded audio data
   * @param {string} filename - Original filename for default naming
   */
  function showAudioPreview(audioData, filename) {
    currentAudioData = audioData
    originalFilename = filename

    // Convert base64 to blob and create URL
    const audioBlob = base64ToBlob(audioData, "audio/mpeg")
    const audioUrl = URL.createObjectURL(audioBlob)

    // Set audio source
    if (audioPlayer) {
      audioPlayer.src = audioUrl
    }

    // Set default filename
    if (customFilename) {
      customFilename.value = filename
    }

    // Show preview section with smooth animation
    if (audioPreviewSection) {
      audioPreviewSection.classList.remove("hidden")
      audioPreviewSection.scrollIntoView({ behavior: "smooth", block: "center" })
    }

    console.log("🎵 Audio preview displayed successfully")
  }

  /**
   * Hides audio preview section and cleans up resources
   */
  function hideAudioPreview() {
    if (audioPreviewSection) {
      audioPreviewSection.classList.add("hidden")
    }

    if (audioPlayer) {
      if (audioPlayer.src) {
        URL.revokeObjectURL(audioPlayer.src)
      }
      audioPlayer.src = ""
    }

    currentAudioData = null
    originalFilename = ""

    console.log("🔄 Audio preview hidden and resources cleaned")
  }

  /**
   * Updates button loading state
   * @param {boolean} isLoading - Whether button should show loading state
   */
  function updateButtonLoadingState(isLoading) {
    if (!convertButton) return

    const buttonText = convertButton.querySelector(".button-text")
    const buttonIcon = convertButton.querySelector(".button-icon")
    const buttonLoader = convertButton.querySelector(".button-loader")

    if (isLoading) {
      if (buttonText) buttonText.textContent = "Generating Premium Audio..."
      if (buttonIcon) buttonIcon.classList.add("hidden")
      if (buttonLoader) buttonLoader.classList.remove("hidden")
      convertButton.disabled = true
    } else {
      if (buttonText) buttonText.textContent = "Generate Premium Audio"
      if (buttonIcon) buttonIcon.classList.remove("hidden")
      if (buttonLoader) buttonLoader.classList.add("hidden")
      convertButton.disabled = false
    }
  }

  /**
   * Downloads the generated audio file
   */
  function downloadAudio() {
    if (!currentAudioData) {
      showError("No audio data available for download.")
      return
    }

    const filename = customFilename.value.trim() || originalFilename
    const audioBlob = base64ToBlob(currentAudioData, "audio/mpeg")
    const url = URL.createObjectURL(audioBlob)

    // Create temporary download link
    const downloadLink = document.createElement("a")
    downloadLink.href = url
    downloadLink.download = `${filename}.mp3`
    document.body.appendChild(downloadLink)
    downloadLink.click()
    document.body.removeChild(downloadLink)

    // Cleanup
    URL.revokeObjectURL(url)

    console.log(`📥 Audio downloaded: ${filename}.mp3`)
  }

  /**
   * Resets the entire form to initial state
   */
  function resetForm() {
    if (uploadForm) {
      uploadForm.reset()
    }

    hideFileSelection()
    hideAudioPreview()
    hideError()
    toggleNarratorGenderField()
    updateButtonLoadingState(false)

    console.log("🔄 Form reset to initial state")
  }

  // ============================================================================
  // FORM VALIDATION FUNCTIONS
  // ============================================================================

  /**
   * Validates form data before submission
   * @returns {Object} Validation result with success flag and error message
   */
  function validateForm() {
    // Check file selection
    if (!fileInput || !fileInput.files[0]) {
      return {
        success: false,
        error: "Please select a document file to convert.",
      }
    }

    // Check language selection
    if (!languageSelect || !languageSelect.value) {
      return {
        success: false,
        error: "Please select a language for the audio.",
      }
    }

    // Check narrator gender if required
    const selectedLanguage = languageSelect.value
    if (LANGUAGES_REQUIRING_GENDER.includes(selectedLanguage)) {
      if (!narratorGenderSelect || !narratorGenderSelect.value) {
        return {
          success: false,
          error: "Please select a narrator voice for the chosen language.",
        }
      }
    }

    return { success: true }
  }

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  /**
   * Handles file input change events
   * @param {Event} event - File input change event
   */
  function handleFileInputChange(event) {
    console.log("📁 File input changed")
    const file = event.target.files[0]

    if (file) {
      console.log(`📄 File selected: ${file.name} (${formatFileSize(file.size)}, ${file.type})`)

      // Validate file
      const validation = validateFile(file)
      if (!validation.success) {
        showError(validation.error)
        fileInput.value = ""
        hideFileSelection()
        return
      }

      showFileSelection(file)
      hideError()
    } else {
      console.log("❌ No file selected")
      hideFileSelection()
    }
  }

  /**
   * Handles form submission
   * @param {Event} event - Form submit event
   */
  function handleFormSubmit(event) {
    event.preventDefault() // Prevent default form submission
    console.log("🚀 Form submission started")

    hideError()

    // Validate form
    const validation = validateForm()
    if (!validation.success) {
      showError(validation.error)
      return
    }

    // Show loading state
    updateButtonLoadingState(true)

    // Create FormData for AJAX submission
    const formData = new FormData(uploadForm)

    // Make AJAX request
    fetch(uploadForm.action, {
      method: "POST",
      body: formData,
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value,
      },
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          console.log("✅ Audio generation successful")
          showAudioPreview(data.audio_data, data.original_filename)
        } else {
          console.error("❌ Audio generation failed:", data.error)
          showError(data.error || "An error occurred while generating audio.")
        }
      })
      .catch((error) => {
        console.error("🌐 Network error:", error)
        showError("Network error occurred. Please check your connection and try again.")
      })
      .finally(() => {
        updateButtonLoadingState(false)
      })

    console.log("📤 AJAX request sent")
  }

  /**
   * Handles drag and drop events
   * @param {Event} event - Drag/drop event
   */
  function handleDragDrop(event) {
    const dataTransfer = event.dataTransfer
    const files = dataTransfer.files

    if (files.length > 0 && fileInput) {
      fileInput.files = files
      const changeEvent = new Event("change", { bubbles: true })
      fileInput.dispatchEvent(changeEvent)
    }
  }

  // ============================================================================
  // EVENT LISTENERS SETUP
  // ============================================================================

  // Language selection change
  if (languageSelect) {
    languageSelect.addEventListener("change", toggleNarratorGenderField)
    toggleNarratorGenderField() // Check initial state
  }

  // File input change
  if (fileInput) {
    fileInput.addEventListener("change", handleFileInputChange)
  }

  // File upload area click
  if (fileUploadArea && fileInput) {
    fileUploadArea.addEventListener("click", () => {
      fileInput.click()
    })
  }

  // Remove file button
  if (removeFileBtn && fileInput) {
    removeFileBtn.addEventListener("click", (e) => {
      e.preventDefault()
      e.stopPropagation()
      console.log("🗑️ Remove file button clicked")
      fileInput.value = ""
      hideFileSelection()
    })
  }

  // Form submission
  if (uploadForm) {
    uploadForm.addEventListener("submit", handleFormSubmit)
  }

  // Download audio button
  if (downloadAudioBtn) {
    downloadAudioBtn.addEventListener("click", downloadAudio)
  }

  // Generate another button
  if (generateAnotherBtn) {
    generateAnotherBtn.addEventListener("click", resetForm)
  }

  // Drag and drop functionality
  if (fileUploadArea) {
    // Prevent default drag behaviors
    ;["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
      fileUploadArea.addEventListener(
        eventName,
        (e) => {
          e.preventDefault()
          e.stopPropagation()
        },
        false,
      )
    })

    // Highlight drop area when dragging over
    ;["dragenter", "dragover"].forEach((eventName) => {
      fileUploadArea.addEventListener(
        eventName,
        () => {
          fileUploadArea.classList.add("border-blue-900", "bg-blue-100")
        },
        false,
      )
    })

    // Remove highlight when dragging leaves
    ;["dragleave", "drop"].forEach((eventName) => {
      fileUploadArea.addEventListener(
        eventName,
        () => {
          fileUploadArea.classList.remove("border-blue-900", "bg-blue-100")
        },
        false,
      )
    })

    // Handle file drop
    fileUploadArea.addEventListener("drop", handleDragDrop, false)
  }

  // ============================================================================
  // INITIALIZATION COMPLETE
  // ============================================================================

  console.log("✅ Document to Audio JavaScript initialization complete")
  console.log("🎯 Ready for premium document-to-audio conversion")
})

/**
 * ============================================================================
 * END OF MODULE
 * ============================================================================
 */
