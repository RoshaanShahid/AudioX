const audioPlayer = document.getElementById("audioPlayer")
const bottomPlayerBar = document.getElementById("bottom-player-bar")
const playerCoverImage = document.getElementById("player-cover-image")
const playerEpisodeNumber = document.getElementById("player-episode-number")
const playerEpisodeTitle = document.getElementById("player-episode-title")
const playerPlayPauseButton = document.getElementById("player-play-pause-button")
const playerPlayIcon = document.getElementById("player-play-icon")
const playerPauseIcon = document.getElementById("player-pause-icon")
const playerPrevButton = document.getElementById("player-prev-button")
const playerNextButton = document.getElementById("player-next-button")
const playerCurrentTime = document.getElementById("player-current-time")
const playerDuration = document.getElementById("player-duration")
const playerSeekBar = document.getElementById("player-seek-bar")
const playerSpeedButton = document.getElementById("player-speed-button")
const mainCoverImageElement = document.getElementById("main-cover-image")
const placeholderCoverSrc = "https://placehold.co/80x80/09065E/FFFFFF?text=N/A&font=sans"

const chapterItems = document.querySelectorAll(".chapter-item")
let currentChapterIndex = -1
let currentlyPlayingListItemButton = null

const playbackSpeeds = [1, 1.5, 2, 0.75]
let currentSpeedIndex = 0
const THEME_COLOR = "#DC2626"

const chapterClipEditorArea = document.getElementById("chapter-clip-editor-area")
const clipEditorChapterTitle = document.getElementById("clip-editor-chapter-title")
const closeClipEditorBtn = document.getElementById("close-clip-editor-btn")
const clipEditorPlayer = document.getElementById("clip-editor-player")
const setStartTimeBtn = document.getElementById("set-start-time-btn")
const clipEditorStartTimeDisplay = document.getElementById("clip-editor-start-time-display")
const setEndTimeBtn = document.getElementById("set-end-time-btn")
const clipEditorEndTimeDisplay = document.getElementById("clip-editor-end-time-display")
const generateClipBtnInline = document.getElementById("generate-clip-btn-inline")
const clipEditorStatus = document.getElementById("clip-editor-status")
const generatedClipAreaInline = document.getElementById("generated-clip-area-inline")
const generatedClipPlayerInline = document.getElementById("generated-clip-player-inline")
const downloadGeneratedClipLinkInline = document.getElementById("download-generated-clip-link-inline")
const shareGeneratedClipBtnInline = document.getElementById("share-generated-clip-btn-inline")

let currentChapterDataForClipping = null
let selectedClipStartTime = 0.0
let selectedClipEndTime = 0.0

const shareButton = document.getElementById("share-button")

let lastProgressUpdateTime = 0
const progressUpdateInterval = 5000

const purchaseButton = document.getElementById("purchase-button")
let stripe = null

let isResumingPlayback = false
let expectedResumePosition = 0
let resumeInitiatedTimestamp = 0

let pageContext = {}
let listeningHistory = {}

// Initialize pageContext and user subscription type
try {
  const contextElement = document.getElementById("page-context-data-detail")
  if (contextElement && contextElement.textContent) {
    pageContext = JSON.parse(contextElement.textContent)
    listeningHistory = JSON.parse(document.getElementById("listening-history-data").textContent || "{}")
  } else {
    pageContext = {}
  }

  // Ensure userSubscriptionType is properly set
  pageContext.userSubscriptionType = pageContext.userSubscriptionType || "FR" // Default to FREE
  pageContext.subscriptionUrl = pageContext.subscriptionUrl || "/subscription/"

  pageContext.generateAudioClipUrl = pageContext.generateAudioClipUrl || "/api/clip/generate/"
  if (
    pageContext.audiobookId &&
    pageContext.audiobookId !== "0" &&
    (!pageContext.getAiSummaryUrl || pageContext.getAiSummaryUrl.includes("/0/"))
  ) {
    pageContext.getAiSummaryUrl = `/audiobook/${pageContext.audiobookId}/get-ai-summary/`
  }
  pageContext.updateListeningProgressUrl =
    pageContext.updateListeningProgressUrl || "URL_NOT_DEFINED_update_listening_progress"
  if (!pageContext.csrfToken) {
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]')
    pageContext.csrfToken = csrfInput ? csrfInput.value : ""
    if (!pageContext.csrfToken) console.error("CRITICAL: CSRF token is missing.")
  }
  pageContext.isAuthenticated = pageContext.isAuthenticated || false
  pageContext.audiobookTitle = pageContext.audiobookTitle || "This Audiobook"

  pageContext.stripePublishableKey = pageContext.stripePublishableKey || null
  pageContext.createCheckoutSessionUrl = pageContext.createCheckoutSessionUrl || null
  pageContext.audiobookPrice = pageContext.audiobookPrice || "0.00"
  pageContext.checkCoinEligibilityUrl =
    pageContext.checkCoinEligibilityUrl || `/purchase/coins/check/${pageContext.audiobookSlug}/`
  pageContext.purchaseWithCoinsUrl = pageContext.purchaseWithCoinsUrl || "/purchase/coins/purchase/"
  pageContext.recordVisitUrl = pageContext.recordVisitUrl || "/ajax/record-audiobook-visit/"
  pageContext.buyCoinsUrl = pageContext.buyCoinsUrl || "/buycoins/"

  pageContext.unlockChapterUrl = pageContext.unlockChapterUrl || "/unlock-chapter-with-coins/"
} catch (e) {
  console.error("Error parsing page context data:", e, ". Using fallback defaults for all context properties.")
  pageContext = {
    isAuthenticated: false,
    audiobookId: null,
    audiobookSlug: null,
    audiobookTitle: "This Audiobook",
    audiobookAuthor: "Unknown Author",
    audiobookLanguage: "N/A",
    audiobookGenre: "N/A",
    isCreatorBook: false,
    userSubscriptionType: "FR", // Default to FREE
    subscriptionUrl: "/subscription/",
    csrfToken: document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "",
    addReviewUrl: "#error-parsing-context",
    addToLibraryApiUrl: "#error-parsing-context",
    myLibraryUrl: "/",
    loginUrl: "/login/",
    getAiSummaryUrl: `/audiobook/0/get-ai-summary/`,
    updateListeningProgressUrl: "URL_NOT_DEFINED_update_listening_progress",
    postChapterCommentUrlBase: "URL_NOT_DEFINED_post_chapter_comment",
    getChapterCommentsUrlBase: "URL_NOT_DEFINED_get_chapter_comments",
    generateAudioClipUrl: "/api/clip/generate/",
    userId: null,
    userFullName: null,
    userProfilePicUrl: null,
    stripePublishableKey: null,
    createCheckoutSessionUrl: null,
    audiobookPrice: "0.00",
    checkCoinEligibilityUrl: `/purchase/coins/check/SLUG/`,
    purchaseWithCoinsUrl: "/purchase/coins/purchase/",
    recordVisitUrl: "/ajax/record-audiobook-visit/",
    buyCoinsUrl: "/buy-coins/",
    unlockChapterUrl: "/unlock-chapter-with-coins/",
    is_in_library: false,
  }
}

function formatTime(seconds) {
  const roundedSeconds = Math.floor(seconds)
  if (isNaN(roundedSeconds) || roundedSeconds < 0) return "0:00"
  const minutes = Math.floor(roundedSeconds / 60)
  const secs = Math.floor(roundedSeconds % 60)
  return `${minutes}:${secs < 10 ? "0" : ""}${secs}`
}

function initializeChapterProgressBars() {
  chapterItems.forEach((item) => {
    const chapterId = item.dataset.chapterId
    const history = listeningHistory[chapterId]
    if (history) {
      const container = item.closest(".chapter-container")?.querySelector(".chapter-progress-bar-container")
      const innerBar = container?.querySelector(".chapter-progress-bar-inner")
      if (container && innerBar) {
        const duration = Number.parseFloat(item.dataset.durationSeconds) || 0
        let progressPercent = 0
        if (history.completed) {
          progressPercent = 100
        } else if (duration > 0 && history.position > 0) {
          progressPercent = (history.position / duration) * 100
        }

        if (progressPercent > 0) {
          container.style.display = "block"
          innerBar.style.width = `${Math.min(progressPercent, 100)}%`
          item.dataset.resumeFrom = history.position
        }
      }
    }
  })
}

const tabs = document.querySelectorAll(".tab-button")
const tabContents = document.querySelectorAll(".tab-content")
let aiSummaryLoaded = false

function showTab(tabId) {
  if (tabId === "summaries" && pageContext.userSubscriptionType !== "PR") {
    showPopup(
      "Premium Required",
      "AI summaries are available for Premium subscribers only. Upgrade to Premium to access AI-generated summaries.",
      'confirm',
      () => { window.location.href = pageContext.subscriptionUrl || "/subscription/"; },
      null,
      "Upgrade to Premium",
      "Cancel"
    );
    return
  }

  tabContents.forEach((content) => content.classList.add("hidden"))
  tabs.forEach((tab) => {
    const isSelected = tab.id === `tab-${tabId}`
    tab.classList.toggle("text-red-600", isSelected)
    tab.classList.toggle("border-red-600", isSelected)
    tab.classList.toggle("font-semibold", isSelected)
    tab.classList.toggle("text-[#09065E]/60", !isSelected)
    tab.classList.toggle("hover:text-red-600", !isSelected)
    tab.classList.toggle("hover:border-red-500/80", !isSelected)
    tab.classList.toggle("border-transparent", !isSelected)
    tab.classList.toggle("font-medium", isSelected)
    tab.setAttribute("aria-current", isSelected ? "page" : "false")
  })
  const contentToShow = document.getElementById(`content-${tabId}`)
  if (contentToShow) contentToShow.classList.remove("hidden")

  const selectedTabButton = document.getElementById(`tab-${tabId}`)
  if (selectedTabButton) {
    if (tabId === "summaries" && !aiSummaryLoaded) {
      fetchAiSummary()
    }
  }
}

const aiSummaryPlaceholder = document.getElementById("ai-summary-placeholder")
const aiSummaryLoading = document.getElementById("ai-summary-loading")
const aiSummaryContent = document.getElementById("ai-summary-content")
const aiSummaryError = document.getElementById("ai-summary-error")
const regenerateSummaryBtn = document.getElementById("regenerate-ai-summary-btn")

async function fetchAiSummary() {
  if (pageContext.userSubscriptionType !== "PR") {
    if (aiSummaryPlaceholder) aiSummaryPlaceholder.classList.add("hidden")
    if (aiSummaryError) {
      aiSummaryError.textContent =
        "AI summaries are available for Premium subscribers only. Upgrade to Premium to access this feature."
      aiSummaryError.classList.remove("hidden")
    }
    if (aiSummaryLoading) aiSummaryLoading.classList.add("hidden")
    if (regenerateSummaryBtn) regenerateSummaryBtn.disabled = true
    return
  }

  const currentAudiobookId = pageContext.audiobookId
  if (!currentAudiobookId || currentAudiobookId === "0" || currentAudiobookId === "") {
    if (aiSummaryPlaceholder) aiSummaryPlaceholder.classList.add("hidden")
    if (aiSummaryError) {
      aiSummaryError.textContent = "Could not load summary: Audiobook ID missing or invalid."
      aiSummaryError.classList.remove("hidden")
    }
    if (aiSummaryLoading) aiSummaryLoading.classList.add("hidden")
    if (regenerateSummaryBtn) regenerateSummaryBtn.disabled = false
    return
  }
  if (aiSummaryPlaceholder) aiSummaryPlaceholder.classList.add("hidden")
  if (aiSummaryContent) aiSummaryContent.classList.add("hidden")
  if (aiSummaryError) aiSummaryError.classList.add("hidden")
  if (aiSummaryLoading) aiSummaryLoading.classList.remove("hidden")
  if (regenerateSummaryBtn) regenerateSummaryBtn.disabled = true
  const summaryUrl = pageContext.getAiSummaryUrl
  if (
    !summaryUrl ||
    summaryUrl.includes("URL_NOT_DEFINED") ||
    (summaryUrl.includes("/0/get-ai-summary/") && currentAudiobookId !== "0")
  ) {
    if (aiSummaryError) {
      aiSummaryError.textContent = "Could not load summary: Configuration error for summary URL."
      aiSummaryError.classList.remove("hidden")
    }
    if (aiSummaryLoading) aiSummaryLoading.classList.add("hidden")
    if (regenerateSummaryBtn) regenerateSummaryBtn.disabled = false
    return
  }
  try {
    const response = await fetch(summaryUrl)
    if (!response.ok) {
      let errorMsg = `Error ${response.status}: ${response.statusText}`
      try {
        const errData = await response.json()
        if (errData.premium_required) {
          errorMsg =
            "AI summaries are available for Premium subscribers only. Upgrade to Premium to access this feature."
        } else {
          errorMsg = errData.message || errData.error || errorMsg
        }
      } catch (e) {}
      throw new Error(errorMsg)
    }
    const data = await response.json()
    if (data.status === "success" && data.summary) {
      if (aiSummaryContent) {
        aiSummaryContent.innerHTML = `<p class="text-sm text-gray-500 mb-2">Summary for "<strong>${data.title || pageContext.audiobookTitle}</strong>"${data.language_of_summary ? ` (in ${data.language_of_summary})` : ""}:</p><div class="prose prose-sm max-w-none">${data.summary.replace(/\n/g, "<br>")}</div>`
        aiSummaryContent.classList.remove("hidden")
      }
      aiSummaryLoaded = true
    } else {
      throw new Error(data.message || data.error || "Summary not found or error in response.")
    }
  } catch (error) {
    if (aiSummaryError) {
      aiSummaryError.textContent = `Failed to load summary: ${error.message}`
      aiSummaryError.classList.remove("hidden")
    }
  } finally {
    if (aiSummaryLoading) aiSummaryLoading.classList.add("hidden")
    if (regenerateSummaryBtn) regenerateSummaryBtn.disabled = false
  }
}
if (regenerateSummaryBtn) regenerateSummaryBtn.addEventListener("click", () => fetchAiSummary())

