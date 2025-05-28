// AudioXApp/static/js/offlineLibrary.js

document.addEventListener('DOMContentLoaded', () => {
    // --- Configuration & Constants (should match downloadManager.js) ---
    const DB_NAME = 'AudioXOfflineDB';
    const DB_VERSION = 1; // Ensure this matches the version used in downloadManager.js
    const AUDIOBOOKS_STORE_NAME = 'downloadedAudiobooksInfo';
    const CHAPTERS_STORE_NAME = 'downloadedChaptersData';
    const AUDIO_CACHE_NAME = 'audiobook-audio-cache-v1';

    // --- DOM Elements ---
    const loadingMessageEl = document.getElementById('loading-downloads-message');
    const noDownloadsMessageEl = document.getElementById('no-downloads-message');
    const downloadsListEl = document.getElementById('downloaded-audiobooks-list');

    const offlinePlayerContainer = document.getElementById('offline-audio-player-container');
    const offlinePlayerTitleEl = document.getElementById('offline-player-title');
    const offlinePlayerAudioEl = document.getElementById('offline-player');
    const closeOfflinePlayerBtn = document.getElementById('close-offline-player-btn');

    let pageContext = {};
    try {
        const contextScript = document.getElementById('page-context-my-downloads');
        if (contextScript) {
            pageContext = JSON.parse(contextScript.textContent);
        }
    } catch (e) {
        console.error("Error parsing page context for my-downloads:", e);
    }
    // const csrfToken = pageContext.csrfToken; // For potential future API calls from this page

    // --- IndexedDB Helper Functions (copied from downloadManager.js for consistency) ---
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
            request.onupgradeneeded = (event) => { // Should have been created by downloadManager
                console.warn("DB upgrade needed in offlineLibrary.js - stores should already exist.");
                const db = event.target.result;
                if (!db.objectStoreNames.contains(AUDIOBOOKS_STORE_NAME)) {
                    db.createObjectStore(AUDIOBOOKS_STORE_NAME, { keyPath: 'audiobookId' });
                }
                if (!db.objectStoreNames.contains(CHAPTERS_STORE_NAME)) {
                    const chapterStore = db.createObjectStore(CHAPTERS_STORE_NAME, { keyPath: 'uniqueId' });
                    chapterStore.createIndex('byAudiobookId', 'audiobookId', { unique: false });
                }
            };
        });
        return dbPromise;
    }

    async function dbGetAll(storeName) {
        const db = await openDB();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction(storeName, 'readonly');
            const store = transaction.objectStore(storeName);
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = (event) => reject("DB GetAll Error: " + event.target.error?.message);
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
    async function getCachedAudioBlobUrl(cacheKey) {
        if (!window.caches) return null;
        try {
            const cache = await caches.open(AUDIO_CACHE_NAME);
            const cachedResponse = await cache.match(cacheKey);
            if (cachedResponse) {
                const blob = await cachedResponse.blob();
                return URL.createObjectURL(blob);
            }
        } catch (error) {
            console.error(`Error getting cached audio for ${cacheKey}:`, error);
        }
        return null;
    }

    async function deleteCachedAudioFile(cacheKey) {
        if (!window.caches) return false;
        try {
            const cache = await caches.open(AUDIO_CACHE_NAME);
            return await cache.delete(cacheKey);
        } catch (error) {
            console.error(`Error deleting cached audio ${cacheKey}:`, error);
            return false;
        }
    }

    // --- UI Rendering ---
    function formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    }

    async function renderDownloads() {
        if (!downloadsListEl || !loadingMessageEl || !noDownloadsMessageEl) return;

        loadingMessageEl.style.display = 'block';
        noDownloadsMessageEl.style.display = 'none';
        downloadsListEl.innerHTML = ''; // Clear existing items

        try {
            const downloadedAudiobooksInfo = await dbGetAll(AUDIOBOOKS_STORE_NAME);

            if (!downloadedAudiobooksInfo || downloadedAudiobooksInfo.length === 0) {
                noDownloadsMessageEl.style.display = 'block';
                loadingMessageEl.style.display = 'none';
                return;
            }

            for (const audiobookInfo of downloadedAudiobooksInfo) {
                const audiobookId = audiobookInfo.audiobookId;
                const chapters = await dbGetAllByIndex(CHAPTERS_STORE_NAME, 'byAudiobookId', audiobookId);
                chapters.sort((a, b) => (a.chapterOrder || 0) - (b.chapterOrder || 0)); // Sort by chapter order

                const audiobookDiv = document.createElement('div');
                audiobookDiv.className = 'bg-white shadow-lg rounded-xl border border-gray-200 overflow-hidden';
                audiobookDiv.dataset.audiobookId = audiobookId;

                let chaptersHtml = '';
                if (chapters && chapters.length > 0) {
                    chapters.forEach(chapter => {
                        chaptersHtml += `
                            <div class="chapter-download-item flex items-center justify-between p-3 rounded-lg download-item hover:shadow-sm" data-chapter-unique-id="${chapter.uniqueId}">
                                <div class="min-w-0 flex-1">
                                    <p class="text-sm font-medium text-gray-800 truncate" title="${chapter.chapterName || 'Untitled Chapter'}">
                                        ${chapter.chapterOrder ? `Ch. ${chapter.chapterOrder}: ` : ''}${chapter.chapterName || 'Untitled Chapter'}
                                    </p>
                                    <p class="text-xs text-gray-500">
                                        Size: ${chapter.sizeBytes ? formatBytes(chapter.sizeBytes) : 'N/A'}
                                        ${chapter.downloadedAt ? `• Downloaded: ${new Date(chapter.downloadedAt).toLocaleDateString()}` : ''}
                                    </p>
                                </div>
                                <div class="flex items-center space-x-2 ml-3">
                                    <button class="play-offline-chapter-btn action-button p-2 text-[#091e65] hover:bg-indigo-100 rounded-full" title="Play Offline" data-cache-key="${chapter.cachedFileKey}" data-chapter-title="${chapter.chapterName || 'Untitled Chapter'}">
                                        <i class="fas fa-play"></i>
                                    </button>
                                    <button class="delete-chapter-btn action-button p-2 text-red-500 hover:bg-red-100 rounded-full" title="Delete Chapter" data-chapter-unique-id="${chapter.uniqueId}" data-cache-key="${chapter.cachedFileKey}">
                                        <i class="fas fa-times-circle"></i>
                                    </button>
                                </div>
                            </div>
                        `;
                    });
                } else {
                    chaptersHtml = '<p class="text-sm text-gray-500 px-3 py-2">No chapters found for this download entry.</p>';
                }


                audiobookDiv.innerHTML = `
                    <div class="p-5 sm:p-6">
                        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between">
                            <div>
                                <h3 class="text-xl sm:text-2xl font-semibold text-[#091e65] font-serif">${audiobookInfo.title || 'Untitled Audiobook'}</h3>
                                <p class="text-xs text-gray-400 mt-1">ID: ${audiobookId}</p>
                                <p class="text-xs text-gray-500 mt-1">Status: ${audiobookInfo.status || 'Unknown'} ${audiobookInfo.status === 'partial' ? `(${audiobookInfo.downloadedChapters || 0}/${audiobookInfo.totalChapters || 'N/A'})` : ''}</p>
                            </div>
                            ${chapters && chapters.length > 0 ? `
                            <button class="delete-audiobook-btn action-button mt-3 sm:mt-0 text-xs text-red-600 hover:text-red-800 border border-red-300 px-3 py-1.5 rounded-md" data-audiobook-id="${audiobookId}">
                                <i class="fas fa-trash-alt mr-1.5"></i>Delete All From This Audiobook
                            </button>` : ''}
                        </div>
                    </div>
                    <div class="border-t border-gray-200 px-5 sm:px-6 py-4 space-y-3 bg-gray-50/50" id="chapters-for-${audiobookId}">
                        ${chaptersHtml}
                    </div>
                `;
                downloadsListEl.appendChild(audiobookDiv);
            }

        } catch (error) {
            console.error("Error rendering downloads:", error);
            noDownloadsMessageEl.innerHTML = `<p class="text-red-500">Error loading downloads: ${error.message}. Please try refreshing.</p>`;
            noDownloadsMessageEl.style.display = 'block';
        } finally {
            loadingMessageEl.style.display = 'none';
        }
    }

    // --- Event Handlers ---
    async function handlePlayOfflineChapter(event) {
        const button = event.target.closest('.play-offline-chapter-btn');
        if (!button) return;

        const cacheKey = button.dataset.cacheKey;
        const chapterTitle = button.dataset.chapterTitle || "Offline Audio";

        if (!cacheKey) {
            Swal.fire('Error', 'Audio source not found for this chapter.', 'error');
            return;
        }

        if (offlinePlayerAudioEl && offlinePlayerTitleEl && offlinePlayerContainer) {
            try {
                const audioBlobUrl = await getCachedAudioBlobUrl(cacheKey);
                if (audioBlobUrl) {
                    offlinePlayerTitleEl.textContent = chapterTitle;
                    offlinePlayerAudioEl.src = audioBlobUrl;
                    offlinePlayerAudioEl.play().catch(e => console.error("Offline playback error:", e));
                    offlinePlayerContainer.classList.add('visible');
                } else {
                    Swal.fire('Playback Error', `Could not load audio for "${chapterTitle}" from offline storage. It might have been deleted or corrupted.`, 'error');
                }
            } catch (error) {
                Swal.fire('Playback Error', `An error occurred while trying to play "${chapterTitle}".`, 'error');
            }
        }
    }

    async function handleDeleteChapter(event) {
        const button = event.target.closest('.delete-chapter-btn');
        if (!button) return;

        const chapterUniqueId = button.dataset.chapterUniqueId;
        const cacheKey = button.dataset.cacheKey;
        const chapterItemDiv = button.closest('.chapter-download-item');
        const audiobookDiv = button.closest('[data-audiobook-id]');
        const audiobookId = audiobookDiv ? audiobookDiv.dataset.audiobookId : null;


        Swal.fire({
            title: 'Delete Chapter?',
            text: "This chapter will be removed from your offline downloads. This action cannot be undone.",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Yes, delete it!'
        }).then(async (result) => {
            if (result.isConfirmed) {
                try {
                    await dbDelete(CHAPTERS_STORE_NAME, chapterUniqueId);
                    await deleteCachedAudioFile(cacheKey);
                    if (chapterItemDiv) chapterItemDiv.remove();
                    Swal.fire('Deleted!', 'The chapter has been removed from your downloads.', 'success');

                    // Update overall audiobook status if it was the last chapter or to 'partial'
                    if (audiobookId) {
                        const remainingChapters = await dbGetAllByIndex(CHAPTERS_STORE_NAME, 'byAudiobookId', audiobookId);
                        const audiobookInfo = await dbGet(AUDIOBOOKS_STORE_NAME, audiobookId);
                        if (audiobookInfo) {
                            if (remainingChapters.length === 0) {
                                await dbDelete(AUDIOBOOKS_STORE_NAME, audiobookId); // Remove audiobook entry if no chapters left
                                if (audiobookDiv) audiobookDiv.remove(); // Remove entire audiobook section from UI
                                 if (downloadsListEl.children.length === 0) {
                                    noDownloadsMessageEl.style.display = 'block';
                                }
                            } else {
                                audiobookInfo.status = 'partial';
                                audiobookInfo.downloadedChapters = remainingChapters.length;
                                // totalChapters should remain the same
                                await dbPut(AUDIOBOOKS_STORE_NAME, audiobookInfo);
                                // Re-render just this audiobook's header or the whole list
                                renderDownloads(); // Simplest way to refresh, could be more targeted
                            }
                        }
                    }


                } catch (error) {
                    console.error("Error deleting chapter:", error);
                    Swal.fire('Error', `Failed to delete chapter: ${error.message}`, 'error');
                }
            }
        });
    }

    async function handleDeleteAudiobook(event) {
        const button = event.target.closest('.delete-audiobook-btn');
        if (!button) return;

        const audiobookId = button.dataset.audiobookId;
        const audiobookDiv = button.closest('[data-audiobook-id]');

        Swal.fire({
            title: 'Delete All Chapters?',
            text: "All downloaded chapters for this audiobook will be removed. This action cannot be undone.",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Yes, delete all!'
        }).then(async (result) => {
            if (result.isConfirmed) {
                try {
                    const chaptersToDelete = await dbGetAllByIndex(CHAPTERS_STORE_NAME, 'byAudiobookId', audiobookId);
                    for (const chapter of chaptersToDelete) {
                        await deleteCachedAudioFile(chapter.cachedFileKey);
                        await dbDelete(CHAPTERS_STORE_NAME, chapter.uniqueId);
                    }
                    await dbDelete(AUDIOBOOKS_STORE_NAME, audiobookId);
                    if (audiobookDiv) audiobookDiv.remove();
                     if (downloadsListEl.children.length === 0) {
                        noDownloadsMessageEl.style.display = 'block';
                    }
                    Swal.fire('Deleted!', 'All chapters for this audiobook have been removed.', 'success');
                } catch (error) {
                    console.error("Error deleting audiobook chapters:", error);
                    Swal.fire('Error', `Failed to delete audiobook chapters: ${error.message}`, 'error');
                }
            }
        });
    }


    // --- Initialization ---
    function init() {
        if (!window.indexedDB || !window.caches) {
            console.warn("Offline storage (IndexedDB or Cache API) not supported. My Downloads page may not work correctly.");
            if (loadingMessageEl) loadingMessageEl.style.display = 'none';
            if (noDownloadsMessageEl) {
                noDownloadsMessageEl.textContent = "Offline downloads are not supported by your browser.";
                noDownloadsMessageEl.style.display = 'block';
            }
            return;
        }

        renderDownloads();

        // Event delegation for play and delete buttons
        if (downloadsListEl) {
            downloadsListEl.addEventListener('click', (event) => {
                if (event.target.closest('.play-offline-chapter-btn')) {
                    handlePlayOfflineChapter(event);
                } else if (event.target.closest('.delete-chapter-btn')) {
                    handleDeleteChapter(event);
                } else if (event.target.closest('.delete-audiobook-btn')) {
                    handleDeleteAudiobook(event);
                }
            });
        }

        if (closeOfflinePlayerBtn && offlinePlayerContainer && offlinePlayerAudioEl) {
            closeOfflinePlayerBtn.addEventListener('click', () => {
                offlinePlayerAudioEl.pause();
                offlinePlayerAudioEl.src = ''; // Release object URL
                offlinePlayerContainer.classList.remove('visible');
                if (offlinePlayerTitleEl) offlinePlayerTitleEl.textContent = "Now Playing...";
            });
        }
    }

    init();
});
