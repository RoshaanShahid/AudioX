// static/js/audiobook_detail.js

// --- DOM Elements ---
const audioPlayer = document.getElementById("audioPlayer"); // Main bottom player
const bottomPlayerBar = document.getElementById("bottom-player-bar");
const playerCoverImage = document.getElementById("player-cover-image");
const playerEpisodeNumber = document.getElementById("player-episode-number");
const playerEpisodeTitle = document.getElementById("player-episode-title");
const playerPlayPauseButton = document.getElementById("player-play-pause-button");
const playerPlayIcon = document.getElementById("player-play-icon");
const playerPauseIcon = document.getElementById("player-pause-icon");
const playerPrevButton = document.getElementById("player-prev-button");
const playerNextButton = document.getElementById("player-next-button");
const playerCurrentTime = document.getElementById("player-current-time");
const playerDuration = document.getElementById("player-duration");
const playerSeekBar = document.getElementById("player-seek-bar");
const playerSpeedButton = document.getElementById("player-speed-button");
const mainCoverImageElement = document.getElementById("main-cover-image");
const placeholderCoverSrc = 'https://placehold.co/80x80/09065E/FFFFFF?text=N/A&font=sans'; // Updated placeholder color

const chapterItems = document.querySelectorAll('.chapter-item');
let currentChapterIndex = -1; // For main bottom player
let currentlyPlayingListItemButton = null; // For main bottom player

const playbackSpeeds = [1, 1.5, 2, 0.75]; // Added 0.75x from creator_details
let currentSpeedIndex = 0;
const THEME_COLOR = '#DC2626'; // Using red-600 as a general theme color from the detail page

// --- START: DOM Elements for Inline Clip Editor ---
const chapterClipEditorArea = document.getElementById('chapter-clip-editor-area');
const clipEditorChapterTitle = document.getElementById('clip-editor-chapter-title');
const closeClipEditorBtn = document.getElementById('close-clip-editor-btn');
const clipEditorPlayer = document.getElementById('clip-editor-player');
const setStartTimeBtn = document.getElementById('set-start-time-btn');
const clipEditorStartTimeDisplay = document.getElementById('clip-editor-start-time-display');
const setEndTimeBtn = document.getElementById('set-end-time-btn');
const clipEditorEndTimeDisplay = document.getElementById('clip-editor-end-time-display');
const generateClipBtnInline = document.getElementById('generate-clip-btn-inline');
const clipEditorStatus = document.getElementById('clip-editor-status');
const generatedClipAreaInline = document.getElementById('generated-clip-area-inline');
const generatedClipPlayerInline = document.getElementById('generated-clip-player-inline');
const downloadGeneratedClipLinkInline = document.getElementById('download-generated-clip-link-inline');
const shareGeneratedClipBtnInline = document.getElementById('share-generated-clip-btn-inline');

let currentChapterDataForClipping = null;
let selectedClipStartTime = 0.0;
let selectedClipEndTime = 0.0;
// --- END: DOM Elements for Inline Clip Editor ---

// --- START: DOM Elements for Share Modal ---
const shareButton = document.getElementById('share-button');
const shareModalContentTemplate = document.getElementById('share-modal-content-template');
// --- END: DOM Elements for Share Modal ---

// --- START: ADDED for Listening Progress ---
let lastProgressUpdateTime = 0;
const progressUpdateInterval = 5000; // Send update every 5 seconds in milliseconds
// --- END: ADDED for Listening Progress ---

// --- START: Stripe Purchase Elements (from audiobook_creator_details.js) ---
const purchaseButton = document.getElementById('purchase-button'); // This ID must exist in the unified HTML
let stripe = null; // Stripe instance
// --- END: Stripe Purchase Elements ---


let pageContext = {};
try {
    const contextElement = document.getElementById('page-context-data-detail');
    if (contextElement && contextElement.textContent) {
        pageContext = JSON.parse(contextElement.textContent);
    } else {
        console.warn("Page context data element 'page-context-data-detail' not found or empty. Using defaults.");
        pageContext = {};
    }

    // Fallbacks for essential properties, ensuring URLs are correctly structured.
    // From audiobook_detail.js
    pageContext.generateAudioClipUrl = pageContext.generateAudioClipUrl || "/api/clip/generate/";
    if (pageContext.audiobookId && pageContext.audiobookId !== '0' && (!pageContext.getAiSummaryUrl || pageContext.getAiSummaryUrl.includes('/0/'))) {
        pageContext.getAiSummaryUrl = `/audiobook/${pageContext.audiobookId}/get-ai-summary/`;
    }
    pageContext.updateListeningProgressUrl = pageContext.updateListeningProgressUrl || "URL_NOT_DEFINED_update_listening_progress";
    if (!pageContext.csrfToken) {
        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        pageContext.csrfToken = csrfInput ? csrfInput.value : '';
        if (!pageContext.csrfToken) console.error("CRITICAL: CSRF token is missing.");
    }
    pageContext.isAuthenticated = pageContext.isAuthenticated || false;
    pageContext.audiobookTitle = pageContext.audiobookTitle || "This Audiobook";

    // From audiobook_creator_details.js (relevant for Stripe, ensure these are in view's page_context_for_js)
    pageContext.stripePublishableKey = pageContext.stripePublishableKey || null;
    pageContext.createCheckoutSessionUrl = pageContext.createCheckoutSessionUrl || null;
    // We need audiobookSlug and price for creator books for Stripe
    // audiobookSlug is already in pageContext
    pageContext.audiobookPrice = pageContext.audiobookPrice || "0.00"; // Added from creator_details context


} catch (e) {
    console.error("Error parsing page context data:", e, ". Using fallback defaults for all context properties.");
    pageContext = {
        isAuthenticated: false, audiobookId: null, audiobookSlug: null,
        audiobookTitle: "This Audiobook", audiobookAuthor: "Unknown Author",
        audiobookLanguage: "N/A", audiobookGenre: "N/A", isCreatorBook: false,
        csrfToken: document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '',
        addReviewUrl: '#error-parsing-context', addToLibraryApiUrl: '#error-parsing-context',
        myLibraryUrl: '/', loginUrl: '/login/', getAiSummaryUrl: `/audiobook/0/get-ai-summary/`,
        updateListeningProgressUrl: "URL_NOT_DEFINED_update_listening_progress",
        postChapterCommentUrlBase: "URL_NOT_DEFINED_post_chapter_comment",
        getChapterCommentsUrlBase: "URL_NOT_DEFINED_get_chapter_comments",
        generateAudioClipUrl: "/api/clip/generate/", userId: null, userFullName: null, userProfilePicUrl: null,
        // Stripe related fallbacks
        stripePublishableKey: null, createCheckoutSessionUrl: null, audiobookPrice: "0.00"
    };
}


// --- Utility Functions ---
function formatTime(seconds) {
    const roundedSeconds = Math.floor(seconds);
    if (isNaN(roundedSeconds) || roundedSeconds < 0) return '0:00';
    const minutes = Math.floor(roundedSeconds / 60);
    const secs = Math.floor(roundedSeconds % 60);
    return `${minutes}:${secs < 10 ? '0' : ''}${secs}`;
}

// --- Tab Navigation ---
const tabs = document.querySelectorAll('.tab-button');
const tabContents = document.querySelectorAll('.tab-content');
let aiSummaryLoaded = false;
function showTab(tabId) {
    tabContents.forEach(content => content.classList.add('hidden'));
    tabs.forEach(tab => {
        // Updated class management for Tailwind from audiobook_detail.html's style
        const isSelected = tab.id === `tab-${tabId}`;
        tab.classList.toggle('text-red-600', isSelected);
        tab.classList.toggle('border-red-600', isSelected);
        tab.classList.toggle('font-semibold', isSelected);
        tab.classList.toggle('text-[#09065E]/60', !isSelected); // primary text color from theme
        tab.classList.toggle('hover:text-red-600', !isSelected);
        tab.classList.toggle('hover:border-red-500/80', !isSelected);
        tab.classList.toggle('border-transparent', !isSelected);
        tab.classList.toggle('font-medium', !isSelected); // Default to medium if not selected
        tab.setAttribute('aria-current', isSelected ? 'page' : 'false');
    });
    const contentToShow = document.getElementById(`content-${tabId}`);
    if (contentToShow) contentToShow.classList.remove('hidden');

    // Logic for AI summary from audiobook_detail.js
    const selectedTabButton = document.getElementById(`tab-${tabId}`);
    if (selectedTabButton) { // Ensure button exists
         if (tabId === 'summaries' && !aiSummaryLoaded) {
            fetchAiSummary();
        }
    }
}


