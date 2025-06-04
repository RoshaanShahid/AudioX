// static/js/offline_manager.js

(function(window) {
    'use strict';

    const DB_NAME = 'AudioXOfflineDB';
    const DB_VERSION = 3; // Incremented for new chapter data fields
    const AUDIOBOOKS_STORE_NAME = 'audiobooks';
    const CHAPTERS_STORE_NAME = 'chapters';

    let db;

    // --- Utility: Format Duration ---
    function formatDuration(totalSeconds) {
        if (isNaN(totalSeconds) || totalSeconds < 0) return "0:00";
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = Math.floor(totalSeconds % 60);
        return `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;
    }

    // --- Utility: Format File Size ---
    function formatFileSize(bytes) {
        if (bytes === 0 || isNaN(bytes) || !isFinite(bytes)) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        if (bytes < 1) return '0 Bytes'; // Handle extremely small or invalid byte values
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        if (i >= sizes.length || i < 0) return parseFloat(bytes.toFixed(2)) + ' Bytes'; // Fallback if i is out of bounds
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // --- Database Initialization ---
    async function initDB() {
        return new Promise((resolve, reject) => {
            if (db) {
                resolve(db);
                return;
            }
            console.log('OfflineManager: Initializing IndexedDB...');
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = (event) => {
                const tempDb = event.target.result;
                console.log(`OfflineManager: Upgrading DB from version ${event.oldVersion} to ${event.newVersion}`);

                if (!tempDb.objectStoreNames.contains(AUDIOBOOKS_STORE_NAME)) {
                    const audiobookStore = tempDb.createObjectStore(AUDIOBOOKS_STORE_NAME, { keyPath: 'audiobookId' });
                    audiobookStore.createIndex('title', 'title', { unique: false });
                    audiobookStore.createIndex('downloadedAt', 'downloadedAt', { unique: false }); // For sorting
                    audiobookStore.createIndex('lastChapterDownloadedAt', 'lastChapterDownloadedAt', { unique: false }); // For sorting
                    console.log(`OfflineManager: Created ${AUDIOBOOKS_STORE_NAME} store.`);
                } else if (event.oldVersion < 3) { // Example: if upgrading to v3 and store exists
                    const audiobookStore = event.target.transaction.objectStore(AUDIOBOOKS_STORE_NAME);
                    if (!audiobookStore.indexNames.contains('downloadedAt')) {
                        audiobookStore.createIndex('downloadedAt', 'downloadedAt', { unique: false });
                    }
                     if (!audiobookStore.indexNames.contains('lastChapterDownloadedAt')) {
                        audiobookStore.createIndex('lastChapterDownloadedAt', 'lastChapterDownloadedAt', { unique: false });
                    }
                }


                let chapterStore;
                if (!tempDb.objectStoreNames.contains(CHAPTERS_STORE_NAME)) {
                    chapterStore = tempDb.createObjectStore(CHAPTERS_STORE_NAME, { keyPath: 'id' });
                    console.log(`OfflineManager: Created ${CHAPTERS_STORE_NAME} store.`);
                } else {
                    chapterStore = event.target.transaction.objectStore(CHAPTERS_STORE_NAME);
                }

                if (!chapterStore.indexNames.contains('audiobookId')) {
                    chapterStore.createIndex('audiobookId', 'audiobookId', { unique: false });
                }
                if (!chapterStore.indexNames.contains('downloadedAt')) { // Added in v3
                    chapterStore.createIndex('downloadedAt', 'downloadedAt', { unique: false });
                }
                 if (!chapterStore.indexNames.contains('chapterIdOriginal')) {
                    chapterStore.createIndex('chapterIdOriginal', 'chapterIdOriginal', { unique: false });
                }
                console.log(`OfflineManager: Ensured indexes for ${CHAPTERS_STORE_NAME} store.`);
            };

            request.onsuccess = (event) => {
                db = event.target.result;
                console.log('OfflineManager: IndexedDB initialized successfully.');
                resolve(db);
            };

            request.onerror = (event) => {
                console.error('OfflineManager: IndexedDB error:', event.target.error);
                reject(event.target.error);
            };
        });
    }

    // Helper to promisify IDBRequest for cleaner async/await usage
    function promisifyRequest(request) {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }


    function getStore(storeName, mode = 'readonly') {
        if (!db) {
            throw new Error('OfflineManager: Database not initialized. Call initDB() first.');
        }
        const transaction = db.transaction(storeName, mode);
        return transaction.objectStore(storeName);
    }

    async function saveAudiobookMetadata(audiobookData) {
        await initDB();
        const store = getStore(AUDIOBOOKS_STORE_NAME, 'readwrite');
        const existingData = await promisifyRequest(store.get(audiobookData.audiobookId));
        
        const dataToStore = {
            audiobookId: audiobookData.audiobookId,
            title: audiobookData.title,
            author: audiobookData.author,
            coverImageUrl: audiobookData.coverImageUrl,
            slug: audiobookData.slug,
            language: audiobookData.language,
            genre: audiobookData.genre,
            isCreatorBook: audiobookData.isCreatorBook,
            downloadedAt: existingData ? existingData.downloadedAt : new Date().toISOString(),
            lastChapterDownloadedAt: new Date().toISOString() // Always update this when a chapter is involved
        };
        return promisifyRequest(store.put(dataToStore));
    }

    async function getAudiobookMetadata(audiobookId) {
        await initDB();
        return promisifyRequest(getStore(AUDIOBOOKS_STORE_NAME).get(audiobookId));
    }
    
    async function getAllDownloadedAudiobookMetadata() {
        await initDB();
        const allMeta = await promisifyRequest(getStore(AUDIOBOOKS_STORE_NAME).getAll());
        return allMeta || [];
    }

    async function saveChapter(chapterData) {
        const chapterToSave = { ...chapterData };
        chapterToSave.fileSize = chapterData.audioBlob.size;
        chapterToSave.downloadedAt = new Date().toISOString();

        await initDB();
        await promisifyRequest(getStore(CHAPTERS_STORE_NAME, 'readwrite').put(chapterToSave));
        
        // Update audiobook's lastChapterDownloadedAt
        const audiobookMeta = await getAudiobookMetadata(chapterToSave.audiobookId);
        if (audiobookMeta) {
            audiobookMeta.lastChapterDownloadedAt = chapterToSave.downloadedAt;
            await saveAudiobookMetadata(audiobookMeta);
        }
    }

    async function getChapter(chapterUniqueId) {
        await initDB();
        return promisifyRequest(getStore(CHAPTERS_STORE_NAME).get(chapterUniqueId));
    }

    async function getChaptersForAudiobook(audiobookId) {
        await initDB();
        const store = getStore(CHAPTERS_STORE_NAME);
        const index = store.index('audiobookId');
        const chapters = await promisifyRequest(index.getAll(audiobookId));
        return chapters ? chapters.sort((a, b) => a.chapterIndex - b.chapterIndex) : [];
    }

    async function isChapterDownloaded(chapterUniqueId) {
        const chapter = await getChapter(chapterUniqueId);
        return !!chapter;
    }

    async function downloadChapter(chapterInfo, audiobookInfo, progressCallback) {
        const chapterUniqueId = `${audiobookInfo.audiobookSlug || audiobookInfo.audiobookId}_${chapterInfo.chapter_id || chapterInfo.chapter_index}`;
        
        if (await isChapterDownloaded(chapterUniqueId)) {
            console.log(`OfflineManager: Chapter "${chapterInfo.chapter_title}" already downloaded.`);
            if (progressCallback) progressCallback(100, 'Already downloaded');
            return { success: true, message: 'Already downloaded' };
        }

        console.log(`OfflineManager: Starting download for chapter "${chapterInfo.chapter_title}"`);
        if (progressCallback) progressCallback(0, 'Starting...');

        try {
            await saveAudiobookMetadata({
                audiobookId: audiobookInfo.audiobookId,
                title: audiobookInfo.audiobookTitle,
                author: audiobookInfo.author,
                coverImageUrl: audiobookInfo.coverImageUrl,
                slug: audiobookInfo.audiobookSlug,
                language: audiobookInfo.language,
                genre: audiobookInfo.genre,
                isCreatorBook: audiobookInfo.isCreatorBook
            });
            
            if (progressCallback) progressCallback(10, 'Fetching...');

            const response = await fetch(chapterInfo.audio_url_template);
            if (!response.ok) {
                throw new Error(`HTTP error ${response.status} fetching audio`);
            }

            const contentLength = +response.headers.get('Content-Length');
            let loaded = 0;
            const total = contentLength || 0;

            const reader = response.body.getReader();
            const chunks = [];
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                chunks.push(value);
                loaded += value.length;
                if (total > 0 && progressCallback) {
                    const percentage = Math.min(Math.round((loaded / total) * 80) + 10, 90);
                    progressCallback(percentage, `Downloading...`);
                } else if (progressCallback) {
                     progressCallback(50, `Downloading... ${formatFileSize(loaded)}`);
                }
            }
            const audioBlob = new Blob(chunks, { type: response.headers.get('Content-Type') || 'audio/mpeg' });

            if (progressCallback) progressCallback(95, 'Saving...');

            await saveChapter({
                id: chapterUniqueId,
                audiobookId: audiobookInfo.audiobookId,
                chapterIdOriginal: chapterInfo.chapter_id,
                title: chapterInfo.chapter_title,
                chapterIndex: chapterInfo.chapter_index,
                audioBlob: audioBlob,
                durationSeconds: chapterInfo.duration_seconds,
                originalUrl: chapterInfo.audio_url_template,
                audiobookTitle: audiobookInfo.audiobookTitle, 
                audiobookAuthor: audiobookInfo.author,
                coverImageUrl: audiobookInfo.coverImageUrl 
            });

            console.log(`OfflineManager: Chapter "${chapterInfo.chapter_title}" downloaded successfully.`);
            if (progressCallback) progressCallback(100, 'Download complete!');
            return { success: true, message: 'Download complete!' };

        } catch (error) {
            console.error(`OfflineManager: Error downloading chapter "${chapterInfo.chapter_title}":`, error);
            if (progressCallback) progressCallback(-1, `Error: ${error.message.substring(0, 30)}`);
            return { success: false, message: `Error: ${error.message}` };
        }
    }

    async function downloadFullAudiobook(chaptersArray, audiobookInfo, chapterProgressCallback, overallProgressCallback) {
        if (!chaptersArray || chaptersArray.length === 0) {
            if (overallProgressCallback) overallProgressCallback(100, "No chapters to download.");
            return { success: true, message: "No chapters to download." };
        }

        const totalChapters = chaptersArray.length;
        let successfullyDownloadedCount = 0;
        let errorsEncountered = 0;

        if (overallProgressCallback) overallProgressCallback(0, `Starting download for "${audiobookInfo.audiobookTitle}"...`);

        for (let i = 0; i < totalChapters; i++) {
            const chapterInfo = chaptersArray[i];
            if (!chapterInfo.is_accessible) {
                console.log(`Skipping locked chapter: ${chapterInfo.chapter_title}`);
                if(chapterProgressCallback) chapterProgressCallback(i, 100, "Skipped (locked)");
                continue;
            }
            
            const chapterUniqueId = `${audiobookInfo.audiobookSlug || audiobookInfo.audiobookId}_${chapterInfo.chapter_id || chapterInfo.chapter_index}`;
            chapterInfo.chapter_unique_id = chapterUniqueId;

            const chapterDownloadStatus = await downloadChapter(chapterInfo, audiobookInfo, (percentage, message) => {
                if (chapterProgressCallback) chapterProgressCallback(i, percentage, message);
            });

            if (chapterDownloadStatus.success) {
                if (chapterDownloadStatus.message !== 'Already downloaded') successfullyDownloadedCount++;
            } else {
                errorsEncountered++;
                console.error(`Failed to download chapter ${i + 1}: ${chapterInfo.chapter_title}. Error: ${chapterDownloadStatus.message}`);
            }
            
            if (overallProgressCallback) {
                const processedChapters = i + 1;
                const overallPercentage = Math.round((processedChapters / totalChapters) * 100);
                overallProgressCallback(overallPercentage, `Processed ${processedChapters}/${totalChapters}. Last: ${chapterInfo.chapter_title}`);
            }
        }

        let finalMessage = "";
        if (errorsEncountered === 0) {
            finalMessage = successfullyDownloadedCount > 0 ? "All new chapters downloaded successfully!" : "All chapters were already downloaded.";
        } else if (successfullyDownloadedCount > 0) {
            finalMessage = `Download complete with ${errorsEncountered} error(s).`;
        } else {
            finalMessage = `Failed to download any new chapters due to ${errorsEncountered} error(s).`;
        }
        if (overallProgressCallback) overallProgressCallback(100, finalMessage);
        return { success: errorsEncountered === 0, message: finalMessage };
    }

    async function deleteChapter(chapterUniqueId) {
        await initDB();
        await promisifyRequest(getStore(CHAPTERS_STORE_NAME, 'readwrite').delete(chapterUniqueId));
        console.log(`OfflineManager: Deleted chapter ${chapterUniqueId}`);
        
        const parts = chapterUniqueId.split('_');
        const audiobookId = parts.slice(0, -1).join('_'); // Handle slugs that might contain underscores
        if (!audiobookId) {
            console.warn("Could not reliably determine audiobookId from chapterUniqueId:", chapterUniqueId);
            return;
        }

        const remainingChapters = await getChaptersForAudiobook(audiobookId);
        if (remainingChapters.length === 0) {
            console.log(`OfflineManager: No chapters left for audiobook ${audiobookId}. Deleting audiobook metadata.`);
            await deleteAudiobookMetadata(audiobookId);
        }
    }
    
    async function deleteAudiobookMetadata(audiobookId) {
        await initDB();
        return promisifyRequest(getStore(AUDIOBOOKS_STORE_NAME, 'readwrite').delete(audiobookId));
    }

    async function deleteAudiobookAndChapters(audiobookId) {
        await initDB();
        const chapterStore = getStore(CHAPTERS_STORE_NAME, 'readwrite');
        const chapterIndex = chapterStore.index('audiobookId');
        const cursorReq = chapterIndex.openCursor(IDBKeyRange.only(audiobookId));
    
        await new Promise((resolve, reject) => {
            let first = true;
            cursorReq.onsuccess = (event) => {
                const cursor = event.target.result;
                if (first && !cursor) { // Handle case where no chapters were found immediately
                    resolve();
                    first = false;
                    return;
                }
                first = false;
                if (cursor) {
                    const deleteRequest = cursor.delete(); // Delete current item
                    deleteRequest.onsuccess = () => {
                        cursor.continue(); // Move to next item
                    };
                    deleteRequest.onerror = (e_del) => {
                        console.error("Error deleting chapter during audiobook delete:", e_del);
                        cursor.continue(); // Try to continue even if one delete fails
                    };
                } else {
                    resolve(); // All items for this key have been processed
                }
            };
            cursorReq.onerror = (event) => reject(event.target.error);
        });
    
        await deleteAudiobookMetadata(audiobookId);
        console.log(`OfflineManager: Deleted audiobook ${audiobookId} and its chapters.`);
    }
    
    async function clearAllDownloads() {
        await initDB();
        await Promise.all([
            promisifyRequest(getStore(CHAPTERS_STORE_NAME, 'readwrite').clear()),
            promisifyRequest(getStore(AUDIOBOOKS_STORE_NAME, 'readwrite').clear())
        ]);
        console.log('OfflineManager: All downloads cleared.');
    }

    async function populateDownloadsPage() {
        const listEl = document.getElementById('downloaded-audiobooks-list');
        const noDownloadsMsg = document.getElementById('no-downloads-message');
        if (!listEl || !noDownloadsMsg) { console.error("Downloads page elements not found."); return; }

        listEl.innerHTML = '';
        try {
            await initDB();
            const audiobooksMeta = await getAllDownloadedAudiobookMetadata();

            if (!audiobooksMeta || audiobooksMeta.length === 0) {
                noDownloadsMsg.classList.remove('hidden');
                return;
            }
            noDownloadsMsg.classList.add('hidden');

            audiobooksMeta.sort((a, b) => new Date(b.lastChapterDownloadedAt || 0) - new Date(a.lastChapterDownloadedAt || 0));

            for (const audiobook of audiobooksMeta) {
                const chapters = await getChaptersForAudiobook(audiobook.audiobookId);
                if (chapters.length === 0) {
                    await deleteAudiobookMetadata(audiobook.audiobookId);
                    continue;
                }

                const audiobookCard = document.createElement('div');
                audiobookCard.className = 'downloaded-audiobook-card bg-white rounded-xl shadow-lg overflow-hidden border border-slate-200 flex flex-col';
                audiobookCard.dataset.audiobookId = audiobook.audiobookId;
                audiobookCard.dataset.audiobookSlug = audiobook.slug || audiobook.audiobookId; // For share link

                const coverSrc = audiobook.coverImageUrl || 'https://placehold.co/96x128/e2e8f0/94a3b8?text=Cover&font=sans';
                const downloadDateFormatted = audiobook.lastChapterDownloadedAt ? new Date(audiobook.lastChapterDownloadedAt).toLocaleDateString() : (audiobook.downloadedAt ? new Date(audiobook.downloadedAt).toLocaleDateString() : 'N/A');

                audiobookCard.innerHTML = `
                    <div class="p-5 border-b border-slate-200">
                        <div class="flex items-start space-x-4">
                            <img src="${coverSrc}" alt="Cover for ${audiobook.title}" class="w-24 h-32 object-cover rounded-md shadow-md flex-shrink-0" onerror="this.onerror=null;this.src='https://placehold.co/96x128/e2e8f0/94a3b8?text=Cover&font=sans';">
                            <div class="flex-grow min-w-0">
                                <h2 class="text-lg font-semibold text-[#091e65] group-hover:text-indigo-700 line-clamp-2 mb-0.5" title="${audiobook.title}">${audiobook.title}</h2>
                                <p class="text-sm text-slate-500 truncate mb-1" title="By ${audiobook.author || 'Unknown Author'}">By ${audiobook.author || 'Unknown Author'}</p>
                                <p class="text-xs text-slate-400">Last activity: ${downloadDateFormatted}</p>
                                <p class="text-xs text-slate-400">${chapters.length} Chapter${chapters.length === 1 ? '' : 's'} Downloaded</p>
                            </div>
                            <button class="delete-audiobook-btn text-slate-400 hover:text-red-600 p-1.5 -mr-1 -mt-1 rounded-full hover:bg-red-100 transition-colors focus:outline-none focus:ring-1 focus:ring-red-500" data-audiobook-id="${audiobook.audiobookId}" data-audiobook-title="${audiobook.title}" title="Delete all chapters for this audiobook">
                                <svg class="w-5 h-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12.56 0c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg>
                            </button>
                        </div>
                    </div>
                    <div class="chapters-list flex-grow overflow-y-auto max-h-[20rem] bg-slate-50/30 p-3 space-y-2 scroll-smooth">
                        ${chapters.map(chapter => `
                            <div class="downloaded-item bg-white p-3 rounded-lg shadow-sm border border-slate-200 flex items-center justify-between space-x-3" data-chapter-unique-id="${chapter.id}" data-audiobook-id="${chapter.audiobookId}" data-chapter-index="${chapter.chapterIndex}">
                                <button class="play-offline-chapter-btn flex-shrink-0 w-9 h-9 bg-indigo-100 hover:bg-indigo-200 text-[#091e65] rounded-full flex items-center justify-center transition focus:outline-none focus:ring-2 focus:ring-[#091e65] focus:ring-offset-1" title="Play '${chapter.title}'">
                                    <svg class="w-4 h-4 play-icon-offline" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" /></svg>
                                    <svg class="w-4 h-4 pause-icon-offline hidden" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path d="M5.75 4.75a.75.75 0 00-1.5 0v10.5a.75.75 0 001.5 0V4.75zM15.75 4.75a.75.75 0 00-1.5 0v10.5a.75.75 0 001.5 0V4.75z" /></svg>
                                </button>
                                <div class="flex-grow min-w-0">
                                    <p class="text-sm font-medium text-slate-700 truncate" title="${chapter.title}">${chapter.chapterIndex + 1}. ${chapter.title}</p>
                                    <p class="text-xs text-slate-500">
                                        ${chapter.durationSeconds ? formatDuration(chapter.durationSeconds) : 'N/A'}
                                        ${chapter.fileSize ? ` &bull; ${formatFileSize(chapter.fileSize)}` : ''}
                                    </p>
                                </div>
                                <div class="flex-shrink-0 flex items-center space-x-1">
                                    <button class="share-chapter-btn text-slate-400 hover:text-[#091e65] p-1.5 rounded-full hover:bg-indigo-50 transition-colors" data-chapter-title="${chapter.title}" data-audiobook-slug="${audiobook.slug || audiobook.audiobookId}" title="Share this chapter">
                                        <svg class="w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" /></svg>
                                    </button>
                                    <button class="delete-chapter-btn text-slate-400 hover:text-red-600 p-1.5 rounded-full hover:bg-red-50 transition-colors" data-chapter-unique-id="${chapter.id}" data-chapter-title="${chapter.title}" title="Delete this chapter">
                                        <svg class="w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                                    </button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
                listEl.appendChild(audiobookCard);
            }
            attachDynamicDownloadsEventListeners();
        } catch (error) {
            console.error("OfflineManager: Error populating downloads page:", error);
            listEl.innerHTML = `<p class="text-red-500 text-center py-10 col-span-full">Error loading downloads: ${error.message}</p>`;
            noDownloadsMsg.classList.add('hidden');
        }
    }

    // Attach event listeners to dynamically created buttons on the downloads page
    function attachDynamicDownloadsEventListeners() {
        document.querySelectorAll('.play-offline-chapter-btn').forEach(button => {
            button.addEventListener('click', function() {
                const item = this.closest('.downloaded-item');
                playOfflineChapter(item.dataset.chapterUniqueId, item.dataset.audiobookId, parseInt(item.dataset.chapterIndex));
            });
        });
        document.querySelectorAll('.delete-chapter-btn').forEach(button => {
            button.addEventListener('click', function(e) {
                e.stopPropagation();
                showDeleteConfirmModal('chapter', this.dataset.chapterUniqueId, this.dataset.chapterTitle);
            });
        });
        document.querySelectorAll('.delete-audiobook-btn').forEach(button => {
            button.addEventListener('click', function(e) {
                e.stopPropagation();
                showDeleteConfirmModal('audiobook', this.dataset.audiobookId, this.dataset.audiobookTitle);
            });
        });
         document.querySelectorAll('.share-chapter-btn').forEach(button => {
            button.addEventListener('click', function(e) {
                e.stopPropagation();
                const chapterTitle = this.dataset.chapterTitle;
                const audiobookSlug = this.dataset.audiobookSlug; // Get slug from data attribute
                const shareLink = `${window.location.origin}/audiobook/${audiobookSlug}/`; // Construct a link to the online detail page
                showShareModal(chapterTitle, shareLink);
            });
        });
    }
    
    // --- Offline Player Logic (for my_downloads.html) ---
    let offlinePlayer;
    let offlinePlayerBar, offlinePlayerCover, offlinePlayerEpisodeTitle, offlinePlayerAudiobookTitle;
    let offlinePlayPauseBtn, offlinePlayIcon, offlinePauseIcon, offlinePrevBtn, offlineNextBtn;
    let offlineCurrentTime, offlineDuration, offlineSeekBar, offlineSpeedBtn, offlineCloseBtn;
    
    let currentOfflinePlaylist = []; 
    let currentOfflineChapterIdx = -1;
    const offlinePlaybackSpeeds = [1, 1.5, 2];
    let currentOfflineSpeedIndex = 0;
    let currentPlayingOfflineItemEl = null;

    function initOfflinePlayer() {
        offlinePlayer = document.getElementById('offlineAudioPlayer');
        offlinePlayerBar = document.getElementById('offline-player-bar');
        offlinePlayerCover = document.getElementById('offline-player-cover-image');
        offlinePlayerEpisodeTitle = document.getElementById('offline-player-episode-title');
        offlinePlayerAudiobookTitle = document.getElementById('offline-player-audiobook-title');
        offlinePlayPauseBtn = document.getElementById('offline-player-play-pause-button');
        offlinePlayIcon = document.getElementById('offline-player-play-icon');
        offlinePauseIcon = document.getElementById('offline-player-pause-icon');
        offlinePrevBtn = document.getElementById('offline-player-prev-button');
        offlineNextBtn = document.getElementById('offline-player-next-button');
        offlineCurrentTime = document.getElementById('offline-player-current-time');
        offlineDuration = document.getElementById('offline-player-duration');
        offlineSeekBar = document.getElementById('offline-player-seek-bar');
        offlineSpeedBtn = document.getElementById('offline-player-speed-button');
        offlineCloseBtn = document.getElementById('offline-player-close-button');

        if (!offlinePlayer || !offlinePlayerBar) {
             console.warn("Offline player elements not all found on this page.");
             return;
        }

        offlinePlayPauseBtn.addEventListener('click', toggleOfflinePlayPause);
        offlinePrevBtn.addEventListener('click', playPreviousOfflineChapter);
        offlineNextBtn.addEventListener('click', playNextOfflineChapter);
        offlineSpeedBtn.addEventListener('click', cycleOfflinePlaybackSpeed);
        offlineCloseBtn.addEventListener('click', closeOfflinePlayer);
        if(offlineSeekBar) offlineSeekBar.addEventListener('input', () => { // Check if seekBar exists
            if (offlinePlayer.duration) offlinePlayer.currentTime = offlineSeekBar.value;
        });

        offlinePlayer.addEventListener('play', () => updateOfflinePlayerUIState('playing'));
        offlinePlayer.addEventListener('pause', () => updateOfflinePlayerUIState('paused'));
        offlinePlayer.addEventListener('ended', () => {
            updateOfflinePlayerUIState('ended');
            playNextOfflineChapter();
        });
        offlinePlayer.addEventListener('loadedmetadata', () => {
            if (offlinePlayer.duration && isFinite(offlinePlayer.duration)) {
                if(offlineDuration) offlineDuration.textContent = formatDuration(offlinePlayer.duration);
                if(offlineSeekBar) offlineSeekBar.max = offlinePlayer.duration;
            } else {
                if(offlineDuration) offlineDuration.textContent = '0:00';
                if(offlineSeekBar) offlineSeekBar.max = 0;
            }
             if(offlineCurrentTime) offlineCurrentTime.textContent = '0:00';
             if(offlineSeekBar) offlineSeekBar.value = 0;
        });
        offlinePlayer.addEventListener('timeupdate', () => {
            if (offlinePlayer.duration) {
                if(offlineCurrentTime) offlineCurrentTime.textContent = formatDuration(offlinePlayer.currentTime);
                if(offlineSeekBar) offlineSeekBar.value = offlinePlayer.currentTime;
            }
        });
        offlinePlayer.addEventListener('error', (e) => {
            console.error("Offline Player Error:", e, offlinePlayer.error);
            updateOfflinePlayerUIState('error');
        });
    }

    function updateOfflinePlayerUIState(state) {
        if (!offlinePlayIcon || !offlinePauseIcon) return;
        offlinePlayIcon.classList.toggle('hidden', state === 'playing');
        offlinePauseIcon.classList.toggle('hidden', state !== 'playing');

        document.querySelectorAll('.downloaded-item.playing .pause-icon-offline').forEach(icon => icon.classList.add('hidden'));
        document.querySelectorAll('.downloaded-item.playing .play-icon-offline').forEach(icon => icon.classList.remove('hidden'));
        document.querySelectorAll('.downloaded-item.playing').forEach(el => el.classList.remove('playing'));

        if (currentPlayingOfflineItemEl) {
            const itemPlayIcon = currentPlayingOfflineItemEl.querySelector('.play-icon-offline');
            const itemPauseIcon = currentPlayingOfflineItemEl.querySelector('.pause-icon-offline');
            if(state === 'playing'){
                if (itemPlayIcon) itemPlayIcon.classList.add('hidden');
                if (itemPauseIcon) itemPauseIcon.classList.remove('hidden');
                currentPlayingOfflineItemEl.classList.add('playing');
            } else { 
                if (itemPlayIcon) itemPlayIcon.classList.remove('hidden');
                if (itemPauseIcon) itemPauseIcon.classList.add('hidden');
                // currentPlayingOfflineItemEl.classList.remove('playing'); // Already done above for all items
            }
        }
    }
    
    async function playOfflineChapter(chapterUniqueId, audiobookId, chapterIndex) {
        try {
            const chapterToPlay = await getChapter(chapterUniqueId);
            const audiobookMeta = await getAudiobookMetadata(audiobookId);

            if (!chapterToPlay || !chapterToPlay.audioBlob || !audiobookMeta) {
                console.error("OfflineManager: Chapter or audiobook metadata not found for playback.", chapterUniqueId, audiobookId);
                alert("Error: Could not load this downloaded chapter.");
                return;
            }

            currentOfflinePlaylist = await getChaptersForAudiobook(audiobookId);
            currentOfflineChapterIdx = currentOfflinePlaylist.findIndex(ch => ch.id === chapterUniqueId);
            
            if(currentOfflineChapterIdx === -1 && chapterIndex !== undefined) {
                currentOfflineChapterIdx = chapterIndex; 
            }


            const blobUrl = URL.createObjectURL(chapterToPlay.audioBlob);
            if (offlinePlayer.previousObjectURL) { URL.revokeObjectURL(offlinePlayer.previousObjectURL); }
            offlinePlayer.previousObjectURL = blobUrl;
            offlinePlayer.src = blobUrl;
            offlinePlayer.load();
            offlinePlayer.play().catch(e => console.error("Error playing offline chapter:", e));

            if(offlinePlayerEpisodeTitle) offlinePlayerEpisodeTitle.textContent = chapterToPlay.title;
            if(offlinePlayerEpisodeTitle) offlinePlayerEpisodeTitle.title = chapterToPlay.title;
            if(offlinePlayerAudiobookTitle) offlinePlayerAudiobookTitle.textContent = audiobookMeta.title;
            if(offlinePlayerCover) offlinePlayerCover.src = audiobookMeta.coverImageUrl || 'https://placehold.co/64x64/e2e8f0/94a3b8?text=N/A&font=sans';
            if(offlinePlayerBar) offlinePlayerBar.classList.remove('translate-y-full');

            if(offlinePrevBtn) offlinePrevBtn.disabled = currentOfflineChapterIdx <= 0;
            if(offlineNextBtn) offlineNextBtn.disabled = currentOfflineChapterIdx >= currentOfflinePlaylist.length - 1;

            const newPlayingItemEl = document.querySelector(`.downloaded-item[data-chapter-unique-id="${chapterUniqueId}"]`);
            if (currentPlayingOfflineItemEl && currentPlayingOfflineItemEl !== newPlayingItemEl) {
                 currentPlayingOfflineItemEl.classList.remove('playing');
                 const oldPlay = currentPlayingOfflineItemEl.querySelector('.play-icon-offline');
                 const oldPause = currentPlayingOfflineItemEl.querySelector('.pause-icon-offline');
                 if(oldPlay) oldPlay.classList.remove('hidden');
                 if(oldPause) oldPause.classList.add('hidden');
            }
            currentPlayingOfflineItemEl = newPlayingItemEl;
            // updateOfflinePlayerUIState will handle adding 'playing' class based on player state
            // if (currentPlayingOfflineItemEl) currentPlayingOfflineItemEl.classList.add('playing');

        } catch (error) {
            console.error("OfflineManager: Error setting up offline chapter for playback:", error);
            alert("Error: Could not play this downloaded chapter.");
        }
    }

    function toggleOfflinePlayPause() {
        if (!offlinePlayer.src || currentOfflineChapterIdx < 0) {
            const firstPlayButton = document.querySelector('.play-offline-chapter-btn');
            if (firstPlayButton) {
                const item = firstPlayButton.closest('.downloaded-item');
                if(item) playOfflineChapter(item.dataset.chapterUniqueId, item.dataset.audiobookId, parseInt(item.dataset.chapterIndex));
            } else {
                 const myDownloadsModal = window.OfflineManager.getModalElements().myDownloadsGeneralModal; // Assuming you add this
                 if(myDownloadsModal) showModal(myDownloadsModal.modal, "No Audio Selected", "Please select a chapter from your downloads to play.", null, "OK", null, true);
                 else console.log("Offline Player: No chapter selected or available to play.");
            }
            return;
        }
        if (offlinePlayer.paused || offlinePlayer.ended) {
            offlinePlayer.play().catch(e => console.error("Error resuming offline play:", e));
        } else {
            offlinePlayer.pause();
        }
    }

    function playNextOfflineChapter() {
        if (currentOfflinePlaylist.length > 0 && currentOfflineChapterIdx < currentOfflinePlaylist.length - 1) {
            currentOfflineChapterIdx++;
            const nextChapter = currentOfflinePlaylist[currentOfflineChapterIdx];
            playOfflineChapter(nextChapter.id, nextChapter.audiobookId, nextChapter.chapterIndex);
        } else {
            updateOfflinePlayerUIState('ended');
        }
    }

    function playPreviousOfflineChapter() {
         if (currentOfflinePlaylist.length > 0 && currentOfflineChapterIdx > 0) {
            currentOfflineChapterIdx--;
            const prevChapter = currentOfflinePlaylist[currentOfflineChapterIdx];
            playOfflineChapter(prevChapter.id, prevChapter.audiobookId, prevChapter.chapterIndex);
        }
    }
    
    function cycleOfflinePlaybackSpeed() {
        if(!offlinePlayer || !offlineSpeedBtn) return;
        currentOfflineSpeedIndex = (currentOfflineSpeedIndex + 1) % offlinePlaybackSpeeds.length;
        const newSpeed = offlinePlaybackSpeeds[currentOfflineSpeedIndex];
        offlinePlayer.playbackRate = newSpeed;
        offlineSpeedBtn.textContent = `${newSpeed}x`;
    }

    function closeOfflinePlayer() {
        if(!offlinePlayer || !offlinePlayerBar) return;
        offlinePlayer.pause();
        if (offlinePlayer.previousObjectURL) {
            URL.revokeObjectURL(offlinePlayer.previousObjectURL);
            offlinePlayer.previousObjectURL = null;
        }
        offlinePlayer.src = '';
        offlinePlayerBar.classList.add('translate-y-full');
        if(currentPlayingOfflineItemEl) {
            currentPlayingOfflineItemEl.classList.remove('playing');
            const playIcon = currentPlayingOfflineItemEl.querySelector('.play-icon-offline');
            const pauseIcon = currentPlayingOfflineItemEl.querySelector('.pause-icon-offline');
            if(playIcon) playIcon.classList.remove('hidden');
            if(pauseIcon) pauseIcon.classList.add('hidden');
        }
        currentPlayingOfflineItemEl = null;
        currentOfflineChapterIdx = -1;
        currentOfflinePlaylist = [];
        if(offlineSeekBar) offlineSeekBar.value = 0;
        if(offlineCurrentTime) offlineCurrentTime.textContent = '0:00';
        if(offlineDuration) offlineDuration.textContent = '0:00';
        if(offlinePlayerEpisodeTitle) offlinePlayerEpisodeTitle.textContent = 'Select an episode';
        if(offlinePlayerAudiobookTitle) offlinePlayerAudiobookTitle.textContent = 'Audiobook Title';
        if(offlinePlayerCover) offlinePlayerCover.src = 'https://placehold.co/64x64/e2e8f0/94a3b8?text=AudioX&font=sans';
        if(offlinePrevBtn) offlinePrevBtn.disabled = true;
        if(offlineNextBtn) offlineNextBtn.disabled = true;
    }

    // --- Modal Logic ---
    let deleteConfirmCallback = null;
    const deleteModal = document.getElementById('delete-confirm-modal');
    const deleteModalTitle = document.getElementById('delete-modal-title');
    const deleteModalMessage = document.getElementById('delete-modal-message');
    const deleteModalConfirmBtn = document.getElementById('delete-modal-confirm-btn');
    const deleteModalCancelBtn = document.getElementById('delete-modal-cancel-btn');
    const deleteModalCloseIcon = document.getElementById('delete-modal-close-icon');

    const shareModal = document.getElementById('share-modal');
    const shareModalTitle = document.getElementById('share-modal-title');
    const shareModalLinkInput = document.getElementById('share-modal-link-input');
    const shareModalCopyBtn = document.getElementById('share-modal-copy-btn');
    const shareModalFeedback = document.getElementById('share-modal-feedback');
    const shareModalCloseIcon = document.getElementById('share-modal-close-icon');
    const shareModalSocialButtons = document.getElementById('share-modal-social-buttons');

    function showModal(modalElement) {
        if (!modalElement) return;
        modalElement.style.display = 'flex'; // Instead of modal-active class for simplicity here
        requestAnimationFrame(() => { // Ensure display:flex is applied before transitions
            modalElement.classList.remove('opacity-0', 'scale-95', 'modal-inactive');
            modalElement.classList.add('opacity-100', 'scale-100');
        });
    }

    function hideModal(modalElement) {
        if (!modalElement) return;
        modalElement.classList.remove('opacity-100', 'scale-100');
        modalElement.classList.add('opacity-0', 'scale-95');
        setTimeout(() => {
            modalElement.style.display = 'none'; // Instead of modal-inactive class
            modalElement.classList.add('modal-inactive'); // Re-add for consistency if used elsewhere
        }, 300); // Match transition duration
    }
    
    function showDeleteConfirmModal(type, id, title) {
        if (!deleteModal || !deleteModalTitle || !deleteModalMessage) return;
        deleteModalTitle.textContent = `Delete ${type === 'all' ? 'All Content' : (type === 'audiobook' ? 'Audiobook' : 'Chapter')}`;
        let message = `Are you sure you want to delete "${title}"? `;
        if (type === 'audiobook') message += 'All its downloaded chapters will be removed. ';
        if (type === 'all') message = `Are you sure you want to delete ALL your downloaded audiobooks and chapters? `;
        message += 'This action cannot be undone.';
        deleteModalMessage.textContent = message;
        
        deleteConfirmCallback = async () => {
            try {
                if (type === 'audiobook') {
                    await deleteAudiobookAndChapters(id);
                } else if (type === 'chapter') {
                    await deleteChapter(id);
                } else if (type === 'all') {
                    await clearAllDownloads();
                    closeOfflinePlayer();
                }
                await populateDownloadsPage();
            } catch(err) {
                console.error("Error during deletion:", err);
                // Show some error to user via a toast perhaps
            } finally {
                hideModal(deleteModal);
            }
        };
        showModal(deleteModal);
    }

    function showShareModal(chapterTitle, shareLink) {
        if (!shareModal || !shareModalTitle || !shareModalLinkInput || !shareModalFeedback || !shareModalSocialButtons) return;
        shareModalTitle.textContent = `Share: ${chapterTitle}`;
        shareModalLinkInput.value = shareLink;
        shareModalFeedback.textContent = '';

        shareModalSocialButtons.innerHTML = ''; 
        const encodedLink = encodeURIComponent(shareLink);
        const encodedTitle = encodeURIComponent(`Listen to ${chapterTitle} on AudioX: ${shareLink}`); // More descriptive for WhatsApp

        const socialPlatforms = [
            { name: 'Facebook', icon: '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M20 3H4a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h8.615v-6.96h-2.338v-2.725h2.338v-2.005c0-2.308 1.386-3.583 3.486-3.583.996 0 1.84.074 2.086.106v2.439h-1.438c-1.124 0-1.341.534-1.341 1.316v1.73h2.695l-.35 2.725h-2.345V21H20a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1z"/></svg>', url: `https://www.facebook.com/sharer/sharer.php?u=${encodedLink}` },
            { name: 'Twitter', icon: '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M22.46 6c-.77.35-1.6.58-2.46.67.88-.53 1.56-1.37 1.88-2.38-.83.49-1.75.85-2.72 1.04C18.37 4.5 17.26 4 16 4c-2.35 0-4.27 1.92-4.27 4.29 0 .34.04.67.11.98C8.28 9.09 5.11 7.38 3 4.79c-.37.63-.58 1.37-.58 2.15 0 1.49.75 2.81 1.91 3.56-.71 0-1.37-.22-1.95-.5v.03c0 2.08 1.48 3.82 3.44 4.21a4.22 4.22 0 0 1-1.94.07 4.28 4.28 0 0 0 4 2.98 8.521 8.521 0 0 1-5.33 1.84c-.34 0-.68-.02-1.02-.06C3.44 20.29 5.58 21 7.89 21 16 21 20.48 14.69 20.48 9.05c0-.21 0-.43-.01-.64.84-.6 1.57-1.36 2.15-2.23z"/></svg>', url: `https://twitter.com/intent/tweet?url=${encodedLink}&text=${encodedTitle}` },
            { name: 'WhatsApp', icon: '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.38 1.25 4.82l-1.34 4.91 5.04-1.32c1.4.72 2.97 1.14 4.61 1.14h.01c5.46 0 9.91-4.45 9.91-9.91S17.5 2 12.04 2zM18 15.23c-.23.12-.76.38-1.01.42-.4.06-.58.06-.84-.12-.32-.23-1.42-1.31-1.79-2.17-.09-.2-.52-1.04.03-1.32.06-.03.41-.18.58-.23.06-.02.18-.03.23.09.06.12.21.52.23.58.03.06.06.12.09.18.1.18.06.3-.03.42-.09.12-.15.18-.23.23-.1.06-.21.09-.3.06-.09-.03-.23-.09-.73-.29-1.14-.46-1.68-1.62-1.73-1.74-.06-.15-.03-.23.03-.3.02-.03.06-.06.09-.09.09-.09.21-.27.3-.36.18-.18.27-.3.39-.52.12-.21.06-.39-.03-.52-.09-.12-.7-.84-.99-1.17s-.49-.26-.76-.26h-.03c-.23 0-.49.03-.67.15-.3.21-.93.9-.93 2.02 0 .7.32 1.38.7 2.02.76 1.24 1.91 2.63 3.72 3.45.69.32 1.24.42 1.76.52.21.03.58.03.82-.06.3-.12.76-.52.96-.73.06-.06.15-.03.23.03l.01.01c.08.06.14.1.12.18z"/></svg>', url: `https://api.whatsapp.com/send?text=${encodedTitle}` }
        ];
        socialPlatforms.forEach(platform => {
            const btn = document.createElement('a');
            btn.href = platform.url;
            btn.target = "_blank";
            btn.rel = "noopener noreferrer";
            btn.className = "p-2.5 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-[#091e65] transition-colors";
            btn.title = `Share on ${platform.name}`;
            btn.innerHTML = platform.icon;
            shareModalSocialButtons.appendChild(btn);
        });
        showModal(shareModal);
    }

    function initDownloadsPageModals() {
        if (deleteModalConfirmBtn) deleteModalConfirmBtn.addEventListener('click', () => { if (deleteConfirmCallback) deleteConfirmCallback(); });
        if (deleteModalCancelBtn) deleteModalCancelBtn.addEventListener('click', () => hideModal(deleteModal));
        if (deleteModalCloseIcon) deleteModalCloseIcon.addEventListener('click', () => hideModal(deleteModal));
        if (deleteModal) deleteModal.addEventListener('click', (e) => { if(e.target === deleteModal) hideModal(deleteModal); });


        if (shareModalCopyBtn) {
            shareModalCopyBtn.addEventListener('click', () => {
                if(shareModalLinkInput && shareModalFeedback) {
                    shareModalLinkInput.select();
                    shareModalLinkInput.setSelectionRange(0, 99999); // For mobile devices
                    try {
                        navigator.clipboard.writeText(shareModalLinkInput.value).then(() => {
                            shareModalFeedback.textContent = 'Link copied to clipboard!';
                            setTimeout(() => { shareModalFeedback.textContent = ''; }, 2500);
                        }).catch(err => {
                             shareModalFeedback.textContent = 'Failed to copy link.';
                             console.error('Failed to copy link using Clipboard API: ', err);
                        });
                    } catch (err) { // Fallback for older browsers (less secure)
                        try {
                             document.execCommand('copy');
                             shareModalFeedback.textContent = 'Link copied to clipboard! (fallback)';
                             setTimeout(() => { shareModalFeedback.textContent = ''; }, 2500);
                        } catch (e) {
                             shareModalFeedback.textContent = 'Failed to copy link.';
                             console.error('Failed to copy link using execCommand: ', e);
                        }
                    }
                }
            });
        }
        if (shareModalCloseIcon) shareModalCloseIcon.addEventListener('click', () => hideModal(shareModal));
        if (shareModal) shareModal.addEventListener('click', (e) => { if(e.target === shareModal) hideModal(shareModal); });


        const clearAllBtn = document.getElementById('clear-all-downloads-btn');
        if (clearAllBtn) {
            clearAllBtn.addEventListener('click', () => {
                showDeleteConfirmModal('all', 'all', 'all your downloaded content');
            });
        }
        
        const searchInput = document.getElementById('search-downloads-input');
        if(searchInput){
            searchInput.addEventListener('input', handleSearchDownloads);
        }
    }
    
    function handleSearchDownloads(event) {
        const searchTerm = event.target.value.toLowerCase().trim();
        const audiobookCards = document.querySelectorAll('.downloaded-audiobook-card');
        let displayedCardsCount = 0;

        audiobookCards.forEach(card => {
            const title = (card.querySelector('h2')?.textContent || '').toLowerCase();
            const author = (card.querySelector('p.text-sm.text-slate-500')?.textContent || '').toLowerCase();
            const chaptersContainer = card.querySelector('.chapters-list');
            const chapters = chaptersContainer ? chaptersContainer.querySelectorAll('.downloaded-item') : [];
            
            let audiobookMatchesSearch = title.includes(searchTerm) || author.includes(searchTerm);
            let anyChapterMatchesSearch = false;

            chapters.forEach(chapter => {
                const chapterTitle = (chapter.querySelector('p.text-sm.font-medium')?.textContent || '').toLowerCase();
                if (chapterTitle.includes(searchTerm)) {
                    chapter.style.display = 'flex';
                    anyChapterMatchesSearch = true;
                } else {
                    chapter.style.display = 'none';
                }
            });

            // If the audiobook card itself matches, show all its chapters (unless a chapter was specifically filtered out - this logic could be enhanced)
            // For now, if the audiobook title/author matches, or if any chapter matches, the card is visible.
            if (audiobookMatchesSearch || anyChapterMatchesSearch) {
                card.style.display = 'flex';
                displayedCardsCount++;
                // If the audiobook itself matched, ensure all its chapters are visible
                if(audiobookMatchesSearch && !anyChapterMatchesSearch && searchTerm){ // Only show all if audiobook matched but no specific chapter
                    chapters.forEach(ch => ch.style.display = 'flex');
                } else if (!searchTerm) { // If search is cleared, show all chapters
                     chapters.forEach(ch => ch.style.display = 'flex');
                }
            } else {
                card.style.display = 'none';
            }
        });

        const noDownloadsMsg = document.getElementById('no-downloads-message');
        if (noDownloadsMsg) {
            const totalAudiobooksPresent = audiobookCards.length > 0; // Check if there were any downloads to begin with

            if (displayedCardsCount === 0 && searchTerm) { // No results for a search term
                noDownloadsMsg.innerHTML = `
                    <svg class="mx-auto h-12 w-12 text-slate-400 mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" /></svg>
                    <h3 class="text-lg font-semibold text-slate-700">No matches for "${searchTerm}"</h3>
                    <p class="text-slate-500 mt-1">Try a different search term or clear your search.</p>`;
                noDownloadsMsg.classList.remove('hidden');
            } else if (displayedCardsCount === 0 && !searchTerm && !totalAudiobooksPresent) { // No downloads at all initially
                noDownloadsMsg.innerHTML = `
                    <svg class="mx-auto h-16 w-16 text-slate-400 mb-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                    </svg>
                    <h3 class="text-xl font-semibold text-slate-700 mb-2">No Downloads Yet</h3>
                    <p class="text-slate-500 mb-6 max-w-md mx-auto">Audiobooks and chapters you download for offline listening will appear here. Start exploring and build your offline library!</p>
                    <a href="/" class="inline-flex items-center bg-[#091e65] text-white px-6 py-3 rounded-lg font-semibold hover:bg-opacity-90 transition-colors shadow-md hover:shadow-lg">
                        <svg class="w-5 h-5 mr-2 -ml-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" /></svg>
                        Browse Audiobooks
                    </a>`; // Consider replacing href="/" with a dynamic home URL if available
                noDownloadsMsg.classList.remove('hidden');
            } else { // Downloads are visible or search cleared with items present
                noDownloadsMsg.classList.add('hidden');
            }
        }
    }


    // --- Public API ---
    window.OfflineManager = {
        initDB,
        isChapterDownloaded,
        downloadChapter,
        downloadFullAudiobook,
        // For downloads page UI and interactions:
        populateDownloadsPage,
        initOfflinePlayer,
        initDownloadsPageModals
    };

})(window);