async function sendListeningProgress(forceUpdate = false) {
  if (!pageContext.isAuthenticated || !audioPlayer.src || currentChapterIndex < 0) {
    return
  }
  const currentTimeMs = Date.now()

  const position = audioPlayer.currentTime

  const TIME_ALLOWED_FOR_SEEK = 3000
  const RESUME_POSITION_ACCURACY_THRESHOLD = 2.0

  if (isResumingPlayback && !forceUpdate) {
    const timeSinceResumeStart = currentTimeMs - resumeInitiatedTimestamp

    if (
      timeSinceResumeStart < TIME_ALLOWED_FOR_SEEK &&
      (position < expectedResumePosition - RESUME_POSITION_ACCURACY_THRESHOLD || position < 1.0)
    ) {
      console.log(
        `[DEBUG] Suppressing progress update: Pos=${position.toFixed(2)}, Exp=${expectedResumePosition.toFixed(2)}, Elapsed=${timeSinceResumeStart}ms`,
      )
      return
    } else {
      isResumingPlayback = false
      expectedResumePosition = 0
      resumeInitiatedTimestamp = 0
      console.log(
        `[DEBUG] Resume suppression cleared. Final pos: ${position.toFixed(2)}. Elapsed: ${timeSinceResumeStart}ms`,
      )
    }
  }

  if (!forceUpdate && currentTimeMs - lastProgressUpdateTime < progressUpdateInterval) {
    return
  }

  const chapterItem = chapterItems[currentChapterIndex]
  if (!chapterItem) return

  const chapterIdString = chapterItem.dataset.chapterId
  if (!chapterIdString) {
    console.warn("Chapter ID is missing for progress update. Skipping.")
    return
  }

  const chapterPk = Number.parseInt(chapterIdString, 10)
  if (isNaN(chapterPk)) {
    console.error(
      "Invalid chapter ID received for progress update. Expected a numeric primary key, but got: " + chapterIdString,
    )
    return
  }

  lastProgressUpdateTime = currentTimeMs
  const duration = audioPlayer.duration

  const isCompleted = duration && isFinite(duration) && duration > 0 && duration - position < 5

  try {
    await fetch(pageContext.updateListeningProgressUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": pageContext.csrfToken,
      },
      body: JSON.stringify({
        chapter_id: chapterPk,
        position: position,
        is_completed: isCompleted,
      }),
    })
    console.log(`[DEBUG] Progress saved: ${position.toFixed(2)}s for chapter ${chapterPk}`)
  } catch (error) {
    console.error("Failed to save listening progress:", error)
  }
}

function updatePlayerUIState(state) {
  if (playerPlayIcon) playerPlayIcon.classList.toggle("hidden", state === "playing" || state === "loading")
  if (playerPauseIcon) playerPauseIcon.classList.toggle("hidden", state !== "playing")
  if (currentlyPlayingListItemButton) {
    updateListItemButtonState(currentlyPlayingListItemButton, state)
  }
}
function updateListItemButtonState(listItemButton, state) {
  if (!listItemButton) return
  const playIcon = listItemButton.querySelector(".play-icon")
  const pauseIcon = listItemButton.querySelector(".pause-icon")
  const loadingIcon = listItemButton.querySelector(".loading-icon")
  const chapterItemDiv = listItemButton.closest(".chapter-item")

  if (playIcon) playIcon.classList.add("hidden")
  if (pauseIcon) pauseIcon.classList.add("hidden")
  if (loadingIcon) loadingIcon.classList.add("hidden")

  listItemButton.classList.remove("bg-pink-100", "text-pink-600", "hover:bg-pink-200", "animate-pulse")
  listItemButton.classList.add("bg-red-100", "text-red-700", "hover:bg-red-200")

  if (state === "playing") {
    if (pauseIcon) pauseIcon.classList.remove("hidden")
    listItemButton.classList.remove("bg-red-100", "text-red-700", "hover:bg-red-200")
    listItemButton.classList.add("bg-pink-100", "text-pink-600", "hover:bg-pink-200")
    if (chapterItemDiv) chapterItemDiv.classList.add("playing", "bg-red-100", "border-l-red-600")
  } else if (state === "loading") {
    if (loadingIcon) loadingIcon.classList.remove("hidden")
    listItemButton.classList.add("animate-pulse")
  } else {
    if (playIcon) playIcon.classList.remove("hidden")
  }
}

function checkCoinPurchaseEligibility() {
  const coinPurchaseSection = document.getElementById("coinPurchaseSection")
  if (!pageContext.isAuthenticated || !pageContext.isCreatorBook || !coinPurchaseSection) {
    if (coinPurchaseSection) coinPurchaseSection.style.display = "none"
    return
  }

  const coinsRequiredEl = document.getElementById("coinsRequired")
  const userCoinBalanceEl = document.getElementById("userCoinBalance")
  const coinPurchaseBtn = document.getElementById("coinPurchaseBtn")
  const coinPurchaseStatusEl = document.getElementById("coinPurchaseStatus")
  const purchaseButton = document.getElementById("purchase-button")
  const purchaseMethodDivider = document.getElementById("purchaseMethodDivider")

  if (!coinsRequiredEl || !userCoinBalanceEl || !coinPurchaseBtn || !coinPurchaseStatusEl) {
    console.error("One or more coin purchase elements are missing from the DOM.")
    return
  }

  const eligibilityUrl = pageContext.checkCoinEligibilityUrl

  fetch(eligibilityUrl)
    .then((response) => {
      if (!response.ok) throw new Error(`Network response was not ok, status: ${response.status}`)
      return response.json()
    })
    .then((data) => {
      if (data.status === "already_purchased") {
        coinPurchaseSection.classList.remove("coin-insufficient")
        coinPurchaseSection.classList.add("coin-already-purchased")
        coinPurchaseSection.innerHTML = `<div class="text-center font-semibold text-green-800"><i class="fas fa-check-circle mr-2"></i>You already own this audiobook!</div>`
        if (purchaseButton) purchaseButton.style.display = "none"
        if (purchaseMethodDivider) purchaseMethodDivider.style.display = "none"
        return
      }

      if (data.status !== "success") {
        coinPurchaseSection.innerHTML = `<p class="text-center text-sm text-amber-800">Could not check coin purchase eligibility.</p>`
        return
      }

      coinsRequiredEl.textContent = data.coins_required
      userCoinBalanceEl.textContent = data.user_coins

      if (data.eligible) {
        coinPurchaseSection.classList.remove("coin-insufficient")
        coinPurchaseBtn.disabled = false
        coinPurchaseStatusEl.innerHTML = ""
      } else {
        // Not enough coins
        coinPurchaseSection.classList.add("coin-insufficient")
        coinPurchaseBtn.disabled = true
        const buyCoinsUrl = pageContext.buyCoinsUrl
        coinPurchaseStatusEl.innerHTML = `<p class="text-center text-sm font-medium text-red-700">You need ${data.coins_short} more coins. <a href="${buyCoinsUrl}" class="font-bold underline hover:text-red-800">Buy Coins</a></p>`
      }
    })
    .catch((error) => {
      console.error("Error checking coin eligibility:", error)
      coinPurchaseSection.innerHTML = `<p class="text-center text-sm text-red-700">Error checking eligibility. Please refresh.</p>`
    })
}

function purchaseWithCoins() {
  const btn = document.getElementById("coinPurchaseBtn")
  const statusEl = document.getElementById("coinPurchaseStatus")

  if (!btn || !statusEl) return

  btn.disabled = true
  btn.innerHTML =
    '<svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Processing...'
  statusEl.innerHTML = ""

  fetch(pageContext.purchaseWithCoinsUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": pageContext.csrfToken,
    },
    body: JSON.stringify({
      audiobook_slug: pageContext.audiobookSlug,
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.status === "success") {
        statusEl.innerHTML = `<p class="text-center font-semibold text-green-700">${data.message}</p>`
        showPopup("Purchase Successful", "Reloading page to reflect your purchase.", "success");
        btn.innerHTML = '<i class="fas fa-check-circle mr-2"></i> Success!'
        setTimeout(() => {
          window.location.href = data.redirect_url || window.location.href
        }, 2000)
      } else {
        statusEl.innerHTML = `<p class="text-center font-semibold text-red-700">${data.message}</p>`
        btn.disabled = false
        const coinsRequiredEl = document.getElementById("coinsRequired")
        const coinsRequired = coinsRequiredEl ? coinsRequiredEl.textContent : pageContext.audiobookPrice
        btn.innerHTML = `<i class="fas fa-coins mr-2"></i> Purchase with ${coinsRequired} Coins`
      }
    })
    .catch((error) => {
      console.error("Error during coin purchase:", error)
      statusEl.innerHTML =
        '<p class="text-center font-semibold text-red-700">An unexpected error occurred. Please try again.</p>'
      btn.disabled = false
      const coinsRequiredEl = document.getElementById("coinsRequired")
      const coinsRequired = coinsRequiredEl ? coinsRequiredEl.textContent : pageContext.audiobookPrice
      btn.innerHTML = `<i class="fas fa-coins mr-2"></i> Purchase with ${coinsRequired} Coins`
    })
}