// --- AI Summary Fetching Logic (from audiobook_detail.js) ---
const aiSummaryPlaceholder = document.getElementById('ai-summary-placeholder');
const aiSummaryLoading = document.getElementById('ai-summary-loading');
const aiSummaryContent = document.getElementById('ai-summary-content');
const aiSummaryError = document.getElementById('ai-summary-error');
const regenerateSummaryBtn = document.getElementById('regenerate-ai-summary-btn');
async function fetchAiSummary() {
    const currentAudiobookId = pageContext.audiobookId;
    if (!currentAudiobookId || currentAudiobookId === '0' || currentAudiobookId === '') {
        if(aiSummaryPlaceholder) aiSummaryPlaceholder.classList.add('hidden');
        if(aiSummaryError) { aiSummaryError.textContent = 'Could not load summary: Audiobook ID missing or invalid.'; aiSummaryError.classList.remove('hidden'); }
        if(aiSummaryLoading) aiSummaryLoading.classList.add('hidden');
        if(regenerateSummaryBtn) regenerateSummaryBtn.disabled = false;
        return;
    }
    if(aiSummaryPlaceholder) aiSummaryPlaceholder.classList.add('hidden');
    if(aiSummaryContent) aiSummaryContent.classList.add('hidden');
    if(aiSummaryError) aiSummaryError.classList.add('hidden');
    if(aiSummaryLoading) aiSummaryLoading.classList.remove('hidden');
    if(regenerateSummaryBtn) regenerateSummaryBtn.disabled = true;
    const summaryUrl = pageContext.getAiSummaryUrl;
    if (!summaryUrl || summaryUrl.includes("URL_NOT_DEFINED") || (summaryUrl.includes('/0/get-ai-summary/') && currentAudiobookId !== '0') ) {
        if(aiSummaryError) { aiSummaryError.textContent = 'Could not load summary: Configuration error for summary URL.'; aiSummaryError.classList.remove('hidden'); }
        if(aiSummaryLoading) aiSummaryLoading.classList.add('hidden');
        if(regenerateSummaryBtn) regenerateSummaryBtn.disabled = false;
        return;
    }
    try {
        const response = await fetch(summaryUrl);
        if (!response.ok) {
            let errorMsg = `Error ${response.status}: ${response.statusText}`;
            try { const errData = await response.json(); errorMsg = errData.message || errData.error || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        const data = await response.json();
        if (data.status === 'success' && data.summary) {
            if(aiSummaryContent) {
                aiSummaryContent.innerHTML = `<p class="text-sm text-gray-500 mb-2">Summary for "<strong>${data.title || pageContext.audiobookTitle}</strong>"${data.language_of_summary ? ` (in ${data.language_of_summary})` : ''}:</p><div class="prose prose-sm max-w-none">${data.summary.replace(/\n/g, '<br>')}</div>`;
                aiSummaryContent.classList.remove('hidden');
            }
            aiSummaryLoaded = true;
        } else { throw new Error(data.message || data.error || 'Summary not found or error in response.'); }
    } catch (error) {
        console.error('Error fetching AI summary:', error);
        if(aiSummaryError) { aiSummaryError.textContent = `Failed to load summary: ${error.message}`; aiSummaryError.classList.remove('hidden');}
    } finally {
        if(aiSummaryLoading) aiSummaryLoading.classList.add('hidden');
        if(regenerateSummaryBtn) regenerateSummaryBtn.disabled = false;
    }
}
if (regenerateSummaryBtn) regenerateSummaryBtn.addEventListener('click', () => fetchAiSummary());


// --- START: Function to Send Listening Progress (from audiobook_detail.js) ---
async function sendListeningProgress(forceUpdate = false) {
    if (!pageContext.isAuthenticated || !audioPlayer.src || audioPlayer.src === window.location.href) {
        return;
    }
    if (!pageContext.audiobookId || pageContext.audiobookId === '0' || pageContext.audiobookId === '' || pageContext.audiobookId === null) {
        console.warn("Cannot update listening progress: pageContext.audiobookId is missing or invalid.");
        return;
    }
    if (!pageContext.updateListeningProgressUrl || pageContext.updateListeningProgressUrl === "URL_NOT_DEFINED_update_listening_progress") {
        console.warn("sendListeningProgress: updateListeningProgressUrl is not defined in pageContext. History updates will fail.");
        return; 
    }
     if (!pageContext.csrfToken) {
        console.error("sendListeningProgress: CSRF token is missing. Cannot send progress.");
        return;
    }

    const currentTimeMs = Date.now();
    if (!forceUpdate && (currentTimeMs - lastProgressUpdateTime < progressUpdateInterval)) {
        return;
    }

    let progressSeconds = Math.floor(audioPlayer.currentTime);
    const durationSeconds = Math.floor(audioPlayer.duration);

    if (durationSeconds > 0 && progressSeconds > durationSeconds) {
        progressSeconds = durationSeconds;
    }
    if (progressSeconds < 0) {
        return;
    }

    const audiobookId = pageContext.audiobookId;
    let chapterId = null;

    const currentChapterPlayingItem = chapterItems[currentChapterIndex];
    if (currentChapterPlayingItem && currentChapterPlayingItem.dataset.chapterId) {
        chapterId = currentChapterPlayingItem.dataset.chapterId;
    } else if (audioPlayer.dataset.currentChapterIdForProgress) {
        chapterId = audioPlayer.dataset.currentChapterIdForProgress;
    }
    
    const payload = {
        audiobook_id: audiobookId,
        progress_seconds: progressSeconds,
    };
    if (chapterId && chapterId !== 'undefined' && chapterId !== 'null' && chapterId !== '') {
        payload.chapter_id = chapterId;
    }

    console.log(`Sending progress (Force: ${forceUpdate}):`, JSON.stringify(payload), "To URL:", pageContext.updateListeningProgressUrl);

    try {
        const response = await fetch(pageContext.updateListeningProgressUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': pageContext.csrfToken
            },
            body: JSON.stringify(payload)
        });

        lastProgressUpdateTime = currentTimeMs; 

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ message: `Server error: ${response.status}` }));
            console.error('Failed to update listening progress (server response not OK):', response.status, errorData.message, "Payload sent:", payload);
        } else {
            const result = await response.json();
            if (result.status === 'success') {
                console.log('Listening progress updated successfully via backend.');
            } else {
                console.error('Error updating listening progress (server status not success):', result.message, "Payload sent:", payload);
            }
        }
    } catch (error) {
        console.error('Network or other error while updating listening progress:', error, "Payload sent:", payload);
    }
}
// --- END: Function to Send Listening Progress ---


// --- Main Bottom Player Logic (from audiobook_detail.js) ---
function updatePlayerUIState(state) {
    if (playerPlayIcon) playerPlayIcon.classList.toggle('hidden', state === 'playing' || state === 'loading');
    if (playerPauseIcon) playerPauseIcon.classList.toggle('hidden', state !== 'playing');
    if (currentlyPlayingListItemButton) {
        updateListItemButtonState(currentlyPlayingListItemButton, state);
    }
}
function updateListItemButtonState(listItemButton, state) {
    if (!listItemButton) return;
    const playIcon = listItemButton.querySelector('.play-icon');
    const pauseIcon = listItemButton.querySelector('.pause-icon');
    const loadingIcon = listItemButton.querySelector('.loading-icon');
    const chapterItemDiv = listItemButton.closest('.chapter-item');

    if (playIcon) playIcon.classList.add('hidden');
    if (pauseIcon) pauseIcon.classList.add('hidden');
    if (loadingIcon) loadingIcon.classList.add('hidden');

    // Reset button-specific classes
    listItemButton.classList.remove('bg-pink-100', 'text-pink-600', 'hover:bg-pink-200', 'animate-pulse');
    listItemButton.classList.add('bg-red-100', 'text-red-700', 'hover:bg-red-200'); // Default style from audiobook_detail

    // Reset chapter item playing styles
    if (chapterItemDiv) {
        chapterItemDiv.classList.remove('playing', 'bg-red-100', 'border-l-red-600'); // Removed specific playing styles
        // Default chapter item styles (if any, or handled by Tailwind directly)
    }

    if (state === 'playing') {
        if (pauseIcon) pauseIcon.classList.remove('hidden');
        listItemButton.classList.remove('bg-red-100', 'text-red-700', 'hover:bg-red-200');
        listItemButton.classList.add('bg-pink-100', 'text-pink-600', 'hover:bg-pink-200'); // Active playing style
        if (chapterItemDiv) chapterItemDiv.classList.add('playing', 'bg-red-100', 'border-l-red-600'); // Add 'playing' class and specific styles
    } else if (state === 'loading') {
        if (loadingIcon) loadingIcon.classList.remove('hidden');
        listItemButton.classList.add('animate-pulse');
    } else { // paused or error
        if (playIcon) playIcon.classList.remove('hidden');
    }
}

function showPlayerBar() { if (bottomPlayerBar) bottomPlayerBar.classList.remove('translate-y-full'); }
function hidePlayerBar() { if (bottomPlayerBar) bottomPlayerBar.classList.add('translate-y-full'); }

function updatePlayerInfo(chapterIndexValue) {
    if (chapterIndexValue < 0 || chapterIndexValue >= chapterItems.length) return;
    const chapterItem = chapterItems[chapterIndexValue];
    if (!chapterItem) return;
    const title = chapterItem.dataset.chapterTitle || 'Unknown Title';
    const episodeNum = chapterIndexValue + 1; // Using simple index for player display
    const totalEpisodes = chapterItems.length;

    if(playerEpisodeTitle) { playerEpisodeTitle.textContent = title; playerEpisodeTitle.title = title; }
    if(playerEpisodeNumber) playerEpisodeNumber.textContent = `Episode ${episodeNum}/${totalEpisodes}`;
    if(playerCoverImage && mainCoverImageElement) {
        playerCoverImage.src = (mainCoverImageElement.tagName === 'IMG' && mainCoverImageElement.src)
                                 ? mainCoverImageElement.src : placeholderCoverSrc;
    } else if (playerCoverImage) { playerCoverImage.src = placeholderCoverSrc; }

    if(playerPrevButton) playerPrevButton.disabled = (chapterIndexValue <= 0);
    if(playerNextButton) playerNextButton.disabled = (chapterIndexValue >= totalEpisodes - 1);
}

window.playChapter = function(buttonElement) { // Made global for onclick in template
    const chapterItem = buttonElement.closest('.chapter-item');
    if (!chapterItem) { showCustomAlert('Player Error', 'Could not find chapter data.', 'error'); return; }

    const audioUrlTemplate = chapterItem.dataset.audioUrlTemplate;
    const chapterTitle = chapterItem.dataset.chapterTitle || 'Episode';
    const chapterIndexFromData = parseInt(chapterItem.dataset.chapterIndex ?? '-1', 10);
    const isAccessible = chapterItem.dataset.isAccessible === 'true';
    const chapterIdForProgress = chapterItem.dataset.chapterId;

    if (!isAccessible) { showCustomAlert('Chapter Locked', 'This chapter is not accessible.', 'warning'); return; }
    if (typeof audioUrlTemplate !== 'string' || audioUrlTemplate.trim() === '' || !audioUrlTemplate.includes('?url=')) {
        showCustomAlert('Audio Link Problem', `Could not prepare audio link for "${chapterTitle}".`, 'error');
        if (buttonElement) updateListItemButtonState(buttonElement, 'error'); return;
    }
    if (audioUrlTemplate.endsWith("?url=")) {
        showCustomAlert('Audio Source Missing', `Audio source for "${chapterTitle}" is missing.`, 'error');
        if (buttonElement) updateListItemButtonState(buttonElement, 'error'); return;
    }
    let audioUrl = audioUrlTemplate;
    if (chapterIndexFromData < 0) {
        showCustomAlert('Chapter Data Error', `Could not load data for "${chapterTitle}".`, 'error');
        if (buttonElement) updateListItemButtonState(buttonElement, 'error'); return;
    }

    const isPlayingThisChapter = (currentlyPlayingListItemButton === buttonElement && audioPlayer.src === audioUrl && !audioPlayer.paused);
    if (isPlayingThisChapter) {
        audioPlayer.pause();
    } else {
        if (currentlyPlayingListItemButton && currentlyPlayingListItemButton !== buttonElement) {
            updateListItemButtonState(currentlyPlayingListItemButton, 'paused');
        }
        currentChapterIndex = chapterIndexFromData;
        currentlyPlayingListItemButton = buttonElement;

        if (audioPlayer && chapterIdForProgress) {
            audioPlayer.dataset.currentChapterIdForProgress = chapterIdForProgress;
        } else if (audioPlayer) {
            delete audioPlayer.dataset.currentChapterIdForProgress;
        }

        updateListItemButtonState(currentlyPlayingListItemButton, 'loading');
        updatePlayerUIState('loading');
        updatePlayerInfo(currentChapterIndex);
        showPlayerBar();
        audioPlayer.src = audioUrl;
        audioPlayer.load();
        audioPlayer.play().catch(e => handlePlaybackError(e, chapterTitle));
    }
}

