/**
 * ==================== AUDIOX HOMEPAGE JAVASCRIPT ====================
 *
 * This file contains all the JavaScript functionality for the AudioX homepage
 * including search filters, language selector, menu interactions, and modals.
 *
 * Author: AudioX Development Team
 * Version: 2.0
 * Last Updated: 2024
 */

document.addEventListener("DOMContentLoaded", () => {
  // ==================== INITIALIZATION ====================

  // Get Django context data
  const contextDataElement = document.getElementById("django-context-data")
  const djangoContext = contextDataElement ? JSON.parse(contextDataElement.textContent || "{}") : {}
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || ""

  // Search Filter State Management
  let currentFilters = {
    language: "",
    genre: "",
    creator: "",
    query: "",
  }

  // Available filter options
  const availableOptions = {
    genres: [],
    creators: [],
  }

  // Language-specific genre mappings
  const languageGenreMapping = {
    English: [
      "Fiction",
      "Mystery",
      "Thriller",
      "Science Fiction",
      "Fantasy",
      "Romance",
      "Biography",
      "History",
      "Self Help",
      "Business",
    ],
    Urdu: ["Novel Afsana", "Shayari", "Tareekh", "Safarnama", "Mazah", "Bachon Ka Adab", "Mazhabi Adab"],
    Punjabi: ["Qissa Lok", "Geet"],
    Sindhi: ["Lok Adab", "Shayari"],
  }

  // ==================== SWEETALERT CONFIGURATION ====================

  const Swal = window.Swal // SweetAlert
  const SwalStyled = Swal.mixin({
    customClass: {
      popup: "rounded-xl shadow-lg font-sans border border-gray-100 bg-white",
      title: "text-xl sm:text-2xl font-bold text-[#091e65] pt-6 px-6 pb-2 text-left",
      htmlContainer: "text-base text-gray-700 text-left px-6 pb-6 leading-relaxed",
      icon: "mt-6 mx-auto",
      confirmButton:
        "inline-flex items-center justify-center gap-2 rounded-lg bg-[#091e65] px-5 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-blue-900 focus:outline-none focus:ring-2 focus:ring-[#091e65] focus:ring-offset-2 transition duration-150 ease-in-out mx-1.5 mb-4",
      cancelButton:
        "inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-semibold text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-indigo-500 focus:ring-offset-2 transition duration-150 ease-in-out mx-1.5 mb-4",
      actions: "flex justify-end px-6 pb-2",
      loader: "border-[#091e65]",
    },
    buttonsStyling: false,
  })

  // Global alert function
  window.showCustomAlert = (title, message, icon = "info", confirmButtonText = "OK", customHtml = null) => {
    SwalStyled.fire({
      title: title,
      html: customHtml || `<p>${message}</p>`,
      icon: icon,
      confirmButtonText: confirmButtonText,
      customClass: {
        title: "text-xl sm:text-2xl font-bold text-[#091e65] pt-6 px-6 pb-2 text-center",
        htmlContainer: "text-base text-gray-700 text-center px-6 pb-6 leading-relaxed",
        icon: "mt-6 mx-auto mb-4",
      },
    })
  }

  // ==================== PREMIUM LANGUAGE SELECTOR ====================

  function initializeLanguageSelector() {
    const languageSelectorBtn = document.getElementById("language-selector-btn")
    const languageDropdown = document.getElementById("language-dropdown")
    const selectedLanguageText = document.getElementById("selected-language-text")
    const languageChevron = document.getElementById("language-chevron")
    const languageOptions = document.querySelectorAll(".language-option")

    if (!languageSelectorBtn || !languageDropdown) return

    // Set initial language based on current page
    function setInitialLanguage() {
      const path = window.location.pathname.toLowerCase()
      let currentLanguage = "English"

      if (path.startsWith("/urdu/")) {
        currentLanguage = "Urdu"
        selectedLanguageText.textContent = "اردو"
      } else if (path.startsWith("/punjabi/")) {
        currentLanguage = "Punjabi"
        selectedLanguageText.textContent = "پنجابی"
      } else if (path.startsWith("/sindhi/")) {
        currentLanguage = "Sindhi"
        selectedLanguageText.textContent = "سنڌي"
      } else {
        selectedLanguageText.textContent = "English"
      }

      // Update check marks
      languageOptions.forEach((option) => {
        const checkIcon = document.getElementById(`check-${option.dataset.language}`)
        if (checkIcon) {
          if (option.dataset.language === currentLanguage) {
            checkIcon.classList.remove("opacity-0")
            checkIcon.classList.add("opacity-100")
          } else {
            checkIcon.classList.remove("opacity-100")
            checkIcon.classList.add("opacity-0")
          }
        }
      })
    }

    // Toggle dropdown
    function toggleLanguageDropdown() {
      // Ensure side menu is closed first
      const slideMenu = document.getElementById("slide-menu")
      if (!slideMenu.classList.contains("-translate-x-full")) {
        return // Don't open language dropdown if side menu is open
      }

      const isVisible = !languageDropdown.classList.contains("opacity-0")

      if (isVisible) {
        hideLanguageDropdown()
      } else {
        showLanguageDropdown()
      }
    }

    // Show dropdown
    function showLanguageDropdown() {
      languageDropdown.classList.remove("opacity-0", "invisible", "scale-95")
      languageDropdown.classList.add("opacity-100", "visible", "scale-100")
      languageChevron.classList.add("rotate-180")
      languageSelectorBtn.setAttribute("aria-expanded", "true")
    }

    // Hide dropdown
    function hideLanguageDropdown() {
      languageDropdown.classList.remove("opacity-100", "visible", "scale-100")
      languageDropdown.classList.add("opacity-0", "invisible", "scale-95")
      languageChevron.classList.remove("rotate-180")
      languageSelectorBtn.setAttribute("aria-expanded", "false")
    }

    // Event listeners
    languageSelectorBtn.addEventListener("click", (e) => {
      e.stopPropagation()
      toggleLanguageDropdown()
    })

    // Language option clicks
    languageOptions.forEach((option) => {
      option.addEventListener("click", (e) => {
        e.preventDefault()
        const language = option.dataset.language
        const url = option.dataset.url

        // Update selected language text
        const languageTexts = {
          English: "English",
          Urdu: "اردو",
          Punjabi: "پنجابی",
          Sindhi: "سنڌي",
        }

        selectedLanguageText.textContent = languageTexts[language]

        // Update check marks
        languageOptions.forEach((opt) => {
          const checkIcon = document.getElementById(`check-${opt.dataset.language}`)
          if (checkIcon) {
            if (opt.dataset.language === language) {
              checkIcon.classList.remove("opacity-0")
              checkIcon.classList.add("opacity-100")
            } else {
              checkIcon.classList.remove("opacity-100")
              checkIcon.classList.add("opacity-0")
            }
          }
        })

        hideLanguageDropdown()

        // Navigate to selected language page
        window.location.href = url
      })
    })

    // Close dropdown when clicking outside - improve this section
    document.addEventListener("click", (e) => {
      // Only close language dropdown if click is not on side menu elements
      const slideMenu = document.getElementById("slide-menu")
      const menuBackdrop = document.getElementById("slide-menu-backdrop")
      if (
        !languageSelectorBtn.contains(e.target) &&
        !languageDropdown.contains(e.target) &&
        !slideMenu.contains(e.target) &&
        !menuBackdrop.contains(e.target)
      ) {
        hideLanguageDropdown()
      }
    })

    // Close dropdown on escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        hideLanguageDropdown()
      }
    })

    // Initialize language on page load
    setInitialLanguage()
  }

  // ==================== SEARCH FILTER FUNCTIONS ====================

  function updateActiveFilters() {
    const activeFiltersContainer = document.getElementById("active-filters")
    const mobileActiveFiltersContainer = document.getElementById("mobile-active-filters")
    const clearFiltersBtn = document.getElementById("clear-filters-btn")

    if (!activeFiltersContainer) return

    activeFiltersContainer.innerHTML = ""
    if (mobileActiveFiltersContainer) mobileActiveFiltersContainer.innerHTML = ""

    let hasActiveFilters = false

    // Add active filter tags
    Object.entries(currentFilters).forEach(([key, value]) => {
      if (value && key !== "query") {
        hasActiveFilters = true
        const filterTag = createFilterTag(key, value)
        activeFiltersContainer.appendChild(filterTag)

        if (mobileActiveFiltersContainer) {
          const mobileFilterTag = createFilterTag(key, value)
          mobileActiveFiltersContainer.appendChild(mobileFilterTag)
        }
      }
    })

    // Show/hide containers and clear button
    if (hasActiveFilters) {
      activeFiltersContainer.classList.remove("hidden")
      if (mobileActiveFiltersContainer) mobileActiveFiltersContainer.classList.remove("hidden")
      if (clearFiltersBtn) clearFiltersBtn.classList.remove("hidden")
    } else {
      activeFiltersContainer.classList.add("hidden")
      if (mobileActiveFiltersContainer) mobileActiveFiltersContainer.classList.add("hidden")
      if (clearFiltersBtn) clearFiltersBtn.classList.add("hidden")
    }

    // Update language button states
    updateLanguageButtonStates()
  }

  function createFilterTag(filterType, value) {
    const tag = document.createElement("span")
    tag.className = "inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-[#091e65] text-white rounded-full"

    const icon = getFilterIcon(filterType)
    tag.innerHTML = `
            <i class="${icon} text-xs"></i>
            <span>${value}</span>
            <button class="ml-1 hover:bg-white/20 rounded-full p-0.5 transition-colors" onclick="removeFilter('${filterType}')">
                <i class="fas fa-times text-xs"></i>
            </button>
        `

    return tag
  }

  function getFilterIcon(filterType) {
    const icons = {
      language: "fas fa-globe",
      genre: "fas fa-tags",
      creator: "fas fa-microphone",
    }
    return icons[filterType] || "fas fa-filter"
  }

  function updateLanguageButtonStates() {
    const languageButtons = document.querySelectorAll(".language-filter-btn, .language-filter-btn-mobile")
    languageButtons.forEach((btn) => {
      const language = btn.dataset.language
      if (currentFilters.language === language) {
        btn.classList.remove("bg-white", "border-gray-300", "text-gray-700")
        btn.classList.add("bg-[#091e65]", "text-white", "border-[#091e65]")
      } else {
        btn.classList.remove("bg-[#091e65]", "text-white", "border-[#091e65]")
        btn.classList.add("bg-white", "border-gray-300", "text-gray-700")
      }
    })
  }

  window.removeFilter = (filterType) => {
    currentFilters[filterType] = ""
    updateActiveFilters()

    // Clear genre if language is removed
    if (filterType === "language") {
      currentFilters.genre = ""
    }

    updateFilterDropdowns()
    performSearch()
  }

  function clearAllFilters() {
    currentFilters = {
      language: "",
      genre: "",
      creator: "",
      query: "",
    }

    // Clear search inputs
    const searchInputs = document.querySelectorAll("#search-input, #search-input-mobile")
    searchInputs.forEach((input) => (input.value = ""))

    updateActiveFilters()
    updateFilterDropdowns()

    // Redirect to home page to show all audiobooks
    window.location.href = "/"
  }

  async function loadFilterOptions() {
    try {
      const params = new URLSearchParams()
      if (currentFilters.language) params.append("language", currentFilters.language)
      if (currentFilters.genre) params.append("genre", currentFilters.genre)

      const response = await fetch(`/get-filter-options/?${params.toString()}`)
      if (response.ok) {
        const data = await response.json()
        availableOptions.creators = data.creators || []

        // Use language-specific genres if language is selected, otherwise use API response
        if (currentFilters.language && languageGenreMapping[currentFilters.language]) {
          availableOptions.genres = languageGenreMapping[currentFilters.language]
        } else {
          availableOptions.genres = data.genres || []
        }

        updateFilterDropdowns()
      } else {
        console.error("Failed to load filter options:", response.status)
        // Fallback to language-specific genres
        if (currentFilters.language && languageGenreMapping[currentFilters.language]) {
          availableOptions.genres = languageGenreMapping[currentFilters.language]
          updateFilterDropdowns()
        }
      }
    } catch (error) {
      console.error("Error loading filter options:", error)
      // Fallback to language-specific genres
      if (currentFilters.language && languageGenreMapping[currentFilters.language]) {
        availableOptions.genres = languageGenreMapping[currentFilters.language]
        updateFilterDropdowns()
      }
    }
  }

  function updateFilterDropdowns() {
    // Update genre options
    updateDropdownOptions("genre-options", availableOptions.genres, "genre")
    updateDropdownOptions("mobile-genre-options", availableOptions.genres, "genre", true)

    // Update creator options
    updateDropdownOptions("creator-options", availableOptions.creators, "creator")
    updateDropdownOptions("mobile-creator-options", availableOptions.creators, "creator", true)
  }

  function updateDropdownOptions(containerId, options, filterType, isMobile = false) {
    const container = document.getElementById(containerId)
    if (!container) return

    container.innerHTML = ""

    if (!options || options.length === 0) {
      const noOptionsElement = document.createElement("div")
      noOptionsElement.className = "text-xs text-gray-500 p-2 text-center"
      noOptionsElement.textContent = `No ${filterType}s available`
      container.appendChild(noOptionsElement)
      return
    }

    options.forEach((option) => {
      const optionElement = document.createElement(isMobile ? "label" : "button")

      if (isMobile) {
        optionElement.className = "flex items-center space-x-2 p-2 hover:bg-gray-50 rounded cursor-pointer"
        optionElement.innerHTML = `
                    <input type="radio" name="mobile-${filterType}" value="${option}" class="text-[#091e65] focus:ring-[#091e65]" ${currentFilters[filterType] === option ? "checked" : ""}>
                    <span class="text-sm text-gray-700">${option}</span>
                `

        optionElement.addEventListener("change", (e) => {
          if (e.target.checked) {
            currentFilters[filterType] = option
            updateActiveFilters()
          }
        })
      } else {
        optionElement.className =
          "block w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded transition-colors"
        optionElement.textContent = option

        optionElement.addEventListener("click", () => {
          currentFilters[filterType] = option
          updateActiveFilters()
          hideAllDropdowns()
          performSearch()
        })
      }

      container.appendChild(optionElement)
    })
  }

  function performSearch() {
    const params = new URLSearchParams()

    Object.entries(currentFilters).forEach(([key, value]) => {
      if (value) {
        if (key === "query") {
          params.append("q", value)
        } else {
          params.append(key, value)
        }
      }
    })

    const searchUrl = `/search/?${params.toString()}`
    window.location.href = searchUrl
  }

  function hideAllDropdowns() {
    const dropdowns = document.querySelectorAll('[id$="-dropdown"]')
    dropdowns.forEach((dropdown) => {
      dropdown.classList.add("hidden")
    })

    const dropdownBtns = document.querySelectorAll(".filter-dropdown-btn i:last-child")
    dropdownBtns.forEach((icon) => {
      icon.classList.remove("rotate-180")
    })
  }

  // ==================== MENU FUNCTIONALITY ====================

  function initializeMenus() {
    const menuToggle = document.getElementById("menu-toggle")
    const slideMenu = document.getElementById("slide-menu")
    const closeMenu = document.getElementById("close-menu")
    const menuBackdrop = document.getElementById("slide-menu-backdrop")

    function openSlideMenu() {
      if (!slideMenu || !menuBackdrop) return
      menuBackdrop.classList.remove("hidden", "pointer-events-none") // Add pointer-events-none here
      document.body.style.overflow = "hidden"
      requestAnimationFrame(() => {
        slideMenu.classList.remove("-translate-x-full")
        menuBackdrop.classList.remove("opacity-0")
        menuBackdrop.classList.add("opacity-100")
      })
    }

    function closeSlideMenu() {
      if (!slideMenu || !menuBackdrop) return
      slideMenu.classList.add("-translate-x-full")
      menuBackdrop.classList.remove("opacity-100")
      menuBackdrop.classList.add("opacity-0")
      setTimeout(() => {
        menuBackdrop.classList.add("hidden")
        menuBackdrop.classList.add("pointer-events-none") // Add this line
        document.body.style.overflow = ""
      }, 300)
    }

    if (menuToggle && slideMenu && closeMenu && menuBackdrop) {
      menuToggle.addEventListener("click", (e) => {
        e.stopPropagation()
        openSlideMenu()
      })
      closeMenu.addEventListener("click", closeSlideMenu)
      menuBackdrop.addEventListener("click", closeSlideMenu)
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !slideMenu.classList.contains("-translate-x-full")) {
          closeSlideMenu()
        }
      })
    }
  }

  // ==================== PROFILE DROPDOWN ====================

  function initializeProfileDropdown() {
    const profileDropdownToggle = document.getElementById("profile-dropdown-toggle")
    const profileDropdown = document.getElementById("profile-dropdown")

    function showProfileDropdown() {
      if (!profileDropdown || !profileDropdownToggle) return
      profileDropdown.classList.remove("hidden")
      profileDropdownToggle.setAttribute("aria-expanded", "true")
    }

    function hideProfileDropdown() {
      if (!profileDropdown || !profileDropdownToggle) return
      profileDropdown.classList.add("hidden")
      profileDropdownToggle.setAttribute("aria-expanded", "false")
    }

    if (profileDropdownToggle && profileDropdown) {
      profileDropdownToggle.addEventListener("click", (event) => {
        event.stopPropagation()
        const isExpanded = profileDropdownToggle.getAttribute("aria-expanded") === "true"
        if (isExpanded) {
          hideProfileDropdown()
        } else {
          showProfileDropdown()
        }
      })

      document.addEventListener("click", (event) => {
        if (
          profileDropdown &&
          !profileDropdown.classList.contains("hidden") &&
          !profileDropdown.contains(event.target) &&
          profileDropdownToggle &&
          !profileDropdownToggle.contains(event.target)
        ) {
          hideProfileDropdown()
        }
      })
    }
  }

  // ==================== SEARCH FUNCTIONALITY ====================

  function initializeSearch() {
    const performSearchQuery = (query, inputElement) => {
      currentFilters.query = query
      if (query || Object.values(currentFilters).some((v) => v)) {
        performSearch()
      } else {
        if (inputElement) inputElement.focus()
      }
    }

    const setupSearchButton = (buttonId, inputId) => {
      const btn = document.getElementById(buttonId)
      const input = document.getElementById(inputId)
      if (!btn || !input) return

      const performSearchAction = () => {
        const query = input.value.trim()
        performSearchQuery(query, input)
      }

      btn.addEventListener("click", performSearchAction)
      input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
          e.preventDefault()
          performSearchAction()
        }
      })
    }

    setupSearchButton("search-btn", "search-input")
    setupSearchButton("search-btn-mobile", "search-input-mobile")
  }

  // ==================== LANGUAGE FILTER BUTTONS ====================

  function initializeLanguageFilters() {
    const languageButtons = document.querySelectorAll(".language-filter-btn, .language-filter-btn-mobile")
    languageButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const language = btn.dataset.language
        if (currentFilters.language === language) {
          currentFilters.language = ""
          currentFilters.genre = "" // Clear genre when language is cleared
        } else {
          currentFilters.language = language
          currentFilters.genre = "" // Clear genre when language changes
        }
        updateActiveFilters()
        updateFilterDropdowns() // Update dropdowns immediately
        performSearch()
      })
    })
  }

  // ==================== FILTER DROPDOWNS ====================

  function initializeFilterDropdowns() {
    const filterDropdownBtns = document.querySelectorAll(".filter-dropdown-btn")
    filterDropdownBtns.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation()
        const dropdownId = btn.id.replace("-btn", "-dropdown")
        const dropdown = document.getElementById(dropdownId)
        const icon = btn.querySelector("i:last-child")

        if (dropdown) {
          const isHidden = dropdown.classList.contains("hidden")
          hideAllDropdowns()

          if (isHidden) {
            dropdown.classList.remove("hidden")
            icon.classList.add("rotate-180")
          }
        }
      })
    })

    // Clear filters button
    const clearFiltersBtn = document.getElementById("clear-filters-btn")
    if (clearFiltersBtn) {
      clearFiltersBtn.addEventListener("click", clearAllFilters)
    }

    // Close dropdowns when clicking outside
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".relative")) {
        hideAllDropdowns()
      }
    })
  }

  // ==================== MOBILE FILTERS MODAL ====================

  function initializeMobileFilters() {
    const mobileMoreFiltersBtn = document.getElementById("mobile-more-filters-btn")
    const mobileFiltersModal = document.getElementById("mobile-filters-modal")
    const mobileFiltersBackdrop = document.getElementById("mobile-filters-modal-backdrop")
    const closeMobileFilters = document.getElementById("close-mobile-filters")
    const mobileApplyFilters = document.getElementById("mobile-apply-filters")
    const mobileClearFilters = document.getElementById("mobile-clear-filters")

    function showMobileFiltersModal() {
      if (!mobileFiltersModal || !mobileFiltersBackdrop) return
      mobileFiltersBackdrop.classList.remove("hidden", "pointer-events-none")
      mobileFiltersModal.classList.remove("pointer-events-none")
      document.body.style.overflow = "hidden"

      requestAnimationFrame(() => {
        mobileFiltersBackdrop.classList.remove("opacity-0")
        mobileFiltersBackdrop.classList.add("opacity-100")
        mobileFiltersModal.classList.remove("translate-y-full")
      })
    }

    function hideMobileFiltersModal() {
      if (!mobileFiltersModal || !mobileFiltersBackdrop) return
      mobileFiltersModal.classList.add("translate-y-full")
      mobileFiltersBackdrop.classList.remove("opacity-100")
      mobileFiltersBackdrop.classList.add("opacity-0")

      setTimeout(() => {
        mobileFiltersBackdrop.classList.add("hidden", "pointer-events-none")
        mobileFiltersModal.classList.add("pointer-events-none")
        document.body.style.overflow = ""
      }, 300)
    }

    if (mobileMoreFiltersBtn) {
      mobileMoreFiltersBtn.addEventListener("click", showMobileFiltersModal)
    }

    if (closeMobileFilters) {
      closeMobileFilters.addEventListener("click", hideMobileFiltersModal)
    }

    if (mobileFiltersBackdrop) {
      mobileFiltersBackdrop.addEventListener("click", hideMobileFiltersModal)
    }

    if (mobileApplyFilters) {
      mobileApplyFilters.addEventListener("click", () => {
        hideMobileFiltersModal()
        performSearch()
      })
    }

    if (mobileClearFilters) {
      mobileClearFilters.addEventListener("click", () => {
        clearAllFilters()
        hideMobileFiltersModal()
      })
    }

    // Search input filtering for mobile
    const mobileCreatorSearch = document.getElementById("mobile-creator-search")
    if (mobileCreatorSearch) {
      mobileCreatorSearch.addEventListener("input", (e) => {
        filterMobileOptions("mobile-creator-options", e.target.value, availableOptions.creators, "creator")
      })
    }

    function filterMobileOptions(containerId, searchTerm, options, filterType) {
      const filteredOptions = options.filter((option) => option.toLowerCase().includes(searchTerm.toLowerCase()))
      updateDropdownOptions(containerId, filteredOptions, filterType, true)
    }
  }

  // ==================== VOICE SEARCH ====================

  function initializeVoiceSearch() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    let recognition

    if (SpeechRecognition) {
      recognition = new SpeechRecognition()
      recognition.continuous = false
      recognition.interimResults = false

      recognition.onstart = () => {
        SwalStyled.fire({
          title: "Listening...",
          imageUrl: "/static/img/microphone-icon.png",
          imageWidth: 60,
          imageHeight: 60,
          imageAlt: "Microphone listening",
          showConfirmButton: false,
          allowOutsideClick: false,
          customClass: {
            popup: "rounded-xl shadow-lg font-sans border border-gray-100 bg-white w-auto max-w-xs",
            title: "text-lg font-semibold text-[#091e65] pt-5 px-5 pb-4 text-center",
            image: "mx-auto mb-2 animate-pulse",
          },
          timer: 10000,
          timerProgressBar: true,
        })
      }

      recognition.onresult = (event) => {
        Swal.close()
        const transcript = event.results[0][0].transcript
        const currentSearchInputId = recognition.currentSearchInputId
        const searchInput = document.getElementById(currentSearchInputId)

        if (searchInput) {
          searchInput.value = transcript
          currentFilters.query = transcript
          performSearch()
        }
      }

      recognition.onerror = (event) => {
        Swal.close()
        let errorMessage = "Voice search error. Please try again."
        if (event.error === "no-speech") {
          errorMessage = "No speech detected. Please try again."
        } else if (event.error === "not-allowed") {
          errorMessage = "Microphone access denied. Please allow microphone access."
        }
        SwalStyled.fire({ title: "Voice Search Failed", text: errorMessage, icon: "error" })
      }

      recognition.onend = () => {
        if (Swal.isVisible()) {
          Swal.close()
        }
      }
    }

    const initiateVoiceSearch = (buttonId, inputId) => {
      const btn = document.getElementById(buttonId)
      const input = document.getElementById(inputId)

      if (!btn || !input) return

      btn.addEventListener("click", () => {
        if (!SpeechRecognition) {
          SwalStyled.fire({
            title: "Voice Search Not Supported",
            text: "Your browser does not support voice input.",
            icon: "warning",
          })
          return
        }

        recognition.currentSearchInputId = inputId
        recognition.lang = "en-US"

        try {
          recognition.start()
        } catch (e) {
          SwalStyled.fire({ title: "Voice Search Error", text: "Could not start voice input.", icon: "error" })
        }
      })
    }

    initiateVoiceSearch("voice-search-btn", "search-input")
    initiateVoiceSearch("voice-search-btn-mobile", "search-input-mobile")
  }

  // ==================== SUBMENU FUNCTIONALITY ====================

  function initializeSubmenus() {
    const submenuToggles = document.querySelectorAll("#slide-menu .submenu-toggle")
    submenuToggles.forEach((toggle) => {
      toggle.addEventListener("click", function (e) {
        e.preventDefault()
        const parentContainer = this.closest(".has-submenu-container")
        if (!parentContainer) return
        const submenu = parentContainer.querySelector(".submenu")
        const icon = this.querySelector(".submenu-icon")
        if (!submenu || !icon) return

        const isOpen = parentContainer.classList.contains("submenu-open")

        document.querySelectorAll("#slide-menu .has-submenu-container.submenu-open").forEach((openContainer) => {
          if (openContainer !== parentContainer) {
            openContainer.classList.remove("submenu-open")
            const otherSubmenu = openContainer.querySelector(".submenu")
            const otherIcon = openContainer.querySelector(".submenu-icon")
            if (otherSubmenu) {
              otherSubmenu.style.maxHeight = null
              otherSubmenu.classList.add("opacity-0")
            }
            if (otherIcon) otherIcon.classList.remove("rotate-180")
          }
        })

        if (isOpen) {
          parentContainer.classList.remove("submenu-open")
          submenu.style.maxHeight = null
          submenu.classList.add("opacity-0")
          icon.classList.remove("rotate-180")
        } else {
          parentContainer.classList.add("submenu-open")
          submenu.style.maxHeight = submenu.scrollHeight + "px"
          submenu.classList.remove("opacity-0")
          icon.classList.add("rotate-180")
        }
      })
    })
  }

  // ==================== CREATOR MODAL ====================

  function initializeCreatorModal() {
    const creatorModal = document.getElementById("creator-modal")
    const creatorModalBackdrop = document.getElementById("creator-modal-backdrop")
    const modalCloseBtns = creatorModal ? creatorModal.querySelectorAll(".modal-close-btn") : []

    function showCreatorModal() {
      if (!creatorModal || !creatorModalBackdrop) return
      creatorModalBackdrop.classList.remove("hidden")
      document.body.style.overflow = "hidden"
      creatorModal.classList.remove("pointer-events-none")
      requestAnimationFrame(() => {
        creatorModalBackdrop.classList.remove("opacity-0")
        creatorModalBackdrop.classList.add("opacity-100")
        creatorModal.classList.remove("opacity-0", "scale-95")
        creatorModal.classList.add("opacity-100", "scale-100")
      })
    }

    function hideCreatorModal() {
      if (!creatorModal || !creatorModalBackdrop) return
      creatorModal.classList.remove("opacity-100", "scale-100")
      creatorModal.classList.add("opacity-0", "scale-95")
      creatorModalBackdrop.classList.remove("opacity-100")
      creatorModalBackdrop.classList.add("opacity-0")
      setTimeout(() => {
        creatorModalBackdrop.classList.add("hidden")
        creatorModal.classList.add("pointer-events-none")
        document.body.style.overflow = ""
      }, 300)
    }

    const featureLoginRequiredButtons = document.querySelectorAll(".feature-login-required")
    featureLoginRequiredButtons.forEach((button) => {
      button.addEventListener("click", (e) => {
        e.preventDefault()
        showCreatorModal()
      })
    })

    modalCloseBtns.forEach((btn) => btn.addEventListener("click", hideCreatorModal))
    if (creatorModalBackdrop) creatorModalBackdrop.addEventListener("click", hideCreatorModal)
  }

  // ==================== CREATOR DASHBOARD FUNCTIONALITY ====================

  function initializeCreatorDashboard() {
    const sidemenuSwitchBtn = document.getElementById("sidemenu-switch-creator-btn")
    if (sidemenuSwitchBtn) {
      sidemenuSwitchBtn.addEventListener("click", (event) => {
        event.preventDefault()
        const dashboardUrl = "/creator/dashboard/"
        SwalStyled.fire({
          title: "Switching Modes",
          html: "Redirecting to Creator Dashboard...",
          timer: 1500,
          allowOutsideClick: false,
          didOpen: () => {
            Swal.showLoading()
          },
          timerProgressBar: true,
        }).then(() => {
          window.location.href = dashboardUrl
        })
      })
    }
  }

  // ==================== INITIALIZATION FUNCTIONS ====================

  function initializeFilters() {
    // Parse URL parameters to set initial filter state
    const urlParams = new URLSearchParams(window.location.search)
    currentFilters.query = urlParams.get("q") || ""
    currentFilters.language = urlParams.get("language") || ""
    currentFilters.genre = urlParams.get("genre") || ""
    currentFilters.creator = urlParams.get("creator") || ""

    // Update UI to reflect current filters
    updateActiveFilters()

    // Set search input values
    if (currentFilters.query) {
      const searchInputs = document.querySelectorAll("#search-input, #search-input-mobile")
      searchInputs.forEach((input) => (input.value = currentFilters.query))
    }

    // Initialize filter options
    updateFilterDropdowns() // Initialize with language-specific genres
    loadFilterOptions() // Then load from API
  }

  // ==================== MAIN INITIALIZATION ====================

  // Initialize all components
  initializeLanguageSelector()
  initializeMenus()
  initializeProfileDropdown()
  initializeSearch()
  initializeLanguageFilters()
  initializeFilterDropdowns()
  initializeMobileFilters()
  initializeVoiceSearch()
  initializeSubmenus()
  initializeCreatorModal()
  initializeCreatorDashboard()
  initializeFilters()

  console.log("AudioX Homepage JavaScript initialized successfully")
})