// ✅ UPDATED: Chapter unlock with coins function to use dynamic cost
window.unlockChapterWithCoins = async (chapterId) => {
  console.log(`[DEBUG] Attempting to unlock chapter ${chapterId} with coins`)

  if (!pageContext.isAuthenticated) {
    showPopup(
      "Login Required",
      "Please log in to unlock chapters.",
      'confirm',
      () => {
        window.location.href = pageContext.loginUrl || "/login/"
      },
      null,
      "Log In",
      "Cancel",
    )
    return
  }

  if (pageContext.userSubscriptionType !== "FR") {
    showPopup("Chapter Unlock", "Chapter unlock is only available for FREE users.", 'info');
    return
  }

  const unlockBtn = document.getElementById(`unlock-btn-${chapterId}`)
  const unlockStatus = document.getElementById(`unlock-status-${chapterId}`)
  
  if (!unlockBtn) {
    console.error(`Unlock button not found for chapter ${chapterId}`)
    return
  }
  
  // ADDED: New code block to prevent multiple clicks (race condition)
  if (unlockBtn.disabled) {
    console.log(`[DEBUG] Unlock for chapter ${chapterId} already in progress. Ignoring click.`)
    return;
  }

  // Get unlock cost from the button's data attribute
  const unlockCost = unlockBtn.dataset.unlockCost ? parseInt(unlockBtn.dataset.unlockCost, 10) : 50;
  const chapterTitle = unlockBtn.closest('.chapter-container')?.querySelector('.chapter-item')?.dataset.chapterTitle || 'This chapter';

  if (isNaN(unlockCost)) {
      showPopup("Unlock Error", "Unlock cost is not valid.", 'error');
      return;
  }

  // Disable button and show loading state
  unlockBtn.disabled = true
  unlockBtn.innerHTML =
    '<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Unlocking...'

  if (unlockStatus) {
    unlockStatus.textContent = "Processing unlock..."
    unlockStatus.className = "text-sm text-blue-600 font-medium"
  }

  try {
    const response = await fetch(pageContext.unlockChapterUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": pageContext.csrfToken,
      },
      body: JSON.stringify({
        chapter_id: chapterId,
      }),
    })

    const data = await response.json()

    if (response.ok && data.status === "success") {
      // Success - chapter unlocked
      showPopup("Success", data.message || "Chapter unlocked successfully!", 'success')

      // Update UI to reflect unlocked state
      const chapterItem = document.querySelector(`.chapter-item[data-chapter-id="${chapterId}"]`)
      if (chapterItem) {
        chapterItem.dataset.isAccessible = "true"
        chapterItem.dataset.lockReason = ""

        const unlockSection = document.getElementById(`unlock-section-${chapterId}`)
        if (unlockSection) {
          unlockSection.style.transition = 'opacity 0.5s, height 0.5s';
          unlockSection.style.opacity = '0';
          setTimeout(() => {
              unlockSection.style.display = 'none';
          }, 500);
        }

        // Update play button to be functional and look enabled
        const playButtonContainer = chapterItem.querySelector(".flex-shrink-0");
        if(playButtonContainer){
            playButtonContainer.innerHTML = `
                <button onclick="playChapter(this)" title="Play Episode"
                        class="play-button flex items-center justify-center w-12 h-12 bg-red-100 hover:bg-red-200 text-red-700 rounded-full transition duration-150 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500">
                    <svg class="w-6 h-6 play-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z"></path></svg>
                    <svg class="w-6 h-6 pause-icon hidden" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M5.75 4.75a.75.75 0 00-1.5 0v10.5a.75.75 0 001.5 0V4.75zM15.75 4.75a.75.75 0 00-1.5 0v10.5a.75.75 0 001.5 0V4.75z"></path></svg>
                    <svg class="w-6 h-6 loading-icon hidden animate-spin text-red-700" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                </button>`;
        }
      }

      // Update all visible coin balance displays
      if (data.new_coin_balance !== undefined) {
          document.querySelectorAll('[id^="user-coins-"], #userCoinBalance').forEach((el) => {
              el.textContent = data.new_coin_balance;
          });
      }

    } else {
      const errorMessage = data.message || "Failed to unlock chapter"
      showPopup("Unlock Failed", errorMessage, 'error')

      if (unlockStatus) {
        unlockStatus.textContent = errorMessage
        unlockStatus.className = "text-sm text-red-600 font-medium"
      }
      unlockBtn.disabled = false
      unlockBtn.innerHTML = `<i class="fas fa-coins mr-2"></i>Unlock for ${unlockCost} Coins`
    }
  } catch (error) {
    console.error("Error unlocking chapter:", error)
    showPopup("Error", "An error occurred while unlocking the chapter. Please try again.", 'error')

    if (unlockStatus) {
      unlockStatus.textContent = "An error occurred. Please try again."
      unlockStatus.className = "text-sm text-red-600 font-medium"
    }
    unlockBtn.disabled = false
    unlockBtn.innerHTML = `<i class="fas fa-coins mr-2"></i>Unlock for ${unlockCost} Coins`
  }
}

function showPlayerBar() {
  if (bottomPlayerBar) bottomPlayerBar.classList.remove("translate-y-full")
}
function hidePlayerBar() {
  if (bottomPlayerBar) bottomPlayerBar.classList.add("translate-y-full")
}

function updatePlayerInfo(chapterIndexValue) {
  if (chapterIndexValue < 0 || chapterIndexValue >= chapterItems.length) return
  const chapterItem = chapterItems[chapterIndexValue]
  if (!chapterItem) return
  const title = chapterItem.dataset.chapterTitle || "Unknown Title"
  const episodeNum = chapterIndexValue + 1
  const totalEpisodes = chapterItems.length

  if (playerEpisodeTitle) {
    playerEpisodeTitle.textContent = title
    playerEpisodeTitle.title = title
  }
  if (playerEpisodeNumber) playerEpisodeNumber.textContent = `Episode ${episodeNum}/${totalEpisodes}`
  if (playerCoverImage && mainCoverImageElement) {
    playerCoverImage.src =
      mainCoverImageElement.tagName === "IMG" && mainCoverImageElement.src
        ? mainCoverImageElement.src
        : placeholderCoverSrc
  } else if (playerCoverImage) {
    playerCoverImage.src = placeholderCoverSrc
  }

  if (playerPrevButton) playerPrevButton.disabled = chapterIndexValue <= 0
  if (playerNextButton) playerNextButton.disabled = chapterIndexValue >= totalEpisodes - 1
}

window.playChapter = (buttonElement) => {
  const chapterItem = buttonElement.closest(".chapter-item")
  if (!chapterItem) {
    showPopup("Player Error", "Could not find chapter data.", 'error');
    return
  }

  const audioUrlTemplate = chapterItem.dataset.audioUrlTemplate
  const chapterTitle = chapterItem.dataset.chapterTitle || "Episode"
  const chapterIndexFromData = Number.parseInt(chapterItem.dataset.chapterIndex ?? "-1", 10)
  const isAccessible = chapterItem.dataset.isAccessible === "true"
  const lockReason = chapterItem.dataset.lockReason
  const chapterIdForProgress = chapterItem.dataset.chapterId
  const resumeTime = Number.parseFloat(chapterItem.dataset.resumeFrom) || 0
  const duration = Number.parseFloat(chapterItem.dataset.durationSeconds) || 0
  const isCompleted = listeningHistory[chapterIdForProgress]?.completed

  // PRIORITY 1: Check accessibility first with enhanced lock reason handling
  if (!isAccessible) {
    console.log(`[DEBUG] Chapter locked: ${chapterTitle}, Lock reason: ${lockReason}`)

    if (lockReason === "purchase_required") {
      // For paid audiobooks, show purchase popup
      console.log(`[DEBUG] Showing purchase popup for locked paid chapter: ${chapterTitle}`)

      showPopup(
        "Premium Chapter",
        `This is a premium chapter. Purchase the full audiobook for just PKR ${pageContext.audiobookPrice} to unlock all episodes!`,
        'confirm',
        () => {
          // Scroll to purchase section
          const purchaseSection = document.querySelector("#purchase-button, #coinPurchaseSection")
          if (purchaseSection) {
            purchaseSection.scrollIntoView({ behavior: "smooth", block: "center" })
          }
        },
        null,
        "Purchase Now",
        "Cancel",
      )
    } else if (lockReason === "premium_required") {
      // For free audiobooks requiring premium subscription
      console.log(`[DEBUG] Showing premium upgrade popup for chapter: ${chapterTitle}`)

      showPopup(
        "Premium Feature",
        "This chapter requires a Premium subscription. Free users can only access the first chapter of free audiobooks. Upgrade now to unlock all chapters!",
        'confirm',
        () => {
          // Redirect to subscription page
          window.location.href = pageContext.subscriptionUrl || "/subscription/"
        },
        null,
        "Upgrade to Premium",
        "Cancel",
      )
    } else if (lockReason === "coin_unlock_available") {
      const unlockBtn = document.getElementById(`unlock-btn-${chapterIdForProgress}`);
      const unlockCost = unlockBtn ? (unlockBtn.dataset.unlockCost || 50) : 50;

      showPopup(
        "Chapter Locked",
        `This chapter is locked but can be unlocked for ${unlockCost} coins. Would you like to unlock "${chapterTitle}" now?`,
        'confirm',
        () => {
          // Call the unlock function
          unlockChapterWithCoins(chapterIdForProgress)
        },
        null,
        `Unlock for ${unlockCost} Coins`,
        "Cancel",
      )
    } else {
      // Fallback for any other lock reasons or legacy cases
      console.log(`[DEBUG] Showing generic lock message for chapter: ${chapterTitle}`)
      showPopup("Chapter Locked", "This chapter is not accessible.", 'error')
    }
    return
  }

  // PRIORITY 2: Validate audio URL
  if (
    typeof audioUrlTemplate !== "string" ||
    audioUrlTemplate.trim() === "" ||
    !audioUrlTemplate.includes("?url=") ||
    audioUrlTemplate.endsWith("?url=")
  ) {
    showPopup("Audio Source Missing", `Audio source for "${chapterTitle}" is missing or invalid.`, 'error');
    if (buttonElement) updateListItemButtonState(buttonElement, "error")
    return
  }

  // PRIORITY 3: Validate chapter data
  const chapterId = chapterItem.dataset.chapterId
  const audiobookSlug = pageContext.audiobookSlug
  let audioUrl = audioUrlTemplate
  if (chapterId && audiobookSlug) {
    const separator = audioUrlTemplate.includes("?") ? "&" : "?"
    audioUrl += `${separator}chapter_id=${encodeURIComponent(chapterId)}&audiobook_slug=${encodeURIComponent(audiobookSlug)}`
  }

  if (chapterIndexFromData < 0) {
    showPopup("Chapter Data Error", `Could not load data for "${chapterTitle}".`, 'error');
    if (buttonElement) updateListItemButtonState(buttonElement, "error")
    return
  }

  console.log(`[DEBUG] Proceeding to play accessible chapter: ${chapterTitle}`)

  // Rest of the playback logic remains the same...
  const isPlayingThisChapter = currentlyPlayingListItemButton === buttonElement && !audioPlayer.paused
  const isDifferentChapter = audioPlayer.src !== audioUrl

  if (isPlayingThisChapter && !isDifferentChapter) {
    audioPlayer.pause()
  } else {
    // Reset resume flags
    isResumingPlayback = false
    expectedResumePosition = 0
    resumeInitiatedTimestamp = 0

    // Update UI for new chapter
    if (currentlyPlayingListItemButton && currentlyPlayingListItemButton !== buttonElement) {
      updateListItemButtonState(currentlyPlayingListItemButton, "paused")
    }
    currentChapterIndex = chapterIndexFromData
    currentlyPlayingListItemButton = buttonElement

    // Set chapter ID for progress tracking
    if (audioPlayer) {
      if (chapterIdForProgress) {
        audioPlayer.dataset.currentChapterIdForProgress = chapterIdForProgress
      } else {
        delete audioPlayer.dataset.currentChapterIdForProgress
      }
    }

    // Update UI states
    updateListItemButtonState(currentlyPlayingListItemButton, "loading")
    updatePlayerUIState("loading")
    updatePlayerInfo(currentChapterIndex)
    showPlayerBar()

    // Determine if we should auto-resume
    const shouldAutoResume =
      !isCompleted &&
      resumeTime &&
      !isNaN(resumeTime) &&
      resumeTime > 0.5 &&
      (duration === 0 || resumeTime < duration - 2)

    console.log(
      `[DEBUG] Resume check: resumeTime=${resumeTime}, shouldAutoResume=${shouldAutoResume}, isCompleted=${isCompleted}, duration=${duration}`,
    )

    // Load and play audio
    if (isDifferentChapter || audioPlayer.paused) {
      audioPlayer.src = audioUrl
      audioPlayer.load()

      if (shouldAutoResume) {
        console.log(`[DEBUG] Auto-resuming to ${resumeTime}s`)

        const handleAutoResume = () => {
          console.log(
            `[DEBUG] Audio fully ready - Duration: ${audioPlayer.duration}s, ReadyState: ${audioPlayer.readyState}, Seekable: ${audioPlayer.seekable.length > 0 ? audioPlayer.seekable.end(0) : "N/A"}s`,
          )

          if (audioPlayer.seekable.length === 0) {
            console.log(`[DEBUG] ⚠️ Audio does not support seeking - starting from beginning`)
            audioPlayer.play().catch((e) => handlePlaybackError(e, chapterTitle))
            return
          }

          isResumingPlayback = true
          expectedResumePosition = resumeTime
          resumeInitiatedTimestamp = Date.now()

          let seekAttempt = 0
          const maxSeekAttempts = 3

          const trySeek = () => {
            seekAttempt++
            console.log(`[DEBUG] Seek attempt ${seekAttempt}/${maxSeekAttempts}`)

            audioPlayer.currentTime = resumeTime
            console.log(`[DEBUG] After direct assignment: ${audioPlayer.currentTime.toFixed(2)}s`)

            setTimeout(() => {
              const actualTime = audioPlayer.currentTime
              console.log(`[DEBUG] After 100ms delay: ${actualTime.toFixed(2)}s`)

              if (Math.abs(actualTime - resumeTime) < 0.5) {
                console.log(`[DEBUG] ✅ Seek successful!`)
                audioPlayer.play().catch((e) => handlePlaybackError(e, chapterTitle))
              } else if (seekAttempt < maxSeekAttempts) {
                console.log(`[DEBUG] Seek failed, trying again...`)
                setTimeout(trySeek, 200)
              } else {
                console.log(`[DEBUG] ⚠️ All seek attempts failed, starting from beginning`)
                isResumingPlayback = false
                expectedResumePosition = 0
                resumeInitiatedTimestamp = 0
                audioPlayer.play().catch((e) => handlePlaybackError(e, chapterTitle))
              }
            }, 100)
          }

          trySeek()
        }

        if (audioPlayer.readyState >= 4) {
          handleAutoResume()
        } else {
          audioPlayer.addEventListener("canplaythrough", handleAutoResume, { once: true })
        }
      } else {
        console.log(`[DEBUG] Starting from beginning (no resume available)`)
        audioPlayer.play().catch((e) => {
          if (e.name === "NotAllowedError") {
            console.warn("Autoplay was prevented by browser. User will need to click play.")
          } else {
            console.error("Initial play() attempt failed:", e)
            handlePlaybackError(e, chapterTitle)
          }
        })
      }
    } else {
      audioPlayer.play().catch((e) => handlePlaybackError(e, chapterTitle))
    }
  }
}