function handlePlaybackError(e, chapterTitle = "the selected audio") {
    let errorUserTitle = 'Playback Error'; let errorUserText = `Could not play ${chapterTitle}.`;
    console.error("Playback error caught:", e, "for chapter:", chapterTitle, "Audio src:", audioPlayer.src);
    if (e && e.name) {
        if (e.name === 'NotAllowedError') { errorUserTitle = 'Autoplay Blocked'; errorUserText = `Playback for ${chapterTitle} was prevented. Click play again.`; }
        else if (e.name === 'AbortError') { errorUserTitle = 'Load Interrupted'; errorUserText = `Loading for ${chapterTitle} interrupted.`; }
        else if (e.name === 'NotSupportedError') { errorUserTitle = 'Format Not Supported'; errorUserText = `Audio format for ${chapterTitle} may not be supported.`;}
    }
    if (audioPlayer.error) { console.error("Audio Element Error:", audioPlayer.error); errorUserText = `Failed to load ${chapterTitle}. (Code: ${audioPlayer.error.code})`;}
    showCustomAlert(errorUserTitle, errorUserText, 'error');
    updatePlayerUIState('error');
    if(currentlyPlayingListItemButton) updateListItemButtonState(currentlyPlayingListItemButton, 'paused');
}

window.togglePlayPause = function() { // Made global
    if (currentChapterIndex < 0 || !audioPlayer.src || audioPlayer.src === window.location.href ) {
        const firstChapterButton = chapterItems[0]?.querySelector('.play-button');
        if (firstChapterButton && chapterItems[0]?.dataset.isAccessible === 'true') playChapter(firstChapterButton);
        else if (chapterItems.length > 0 && chapterItems[0]?.dataset.isAccessible !== 'true') showCustomToast('First episode is locked.', 'warning');
        else showCustomToast('Select an episode to play', 'info');
        return;
    }
    if (audioPlayer.paused || audioPlayer.ended) audioPlayer.play().catch(e => handlePlaybackError(e, playerEpisodeTitle.textContent));
    else audioPlayer.pause();
}

window.playNextChapter = function() { // Made global
    const nextIndex = currentChapterIndex + 1;
    if (nextIndex < chapterItems.length) {
        const nextChapterItem = chapterItems[nextIndex];
        if (nextChapterItem?.dataset.isAccessible === 'true') {
            const playButton = nextChapterItem.querySelector('.play-button'); if (playButton) playChapter(playButton);
        } else { showCustomToast('Next chapter is locked.', 'info'); updatePlayerUIState('ended'); }
    } else { showCustomToast('End of audiobook reached.', 'info'); updatePlayerUIState('ended');}
}

window.playPreviousChapter = function() { // Made global
    const prevIndex = currentChapterIndex - 1;
    if (prevIndex >= 0) {
        const prevChapterItem = chapterItems[prevIndex];
        if (prevChapterItem?.dataset.isAccessible === 'true') {
            const playButton = prevChapterItem.querySelector('.play-button'); if (playButton) playChapter(playButton);
        } else { showCustomToast('Previous chapter is locked.', 'info'); }
    }
}

window.closePlayer = function() { // Made global
    audioPlayer.pause(); audioPlayer.src = ''; hidePlayerBar();
    if(currentlyPlayingListItemButton) updateListItemButtonState(currentlyPlayingListItemButton, 'paused');
    currentlyPlayingListItemButton = null; currentChapterIndex = -1;
    if(playerSeekBar) playerSeekBar.value = 0;
    if(playerCurrentTime) playerCurrentTime.textContent = '0:00';
    if(playerDuration) playerDuration.textContent = '0:00';
    if(playerEpisodeTitle) playerEpisodeTitle.textContent = 'Select an episode';
    if(playerEpisodeNumber) playerEpisodeNumber.textContent = 'Episode N/A';
    if(playerCoverImage) playerCoverImage.src = placeholderCoverSrc;
    if(playerPrevButton) playerPrevButton.disabled = true;
    if(playerNextButton) playerNextButton.disabled = true;
    currentSpeedIndex = 0; audioPlayer.playbackRate = playbackSpeeds[currentSpeedIndex];
    if(playerSpeedButton) playerSpeedButton.textContent = `${playbackSpeeds[currentSpeedIndex]}x`;
    updatePlayerUIState('paused');
}

window.cyclePlaybackSpeed = function() { // Made global
    currentSpeedIndex = (currentSpeedIndex + 1) % playbackSpeeds.length;
    const newSpeed = playbackSpeeds[currentSpeedIndex];
    audioPlayer.playbackRate = newSpeed;
    if(playerSpeedButton) playerSpeedButton.textContent = `${newSpeed}x`;
}

if (audioPlayer) {
    audioPlayer.addEventListener('play', () => { updatePlayerUIState('playing'); sendListeningProgress(true); });
    audioPlayer.addEventListener('pause', () => { updatePlayerUIState('paused'); if (audioPlayer.src && audioPlayer.src !== window.location.href && audioPlayer.currentTime > 0) sendListeningProgress(true); });
    audioPlayer.addEventListener('ended', () => {
        updatePlayerUIState('ended');
        if (audioPlayer.src && audioPlayer.src !== window.location.href && audioPlayer.currentTime > 0 && isFinite(audioPlayer.duration) && audioPlayer.duration > 0) {
            sendListeningProgress(true); // Send final progress as 'ended'
        }
        playNextChapter();
    });
    audioPlayer.addEventListener('error', (e) => {
        let contextMessage = "audio track";
        if (currentChapterIndex >= 0 && chapterItems[currentChapterIndex]) contextMessage = `"${chapterItems[currentChapterIndex].dataset.chapterTitle}"`;
        handlePlaybackError(e, contextMessage);
    });
    audioPlayer.addEventListener('loadedmetadata', () => {
        if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
            if(playerDuration) playerDuration.textContent = formatTime(audioPlayer.duration);
            if(playerSeekBar) playerSeekBar.max = audioPlayer.duration;
        } else { if(playerDuration) playerDuration.textContent = '--:--'; if(playerSeekBar) playerSeekBar.max = 0; }
        if(playerCurrentTime) playerCurrentTime.textContent = '0:00'; if(playerSeekBar) playerSeekBar.value = 0;
    });
    audioPlayer.addEventListener('timeupdate', () => {
        if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
            if(playerCurrentTime) playerCurrentTime.textContent = formatTime(audioPlayer.currentTime);
            if(playerSeekBar && !playerSeekBar.matches(':active')) playerSeekBar.value = audioPlayer.currentTime; // Check if user is not dragging
            sendListeningProgress();
        }
    });
}

if (playerSeekBar) {
    playerSeekBar.addEventListener('input', () => {
        if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration) && audioPlayer.readyState >= 1) audioPlayer.currentTime = playerSeekBar.value;
    });
}


// --- Downloads Code (from audiobook_detail.js) ---
const fullAudiobookDownloadBtnExisting = document.getElementById('download-full-audiobook-btn');
const fullAudiobookDownloadTextExisting = document.getElementById('download-full-audiobook-text');
const fullAudiobookStatusMessagesExisting = document.getElementById('download-status-messages');
const fullAudiobookProgressBarContainerExisting = document.getElementById('overall-download-progress-bar-container');
const fullAudiobookProgressBarExisting = document.getElementById('overall-download-progress-bar');

function updateChapterDownloadButtonUI(button, status, data) {
    if (!button) return;
    const container = button.closest('.chapter-download-container');
    const downloadIcon = button.querySelector('.download-icon');
    const downloadedIcon = button.querySelector('.downloaded-icon');
    const downloadingIcon = button.querySelector('.downloading-icon');
    const statusSpan = container?.querySelector('.chapter-download-status');

    if (downloadIcon) downloadIcon.classList.add('hidden');
    if (downloadedIcon) downloadedIcon.classList.add('hidden');
    if (downloadingIcon) downloadingIcon.classList.add('hidden');
    button.disabled = false;

    if (statusSpan) {
        if (status === 'downloading') {
            if (typeof data === 'number') statusSpan.textContent = `${data}%`;
            else if (typeof data === 'string' && data) statusSpan.textContent = data;
            else statusSpan.textContent = 'Preparing...';
        } else if (status === 'downloaded') statusSpan.textContent = 'Saved';
        else if (status === 'error') statusSpan.textContent = (typeof data === 'string' && data) ? data : 'Error';
        else statusSpan.textContent = (typeof data === 'string' && data) ? data : '';
    }

    switch (status) {
        case 'downloading': if (downloadingIcon) downloadingIcon.classList.remove('hidden'); button.disabled = true; button.title = "Downloading episode..."; break;
        case 'downloaded': if (downloadedIcon) downloadedIcon.classList.remove('hidden'); button.disabled = true; button.title = "Episode downloaded"; break;
        case 'error': if (downloadIcon) downloadIcon.classList.remove('hidden'); button.title = `Download failed: ${ (typeof data === 'string' && data) ? data : 'Unknown error'}`; break;
        default: if (downloadIcon) downloadIcon.classList.remove('hidden'); button.title = "Download Episode"; break;
    }
}

