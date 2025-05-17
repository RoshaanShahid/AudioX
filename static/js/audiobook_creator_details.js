document.addEventListener('DOMContentLoaded', () => {

    // --- Constants and Global Variables ---
    const THEME_COLOR = '#091e65';
    const PLACEHOLDER_COVER_SRC = 'https://placehold.co/80x80/e5e7eb/4b5563?text=N/A';
    const PLAYBACK_SPEEDS = [1, 1.5, 2, 0.75];
    const DEFAULT_SUBMIT_BUTTON_HTML = '<i class="fas fa-paper-plane mr-2"></i>Submit Review';
    const UPDATE_SUBMIT_BUTTON_HTML = '<i class="fas fa-save mr-2"></i>Update Review';

    let currentChapterIndex = -1;
    let currentlyPlayingListItemButton = null;
    let currentSpeedIndex = 0;
    let currentUserId = null; // Will be populated from userReviewData
    let stripe = null;

    // --- Data Retrieval from HTML ---
    // Function to safely retrieve and parse JSON data from a script tag
    const getJsonData = (id) => {
        const element = document.getElementById(id);
        if (!element) {
            return null;
        }
        try {
            return JSON.parse(element.textContent);
        } catch (e) {
            return null;
        }
    };

    // Retrieve data from script tags embedded in the HTML
    const userReviewData = getJsonData('user-review-data') || {};
    const stripePublishableKey = getJsonData('stripe-key-data');
    const djangoUrls = getJsonData('django-urls-data') || {};
    const pageContext = getJsonData('page-context-data') || {};

    // Assign retrieved data to constants and variables
    currentUserId = userReviewData.user_id || null;
    const STRIPE_PUBLISHABLE_KEY = stripePublishableKey;
    const CREATE_CHECKOUT_SESSION_URL = djangoUrls.createCheckoutSessionUrl;
    const LOG_AUDIOBOOK_VIEW_URL = djangoUrls.logAudiobookViewUrl;
    const ADD_REVIEW_URL_BASE = djangoUrls.addReviewUrlBase;
    const IS_AUTHENTICATED = pageContext.isAuthenticated || false;
    const AUDIOBOOK_SLUG = pageContext.audiobookSlug;
    const AUDIOBOOK_PRICE_FORMATTED = pageContext.audiobookPrice || 'N/A';
    const CSRF_TOKEN = pageContext.csrfToken;

    // --- DOM Element Selectors ---
    // Select various elements from the DOM
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
    const playerDurationDisplay = document.getElementById("player-duration");
    const playerSeekBar = document.getElementById("player-seek-bar");
    const playerSpeedButton = document.getElementById("player-speed-button");
    const playerCloseButton = document.getElementById("player-close-button");

    const mainCoverImage = document.getElementById("main-cover-image");
    const chapterItems = document.querySelectorAll('.chapter-item[data-audio-url]');
    const allChapterItems = document.querySelectorAll('.chapter-item');

    const tabs = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    const reviewForm = document.getElementById('review-form');
    const reviewRatingInput = document.getElementById('review-rating-input');
    const ratingValueInput = document.getElementById('rating-value-input');
    const ratingError = document.getElementById('rating-error');
    const commentInput = document.getElementById('comment-input');
    const submitReviewBtn = document.getElementById('submit-review-btn');
    const reviewsListDiv = document.getElementById('reviews-list');
    const noReviewsMessage = document.getElementById('no-reviews-message');
    const formMessageDiv = document.getElementById('form-message');
    const reviewCountSpan = document.getElementById('review-count');
    const reviewCountTabSpan = document.getElementById('review-count-tab');
    const editReviewPrompt = document.getElementById('edit-review-prompt');
    const avgRatingDisplays = document.querySelectorAll('.star-rating-display');
    const audiobookTotalViewsSpan = document.getElementById('audiobook-total-views-span');

    const purchaseButton = document.getElementById('purchase-button');
    const shareButton = document.getElementById('share-button');
    const rateButton = document.getElementById('rate-button');
    const editMyReviewButtonFromPrompt = document.getElementById('edit-my-review-button');


    // --- Utility Functions ---
    // Formats time in seconds into MM:SS format
    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) return '0:00';
        const minutes = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${minutes}:${secs < 10 ? '0' : ''}${secs}`;
    }

    // Escapes HTML characters for safe display
    function escapeHTML(str) {
        if (str === null || typeof str === 'undefined') return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;")
            .replace(/\n/g, '<br>'); // Keep newlines as <br> for display
    }

    // Escapes HTML characters for safe use in data attributes
    function escapeForDataAttr(str) {
        if (str === null || typeof str === 'undefined') return '';
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }


    // --- Tab Navigation ---
    // Function to show a specific tab and hide others
    function showTab(tabId) {
        tabContents.forEach(content => content.classList.add('hidden'));
        tabs.forEach(tab => {
            const currentButtonTabId = tab.id ? tab.id.replace('tab-', '') : '';
            const isSelected = currentButtonTabId === tabId;
            tab.classList.toggle('active', isSelected);
            tab.classList.toggle('border-indigo-600', isSelected);
            tab.classList.toggle('text-indigo-600', isSelected);
            tab.classList.toggle('font-semibold', isSelected);
            tab.classList.toggle('border-transparent', !isSelected);
            tab.classList.toggle('text-gray-500', !isSelected);
            tab.classList.toggle('hover:text-gray-700', !isSelected);
            tab.classList.toggle('hover:border-gray-300', !isSelected);
            tab.classList.toggle('font-medium', !isSelected);
            tab.setAttribute('aria-current', isSelected ? 'page' : 'false');
        });
        const selectedContent = document.getElementById(`content-${tabId}`);
        if (selectedContent) {
            selectedContent.classList.remove('hidden');
        }
    }

    // Add event listeners to tab buttons and determine initial tab
    if (tabs.length > 0 && tabContents.length > 0) {
        tabs.forEach(tabButton => {
            if (!tabButton.id) { return; }
            tabButton.addEventListener('click', (event) => {
                const tabId = event.currentTarget.id.replace('tab-', '');
                if (tabId) { showTab(tabId); }
            });
        });

        // Determine initial tab based on URL hash or default to 'about'
        const hash = window.location.hash;
        let initialTabId = 'about';
        if (hash && hash.startsWith('#content-')) {
            const hashTabId = hash.substring('#content-'.length);
            if (document.getElementById(`tab-${hashTabId}`) && document.getElementById(`content-${hashTabId}`)) {
                initialTabId = hashTabId;
            }
        }

        // Show the determined initial tab
        if (document.getElementById(`tab-${initialTabId}`) && document.getElementById(`content-${initialTabId}`)) {
            showTab(initialTabId);
        } else if (tabs.length > 0 && tabs[0].id) {
            const firstAvailableTabId = tabs[0].id.replace('tab-', '');
            if (document.getElementById(`content-${firstAvailableTabId}`)){ showTab(firstAvailableTabId); }
        }
    }

    // --- Audio Player Logic ---
    if (audioPlayer) {
        // Updates the UI state of the main player bar
        function updatePlayerUIState(state) {
            if (!playerPlayIcon || !playerPauseIcon) return;
            const isPlaying = state === 'playing';
            playerPlayIcon.classList.toggle('hidden', isPlaying);
            playerPauseIcon.classList.toggle('hidden', !isPlaying);
            if (currentlyPlayingListItemButton) {
                updateListItemButtonState(currentlyPlayingListItemButton, state);
            }
        }

        // Updates the UI state of a chapter list item button
        function updateListItemButtonState(listItemButton, state) {
            if (!listItemButton) return;
            const playIcon = listItemButton.querySelector('.play-icon');
            const pauseIcon = listItemButton.querySelector('.pause-icon');
            const loadingIcon = listItemButton.querySelector('.loading-icon');
            const chapterItemDiv = listItemButton.closest('.chapter-item');

            // Hide all icons initially
            playIcon?.classList.add('hidden');
            pauseIcon?.classList.add('hidden');
            loadingIcon?.classList.add('hidden');

            // Reset general classes
            listItemButton.classList.remove('bg-pink-100', 'text-pink-600', 'hover:bg-pink-200', 'animate-pulse', 'opacity-50');
            listItemButton.classList.add('bg-[#eef2ff]', 'text-[#091e65]', 'hover:bg-[#e0e7ff]');
            chapterItemDiv?.classList.remove('playing', 'bg-indigo-100', 'border-indigo-400', 'ring-2', 'ring-indigo-300', 'ring-offset-1');
            chapterItemDiv?.classList.add('bg-white', 'border-gray-200', 'hover:border-indigo-300', 'hover:bg-indigo-50');

            // Set state-specific classes and show appropriate icon
            switch (state) {
                case 'playing':
                    pauseIcon?.classList.remove('hidden');
                    listItemButton.classList.remove('bg-[#eef2ff]', 'text-[#091e65]', 'hover:bg-[#e0e7ff]');
                    listItemButton.classList.add('bg-pink-100', 'text-pink-600', 'hover:bg-pink-200');
                    chapterItemDiv?.classList.remove('bg-white', 'border-gray-200', 'hover:border-indigo-300', 'hover:bg-indigo-50');
                    chapterItemDiv?.classList.add('playing', 'bg-indigo-100', 'border-indigo-400');
                    break;
                case 'loading':
                    loadingIcon?.classList.remove('hidden');
                    listItemButton.classList.add('animate-pulse', 'opacity-50');
                    break;
                case 'error':
                    playIcon?.classList.remove('hidden');
                    listItemButton.classList.add('opacity-50');
                    break;
                case 'paused':
                case 'ended':
                default:
                    playIcon?.classList.remove('hidden');
                    break;
            }
        }

        // Shows the bottom player bar
        function showPlayerBar() { bottomPlayerBar?.classList.remove('translate-y-full'); }

        // Hides the bottom player bar
        function hidePlayerBar() { bottomPlayerBar?.classList.add('translate-y-full'); }

        // Updates the player info display (title, episode number, cover)
        function updatePlayerInfo(playableChapterIndex) {
            const chapterItem = chapterItems[playableChapterIndex];
            if (!chapterItem) return;
            const title = chapterItem.dataset.chapterTitle || 'Unknown Title';
            const originalChapterOrderMatch = chapterItem.querySelector('.font-mono')?.textContent.match(/^(\d+)\./);
            const originalChapterOrder = originalChapterOrderMatch ? originalChapterOrderMatch[1] : (parseInt(chapterItem.dataset.chapterIndex || '-1', 10) + 1);
            const totalOriginalChapters = allChapterItems.length;

            if (playerEpisodeTitle) { playerEpisodeTitle.textContent = title; playerEpisodeTitle.title = title; }
            if (playerEpisodeNumber) playerEpisodeNumber.textContent = `Episode ${originalChapterOrder} of ${totalOriginalChapters}`;
            if (playerCoverImage) playerCoverImage.src = mainCoverImage?.src || PLACEHOLDER_COVER_SRC;
            if (playerPrevButton) playerPrevButton.disabled = playableChapterIndex <= 0;
            if (playerNextButton) playerNextButton.disabled = playableChapterIndex >= chapterItems.length - 1;
        }

        // Initiates playback of a specific chapter
        window.playChapter = function(buttonElement) {
            if (!audioPlayer) return;
            const chapterItem = buttonElement.closest('.chapter-item');
            if (!chapterItem || chapterItem.classList.contains('opacity-60') || chapterItem.classList.contains('cursor-not-allowed')) {
                return;
            }
            const audioUrl = chapterItem.dataset.audioUrl;
            const chapterTitle = chapterItem.dataset.chapterTitle || 'Episode';
            const playableChapterIndex = Array.from(chapterItems).indexOf(chapterItem);

            if (!audioUrl || audioUrl === 'None' || audioUrl.endsWith('?url=') || audioUrl.includes('?url=None') || playableChapterIndex < 0) {
                 // Display error using Swal
                Swal.fire({ icon: 'error', title: 'Audio Unavailable', text: `Could not load audio data for "${chapterTitle}".`, customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                updateListItemButtonState(buttonElement, 'error');
                return;
            }

            // Pause currently playing item if different
            if (currentlyPlayingListItemButton && currentlyPlayingListItemButton !== buttonElement) {
                updateListItemButtonState(currentlyPlayingListItemButton, 'paused');
            }

            const isCurrentlyPlayingThis = currentlyPlayingListItemButton === buttonElement && !audioPlayer.paused;

            if (isCurrentlyPlayingThis) {
                audioPlayer.pause();
            } else {
                currentChapterIndex = playableChapterIndex;
                currentlyPlayingListItemButton = buttonElement;
                updateListItemButtonState(currentlyPlayingListItemButton, 'loading');
                updatePlayerUIState('loading');
                updatePlayerInfo(currentChapterIndex);
                showPlayerBar();
                audioPlayer.src = audioUrl;
                audioPlayer.load();
                audioPlayer.play().catch(e => {
                    // Display playback error using Swal
                    Swal.fire({ icon: 'error', title: 'Playback Error', text: 'Could not play audio. Please try another episode or check your connection.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                    updatePlayerUIState('error');
                    updateListItemButtonState(currentlyPlayingListItemButton, 'error');
                });
            }
        };

        // Toggles play/pause state of the audio player
        window.togglePlayPause = function() {
            if (!audioPlayer) return;
            if (currentChapterIndex < 0 && chapterItems.length > 0) {
                const firstPlayableChapterButton = chapterItems[0]?.querySelector('.play-button');
                if (firstPlayableChapterButton) playChapter(firstPlayableChapterButton);
                 // Display info using Swal
                else Swal.fire({ toast: true, position: 'bottom-end', icon: 'info', title: 'No playable episodes.', showConfirmButton: false, timer: 2500, timerProgressBar: true, customClass: { popup: 'bg-gray-100 text-gray-800 rounded-lg shadow-lg', title: 'text-sm font-medium', timerProgressBar: `bg-[${THEME_COLOR}]` } });
                return;
            }
            if (audioPlayer.paused || audioPlayer.ended) {
                if (audioPlayer.src && audioPlayer.src !== window.location.href) {
                    audioPlayer.play().catch(e => {
                        // Display playback error using Swal
                        Swal.fire({ icon: 'error', title: 'Playback Error', text: 'Could not resume audio.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4`, icon: 'text-red-500 border-red-300' } });
                        updatePlayerUIState('error');
                    });
                } else if (currentChapterIndex >= 0) {
                    const currentButton = chapterItems[currentChapterIndex]?.querySelector('.play-button');
                    if (currentButton) playChapter(currentButton); else closePlayer();
                }
            } else {
                audioPlayer.pause();
            }
        };

        // Plays the next chapter in the list
        window.playNextChapter = function() {
            if (!audioPlayer || chapterItems.length === 0) return;
            const nextPlayableIndex = currentChapterIndex + 1;
            if (nextPlayableIndex < chapterItems.length) {
                const nextButton = chapterItems[nextPlayableIndex]?.querySelector('.play-button');
                if (nextButton) playChapter(nextButton);
            }
        };

        // Plays the previous chapter in the list
        window.playPreviousChapter = function() {
            if (!audioPlayer || chapterItems.length === 0) return;
            const prevPlayableIndex = currentChapterIndex - 1;
            if (prevPlayableIndex >= 0) {
                const prevButton = chapterItems[prevPlayableIndex]?.querySelector('.play-button');
                if (prevButton) playChapter(prevButton);
            }
        };

        // Closes and resets the audio player
        window.closePlayer = function() {
            if (!audioPlayer) return;
            audioPlayer.pause();
            audioPlayer.src = '';
            hidePlayerBar();
            if (currentlyPlayingListItemButton) updateListItemButtonState(currentlyPlayingListItemButton, 'paused');
            currentlyPlayingListItemButton = null;
            currentChapterIndex = -1;
            if (playerSeekBar) playerSeekBar.value = 0;
            if (playerCurrentTime) playerCurrentTime.textContent = '0:00';
            if (playerDurationDisplay) playerDurationDisplay.textContent = '0:00';
            if (playerEpisodeTitle) playerEpisodeTitle.textContent = 'Select an episode';
            if (playerEpisodeNumber) playerEpisodeNumber.textContent = 'Episode N/A';
            if (playerCoverImage) playerCoverImage.src = PLACEHOLDER_COVER_SRC;
            if (playerPrevButton) playerPrevButton.disabled = true;
            if (playerNextButton) playerNextButton.disabled = chapterItems.length <= 1;
            updatePlayerUIState('paused');
            currentSpeedIndex = 0;
            audioPlayer.playbackRate = PLAYBACK_SPEEDS[currentSpeedIndex];
            if (playerSpeedButton) playerSpeedButton.textContent = `${PLAYBACK_SPEEDS[currentSpeedIndex]}x`;
        };

        // Cycles through available playback speeds
        window.cyclePlaybackSpeed = function() {
            if (!audioPlayer) return;
            currentSpeedIndex = (currentSpeedIndex + 1) % PLAYBACK_SPEEDS.length;
            const newSpeed = PLAYBACK_SPEEDS[currentSpeedIndex];
            audioPlayer.playbackRate = newSpeed;
            if (playerSpeedButton) playerSpeedButton.textContent = `${newSpeed}x`;
        };

        // Add event listeners for audio player events
        audioPlayer.addEventListener('play', () => updatePlayerUIState('playing'));
        audioPlayer.addEventListener('pause', () => updatePlayerUIState('paused'));
        audioPlayer.addEventListener('ended', () => { updatePlayerUIState('ended'); playNextChapter(); });
        audioPlayer.addEventListener('loadedmetadata', () => {
            if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
                if (playerDurationDisplay) playerDurationDisplay.textContent = formatTime(audioPlayer.duration);
                if (playerSeekBar) playerSeekBar.max = audioPlayer.duration;
            } else {
                if (playerDurationDisplay) playerDurationDisplay.textContent = '--:--';
                if (playerSeekBar) playerSeekBar.max = 0;
            }
            if (playerCurrentTime) playerCurrentTime.textContent = '0:00';
            if (playerSeekBar) playerSeekBar.value = 0;
        });
        audioPlayer.addEventListener('timeupdate', () => {
            if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration)) {
                if (playerCurrentTime) playerCurrentTime.textContent = formatTime(audioPlayer.currentTime);
                if (playerSeekBar && !playerSeekBar.matches(':active')) {
                    playerSeekBar.value = audioPlayer.currentTime;
                }
            }
        });

        // Add event listeners to player control buttons
        playerPlayPauseButton?.addEventListener('click', window.togglePlayPause);
        playerNextButton?.addEventListener('click', window.playNextChapter);
        playerPrevButton?.addEventListener('click', window.playPreviousChapter);
        playerSpeedButton?.addEventListener('click', window.cyclePlaybackSpeed);
        playerCloseButton?.addEventListener('click', window.closePlayer);
        playerSeekBar?.addEventListener('input', () => {
             if (!isNaN(audioPlayer.duration) && isFinite(audioPlayer.duration) && audioPlayer.readyState >= 1) {
                 audioPlayer.currentTime = playerSeekBar.value;
             }
        });

        // Initial state setup for the player bar
        hidePlayerBar();
        if (playerPrevButton) playerPrevButton.disabled = true;
        if (playerNextButton) playerNextButton.disabled = chapterItems.length <= 1;
        if (playerSpeedButton) playerSpeedButton.textContent = `${PLAYBACK_SPEEDS[currentSpeedIndex]}x`;
    }

    // --- Review Form, Rating, and Display Logic ---

    // Scrolls to the reviews section and switches to the reviews tab
    window.scrollToReviews = function() {
        const reviewsTabButton = document.getElementById('tab-reviews');
        const reviewsContent = document.getElementById('content-reviews');
        if (reviewsTabButton && reviewsContent && typeof showTab === 'function') {
            showTab('reviews');
            reviewsContent.scrollIntoView({ behavior: 'smooth', block: 'start' });
            if (reviewForm && !reviewForm.classList.contains('hidden') && reviewRatingInput) {
                const firstStar = reviewRatingInput.querySelector('i[data-rating-value="1"]');
                firstStar?.focus();
            }
        }
    };

    // Shows the review form and hides the "already reviewed" prompt
    window.showReviewForm = function() {
        if (reviewForm) {
            reviewForm.classList.remove('hidden');
            reviewForm.scrollIntoView({ behavior: 'smooth', block: 'center' });
            const firstStar = reviewRatingInput?.querySelector('i[data-rating-value="1"]');
            firstStar?.focus();
        }
        editReviewPrompt?.classList.add('hidden');
    };

    // Handles the click event for editing a review, populating the form
    window.handleEditClick = function(buttonElement) {
        if (!reviewForm || !ratingValueInput || !commentInput || !submitReviewBtn) {
            return;
        }

        let ratingToLoad = 0;
        let commentToLoad = '';

        if (buttonElement && buttonElement.id === 'edit-my-review-button') {
            if (userReviewData && userReviewData.has_reviewed) {
                ratingToLoad = parseInt(userReviewData.rating || '0', 10);
                commentToLoad = userReviewData.comment || '';
            }
        } else if (buttonElement && buttonElement.classList.contains('edit-user-review-button')) {
            ratingToLoad = parseInt(buttonElement.dataset.rating || '0', 10);
            commentToLoad = buttonElement.dataset.comment || '';
        } else {
            return;
        }

        if (typeof updateStarsUI === 'function') {
            updateStarsUI(ratingToLoad);
        } else {
            ratingValueInput.value = ratingToLoad;
        }
        commentInput.value = commentToLoad;
        submitReviewBtn.innerHTML = UPDATE_SUBMIT_BUTTON_HTML;

        if (typeof showReviewForm === 'function') {
            showReviewForm();
        }
    };

    // Add event listener to the "Rate" button
    if (rateButton) rateButton.addEventListener('click', window.scrollToReviews);

    // Add event listener to the "Edit Your Review" button in the prompt
    if (editMyReviewButtonFromPrompt) {
        editMyReviewButtonFromPrompt.addEventListener('click', function() {
            window.handleEditClick(this);
        });
    }

    // Attaches click listeners to all edit review buttons in the list
    function attachEditButtonListeners() {
        document.querySelectorAll('#reviews-list .edit-user-review-button').forEach(button => {
            button.removeEventListener('click', handleEditClickWrapper); // Prevent duplicate listeners
            button.addEventListener('click', handleEditClickWrapper);
        });
    }

    // Wrapper function for edit click event
    function handleEditClickWrapper(event) {
        window.handleEditClick(event.currentTarget);
    }

    // Attach listeners initially
    attachEditButtonListeners();


    if (reviewForm && reviewRatingInput && ratingValueInput && commentInput && submitReviewBtn && reviewsListDiv && formMessageDiv && reviewCountSpan && reviewCountTabSpan && editReviewPrompt) {
        const stars = reviewRatingInput.querySelectorAll('i[data-rating-value]');

        // Updates the visual appearance of the star rating based on a given rating value
        function updateStarsUI(rating) {
            if (!stars || !ratingValueInput) return;
            stars.forEach(star => {
                const starValue = parseInt(star.dataset.ratingValue);
                const isSelected = starValue <= rating;
                star.classList.toggle('far', !isSelected);
                star.classList.toggle('fas', isSelected);
                star.classList.toggle('text-yellow-400', isSelected);
                star.classList.toggle('text-gray-300', !isSelected);
                star.classList.remove('hover:text-yellow-400');
                if (!isSelected) star.classList.add('hover:text-yellow-400');
            });
            ratingValueInput.value = rating;
            if (ratingError) ratingError.textContent = '';
        }
        window.updateStarsUI = updateStarsUI; // Make global

        // Add event listeners for star rating interaction (hover and click)
        reviewRatingInput.addEventListener('mouseover', (event) => {
            if (event.target.tagName === 'I' && event.target.dataset.ratingValue) {
                const hoverRating = parseInt(event.target.dataset.ratingValue);
                stars.forEach(star => {
                    const starValue = parseInt(star.dataset.ratingValue);
                    const shouldBeLit = starValue <= hoverRating;
                    star.classList.toggle('far', !shouldBeLit);
                    star.classList.toggle('fas', shouldBeLit);
                    star.classList.toggle('text-yellow-400', shouldBeLit);
                    star.classList.toggle('text-gray-300', !shouldBeLit);
                });
            }
        });
        reviewRatingInput.addEventListener('mouseout', () => {
            const currentRating = parseInt(ratingValueInput.value || '0');
            updateStarsUI(currentRating);
        });
        reviewRatingInput.addEventListener('click', (event) => {
            if (event.target.tagName === 'I' && event.target.dataset.ratingValue) {
                const clickedRating = parseInt(event.target.dataset.ratingValue);
                updateStarsUI(clickedRating);
            }
        });

        // Creates the HTML string for a single review item
        function createReviewHtml(reviewData) {
            let starsHtml = '';
            const rating = reviewData.rating || 0;
            for (let i = 1; i <= 5; i++) { starsHtml += `<i class="${i <= rating ? 'fas text-yellow-400' : 'far text-gray-300'} fa-star"></i>`; }

            const profilePicHtml = reviewData.user_profile_pic ?
                `<img class="h-10 w-10 rounded-full object-cover shadow-sm" src="${reviewData.user_profile_pic}" alt="${escapeHTML(reviewData.user_name)}">` :
                `<span class="h-10 w-10 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center text-gray-500 shadow-sm"><i class="fas fa-user text-lg"></i></span>`;

            const escapedCommentForDisplay = escapeHTML(reviewData.comment || '');
            const commentHtml = escapedCommentForDisplay ? `<div class="mt-2 text-sm text-gray-600 prose prose-sm max-w-none leading-relaxed"><p>${escapedCommentForDisplay}</p></div>` : '';

            const timeAgo = reviewData.timesince || 'Just now';

            const commentForDataAttr = escapeForDataAttr(reviewData.comment || '');

            const isCurrentUserReview = currentUserId && reviewData.user_id && reviewData.user_id.toString() === currentUserId.toString();

            const editButtonHtml = isCurrentUserReview ?
                `<div class="mt-2 text-xs">
                    <button data-review-id="${reviewData.review_id}"
                            data-rating="${reviewData.rating}"
                            data-comment="${commentForDataAttr}"
                            class="edit-user-review-button text-indigo-600 hover:text-indigo-800 hover:underline font-medium focus:outline-none focus:ring-1 focus:ring-indigo-300 rounded px-1 py-0.5">
                        <i class="fas fa-pencil-alt mr-1 text-xs"></i>Edit
                    </button>
                </div>` : '';

            return `<div class="review-item flex space-x-4 py-4 border-b border-gray-100 last:border-b-0" id="review-${reviewData.review_id}">${profilePicHtml}<div class="flex-grow"><div class="flex items-center justify-between mb-1"><h5 class="text-sm font-semibold text-gray-800">${escapeHTML(reviewData.user_name)}</h5><time datetime="${reviewData.created_at || new Date().toISOString()}" class="flex-shrink-0 ml-4 text-xs text-gray-400">${timeAgo}</time></div><div class="mb-1 flex items-center star-rating-display text-xs">${starsHtml}</div>${commentHtml}${editButtonHtml}</div></div>`;
        }

        // Updates the average rating display and count across the page
        function updateAverageRatingDisplays(newAvgRatingStr, reviewCount) {
            const newAvg = parseFloat(newAvgRatingStr);
            let starsHtml = '';
            let ratingText = '';
            let reviewCountTextBase = `(${reviewCount} rating${reviewCount !== 1 ? 's' : ''})`;

            if (!isNaN(newAvg) && newAvg > 0) {
                let tempRating = newAvg;
                for (let i = 0; i < 5; i++) {
                    if (tempRating >= 1) {
                        starsHtml += '<i class="fas fa-star text-yellow-400"></i>';
                        tempRating -= 1;
                    } else if (tempRating >= 0.5) {
                        starsHtml += '<i class="fas fa-star-half-alt text-yellow-400"></i>';
                        tempRating = 0;
                    } else {
                        starsHtml += '<i class="far fa-star text-gray-300"></i>';
                    }
                }
                ratingText = `<span class="font-semibold text-gray-700 ml-1.5">${newAvg.toFixed(1)}</span>`;
            } else {
                for (let i = 0; i < 5; i++) starsHtml += '<i class="far fa-star text-gray-300"></i>';
                ratingText = `<span class="text-gray-400 italic ml-1.5">No ratings yet</span>`;
                reviewCountTextBase = '';
            }

            avgRatingDisplays.forEach(el => {
                const isReviewTabAvg = el.closest('#content-reviews');
                const avgSuffix = isReviewTabAvg ? ' avg' : '';
                const reviewCountText = reviewCountTextBase ? `<span class="ml-1">${reviewCountTextBase}${avgSuffix}</span>` : '';
                const textSizeClass = el.closest('#content-reviews') ? 'text-sm' : 'text-base';
                el.className = `flex items-center star-rating-display ${textSizeClass}`;
                el.innerHTML = starsHtml + ratingText + reviewCountText;
            });
        }

        // Handles the submission of the review form
        reviewForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!CSRF_TOKEN || !ADD_REVIEW_URL_BASE || !AUDIOBOOK_SLUG) {
                if (formMessageDiv) { formMessageDiv.textContent = 'Configuration error.'; formMessageDiv.className = 'text-sm flex-grow text-red-600'; }
                return;
            }
            if (formMessageDiv) { formMessageDiv.textContent = ''; formMessageDiv.className = 'text-sm flex-grow'; }
            if (ratingError) ratingError.textContent = '';
            submitReviewBtn.disabled = true;
            submitReviewBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Submitting...';

            const rating = parseInt(ratingValueInput.value || '0');
            const comment = commentInput.value.trim();
            const url = ADD_REVIEW_URL_BASE.replace('PLACEHOLDER_SLUG', AUDIOBOOK_SLUG);

            if (rating === 0) {
                if (ratingError) ratingError.textContent = 'Please select a rating (1-5 stars).';
                submitReviewBtn.disabled = false;
                const isUpdating = submitReviewBtn.innerHTML.includes("Update");
                submitReviewBtn.innerHTML = isUpdating ? UPDATE_SUBMIT_BUTTON_HTML : DEFAULT_SUBMIT_BUTTON_HTML;
                return;
            }

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': CSRF_TOKEN,
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({ rating: rating, comment: comment })
                });
                const result = await response.json();

                if (response.ok && result.status === 'success' && result.review_data) {
                    if (formMessageDiv) { formMessageDiv.textContent = result.message || 'Review submitted successfully!'; formMessageDiv.classList.add('text-green-600'); }
                    reviewForm.classList.add('hidden');
                    reviewForm.reset();
                    updateStarsUI(0);
                    editReviewPrompt?.classList.remove('hidden');

                    userReviewData.has_reviewed = true;
                    userReviewData.rating = result.review_data.rating;
                    userReviewData.comment = result.review_data.comment;
                    if (result.review_data.user_id) currentUserId = result.review_data.user_id.toString();

                    const newReviewHtml = createReviewHtml(result.review_data);
                    const existingReviewElement = document.getElementById(`review-${result.review_data.review_id}`);
                    if (existingReviewElement) {
                        existingReviewElement.outerHTML = newReviewHtml;
                    } else {
                        reviewsListDiv.insertAdjacentHTML('afterbegin', newReviewHtml);
                        noReviewsMessage?.classList.add('hidden');
                    }

                    attachEditButtonListeners();

                    const currentReviewCount = document.querySelectorAll('#reviews-list .review-item').length;
                    if (reviewCountSpan) reviewCountSpan.textContent = currentReviewCount;
                    if (reviewCountTabSpan) reviewCountTabSpan.textContent = currentReviewCount;
                    updateAverageRatingDisplays(result.new_average_rating, currentReviewCount);

                    submitReviewBtn.innerHTML = UPDATE_SUBMIT_BUTTON_HTML;

                } else {
                    if (formMessageDiv) { formMessageDiv.textContent = result.message || `Error: ${response.status} ${response.statusText}`; formMessageDiv.classList.add('text-red-600'); }
                    if (result.errors && result.errors.rating && ratingError) ratingError.textContent = result.errors.rating.join(' ');
                }
            } catch (error) {
                if (formMessageDiv) { formMessageDiv.textContent = 'Network error or invalid server response. Please try again.'; formMessageDiv.classList.add('text-red-600'); }
            } finally {
                submitReviewBtn.disabled = false;
                if (!reviewForm.classList.contains('hidden')) {
                    const isUpdating = (userReviewData.has_reviewed && userReviewData.rating > 0);
                    submitReviewBtn.innerHTML = isUpdating ? UPDATE_SUBMIT_BUTTON_HTML : DEFAULT_SUBMIT_BUTTON_HTML;
                } else {
                    if (userReviewData.has_reviewed) {
                        submitReviewBtn.innerHTML = UPDATE_SUBMIT_BUTTON_HTML;
                    }
                }
                setTimeout(() => {
                    if (formMessageDiv && (formMessageDiv.classList.contains('text-green-600') || formMessageDiv.classList.contains('text-red-600'))) {
                        formMessageDiv.textContent = '';
                        formMessageDiv.className = 'text-sm flex-grow';
                    }
                }, 7000);
            }
        });

        // Initial setup of review form visibility and button text
        if (userReviewData && userReviewData.has_reviewed) {
            reviewForm.classList.add('hidden');
            editReviewPrompt?.classList.remove('hidden');
            if (submitReviewBtn) submitReviewBtn.innerHTML = UPDATE_SUBMIT_BUTTON_HTML;
        } else {
            editReviewPrompt?.classList.add('hidden');
            reviewForm.classList.remove('hidden');
            if (submitReviewBtn) submitReviewBtn.innerHTML = DEFAULT_SUBMIT_BUTTON_HTML;
        }
    }

    // --- Stripe Purchase Logic ---
    // Initializes Stripe and handles the purchase button click
    if (purchaseButton && STRIPE_PUBLISHABLE_KEY && CSRF_TOKEN && CREATE_CHECKOUT_SESSION_URL && AUDIOBOOK_SLUG) {
        try {
            stripe = Stripe(STRIPE_PUBLISHABLE_KEY);
            purchaseButton.addEventListener('click', async (event) => {
                event.target.disabled = true;
                event.target.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Processing...';
                try {
                    const response = await fetch(CREATE_CHECKOUT_SESSION_URL, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': CSRF_TOKEN,
                            'X-Requested-With': 'XMLHttpRequest'
                        },
                        body: JSON.stringify({ 'audiobook_slug': AUDIOBOOK_SLUG })
                    });
                    const session = await response.json();
                    if (session.error || !session.id) { throw new Error(session.error || 'Failed to create checkout session.'); }
                    const result = await stripe.redirectToCheckout({ sessionId: session.id });
                    if (result.error) { throw new Error(result.error.message); }
                } catch (error) {
                     // Display Stripe error using Swal
                    Swal.fire({ icon: 'error', title: 'Payment Error', text: error.message || 'Could not initiate payment. Please try again.', customClass: { popup: 'rounded-xl', confirmButton: `bg-[${THEME_COLOR}] hover:bg-opacity-80 rounded-lg text-white py-2 px-4` }});
                    event.target.disabled = false;
                    event.target.innerHTML = `<i class="fas fa-shopping-cart mr-2"></i> Purchase Now (PKR ${AUDIOBOOK_PRICE_FORMATTED})`;
                }
            });
        } catch (e) {
            if (purchaseButton) { purchaseButton.disabled = true; purchaseButton.innerHTML = '<i class="fas fa-exclamation-circle mr-2"></i> Payment Init Failed'; }
        }
    } else if (purchaseButton) {
        purchaseButton.disabled = true;
        purchaseButton.innerHTML = '<i class="fas fa-exclamation-circle mr-2"></i> Payment Unavailable';
    }

    // --- Share Button Logic ---
    // Handles the click event for the share button
    if (shareButton) {
        shareButton.addEventListener('click', () => {
            const urlToShare = window.location.href;
            const audiobookTitleElement = document.getElementById('audiobook-title-heading');
            const audiobookTitle = audiobookTitleElement ? audiobookTitleElement.textContent : 'this audiobook';
            const shareData = {
                title: `Check out ${audiobookTitle} on AudioX!`,
                text: `Listen to ${audiobookTitle} and more on AudioX.`,
                url: urlToShare,
            };
            if (navigator.share) {
                navigator.share(shareData).catch(() => {}); // Catch and ignore potential errors
            } else {
                navigator.clipboard.writeText(urlToShare).then(() => {
                     // Display success message using Swal
                    Swal.fire({
                        toast: true,
                        position: 'top-end',
                        icon: 'success',
                        title: 'Link copied to clipboard!',
                        showConfirmButton: false,
                        timer: 2000,
                        timerProgressBar: true,
                        customClass: { popup: 'bg-gray-100 text-gray-800 rounded-lg shadow-lg', title: 'text-sm font-medium', timerProgressBar: `bg-[${THEME_COLOR}]` }
                    });
                }).catch(() => {
                     // Display error message using Swal
                    Swal.fire({ icon: 'error', title: 'Oops!', text: 'Could not copy link.', customClass: { popup: 'rounded-xl' } });
                });
            }
        });
    }

    // --- View Logging ---
    // Logs a view for the current audiobook
    function logViewForAudiobook() {
        if (!audioPlayer) { return; }

        const audiobookDbId = audioPlayer.dataset.audiobookDbId;

        if (!audiobookDbId || audiobookDbId.trim() === "") { return; }
        if (!IS_AUTHENTICATED) { return; }
        if (!LOG_AUDIOBOOK_VIEW_URL) { return; }
        if (!CSRF_TOKEN) { return; }

        fetch(LOG_AUDIOBOOK_VIEW_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN, 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ audiobook_id: audiobookDbId })
            })
            .then(response => {
                if (!response.ok) {
                    return Promise.reject(new Error(`HTTP error ${response.status}`));
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    if (audiobookTotalViewsSpan && data.total_views !== undefined) {
                        audiobookTotalViewsSpan.textContent = `${data.total_views.toLocaleString()} Views`;
                    }
                }
            })
            .catch(() => {
                // Ignore errors during view logging as it's not critical user functionality
            });
    }

    // Log view when the page is loaded, if on the details page
    if (document.getElementById('tab-about')) {
        logViewForAudiobook();
    }
}); // End DOMContentLoaded