function handlePlaybackError(e, chapterTitle = "the selected audio") {
  let errorUserTitle = "Playback Error"
  let errorUserText = `Could not play ${chapterTitle}.`
  if (e && e.name) {
    if (e.name === "NotAllowedError") {
      errorUserTitle = "Autoplay Blocked"
      errorUserText = `Playback for ${chapterTitle} was prevented. Click play again.`
    } else if (e.name === "AbortError") {
      errorUserTitle = "Load Interrupted"
      errorUserText = `Loading for ${chapterTitle} interrupted.`
    } else if (e.name === "NotSupportedError") {
      errorUserTitle = "Format Not Supported"
      errorUserText = `Audio format for ${chapterTitle} may not be supported.`
    }
  }
  if (audioPlayer.error) {
    errorUserText = `Failed to load ${chapterTitle}. (Code: ${audioPlayer.error.code})`
  }
  showPopup(errorUserTitle, errorUserText, 'error');
  updatePlayerUIState("error")
  if (currentlyPlayingListItemButton) updateListItemButtonState(currentlyPlayingListItemButton, "paused")
}

window.togglePlayPause = () => {
  if (currentChapterIndex < 0 || !audioPlayer.src || audioPlayer.src === window.location.href) {
    const firstChapterButton = chapterItems[0]?.querySelector(".play-button")
    if (firstChapterButton && chapterItems[0]?.dataset.isAccessible === "true") playChapter(firstChapterButton)
    else if (chapterItems.length > 0 && chapterItems[0]?.dataset.isAccessible !== "true")
      showPopup("Locked", "First episode is locked.", 'info')
    else showPopup("No Episode", "Select an episode", 'info')
    return
  }
  if (isResumingPlayback) {
    console.warn("Manual toggle during resume attempt. Clearing flags.")
    isResumingPlayback = false
    expectedResumePosition = 0
    resumeInitiatedTimestamp = 0
  }
  if (audioPlayer.paused || audioPlayer.ended)
    audioPlayer.play().catch((e) => handlePlaybackError(e, playerEpisodeTitle.textContent))
  else audioPlayer.pause()
}

window.playNextChapter = () => {
  isResumingPlayback = false
  expectedResumePosition = 0
  resumeInitiatedTimestamp = 0

  const nextIndex = currentChapterIndex + 1
  if (nextIndex < chapterItems.length) {
    const nextChapterItem = chapterItems[nextIndex]
    if (nextChapterItem?.dataset.isAccessible === "true") {
      const playButton = nextChapterItem.querySelector(".play-button")
      if (playButton) playChapter(playButton)
    } else {
      showPopup("Locked", "Next chapter is locked.", 'info')
      updatePlayerUIState("ended")
    }
  } else {
    showPopup("End of Audiobook", "End of audiobook reached.", 'info')
    updatePlayerUIState("ended")
  }
}

window.playPreviousChapter = () => {
  isResumingPlayback = false
  expectedResumePosition = 0
  resumeInitiatedTimestamp = 0

  const prevIndex = currentChapterIndex - 1
  if (prevIndex >= 0) {
    const prevChapterItem = chapterItems[prevIndex]
    if (prevChapterItem?.dataset.isAccessible === "true") {
      const playButton = prevChapterItem.querySelector(".play-button")
      if (playButton) playChapter(playButton)
    } else {
      showPopup("Locked", "Previous chapter is locked.", 'info')
    }
  }
}

window.closePlayer = () => {
  audioPlayer.pause()
  audioPlayer.src = ""
  hidePlayerBar()
  if (currentlyPlayingListItemButton) updateListItemButtonState(currentlyPlayingListItemButton, "paused")
  currentlyPlayingListItemButton = null
  currentChapterIndex = -1
  if (playerSeekBar) playerSeekBar.value = 0
  if (playerCurrentTime) playerCurrentTime.textContent = "0:00"
  if (playerDuration) playerDuration.textContent = "0:00"
  if (playerEpisodeTitle) playerEpisodeTitle.textContent = "Select an episode"
  if (playerEpisodeNumber) playerEpisodeNumber.textContent = "Episode N/A"
  if (playerCoverImage) playerCoverImage.src = placeholderCoverSrc
  if (playerPrevButton) playerPrevButton.disabled = true
  if (playerNextButton) playerNextButton.disabled = true
  currentSpeedIndex = 0
  audioPlayer.playbackRate = playbackSpeeds[currentSpeedIndex]
  if (playerSpeedButton) playerSpeedButton.textContent = `${playbackSpeeds[currentSpeedIndex]}x`
  updatePlayerUIState("paused")
  isResumingPlayback = false
  expectedResumePosition = 0
  resumeInitiatedTimestamp = 0
}

window.cyclePlaybackSpeed = () => {
  currentSpeedIndex = (currentSpeedIndex + 1) % playbackSpeeds.length
  const newSpeed = playbackSpeeds[currentSpeedIndex]
  audioPlayer.playbackRate = newSpeed
  if (playerSpeedButton) playerSpeedButton.textContent = `${newSpeed}x`
}

const mainTimeupdateHandler = () => {
  if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
    if (playerCurrentTime) playerCurrentTime.textContent = formatTime(audioPlayer.currentTime)
    if (playerSeekBar && !playerSeekBar.matches(":active")) playerSeekBar.value = audioPlayer.currentTime
    const chapterItem = chapterItems[currentChapterIndex]
    if (chapterItem) {
      const container = chapterItem.closest(".chapter-container")?.querySelector(".chapter-progress-bar-container")
      const innerBar = container?.querySelector(".chapter-progress-bar-inner")
      if (container && innerBar) {
        container.style.display = "block"
        innerBar.style.width = `${(audioPlayer.currentTime / audioPlayer.duration) * 100}%`
      }
    }
    sendListeningProgress()
  }
}

if (audioPlayer) {
  audioPlayer.addEventListener("play", () => updatePlayerUIState("playing"))
  audioPlayer.addEventListener("pause", () => {
    sendListeningProgress(true)
    updatePlayerUIState("paused")
  })
  audioPlayer.addEventListener("ended", () => {
    sendListeningProgress(true)
    playNextChapter()
  })
  audioPlayer.addEventListener("error", (e) => {
    let contextMessage = "audio track"
    if (currentChapterIndex >= 0 && chapterItems[currentChapterIndex])
      contextMessage = `"${chapterItems[currentChapterIndex].dataset.chapterTitle}"`
    handlePlaybackError(e, contextMessage)
  })
  audioPlayer.addEventListener("loadedmetadata", () => {
    if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
      if (playerDuration) playerDuration.textContent = formatTime(audioPlayer.duration)
      if (playerSeekBar) playerSeekBar.max = audioPlayer.duration
    }
  })

  audioPlayer.addEventListener("timeupdate", mainTimeupdateHandler)
}

if (playerSeekBar) {
  playerSeekBar.addEventListener("input", () => {
    if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration) && audioPlayer.readyState >= 1)
      audioPlayer.currentTime = playerSeekBar.value
  })
}

const fullAudiobookDownloadBtnExisting = document.getElementById("download-full-audiobook-btn")
const fullAudiobookDownloadTextExisting = document.getElementById("download-full-audiobook-text")
const fullAudiobookStatusMessagesExisting = document.getElementById("download-status-messages")
const fullAudiobookProgressBarContainerExisting = document.getElementById("overall-download-progress-bar-container")
const fullAudiobookProgressBarExisting = document.getElementById("overall-download-progress-bar")

function updateChapterDownloadButtonUI(button, status, data) {
  if (!button) return
  const container = button.closest(".chapter-download-container")
  const downloadIcon = button.querySelector(".download-icon")
  const downloadedIcon = button.querySelector(".downloaded-icon")
  const downloadingIcon = button.querySelector(".downloading-icon")
  const statusSpan = container?.querySelector(".chapter-download-status")

  if (downloadIcon) downloadIcon.classList.add("hidden")
  if (downloadedIcon) downloadedIcon.classList.add("hidden")
  if (downloadingIcon) downloadingIcon.classList.add("hidden")
  button.disabled = false

  if (statusSpan) {
    if (status === "downloading") {
      if (typeof data === "number") statusSpan.textContent = `${data}%`
      else if (typeof data === "string" && data) statusSpan.textContent = data
      else statusSpan.textContent = "Preparing..."
    } else if (status === "downloaded") statusSpan.textContent = "Saved"
    else if (status === "error") statusSpan.textContent = typeof data === "string" && data ? data : "Error"
    else statusSpan.textContent = typeof data === "string" && data ? data : ""
  }

  switch (status) {
    case "downloading":
      if (downloadingIcon) downloadingIcon.classList.remove("hidden")
      button.disabled = true
      button.title = "Downloading episode..."
      break
    case "downloaded":
      if (downloadedIcon) downloadedIcon.classList.remove("hidden")
      button.disabled = true
      button.title = "Episode downloaded"
      break
    case "error":
      if (downloadIcon) downloadIcon.classList.remove("hidden")
      button.title = `Download failed: ${typeof data === "string" && data ? data : "Unknown error"}`
      break
    default:
      if (downloadIcon) downloadIcon.classList.remove("hidden")
      button.title = "Download Episode"
      break
  }
}