function attachChapterDownloadListeners() {
    document.querySelectorAll('.download-chapter-btn').forEach(button => {
        button.addEventListener('click', async function(event) {
            event.stopPropagation(); const currentClickedButton = this;
            if (!window.OfflineManager || typeof window.OfflineManager.downloadChapter !== 'function') { showCustomToast('Offline download feature not available.', 'error'); return; }
            const chapterItemDiv = currentClickedButton.closest('.chapter-item');
            if (!chapterItemDiv) { showCustomToast('Chapter data error. Cannot download.', 'error'); return; }

            const chapterInfoForDownload = {
                chapter_id: currentClickedButton.dataset.chapterId || chapterItemDiv.dataset.chapterId,
                chapter_unique_id: currentClickedButton.dataset.chapterUniqueId,
                chapter_index: parseInt(currentClickedButton.dataset.chapterIndex || chapterItemDiv.dataset.chapterIndex, 10),
                chapter_title: chapterItemDiv.dataset.chapterTitle,
                audio_url_template: chapterItemDiv.dataset.audioUrlTemplate,
                duration_seconds: parseInt(chapterItemDiv.dataset.durationSeconds, 10),
                is_accessible: chapterItemDiv.dataset.isAccessible === 'true'
            };
            const mainCoverImg = document.getElementById('main-cover-image');
            const audiobookInfoForDownload = {
                audiobookId: pageContext.audiobookId, audiobookTitle: pageContext.audiobookTitle,
                author: pageContext.audiobookAuthor || 'Unknown Author',
                coverImageUrl: mainCoverImg ? mainCoverImg.src : placeholderCoverSrc,
                slug: pageContext.audiobookSlug,
                language: pageContext.audiobookLanguage || 'N/A', genre: pageContext.audiobookGenre || 'N/A',
                isCreatorBook: pageContext.isCreatorBook === true
            };

            if (!chapterInfoForDownload.is_accessible) { showCustomToast('This chapter is not accessible for download.', 'warning'); return; }
            if (!chapterInfoForDownload.audio_url_template || chapterInfoForDownload.audio_url_template.endsWith("?url=")) {
                showCustomToast('Audio source not found for this chapter.', 'error');
                updateChapterDownloadButtonUI(currentClickedButton, 'error', 'No audio URL'); return;
            }

            updateChapterDownloadButtonUI(currentClickedButton, 'downloading', 'Preparing...');
            try {
                const result = await OfflineManager.downloadChapter(chapterInfoForDownload, audiobookInfoForDownload,
                    (percentage, message) => { // progressCallback
                        if (percentage === -1) updateChapterDownloadButtonUI(currentClickedButton, 'error', message);
                        else if (message.toLowerCase().includes('already downloaded')) updateChapterDownloadButtonUI(currentClickedButton, 'downloaded', 'Already downloaded');
                        else if (percentage === 100 && message.toLowerCase().includes('complete')) updateChapterDownloadButtonUI(currentClickedButton, 'downloaded', 'Download complete!');
                        else updateChapterDownloadButtonUI(currentClickedButton, 'downloading', percentage);
                    }
                );
                if (result.success && !result.message.toLowerCase().includes('already downloaded')) showCustomToast(`Chapter "${chapterInfoForDownload.chapter_title}" downloaded!`, 'success');
                else if (!result.success && !result.message.toLowerCase().includes('already downloaded')) showCustomToast(`Failed to download "${chapterInfoForDownload.chapter_title}": ${result.message}`, 'error');
            } catch (err) { console.error("Error in downloadChapter click handler:", err); showCustomToast('An unexpected error occurred during download.', 'error'); updateChapterDownloadButtonUI(currentClickedButton, 'error', 'Error');}
        });
    });
}

