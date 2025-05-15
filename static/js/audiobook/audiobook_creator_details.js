/**
 * Audiobook Creator Details Page Script
 *
 * Handles audio playback, tab navigation, review submission/editing,
 * Stripe purchase flow, and view logging for the audiobook details page.
 */

// Wait for the DOM to be fully loaded before executing script
document.addEventListener('DOMContentLoaded', () => {

    // --- Constants and Global Variables ---
    const THEME_COLOR = '#091e65'; // Theme color for UI elements like progress bars
    const PLACEHOLDER_COVER_SRC = 'https://placehold.co/80x80/e5e7eb/4b5563?text=N/A';
    const PLAYBACK_SPEEDS = [1, 1.5, 2, 0.75]; // Available playback speeds

    let currentChapterIndex = -1; // Index of the currently loaded/playing chapter in the 'chapterItems' NodeList
    let currentlyPlayingListItemButton = null; // Reference to the play button element in the episode list for the current track
    let currentSpeedIndex = 0; // Index for the PLAYBACK_SPEEDS array
    let currentUserId = null; // Store the logged-in user's ID for review editing checks
    let stripe = null; // Stripe instance

    // --- Data Retrieval from HTML ---
    // Helper function to parse JSON data from script tags
    const getJsonData = (id) => {
        const element = document.getElementById(id);
        if (!element) {
            console.error(`Data script tag with id "${id}" not found.`);
            return null;
        }
        try {
            return JSON.parse(element.textContent);
        } catch (e) {
            console.error(`Error parsing JSON from script tag "${id}":`, e);
            return null;
        }
    };

    // Retrieve data passed from Django templates
    const userReviewData = getJsonData('user-review-data') || {};
    const stripePublishableKey = getJsonData('stripe-key-data');
    const djangoUrls = getJsonData('django-urls-data') || {};
    const pageContext = getJsonData('page-context-data') || {};

    // Assign retrieved data to variables
    currentUserId = userReviewData.user_id || null;
    const STRIPE_PUBLISHABLE_KEY = stripePublishableKey;
    const CREATE_CHECKOUT_SESSION_URL = djangoUrls.createCheckoutSessionUrl;
    const LOG_AUDIOBOOK_VIEW_URL = djangoUrls.logAudiobookViewUrl;
    const ADD_REVIEW_URL_BASE = djangoUrls.addReviewUrlBase; // Base URL, slug needs replacement
    const IS_AUTHENTICATED = pageContext.isAuthenticated || false;
    const AUDIOBOOK_SLUG = pageContext.audiobookSlug;
    const AUDIOBOOK_PRICE_FORMATTED = pageContext.audiobookPrice || 'N/A'; // For display fallback
    const CSRF_TOKEN = pageContext.csrfToken;

    // --- DOM Element Selectors ---
    // Audio Player Elements
    const audioPlayer = document.getElementById("audioPlayer");
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

    // Page Elements
    const mainCoverImage = document.getElementById("main-cover-image");
    const chapterItems = document.querySelectorAll('.chapter-item[data-audio-url]'); // Select only playable items
    const allChapterItems = document.querySelectorAll('.chapter-item'); // For getting total count correctly
    const tabs = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    // Review Elements
    const reviewForm = document.getElementById('review-form');
    const reviewRatingInput = document.getElementById('review-rating-input');
    const ratingValueInput = document.getElementById('rating-value');
    const ratingError = document.getElementById('rating-error');
    const commentInput = document.getElementById('comment');
    const submitReviewBtn = document.getElementById('submit-review-btn');
    const reviewsListDiv = document.getElementById('reviews-list');
    const noReviewsMessage = document.getElementById('no-reviews-message');
    const formMessageDiv = document.getElementById('form-message');
    const reviewCountSpan = document.getElementById('review-count'); // Count in the review tab header
    const reviewCountTabSpan = document.getElementById('review-count-tab'); // Count in the tab button itself
    const editReviewPrompt = document.getElementById('edit-review-prompt');
    const avgRatingDisplays = document.querySelectorAll('.star-rating-display'); // All elements showing average rating

    // Purchase Button
    const purchaseButton = document.getElementById('purchase-button');

    // --- Utility Functions ---

    /**
     * Formats time in seconds to a m:ss string.
     * @param {number} seconds - Time in seconds.
     * @returns {string} Formatted time string (e.g., "1:23").
     */
    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return '0:00';
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${minutes}:${secs < 10 ? '0' : ''}${secs}`;
    }

    /**
     * Escapes HTML special characters in a string.
     * @param {string} str - The string to escape.
     * @returns {string} The escaped string.
     */
    function escapeHTML(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        // Replace newlines with <br> for display in HTML
        return div.innerHTML.replace(/\n/g, '<br>');
    }

    // --- Tab Navigation ---

    /**
     * Shows the specified tab content and updates tab button styles.
     * @param {string} tabId - The ID suffix of the tab to show (e.g., 'about', 'episodes').
     */
    window.showTab = function(tabId) { // Attach to window to be callable from HTML onclick
        tabContents.forEach(content => content.classList.add('hidden'));
        tabs.forEach(tab => {
            const isSelected = tab.id === `tab-${tabId}`;
            tab.classList.toggle(`text-[#091e65]`, isSelected);
            tab.classList.toggle(`border-[#091e65]`, isSelected);
            tab.classList.toggle('font-semibold', isSelected);
            tab.classList.toggle('text-gray-500', !isSelected);
            tab.classList.toggle('hover:text-gray-700', !isSelected);
            tab.classList.toggle('hover:border-gray-300', !isSelected);
            tab.classList.toggle('border-transparent', !isSelected);
            tab.classList.toggle('font-medium', !isSelected);
            tab.setAttribute('aria-current', isSelected ? 'page' : 'false');
        });

        const selectedContent = document.getElementById(`content-${tabId}`);
        if (selectedContent) {
            selectedContent.classList.remove('hidden');
        } else {
            console.warn(`Tab content with id "content-${tabId}" not found.`);
        }
    }

    // --- Audio Player Logic ---

    /**
     * Updates the main player bar's play/pause button UI state.
     * Also updates the corresponding button in the episode list.
     * @param {'playing' | 'paused' | 'loading' | 'ended' | 'error'} state - The current player state.
     */
    function updatePlayerUIState(state) {
        const isPlaying = state === 'playing';
        const isLoading = state === 'loading';

        playerPlayIcon?.classList.toggle('hidden', isPlaying || isLoading);
        playerPauseIcon?.classList.toggle('hidden', !isPlaying);
        // Optionally add loading state to main button if desired
        // playerPlayPauseButton?.classList.toggle('animate-pulse', isLoading);

        if (currentlyPlayingListItemButton) {
            updateListItemButtonState(currentlyPlayingListItemButton, state);
        }
    }

    /**
     * Updates the UI state of a specific play button within the episode list.
     * @param {HTMLElement} listItemButton - The button element in the list item.
     * @param {'playing' | 'paused' | 'loading' | 'ended' | 'error'} state - The target state.
     */
    function updateListItemButtonState(listItemButton, state) {
        if (!listItemButton) return;
        const playIcon = listItemButton.querySelector('.play-icon');
        const pauseIcon = listItemButton.querySelector('.pause-icon');
        const loadingIcon = listItemButton.querySelector('.loading-icon');
        const chapterItemDiv = listItemButton.closest('.chapter-item');

        // Reset icons and styles
        playIcon?.classList.add('hidden');
        pauseIcon?.classList.add('hidden');
        loadingIcon?.classList.add('hidden');
        listItemButton.classList.remove('bg-pink-100', 'text-pink-600', 'hover:bg-pink-200', 'animate-pulse', 'opacity-50');
        listItemButton.classList.add(`bg-[#eef2ff]`, `text-[#091e65]`, `hover:bg-[#e0e7ff]`); // Default style
        chapterItemDiv?.classList.remove(`bg-indigo-100`, `border-indigo-400`, `ring-2`, `ring-indigo-300`, `ring-offset-1`);
        chapterItemDiv?.classList.add('bg-white', 'border-gray-200', `hover:border-indigo-300`, 'hover:bg-indigo-50'); // Default style

        // Apply state-specific styles
        switch (state) {
            case 'playing':
                pauseIcon?.classList.remove('hidden');
                listItemButton.classList.remove(`bg-[#eef2ff]`, `text-[#091e65]`, `hover:bg-[#e0e7ff]`);
                listItemButton.classList.add('bg-pink-100', 'text-pink-600', 'hover:bg-pink-200'); // Active playing style
                chapterItemDiv?.classList.remove('bg-white', 'border-gray-200', `hover:border-indigo-300`, 'hover:bg-indigo-50');
                chapterItemDiv?.classList.add(`bg-indigo-100`, `border-indigo-400`, `ring-2`, `ring-indigo-300`, `ring-offset-1`); // Highlight playing item
                break;
            case 'loading':
                loadingIcon?.classList.remove('hidden');
                listItemButton.classList.add('animate-pulse', 'opacity-50'); // Loading style
                break;
            case 'error':
                 playIcon?.classList.remove('hidden'); // Show play icon again on error
                 listItemButton.classList.add('opacity-50'); // Indicate error state subtly
                 // Optionally add specific error styling
                 break;
            case 'paused':
            case 'ended':
            default:
                playIcon?.classList.remove('hidden'); // Show play icon for paused/ended/default
                break;
        }
    }

    /** Shows the bottom player bar. */
    function showPlayerBar() {
        bottomPlayerBar?.classList.remove('translate-y-full');
    }

    /** Hides the bottom player bar. */
    function hidePlayerBar() {
        bottomPlayerBar?.classList.add('translate-y-full');
    }

    /**
     * Updates the player bar information (title, episode number, cover).
     * @param {number} playableChapterIndex - The index within the `chapterItems` NodeList.
     */
    function updatePlayerInfo(playableChapterIndex) {
        const chapterItem = chapterItems[playableChapterIndex];
        if (!chapterItem) return;

        const title = chapterItem.dataset.chapterTitle || 'Unknown Title';
        // Get the original index and total count from *all* items (including locked ones) for display
        const originalIndex = parseInt(chapterItem.dataset.chapterIndex ?? '-1', 10);
        const totalOriginalChapters = allChapterItems.length;

        if (playerEpisodeTitle) {
            playerEpisodeTitle.textContent = title;
            playerEpisodeTitle.title = title;
        }
        if (playerEpisodeNumber) {
            playerEpisodeNumber.textContent = `Episode ${originalIndex + 1} of ${totalOriginalChapters}`;
        }
        if (playerCoverImage) {
            playerCoverImage.src = mainCoverImage?.src || PLACEHOLDER_COVER_SRC;
        }
        if (playerPrevButton) {
            playerPrevButton.disabled = playableChapterIndex <= 0;
        }
        if (playerNextButton) {
            playerNextButton.disabled = playableChapterIndex >= chapterItems.length - 1;
        }
    }

    /**
     * Initiates playback of a chapter when its list item button is clicked.
     * Handles loading, playing, pausing, and switching between chapters.
     * @param {HTMLElement} buttonElement - The play button element clicked in the episode list.
     */
    window.playChapter = function(buttonElement) { // Attach to window
        const chapterItem = buttonElement.closest('.chapter-item');
        // Double-check if it's somehow locked (shouldn't happen if selector is correct)
        if (!chapterItem || chapterItem.classList.contains('opacity-60') || chapterItem.classList.contains('cursor-not-allowed')) return;

        const audioUrl = chapterItem?.dataset.audioUrl;
        const chapterTitle = chapterItem?.dataset.chapterTitle || 'Episode';
        const playableChapterIndex = Array.from(chapterItems).findIndex(item => item === chapterItem);

        // Validate audio URL and index
        if (!audioUrl || audioUrl === 'None' || audioUrl.endsWith('?url=') || audioUrl.includes('?url=None') || playableChapterIndex < 0) {
            Swal.fire({
                icon: 'error',
                title: 'Audio Unavailable',
                text: `Could not load audio data for "${chapterTitle}". The file might be missing or inaccessible.`,
                customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' }
            });
            updateListItemButtonState(buttonElement, 'error'); // Mark button as errored
            return;
        }

        const isCurrentlyPlayingThis = currentlyPlayingListItemButton === buttonElement && !audioPlayer.paused;

        // If another chapter is playing, reset its button state first
        if (currentlyPlayingListItemButton && currentlyPlayingListItemButton !== buttonElement) {
             updateListItemButtonState(currentlyPlayingListItemButton, 'paused'); // Reset previous button
        }

        // --- Play/Pause Logic ---
        if (isCurrentlyPlayingThis) {
            // If clicking the button of the currently playing chapter, pause it
            audioPlayer.pause();
            // UI update handled by 'pause' event listener
        } else {
            // If clicking a new chapter or resuming a paused one

            // Reset state of the previously playing item's list button if different
             if (currentlyPlayingListItemButton && currentlyPlayingListItemButton !== buttonElement) {
                 updateListItemButtonState(currentlyPlayingListItemButton, 'paused');
             }

            currentChapterIndex = playableChapterIndex;
            currentlyPlayingListItemButton = buttonElement;

            // Update UI to loading state
            updateListItemButtonState(currentlyPlayingListItemButton, 'loading');
            updatePlayerUIState('loading');
            updatePlayerInfo(currentChapterIndex); // Update player bar info
            showPlayerBar(); // Ensure player bar is visible

            // Load and play the audio
            audioPlayer.src = audioUrl;
            audioPlayer.load(); // Important for some browsers

            audioPlayer.play().catch(e => {
                console.error("Audio playback error:", e);
                let errorTitle = 'Playback Error';
                let errorText = 'Could not play audio. Please try again.';
                if (e.name === 'NotAllowedError') { errorTitle = 'Autoplay Blocked'; errorText = 'Playback was blocked by the browser. Please click play again.'; }
                else if (e.name === 'AbortError') { errorTitle = 'Load Interrupted'; errorText = 'Audio loading was interrupted.'; }
                else if (e.name === 'NotSupportedError') { errorTitle = 'Format Not Supported'; errorText = 'The audio format might not be supported by your browser.'; }

                Swal.fire({
                    icon: 'error',
                    title: errorTitle,
                    text: errorText,
                    customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' }
                });
                updatePlayerUIState('error'); // Update main player UI
                updateListItemButtonState(currentlyPlayingListItemButton, 'error'); // Update list item button UI
            });
        }
    }

    /** Toggles play/pause state of the current audio track. Plays first track if none selected. */
    window.togglePlayPause = function() { // Attach to window
        if (currentChapterIndex < 0 && chapterItems.length > 0) {
            // If nothing is selected, play the first available chapter
            const firstPlayableChapterButton = chapterItems[0]?.querySelector('.play-button');
            if (firstPlayableChapterButton) {
                playChapter(firstPlayableChapterButton); // Use playChapter to handle loading etc.
            } else {
                // No playable chapters found
                Swal.fire({ toast: true, position: 'bottom-end', icon: 'info', title: 'No playable episodes found.', showConfirmButton: false, timer: 2500, timerProgressBar: true, customClass: { popup: 'bg-gray-100 text-gray-800 rounded-lg shadow-lg', title: 'text-sm font-medium', timerProgressBar: `bg-[${THEME_COLOR}]` } });
            }
            return;
        }

        // If a chapter is loaded
        if (audioPlayer.paused || audioPlayer.ended) {
             if (audioPlayer.src && audioPlayer.src !== window.location.href) { // Check if src is valid
                 audioPlayer.play().catch(e => {
                     console.error("Audio resume error:", e);
                     Swal.fire({ icon: 'error', title: 'Playback Error', text: 'Could not resume audio.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                     updatePlayerUIState('error');
                 });
             } else if (currentChapterIndex >= 0) {
                 // If src is somehow invalid but we have an index, try playing that chapter again
                 const currentButton = chapterItems[currentChapterIndex]?.querySelector('.play-button');
                 if (currentButton) { playChapter(currentButton); } else { closePlayer(); } // Fallback
             }
        } else {
            audioPlayer.pause();
        }
    }

    /** Plays the next available chapter in the list. */
    window.playNextChapter = function() { // Attach to window
        const nextPlayableIndex = currentChapterIndex + 1;
        if (nextPlayableIndex < chapterItems.length) {
            const nextButton = chapterItems[nextPlayableIndex]?.querySelector('.play-button');
            if (nextButton) {
                playChapter(nextButton);
            }
        } else {
             // Optional: Notify user they reached the end or loop back
             console.log("Reached end of playable chapters.");
             // audioPlayer.pause(); // Or pause if desired
        }
    }

    /** Plays the previous available chapter in the list. */
    window.playPreviousChapter = function() { // Attach to window
        const prevPlayableIndex = currentChapterIndex - 1;
        if (prevPlayableIndex >= 0) {
            const prevButton = chapterItems[prevPlayableIndex]?.querySelector('.play-button');
            if (prevButton) {
                playChapter(prevButton);
            }
        }
    }

    /** Closes the player bar, stops audio, and resets player state. */
    window.closePlayer = function() { // Attach to window
        audioPlayer.pause();
        audioPlayer.src = ''; // Clear source
        hidePlayerBar();

        // Reset the button state of the chapter that was playing
        if (currentlyPlayingListItemButton) {
            updateListItemButtonState(currentlyPlayingListItemButton, 'paused'); // Reset to default paused state
        }

        // Reset global state variables
        currentlyPlayingListItemButton = null;
        currentChapterIndex = -1;

        // Reset player bar UI elements
        if (playerSeekBar) playerSeekBar.value = 0;
        if (playerCurrentTime) playerCurrentTime.textContent = '0:00';
        if (playerDuration) playerDuration.textContent = '0:00';
        if (playerEpisodeTitle) playerEpisodeTitle.textContent = 'Select an episode';
        if (playerEpisodeNumber) playerEpisodeNumber.textContent = 'Episode N/A';
        if (playerCoverImage) playerCoverImage.src = PLACEHOLDER_COVER_SRC;
        if (playerPrevButton) playerPrevButton.disabled = true;
        if (playerNextButton) playerNextButton.disabled = chapterItems.length <= 1; // Disable if only 0 or 1 item
        updatePlayerUIState('paused'); // Ensure main play button shows 'play'

        // Reset playback speed
        currentSpeedIndex = 0;
        audioPlayer.playbackRate = PLAYBACK_SPEEDS[currentSpeedIndex];
        if (playerSpeedButton) playerSpeedButton.textContent = `${PLAYBACK_SPEEDS[currentSpeedIndex]}x`;
    }

    /** Cycles through the available playback speeds. */
    window.cyclePlaybackSpeed = function() { // Attach to window
        currentSpeedIndex = (currentSpeedIndex + 1) % PLAYBACK_SPEEDS.length;
        const newSpeed = PLAYBACK_SPEEDS[currentSpeedIndex];
        audioPlayer.playbackRate = newSpeed;
        if (playerSpeedButton) playerSpeedButton.textContent = `${newSpeed}x`;
    }

    // --- Audio Player Event Listeners ---
    if (audioPlayer) {
        audioPlayer.addEventListener('play', () => updatePlayerUIState('playing'));
        audioPlayer.addEventListener('pause', () => updatePlayerUIState('paused'));
        audioPlayer.addEventListener('ended', () => {
            updatePlayerUIState('ended');
            playNextChapter(); // Automatically play next on end
        });
        audioPlayer.addEventListener('error', (e) => {
             console.error("Audio Element Error:", e);
             updatePlayerUIState('error');
             // Optionally show a generic error message if not handled elsewhere
        });
        audioPlayer.addEventListener('loadedmetadata', () => {
            if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
                if (playerDuration) playerDuration.textContent = formatTime(audioPlayer.duration);
                if (playerSeekBar) playerSeekBar.max = audioPlayer.duration;
            } else {
                // Handle cases where duration is not available (e.g., live streams, some errors)
                if (playerDuration) playerDuration.textContent = '--:--';
                if (playerSeekBar) playerSeekBar.max = 0; // Or a default value
                console.warn("Audio duration is invalid or infinite.");
            }
            // Reset time and seek bar visually on new track load
            if (playerCurrentTime) playerCurrentTime.textContent = '0:00';
            if (playerSeekBar) playerSeekBar.value = 0;
        });
        audioPlayer.addEventListener('timeupdate', () => {
            // Update current time and seek bar position during playback
            if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
                if (playerCurrentTime) playerCurrentTime.textContent = formatTime(audioPlayer.currentTime);
                // Only update seek bar value if the user is not currently dragging it
                if (playerSeekBar && !playerSeekBar.matches(':active')) {
                     playerSeekBar.value = audioPlayer.currentTime;
                }
            }
        });
    }

    // Seek Bar Interaction
    if (playerSeekBar) {
        playerSeekBar.addEventListener('input', () => {
            // Update audio current time when the user drags the seek bar
            if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration) && audioPlayer.readyState >= 1) { // readyState >= 1 means metadata is loaded
                audioPlayer.currentTime = playerSeekBar.value;
            }
        });
    }

    // --- Review Form Logic ---
    if (reviewForm && reviewRatingInput && ratingValueInput && commentInput && submitReviewBtn && reviewsListDiv && formMessageDiv && reviewCountSpan && reviewCountTabSpan && editReviewPrompt) {
        const stars = reviewRatingInput.querySelectorAll('i[data-rating-value]');

        /**
         * Updates the visual state of the rating stars.
         * @param {number} rating - The rating value (1-5).
         */
        function updateStarsUI(rating) {
            stars.forEach(star => {
                const starValue = parseInt(star.dataset.ratingValue);
                const isSelected = starValue <= rating;
                star.classList.toggle('far', !isSelected); // Empty star icon
                star.classList.toggle('fas', isSelected); // Solid star icon
                star.classList.toggle('text-yellow-400', isSelected); // Selected color
                star.classList.toggle('text-gray-300', !isSelected); // Default color
                star.classList.toggle('hover:text-yellow-300', !isSelected); // Hover effect only on unselected
            });
            ratingValueInput.value = rating; // Update hidden input
            if (ratingError) ratingError.textContent = ''; // Clear error on selection
        }

        // Star Rating Input Hover/Click Listeners
        reviewRatingInput.addEventListener('mouseover', (event) => {
            if (event.target.matches('i[data-rating-value]')) {
                const hoverRating = parseInt(event.target.dataset.ratingValue);
                // Temporarily highlight stars up to the hovered one
                stars.forEach(star => {
                    const starValue = parseInt(star.dataset.ratingValue);
                    star.classList.toggle('text-yellow-400', starValue <= hoverRating);
                    star.classList.toggle('text-gray-300', starValue > hoverRating);
                    star.classList.toggle('fas', starValue <= hoverRating);
                    star.classList.toggle('far', starValue > hoverRating);
                });
            }
        });

        reviewRatingInput.addEventListener('mouseout', () => {
            // Restore stars to the currently selected rating value
            updateStarsUI(parseInt(ratingValueInput.value || '0'));
        });

        reviewRatingInput.addEventListener('click', (event) => {
            if (event.target.matches('i[data-rating-value]')) {
                const clickedRating = parseInt(event.target.dataset.ratingValue);
                updateStarsUI(clickedRating); // Set the rating permanently
            }
        });

        /**
         * Creates HTML string for a single review item.
         * @param {object} reviewData - Data for the review.
         * @returns {string} HTML string for the review item.
         */
        function createReviewHtml(reviewData) {
            let starsHtml = '';
            const rating = reviewData.rating || 0;
            const fullStars = Math.floor(rating);
            const emptyStars = 5 - fullStars;
            for (let i = 0; i < fullStars; i++) starsHtml += '<i class="fas fa-star text-yellow-400"></i>';
            for (let i = 0; i < emptyStars; i++) starsHtml += '<i class="far fa-star text-gray-300"></i>';

            const profilePicHtml = reviewData.user_profile_pic
                ? `<img class="h-10 w-10 rounded-full object-cover shadow-sm" src="${reviewData.user_profile_pic}" alt="${escapeHTML(reviewData.user_name)}">`
                : `<span class="h-10 w-10 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center text-gray-500 shadow-sm"><i class="fas fa-user text-lg"></i></span>`;

            const escapedComment = escapeHTML(reviewData.comment || ''); // Escape and handle potential line breaks
            const commentHtml = escapedComment ? `<div class="mt-2 text-sm text-gray-600 prose prose-sm max-w-none leading-relaxed"><p>${escapedComment}</p></div>` : '';

            const timeAgo = reviewData.timesince || 'Just now';
            // Escape comment for data attribute, ensuring valid JSON string literal
            const escapedCommentForDataAttr = JSON.stringify(reviewData.comment || '').replace(/'/g, "\\'"); // Escape single quotes within JSON string

            // Show edit button only if the review belongs to the current user
            const editButtonHtml = (reviewData.user_id && reviewData.user_id === currentUserId)
                ? `<div class="mt-2 text-xs">
                       <button onclick="handleEditClick(this)"
                               data-review-id="${reviewData.review_id}"
                               data-rating="${reviewData.rating}"
                               data-comment='${escapedCommentForDataAttr}'
                               class="text-indigo-600 hover:text-indigo-800 hover:underline font-medium focus:outline-none focus:ring-1 focus:ring-indigo-300 rounded px-1 py-0.5">
                           <i class="fas fa-pencil-alt mr-1 text-xs"></i>Edit
                       </button>
                   </div>`
                : '';

            return `
                <div class="review-item flex space-x-4 py-4 border-b border-gray-100 last:border-b-0" id="review-${reviewData.review_id}">
                    <div class="flex-shrink-0 pt-1">${profilePicHtml}</div>
                    <div class="flex-grow">
                        <div class="flex items-center justify-between mb-1">
                            <h5 class="text-sm font-semibold text-gray-800">${escapeHTML(reviewData.user_name)}</h5>
                            <time datetime="${reviewData.created_at || new Date().toISOString()}" class="flex-shrink-0 ml-4 text-xs text-gray-400">${timeAgo}</time>
                        </div>
                        <div class="mb-1 flex items-center star-rating-display text-xs">${starsHtml}</div>
                        ${commentHtml}
                        ${editButtonHtml}
                    </div>
                </div>`;
        }

        /** Updates all average rating display elements on the page */
        function updateAverageRatingDisplays(newAvgRatingStr, reviewCount) {
             const newAvg = parseFloat(newAvgRatingStr);
             let starsHtml = '';
             let ratingText = '';
             let reviewCountTextBase = `(${reviewCount} rating${reviewCount !== 1 ? 's' : ''})`;

             if (!isNaN(newAvg) && newAvg > 0) {
                 const fullStars = Math.floor(newAvg);
                 const hasHalfStar = newAvg - fullStars >= 0.5;
                 const emptyStars = 5 - fullStars - (hasHalfStar ? 1 : 0);
                 for(let i=0; i<fullStars; i++) starsHtml += '<i class="fas fa-star text-yellow-400"></i>';
                 if(hasHalfStar) starsHtml += '<i class="fas fa-star-half-alt text-yellow-400"></i>';
                 for(let i=0; i<emptyStars; i++) starsHtml += '<i class="far fa-star text-gray-300"></i>';
                 ratingText = `<span class="font-semibold text-gray-700 ml-1.5">${newAvg.toFixed(1)}</span>`;
             } else {
                 // Display 5 empty stars if no rating
                 for(let i=0; i<5; i++) starsHtml += '<i class="far fa-star text-gray-300"></i>';
                 ratingText = `<span class="text-gray-400 italic ml-1.5">No ratings yet</span>`;
                 reviewCountTextBase = ''; // Don't show count if no ratings
             }

             avgRatingDisplays.forEach(el => {
                 const isReviewTabAvg = el.closest('#content-reviews');
                 const avgSuffix = isReviewTabAvg ? ' avg' : '';
                 const reviewCountText = reviewCountTextBase ? `<span class="ml-1">${reviewCountTextBase}${avgSuffix}</span>` : '';
                 // Ensure correct text size (base for main display, sm for review tab)
                 const textSizeClass = el.closest('#content-reviews') ? 'text-sm' : 'text-base';
                 el.className = `flex items-center star-rating-display ${textSizeClass}`; // Reset classes and set size
                 el.innerHTML = starsHtml + ratingText + reviewCountText;
             });
        }


        // Review Form Submission Handler
        reviewForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            formMessageDiv.textContent = ''; // Clear previous messages
            formMessageDiv.className = 'text-sm flex-grow'; // Reset class
            ratingError.textContent = '';
            submitReviewBtn.disabled = true;
            submitReviewBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Submitting...'; // Loading state

            const rating = parseInt(ratingValueInput.value || '0');
            const comment = commentInput.value.trim();
            // Construct the specific URL for this audiobook
            const url = ADD_REVIEW_URL_BASE.replace('PLACEHOLDER_SLUG', AUDIOBOOK_SLUG);

            if (rating === 0) {
                ratingError.textContent = 'Please select a rating (1-5 stars).';
                submitReviewBtn.disabled = false;
                submitReviewBtn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Submit Review';
                return;
            }

            if (!url || url.includes('PLACEHOLDER_SLUG')) {
                 formMessageDiv.textContent = 'Error: Could not determine submission URL.';
                 formMessageDiv.classList.add('text-red-600');
                 submitReviewBtn.disabled = false;
                 submitReviewBtn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Submit Review';
                 return;
            }

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': CSRF_TOKEN, // Use the token retrieved earlier
                        'X-Requested-With': 'XMLHttpRequest' // Standard header for Django AJAX detection
                    },
                    body: JSON.stringify({ rating: rating, comment: comment })
                });

                const result = await response.json();

                if (response.ok && result.status === 'success' && result.review_data) {
                    formMessageDiv.textContent = result.message || 'Review submitted successfully!';
                    formMessageDiv.classList.add('text-green-600');
                    reviewForm.classList.add('hidden'); // Hide form
                    editReviewPrompt.classList.remove('hidden'); // Show edit prompt

                    // Create or update review in the list
                    const newReviewHtml = createReviewHtml(result.review_data);
                    const existingReviewElement = document.getElementById(`review-${result.review_data.review_id}`);

                    if (existingReviewElement) {
                        existingReviewElement.outerHTML = newReviewHtml; // Replace existing review
                    } else {
                        reviewsListDiv.insertAdjacentHTML('afterbegin', newReviewHtml); // Add new review to top
                        noReviewsMessage?.classList.add('hidden'); // Hide "no reviews" message if it was visible
                        // Ensure proper spacing/borders if adding the first review after others existed (unlikely but safe)
                        if (reviewsListDiv.children.length > 1) {
                            const secondChild = reviewsListDiv.children[1];
                             if(secondChild && !secondChild.classList.contains('border-t')) { // Check if divider needed
                                 // This logic might need adjustment based on exact HTML structure/styling
                                 // secondChild.classList.add('border-t', 'border-gray-200', 'pt-4');
                             }
                        }
                    }

                    // Update review counts and average rating display
                    const currentReviewCount = document.querySelectorAll('#reviews-list .review-item').length;
                    reviewCountSpan.textContent = currentReviewCount;
                    reviewCountTabSpan.textContent = currentReviewCount; // Update tab count too
                    updateAverageRatingDisplays(result.new_average_rating, currentReviewCount);


                    // Reset form for potential future edits (optional)
                    // updateStarsUI(0);
                    // commentInput.value = '';

                } else {
                    // Handle errors reported by the server
                    formMessageDiv.textContent = result.message || 'An error occurred while submitting the review.';
                    formMessageDiv.classList.add('text-red-600');
                    if (result.errors) {
                        // Display specific field errors if provided (e.g., under the rating or comment box)
                        console.error("Server validation errors:", result.errors);
                        if (result.errors.rating && ratingError) ratingError.textContent = result.errors.rating.join(' ');
                        // Add similar logic for comment errors if needed
                    }
                }
            } catch (error) {
                console.error("Network error submitting review:", error);
                formMessageDiv.textContent = 'An unexpected network error occurred. Please try again.';
                formMessageDiv.classList.add('text-red-600');
            } finally {
                submitReviewBtn.disabled = false;
                submitReviewBtn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Submit Review'; // Reset button text
            }
        });
    } // End of review form logic block

    /** Shows the review form and hides the edit prompt. */
    window.showReviewForm = function() { // Attach to window
        reviewForm?.classList.remove('hidden');
        editReviewPrompt?.classList.add('hidden');
        reviewForm?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Focus the first interactive element, maybe the first star or the comment box
        reviewRatingInput?.querySelector('i')?.focus();
    }

    /**
     * Populates the review form with existing review data for editing.
     * Called by the 'Edit' button's onclick handler.
     * @param {HTMLElement} buttonElement - The edit button that was clicked.
     */
    window.handleEditClick = function(buttonElement) { // Attach to window
        if (!reviewForm) return; // Ensure form exists

        // const reviewId = buttonElement.dataset.reviewId; // Not strictly needed for populating form
        const rating = parseInt(buttonElement.dataset.rating || '0');
        let comment = '';
        try {
            // Safely parse the comment, which might be JSON stringified
            comment = JSON.parse(buttonElement.dataset.comment || '""');
        } catch (e) {
            console.warn("Could not parse comment data attribute, using raw value.", buttonElement.dataset.comment);
            comment = buttonElement.dataset.comment || ''; // Fallback to raw value
        }

        // Populate form fields
        if (ratingValueInput && rating > 0) {
            updateStarsUI(rating); // Update stars visually and hidden input
        } else {
             updateStarsUI(0); // Reset stars if rating is invalid
        }
        if (commentInput) {
            commentInput.value = comment;
        }

        // Show the form, hide the prompt, and scroll/focus
        showReviewForm();
    }

    /** Scrolls to the reviews tab and focuses the form if visible. */
    window.scrollToReviews = function() { // Attach to window
        const reviewsTabButton = document.getElementById('tab-reviews');
        const reviewsContent = document.getElementById('content-reviews');
        if (reviewsTabButton && reviewsContent) {
            showTab('reviews'); // Switch to the reviews tab
            // Scroll the reviews content area into view
            reviewsContent.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // If the form is now visible (not hidden), focus an element within it
            if (reviewForm && !reviewForm.classList.contains('hidden')) {
                reviewRatingInput?.querySelector('i')?.focus(); // Focus the first star
            }
        }
    }

    // --- Stripe Purchase Logic ---
    if (purchaseButton) {
        if (!STRIPE_PUBLISHABLE_KEY) {
            console.error("Stripe Publishable Key is missing.");
            purchaseButton.disabled = true;
            purchaseButton.innerHTML = '<i class="fas fa-exclamation-circle mr-2"></i> Payment Config Error';
            purchaseButton.title = "Stripe configuration is missing. Cannot process payments.";
        } else if (!CSRF_TOKEN) {
             console.error("CSRF Token is missing.");
             purchaseButton.disabled = true;
             purchaseButton.innerHTML = '<i class="fas fa-exclamation-circle mr-2"></i> Security Token Error';
             purchaseButton.title = "Security token (CSRF) is missing. Cannot process payments.";
        } else {
            // Initialize Stripe only if the key is present
            try {
                stripe = Stripe(STRIPE_PUBLISHABLE_KEY);
            } catch (e) {
                console.error("Failed to initialize Stripe:", e);
                 purchaseButton.disabled = true;
                 purchaseButton.innerHTML = '<i class="fas fa-exclamation-circle mr-2"></i> Payment Init Error';
                 purchaseButton.title = "Failed to initialize the payment system.";
            }

            // Add click listener only if Stripe initialized successfully
            if (stripe) {
                purchaseButton.addEventListener('click', async (event) => {
                    event.preventDefault();

                    // Check again if Stripe object is valid (paranoid check)
                    if (!stripe) {
                         Swal.fire({ icon: 'error', title: 'Payment System Error', text: 'Stripe object is not available. Please refresh.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                         return;
                    }

                    purchaseButton.disabled = true;
                    purchaseButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Processing...';
                    const audiobookSlugForPurchase = purchaseButton.dataset.audiobookSlug;

                    if (!audiobookSlugForPurchase) {
                        Swal.fire({ icon: 'error', title: 'Error', text: 'Could not identify the audiobook. Please refresh the page.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                        purchaseButton.disabled = false;
                        purchaseButton.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${AUDIOBOOK_PRICE_FORMATTED})`;
                        return;
                    }

                    if (!CREATE_CHECKOUT_SESSION_URL) {
                         Swal.fire({ icon: 'error', title: 'Configuration Error', text: 'Checkout URL is not configured.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                         purchaseButton.disabled = false;
                         purchaseButton.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${AUDIOBOOK_PRICE_FORMATTED})`;
                         return;
                    }


                    try {
                        const response = await fetch(CREATE_CHECKOUT_SESSION_URL, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': CSRF_TOKEN,
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            body: JSON.stringify({
                                item_type: 'audiobook',
                                item_id: audiobookSlugForPurchase // Use the slug from the button's data attribute
                            })
                        });

                        const sessionData = await response.json();

                        if (response.ok && sessionData.sessionId) {
                            // Redirect to Stripe Checkout
                            const { error } = await stripe.redirectToCheckout({ sessionId: sessionData.sessionId });
                            if (error) {
                                console.error("Stripe redirect error:", error);
                                Swal.fire({ icon: 'error', title: 'Payment Redirect Error', text: error.message, customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                                purchaseButton.disabled = false; // Re-enable button on redirect failure
                                purchaseButton.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${AUDIOBOOK_PRICE_FORMATTED})`;
                            }
                            // If redirect is successful, the user leaves the page.
                        } else if (response.status === 400 && sessionData.status === 'already_purchased') {
                             // Handle case where user already owns the item (server-side check)
                             Swal.fire({ icon: 'info', title: 'Already Purchased', text: sessionData.message, customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-blue-500 border-blue-300' } });
                             purchaseButton.style.display = 'none'; // Hide purchase button
                             // Optionally, update the UI to show the "Purchased" status dynamically if not already shown
                             const accessStatusDiv = purchaseButton.closest('.w-full.p-5.bg-white');
                             if (accessStatusDiv) {
                                 const existingPurchasedMessage = accessStatusDiv.querySelector('.bg-gradient-to-r.from-green-50');
                                 if (!existingPurchasedMessage) {
                                     let premiumInfoDiv = accessStatusDiv.querySelector('.bg-gradient-to-r.from-blue-50');
                                     let newMsgHtml = '<div class="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-300 text-green-900 px-4 py-3 rounded-lg relative text-center text-sm shadow-sm font-medium mt-4" role="alert"><i class="fas fa-check-circle mr-2 text-green-600"></i> Purchased & Unlocked</div>';
                                      if (premiumInfoDiv) {
                                          premiumInfoDiv.insertAdjacentHTML('afterend', newMsgHtml);
                                      } else {
                                          // Find the heading and insert after that if premium info wasn't present
                                          const heading = accessStatusDiv.querySelector('h3');
                                          if (heading) heading.insertAdjacentHTML('afterend', newMsgHtml);
                                          else accessStatusDiv.insertAdjacentHTML('beforeend', newMsgHtml); // Fallback
                                      }
                                 }
                             }
                        } else {
                            // Handle other errors from the session creation endpoint
                            const errorMessage = sessionData.error || 'Could not initiate purchase. Please try again.';
                            console.error("Checkout session creation error:", sessionData);
                            Swal.fire({ icon: 'error', title: 'Purchase Error', text: errorMessage, customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                            purchaseButton.disabled = false;
                            purchaseButton.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${AUDIOBOOK_PRICE_FORMATTED})`;
                        }
                    } catch (error) {
                        console.error("Network error during purchase initiation:", error);
                        Swal.fire({ icon: 'error', title: 'Network Error', text: 'Could not connect to the server. Please check your connection and try again.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                        purchaseButton.disabled = false;
                        purchaseButton.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${AUDIOBOOK_PRICE_FORMATTED})`;
                    }
                });
            } // end if(stripe)
        } // end else (Stripe key and CSRF token are present)
    } // End of purchase button logic block

    // --- View Logging ---
    /** Logs a view for the audiobook if the user is authenticated. */
    function logViewForAudiobook() {
        const audiobookIdForView = audioPlayer?.dataset.audiobookId; // Get ID from player data attribute
        if (!IS_AUTHENTICATED || !audiobookIdForView || !LOG_AUDIOBOOK_VIEW_URL || !CSRF_TOKEN) {
            // console.log("View logging prerequisites not met.");
            return; // Don't log if not authenticated, no ID, no URL, or no token
        }

        fetch(LOG_AUDIOBOOK_VIEW_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded', // Use form encoding for simple data
                'X-CSRFToken': CSRF_TOKEN,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: `audiobook_id=${encodeURIComponent(audiobookIdForView)}` // Send audiobook ID
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // console.log('Audiobook view logged successfully.');
                // Optionally update the view count display dynamically if needed
                // const viewCountElement = document.querySelector('.flex.items-center.space-x-1.text-gray-600 span:last-child');
                // if (viewCountElement && data.new_view_count) {
                //    viewCountElement.textContent = `${data.new_view_count.toLocaleString()} Views`;
                // }
            } else {
                console.warn('Failed to log audiobook view:', data.message || 'Unknown error');
            }
        })
        .catch(error => {
            console.error('Error logging audiobook view:', error);
        });
    }


    // --- Initialization ---
    // Set initial tab
    showTab('about');

    // Hide player bar initially
    hidePlayerBar();

    // Set initial player button states
    if (playerPrevButton) playerPrevButton.disabled = true;
    if (playerNextButton) playerNextButton.disabled = chapterItems.length <= 1;
    if (playerSpeedButton) playerSpeedButton.textContent = `${PLAYBACK_SPEEDS[currentSpeedIndex]}x`;

    // Initialize review form state based on userReviewData
    if (userReviewData.has_reviewed && reviewForm && editReviewPrompt) {
        const initialRating = parseInt(userReviewData.rating || '0');
        const initialComment = userReviewData.comment || '';
        if (ratingValueInput && initialRating > 0) { updateStarsUI(initialRating); }
        if (commentInput) { commentInput.value = initialComment; }
        reviewForm.classList.add('hidden');
        editReviewPrompt.classList.remove('hidden');
    } else if (editReviewPrompt) {
        editReviewPrompt.classList.add('hidden'); // Ensure edit prompt is hidden if no prior review
    }

    // Log the view for the audiobook on page load if applicable
    logViewForAudiobook();

}); // End DOMContentLoaded