function attachChapterDownloadListeners() {
  document.querySelectorAll(".download-chapter-btn").forEach((button) => {
    button.addEventListener("click", async function (event) {
      event.stopPropagation()

      if (pageContext.userSubscriptionType !== "PR") {
        showPopup(
          "Premium Required",
          "Downloads are available for Premium subscribers only. Upgrade to Premium to download audiobooks for offline listening.",
          'confirm',
          () => {
            window.location.href = pageContext.subscriptionUrl || "/subscription/"
          },
          null,
          "Upgrade to Premium",
          "Cancel",
        )
        return
      }

      if (!window.OfflineManager || typeof window.OfflineManager.downloadChapter !== "function") {
        showPopup("Offline Unavailable", "Offline download feature not available.", 'error');
        return
      }
      const chapterItemDiv = this.closest(".chapter-item")
      if (!chapterItemDiv) {
        showPopup("Download Error", "Chapter data error. Cannot download.", 'error');
        return
      }

      const chapterInfoForDownload = {
        chapter_id: this.dataset.chapterId || chapterItemDiv.dataset.chapterId,
        chapter_unique_id: this.dataset.chapterUniqueId,
        chapter_index: Number.parseInt(this.dataset.chapterIndex || chapterItemDiv.dataset.chapterIndex, 10),
        chapter_title: chapterItemDiv.dataset.chapterTitle,
        audio_url_template: chapterItemDiv.dataset.audioUrlTemplate,
        duration_seconds: Number.parseInt(chapterItemDiv.dataset.durationSeconds, 10),
        is_accessible: chapterItemDiv.dataset.isAccessible === "true",
      }
      const mainCoverImg = document.getElementById("main-cover-image")
      const audiobookInfoForDownload = {
        audiobookId: pageContext.audiobookId,
        audiobookTitle: pageContext.audiobookTitle,
        author: pageContext.audiobookAuthor || "Unknown Author",
        coverImageUrl: mainCoverImg ? mainCoverImg.src : placeholderCoverSrc,
        slug: pageContext.audiobookSlug,
        language: pageContext.audiobookLanguage || "N/A",
        genre: pageContext.audiobookGenre || "N/A",
        isCreatorBook: pageContext.isCreatorBook === true,
      }

      if (!chapterInfoForDownload.is_accessible) {
        showPopup("Download Not Allowed", "This chapter is not accessible for download.", 'info');
        return
      }
      if (!chapterInfoForDownload.audio_url_template || chapterInfoForDownload.audio_url_template.endsWith("?url=")) {
        showPopup("Download Error", "Audio source not found for this chapter.", 'error');
        updateChapterDownloadButtonUI(this, "error", "No audio URL")
        return
      }

      updateChapterDownloadButtonUI(this, "downloading", "Preparing...")
      try {
        const result = await OfflineManager.downloadChapter(
          chapterInfoForDownload,
          audiobookInfoForDownload,
          (percentage, message) => {
            if (percentage === -1) updateChapterDownloadButtonUI(this, "error", message)
            else if (message.toLowerCase().includes("already downloaded"))
              updateChapterDownloadButtonUI(this, "downloaded", "Already downloaded")
            else if (percentage === 100 && message.toLowerCase().includes("complete"))
              updateChapterDownloadButtonUI(this, "downloaded", "Download complete!")
            else updateChapterDownloadButtonUI(this, "downloading", percentage)
          },
        )
        if (result.success && !result.message.toLowerCase().includes("already downloaded"))
          showPopup("Download Complete", `Chapter "${chapterInfoForDownload.chapter_title}" downloaded!`, 'success');
        else if (!result.success && !result.message.toLowerCase().includes("already downloaded"))
          showPopup("Download Failed", `Failed to download "${chapterInfoForDownload.chapter_title}": ${result.message}`, 'error');

      } catch (err) {
        showPopup("Download Error", "An unexpected error occurred during download.", 'error');
        updateChapterDownloadButtonUI(this, "error", "Error")
      }
    })
  })
}