if (fullAudiobookDownloadBtnExisting) {
    fullAudiobookDownloadBtnExisting.addEventListener('click', async function() {
        const currentFullDownloadButton = this;
        if (!window.OfflineManager || typeof window.OfflineManager.downloadFullAudiobook !== 'function') { showCustomToast('Offline download feature not available.', 'error'); return; }
        const chaptersToDownload = [];
        document.querySelectorAll('.chapter-item').forEach(item => {
            if (item.dataset.isAccessible === 'true') chaptersToDownload.push({
                chapter_id: item.dataset.chapterId,
                chapter_unique_id: `${pageContext.audiobookSlug || pageContext.audiobookId}_${item.dataset.chapterId || item.dataset.chapterIndex}`,
                chapter_index: parseInt(item.dataset.chapterIndex, 10),
                chapter_title: item.dataset.chapterTitle,
                audio_url_template: item.dataset.audioUrlTemplate,
                duration_seconds: parseInt(item.dataset.durationSeconds, 10),
                is_accessible: true
            });
        });
        if (chaptersToDownload.length === 0) { showCustomToast('No accessible chapters to download.', 'info'); return; }

        const mainCoverImg = document.getElementById('main-cover-image');
        const audiobookInfoForDownload = {
            audiobookId: pageContext.audiobookId, audiobookTitle: pageContext.audiobookTitle,
            author: pageContext.audiobookAuthor || 'Unknown Author',
            coverImageUrl: mainCoverImg ? mainCoverImg.src : placeholderCoverSrc,
            slug: pageContext.audiobookSlug,
            language: pageContext.audiobookLanguage || 'N/A', genre: pageContext.audiobookGenre || 'N/A',
            isCreatorBook: pageContext.isCreatorBook === true
        };

        currentFullDownloadButton.disabled = true;
        if(fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = 'Preparing...';
        if(fullAudiobookStatusMessagesExisting) fullAudiobookStatusMessagesExisting.textContent = 'Starting full download...';
        if(fullAudiobookProgressBarContainerExisting) fullAudiobookProgressBarContainerExisting.classList.remove('hidden');
        if(fullAudiobookProgressBarExisting) fullAudiobookProgressBarExisting.style.width = '0%';

        try {
            await OfflineManager.downloadFullAudiobook(chaptersToDownload, audiobookInfoForDownload,
                (chapterIndexInArray, progress, message) => { // chapterProgressCallback
                    const chapterData = chaptersToDownload[chapterIndexInArray];
                    const btn = document.querySelector(`.download-chapter-btn[data-chapter-unique-id="${chapterData.chapter_unique_id}"]`);
                    if (btn) {
                        if (progress === -1) updateChapterDownloadButtonUI(btn, 'error', message);
                        else if (message.toLowerCase().includes('already downloaded')) updateChapterDownloadButtonUI(btn, 'downloaded');
                        else if (progress === 100 && message.toLowerCase().includes('complete')) updateChapterDownloadButtonUI(btn, 'downloaded');
                        else updateChapterDownloadButtonUI(btn, 'downloading', progress);
                    }
                },
                (overallPercentage, message) => { // overallProgressCallback
                    if(fullAudiobookProgressBarExisting) fullAudiobookProgressBarExisting.style.width = `${overallPercentage}%`;
                    if(fullAudiobookStatusMessagesExisting) fullAudiobookStatusMessagesExisting.textContent = message;
                    if (overallPercentage === 100) {
                        if(fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = message.includes("error") ? 'Partial' : 'All Downloaded';
                        if (!message.includes("error")) {
                            currentFullDownloadButton.classList.remove('border-[#09065E]/40', 'text-[#09065E]/90', 'hover:bg-[#09065E]/5'); // Default styles
                            currentFullDownloadButton.classList.add('border-green-500', 'text-green-600', 'bg-green-50'); // Downloaded styles
                        } else { currentFullDownloadButton.disabled = false; } // Re-enable if errors
                        showCustomToast(message, message.includes("error") ? 'warning' : 'success');
                    }
                }
            );
        } catch (err) {
            console.error("Error in full audiobook download click handler:", err);
            showCustomToast('An unexpected error occurred during full download.', 'error');
            if(fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = 'Download Failed';
            if(fullAudiobookStatusMessagesExisting) fullAudiobookStatusMessagesExisting.textContent = 'Error during download.';
            currentFullDownloadButton.disabled = false;
        }
    });
}

async function checkInitialDownloadStates() {
    if (!window.OfflineManager || !pageContext.audiobookId || typeof window.OfflineManager.initDB !== 'function') { return; }
    try {
        await OfflineManager.initDB(); let allAccessibleChaptersOnPageDownloaded = true; let accessibleChaptersCount = 0;
        const chapterDownloadButtons = document.querySelectorAll('.download-chapter-btn');

        for (const button of chapterDownloadButtons) {
            const chapterItemDiv = button.closest('.chapter-item'); if (!chapterItemDiv ) continue;
            if(chapterItemDiv.dataset.isAccessible !== 'true'){ if(button.parentElement.classList.contains('chapter-download-container')) button.parentElement.style.display = 'none'; continue; }
            accessibleChaptersCount++; const chapterUniqueId = button.dataset.chapterUniqueId;
            if (await OfflineManager.isChapterDownloaded(chapterUniqueId)) updateChapterDownloadButtonUI(button, 'downloaded');
            else { updateChapterDownloadButtonUI(button, 'idle'); allAccessibleChaptersOnPageDownloaded = false; }
        }

        if (fullAudiobookDownloadBtnExisting) {
            if (accessibleChaptersCount === 0) {
                if(fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = 'No Chapters';
                fullAudiobookDownloadBtnExisting.disabled = true;
                if(fullAudiobookStatusMessagesExisting) fullAudiobookStatusMessagesExisting.textContent = 'No accessible chapters to download.';
                fullAudiobookDownloadBtnExisting.classList.add('opacity-50', 'cursor-not-allowed');
            } else if (allAccessibleChaptersOnPageDownloaded) {
                if(fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = 'All Downloaded';
                fullAudiobookDownloadBtnExisting.classList.remove('border-[#09065E]/40', 'text-[#09065E]/90', 'hover:bg-[#09065E]/5');
                fullAudiobookDownloadBtnExisting.classList.add('border-green-500', 'text-green-600', 'bg-green-50');
                fullAudiobookDownloadBtnExisting.disabled = true;
                if(fullAudiobookStatusMessagesExisting) fullAudiobookStatusMessagesExisting.textContent = '';
                if(fullAudiobookProgressBarContainerExisting) fullAudiobookProgressBarContainerExisting.classList.add('hidden');
            } else {
                if(fullAudiobookDownloadTextExisting) fullAudiobookDownloadTextExisting.textContent = 'Download All';
                fullAudiobookDownloadBtnExisting.classList.add('border-[#09065E]/40', 'text-[#09065E]/90', 'hover:bg-[#09065E]/5');
                fullAudiobookDownloadBtnExisting.classList.remove('border-green-500', 'text-green-600', 'bg-green-50');
                fullAudiobookDownloadBtnExisting.disabled = false;
                fullAudiobookDownloadBtnExisting.classList.remove('opacity-50', 'cursor-not-allowed');
            }
        }
    } catch (error) { console.error("Error checking initial download states:", error); }
}


// --- Review Form Logic (from audiobook_detail.js, minor adaptations) ---
const reviewForm = document.getElementById('review-form');
const reviewRatingInputContainer = document.getElementById('review-rating-input'); // This is the div with stars
const ratingValueInput = document.getElementById('rating-value-input'); // Hidden input
const commentInput = document.getElementById('comment-input');
const ratingError = document.getElementById('rating-error');
const formMessage = document.getElementById('form-message');
const submitReviewBtn = document.getElementById('submit-review-btn');
const reviewsList = document.getElementById('reviews-list');
const reviewCountSpan = document.getElementById('review-count'); // For main count display
const reviewCountTabSpan = document.getElementById('review-count-tab'); // For tab count
const editReviewPrompt = document.getElementById('edit-review-prompt');
const editMyReviewButton = document.getElementById('edit-my-review-button'); // Button in the prompt


function setStarRating(rating) { // For review form input
    if (!reviewRatingInputContainer) return;
    const stars = reviewRatingInputContainer.querySelectorAll('.star-input-icon'); // Assuming SVG or similar
    stars.forEach((star, i) => {
        const isSelected = i < rating;
        star.classList.toggle('text-red-500', isSelected); // Active color from merged template
        star.classList.toggle('text-[#09065E]/30', !isSelected); // Inactive color
    });
    if (ratingValueInput) ratingValueInput.value = rating;
    if (ratingError) ratingError.textContent = '';
}

if (reviewRatingInputContainer) {
    const stars = reviewRatingInputContainer.querySelectorAll('.star-input-icon');
    stars.forEach(star => {
        star.addEventListener('mouseover', () => {
            const rating = parseInt(star.dataset.ratingValue);
            stars.forEach((s, i) => {
                const isHovered = i < rating;
                s.classList.toggle('text-red-400', isHovered); // Hover color
                s.classList.toggle('text-[#09065E]/30', !isHovered && !s.classList.contains('text-red-500')); // If not selected active
            });
        });
        star.addEventListener('mouseout', () => {
            const currentRating = parseInt(ratingValueInput.value);
            setStarRating(currentRating);
        });
        star.addEventListener('click', () => {
            const rating = parseInt(star.dataset.ratingValue);
            setStarRating(rating);
        });
    });
}

function displayReviewInList(reviewData, isNew) {
    if (!reviewsList) return;
    const existingReviewElement = document.getElementById(`review-${reviewData.review_id}`);
    if (existingReviewElement) existingReviewElement.remove();

    const reviewItem = document.createElement('article');
    reviewItem.className = 'review-item flex space-x-4 sm:space-x-5 p-5 sm:p-6 bg-white rounded-xl border border-[#09065E]/20 shadow-lg shadow-[#09065E]/[0.07]';
    reviewItem.id = `review-${reviewData.review_id}`;

    let avatarHtml = `<span class="h-12 w-12 sm:h-14 sm:w-14 rounded-full bg-[#09065E]/10 flex items-center justify-center text-[#09065E]/50 border-2 border-white shadow-md"><svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd" /></svg></span>`;
    if (reviewData.user_profile_pic) {
        avatarHtml = `<img class="h-12 w-12 sm:h-14 sm:w-14 rounded-full object-cover border-2 border-white shadow-md" src="${reviewData.user_profile_pic}" alt="${reviewData.user_name}">`;
    }

    let starsHtml = '';
    for (let i = 0; i < 5; i++) {
        starsHtml += `<svg class="w-4 h-4 ${i < reviewData.rating ? 'text-red-500' : 'text-[#09065E]/20'}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" /></svg>`;
    }

    let editButtonHtml = '';
    const currentUserIdNum = typeof pageContext.userId === 'string' ? parseInt(pageContext.userId, 10) : pageContext.userId;
    if (pageContext.isAuthenticated && reviewData.user_id && currentUserIdNum === reviewData.user_id) {
        editButtonHtml = `<div class="mt-4 text-xs"><button data-review-id="${reviewData.review_id}" data-rating="${reviewData.rating}" data-comment="${reviewData.comment.replace(/"/g, '&quot;')}" class="edit-user-review-button text-red-600 hover:text-red-700 hover:underline font-semibold focus:outline-none focus:ring-1 focus:ring-offset-1 focus:ring-red-500/70 rounded px-1.5 py-0.5 transition-colors duration-150"><svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 inline mr-1 align-text-bottom" viewBox="0 0 20 20" fill="currentColor"><path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z" /><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd" /></svg>Edit</button></div>`;
    }

    reviewItem.innerHTML = `
        <div class="flex-shrink-0 pt-1">${avatarHtml}</div>
        <div class="flex-grow">
            <div class="flex items-baseline justify-between mb-1.5">
                <h5 class="text-lg font-semibold text-[#09065E]">${reviewData.user_name}</h5>
                <time datetime="${reviewData.created_at}" class="flex-shrink-0 ml-4 text-xs text-[#09065E]/60">${reviewData.timesince}</time>
            </div>
            <div class="mb-2.5 flex items-center text-xs space-x-0.5">${starsHtml}</div>
            ${reviewData.comment ? `<div class="text-sm text-[#09065E]/80 prose prose-sm max-w-none leading-relaxed selection:bg-red-200 selection:text-red-800 prose-p:text-[#09065E]/80"><p>${reviewData.comment.replace(/\n/g, '<br>')}</p></div>` : ''}
            ${editButtonHtml}
        </div>`;

    const newEditButton = reviewItem.querySelector('.edit-user-review-button');
    if (newEditButton) newEditButton.addEventListener('click', handleEditReviewButtonClick);

    const noReviewsMsg = document.getElementById('no-reviews-message');
    if (noReviewsMsg) noReviewsMsg.style.display = 'none';

    if (isNew && reviewsList.firstChild) reviewsList.insertBefore(reviewItem, reviewsList.firstChild);
    else reviewsList.prepend(reviewItem);
}

function handleEditReviewButtonClick(event) {
    const button = event.currentTarget;
    const rating = button.dataset.rating;
    const comment = button.dataset.comment;
    if (reviewForm && ratingValueInput && commentInput) {
        setStarRating(parseInt(rating));
        commentInput.value = comment;
        reviewForm.classList.remove('hidden');
        if (editReviewPrompt) editReviewPrompt.classList.add('hidden');
        reviewForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
        if (formMessage) formMessage.textContent = 'Editing your review...';
        if (submitReviewBtn) submitReviewBtn.innerHTML = '<i class="fas fa-save mr-2.5"></i>Update Review'; // Consistent icon
    }
}

if (editMyReviewButton) editMyReviewButton.addEventListener('click', handleEditReviewButtonClick);
document.querySelectorAll('.edit-user-review-button').forEach(button => {
    button.addEventListener('click', handleEditReviewButtonClick);
});


if (reviewForm) {
    reviewForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        if (!pageContext.isAuthenticated) {
            showCustomModal('Authentication Required', 'Please log in to submit a review.', () => { if (pageContext.loginUrl) window.location.href = pageContext.loginUrl; }, null, 'Log In', 'Cancel');
            return;
        }
        if (ratingValueInput.value === "0") {
            if(ratingError) ratingError.textContent = 'Please select a rating.'; return;
        }
        if(ratingError) ratingError.textContent = '';
        if(formMessage) formMessage.textContent = '';
        const isUpdate = submitReviewBtn.innerHTML.includes("Update");

        const payload = { rating: ratingValueInput.value, comment: commentInput.value.trim() };
        try {
            if(submitReviewBtn) submitReviewBtn.disabled = true;
            if(formMessage) formMessage.textContent = 'Submitting...';
            if(submitReviewBtn) submitReviewBtn.innerHTML = '<svg class="animate-spin h-5 w-5 mr-2.5 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>Submitting...';


            const response = await fetch(pageContext.addReviewUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': pageContext.csrfToken },
                body: JSON.stringify(payload)
            });
            const result = await response.json();

            if (response.ok && result.status === 'success') {
                showCustomToast(result.message, 'success');
                reviewForm.reset(); setStarRating(0);
                reviewForm.classList.add('hidden');
                if (editReviewPrompt) {
                    editReviewPrompt.classList.remove('hidden');
                    // Update the prompt content with new review data
                    const promptRatingStarsContainer = editReviewPrompt.querySelector('p.flex.items-center.justify-center'); // Assuming a more specific selector
                     if(promptRatingStarsContainer) {
                        let starsHtmlPrompt = 'Your rating: ';
                        for(let i=0; i < 5; i++) { starsHtmlPrompt += `<svg class="w-4 h-4 ml-1 ${i < result.review_data.rating ? 'text-red-500' : 'text-[#09065E]/20'}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" /></svg>`; }
                        promptRatingStarsContainer.innerHTML = starsHtmlPrompt;
                    }
                    const promptCommentP = editReviewPrompt.querySelector('p.italic');
                    if(promptCommentP) {
                        if(result.review_data.comment) {
                            promptCommentP.textContent = `"${result.review_data.comment.substring(0,50)}${result.review_data.comment.length > 50 ? '...' : ''}"`;
                            promptCommentP.classList.remove('hidden');
                        } else { promptCommentP.classList.add('hidden'); }
                    }
                    if(editMyReviewButton) {
                        editMyReviewButton.dataset.rating = result.review_data.rating;
                        editMyReviewButton.dataset.comment = result.review_data.comment;
                    }
                }
                displayReviewInList(result.review_data, result.created);
                if(result.created) {
                    const currentTotalReviews = parseInt(reviewCountSpan.textContent) || 0;
                    if(reviewCountSpan) reviewCountSpan.textContent = currentTotalReviews + 1;
                    if(reviewCountTabSpan) reviewCountTabSpan.textContent = currentTotalReviews + 1;
                }
                // Update overall average rating display on the page
                const overallAvgRatingDisplayElements = document.querySelectorAll('.lg\\:col-span-8 .flex.items-center.space-x-1\\.5 span.font-semibold.text-\\[\\#09065E\\], .lg\\:col-span-8 .flex.items-center.space-x-1\\.5 span.text-\\[\\#09065E\\].font-semibold.pt-px');
                 overallAvgRatingDisplayElements.forEach(el => {
                    if (result.new_average_rating && result.new_average_rating !== "0.0") {
                       el.textContent = `${parseFloat(result.new_average_rating).toFixed(1)}`;
                    }
                });
                if(submitReviewBtn) submitReviewBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z"></path><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd"></path></svg>Edit Your Review';


            } else { showCustomAlert('Error', result.message || 'Could not submit your review.', 'error'); }
        } catch (error) {
            console.error('Review submission fetch error:', error);
            showCustomAlert('Error', 'An unexpected error occurred. Please try again.', 'error');
        } finally {
            if(submitReviewBtn) {
                submitReviewBtn.disabled = false;
                // Reset button text based on context
                if (reviewForm.classList.contains('hidden')) { // Review was successful
                    submitReviewBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z"></path><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd"></path></svg>Edit Your Review';
                } else if (isUpdate) { // Error during update
                    submitReviewBtn.innerHTML = '<i class="fas fa-save mr-2.5"></i>Update Review';
                } else { // Error during initial submit
                    submitReviewBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 16.571V11.5a1 1 0 011-1h.094a1 1 0 01.803.424l4.25 5.5a1 1 0 001.6-.25L17.894 3.962a1 1 0 00-.999-1.409l-7 .001z" /></svg>Submit Review';
                }
            }
            if(formMessage) formMessage.textContent = '';
        }
    });
}

// --- Add to Library Logic (from audiobook_detail.js) ---
const addToLibraryButton = document.getElementById('add-to-library-button');
async function handleAddToLibrary() {
    if (!pageContext.isAuthenticated) {
        showCustomModal( 'Login Required', 'Please log in to add audiobooks to your library.', () => { if (pageContext.loginUrl) window.location.href = pageContext.loginUrl; }, null, 'Log In', 'Cancel' );
        return;
    }
    const audiobookIdLib = addToLibraryButton.dataset.audiobookId;
    if (!audiobookIdLib || audiobookIdLib.trim() === '' || audiobookIdLib === 'null') {
        showCustomAlert('Error', 'Audiobook ID is missing or invalid for library action.', 'error'); return;
    }
    if (!pageContext.addToLibraryApiUrl || pageContext.addToLibraryApiUrl === '#error-parsing-context') {
        showCustomAlert('Configuration Error', 'This feature (add to library) is not correctly configured.', 'error'); return;
    }
    showCustomToast('Processing library request...', 'info', { duration: null }); // Persistent toast
    try {
        const response = await fetch(pageContext.addToLibraryApiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': pageContext.csrfToken },
            body: JSON.stringify({ audiobook_id: audiobookIdLib })
        });
        const result = await response.json();
        dismissAllToasts();
        if (response.ok && result.status === 'success') {
            showCustomToast(result.message || `Library updated for "${pageContext.audiobookTitle}"!`, 'success');
            const btnText = document.getElementById('add-to-library-text');
            if(btnText) btnText.textContent = result.is_in_library ? 'In Library' : 'Add to Library';
            // Update button appearance based on library status
            addToLibraryButton.classList.toggle('bg-green-600', result.is_in_library);
            addToLibraryButton.classList.toggle('hover:bg-green-700', result.is_in_library);
            addToLibraryButton.classList.toggle('bg-red-600', !result.is_in_library); // Default if not in library
            addToLibraryButton.classList.toggle('hover:bg-red-700', !result.is_in_library);
        } else { showCustomAlert('Error', result.message || 'Could not update library.', 'error'); }
    } catch (error) {
        dismissAllToasts();
        console.error('Add to Library Error:', error);
        showCustomAlert('Request Failed', 'An error occurred while updating your library.', 'error');
    }
}
if (addToLibraryButton) addToLibraryButton.addEventListener('click', handleAddToLibrary);

// --- Custom Modal & Toast Implementation (from audiobook_detail.js) ---
const modalOverlay = document.getElementById('custom-modal-overlay');
const modalContentElem = document.getElementById('custom-modal-content');
const modalTitleElem = document.getElementById('custom-modal-title');
const modalBodyElem = document.getElementById('custom-modal-body');
const modalConfirmBtn = document.getElementById('custom-modal-confirm-btn');
const modalCancelBtn = document.getElementById('custom-modal-cancel-btn');
const modalCloseBtnIconElem = document.getElementById('custom-modal-close-btn-icon');
let currentConfirmCallback = null; let currentCancelCallback = null;

function showCustomModal(title, bodyHTML, confirmCallback, cancelCallback, confirmText = 'Confirm', cancelText = 'Cancel') {
    if (!modalOverlay || !modalTitleElem || !modalBodyElem || !modalConfirmBtn || !modalCancelBtn) {
        alert(`${title}\n\n${bodyHTML.replace(/<br\s*\/?>/gi, '\n')}`);
        if (confirmCallback && confirmText !== null) if (confirm("Proceed? (Simulated from custom modal)")) confirmCallback();
        return;
    }
    modalTitleElem.textContent = title;
    if (typeof bodyHTML === 'string') modalBodyElem.innerHTML = bodyHTML;
    else if (bodyHTML instanceof HTMLElement) { modalBodyElem.innerHTML = ''; modalBodyElem.appendChild(bodyHTML); }
    else modalBodyElem.textContent = 'Invalid modal content.';

    modalConfirmBtn.textContent = confirmText;
    modalCancelBtn.textContent = cancelText;
    modalConfirmBtn.style.display = confirmText === null ? 'none' : 'inline-flex';
    modalCancelBtn.style.display = cancelText === null ? 'none' : 'inline-flex';
    currentConfirmCallback = confirmCallback; currentCancelCallback = cancelCallback;
    modalOverlay.classList.remove('hidden');
    setTimeout(() => { modalOverlay.classList.remove('opacity-0'); modalContentElem.classList.remove('opacity-0', 'scale-95'); }, 10);
}

function hideCustomModal() {
    if (!modalOverlay || !modalContentElem) return;
    modalOverlay.classList.add('opacity-0'); modalContentElem.classList.add('opacity-0', 'scale-95');
    setTimeout(() => modalOverlay.classList.add('hidden'), 200);
}

if(modalConfirmBtn) modalConfirmBtn.addEventListener('click', () => { if (currentConfirmCallback) currentConfirmCallback(); hideCustomModal(); });
if(modalCancelBtn) modalCancelBtn.addEventListener('click', () => { if (currentCancelCallback) currentCancelCallback(); hideCustomModal(); });
if(modalCloseBtnIconElem) modalCloseBtnIconElem.addEventListener('click', hideCustomModal);
if(modalOverlay) modalOverlay.addEventListener('click', (event) => { if (event.target === modalOverlay) hideCustomModal(); });

const inlineMessageContainer = document.getElementById('inline-message-container');
let toastIdCounter = 0; const activeToasts = {};

function showCustomToast(message, type = 'info', options = {}) {
    if (!inlineMessageContainer) { console.log(`Toast [${type}]: ${message}`); alert(`[${type.toUpperCase()}] ${message}`); return; }
    const { duration = 3000, persistent = false } = options; toastIdCounter++; const toastId = `toast-${toastIdCounter}`;
    const toast = document.createElement('div');
    toast.className = `message-item p-4 rounded-lg shadow-xl text-sm font-medium flex items-start justify-between transition-all duration-300 opacity-0 translate-y-2`;
    toast.dataset.toastId = toastId;
    let bgColor, textColor, iconSvg;
    switch (type) {
        case 'success': bgColor = 'bg-green-500'; textColor = 'text-white'; iconSvg = `<svg class="w-5 h-5 mr-3 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" /></svg>`; break;
        case 'error': bgColor = 'bg-red-500'; textColor = 'text-white'; iconSvg = `<svg class="w-5 h-5 mr-3 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 101.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" /></svg>`; break;
        case 'warning': bgColor = 'bg-yellow-400'; textColor = 'text-yellow-800'; iconSvg = `<svg class="w-5 h-5 mr-3 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 3.001-1.742 3.001H4.42c-1.53 0-2.493-1.667-1.743-3.001l5.58-9.92zM10 13a1 1 0 110-2 1 1 0 010 2zm-1.75-5.75a.75.75 0 00-1.5 0v3a.75.75 0 001.5 0v-3z" clip-rule="evenodd" /></svg>`; break;
        default: bgColor = 'bg-blue-500'; textColor = 'text-white'; iconSvg = `<svg class="w-5 h-5 mr-3 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" /></svg>`;
    }
    toast.classList.add(bgColor, textColor);
    toast.innerHTML = `<div class="flex items-center">${iconSvg}<span class="message-text">${message}</span></div><button class="message-close-btn ml-4 p-0.5 -mr-1 -mt-1 text-current opacity-70 hover:opacity-100 rounded-full hover:bg-black/10 focus:outline-none focus:ring-1 focus:ring-white/50"><svg class="w-4 h-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" /></svg></button>`;
    inlineMessageContainer.appendChild(toast);
    setTimeout(() => { toast.classList.remove('opacity-0', 'translate-y-2'); }, 10);
    const closeBtn = toast.querySelector('.message-close-btn');
    closeBtn.addEventListener('click', () => dismissToast(toastId));
    if (!persistent && duration !== null) activeToasts[toastId] = setTimeout(() => dismissToast(toastId), duration);
    else if (persistent) activeToasts[toastId] = 'persistent';
}

function dismissToast(toastId) {
    const toast = document.querySelector(`.message-item[data-toast-id="${toastId}"]`);
    if (toast) {
        toast.classList.add('opacity-0'); toast.style.transform = 'scale(0.95)';
        setTimeout(() => {
            toast.remove();
            if (activeToasts[toastId] && activeToasts[toastId] !== 'persistent') clearTimeout(activeToasts[toastId]);
            delete activeToasts[toastId];
        }, 300);
    }
}

function dismissAllToasts() { Object.keys(activeToasts).forEach(toastId => dismissToast(toastId)); }

// --- Share Button & Modal Logic (from audiobook_detail.js) ---
function openShareModal() {
    if (!pageContext.audiobookTitle || !modalBodyElem || !modalTitleElem || !shareModalContentTemplate) {
        showCustomModal('Error', 'Share feature is not properly configured.', null, null, 'OK', null);
        return;
    }
    const shareUrl = window.location.href;
    const audiobookTitleForShare = pageContext.audiobookTitle || "this audiobook";
    const newShareContent = shareModalContentTemplate.cloneNode(true);
    newShareContent.classList.remove('hidden'); newShareContent.removeAttribute('id');
    const modalBodyContentHTML = newShareContent.outerHTML;
    showCustomModal( `Share "${audiobookTitleForShare}"`, modalBodyContentHTML, null, null, null, 'Close' );
    const activeModalBody = document.getElementById('custom-modal-body'); // Re-query inside active modal
    if (activeModalBody) {
        const shareLinkInput = activeModalBody.querySelector('#share-link-input');
        const copyShareLinkButton = activeModalBody.querySelector('#copy-share-link-button');
        const copyStatusMessage = activeModalBody.querySelector('#copy-status-message');
        const shareFacebook = activeModalBody.querySelector('#share-facebook');
        const shareTwitter = activeModalBody.querySelector('#share-twitter');
        const shareWhatsapp = activeModalBody.querySelector('#share-whatsapp');
        const shareEmail = activeModalBody.querySelector('#share-email');

        if (shareLinkInput) shareLinkInput.value = shareUrl;
        if (copyShareLinkButton && shareLinkInput && copyStatusMessage) {
            copyShareLinkButton.addEventListener('click', () => {
                shareLinkInput.select(); shareLinkInput.setSelectionRange(0, 99999);
                try {
                    document.execCommand('copy'); copyStatusMessage.textContent = 'Link copied!';
                    setTimeout(() => { copyStatusMessage.textContent = ''; }, 2000);
                } catch (err) {
                    copyStatusMessage.textContent = 'Failed to copy.'; console.error('Failed to copy link: ', err);
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        navigator.clipboard.writeText(shareUrl).then(() => {
                            copyStatusMessage.textContent = 'Link copied! (fallback)'; setTimeout(() => { copyStatusMessage.textContent = ''; }, 2000);
                        }).catch(clipErr => { copyStatusMessage.textContent = 'Failed to copy (fallback).'; console.error('Fallback clipboard copy failed: ', clipErr); });
                    }
                }
            });
        }
        const encodedUrl = encodeURIComponent(shareUrl);
        const shareText = `Check out this audiobook: ${audiobookTitleForShare}`;
        const encodedTitle = encodeURIComponent(shareText);
        if(shareFacebook) shareFacebook.href = `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`;
        if(shareTwitter) shareTwitter.href = `https://twitter.com/intent/tweet?url=${encodedUrl}&text=${encodedTitle}`;
        if(shareWhatsapp) shareWhatsapp.href = `https://api.whatsapp.com/send?text=${encodedTitle}%20${encodedUrl}`;
        if(shareEmail) shareEmail.href = `mailto:?subject=${encodeURIComponent(`Interesting Audiobook: ${audiobookTitleForShare}`)}&body=${encodedTitle}%0A%0A${encodedUrl}`;
    }
}
if (shareButton) shareButton.addEventListener('click', openShareModal);


