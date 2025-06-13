// Wait for the DOM to be fully loaded before executing the script
document.addEventListener('DOMContentLoaded', function() {
    // --- Constants ---
    const THEME_COLOR_PRIMARY = '#091e65';
    const THEME_COLOR_ERROR = '#ef4444';
    const THEME_COLOR_SUCCESS = '#10b981';
    const THEME_COLOR_WARNING = '#f97316';

    // --- CSRF Token and URLs ---
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    const generateTtsPreviewUrl = document.getElementById('generate-tts-preview-url-manage')?.textContent.trim();
    const generateDocumentTtsPreviewUrl = document.getElementById('generate-document-tts-preview-url-manage')?.textContent.trim();

    // --- TTS Voice Data & Fixed Audiobook Language ---
    let edgeTtsVoicesByLangManage = {};
    let ALL_EDGE_TTS_VOICES_MAP_MANAGE = {}; // For quick lookup by voice ID
    const ttsVoicesDataScriptManage = document.getElementById('edge-tts-voices-data-manage');
    if (ttsVoicesDataScriptManage && ttsVoicesDataScriptManage.textContent) {
        try {
            edgeTtsVoicesByLangManage = JSON.parse(ttsVoicesDataScriptManage.textContent || '{}');
            for (const lang in edgeTtsVoicesByLangManage) {
                if (edgeTtsVoicesByLangManage.hasOwnProperty(lang)) {
                    edgeTtsVoicesByLangManage[lang].forEach(voice => {
                        ALL_EDGE_TTS_VOICES_MAP_MANAGE[voice.id] = voice;
                    });
                }
            }
        } catch (e) {
            console.error("Error parsing Edge TTS voices data for manage page:", e);
        }
    }
    const currentAudiobookLanguageManage = document.getElementById('current-audiobook-language-manage')?.textContent.trim() || '';
    if (!currentAudiobookLanguageManage) {
        // console.warn("Audiobook language could not be determined from the page. TTS functionality might be affected.");
    }

    // --- Cover Image Handling ---
    const coverInputMainForm = document.getElementById('cover_image_input_main_form');
    const coverPreview = document.getElementById('coverImagePreview');
    const coverNameDisplay = document.getElementById('coverImageNameDisplay');
    const originalCoverSrc = coverPreview ? coverPreview.src : '';
    const originalCoverName = coverNameDisplay ? coverNameDisplay.textContent : '';

    if (coverInputMainForm && coverPreview && coverNameDisplay) {
        coverInputMainForm.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                if (file.size > 2 * 1024 * 1024) { // Max 2MB
                    Swal.fire({ title: 'Cover Image Too Large', html: `Cover image must be under <strong>2MB</strong>. <br/>Selected file is ${(file.size / (1024*1024)).toFixed(2)}MB.`, icon: 'error', iconColor: THEME_COLOR_ERROR, confirmButtonColor: THEME_COLOR_PRIMARY, customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal' }});
                    event.target.value = '';
                    coverPreview.src = originalCoverSrc;
                    coverNameDisplay.textContent = originalCoverName;
                    return;
                }
                if (!['image/jpeg', 'image/png', 'image/jpg'].includes(file.type)) {
                    Swal.fire({ title: 'Invalid File Type', text: 'Please select a JPG, JPEG, or PNG image.', icon: 'error', iconColor: THEME_COLOR_ERROR, confirmButtonColor: THEME_COLOR_PRIMARY, customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal' }});
                    event.target.value = '';
                    coverPreview.src = originalCoverSrc;
                    coverNameDisplay.textContent = originalCoverName;
                    return;
                }
                const reader = new FileReader();
                reader.onload = function(e) { coverPreview.src = e.target.result; }
                reader.readAsDataURL(file);
                coverNameDisplay.textContent = file.name;
            } else {
                coverPreview.src = originalCoverSrc;
                coverNameDisplay.textContent = originalCoverName;
            }
        });
    }

    // --- Toggle "Add New Chapter" Form Visibility ---
    const addChapterBtn = document.getElementById('toggleAddChapterFormBtn');
    const addChapterFormContainer = document.getElementById('addChapterFormContainer');
    const addChapterIcon = document.getElementById('addChapterIcon');
    const addChapterText = document.getElementById('addChapterText');

    let formErrors = {};
    let submittedValuesFromDjango = {}; // To store values passed from Django, if any

    const formErrorsDataScript = document.getElementById('django-form-errors-data');
    if (formErrorsDataScript && formErrorsDataScript.textContent) {
        try {
            formErrors = JSON.parse(formErrorsDataScript.textContent || '{}');
        } catch(e) {
            console.error("Error parsing form errors JSON for manage page:", e);
        }
    }

    const submittedValuesDataScript = document.getElementById('django-submitted-values-data');
    if (submittedValuesDataScript && submittedValuesDataScript.textContent) {
        try {
            submittedValuesFromDjango = JSON.parse(submittedValuesDataScript.textContent || '{}');
            // console.log("Submitted values from Django:", submittedValuesFromDjango); // Debugging
        } catch (e) {
            console.error("Error parsing submitted values JSON for manage page:", e);
        }
    }


    if (addChapterFormContainer && formErrors.add_chapter_active_with_errors) {
        addChapterFormContainer.classList.remove('hidden-area');
        addChapterFormContainer.classList.add('visible-area');
        if (addChapterIcon) addChapterIcon.className = 'fas fa-times transition-transform duration-300 ease-in-out';
        if (addChapterText) addChapterText.textContent = 'Cancel Adding';
    }

    if (addChapterBtn && addChapterFormContainer) {
        addChapterBtn.addEventListener('click', function() {
            const isHidden = addChapterFormContainer.classList.contains('hidden-area');
            addChapterFormContainer.classList.toggle('hidden-area', !isHidden);
            addChapterFormContainer.classList.toggle('visible-area', isHidden);
            if (addChapterIcon) addChapterIcon.className = isHidden ? 'fas fa-times transition-transform duration-300 ease-in-out' : 'fas fa-plus transition-transform duration-300 ease-in-out';
            if (addChapterText) addChapterText.textContent = isHidden ? 'Cancel Adding' : 'Add New Chapter';
            if (isHidden) {
                addChapterFormContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        });
    }

    // --- TTS Voice Population and Preview Button Logic (scoped to a chapter form) ---
    function updateChapterPreviewButtonState(chapterFormElement, isForDocument = false) {
        const textInput = chapterFormElement.querySelector('.chapter-text-content-input-js, #new_chapter_text_content');
        const voiceSelect = chapterFormElement.querySelector('.chapter-tts-voice-select-js, #new_chapter_tts_voice');
        const previewBtn = chapterFormElement.querySelector('.generate-chapter-tts-preview-btn, .generate-new-chapter-tts-preview-btn');

        const docInput = chapterFormElement.querySelector('.chapter-document-input-js, .new-chapter-document-input-js');
        const docTtsVoiceSelect = chapterFormElement.querySelector('.chapter-doc-tts-voice-select-js, #new_chapter_doc_tts_voice');
        const docPreviewBtn = chapterFormElement.querySelector('.generate-document-tts-preview-btn, .generate-new-chapter-document-tts-preview-btn, .generate-edit-chapter-document-tts-preview-btn');

        const inputTypeHidden = chapterFormElement.querySelector('.chapter-input-type-hidden-js, .new-chapter-input-type-hidden-js, .edit-chapter-input-type-hidden-js');

        if (!inputTypeHidden) return;
        const currentInputType = inputTypeHidden.value;
        // console.log("updateChapterPreviewButtonState:", {currentInputType, isForDocument}); // Debugging

        // Logic for Text-to-Speech (manual text)
        if (currentInputType === 'tts' && previewBtn && textInput && voiceSelect) {
            const isLangFixedAndValid = currentAudiobookLanguageManage && currentAudiobookLanguageManage !== "";
            const voicesForLang = isLangFixedAndValid ? edgeTtsVoicesByLangManage[currentAudiobookLanguageManage] : null;
            const areVoicesAvailable = voicesForLang && voicesForLang.length > 0;
            // IMPORTANT: Check if voiceSelect.value is NOT "default" and NOT empty string
            const isVoiceSelected = voiceSelect.value && voiceSelect.value !== 'default' && voiceSelect.value !== "";
            const isTextValid = textInput.value.trim().length >= 10 && textInput.value.trim().length <= 5000;
            previewBtn.disabled = !(isLangFixedAndValid && areVoicesAvailable && isVoiceSelected && isTextValid);
            // console.log("TTS Button State:", {isLangFixedAndValid, areVoicesAvailable, isVoiceSelected, isTextValid, disabled: previewBtn.disabled}); // Debugging
        } else if (previewBtn) {
            previewBtn.disabled = true; // Disable if not in TTS mode
        }

        // Logic for Document-to-Speech
        if (currentInputType === 'document_tts' && docPreviewBtn && docInput && docTtsVoiceSelect) {
            const isLangFixedAndValid = currentAudiobookLanguageManage && currentAudiobookLanguageManage !== "";
            const voicesForLang = isLangFixedAndValid ? edgeTtsVoicesByLangManage[currentAudiobookLanguageManage] : null;
            const areVoicesAvailable = voicesForLang && voicesForLang.length > 0;
            // IMPORTANT: Check if docTtsVoiceSelect.value is NOT "default" and NOT empty string
            const isDocVoiceSelected = docTtsVoiceSelect.value && docTtsVoiceSelect.value !== 'default' && docTtsVoiceSelect.value !== "";
            const isDocFileSelected = docInput.files.length > 0;
            docPreviewBtn.disabled = !(isLangFixedAndValid && areVoicesAvailable && isDocVoiceSelected && isDocFileSelected);
            // console.log("Doc TTS Button State:", {isLangFixedAndValid, areVoicesAvailable, isDocVoiceSelected, isDocFileSelected, disabled: docPreviewBtn.disabled}); // Debugging
        } else if (docPreviewBtn) {
            docPreviewBtn.disabled = true; // Disable if not in Document TTS mode
        }
    }


    function populateChapterTtsVoices(chapterFormElement, audiobookLang, selectedTtsVoiceId, isForDocument = false) {
        const voiceSelectClass = isForDocument ? '.chapter-doc-tts-voice-select-js, #new_chapter_doc_tts_voice' : '.chapter-tts-voice-select-js, #new_chapter_tts_voice';
        const unavailableMsgClass = isForDocument ? '.chapter-doc-tts-unavailable-message-js, .new-chapter-doc-tts-unavailable-message-js' : '.chapter-tts-unavailable-message-js, .new-chapter-tts-unavailable-message-js';

        const ttsVoiceSelect = chapterFormElement.querySelector(voiceSelectClass);
        const unavailableMsg = chapterFormElement.querySelector(unavailableMsgClass);

        if (!ttsVoiceSelect || !unavailableMsg) {
            console.error("TTS voice select or unavailable message not found in chapter form for type:", isForDocument ? "document" : "manual", chapterFormElement);
            return;
        }

        ttsVoiceSelect.innerHTML = '';
        unavailableMsg.classList.add('hidden');
        ttsVoiceSelect.disabled = true;

        if (!audiobookLang) {
            const defaultOpt = document.createElement('option');
            defaultOpt.value = "";
            defaultOpt.textContent = "Audiobook Language Not Set";
            ttsVoiceSelect.appendChild(defaultOpt);
            // console.warn("populateChapterTtsVoices: Audiobook language is missing for this chapter form.");
            updateChapterPreviewButtonState(chapterFormElement, isForDocument);
            return;
        }

        const voicesForLang = edgeTtsVoicesByLangManage[audiobookLang];
        if (!voicesForLang) {
            const errOpt = document.createElement('option');
            errOpt.value = ""; errOpt.textContent = "TTS Error: Lang Config Issue";
            ttsVoiceSelect.appendChild(errOpt);
            console.error(`TTS voices not configured for language: ${audiobookLang}`);
            updateChapterPreviewButtonState(chapterFormElement, isForDocument);
            return;
        }

        if (voicesForLang.length === 0) {
            const noTtsOpt = document.createElement('option');
            noTtsOpt.value = ""; noTtsOpt.textContent = "TTS Not Available for " + audiobookLang;
            ttsVoiceSelect.appendChild(noTtsOpt);
            unavailableMsg.classList.remove('hidden');
        } else {
            ttsVoiceSelect.disabled = false;
            const defaultSelectOpt = document.createElement('option');
            defaultSelectOpt.value = "default"; defaultSelectOpt.textContent = "Select Narrator...";
            ttsVoiceSelect.appendChild(defaultSelectOpt);

            voicesForLang.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.id;
                option.textContent = voice.name;
                if (voice.id === selectedTtsVoiceId) {
                    option.selected = true;
                }
                ttsVoiceSelect.appendChild(option);
            });

            // Ensure a voice is actually selected if one was previously (e.g., on error re-render)
            // or default to "default" if no valid match
            if (selectedTtsVoiceId && voicesForLang.some(v => v.id === selectedTtsVoiceId)) {
                ttsVoiceSelect.value = selectedTtsVoiceId;
            } else {
                ttsVoiceSelect.value = "default";
            }
        }
        updateChapterPreviewButtonState(chapterFormElement, isForDocument);
    }


    // --- Helper Function for TTS Preview AJAX Call (Manual Text) ---
    async function generateChapterTtsPreview(params) {
        const {
            chapterForm,
            textContentInput, voiceSelect, playerContainer, player, messageEl,
            confirmUseBtn, generateBtn, generatedUrlInputForChapter,
            lockedDisplayForChapter, lockedFilenameSpanForChapter
        } = params;

        const text = textContentInput.value.trim();
        const voiceOptionId = voiceSelect.value;
        const btnTextEl = generateBtn.querySelector('.btn-text');
        const spinnerEl = generateBtn.querySelector('.spinner');

        messageEl.textContent = '';
        playerContainer.classList.add('hidden');
        player.src = '';
        if (confirmUseBtn) confirmUseBtn.classList.add('hidden');
        if (generatedUrlInputForChapter) generatedUrlInputForChapter.value = '';
        if (lockedDisplayForChapter) {
            lockedDisplayForChapter.classList.add('hidden-area');
            lockedDisplayForChapter.classList.remove('visible-area');
        }

        let isValid = true;
        if (!text) { messageEl.textContent = 'Text is required.'; isValid = false; }
        else if (text.length < 10) { messageEl.textContent = 'Text too short (min 10 chars).'; isValid = false; }
        else if (text.length > 5000) { messageEl.textContent = 'Text too long (max 5000 chars for preview).'; isValid = false; }
        if (voiceOptionId === 'default' || !voiceOptionId || (voiceSelect.options.length > 0 && voiceSelect.selectedIndex === 0 && voiceSelect.options[0].value === 'default')) {
            messageEl.textContent = (messageEl.textContent ? messageEl.textContent + ' ' : '') + 'Select a narrator voice.';
            isValid = false;
        }

        if (!isValid) {
            messageEl.className = messageEl.className.replace(/text-(green|indigo|blue)-[0-9a-zA-Z]+/g, 'text-red-600');
            return;
        }

        generateBtn.disabled = true;
        if(btnTextEl) btnTextEl.classList.add('hidden');
        if(spinnerEl) spinnerEl.classList.remove('hidden');
        messageEl.textContent = 'Generating preview...';
        messageEl.className = messageEl.className.replace(/text-(red|green)-[0-9a-zA-Z]+/g, 'text-indigo-600');

        const formData = new FormData();
        formData.append('text_content', text);
        formData.append('tts_voice_id', voiceOptionId);
        formData.append('audiobook_language', currentAudiobookLanguageManage);
        formData.append('csrfmiddlewaretoken', csrfToken);

        try {
            const response = await fetch(generateTtsPreviewUrl, { method: 'POST', body: formData, headers: {'X-CSRFToken': csrfToken} });
            const data = await response.json();

            if (response.ok && data.status === 'success') {
                player.src = data.audio_url;
                playerContainer.classList.remove('hidden');
                messageEl.textContent = `Preview ready! (${data.filename || 'Generated Audio'})`;
                messageEl.className = messageEl.className.replace(/text-(red|indigo)-[0-9a-zA-Z]+/g, 'text-green-600');
                if (confirmUseBtn) {
                    confirmUseBtn.classList.remove('hidden');
                    confirmUseBtn.dataset.generatedUrl = data.audio_url;
                    confirmUseBtn.dataset.generatedVoiceId = data.voice_id_used;
                    confirmUseBtn.dataset.generatedFilename = data.filename || "Generated_Audio.mp3";
                }
            } else {
                messageEl.textContent = `Error: ${data.message || 'Unknown TTS error.'}`;
                messageEl.className = messageEl.className.replace(/text-(green|indigo)-[0-9a-zA-Z]+/g, 'text-red-600');
            }
        } catch (error) {
            messageEl.textContent = 'Network error during TTS preview.';
            messageEl.className = messageEl.className.replace(/text-(green|indigo)-[0-9a-zA-Z]+/g, 'text-red-600');
            console.error('Chapter TTS Preview Fetch Error:', error);
        } finally {
            generateBtn.disabled = false;
            if(btnTextEl) btnTextEl.classList.remove('hidden');
            if(spinnerEl) spinnerEl.classList.add('hidden');
            updateChapterPreviewButtonState(chapterForm, false); // isForDocument = false
        }
    }

    // --- Helper Function for Document TTS Preview AJAX Call ---
    async function generateDocumentTtsPreview(params) {
        const {
            chapterForm,
            documentInput, docVoiceSelect,
            playerContainer, player, messageEl,
            confirmUseBtn, generateBtn, generatedDocUrlInput,
            lockedDisplay, lockedFilenameSpan
        } = params;

        const docFile = documentInput.files[0];
        const voiceOptionId = docVoiceSelect.value;
        const btnTextEl = generateBtn.querySelector('.btn-text');
        const spinnerEl = generateBtn.querySelector('.spinner');

        messageEl.textContent = '';
        playerContainer.classList.add('hidden');
        player.src = '';
        if (confirmUseBtn) confirmUseBtn.classList.add('hidden');
        if (generatedDocUrlInput) generatedDocUrlInput.value = '';
        if (lockedDisplay) {
            lockedDisplay.classList.add('hidden-area');
            lockedDisplay.classList.remove('visible-area');
        }

        let isValid = true;
        if (!docFile) { messageEl.textContent = 'Please select a document file.'; isValid = false; }
        // FIX: Check if docVoiceSelect.value is actually selected and not "default" or empty
        if (voiceOptionId === 'default' || !voiceOptionId || (docVoiceSelect.options.length > 0 && docVoiceSelect.selectedIndex === 0 && docVoiceSelect.options[0].value === 'default')) {
            messageEl.textContent = (messageEl.textContent ? messageEl.textContent + ' ' : '') + 'Select a narrator voice.';
            isValid = false;
        }
        if (docFile) {
            const maxSize = 10 * 1024 * 1024; // 10MB
            const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
            const allowedExtensions = ['.pdf', '.doc', '.docx'];
            const fileExtension = docFile.name.substring(docFile.name.lastIndexOf('.')).toLowerCase();
            if (docFile.size > maxSize) { messageEl.textContent = 'Document too large (Max 10MB).'; isValid = false;}
            if (!allowedTypes.includes(docFile.type) && !allowedExtensions.includes(fileExtension)) { messageEl.textContent = 'Invalid document type (PDF, DOC, DOCX).'; isValid = false;}
        }

        if (!isValid) {
            messageEl.className = messageEl.className.replace(/text-(green|indigo|blue)-[0-9a-zA-Z]+/g, 'text-red-600');
            return;
        }

        generateBtn.disabled = true;
        if(btnTextEl) btnTextEl.classList.add('hidden');
        if(spinnerEl) spinnerEl.classList.remove('hidden');
        messageEl.textContent = 'Processing document & generating preview...';
        messageEl.className = messageEl.className.replace(/text-(red|green)-[0-9a-zA-Z]+/g, 'text-indigo-600');

        const formData = new FormData();
        formData.append('document_file', docFile);
        formData.append('tts_voice_id', voiceOptionId);
        // FIX: The view expects 'language' from the form, not 'audiobook_language'
        formData.append('language', currentAudiobookLanguageManage);
        formData.append('csrfmiddlewaretoken', csrfToken);

        try {
            const response = await fetch(generateDocumentTtsPreviewUrl, { method: 'POST', body: formData, headers: {'X-CSRFToken': csrfToken} });
            const data = await response.json();

            if (response.ok && data.status === 'success') {
                player.src = data.audio_url;
                playerContainer.classList.remove('hidden');
                messageEl.textContent = `Preview ready! (From: ${data.source_filename || 'document'})`;
                messageEl.className = messageEl.className.replace(/text-(red|indigo)-[0-9a-zA-Z]+/g, 'text-green-600');
                if (confirmUseBtn) {
                    confirmUseBtn.classList.remove('hidden');
                    confirmUseBtn.dataset.generatedUrl = data.audio_url;
                    confirmUseBtn.dataset.generatedVoiceId = data.voice_id_used;
                    confirmUseBtn.dataset.generatedFilename = data.filename || "Generated_Audio_from_Doc.mp3";
                    confirmUseBtn.dataset.sourceDocumentName = data.source_filename || docFile.name;
                }
            } else {
                messageEl.textContent = `Error: ${data.message || 'Unknown document TTS error.'}`;
                messageEl.className = messageEl.className.replace(/text-(green|indigo)-[0-9a-zA-Z]+/g, 'text-red-600');
            }
        } catch (error) {
            messageEl.textContent = 'Network error during document TTS preview.';
            messageEl.className = messageEl.className.replace(/text-(green|indigo)-[0-9a-zA-Z]+/g, 'text-red-600');
            console.error('Document TTS Preview Fetch Error:', error);
        } finally {
            generateBtn.disabled = false;
            if(btnTextEl) btnTextEl.classList.remove('hidden');
            if(spinnerEl) spinnerEl.classList.add('hidden');
            updateChapterPreviewButtonState(chapterForm, true); // isForDocument = true
        }
    }


    // --- Initialize Controls for "Add New Chapter" Form ---
    const addChapterForm = document.getElementById('addChapterForm');
    if (addChapterForm) {
        const inputTypeHidden = addChapterForm.querySelector('.new-chapter-input-type-hidden-js');
        const fileUploadControls = addChapterForm.querySelector('.new-chapter-file-upload-controls');
        const ttsGenerationControls = addChapterForm.querySelector('.new-chapter-tts-generation-controls');
        const documentTtsControls = addChapterForm.querySelector('.new-chapter-document-tts-controls');
        const lockedDisplay = addChapterForm.querySelector('.new-chapter-locked-generated-audio-display');
        const generatedTtsUrlInput = addChapterForm.querySelector('.new-chapter-generated-tts-url-input-js');
        const generatedDocTtsUrlInput = addChapterForm.querySelector('.new-chapter-generated-document-tts-url-input-js');
        const lockedFilenameSpan = addChapterForm.querySelector('.new-chapter-generated-tts-filename-js');

        const audioInput = fileUploadControls?.querySelector('#new_chapter_audio');
        const textInput = ttsGenerationControls?.querySelector('#new_chapter_text_content');
        const voiceSelect = ttsGenerationControls?.querySelector('#new_chapter_tts_voice');
        const documentInput = documentTtsControls?.querySelector('#new_chapter_document_file');
        const docVoiceSelect = documentTtsControls?.querySelector('#new_chapter_doc_tts_voice');
        const documentFileNameSpan = documentTtsControls?.querySelector('.new-chapter-document-filename-js');


        function toggleAddNewChapterFields(type) {
            if (inputTypeHidden) inputTypeHidden.value = type;
            fileUploadControls?.classList.add('hidden-area'); fileUploadControls?.classList.remove('visible-area');
            ttsGenerationControls?.classList.add('hidden-area'); ttsGenerationControls?.classList.remove('visible-area');
            documentTtsControls?.classList.add('hidden-area'); documentTtsControls?.classList.remove('visible-area');
            lockedDisplay?.classList.add('hidden-area'); lockedDisplay?.classList.remove('visible-area');

            // Reset required attributes
            if(audioInput) audioInput.required = false;
            if(textInput) textInput.required = false;
            // voiceSelect is dynamically populated, so don't set required here directly.
            // Required check is done in JS validation before sending to server.
            if(documentInput) documentInput.required = false;
            // docVoiceSelect is dynamically populated.

            if (type === 'file') {
                fileUploadControls?.classList.remove('hidden-area'); fileUploadControls?.classList.add('visible-area');
                if(audioInput) audioInput.required = true;
            } else if (type === 'tts') {
                ttsGenerationControls?.classList.remove('hidden-area'); ttsGenerationControls?.classList.add('visible-area');
                lockedDisplay?.classList.add('hidden-area'); lockedDisplay?.classList.remove('visible-area');
                if(textInput) textInput.required = true;
                // Voice select for TTS is handled by populateChapterTtsVoices & updateChapterPreviewButtonState
                if (inputTypeHidden) inputTypeHidden.value = 'tts';
            } else if (type === 'document_tts') {
                documentTtsControls?.classList.remove('hidden-area'); documentTtsControls?.classList.add('visible-area');
                if(documentInput) documentInput.required = true;
                // Voice select for document TTS is handled by populateChapterTtsVoices & updateChapterPreviewButtonState
                if (inputTypeHidden) inputTypeHidden.value = 'document_tts';
            } else if (type === 'generated_tts' || type === 'generated_document_tts') {
                lockedDisplay?.classList.remove('hidden-area'); lockedDisplay?.classList.add('visible-area');
                ttsGenerationControls?.classList.add('hidden-area'); ttsGenerationControls?.classList.remove('visible-area');
                fileUploadControls?.classList.add('hidden-area'); fileUploadControls?.classList.remove('visible-area');
                documentTtsControls?.classList.add('hidden-area'); documentTtsControls?.classList.remove('visible-area');
                if (inputTypeHidden) inputTypeHidden.value = type;
            }
            updateChapterPreviewButtonState(addChapterForm, type === 'document_tts');
        }


        addChapterForm.querySelectorAll('.new-chapter-input-type-toggle-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const type = this.dataset.type;
                addChapterForm.querySelectorAll('.new-chapter-input-type-toggle-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                if ((type === 'file' || type === 'document_tts') && generatedTtsUrlInput && generatedTtsUrlInput.value) {
                    generatedTtsUrlInput.value = '';
                    if(lockedFilenameSpan) lockedFilenameSpan.textContent = "Generated Audio";
                    const confirmBtnAdd = addChapterForm.querySelector('.confirm-use-new-chapter-generated-audio-btn');
                    if(confirmBtnAdd) confirmBtnAdd.classList.add('hidden');
                    const playerContainerAdd = addChapterForm.querySelector('.new-chapter-tts-preview-player-container');
                    if(playerContainerAdd) playerContainerAdd.classList.add('hidden');
                    const messageElAdd = addChapterForm.querySelector('.new-chapter-tts-message');
                    if(messageElAdd) messageElAdd.textContent = '';
                }
                if ((type === 'file' || type === 'tts') && generatedDocTtsUrlInput && generatedDocTtsUrlInput.value) {
                    generatedDocTtsUrlInput.value = '';
                    const confirmDocBtnAdd = addChapterForm.querySelector('.confirm-use-new-chapter-document-audio-btn');
                    if(confirmDocBtnAdd) confirmDocBtnAdd.classList.add('hidden');
                    const docPlayerContainerAdd = addChapterForm.querySelector('.new-chapter-document-tts-preview-player-container');
                    if(docPlayerContainerAdd) docPlayerContainerAdd.classList.add('hidden');
                    const docMessageElAdd = addChapterForm.querySelector('.new-chapter-document-tts-message');
                    if(docMessageElAdd) docMessageElAdd.textContent = '';
                }
                toggleAddNewChapterFields(type);
            });
        });

        // Use submittedValuesFromDjango for initial state of "Add New Chapter" form
        const initialNewChapterTypeFromDjango = submittedValuesFromDjango.new_chapter_input_type_hidden || 'file';
        let uiInitialType = initialNewChapterTypeFromDjango;
        if (initialNewChapterTypeFromDjango === 'generated_tts') uiInitialType = 'tts';
        else if (initialNewChapterTypeFromDjango === 'generated_document_tts') uiInitialType = 'document_tts';

        addChapterForm.querySelectorAll('.new-chapter-input-type-toggle-btn').forEach(btn => {
            if (btn.dataset.type === uiInitialType) btn.classList.add('active');
            else btn.classList.remove('active');
        });
        toggleAddNewChapterFields(initialNewChapterTypeFromDjango);


        // Event listener for manual TTS preview button in "Add New Chapter"
        const generateManualTtsBtn = addChapterForm.querySelector('.generate-new-chapter-tts-preview-btn');
        const manualTtsPlayerContainer = addChapterForm.querySelector('.new-chapter-tts-preview-player-container');
        const manualTtsPlayer = manualTtsPlayerContainer?.querySelector('.chapter-tts-preview-player');
        const manualTtsMessageEl = addChapterForm.querySelector('.new-chapter-tts-message');
        const confirmUseManualTtsBtn = addChapterForm.querySelector('.confirm-use-new-chapter-generated-audio-btn');

        if (generateManualTtsBtn && textInput && voiceSelect && manualTtsPlayerContainer && manualTtsPlayer && manualTtsMessageEl && confirmUseManualTtsBtn) {
            generateManualTtsBtn.addEventListener('click', function() {
                generateChapterTtsPreview({
                    chapterForm: addChapterForm, textContentInput: textInput, voiceSelect,
                    playerContainer: manualTtsPlayerContainer, player: manualTtsPlayer, messageEl: manualTtsMessageEl,
                    confirmUseBtn: confirmUseManualTtsBtn, generateBtn: this,
                    generatedUrlInputForChapter: generatedTtsUrlInput,
                    lockedDisplayForChapter: lockedDisplay, lockedFilenameSpanForChapter: lockedFilenameSpan,
                });
            });
        }
        if (confirmUseManualTtsBtn && generatedTtsUrlInput && lockedDisplay && lockedFilenameSpan && voiceSelect && inputTypeHidden && manualTtsMessageEl) {
            confirmUseManualTtsBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const filenameUsed = this.dataset.generatedFilename;
                if (urlToUse) {
                    generatedTtsUrlInput.value = urlToUse;
                    if(generatedDocTtsUrlInput) generatedDocTtsUrlInput.value = '';
                    let displayFilenameText = `Generated Audio (from Text)`;
                    const voiceDetail = ALL_EDGE_TTS_VOICES_MAP_MANAGE[voiceUsed];
                    if (voiceDetail) displayFilenameText += ` (Voice: ${voiceDetail.name})`;
                    lockedFilenameSpan.textContent = displayFilenameText;
                    voiceSelect.value = voiceUsed;
                    manualTtsMessageEl.textContent = 'Audio selected for this new chapter!';
                    manualTtsMessageEl.className = 'new-chapter-tts-message text-xs my-1.5 min-h-[16px] text-green-700 font-semibold';
                    this.classList.add('hidden');
                    if(manualTtsPlayerContainer) manualTtsPlayerContainer.classList.add('hidden');
                    toggleAddNewChapterFields('generated_tts');
                }
            });
        }

        // Event listener for Document TTS preview button in "Add New Chapter"
        const generateDocTtsBtn = addChapterForm.querySelector('.generate-new-chapter-document-tts-preview-btn');
        const docTtsPlayerContainer = addChapterForm.querySelector('.new-chapter-document-tts-preview-player-container');
        const docTtsPlayer = docTtsPlayerContainer?.querySelector('.document-tts-preview-player');
        const docTtsMessageEl = addChapterForm.querySelector('.new-chapter-document-tts-message');
        const confirmUseDocTtsBtn = addChapterForm.querySelector('.confirm-use-new-chapter-document-audio-btn');

        if (generateDocTtsBtn && documentInput && docVoiceSelect && docTtsPlayerContainer && docTtsPlayer && docTtsMessageEl && confirmUseDocTtsBtn) {
            generateDocTtsBtn.addEventListener('click', function() {
                generateDocumentTtsPreview({
                    chapterForm: addChapterForm, documentInput, docVoiceSelect,
                    playerContainer: docTtsPlayerContainer, player: docTtsPlayer, messageEl: docTtsMessageEl,
                    confirmUseBtn: confirmUseDocTtsBtn, generateBtn: this,
                    generatedDocUrlInput: generatedDocTtsUrlInput,
                    lockedDisplay: lockedDisplay,
                    lockedFilenameSpan: lockedFilenameSpan,
                });
            });
        }
        if (confirmUseDocTtsBtn && generatedDocTtsUrlInput && lockedDisplay && lockedFilenameSpan && docVoiceSelect && inputTypeHidden && docTtsMessageEl) {
            confirmUseDocTtsBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const sourceDocName = this.dataset.sourceDocumentName || "document";
                if (urlToUse) {
                    generatedDocTtsUrlInput.value = urlToUse;
                    if(generatedTtsUrlInput) generatedTtsUrlInput.value = '';

                    let displayFilenameText = `Generated Audio (from Document: ${sourceDocName})`;
                    const voiceDetail = ALL_EDGE_TTS_VOICES_MAP_MANAGE[voiceUsed];
                    if (voiceDetail) displayFilenameText += ` (Voice: ${voiceDetail.name})`;
                    lockedFilenameSpan.textContent = displayFilenameText;

                    docVoiceSelect.value = voiceUsed;
                    docTtsMessageEl.textContent = 'Document audio selected for this new chapter!';
                    docTtsMessageEl.className = 'new-chapter-document-tts-message text-xs my-1.5 min-h-[16px] text-green-700 font-semibold';
                    this.classList.add('hidden');
                    if(docTtsPlayerContainer) docTtsPlayerContainer.classList.add('hidden');
                    toggleAddNewChapterFields('generated_document_tts');
                }
            });
        }


        // Initial population for add new chapter form using the fixed audiobook language
        if(voiceSelect) {
            const submittedNewChapterVoice = submittedValuesFromDjango.new_chapter_tts_voice;
            populateChapterTtsVoices(addChapterForm, currentAudiobookLanguageManage, submittedNewChapterVoice, false);
        }
        if(docVoiceSelect) {
            const submittedNewDocChapterVoice = submittedValuesFromDjango.new_chapter_doc_tts_voice;
            populateChapterTtsVoices(addChapterForm, currentAudiobookLanguageManage, submittedNewDocChapterVoice, true);
        }

        if (documentInput && documentFileNameSpan) {
            documentInput.addEventListener('change', function(e) {
                const docErrorEl = addChapterForm.querySelector('.new-chapter-document-tts-controls .chapter-document-error-js');
                if (docErrorEl) docErrorEl.textContent = '';
                if (e.target.files.length > 0) {
                    const file = e.target.files[0];
                    const maxSize = 10 * 1024 * 1024;
                    const allowedExtensions = ['.pdf', '.doc', '.docx'];
                    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
                    if (file.size > maxSize) {
                        if(docErrorEl) docErrorEl.textContent = `File too large (Max 10MB).`;
                        e.target.value = ''; documentFileNameSpan.textContent = 'No document chosen (too large)';
                        updateChapterPreviewButtonState(addChapterForm, true); return;
                    }
                    if (!allowedExtensions.includes(fileExtension)) { // Simplified check
                        if(docErrorEl) docErrorEl.textContent = "Invalid type (PDF, DOC, DOCX).";
                        e.target.value = ''; documentFileNameSpan.textContent = 'No document chosen (invalid type)';
                        updateChapterPreviewButtonState(addChapterForm, true); return;
                    }
                    documentFileNameSpan.textContent = file.name;
                } else {
                    documentFileNameSpan.textContent = 'No document chosen';
                }
                updateChapterPreviewButtonState(addChapterForm, true);
            });
        }
           if(textInput){ // For manual TTS in Add New Chapter
               textInput.addEventListener('input', () => updateChapterPreviewButtonState(addChapterForm, false));
        }
           if(voiceSelect){ // For manual TTS in Add New Chapter
               voiceSelect.addEventListener('change', () => updateChapterPreviewButtonState(addChapterForm, false));
        }
           if(docVoiceSelect) { // For document TTS in Add New Chapter
               docVoiceSelect.addEventListener('change', () => updateChapterPreviewButtonState(addChapterForm, true));
        }
    }

    // --- Initialize Controls for EACH "Edit Existing Chapter" Form ---
    document.querySelectorAll('.edit-chapter-form-js').forEach(editForm => {
        const chapterId = editForm.dataset.chapterId;
        const chapterCard = editForm.closest('.chapter-card');

        const inputTypeHidden = editForm.querySelector(`.edit-chapter-input-type-hidden-js`);
        const fileUploadControls = editForm.querySelector(`.edit-chapter-file-upload-controls`);
        const ttsGenerationControls = editForm.querySelector(`.edit-chapter-tts-generation-controls`);
        const documentTtsControls = editForm.querySelector('.edit-chapter-document-tts-controls');
        const lockedDisplay = editForm.querySelector('.locked-generated-audio-display');
        const generatedTtsUrlInput = editForm.querySelector(`.edit-chapter-generated-tts-url-input-js`);
        const generatedDocTtsUrlInput = editForm.querySelector(`.edit-chapter-generated-document-tts-url-input-js`);
        const lockedFilenameSpan = lockedDisplay?.querySelector('.chapter-generated-tts-filename-js');

        const audioInput = fileUploadControls?.querySelector(`#chapter_audio_edit_${chapterId}`);
        const textInput = ttsGenerationControls?.querySelector(`#chapter_text_content_edit_${chapterId}`);
        const voiceSelect = ttsGenerationControls?.querySelector(`#chapter_tts_voice_edit_${chapterId}`);
        const fileNameSpan = fileUploadControls?.querySelector('.chapter-filename-js');

        const documentInput = documentTtsControls?.querySelector(`#chapter_document_edit_${chapterId}`);
        const docVoiceSelect = documentTtsControls?.querySelector(`#chapter_doc_tts_voice_edit_${chapterId}`);
        const documentFileNameSpan = documentTtsControls?.querySelector('.chapter-document-filename-js');


        function toggleEditChapterFields(type) {
            if (inputTypeHidden) inputTypeHidden.value = type;
            fileUploadControls?.classList.add('hidden-area'); fileUploadControls?.classList.remove('visible-area');
            ttsGenerationControls?.classList.add('hidden-area'); ttsGenerationControls?.classList.remove('visible-area');
            documentTtsControls?.classList.add('hidden-area'); documentTtsControls?.classList.remove('visible-area');
            lockedDisplay?.classList.add('hidden-area'); lockedDisplay?.classList.remove('visible-area');

            // Reset required attributes
            if(audioInput) audioInput.required = false;
            if(textInput) textInput.required = false;
            // voiceSelect is dynamically populated, so don't set required here directly.
            // Required check is done in JS validation before sending to server.
            if(documentInput) documentInput.required = false;
            // docVoiceSelect is dynamically populated.


            if (type === 'file') {
                fileUploadControls?.classList.remove('hidden-area'); fileUploadControls?.classList.add('visible-area');
            } else if (type === 'tts') {
                ttsGenerationControls?.classList.remove('hidden-area'); ttsGenerationControls?.classList.add('visible-area');
                lockedDisplay?.classList.add('hidden-area'); lockedDisplay?.classList.remove('visible-area');
                if(textInput) textInput.required = true;
                // Voice select for TTS is handled by populateChapterTtsVoices & updateChapterPreviewButtonState
                if (inputTypeHidden) inputTypeHidden.value = 'tts';
            } else if (type === 'document_tts') {
                documentTtsControls?.classList.remove('hidden-area'); documentTtsControls?.classList.add('visible-area');
                if(documentInput) documentInput.required = true;
                // Voice select for document TTS is handled by populateChapterTtsVoices & updateChapterPreviewButtonState
                if (inputTypeHidden) inputTypeHidden.value = 'document_tts';
            } else if (type === 'generated_tts' || type === 'generated_document_tts') {
                lockedDisplay?.classList.remove('hidden-area'); lockedDisplay?.classList.add('visible-area');
                ttsGenerationControls?.classList.add('hidden-area'); ttsGenerationControls?.classList.remove('visible-area');
                fileUploadControls?.classList.add('hidden-area'); fileUploadControls?.classList.remove('visible-area');
                documentTtsControls?.classList.add('hidden-area'); documentTtsControls?.classList.remove('visible-area');
                if (inputTypeHidden) inputTypeHidden.value = type;
            }
               updateChapterPreviewButtonState(editForm, type === 'document_tts' || type === 'generated_document_tts');
        }

        editForm.querySelectorAll('.edit-chapter-input-type-toggle-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const type = this.dataset.type;
                editForm.querySelectorAll('.edit-chapter-input-type-toggle-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                   if ((type === 'file' || type === 'document_tts') && generatedTtsUrlInput && generatedTtsUrlInput.value) {
                    generatedTtsUrlInput.value = '';
                    if(lockedFilenameSpan) lockedFilenameSpan.textContent = "Generated Audio";
                    const confirmBtnEdit = editForm.querySelector('.confirm-use-generated-audio-btn');
                    if(confirmBtnEdit) confirmBtnEdit.classList.add('hidden');
                    const playerContainerEdit = editForm.querySelector('.chapter-tts-preview-player-container');
                    if(playerContainerEdit) playerContainerEdit.classList.add('hidden');
                    const messageElEdit = editForm.querySelector('.chapter-tts-message');
                    if(messageElEdit) messageElEdit.textContent = '';
                }
                if ((type === 'file' || type === 'tts') && generatedDocTtsUrlInput && generatedDocTtsUrlInput.value) {
                    generatedDocTtsUrlInput.value = '';
                    const confirmDocBtnEdit = editForm.querySelector('.confirm-use-edit-chapter-document-audio-btn');
                    if(confirmDocBtnEdit) confirmDocBtnEdit.classList.add('hidden');
                    const docPlayerContainerEdit = editForm.querySelector('.edit-chapter-document-tts-preview-player-container');
                    if(docPlayerContainerEdit) docPlayerContainerEdit.classList.add('hidden');
                    const docMessageElEdit = editForm.querySelector('.edit-chapter-document-tts-message');
                    if(docMessageElEdit) docMessageElEdit.textContent = '';
                }
                toggleEditChapterFields(type);
            });
        });

        const initialEditTypeRaw = inputTypeHidden ? inputTypeHidden.value : 'file';
        let initialEditTypeUI = initialEditTypeRaw;
        if (initialEditTypeRaw === 'generated_tts') {
            initialEditTypeUI = 'tts';
        } else if (initialEditTypeRaw === 'generated_document_tts') {
            initialEditTypeUI = 'document_tts';
        }

        editForm.querySelectorAll('.edit-chapter-input-type-toggle-btn').forEach(btn => {
            if (btn.dataset.type === initialEditTypeUI) btn.classList.add('active');
            else btn.classList.remove('active');
        });
        toggleEditChapterFields(initialEditTypeRaw);

        // Event listener for manual TTS preview button in "Edit Chapter"
        const generateManualTtsBtn = editForm.querySelector('.generate-chapter-tts-preview-btn');
        const manualTtsPlayerContainer = editForm.querySelector('.chapter-tts-preview-player-container');
        const manualTtsPlayer = manualTtsPlayerContainer?.querySelector('.chapter-tts-preview-player');
        const manualTtsMessageEl = editForm.querySelector('.chapter-tts-message');
        const confirmUseManualTtsBtn = editForm.querySelector('.confirm-use-generated-audio-btn');

        if (generateManualTtsBtn && textInput && voiceSelect && manualTtsPlayerContainer && manualTtsPlayer && manualTtsMessageEl && confirmUseManualTtsBtn) {
            generateManualTtsBtn.addEventListener('click', function() {
                generateChapterTtsPreview({
                    chapterForm: editForm, textContentInput: textInput, voiceSelect,
                    playerContainer: manualTtsPlayerContainer, player: manualTtsPlayer, messageEl: manualTtsMessageEl,
                    confirmUseBtn: confirmUseManualTtsBtn, generateBtn: this,
                    generatedUrlInputForChapter: generatedTtsUrlInput,
                    lockedDisplayForChapter: lockedDisplay, lockedFilenameSpanForChapter: lockedFilenameSpan,
                });
            });
        }
        if (confirmUseManualTtsBtn && generatedTtsUrlInput && lockedDisplay && lockedFilenameSpan && voiceSelect && inputTypeHidden && manualTtsMessageEl) {
            confirmUseManualTtsBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const filenameUsed = this.dataset.generatedFilename;
                if (urlToUse) {
                    generatedTtsUrlInput.value = urlToUse;
                    if(generatedDocTtsUrlInput) generatedDocTtsUrlInput.value = '';
                    let displayFilenameText = filenameUsed;
                    const voiceDetail = ALL_EDGE_TTS_VOICES_MAP_MANAGE[voiceUsed];
                    if (voiceDetail) displayFilenameText += ` (Voice: ${voiceDetail.name})`;
                    lockedFilenameSpan.textContent = `(from Text): ${displayFilenameText}`;
                    voiceSelect.value = voiceUsed;
                    manualTtsMessageEl.textContent = 'Previewed audio selected for this chapter.';
                    manualTtsMessageEl.className = 'chapter-tts-message text-xs my-1.5 min-h-[16px] text-green-700 font-semibold';
                    this.classList.add('hidden');
                    if(manualTtsPlayerContainer) manualTtsPlayerContainer.classList.add('hidden');
                    toggleEditChapterFields('generated_tts');
                }
            });
        }

        // Event listener for Document TTS preview button in "Edit Chapter"
        const generateDocTtsBtn = editForm.querySelector('.generate-edit-chapter-document-tts-preview-btn');
        const docTtsPlayerContainer = editForm.querySelector('.edit-chapter-document-tts-preview-player-container');
        const docTtsPlayer = docTtsPlayerContainer?.querySelector('.document-tts-preview-player');
        const docTtsMessageEl = editForm.querySelector('.edit-chapter-document-tts-message');
        const confirmUseDocTtsBtn = editForm.querySelector('.confirm-use-edit-chapter-document-audio-btn');

        if (generateDocTtsBtn && documentInput && docVoiceSelect && docTtsPlayerContainer && docTtsPlayer && docTtsMessageEl && confirmUseDocTtsBtn) {
            generateDocTtsBtn.addEventListener('click', function() {
                generateDocumentTtsPreview({
                    chapterForm: editForm, documentInput, docVoiceSelect,
                    playerContainer: docTtsPlayerContainer, player: docTtsPlayer, messageEl: docTtsMessageEl,
                    confirmUseBtn: confirmUseDocTtsBtn, generateBtn: this,
                    generatedDocUrlInput: generatedDocTtsUrlInput,
                    lockedDisplay: lockedDisplay,
                    lockedFilenameSpan: lockedFilenameSpan,
                });
            });
        }
        if (confirmUseDocTtsBtn && generatedDocTtsUrlInput && lockedDisplay && lockedFilenameSpan && docVoiceSelect && inputTypeHidden && docTtsMessageEl) {
            confirmUseDocTtsBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const sourceDocName = this.dataset.sourceDocumentName || "document";
                if (urlToUse) {
                    generatedDocTtsUrlInput.value = urlToUse;
                    if(generatedTtsUrlInput) generatedTtsUrlInput.value = '';

                    let displayFilenameText = `Audio from: ${sourceDocName}`;
                    const voiceDetail = ALL_EDGE_TTS_VOICES_MAP_MANAGE[voiceUsed];
                    if (voiceDetail) displayFilenameText += ` (Voice: ${voiceDetail.name})`;
                    lockedFilenameSpan.textContent = displayFilenameText;

                    docVoiceSelect.value = voiceUsed;
                    docTtsMessageEl.textContent = 'Document audio selected for this chapter!';
                    docTtsMessageEl.className = 'edit-chapter-document-tts-message text-xs my-1.5 min-h-[16px] text-green-700 font-semibold';
                    this.classList.add('hidden');
                    if(docTtsPlayerContainer) docTtsPlayerContainer.classList.add('hidden');
                    toggleEditChapterFields('generated_document_tts');
                }
            });
        }


        if (audioInput && fileNameSpan) {
            audioInput.addEventListener('change', function(e) {
                const audioErrorEl = editForm.querySelector('.chapter-audio-error-js');
                if(audioErrorEl) audioErrorEl.textContent = '';

                if (e.target.files.length > 0) {
                    const file = e.target.files[0];
                    const maxAudioSize = 50 * 1024 * 1024;
                    const allowedAudioTypes = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a'];
                    if (file.size > maxAudioSize) {
                        if(audioErrorEl) audioErrorEl.textContent = `File too large (Max 50MB).`;
                        e.target.value = ''; fileNameSpan.textContent = 'Choose new audio file... (too large)'; return;
                    }
                    if (!allowedAudioTypes.includes(file.type)) {
                        if(audioErrorEl) audioErrorEl.textContent = "Invalid audio file type.";
                        e.target.value = ''; fileNameSpan.textContent = 'Choose new audio file... (invalid type)'; return;
                    }
                    fileNameSpan.textContent = file.name;
                } else { fileNameSpan.textContent = 'Choose new audio file...'; }
            });
        }
        // Event listener for document file input in "Edit Chapter" form
        if (documentInput && documentFileNameSpan) {
            documentInput.addEventListener('change', function(e) {
                const docErrorEl = editForm.querySelector('.edit-chapter-document-tts-controls .chapter-document-error-js');
                if (docErrorEl) docErrorEl.textContent = '';

                if (e.target.files.length > 0) {
                    const file = e.target.files[0];
                    const maxSize = 10 * 1024 * 1024; // 10MB
                    const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
                    const allowedExtensions = ['.pdf', '.doc', '.docx'];
                    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

                    if (file.size > maxSize) {
                        if(docErrorEl) docErrorEl.textContent = `File too large (Max 10MB).`;
                        e.target.value = ''; documentFileNameSpan.textContent = 'No document chosen (too large)';
                        updateChapterPreviewButtonState(editForm, true); return;
                    }
                    if (!allowedTypes.includes(file.type) && !allowedExtensions.includes(fileExtension)) {
                        if(docErrorEl) docErrorEl.textContent = "Invalid document type (PDF, DOC, DOCX).";
                        e.target.value = ''; documentFileNameSpan.textContent = 'No document chosen (invalid type)';
                        updateChapterPreviewButtonState(editForm, true); return;
                    }
                    documentFileNameSpan.textContent = file.name;
                } else {
                    const existingDocName = chapterCard.dataset.existingDocumentFilename;
                    documentFileNameSpan.textContent = existingDocName || 'No document chosen';
                }
                   updateChapterPreviewButtonState(editForm, true); // Update button state on file change
            });
        }
           if(textInput){ // For manual TTS in Edit Chapter
               textInput.addEventListener('input', () => updateChapterPreviewButtonState(editForm, false));
        }
           if(voiceSelect){ // For manual TTS in Edit Chapter
               voiceSelect.addEventListener('change', () => updateChapterPreviewButtonState(editForm, false));
        }
           if(docVoiceSelect) { // For document TTS in Edit form
               docVoiceSelect.addEventListener('change', () => updateChapterPreviewButtonState(editForm, true));
        }


        // Initial population for existing chapter edit forms using the fixed audiobook language
        if(voiceSelect) { // For manual TTS
            const originalVoiceIdField = editForm.querySelector(`input[name="chapter_tts_voice_id_orig_${chapterId}"]`);
            const originalVoiceId = originalVoiceIdField ? originalVoiceIdField.value : voiceSelect.value;
            populateChapterTtsVoices(editForm, currentAudiobookLanguageManage, originalVoiceId, false);
        }
        if(docVoiceSelect) { // For document TTS
            const existingDocTTSVoiceId = chapterCard.dataset.existingDocTtsVoiceId;
            populateChapterTtsVoices(editForm, currentAudiobookLanguageManage, existingDocTTSVoiceId || docVoiceSelect.value, true);
        }
    });


    // --- Django Messages Handling ---
    const djangoMessagesJsonScript = document.getElementById('django_messages_json');
    if (djangoMessagesJsonScript && typeof Swal !== 'undefined' && djangoMessagesJsonScript.textContent) {
        try {
            // Ensure messagesData is always an array
            const messagesData = JSON.parse(djangoMessagesJsonScript.textContent || '[]');
            if (Array.isArray(messagesData) && messagesData.length > 0) { // Add Array.isArray check
                const Toast = Swal.mixin({
                    toast: true, position: 'top-end', showConfirmButton: false, timer: 5000, timerProgressBar: true,
                    didOpen: (toast) => {
                        toast.addEventListener('mouseenter', Swal.stopTimer);
                        toast.addEventListener('mouseleave', Swal.resumeTimer);
                    }
                });
                messagesData.forEach(message => {
                    let iconType = message.tags;
                    if (message.tags === 'debug') iconType = 'info';
                    else if (message.tags === 'error') iconType = 'error';
                    else if (message.tags === 'success') iconType = 'success';
                    else if (message.tags === 'warning') iconType = 'warning';
                    else iconType = 'info';

                    let bgColor, textColor, progressBarClass;
                    switch (message.tags) {
                        case 'success': bgColor = '#ecfdf5'; textColor = '#059669'; progressBarClass = 'bg-green-500'; break;
                        case 'error': bgColor = '#fef2f2'; textColor = '#dc2626'; progressBarClass = 'bg-red-500'; break;
                        case 'warning': bgColor = '#fffbeb'; textColor = '#d97706'; progressBarClass = 'bg-amber-500'; break;
                        default: bgColor = '#eff6ff'; textColor = '#2563eb'; progressBarClass = 'bg-blue-500'; break;
                    }
                    Toast.fire({ icon: iconType, title: message.message, background: bgColor, color: textColor, customClass: { timerProgressBar: progressBarClass } });
                });
            }
        } catch (e) {
            console.error("Error parsing or displaying Django messages on manage page:", e);
        }
    }

    // --- Form Submission Loader ---
    function showManageLoader(message = "Processing Request...") {
        const loadingOverlayManage = document.getElementById('loadingOverlayManage');
        const loaderMessageManage = document.getElementById('loaderMessageManage');
        if (loadingOverlayManage && loaderMessageManage) {
            loaderMessageManage.textContent = message;
            loadingOverlayManage.classList.remove('hidden');
        }
    }
    document.querySelectorAll('.manage-audiobook-form').forEach(form => {
        form.addEventListener('submit', function(event) {
            // Basic client-side validation for visible required fields
            let formIsValid = true;
            form.querySelectorAll('input[required]:not([type="file"]), select[required], textarea[required]').forEach(requiredField => {
                let parent = requiredField;
                let isVisible = true;
                while(parent && parent !== form) {
                    if (parent.classList.contains('hidden') || parent.classList.contains('hidden-area') || getComputedStyle(parent).display === 'none') {
                        isVisible = false; break;
                    }
                    parent = parent.parentElement;
                }
                if (isVisible && !requiredField.value.trim()) {
                    formIsValid = false;
                }
            });
               form.querySelectorAll('input[type="file"][required]').forEach(fileInput => {
                   let parentControls = fileInput.closest('.new-chapter-file-upload-controls, .edit-chapter-file-upload-controls, .new-chapter-document-tts-controls, .edit-chapter-document-tts-controls');
                   let isVisible = parentControls && (parentControls.classList.contains('visible-area') || (!parentControls.classList.contains('hidden-area') && !parentControls.classList.contains('hidden')));

                   if (isVisible && fileInput.files.length === 0) {
                       // For edit forms, a file is only required if one wasn't already there or if explicitly replacing
                       // This basic check might need refinement based on specific edit logic
                       if (form.id === 'addChapterForm' || (form.classList.contains('edit-chapter-form-js') && !fileInput.dataset.hasExistingFile)) {
                            formIsValid = false;
                       }
                   }
               });

            if (!formIsValid) {
                // Optionally, show a generic error or highlight fields, but Django will do more thorough validation
                // console.warn("Basic client-side validation failed. Form will still attempt to submit.");
                // To prevent submission if client-side validation fails:
                // event.preventDefault();
                // Swal.fire('Incomplete Form', 'Please fill all required fields.', 'warning');
                // return;
            }

            let actionMessage = "Processing request...";
            const actionInput = form.querySelector('input[name="action"]');
            if (actionInput) {
                if (actionInput.value.startsWith('add_chapter')) actionMessage = "Adding new chapter...";
                else if (actionInput.value.startsWith('edit_chapter_')) actionMessage = "Updating chapter...";
                else if (actionInput.value.startsWith('delete_chapter_')) actionMessage = "Deleting chapter...";
                else if (actionInput.value === 'update_status_only') actionMessage = "Updating status...";
                else if (actionInput.value === 'edit_audiobook_details') actionMessage = "Saving audiobook details...";
            }
            showManageLoader(actionMessage);
        });
    });

}); // End DOMContentLoaded