if (fullAudiobookDownloadBtnExisting) {
  fullAudiobookDownloadBtnExisting.addEventListener("click", async function () {
    if (pageContext.userSubscriptionType !== "PR") {
      showPopup(
        "Premium Required",
        "Downloads are available for Premium subscribers only. Upgrade to Premium to download audiobooks for offline listening.",
        'confirm',
        () => {
          // Redirect to subscription page
          window.location.href = pageContext.subscriptionUrl || "/subscription/"
        },
        null,
        "Upgrade to Premium",
        "Cancel",
      )
      return // Stop execution here for free users
    }

    if (!window.OfflineManager || typeof window.OfflineManager.downloadFullAudiobook !== "function") {
      showPopup("Offline Unavailable", "Offline download feature not available.", 'error');
      return
    }

    const chaptersToDownload = []
    document.querySelectorAll(".chapter-item").forEach((item) => {
      if (item.dataset.isAccessible === "true") {
        const chapterInfoForId = {
            chapter_id: item.dataset.chapterId,
            chapterIndex: Number.parseInt(item.dataset.chapterIndex, 10)
        };
        const audiobookInfoForId = {
            audiobookSlug: pageContext.audiobookSlug,
            audiobookId: pageContext.audiobookId
        };
        
        chaptersToDownload.push({
          chapter_id: item.dataset.chapterId,
          chapter_unique_id: window.OfflineManager.createChapterUniqueId(audiobookInfoForId, chapterInfoForId),
          chapter_index: Number.parseInt(item.dataset.chapterIndex, 10),
          chapter_title: item.dataset.chapterTitle,
          audio_url_template: item.dataset.audioUrlTemplate,
          duration_seconds: Number.parseInt(item.dataset.durationSeconds, 10),
          is_accessible: true,
        })
      }
    })

    if (chaptersToDownload.length === 0) {
      showPopup("No Chapters", "No accessible chapters to download.", 'info');
      return
    }

    const mainCoverImg = document.getElementById("main-cover-image")
    const audiobookInfoForDownload = {
      audiobookId: pageContext.audiobookId,
      audiobookTitle: pageContext.audiobookTitle,
      author: pageContext.audiobookAuthor || "Unknown Author",
      coverImageUrl: mainCoverImg ? mainCoverImg.src : placeholderCoverSrc,
      slug: pageContext.audiobookSlug,
      language: pageContext.audiobookLanguage || "N/A",
      genre: pageContext.audiobookGenre || "N/A",
      isCreatorBook: pageContext.isCreatorBook === true,
    }

    this.disabled = true
    if (fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = "Preparing..."
    if (fullAudiobookStatusMessagesExisting)
      fullAudiobookStatusMessagesExisting.textContent = "Starting full download..."
    if (fullAudiobookProgressBarContainerExisting) fullAudiobookProgressBarContainerExisting.classList.remove("hidden")
    if (fullAudiobookProgressBarExisting) fullAudiobookProgressBarExisting.style.width = "0%"

    try {
      await window.OfflineManager.downloadFullAudiobook(
        chaptersToDownload,
        audiobookInfoForDownload,
        (chapterIndexInArray, progress, message) => {
          const chapterData = chaptersToDownload[chapterIndexInArray]
          const btn = document.querySelector(
            `.download-chapter-btn[data-chapter-unique-id="${chapterData.chapter_unique_id}"]`,
          )
          if (btn) {
            if (progress === -1) updateChapterDownloadButtonUI(btn, "error", message)
            else if (message.toLowerCase().includes("already downloaded"))
              updateChapterDownloadButtonUI(btn, "downloaded")
            else if (progress === 100 && message.toLowerCase().includes("complete"))
              updateChapterDownloadButtonUI(btn, "downloaded")
            else updateChapterDownloadButtonUI(btn, "downloading", progress)
          }
        },
        (overallPercentage, message) => {
          if (fullAudiobookProgressBarExisting) fullAudiobookProgressBarExisting.style.width = `${overallPercentage}%`
          if (fullAudiobookStatusMessagesExisting) fullAudiobookStatusMessagesExisting.textContent = message
          if (overallPercentage === 100) {
            if (fullAudiobookDownloadTextExisting)
              fullAudiobookDownloadTextExisting.textContent = message.includes("error") ? "Partial" : "All Downloaded"
            if (!message.includes("error")) {
              this.classList.remove("border-[#09065E]/40", "text-[#09065E]/90", "hover:bg-[#09065E]/5")
              this.classList.add("border-green-500", "text-green-600", "bg-green-50")
            } else {
              this.disabled = false
            }
            showPopup(
              message.includes("error") ? "Download Warning" : "Download Complete",
              message,
              message.includes("error") ? "info" : "success"
            );
          }
        },
      )
    } catch (err) {
      showPopup("Download Error", "An unexpected error occurred during full download.", 'error');
      if (fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = "Download Failed"
      if (fullAudiobookStatusMessagesExisting)
        fullAudiobookStatusMessagesExisting.textContent = "Error during download."
      this.disabled = false
    }
  })
}

async function checkInitialDownloadStates() {
  if (!window.OfflineManager || !pageContext.audiobookId || typeof window.OfflineManager.initDB !== "function") {
    return
  }
  try {
    await window.OfflineManager.initDB()
    const chapterDownloadButtons = document.querySelectorAll(".download-chapter-btn")
    
    const downloadCheckPromises = [];

    chapterDownloadButtons.forEach(button => {
        const chapterUniqueId = button.dataset.chapterUniqueId;
        const promise = window.OfflineManager.isChapterDownloaded(chapterUniqueId).then(isDownloaded => {
            if (isDownloaded) {
                updateChapterDownloadButtonUI(button, "downloaded");
                return true;
            } else {
                updateChapterDownloadButtonUI(button, "idle");
                return false;
            }
        });
        downloadCheckPromises.push(promise);
    });

    const downloadedStatuses = await Promise.all(downloadCheckPromises);
    const downloadedChaptersCount = downloadedStatuses.filter(status => status).length;

    if (fullAudiobookDownloadBtnExisting) {
      const totalAccessibleCount = document.querySelectorAll('.chapter-item[data-is-accessible="true"]').length;

      if (pageContext.userSubscriptionType !== "PR") {
        if (fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = "Premium Required"
        fullAudiobookDownloadBtnExisting.disabled = true
        if (fullAudiobookStatusMessagesExisting)
          fullAudiobookStatusMessagesExisting.textContent = "Downloads are available for Premium subscribers only."
        fullAudiobookDownloadBtnExisting.classList.add("opacity-50", "cursor-not-allowed")
      } else if (totalAccessibleCount === 0) {
        if (fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = "No Chapters"
        fullAudiobookDownloadBtnExisting.disabled = true;
      } else if (totalAccessibleCount > 0 && totalAccessibleCount === downloadedChaptersCount) {
        if (fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = "All Downloaded"
        fullAudiobookDownloadBtnExisting.classList.remove("border-[#09065E]/40", "text-[#09065E]/90", "hover:bg-[#09065E]/5")
        fullAudiobookDownloadBtnExisting.classList.add("border-green-500", "text-green-600", "bg-green-50")
        fullAudiobookDownloadBtnExisting.disabled = true
        fullAudiobookDownloadBtnExisting.title = "All chapters have been downloaded"
      } else {
        if (fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = "Download All"
        fullAudiobookDownloadBtnExisting.classList.add("border-[#09065E]/40", "text-[#09065E]/90", "hover:bg-[#09065E]/5")
        fullAudiobookDownloadBtnExisting.classList.remove("border-green-500", "text-green-600", "bg-green-50")
        fullAudiobookDownloadBtnExisting.disabled = false
        fullAudiobookDownloadBtnExisting.title = "Download all accessible chapters"
      }
    }
  } catch (error) {
    console.error("Error in checkInitialDownloadStates:", error)
  }
}

const reviewForm = document.getElementById("review-form")
const reviewRatingInputContainer = document.getElementById("review-rating-input")
const ratingValueInput = document.getElementById("rating-value-input")
const commentInput = document.getElementById("comment-input")
const ratingError = document.getElementById("rating-error")
const formMessage = document.getElementById("form-message")
const submitReviewBtn = document.getElementById("submit-review-btn")
const reviewsList = document.getElementById("reviews-list")
const reviewCountSpan = document.getElementById("review-count")
const reviewCountTabSpan = document.getElementById("review-count-tab")
const editReviewPrompt = document.getElementById("edit-review-prompt")
const editMyReviewButton = document.getElementById("edit-my-review-button")

function setStarRating(rating) {
  if (!reviewRatingInputContainer) return
  const stars = reviewRatingInputContainer.querySelectorAll(".star-input-icon")
  stars.forEach((star, i) => {
    const isSelected = i < rating
    star.classList.toggle("text-red-500", isSelected)
    star.classList.toggle("text-[#09065E]/30", !isSelected)
  })
  if (ratingValueInput) ratingValueInput.value = rating
  if (ratingError) ratingError.textContent = ""
}

if (reviewRatingInputContainer) {
  const stars = reviewRatingInputContainer.querySelectorAll(".star-input-icon")
  stars.forEach((star) => {
    star.addEventListener("mouseover", () => {
      const rating = Number.parseInt(star.dataset.ratingValue)
      stars.forEach((s, i) => {
        const isHovered = i < rating
        s.classList.toggle("text-red-400", isHovered)
        s.classList.toggle("text-[#09065E]/30", !isHovered && !s.classList.contains("text-red-500"))
      })
    })
    star.addEventListener("mouseout", () => {
      const currentRating = Number.parseInt(ratingValueInput.value)
      setStarRating(currentRating)
    })
    star.addEventListener("click", () => {
      const rating = Number.parseInt(star.dataset.ratingValue)
      setStarRating(rating)
    })
  })
}

function displayReviewInList(reviewData, isNew) {
  if (!reviewsList) return
  const existingReviewElement = document.getElementById(`review-${reviewData.review_id}`)
  if (existingReviewElement) existingReviewElement.remove()

  const reviewItem = document.createElement("article")
  reviewItem.className =
    "review-item flex space-x-4 sm:space-x-5 p-5 sm:p-6 bg-white rounded-xl border border-[#09065E]/20 shadow-lg shadow-[#09065E]/[0.07]"
  reviewItem.id = `review-${reviewData.review_id}`

  let avatarHtml = `<span class="h-12 w-12 sm:h-14 sm:w-14 rounded-full bg-[#09065E]/10 flex items-center justify-center text-[#09065E]/50 border-2 border-white shadow-md"><svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd" /></svg></span>`
  if (reviewData.user_profile_pic) {
    avatarHtml = `<img class="h-12 w-12 sm:h-14 sm:w-14 rounded-full object-cover border-2 border-white shadow-md" src="${reviewData.user_profile_pic}" alt="${reviewData.user_name}">`
  }

  let starsHtml = ""
  for (let i = 0; i < 5; i++) {
    starsHtml += `<svg class="w-4 h-4 ${i < reviewData.rating ? "text-red-500" : "text-[#09065E]/20"}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" /></svg>`
  }

  let editButtonHtml = ""
  const currentUserIdNum =
    typeof pageContext.userId === "string" ? Number.parseInt(pageContext.userId, 10) : pageContext.userId
  if (pageContext.isAuthenticated && reviewData.user_id && currentUserIdNum === reviewData.user_id) {
    editButtonHtml = `<div class="mt-4 text-xs"><button data-review-id="${reviewData.review_id}" data-rating="${reviewData.rating}" data-comment="${reviewData.comment.replace(/"/g, "&quot;")}" class="edit-user-review-button text-red-600 hover:text-red-700 hover:underline font-semibold focus:outline-none focus:ring-1 focus:ring-offset-1 focus:ring-red-500/70 rounded px-1.5 py-0.5 transition-colors duration-150"><svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 inline mr-1 align-text-bottom" viewBox="0 0 20 20" fill="currentColor"><path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" /><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" /></svg>Edit</button></div>`
  }

  reviewItem.innerHTML = `
        <div class="flex-shrink-0 pt-1">${avatarHtml}</div>
        <div class="flex-grow">
            <div class="flex items-baseline justify-between mb-1.5">
                <h5 class="text-lg font-semibold text-[#09065E]">${reviewData.user_name}</h5>
                <time datetime="${reviewData.created_at}" class="flex-shrink-0 ml-4 text-xs text-[#09065E]/60">${reviewData.timesince}</time>
            </div>
            <div class="mb-2.5 flex items-center text-xs space-x-0.5">${starsHtml}</div>
            ${reviewData.comment ? `<div class="text-sm text-[#09065E]/80 prose prose-sm max-w-none leading-relaxed selection:bg-red-200 selection:text-red-800 prose-p:text-[#09065E]/80"><p>${reviewData.comment.replace(/\n/g, "<br>")}</p></div>` : ""}
            ${editButtonHtml}
        </div>`

  const newEditButton = reviewItem.querySelector(".edit-user-review-button")
  if (newEditButton) newEditButton.addEventListener("click", handleEditReviewButtonClick)

  const noReviewsMsg = document.getElementById("no-reviews-message")
  if (noReviewsMsg) noReviewsMsg.style.display = "none"

  if (isNew && reviewsList.firstChild) reviewsList.insertBefore(reviewItem, reviewsList.firstChild)
  else reviewsList.prepend(reviewItem)
}

function handleEditReviewButtonClick(event) {
  const button = event.currentTarget
  const rating = button.dataset.rating
  const comment = button.dataset.comment
  if (reviewForm && ratingValueInput && commentInput) {
    setStarRating(Number.parseInt(rating))
    commentInput.value = comment
    reviewForm.classList.remove("hidden")
    if (editReviewPrompt) editReviewPrompt.classList.add("hidden")
    reviewForm.scrollIntoView({ behavior: "smooth", block: "center" })
    if (formMessage) formMessage.textContent = "Editing your review..."
    if (submitReviewBtn) submitReviewBtn.innerHTML = '<i class="fas fa-save mr-2.5"></i>Update Review'
  }
}

if (editMyReviewButton) editMyReviewButton.addEventListener("click", handleEditReviewButtonClick)
document.querySelectorAll(".edit-user-review-button").forEach((button) => {
  button.addEventListener("click", handleEditReviewButtonClick)
})

if (reviewForm) {
  reviewForm.addEventListener("submit", async (event) => {
    event.preventDefault()
    if (!pageContext.isAuthenticated) {
        showPopup(
            "Authentication Required",
            "Please log in to submit a review.",
            'confirm',
            () => { if (pageContext.loginUrl) window.location.href = pageContext.loginUrl; },
            null,
            "Log In",
            "Cancel"
        );
      return
    }
    if (ratingValueInput.value === "0") {
      if (ratingError) ratingError.textContent = "Please select a rating."
      return
    }
    if (ratingError) ratingError.textContent = ""
    if (formMessage) formMessage.textContent = ""
    const isUpdate = submitReviewBtn.innerHTML.includes("Update")

    const payload = { rating: ratingValueInput.value, comment: commentInput.value.trim() }
    try {
      if (submitReviewBtn) submitReviewBtn.disabled = true
      if (formMessage) formMessage.textContent = "Submitting..."
      if (submitReviewBtn)
        submitReviewBtn.innerHTML =
          '<svg class="animate-spin h-5 w-5 mr-2.5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Submitting...'

      const response = await fetch(pageContext.addReviewUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": pageContext.csrfToken },
        body: JSON.stringify(payload),
      })
      const result = await response.json()

      if (response.ok && result.status === "success") {
        showPopup("Success", result.message, 'success');
        reviewForm.reset()
        setStarRating(0)
        reviewForm.classList.add("hidden")
        if (editReviewPrompt) {
          editReviewPrompt.classList.remove("hidden")
          const promptRatingStarsContainer = editReviewPrompt.querySelector("p.flex.items-center.justify-center")
          if (promptRatingStarsContainer) {
            let starsHtmlPrompt = "Your rating: "
            for (let i = 0; i < 5; i++) {
              starsHtmlPrompt += `<svg class="w-4 h-4 ml-1 ${i < result.review_data.rating ? "text-red-500" : "text-[#09065E]/20"}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" /></svg>`
            }
            promptRatingStarsContainer.innerHTML = starsHtmlPrompt
          }
          const promptCommentP = editReviewPrompt.querySelector("p.italic")
          if (promptCommentP) {
            if (result.review_data.comment) {
              promptCommentP.textContent = `"${result.review_data.comment.substring(0, 50)}${result.review_data.comment.length > 50 ? "..." : ""}"`
              promptCommentP.classList.remove("hidden")
            } else {
              promptCommentP.classList.add("hidden")
            }
          }
          if (editMyReviewButton) {
            editMyReviewButton.dataset.rating = result.review_data.rating
            editMyReviewButton.dataset.comment = result.review_data.comment
          }
        }
        displayReviewInList(result.review_data, result.created)
        if (result.created) {
          const currentTotalReviews = Number.parseInt(reviewCountSpan.textContent) || 0
          if (reviewCountSpan) reviewCountSpan.textContent = currentTotalReviews + 1
          if (reviewCountTabSpan) reviewCountTabSpan.textContent = currentTotalReviews + 1
        }
        const overallAvgRatingDisplayElements = document.querySelectorAll(
          ".lg\\:col-span-8 .flex.items-center.space-x-1\\.5 span.font-semibold.text-\\[\\#09065E\\], .lg\\:col-span-8 .flex.items-center.space-x-1\\.5 span.text-\\[\\#09065E\\].font-semibold.pt-px",
        )
        overallAvgRatingDisplayElements.forEach((el) => {
          if (result.new_average_rating && result.new_average_rating !== "0.0") {
            el.textContent = `${Number.parseFloat(result.new_average_rating).toFixed(1)}`
          }
        })
        if (submitReviewBtn)
          submitReviewBtn.innerHTML =
            '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z"></path><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd"></path></svg>Edit Your Review'
      } else {
        showPopup("Error", result.message || "Could not submit your review.", 'error');
      }
    } catch (error) {
      showPopup("Error", "An unexpected error occurred. Please try again.", 'error');
    } finally {
      if (submitReviewBtn) {
        submitReviewBtn.disabled = false
        if (reviewForm.classList.contains("hidden")) {
          submitReviewBtn.innerHTML =
            '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z"></path><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd"></path></svg>Edit Your Review'
        } else if (isUpdate) {
          submitReviewBtn.innerHTML = '<i class="fas fa-save mr-2.5"></i>Update Review'
        } else {
          submitReviewBtn.innerHTML =
            '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 16.571V11.5a1 1 0 011-1h.094a1 1 0 01.803.424l4.25 5.5a1 1 0 001.6-.25L17.894 3.962a1 1 0 00-.999-1.409l-7 .001z" /></svg>Submit Review'
        }
      }
      if (formMessage) formMessage.textContent = ""
    }
  })
}

const addToLibraryButton = document.getElementById("add-to-library-button")
async function handleAddToLibrary() {
  if (!pageContext.isAuthenticated) {
    showPopup(
      "Login Required",
      "Please log in to add audiobooks to your library.",
      'confirm',
      () => { if (pageContext.loginUrl) window.location.href = pageContext.loginUrl },
      null,
      "Log In",
      "Cancel"
    );
    return
  }
  const audiobookIdLib = addToLibraryButton.dataset.audiobookId
  if (!audiobookIdLib || audiobookIdLib.trim() === "" || audiobookIdLib === "null") {
    showPopup("Error", "Audiobook ID is missing or invalid for library action.", 'error');
    return
  }
  if (!pageContext.addToLibraryApiUrl || pageContext.addToLibraryApiUrl === "#error-parsing-context") {
    showPopup("Configuration Error", "This feature (add to library) is not correctly configured.", 'error');
    return
  }
  
  const originalButtonText = addToLibraryButton.querySelector('#add-to-library-text').textContent;
  addToLibraryButton.querySelector('#add-to-library-text').textContent = "Processing...";
  addToLibraryButton.disabled = true;

  try {
    const response = await fetch(pageContext.addToLibraryApiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": pageContext.csrfToken },
      body: JSON.stringify({ audiobook_id: audiobookIdLib }),
    })
    const result = await response.json()
    
    if (response.ok && result.status === "success") {
      showPopup("Library Updated", result.message || `Library updated for "${pageContext.audiobookTitle}"!`, 'success');
      const btnText = document.getElementById("add-to-library-text")
      const isInLibraryNow = result.is_in_library;
      if (btnText) btnText.textContent = isInLibraryNow ? "In Library" : "Add to Library";

      addToLibraryButton.classList.toggle("bg-[#091e65]", isInLibraryNow);
      addToLibraryButton.classList.toggle("hover:bg-opacity-90", isInLibraryNow);
      addToLibraryButton.classList.toggle("focus:ring-[#091e65]/70", isInLibraryNow);

      addToLibraryButton.classList.toggle("bg-red-600", !isInLibraryNow);
      addToLibraryButton.classList.toggle("hover:bg-red-700", !isInLibraryNow);
      addToLibraryButton.classList.toggle("focus:ring-red-600/70", !isInLibraryNow);

    } else {
        showPopup("Error", result.message || "Could not update library.", 'error');
        addToLibraryButton.querySelector('#add-to-library-text').textContent = originalButtonText;
    }
  } catch (error) {
    showPopup("Request Failed", "An error occurred while updating your library.", 'error');
    addToLibraryButton.querySelector('#add-to-library-text').textContent = originalButtonText;
  } finally {
      addToLibraryButton.disabled = false;
  }
}

const popupOverlay = document.getElementById("audiox-popup-overlay");
const popupContent = document.getElementById("audiox-popup-content");
const popupTitle = document.getElementById("audiox-popup-title");
const popupBody = document.getElementById("audiox-popup-body");
const popupConfirmBtn = document.getElementById("audiox-popup-confirm-btn");
const popupCancelBtn = document.getElementById("audiox-popup-cancel-btn");
const popupCloseBtn = document.getElementById("audiox-popup-close-btn-icon");
let popupConfirmCallback = null;
let popupCancelCallback = null;
let popupTimeout = null;

function showPopup(title, message, type = 'info', confirmCallback = null, cancelCallback = null, confirmText = "OK", cancelText = "Cancel") {
    if (!popupOverlay) { 
        alert(`${title}\n\n${message}`);
        return;
    }
    
    clearTimeout(popupTimeout);

    popupTitle.textContent = title;
    popupBody.innerHTML = message;

    popupConfirmCallback = confirmCallback;
    popupCancelCallback = cancelCallback;

    popupConfirmBtn.textContent = confirmText;
    popupCancelBtn.textContent = cancelText;

    popupConfirmBtn.className = 'px-6 py-2.5 rounded-md text-sm font-semibold text-white transition-colors duration-150';
    popupCancelBtn.className = 'px-6 py-2.5 rounded-md text-sm font-semibold border-2 bg-white hover:bg-[#09065E]/5 transition-colors duration-150';
    
    const isConfirmDialog = type === 'confirm' || (confirmCallback !== null);

    switch(type) {
        case 'error':
            popupConfirmBtn.classList.add('bg-red-600', 'hover:bg-red-700');
            break;
        case 'confirm':
            popupConfirmBtn.classList.add('bg-red-600', 'hover:bg-red-700');
            popupCancelBtn.classList.add('border-[#09065E]', 'text-[#09065E]');
            break;
        case 'info':
        case 'success':
        default:
            popupConfirmBtn.classList.add('bg-[#091e65]', 'hover:bg-opacity-90');
            break;
    }
    
    popupCancelBtn.style.display = isConfirmDialog ? 'inline-flex' : 'none';
    popupConfirmBtn.style.display = 'inline-flex';

    popupOverlay.classList.remove("hidden");
    setTimeout(() => {
        popupOverlay.classList.remove("opacity-0");
        popupContent.classList.remove("opacity-0", "scale-95");
    }, 10);
    
    if (!isConfirmDialog) {
        popupTimeout = setTimeout(() => hidePopup(), 3000);
    }
}

function hidePopup() {
    if (!popupOverlay) return;
    popupOverlay.classList.add("opacity-0");
    popupContent.classList.add("opacity-0", "scale-95");
    setTimeout(() => {
        popupOverlay.classList.add("hidden");
    }, 300);
}

if (popupConfirmBtn) popupConfirmBtn.addEventListener("click", () => {
    if (popupConfirmCallback) popupConfirmCallback();
    hidePopup();
});
if (popupCancelBtn) popupCancelBtn.addEventListener("click", () => {
    if (popupCancelCallback) popupCancelCallback();
    hidePopup();
});
if (popupCloseBtn) popupCloseBtn.addEventListener("click", hidePopup);
if (popupOverlay) popupOverlay.addEventListener("click", (e) => {
    if (e.target === popupOverlay) hidePopup();
});

function openShareModal() {
  if (!pageContext.audiobookTitle) {
    showPopup("Error", "Share feature is not properly configured.", 'error')
    return
  }
  const shareUrl = window.location.href
  const audiobookTitleForShare = pageContext.audiobookTitle || "this audiobook"
  const shareContentHTML = `
    <div class="space-y-4">
        <div>
            <label for="share-link-input" class="block text-sm font-semibold text-[#09065E] mb-1.5">Shareable Link:</label>
            <div class="flex rounded-md shadow-sm border border-[#09065E]/20">
                <input type="text" id="share-link-input" readonly class="flex-1 block w-full rounded-l-md sm:text-sm bg-gray-100 p-2 text-[#09065E] border-0 focus:ring-0" value="${shareUrl}">
                <button id="copy-link-btn" class="inline-flex items-center px-3 py-2 border-l border-[#09065E]/20 text-sm font-medium text-[#09065E] bg-gray-50 hover:bg-gray-100">Copy</button>
            </div>
            <div id="copy-status" class="text-xs text-[#09065E]/70 mt-1.5 min-h-[1rem]"></div>
        </div>
    </div>`;

  showPopup(`Share "${audiobookTitleForShare}"`, shareContentHTML, 'info', hidePopup, null, 'Close');

  const copyBtn = document.getElementById('copy-link-btn');
  const copyStatus = document.getElementById('copy-status');
  if(copyBtn && copyStatus) {
    copyBtn.addEventListener('click', () => {
        const linkInput = document.getElementById('share-link-input');
        linkInput.select();
        try {
            document.execCommand('copy');
            copyStatus.textContent = 'Link copied!';
            copyStatus.style.color = '#091e65';
        } catch (err) {
            copyStatus.textContent = 'Failed to copy.';
            copyStatus.style.color = 'red';
        }
        setTimeout(() => { copyStatus.textContent = ''; }, 2000);
    });
  }
}

function showClipEditor(chapterData) {
  if (
    !chapterClipEditorArea ||
    !clipEditorChapterTitle ||
    !clipEditorPlayer ||
    !clipEditorStartTimeDisplay ||
    !clipEditorEndTimeDisplay ||
    !generateClipBtnInline
  ) {
    showPopup("Error", "Clip creation UI is not available.", 'error')
    return
  }
  if (currentChapterDataForClipping && currentChapterDataForClipping.id !== chapterData.id) hideClipEditor()
  currentChapterDataForClipping = chapterData
  clipEditorChapterTitle.textContent = chapterData.title
  const totalDurationSeconds = Number.parseInt(chapterData.duration, 10)
  selectedClipStartTime = 0
  selectedClipEndTime = totalDurationSeconds > 0 ? Math.min(10, totalDurationSeconds) : 0
  if (selectedClipEndTime <= selectedClipStartTime && totalDurationSeconds > selectedClipStartTime)
    selectedClipEndTime = selectedClipStartTime + Math.min(10, totalDurationSeconds - selectedClipStartTime)
  else if (selectedClipEndTime <= selectedClipStartTime) selectedClipEndTime = selectedClipStartTime

  clipEditorStartTimeDisplay.textContent = formatTime(selectedClipStartTime)
  clipEditorEndTimeDisplay.textContent = formatTime(selectedClipEndTime)

  const onClipEditorPlayerReady = () => {
    clipEditorPlayer.currentTime = 0
    if (clipEditorStatus)
      clipEditorStatus.textContent = 'Use player to find desired start/end, then click "Set" buttons.'
    clipEditorPlayer.removeEventListener("loadedmetadata", onClipEditorPlayerReady)
  }

  let clipAudioUrl = chapterData.audioUrlTemplate
  if (chapterData.id && pageContext.audiobookSlug) {
    const separator = clipAudioUrl.includes("?") ? "&" : "?"
    clipAudioUrl += `${separator}chapter_id=${encodeURIComponent(chapterData.id)}&audiobook_slug=${encodeURIComponent(pageContext.audiobookSlug)}`
  }
  clipEditorPlayer.src = clipAudioUrl

  if (generatedClipAreaInline) generatedClipAreaInline.classList.add("hidden")
  if (generatedClipPlayerInline) generatedClipPlayerInline.src = ""
  if (downloadGeneratedClipLinkInline) downloadGeneratedClipLinkInline.href = "#"
  const generateBtnText = generateClipBtnInline.querySelector(".generate-text-inline")
  const generatingBtnText = generateClipBtnInline.querySelector(".generating-text-inline")
  if (generateBtnText) generateBtnText.classList.remove("hidden")
  if (generatingBtnText) generatingBtnText.classList.add("hidden")
  generateClipBtnInline.disabled = false
  chapterClipEditorArea.classList.remove("hidden")
  const editorTop = chapterClipEditorArea.offsetTop
  const headerOffset = 100
  const scrollPosition = editorTop - headerOffset
  const rect = chapterClipEditorArea.getBoundingClientRect()
  if (rect.top < headerOffset || rect.bottom > window.innerHeight - 50)
    window.scrollTo({ top: scrollPosition, behavior: "smooth" })
}

function hideClipEditor() {
  if (!chapterClipEditorArea) return
  chapterClipEditorArea.classList.add("hidden")
  if (clipEditorPlayer) {
    clipEditorPlayer.pause()
    clipEditorPlayer.src = ""
  }
  if (generatedClipPlayerInline) {
    generatedClipPlayerInline.pause()
    generatedClipPlayerInline.src = ""
  }
  currentChapterDataForClipping = null
  selectedClipStartTime = 0
  selectedClipEndTime = 0
}
if (closeClipEditorBtn) closeClipEditorBtn.addEventListener("click", hideClipEditor)

if (setStartTimeBtn && clipEditorPlayer && clipEditorStartTimeDisplay) {
  setStartTimeBtn.addEventListener("click", () => {
    if (!currentChapterDataForClipping || !clipEditorPlayer || clipEditorPlayer.readyState < 1) {
      if (clipEditorStatus) clipEditorStatus.textContent = "Player not ready. Try again."
      return
    }
    selectedClipStartTime = clipEditorPlayer.currentTime
    const totalDuration = Number.parseInt(currentChapterDataForClipping.duration, 10)
    if (selectedClipStartTime >= selectedClipEndTime || selectedClipEndTime === 0) {
      selectedClipEndTime = Math.min(selectedClipStartTime + 10, totalDuration)
      if (selectedClipEndTime <= selectedClipStartTime && totalDuration > selectedClipStartTime)
        selectedClipEndTime = selectedClipStartTime + Math.min(10, totalDuration - selectedClipStartTime)
      else if (selectedClipEndTime <= selectedClipStartTime) selectedClipEndTime = selectedClipStartTime
    }
    selectedClipStartTime = Math.max(0, selectedClipStartTime)
    if (totalDuration > 0 && selectedClipStartTime >= totalDuration) {
      selectedClipStartTime = totalDuration - 0.1
      selectedClipStartTime = Math.max(0, selectedClipStartTime)
    }
    clipEditorStartTimeDisplay.textContent = formatTime(selectedClipStartTime)
    if (clipEditorStatus) clipEditorStatus.textContent = `Start: ${formatTime(selectedClipStartTime)}. Set End.`
  })
}

if (setEndTimeBtn && clipEditorPlayer && clipEditorEndTimeDisplay) {
  setEndTimeBtn.addEventListener("click", () => {
    if (!currentChapterDataForClipping || !clipEditorPlayer || clipEditorPlayer.readyState < 1) {
      if (clipEditorStatus) clipEditorStatus.textContent = "Player not ready. Try again."
      return
    }
    selectedClipEndTime = clipEditorPlayer.currentTime
    const totalDuration = Number.parseInt(currentChapterDataForClipping.duration, 10)
    selectedClipEndTime = Math.min(selectedClipEndTime, totalDuration)
    if (selectedClipEndTime <= selectedClipStartTime) {
      selectedClipStartTime = Math.max(0, selectedClipEndTime - 0.1)
      if (selectedClipStartTime >= selectedClipEndTime && selectedClipEndTime > 0)
        selectedClipStartTime = Math.max(0, selectedClipEndTime - 1)
      if (clipEditorStartTimeDisplay) clipEditorStartTimeDisplay.textContent = formatTime(selectedClipStartTime)
    }
    selectedClipEndTime = Math.max(selectedClipStartTime + 0.01, selectedClipEndTime)
    selectedClipEndTime = Math.min(selectedClipEndTime, totalDuration)
    clipEditorEndTimeDisplay.textContent = formatTime(selectedClipEndTime)
    if (clipEditorStatus) clipEditorStatus.textContent = `End: ${formatTime(selectedClipEndTime)}. Ready to Generate.`
  })
}

if (generateClipBtnInline) {
  generateClipBtnInline.addEventListener("click", async () => {
    if (!currentChapterDataForClipping) {
        showPopup("Error", "No chapter loaded for clipping.", 'error');
      return
    }
    const preciseStartTime = selectedClipStartTime
    const preciseEndTime = selectedClipEndTime
    if (preciseEndTime <= preciseStartTime) {
      if (clipEditorStatus) clipEditorStatus.textContent = "Invalid time selection: End time must be after start time."
      showPopup("Invalid Time Selection", "Ensure end time is after start time.", 'error');
      return
    }
    const chapterId = currentChapterDataForClipping.id
    const maxClipDuration = pageContext.maxAudioClipDurationSeconds || 300
    if (preciseEndTime - preciseStartTime > maxClipDuration) {
      if (clipEditorStatus) clipEditorStatus.textContent = `Clip too long (max ${formatTime(maxClipDuration)}).`
      showPopup("Clip Too Long", `Maximum clip duration is ${formatTime(maxClipDuration)}.`, 'error');
      return
    }
    if (clipEditorStatus) clipEditorStatus.textContent = "Generating clip, please wait..."
    if (generatedClipAreaInline) generatedClipAreaInline.classList.add("hidden")
    const generateBtnText = generateClipBtnInline.querySelector(".generate-text-inline")
    const generatingBtnText = generateClipBtnInline.querySelector(".generating-text-inline")
    if (generateBtnText) generateBtnText.classList.remove("hidden")
    if (generatingBtnText) generatingBtnText.classList.add("hidden")
    generateClipBtnInline.disabled = false
    const payload = { chapter_id: chapterId, start_time_seconds: preciseStartTime, end_time_seconds: preciseEndTime }
    const clipUrlForFetch = pageContext.generateAudioClipUrl

    try {
      const response = await fetch(clipUrlForFetch, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": pageContext.csrfToken },
        body: JSON.stringify(payload),
      })
      const resultText = await response.text()
      let result
      try {
        result = JSON.parse(resultText)
      } catch (e) {
        throw new Error(`Server returned non-JSON response (status: ${response.status}). Check server logs.`)
      }

      if (response.ok && result.status === "success") {
        if (clipEditorStatus) clipEditorStatus.textContent = "Clip generated successfully!"
        if (generatedClipPlayerInline) generatedClipPlayerInline.src = result.clip_url
        if (downloadGeneratedClipLinkInline) {
          downloadGeneratedClipLinkInline.href = result.clip_url
          downloadGeneratedClipLinkInline.download =
            result.filename || `clip_${chapterId}_${Math.floor(preciseStartTime)}-${Math.floor(preciseEndTime)}.mp3`
        }
        if (generatedClipAreaInline) generatedClipAreaInline.classList.remove("hidden")
        showPopup("Success", "Audio clip created!", 'success');
      } else {
        if (clipEditorStatus) clipEditorStatus.textContent = `Error: ${result.message || "Failed to generate clip."}`
        showPopup("Clip Generation Failed", result.message || "Could not generate the audio clip.", 'error');
      }
    } catch (error) {
      if (clipEditorStatus) clipEditorStatus.textContent = `Error: ${error.message || "Network error."}`
        showPopup("Request Error", `An error occurred: ${error.message || "Please try again."}`, 'error');
    } finally {
      if (generateBtnText) generateBtnText.classList.remove("hidden")
      if (generatingBtnText) generatingBtnText.classList.add("hidden")
      generateClipBtnInline.disabled = false
    }
  })
}

if (shareGeneratedClipBtnInline && generatedClipPlayerInline) {
  shareGeneratedClipBtnInline.addEventListener("click", async () => {
    const clipUrl = generatedClipPlayerInline.src
    const chapterTitleForShare = currentChapterDataForClipping?.title || "Audio Clip"
    const audiobookTitleForShare = pageContext.audiobookTitle || "AudioX"
    if (!clipUrl || clipUrl === window.location.href || clipUrl.startsWith("blob:")) {
        showPopup("Share Error", "Clip not ready or cannot be shared directly. Please download first.", 'info');
      return
    }
    const shareData = {
      title: `Clip from: ${chapterTitleForShare}`,
      text: `Listen to this cool clip from "${chapterTitleForShare}" on ${audiobookTitleForShare}! Listen here: ${clipUrl}`,
      url: clipUrl,
    }
    if (navigator.share && navigator.canShare(shareData)) {
      try {
        await navigator.share(shareData)
        showPopup("Success", "Clip shared!", 'success');
      } catch (err) {
        if (err.name !== "AbortError") showPopup("Share Failed", `Share failed: ${err.message}`, 'error');
      }
    } else {
      try {
        await navigator.clipboard.writeText(clipUrl)
        showPopup("Share Not Available", "Could not automatically share. Link copied to clipboard.", 'info');
      } catch (err) {
        showPopup("Share Not Available", "Could not automatically share.", 'error');
      }
    }
  })
}

function attachClipButtonListeners() {
  document.querySelectorAll(".clip-chapter-btn").forEach((button) => {
    button.addEventListener("click", function () {
      const chapterData = {
        id: this.dataset.chapterId,
        title: this.dataset.chapterTitle,
        duration: this.dataset.chapterDuration,
        audioUrlTemplate: this.dataset.audioUrlTemplate,
      }
      if (
        currentChapterDataForClipping &&
        currentChapterDataForClipping.id !== chapterData.id &&
        chapterClipEditorArea &&
        !chapterClipEditorArea.classList.contains("hidden")
      ) {
        hideClipEditor()
        setTimeout(() => showClipEditor(chapterData), 50)
      } else if (chapterClipEditorArea && chapterClipEditorArea.classList.contains("hidden")) {
        showClipEditor(chapterData)
      } else if (
        currentChapterDataForClipping &&
        currentChapterDataForClipping.id === chapterData.id &&
        chapterClipEditorArea &&
        !chapterClipEditorArea.classList.contains("hidden")
      ) {
        hideClipEditor()
      } else {
        showClipEditor(chapterData)
      }
    })
  })
}

if (
  purchaseButton &&
  pageContext.stripePublishableKey &&
  pageContext.createCheckoutSessionUrl &&
  pageContext.audiobookSlug
) {
  try {
    stripe = Stripe(pageContext.stripePublishableKey)
    purchaseButton.addEventListener("click", async (event) => {
      event.target.disabled = true
      event.target.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...'

      try {
        const response = await fetch(pageContext.createCheckoutSessionUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": pageContext.csrfToken,
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify({
            item_type: "audiobook",
            item_id: pageContext.audiobookSlug,
          }),
        })
        const session = await response.json()

        if (session.error || !session.sessionId) {
          showPopup("Payment Error", session.error || "Failed to create checkout session. Please check item details or contact support.", 'error');
          event.target.disabled = false
          event.target.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${pageContext.audiobookPrice})`
          return
        }

        const result = await stripe.redirectToCheckout({ sessionId: session.sessionId })

        if (result.error) {
          throw new Error(result.error.message)
        }
      } catch (error) {
        showPopup("Payment Error", error.message || "Could not initiate payment. Please try again.", 'error');
        event.target.disabled = false
        event.target.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${pageContext.audiobookPrice})`
      }
    })
  } catch (e) {
    if (purchaseButton) {
      purchaseButton.disabled = true
      purchaseButton.innerHTML = '<i class="fas fa-exclamation-circle mr-2"></i> Payment Init Failed'
    }
  }
} else if (purchaseButton) {
  purchaseButton.disabled = true
  const priceText = pageContext.audiobookPrice ? ` (PKR ${pageContext.audiobookPrice})` : ""
  purchaseButton.innerHTML = `<i class="fas fa-times-circle mr-2"></i> Purchase Unavailable${priceText}`
  purchaseButton.title = "Payment system is currently unavailable for this item."
}

function debugListeningHistory() {
  console.log("[DEBUG] Listening History:", listeningHistory)
}

document.addEventListener("DOMContentLoaded", () => {
  const hash = window.location.hash
  let initialTabId = "about"
  if (hash && hash.startsWith("#content-")) {
    const hashTabId = hash.substring("#content-".length)
    if (document.getElementById(`tab-${hashTabId}`) && document.getElementById(`content-${hashTabId}`)) {
      initialTabId = hashTabId
    }
  }
  showTab(initialTabId)

  if (!audioPlayer || !audioPlayer.getAttribute("src")) hidePlayerBar()
  if (playerPrevButton) playerPrevButton.disabled = true
  if (playerNextButton) playerNextButton.disabled = true
  if (playerSpeedButton) playerSpeedButton.textContent = `${playbackSpeeds[currentSpeedIndex]}x`

  const playFirstChapterBtn = document.getElementById("play-first-chapter-btn")
  if (playFirstChapterBtn && chapterItems.length > 0) {
    playFirstChapterBtn.addEventListener("click", (e) => {
      e.preventDefault()
      e.stopPropagation()

      const firstChapterPlayButton = chapterItems[0]?.querySelector(".play-button")
      if (firstChapterPlayButton && chapterItems[0]?.dataset.isAccessible === "true") {
        playChapter(firstChapterPlayButton)
      } else if (chapterItems.length > 0 && chapterItems[0]?.dataset.isAccessible !== "true") {
        showPopup("Locked", "First episode is locked.", 'info');
      } else {
        showPopup("Unavailable", "First episode is not available.", 'info');
      }
    })
  }

  if (addToLibraryButton) {
    addToLibraryButton.addEventListener("click", async (e) => {
      e.preventDefault()
      e.stopPropagation()
      await handleAddToLibrary()
    })
  }

  if (shareButton) {
    shareButton.addEventListener("click", (e) => {
      e.preventDefault()
      e.stopPropagation()
      openShareModal()
    })
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", (e) => {
      e.preventDefault()
      e.stopPropagation()

      const tabId = tab.id.replace("tab-", "")
      showTab(tabId)
    })
  })

  document.querySelectorAll('[id^="unlock-btn-"]').forEach((button) => {
    button.addEventListener("click", (e) => {
      e.preventDefault()
      e.stopPropagation()

      const chapterId = button.id.replace("unlock-btn-", "")
      unlockChapterWithCoins(chapterId)
    })
  })

  initializeChapterProgressBars()
  attachChapterDownloadListeners()
  attachClipButtonListeners()
  debugListeningHistory()

  const MGR_CHECK_INTERVAL = 100
  const MGR_CHECK_TIMEOUT = 5000
  let time_elapsed = 0
  function attemptInitDownloadsCheck() {
    if (window.OfflineManager && typeof window.OfflineManager.initDB === "function") {
      window.OfflineManager.initDB()
        .then(() => {
          if (typeof window.OfflineManager.isChapterDownloaded === "function") {
            checkInitialDownloadStates()
          }
        })
        .catch((err) => console.error("Failed to init DB for initial download state check:", err))
    } else {
      time_elapsed += MGR_CHECK_INTERVAL
      if (time_elapsed < MGR_CHECK_TIMEOUT) {
        setTimeout(attemptInitDownloadsCheck, MGR_CHECK_INTERVAL)
      } else {
        document.querySelectorAll(".download-chapter-btn, #download-full-audiobook-btn").forEach((btn) => {
          btn.style.display = "none"
          const btnContainer = btn.closest(".chapter-download-container")
          if (btnContainer) {
            const statusEl = btnContainer.querySelector(".chapter-download-status")
            if (statusEl) statusEl.textContent = "Offline N/A"
          }
        })
        if (fullAudiobookStatusMessagesExisting)
          fullAudiobookStatusMessagesExisting.textContent = "Offline features unavailable."
      }
    }
  }
  attemptInitDownloadsCheck()

  window.addEventListener("beforeunload", () => {
    if (
      pageContext.isAuthenticated &&
      audioPlayer &&
      !audioPlayer.paused &&
      audioPlayer.src &&
      currentChapterIndex >= 0
    ) {
      sendListeningProgress(true)
    }
  })

  if (pageContext.isAuthenticated && pageContext.audiobookId && pageContext.recordVisitUrl) {
    fetch(pageContext.recordVisitUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": pageContext.csrfToken },
      body: JSON.stringify({ audiobook_id: pageContext.audiobookId }),
    }).catch((err) => console.warn("Failed to record visit:", err))
  }

  checkCoinPurchaseEligibility()
  if (document.getElementById("coinPurchaseBtn")) {
    document.getElementById("coinPurchaseBtn").addEventListener("click", purchaseWithCoins)
  }
})