// --- Inline Clip Editor Logic (from audiobook_detail.js) ---
function showClipEditor(chapterData) {
    if (!chapterClipEditorArea || !clipEditorChapterTitle || !clipEditorPlayer || !clipEditorStartTimeDisplay || !clipEditorEndTimeDisplay || !generateClipBtnInline) {
        console.error("Clip editor elements not found."); showCustomModal("Error", "Clip creation UI is not available.", null, null, 'OK', null); return;
    }
    if (currentChapterDataForClipping && currentChapterDataForClipping.id !== chapterData.id) hideClipEditor();
    currentChapterDataForClipping = chapterData;
    clipEditorChapterTitle.textContent = chapterData.title;
    const totalDurationSeconds = parseInt(chapterData.duration, 10);
    selectedClipStartTime = 0;
    selectedClipEndTime = totalDurationSeconds > 0 ? Math.min(10, totalDurationSeconds) : 0;
    if (selectedClipEndTime <= selectedClipStartTime && totalDurationSeconds > selectedClipStartTime) selectedClipEndTime = selectedClipStartTime + Math.min(10, totalDurationSeconds - selectedClipStartTime);
    else if (selectedClipEndTime <= selectedClipStartTime) selectedClipEndTime = selectedClipStartTime;

    clipEditorStartTimeDisplay.textContent = formatTime(selectedClipStartTime);
    clipEditorEndTimeDisplay.textContent = formatTime(selectedClipEndTime);

    const onClipEditorPlayerReady = () => {
        clipEditorPlayer.currentTime = 0;
        if(clipEditorStatus) clipEditorStatus.textContent = 'Use player to find desired start/end, then click "Set" buttons.';
        clipEditorPlayer.removeEventListener('loadedmetadata', onClipEditorPlayerReady);
    };

    if (chapterData.audioUrlTemplate && chapterData.audioUrlTemplate.includes("?url=")) {
        clipEditorPlayer.src = chapterData.audioUrlTemplate;
        clipEditorPlayer.addEventListener('loadedmetadata', onClipEditorPlayerReady, { once: true });
        clipEditorPlayer.load();
    } else {
        clipEditorPlayer.src = ''; console.warn("No valid audio URL template for clip editor for chapter:", chapterData.title);
        showCustomToast("Cannot load audio for clipping.", "error");
        if(clipEditorStatus) clipEditorStatus.textContent = 'Error loading audio for clipping.';
    }

    if(generatedClipAreaInline) generatedClipAreaInline.classList.add('hidden');
    if(generatedClipPlayerInline) generatedClipPlayerInline.src = '';
    if(downloadGeneratedClipLinkInline) downloadGeneratedClipLinkInline.href = '#';
    const generateBtnText = generateClipBtnInline.querySelector('.generate-text-inline');
    const generatingBtnText = generateClipBtnInline.querySelector('.generating-text-inline');
    if (generateBtnText) generateBtnText.classList.remove('hidden');
    if (generatingBtnText) generatingBtnText.classList.add('hidden');
    generateClipBtnInline.disabled = false;
    chapterClipEditorArea.classList.remove('hidden');
    const editorTop = chapterClipEditorArea.offsetTop; const headerOffset = 100; const scrollPosition = editorTop - headerOffset;
    const rect = chapterClipEditorArea.getBoundingClientRect();
    if (rect.top < headerOffset || rect.bottom > (window.innerHeight - 50) ) window.scrollTo({ top: scrollPosition, behavior: 'smooth' });
}