// Global functions for inline event handlers
window.toggleEditChapterForm = (chapterId, forceHide = false) => {
    const formContainer = document.getElementById(`editChapterFormContainer_${chapterId}`);
    if (formContainer) {
        const isCurrentlyHidden = formContainer.classList.contains('hidden-area');
        // Hide all other edit forms
        document.querySelectorAll('[id^="editChapterFormContainer_"]').forEach(otherContainer => {
            if (otherContainer.id !== formContainer.id) {
                otherContainer.classList.add('hidden-area');
                otherContainer.classList.remove('visible-area');
            }
        });
        if (forceHide) {
            formContainer.classList.add('hidden-area');
            formContainer.classList.remove('visible-area');
        } else {
            formContainer.classList.toggle('hidden-area', !isCurrentlyHidden);
            formContainer.classList.toggle('visible-area', isCurrentlyHidden);
            if (isCurrentlyHidden) { // If it was hidden and now is visible
                formContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    } else {
        console.error("Edit chapter form container not found for ID:", chapterId);
    }
};

window.confirmDeleteChapter = (chapterName) => {
    return Swal.fire({
        title: 'Delete Chapter?',
        html: `Are you sure you want to delete chapter: "<strong>${chapterName}</strong>"?<br/>This action cannot be undone.`,
        icon: 'warning',
        iconColor: '#ef4444', // THEME_COLOR_ERROR
        showCancelButton: true,
        confirmButtonText: 'Yes, Delete It!',
        confirmButtonColor: '#ef4444', // THEME_COLOR_ERROR
        cancelButtonText: 'Keep Chapter',
        reverseButtons: true,
        customClass: {
            popup: 'rounded-xl shadow-2xl font-sans text-sm',
            title: 'text-lg font-semibold text-slate-800',
            htmlContainer: 'text-slate-600 pt-1 leading-normal',
            confirmButton: 'px-5 py-2.5 rounded-lg text-sm font-semibold text-white shadow-md hover:shadow-lg transition-shadow',
            cancelButton: 'px-5 py-2.5 rounded-lg text-sm font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 hover:border-slate-400 transition-colors'
        }
    }).then((result) => result.isConfirmed);
};
