// AudioXApp/static/js/downloadManager.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Configuration & Constants ---
    const DB_NAME = 'AudioXOfflineDB';
    const DB_VERSION = 1;
    const AUDIOBOOKS_STORE_NAME = 'downloadedAudiobooksInfo'; // Stores metadata for overall audiobook download status
    const CHAPTERS_STORE_NAME = 'downloadedChaptersData';   // Stores metadata for individual downloaded chapters
    const AUDIO_CACHE_NAME = 'audiobook-audio-cache-v1';    // Cache storage for actual audio blobs

    // --- DOM Elements ---
    const downloadFullBtn = document.getElementById('download-full-audiobook-btn');
    const selectChaptersBtn = document.getElementById('select-chapters-download-btn'); // Functionality for this button is a TODO
    const downloadStatusMessagesEl = document.getElementById('download-status-messages');
    const overallProgressBarContainer = document.getElementById('overall-download-progress-bar-container');
    const overallProgressBarEl = document.getElementById('overall-download-progress-bar');
    const chapterListContainer = document.getElementById('content-episodes');

    // --- Page Context (from <script type="application/json">) ---
    let pageContextData = {};
    try {
        const contextScript = document.getElementById('page-context-data-detail');
        if (contextScript) {
            pageContextData = JSON.parse(contextScript.textContent);
        } else {
            console.error("Page context data script not found!");
        }
    } catch (e) {
        console.error("Error parsing page context data:", e);
    }

    const currentAudiobookId = pageContextData.audiobookId;
    const currentAudiobookTitle = pageContextData.audiobookTitle;
    const csrfToken = pageContextData.csrfToken;
    const apiEndpoints = pageContextData.apiEndpoints || {};


    // --- IndexedDB Helper Functions ---
    let dbPromise = null;
    function openDB() {
        if (dbPromise) return dbPromise;
        dbPromise = new Promise((resolve, reject) => {
            if (!window.indexedDB) {
                reject("IndexedDB not supported.");
                return;
            }
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onerror = (event) => reject("IndexedDB error: " + event.target.error?.message);
            request.onsuccess = (event) => resolve(event.target.result);
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(AUDIOBOOKS_STORE_NAME)) {
                    db.createObjectStore(AUDIOBOOKS_STORE_NAME, { keyPath: 'audiobookId' });
                }
                if (!db.objectStoreNames.contains(CHAPTERS_STORE_NAME)) {
                    const chapterStore = db.createObjectStore(CHAPTERS_STORE_NAME, { keyPath: 'uniqueId' }); // audiobookId_chapterId
                    chapterStore.createIndex('byAudiobookId', 'audiobookId', { unique: false });
                }
            };
        });
        return dbPromise;
    }

    async function dbGet(storeName, key) {
        const db = await openDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(storeName, 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = (event) => reject("DB Get Error: " + event.target.error?.message);
        });
    }

    async function dbGetAllByIndex(storeName, indexName, key) {
        const db = await openDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(storeName, 'readonly');
            const store = transaction.objectStore(storeName);
            const index = store.index(indexName);
            const request = index.getAll(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = (event) => reject("DB GetAll By Index Error: " + event.target.error?.message);
        });
    }

    async function dbPut(storeName, item) {
        const db = await openDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.put(item);
            request.onsuccess = () => resolve(request.result);
            request.onerror = (event) => reject("DB Put Error: " + event.target.error?.message);
        });
    }
    async function dbDelete(storeName, key) {
        const db = await openDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(storeName, 'readwrite');
            const store = transaction.objectStore(storeName);
            const request = store.delete(key);
            request.onsuccess = () => resolve(true);
            request.onerror = (event) => reject("DB Delete Error: " + event.target.error?.message);
        });
    }


    // --- Cache API Helper Functions ---
    async function cacheAudioFile(cacheKey, audioBlob) {
        if (!window.caches) throw new Error("Cache API not supported.");
        const cache = await caches.open(AUDIO_CACHE_NAME);
        const responseToCache = new Response(audioBlob, {
            status: 200, statusText: 'OK',
            headers: { 'Content-Type': audioBlob.type || 'audio/mpeg', 'Content-Length': audioBlob.size.toString() }
        });
        await cache.put(cacheKey, responseToCache);
    }

    async function getCachedAudioBlobUrl(cacheKey) { // For playing directly
        if (!window.caches) return null;
        const cache = await caches.open(AUDIO_CACHE_NAME);
        const cachedResponse = await cache.match(cacheKey);
        if (cachedResponse) {
            const blob = await cachedResponse.blob();
            return URL.createObjectURL(blob);
        }
        return null;
    }

    async function deleteCachedAudioFile(cacheKey) {
        if (!window.caches) return false;
        const cache = await caches.open(AUDIO_CACHE_NAME);
        return await cache.delete(cacheKey);
    }

    // --- UI Update Functions ---
    function updateOverallStatus(message, isError = false, isLoading = false) {
        if (downloadStatusMessagesEl) {
            downloadStatusMessagesEl.textContent = message;
            downloadStatusMessagesEl.className = `download-status text-center md:text-left mt-2 text-sm ${
                isError ? 'text-red-600' : (isLoading ? 'text-blue-600' : 'text-green-600')
            }`;
        }
    }

    function updateOverallProgress(percentage) {
        if (overallProgressBarEl && overallProgressBarContainer) {
            overallProgressBarEl.style.width = `${percentage}%`;
            overallProgressBarContainer.classList.toggle('hidden', percentage === 0 || percentage >= 100);
        }
    }

    function updateChapterDownloadUI(chapterId, statusType, message = '') { // statusType: 'pending', 'downloading', 'downloaded', 'error'
        const chapterItem = document.querySelector(`.chapter-item[data-chapter-id="${chapterId}"]`);
        if (!chapterItem) return;

        const downloadBtn = chapterItem.querySelector('.chapter-download-btn');
        const icon = chapterItem.querySelector('.chapter-download-icon'); // This is the <i> tag
        const statusSpan = chapterItem.querySelector('.chapter-download-status');

        if (icon) {
            icon.className = 'fas chapter-download-icon'; // Reset classes
        }
        if (downloadBtn) downloadBtn.disabled = false;
        if (statusSpan) statusSpan.textContent = message;

        switch (statusType) {
            case 'pending':
                if (icon) icon.classList.add('fa-download', 'text-gray-500', 'hover:text-[#091e65]');
                break;
            case 'downloading':
                if (icon) icon.classList.add('fa-spinner', 'animate-spin', 'text-blue-500');
                if (downloadBtn) downloadBtn.disabled = true;
                if (statusSpan) statusSpan.textContent = 'Downloading...';
                break;
            case 'downloaded':
                if (icon) icon.classList.add('fa-check-circle', 'text-green-500');
                if (downloadBtn) downloadBtn.disabled = true; // Or change to a "delete" or "play offline" icon
                if (statusSpan) statusSpan.textContent = 'Downloaded';
                break;
            case 'error':
                if (icon) icon.classList.add('fa-times-circle', 'text-red-500');
                if (statusSpan && !message) statusSpan.textContent = 'Error';
                break;
        }
    }

    // --- API Interaction ---
    async function apiRequest(url, options = {}) {
        const defaultHeaders = {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
        };
        // Add Authorization header if using token auth for client apps
        // const authToken = localStorage.getItem('authToken'); // Example
        // if (authToken) {
        //     defaultHeaders['Authorization'] = `Token ${authToken}`;
        // }

        options.headers = { ...defaultHeaders, ...options.headers };
        const response = await fetch(url, options);

        if (!response.ok) {
            let errorData;
            try {
                errorData = await response.json();
            } catch (e) {
                errorData = { detail: `HTTP error ${response.status} and failed to parse error JSON.` };
            }
            console.error("API Request Error:", response.status, errorData);
            throw new Error(errorData.detail || errorData.message || `API request failed: ${response.status}`);
        }
        // For GET requests that might return empty body on 204, or file streams
        if (response.status === 204) return null;
        if (options.isFileDownload) return response.blob(); // For downloading files

        return response.json();
    }

    // --- Core Download Functions ---
    async function downloadAndStoreChapter(audiobookId, audiobookTitle, chapter, chapterDownloadUrl) {
        const chapterId = chapter.chapter_id.toString();
        const chapterUniqueId = `${audiobookId}_${chapterId}`; // For IndexedDB primary key
        const chapterCacheKey = `${AUDIO_CACHE_NAME}_${chapterUniqueId}`; // For Cache API key

        updateChapterDownloadUI(chapterId, 'downloading');
        try {
            const audioBlob = await apiRequest(chapterDownloadUrl, { isFileDownload: true });
            await cacheAudioFile(chapterCacheKey, audioBlob);

            const chapterMeta = {
                uniqueId: chapterUniqueId,
                audiobookId: audiobookId,
                audiobookTitle: audiobookTitle,
                chapterId: chapterId,
                chapterName: chapter.chapter_name,
                chapterOrder: chapter.chapter_order,
                cachedFileKey: chapterCacheKey,
                downloadedAt: new Date().toISOString(),
                sizeBytes: audioBlob.size,
            };
            await dbPut(CHAPTERS_STORE_NAME, chapterMeta);
            updateChapterDownloadUI(chapterId, 'downloaded');
            return { success: true, chapterId: chapterId };
        } catch (error) {
            console.error(`Error downloading/storing chapter ${chapterId}:`, error);
            updateChapterDownloadUI(chapterId, 'error', 'Failed');
            return { success: false, chapterId: chapterId, error: error.message };
        }
    }

    async function confirmDownloadWithBackend(audiobookIdToConfirm) {
        if (!apiEndpoints.confirmDownloadBase) {
            console.error("Confirm download API endpoint not configured.");
            return;
        }
        try {
            const confirmUrl = `${apiEndpoints.confirmDownloadBase}${audiobookIdToConfirm}/confirm-downloaded/`;
            await apiRequest(confirmUrl, { method: 'POST' });
            console.log(`Download confirmed with backend for audiobook ${audiobookIdToConfirm}`);
        } catch (error) {
            console.error(`Failed to confirm download with backend for ${audiobookIdToConfirm}:`, error);
            // Non-critical for user if files are local, but good to log/retry
        }
    }

    async function handleFullAudiobookDownload() {
        if (!pageContextData.isAuthenticated) {
            Swal.fire('Login Required', 'Please log in to download audiobooks.', 'info');
            return;
        }
        if (!apiEndpoints.downloadInfoBase || !currentAudiobookId) {
            updateOverallStatus("Download configuration error.", true);
            return;
        }

        updateOverallStatus(`Fetching download info for "${currentAudiobookTitle}"...`, false, true);
        updateOverallProgress(5);
        downloadFullBtn.disabled = true;
        if(selectChaptersBtn) selectChaptersBtn.disabled = true;


        try {
            const downloadInfoUrl = `${apiEndpoints.downloadInfoBase}${currentAudiobookId}/download-info/`;
            const data = await apiRequest(downloadInfoUrl); // This also creates/updates UserDownloadedAudiobook on backend

            if (!data.chapters || data.chapters.length === 0) {
                updateOverallStatus('No chapters found for this audiobook.', true);
                updateOverallProgress(0);
                return;
            }

            updateOverallStatus(`Starting download for ${data.chapters.length} chapters...`, false, true);
            let downloadedCount = 0;
            const totalChapters = data.chapters.length;
            let hasErrors = false;

            await dbPut(AUDIOBOOKS_STORE_NAME, {
                audiobookId: currentAudiobookId,
                title: currentAudiobookTitle,
                totalChapters: totalChapters,
                status: 'downloading',
                downloadInitiatedAt: new Date().toISOString()
            });

            for (const chapter of data.chapters) {
                const result = await downloadAndStoreChapter(currentAudiobookId, currentAudiobookTitle, chapter, chapter.download_url);
                if (result.success) {
                    downloadedCount++;
                } else {
                    hasErrors = true;
                }
                updateOverallProgress(Math.round((downloadedCount / totalChapters) * 90) + 5);
            }

            if (downloadedCount === totalChapters) {
                await confirmDownloadWithBackend(currentAudiobookId);
                updateOverallStatus(`"${currentAudiobookTitle}" downloaded successfully!`, false);
                await dbPut(AUDIOBOOKS_STORE_NAME, { audiobookId: currentAudiobookId, title: currentAudiobookTitle, status: 'completed', totalChapters: totalChapters, downloadedAt: new Date().toISOString() });
            } else if (downloadedCount > 0) {
                await confirmDownloadWithBackend(currentAudiobookId); // Confirm even if partial
                updateOverallStatus(`Partially downloaded "${currentAudiobookTitle}" (${downloadedCount}/${totalChapters}).`, true);
                await dbPut(AUDIOBOOKS_STORE_NAME, { audiobookId: currentAudiobookId, title: currentAudiobookTitle, status: 'partial', downloadedChapters: downloadedCount, totalChapters: totalChapters });
            } else {
                updateOverallStatus(`Failed to download any chapters for "${currentAudiobookTitle}".`, true);
                await dbPut(AUDIOBOOKS_STORE_NAME, { audiobookId: currentAudiobookId, title: currentAudiobookTitle, status: 'failed', totalChapters: totalChapters });
            }
            updateOverallProgress(100); // Clear progress bar or show final state
            await checkAndInitializeChapterDownloadStates(currentAudiobookId); // Refresh all chapter icons

        } catch (error) {
            console.error("Error in full audiobook download:", error);
            updateOverallStatus(`Download error: ${error.message}`, true);
            updateOverallProgress(0);
        } finally {
            downloadFullBtn.disabled = false;
            if(selectChaptersBtn) selectChaptersBtn.disabled = false;
        }
    }

    async function handleSingleChapterDownload(chapterIdToDownload) {
        if (!pageContextData.isAuthenticated) {
            Swal.fire('Login Required', 'Please log in to download audiobooks.', 'info');
            return;
        }
         if (!apiEndpoints.downloadInfoBase || !currentAudiobookId || !chapterIdToDownload) {
            updateChapterDownloadUI(chapterIdToDownload, 'error', "Config error");
            return;
        }

        updateChapterDownloadUI(chapterIdToDownload, 'downloading');

        try {
            // Get full download info to ensure UserDownloadedAudiobook record is created/updated on backend
            const downloadInfoUrl = `${apiEndpoints.downloadInfoBase}${currentAudiobookId}/download-info/`;
            const data = await apiRequest(downloadInfoUrl);

            const chapterToDownload = data.chapters.find(ch => ch.chapter_id.toString() === chapterIdToDownload.toString());

            if (!chapterToDownload || !chapterToDownload.download_url) {
                updateChapterDownloadUI(chapterIdToDownload, 'error', 'Info missing');
                return;
            }

            const result = await downloadAndStoreChapter(currentAudiobookId, currentAudiobookTitle, chapterToDownload, chapterToDownload.download_url);

            if (result.success) {
                // Check if all chapters are now downloaded to update overall status
                const allChaptersInBook = data.chapters.length;
                const downloadedChaptersForBook = await dbGetAllByIndex(CHAPTERS_STORE_NAME, 'byAudiobookId', currentAudiobookId);

                if (downloadedChaptersForBook.length === allChaptersInBook) {
                    await confirmDownloadWithBackend(currentAudiobookId);
                    updateOverallStatus(`"${currentAudiobookTitle}" fully downloaded.`, false);
                     await dbPut(AUDIOBOOKS_STORE_NAME, { audiobookId: currentAudiobookId, title: currentAudiobookTitle, status: 'completed', totalChapters: allChaptersInBook, downloadedAt: new Date().toISOString() });
                } else {
                    updateOverallStatus(`Chapter "${chapterToDownload.chapter_name}" downloaded. (${downloadedChaptersForBook.length}/${allChaptersInBook})`, false, true);
                    await dbPut(AUDIOBOOKS_STORE_NAME, { audiobookId: currentAudiobookId, title: currentAudiobookTitle, status: 'partial', downloadedChapters: downloadedChaptersForBook.length, totalChapters: allChaptersInBook });
                }
            }
            // Error state is handled by downloadAndStoreChapter

        } catch (error) {
            console.error(`Error downloading single chapter ${chapterIdToDownload}:`, error);
            updateChapterDownloadUI(chapterIdToDownload, 'error', 'Failed');
        }
    }


    // --- Initialization & Event Listeners ---
    async function checkAndInitializeChapterDownloadStates(audiobookId) {
        if (!window.indexedDB || !window.caches || !audiobookId) return;

        const chapterElements = document.querySelectorAll(`.chapter-item[data-chapter-id]`);
        if (chapterElements.length === 0) return;

        try {
            const downloadedChapters = await dbGetAllByIndex(CHAPTERS_STORE_NAME, 'byAudiobookId', audiobookId);
            const downloadedChapterIds = new Set(downloadedChapters.map(ch => ch.chapterId.toString()));

            chapterElements.forEach(el => {
                const chapterId = el.dataset.chapterId;
                if (chapterId) { // Ensure chapterId is present
                    if (downloadedChapterIds.has(chapterId)) {
                        updateChapterDownloadUI(chapterId, 'downloaded');
                    } else {
                        updateChapterDownloadUI(chapterId, 'pending');
                    }
                }
            });

            const audiobookInfo = await dbGet(AUDIOBOOKS_STORE_NAME, audiobookId);
            if (audiobookInfo) {
                if (audiobookInfo.status === 'completed') {
                    updateOverallStatus(`"${audiobookInfo.title}" is downloaded.`, false);
                    if(downloadFullBtn) downloadFullBtn.disabled = true;
                } else if (audiobookInfo.status === 'partial') {
                    updateOverallStatus(`"${audiobookInfo.title}" is partially downloaded. (${audiobookInfo.downloadedChapters}/${audiobookInfo.totalChapters})`, false, true);
                }
            }


        } catch (error) {
            console.error("Error initializing chapter download states from DB:", error);
        }
    }


    function init() {
        if (!window.indexedDB || !window.caches) {
            console.warn("Offline storage (IndexedDB or Cache API) not supported. Download feature limited/disabled.");
            if (downloadStatusMessagesEl) downloadStatusMessagesEl.textContent = "Offline downloads not supported by your browser.";
            if (downloadFullBtn) downloadFullBtn.disabled = true;
            if (selectChaptersBtn) selectChaptersBtn.disabled = true;
            // Disable all individual chapter download buttons too
            document.querySelectorAll('.chapter-download-btn').forEach(btn => btn.disabled = true);
            return;
        }

        if (!currentAudiobookId) {
            console.warn("Audiobook ID not found in page context. Download manager not fully initialized.");
            return;
        }

        if (downloadFullBtn) {
            downloadFullBtn.addEventListener('click', () => {
                Swal.fire({
                    title: `Download "${currentAudiobookTitle}"?`,
                    text: "This will download all chapters for offline listening.",
                    icon: 'question',
                    showCancelButton: true,
                    confirmButtonText: 'Yes, Download All',
                    cancelButtonText: 'Cancel',
                    confirmButtonColor: '#091e65',
                }).then((result) => {
                    if (result.isConfirmed) {
                        handleFullAudiobookDownload();
                    }
                });
            });
        }

        if (selectChaptersBtn) {
            selectChaptersBtn.addEventListener('click', () => {
                // TODO: Implement UI for selecting specific chapters
                // This might involve showing checkboxes next to each chapter
                // or opening a modal. For now, it's a placeholder.
                Swal.fire('Feature Coming Soon', 'Selecting individual chapters for download is under development.', 'info');
            });
        }

        if (chapterListContainer) {
            chapterListContainer.addEventListener('click', async (event) => {
                const chapterDownloadButton = event.target.closest('.chapter-download-btn');
                if (chapterDownloadButton && currentAudiobookId) {
                    const chapterId = chapterDownloadButton.dataset.chapterId;
                    if (chapterId) {
                        // Check if already downloaded
                        const chapterUniqueId = `${currentAudiobookId}_${chapterId}`;
                        try {
                            const existingChapterMeta = await dbGet(CHAPTERS_STORE_NAME, chapterUniqueId);
                            if (existingChapterMeta && await caches.match(`${AUDIO_CACHE_NAME}_${chapterUniqueId}`)) {
                                Swal.fire('Already Downloaded', 'This chapter is already available offline.', 'info');
                                updateChapterDownloadUI(chapterId, 'downloaded');
                            } else {
                                // If metadata exists but cache doesn't, or vice-versa, might be an inconsistent state.
                                // For simplicity, allow re-download if not fully consistent.
                                handleSingleChapterDownload(chapterId);
                            }
                        } catch (dbError) {
                             console.error("DB check error before single download:", dbError);
                             handleSingleChapterDownload(chapterId); // Proceed if DB check fails
                        }
                    }
                }
            });
        }

        // Initialize download states for chapters on page load
        checkAndInitializeChapterDownloadStates(currentAudiobookId);
    }

    // --- Service Worker Registration (Example - place in your main site JS or base template) ---
    /*
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/js/service-worker.js') // Adjust path as needed
                .then(registration => {
                    console.log('ServiceWorker registration successful with scope: ', registration.scope);
                })
                .catch(error => {
                    console.log('ServiceWorker registration failed: ', error);
                });
        });
    }
    */

    init();
});