function hideClipEditor() {
    if (!chapterClipEditorArea) return;
    chapterClipEditorArea.classList.add('hidden');
    if (clipEditorPlayer) { clipEditorPlayer.pause(); clipEditorPlayer.src = ''; }
    if (generatedClipPlayerInline) { generatedClipPlayerInline.pause(); generatedClipPlayerInline.src = ''; }
    currentChapterDataForClipping = null; selectedClipStartTime = 0; selectedClipEndTime = 0;
}
if (closeClipEditorBtn) closeClipEditorBtn.addEventListener('click', hideClipEditor);

if (setStartTimeBtn && clipEditorPlayer && clipEditorStartTimeDisplay) {
    setStartTimeBtn.addEventListener('click', () => {
        if (!currentChapterDataForClipping || !clipEditorPlayer || clipEditorPlayer.readyState < 1) { if(clipEditorStatus) clipEditorStatus.textContent = "Player not ready. Try again."; return; }
        selectedClipStartTime = clipEditorPlayer.currentTime;
        const totalDuration = parseInt(currentChapterDataForClipping.duration, 10);
        if (selectedClipStartTime >= selectedClipEndTime || selectedClipEndTime === 0) {
            selectedClipEndTime = Math.min(selectedClipStartTime + 10, totalDuration);
            if (selectedClipEndTime <= selectedClipStartTime && totalDuration > selectedClipStartTime) selectedClipEndTime = selectedClipStartTime + Math.min(1, totalDuration - selectedClipStartTime);
            else if (selectedClipEndTime <= selectedClipStartTime) selectedClipEndTime = selectedClipStartTime;
            if (clipEditorEndTimeDisplay) clipEditorEndTimeDisplay.textContent = formatTime(selectedClipEndTime);
        }
        selectedClipStartTime = Math.max(0, selectedClipStartTime);
        if (totalDuration > 0 && selectedClipStartTime >= totalDuration) { selectedClipStartTime = totalDuration - 0.1; selectedClipStartTime = Math.max(0, selectedClipStartTime); }
        clipEditorStartTimeDisplay.textContent = formatTime(selectedClipStartTime);
        if(clipEditorStatus) clipEditorStatus.textContent = `Start: ${formatTime(selectedClipStartTime)}. Set End.`;
    });
}

if (setEndTimeBtn && clipEditorPlayer && clipEditorEndTimeDisplay) {
    setEndTimeBtn.addEventListener('click', () => {
        if (!currentChapterDataForClipping || !clipEditorPlayer || clipEditorPlayer.readyState < 1) { if(clipEditorStatus) clipEditorStatus.textContent = "Player not ready. Try again."; return; }
        selectedClipEndTime = clipEditorPlayer.currentTime;
        const totalDuration = parseInt(currentChapterDataForClipping.duration, 10);
        selectedClipEndTime = Math.min(selectedClipEndTime, totalDuration);
        if (selectedClipEndTime <= selectedClipStartTime) {
            selectedClipStartTime = Math.max(0, selectedClipEndTime - 0.1);
            if (selectedClipStartTime >= selectedClipEndTime && selectedClipEndTime > 0) selectedClipStartTime = Math.max(0, selectedClipEndTime - 1);
            if (clipEditorStartTimeDisplay) clipEditorStartTimeDisplay.textContent = formatTime(selectedClipStartTime);
        }
        selectedClipEndTime = Math.max(selectedClipStartTime + 0.01, selectedClipEndTime);
        selectedClipEndTime = Math.min(selectedClipEndTime, totalDuration);
        clipEditorEndTimeDisplay.textContent = formatTime(selectedClipEndTime);
        if(clipEditorStatus) clipEditorStatus.textContent = `End: ${formatTime(selectedClipEndTime)}. Ready to Generate.`;
    });
}

if (generateClipBtnInline) {
    generateClipBtnInline.addEventListener('click', async () => {
        if (!currentChapterDataForClipping) { showCustomModal("Error", "No chapter loaded for clipping.", null,null,'OK',null); return; }
        const preciseStartTime = selectedClipStartTime; const preciseEndTime = selectedClipEndTime;
        if (preciseEndTime <= preciseStartTime) {
            if(clipEditorStatus) clipEditorStatus.textContent = "Invalid time selection: End time must be after start time.";
            showCustomToast("Invalid time selection. Ensure end time is after start time.", "error"); return;
        }
        const chapterId = currentChapterDataForClipping.id;
        const maxClipDuration = pageContext.maxAudioClipDurationSeconds || 300;
        if ((preciseEndTime - preciseStartTime) > maxClipDuration) {
            if(clipEditorStatus) clipEditorStatus.textContent = `Clip too long (max ${formatTime(maxClipDuration)}).`;
            showCustomToast(`Clip is too long. Maximum duration is ${formatTime(maxClipDuration)}.`, "error"); return;
        }
        if(clipEditorStatus) clipEditorStatus.textContent = "Generating clip, please wait...";
        if(generatedClipAreaInline) generatedClipAreaInline.classList.add('hidden');
        const generateBtnText = generateClipBtnInline.querySelector('.generate-text-inline');
        const generatingBtnText = generateClipBtnInline.querySelector('.generating-text-inline');
        if (generateBtnText) generateBtnText.classList.add('hidden');
        if (generatingBtnText) generatingBtnText.classList.remove('hidden');
        generateClipBtnInline.disabled = true;
        const payload = { chapter_id: chapterId, start_time_seconds: preciseStartTime, end_time_seconds: preciseEndTime };
        const clipUrlForFetch = pageContext.generateAudioClipUrl;

        try {
            const response = await fetch(clipUrlForFetch, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': pageContext.csrfToken }, body: JSON.stringify(payload) });
            const resultText = await response.text(); let result;
            try { result = JSON.parse(resultText); }
            catch (e) { console.error("Failed to parse server response as JSON. Raw response:", resultText); throw new Error(`Server returned non-JSON response (status: ${response.status}). Check server logs.`); }

            if (response.ok && result.status === 'success') {
                if(clipEditorStatus) clipEditorStatus.textContent = "Clip generated successfully!";
                if(generatedClipPlayerInline) generatedClipPlayerInline.src = result.clip_url;
                if(downloadGeneratedClipLinkInline) { downloadGeneratedClipLinkInline.href = result.clip_url; downloadGeneratedClipLinkInline.download = result.filename || `clip_${chapterId}_${Math.floor(preciseStartTime)}-${Math.floor(preciseEndTime)}.mp3`;}
                if(generatedClipAreaInline) generatedClipAreaInline.classList.remove('hidden');
                showCustomToast("Audio clip created!", "success");
            } else {
                if(clipEditorStatus) clipEditorStatus.textContent = `Error: ${result.message || 'Failed to generate clip.'}`;
                showCustomModal("Clip Generation Failed", result.message || "Could not generate the audio clip.", null,null,'OK',null);
            }
        } catch (error) {
            console.error("Error generating clip:", error);
            if(clipEditorStatus) clipEditorStatus.textContent = `Error: ${error.message || "Network error."}`;
            showCustomModal("Request Error", `An error occurred: ${error.message || "Please try again."}`, null,null,'OK',null);
        } finally {
            if (generateBtnText) generateBtnText.classList.remove('hidden');
            if (generatingBtnText) generatingBtnText.classList.add('hidden');
            generateClipBtnInline.disabled = false;
        }
    });
}

if (shareGeneratedClipBtnInline && generatedClipPlayerInline) {
    shareGeneratedClipBtnInline.addEventListener('click', async () => {
        const clipUrl = generatedClipPlayerInline.src;
        const chapterTitleForShare = currentChapterDataForClipping?.title || "Audio Clip";
        const audiobookTitleForShare = pageContext.audiobookTitle || "AudioX";
        if (!clipUrl || clipUrl === window.location.href || clipUrl.startsWith('blob:')) { showCustomToast("Clip not ready or cannot be shared directly. Please download first.", "warning"); return; }
        const shareData = { title: `Clip from: ${chapterTitleForShare}`, text: `Listen to this cool clip from "${chapterTitleForShare}" on ${audiobookTitleForShare}! Listen here: ${clipUrl}`, url: clipUrl };
        if (navigator.share && navigator.canShare(shareData)) {
            try { await navigator.share(shareData); showCustomToast("Clip shared!", "success"); }
            catch (err) { if (err.name !== 'AbortError') showCustomToast(`Share failed: ${err.message}`, "error");}
        } else {
            try { await navigator.clipboard.writeText(clipUrl); showCustomToast("Clip URL copied to clipboard!", "info"); }
            catch (err) { showCustomModal("Share Not Available", "Could not automatically share.", null,null,'OK',null); }
        }
    });
}

function attachClipButtonListeners() {
    document.querySelectorAll('.clip-chapter-btn').forEach(button => {
        button.addEventListener('click', function() {
            const chapterData = {
                id: this.dataset.chapterId, title: this.dataset.chapterTitle,
                duration: this.dataset.chapterDuration, audioUrlTemplate: this.dataset.audioUrlTemplate
            };
            if (currentChapterDataForClipping && currentChapterDataForClipping.id !== chapterData.id && chapterClipEditorArea && !chapterClipEditorArea.classList.contains('hidden')) {
                hideClipEditor(); setTimeout(() => showClipEditor(chapterData), 50);
            } else if (chapterClipEditorArea && chapterClipEditorArea.classList.contains('hidden')) {
                showClipEditor(chapterData);
            } else if (currentChapterDataForClipping && currentChapterDataForClipping.id === chapterData.id && chapterClipEditorArea && !chapterClipEditorArea.classList.contains('hidden')) {
                hideClipEditor();
            } else { showClipEditor(chapterData); }
        });
    });
}
// --- END: Updated Inline Clip Editor Logic ---


// --- START: Stripe Purchase Logic (Integrated from audiobook_creator_details.js) ---
if (purchaseButton && pageContext.stripePublishableKey && pageContext.createCheckoutSessionUrl && pageContext.audiobookSlug) {
    try {
        stripe = Stripe(pageContext.stripePublishableKey);
        purchaseButton.addEventListener('click', async (event) => {
            event.target.disabled = true;
            event.target.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...'; // Font Awesome icon

            try {
                const response = await fetch(pageContext.createCheckoutSessionUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': pageContext.csrfToken, // pageContext should have csrfToken
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        'item_type': 'audiobook',
                        'item_id': pageContext.audiobookSlug // audiobookSlug from pageContext
                    })
                });
                const session = await response.json();

                if (session.error || !session.sessionId) {
                    console.error('Error from server or missing session ID:', session.error || 'Missing session.sessionId');
                    showCustomModal('Payment Error', session.error || 'Failed to create checkout session. Please check item details or contact support.', null, null, 'OK', null);
                    event.target.disabled = false;
                    event.target.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${pageContext.audiobookPrice})`;
                    return;
                }

                const result = await stripe.redirectToCheckout({ sessionId: session.sessionId });

                if (result.error) {
                    console.error('Stripe redirectToCheckout error:', result.error);
                    throw new Error(result.error.message);
                }
            } catch (error) {
                console.error('Error during purchase process:', error);
                showCustomModal('Payment Error', error.message || 'Could not initiate payment. Please try again.', null, null, 'OK', null);
                event.target.disabled = false;
                event.target.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${pageContext.audiobookPrice})`;
            }
        });
    } catch (e) {
        console.error("Stripe initialization failed:", e);
        if (purchaseButton) {
            purchaseButton.disabled = true;
            purchaseButton.innerHTML = '<i class="fas fa-exclamation-circle mr-2"></i> Payment Init Failed';
        }
    }
} else if (purchaseButton) {
    console.warn("Purchase button found, but Stripe or necessary data (Key, URL, Slug) is not configured in pageContext.");
    purchaseButton.disabled = true;
    // Ensure the button text reflects it's unavailable if it's rendered
    const priceText = pageContext.audiobookPrice ? ` (PKR ${pageContext.audiobookPrice})` : '';
    purchaseButton.innerHTML = `<i class="fas fa-times-circle mr-2"></i> Purchase Unavailable${priceText}`;
    purchaseButton.title = "Payment system is currently unavailable for this item.";
}
// --- END: Stripe Purchase Logic ---


// --- Initialize Page ---
document.addEventListener('DOMContentLoaded', () => {
    // Initial Tab Setup
    const hash = window.location.hash;
    let initialTabId = 'about';
    if (hash && hash.startsWith('#content-')) {
        const hashTabId = hash.substring('#content-'.length);
        if (document.getElementById(`tab-${hashTabId}`) && document.getElementById(`content-${hashTabId}`)) {
            initialTabId = hashTabId;
        }
    }
    showTab(initialTabId); // Use the consistent showTab from audiobook_detail.js

    // Player initialization
    if (!audioPlayer || !audioPlayer.getAttribute('src')) hidePlayerBar();
    if(playerPrevButton) playerPrevButton.disabled = true;
    if(playerNextButton) playerNextButton.disabled = true;
    if(playerSpeedButton) playerSpeedButton.textContent = `${playbackSpeeds[currentSpeedIndex]}x`;

    const playFirstChapterBtn = document.getElementById('play-first-chapter-btn');
    if(playFirstChapterBtn && chapterItems.length > 0) {
        playFirstChapterBtn.addEventListener('click', () => {
            const firstChapterPlayButton = chapterItems[0]?.querySelector('.play-button');
            if (firstChapterPlayButton && chapterItems[0]?.dataset.isAccessible === 'true') {
                playChapter(firstChapterPlayButton);
            } else if (chapterItems.length > 0 && chapterItems[0]?.dataset.isAccessible !== 'true'){
                showCustomToast('First episode is locked.', 'warning');
            } else {
                showCustomToast('First episode is not available.', 'warning');
            }
        });
    }

    attachChapterDownloadListeners();
    attachClipButtonListeners();

    // Offline Manager Initialization (from audiobook_detail.js)
    const MGR_CHECK_INTERVAL = 100;
    const MGR_CHECK_TIMEOUT = 5000;
    let time_elapsed = 0;
    function attemptInitDownloadsCheck() {
        if (window.OfflineManager && typeof window.OfflineManager.initDB === 'function') {
            OfflineManager.initDB().then(() => {
                if (typeof window.OfflineManager.isChapterDownloaded === 'function') {
                    checkInitialDownloadStates();
                }
            }).catch(err => console.error("Failed to init DB for initial download state check:", err));
        } else {
            time_elapsed += MGR_CHECK_INTERVAL;
            if (time_elapsed < MGR_CHECK_TIMEOUT) {
                setTimeout(attemptInitDownloadsCheck, MGR_CHECK_INTERVAL);
            } else {
                document.querySelectorAll('.download-chapter-btn, #download-full-audiobook-btn').forEach(btn => {
                    btn.style.display = 'none';
                    const btnContainer = btn.closest('.chapter-download-container');
                    if (btnContainer){
                        const statusEl = btnContainer.querySelector('.chapter-download-status');
                        if(statusEl) statusEl.textContent = 'Offline N/A';
                    }
                });
                if(fullAudiobookStatusMessagesExisting) fullAudiobookStatusMessagesExisting.textContent = 'Offline features unavailable.';
            }
        }
    }
    attemptInitDownloadsCheck();

    // Final progress update on page unload
    window.addEventListener('beforeunload', () => {
        if (pageContext.isAuthenticated && audioPlayer && !audioPlayer.paused && audioPlayer.currentTime > 0 &&
            pageContext.updateListeningProgressUrl && pageContext.updateListeningProgressUrl !== "URL_NOT_DEFINED_update_listening_progress" &&
            pageContext.csrfToken) {
            sendListeningProgress(true);
        }
    });

    // Initial setup of review form visibility and button text (from audiobook_creator_details.js, adapted)
    const userReviewDataElement = document.getElementById('user-review-data'); // If this exists from old template
    let localUserReviewData = {};
    if (userReviewDataElement) { // Fallback if pageContext didn't get user review data fully
        try { localUserReviewData = JSON.parse(userReviewDataElement.textContent); } catch (e) { console.warn("Could not parse user-review-data script tag."); }
    }

    const hasReviewed = pageContext.current_user_has_reviewed || localUserReviewData.has_reviewed;
    const userRating = pageContext.user_review_object?.rating || localUserReviewData.rating;
    const userComment = pageContext.user_review_object?.comment || localUserReviewData.comment;

    if (reviewForm && submitReviewBtn && editReviewPrompt) {
        if (pageContext.isAuthenticated && hasReviewed) {
            reviewForm.classList.add('hidden');
            editReviewPrompt.classList.remove('hidden');
             if(editMyReviewButton) { // Ensure this specific button in prompt is updated
                editMyReviewButton.dataset.rating = userRating || "0";
                editMyReviewButton.dataset.comment = userComment || "";
            }
            submitReviewBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M17.414 2.586a2 2 0 00-2.828 0L7 10.172V13h2.828l7.586-7.586a2 2 0 000-2.828z"></path><path fill-rule="evenodd" d="M2 6a2 2 0 012-2h4a1 1 0 010 2H4v10h10v-4a1 1 0 112 0v4a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" clip-rule="evenodd"></path></svg>Edit Your Review'; // Default to "Edit" text if already reviewed
        } else if (pageContext.isAuthenticated) { // Authenticated but not reviewed
            editReviewPrompt.classList.add('hidden');
            reviewForm.classList.remove('hidden');
            submitReviewBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 mr-2.5" viewBox="0 0 20 20" fill="currentColor"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 16.571V11.5a1 1 0 011-1h.094a1 1 0 01.803.424l4.25 5.5a1 1 0 001.6-.25L17.894 3.962a1 1 0 00-.999-1.409l-7 .001z" /></svg>Submit Review';
        } else { // Not authenticated
             editReviewPrompt.classList.add('hidden'); // Hide prompt if not logged in
             // Review form itself is already handled by template for non-auth users
        }
    }

}); // End DOMContentLoaded