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
    let TTS_VOICE_CHOICES_FROM_SCRIPT = []; // Renamed to avoid conflict if TTS_VOICE_CHOICES is global
    const ttsVoiceChoicesDataScript = document.getElementById('tts-voice-choices-data');
    if (ttsVoiceChoicesDataScript) {
        try {
            TTS_VOICE_CHOICES_FROM_SCRIPT = JSON.parse(ttsVoiceChoicesDataScript.textContent || '[]');
        } catch (e) {
            console.error("Error parsing TTS voice choices JSON:", e);
        }
    }

    // --- Cover Image Handling ---
    const mainDetailsForm = document.getElementById('detailsForm');
    const coverInputMainForm = document.getElementById('cover_image_input_main_form');
    const coverPreview = document.getElementById('coverImagePreview');
    const coverNameDisplay = document.getElementById('coverImageNameDisplay');
    const originalCoverSrc = coverPreview ? coverPreview.src : '';
    const originalCoverName = coverNameDisplay ? coverNameDisplay.textContent : '';

    if (coverInputMainForm && coverPreview && coverNameDisplay) {
        coverInputMainForm.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                if (file.size > 2 * 1024 * 1024) { 
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
    const formErrorsDataScript = document.getElementById('django-form-errors-data-for-js');
    if (formErrorsDataScript) {
        try { formErrors = JSON.parse(formErrorsDataScript.textContent || '{}'); } catch(e) { console.error("Error parsing form errors JSON for manage page:", e); }
    }

    if (addChapterFormContainer && formErrors.add_chapter_active_with_errors) {
        addChapterFormContainer.classList.remove('hidden');
        if (addChapterIcon) addChapterIcon.className = 'fas fa-times transition-transform duration-300 ease-in-out';
        if (addChapterText) addChapterText.textContent = 'Cancel Adding';
    }

    if (addChapterBtn && addChapterFormContainer) {
        addChapterBtn.addEventListener('click', function() {
            const isHidden = addChapterFormContainer.classList.contains('hidden');
            addChapterFormContainer.classList.toggle('hidden');
            if (addChapterIcon) addChapterIcon.className = isHidden ? 'fas fa-times transition-transform duration-300 ease-in-out' : 'fas fa-plus transition-transform duration-300 ease-in-out';
            if (addChapterText) addChapterText.textContent = isHidden ? 'Cancel Adding' : 'Add New Chapter';
            if (isHidden) addChapterFormContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    }

    // --- Helper Function for TTS Preview AJAX Call ---
    async function generateChapterTtsPreview(params) {
        const {
            textContentInput, voiceSelect, playerContainer, player, messageEl, 
            confirmUseBtn, generateBtn, generatedUrlInputForChapter, 
            lockedDisplayForChapter, lockedFilenameSpanForChapter, inputTypeHiddenForChapter
        } = params;

        const text = textContentInput.value.trim();
        const voiceId = voiceSelect.value;
        const btnTextEl = generateBtn.querySelector('.btn-text');
        const spinnerEl = generateBtn.querySelector('.spinner');

        messageEl.textContent = '';
        playerContainer.classList.add('hidden');
        player.src = '';
        if (confirmUseBtn) confirmUseBtn.classList.add('hidden');
        if (generatedUrlInputForChapter) generatedUrlInputForChapter.value = ''; 
        if (lockedDisplayForChapter) lockedDisplayForChapter.classList.add('hidden');

        let isValid = true;
        if (!text) { messageEl.textContent = 'Text is required.'; isValid = false; }
        else if (text.length < 10) { messageEl.textContent = 'Text too short (min 10 chars).'; isValid = false; }
        else if (text.length > 5000) { messageEl.textContent = 'Text too long (max 5000 chars for preview).'; isValid = false; }
        // Ensure a valid voice is selected (not the placeholder/default if one exists, or if the list is empty)
        if (voiceId === 'default' || !voiceId || (voiceSelect.options.length > 0 && voiceSelect.selectedIndex === 0 && voiceSelect.options[0].value === 'default')) { 
            messageEl.textContent = (messageEl.textContent ? messageEl.textContent + ' ' : '') + 'Select a narrator voice.'; 
            isValid = false; 
        }
        
        if (!isValid) { 
            messageEl.className = messageEl.className.replace(/text-(green|indigo|blue)-[0-9]+/g, 'text-red-600');
            return; 
        }

        generateBtn.disabled = true;
        if(btnTextEl) btnTextEl.classList.add('hidden');
        if(spinnerEl) spinnerEl.classList.remove('hidden');
        messageEl.textContent = 'Generating preview...';
        messageEl.className = messageEl.className.replace(/text-(red|green)-[0-9]+/g, 'text-indigo-600');

        const formData = new FormData();
        formData.append('text_content', text);
        formData.append('tts_voice_id', voiceId);
        formData.append('csrfmiddlewaretoken', csrfToken);

        try {
            const response = await fetch(generateTtsPreviewUrl, { method: 'POST', body: formData, headers: {'X-CSRFToken': csrfToken} });
            const data = await response.json();

            if (response.ok && data.status === 'success') {
                player.src = data.audio_url;
                playerContainer.classList.remove('hidden');
                messageEl.textContent = `Preview ready! (${data.filename || 'Generated Audio'})`;
                messageEl.className = messageEl.className.replace(/text-(red|indigo)-[0-9]+/g, 'text-green-600');
                if (confirmUseBtn) {
                    confirmUseBtn.classList.remove('hidden');
                    confirmUseBtn.dataset.generatedUrl = data.audio_url;
                    confirmUseBtn.dataset.generatedVoiceId = data.voice_id_used;
                    confirmUseBtn.dataset.generatedFilename = data.filename || "Generated_Audio.mp3";
                }
            } else {
                messageEl.textContent = `Error: ${data.message || 'Unknown TTS error.'}`;
                messageEl.className = messageEl.className.replace(/text-(green|indigo)-[0-9]+/g, 'text-red-600');
            }
        } catch (error) {
            messageEl.textContent = 'Network error during TTS preview.';
            messageEl.className = messageEl.className.replace(/text-(green|indigo)-[0-9]+/g, 'text-red-600');
            console.error('Chapter TTS Preview Fetch Error:', error);
        } finally {
            generateBtn.disabled = false;
            if(btnTextEl) btnTextEl.classList.remove('hidden');
            if(spinnerEl) spinnerEl.classList.add('hidden');
        }
    }

    // --- Initialize Controls for "Add New Chapter" Form ---
    const addChapterForm = document.getElementById('addChapterForm');
    if (addChapterForm) {
        const inputTypeHidden = addChapterForm.querySelector('.new-chapter-input-type-hidden-js');
        const fileUploadControls = addChapterForm.querySelector('.new-chapter-file-upload-controls');
        const ttsGenerationControls = addChapterForm.querySelector('.new-chapter-tts-generation-controls');
        const lockedDisplay = addChapterForm.querySelector('.new-chapter-locked-generated-audio-display');
        const generatedUrlInput = addChapterForm.querySelector('.new-chapter-generated-tts-url-input-js');
        const lockedFilenameSpan = addChapterForm.querySelector('.new-chapter-generated-tts-filename-js');
        const audioInput = fileUploadControls?.querySelector('#new_chapter_audio');
        const textInput = ttsGenerationControls?.querySelector('#new_chapter_text_content');
        const voiceSelect = ttsGenerationControls?.querySelector('#new_chapter_tts_voice');
        
        function toggleAddNewChapterFields(type) {
            if (inputTypeHidden) inputTypeHidden.value = type;
            fileUploadControls?.classList.add('hidden');
            ttsGenerationControls?.classList.add('hidden');
            lockedDisplay?.classList.add('hidden');

            if(audioInput) audioInput.required = false;
            if(textInput) textInput.required = false;
            if(voiceSelect) voiceSelect.required = false;

            if (type === 'file') {
                fileUploadControls?.classList.remove('hidden');
                if(audioInput) audioInput.required = true;
            } else if (type === 'tts') {
                ttsGenerationControls?.classList.remove('hidden');
                if (generatedUrlInput && generatedUrlInput.value) { 
                    lockedDisplay?.classList.remove('hidden'); 
                    if (inputTypeHidden) inputTypeHidden.value = 'generated_tts';
                } else { 
                    if(textInput) textInput.required = true;
                    if(voiceSelect) voiceSelect.required = true;
                }
            }
        }

        addChapterForm.querySelectorAll('.new-chapter-input-type-toggle-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const type = this.dataset.type;
                addChapterForm.querySelectorAll('.new-chapter-input-type-toggle-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                if (type === 'file' && generatedUrlInput && generatedUrlInput.value) { 
                    generatedUrlInput.value = ''; 
                    if(lockedFilenameSpan) lockedFilenameSpan.textContent = "Generated Audio";
                    const confirmBtn = addChapterForm.querySelector('.confirm-use-new-chapter-generated-audio-btn');
                    if(confirmBtn) confirmBtn.classList.add('hidden');
                    const playerContainer = addChapterForm.querySelector('.new-chapter-tts-preview-player-container');
                    if(playerContainer) playerContainer.classList.add('hidden');
                     const messageEl = addChapterForm.querySelector('.new-chapter-tts-message');
                    if(messageEl) messageEl.textContent = '';
                }
                toggleAddNewChapterFields(type);
            });
        });
        
        const initialNewChapterType = inputTypeHidden ? (inputTypeHidden.value || 'file') : 'file';
        addChapterForm.querySelectorAll('.new-chapter-input-type-toggle-btn').forEach(btn => {
            const btnType = btn.dataset.type;
            if (btnType === initialNewChapterType || (initialNewChapterType === 'generated_tts' && btnType === 'tts')) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        toggleAddNewChapterFields(initialNewChapterType === 'generated_tts' ? 'tts' : initialNewChapterType);

        const generateBtn = addChapterForm.querySelector('.generate-new-chapter-tts-preview-btn');
        const playerContainer = addChapterForm.querySelector('.new-chapter-tts-preview-player-container');
        const player = playerContainer?.querySelector('.chapter-tts-preview-player');
        const messageEl = addChapterForm.querySelector('.new-chapter-tts-message');
        const confirmUseBtn = addChapterForm.querySelector('.confirm-use-new-chapter-generated-audio-btn');

        if (generateBtn && textInput && voiceSelect && playerContainer && player && messageEl && confirmUseBtn) {
            generateBtn.addEventListener('click', function() {
                generateChapterTtsPreview({
                    textContentInput: textInput, voiceSelect, playerContainer, player, messageEl, 
                    confirmUseBtn, generateBtn: this, generatedUrlInputForChapter: generatedUrlInput, 
                    lockedDisplayForChapter: lockedDisplay, lockedFilenameSpanForChapter: lockedFilenameSpan,
                    inputTypeHiddenForChapter: inputTypeHidden
                });
            });
        }
        if (confirmUseBtn && generatedUrlInput && lockedDisplay && lockedFilenameSpan && voiceSelect && inputTypeHidden && messageEl) {
            confirmUseBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const filenameUsed = this.dataset.generatedFilename;
                if (urlToUse) {
                    generatedUrlInput.value = urlToUse;
                    
                    let displayFilenameText = filenameUsed;
                    if (voiceUsed && voiceUsed !== 'default') {
                        const voiceOption = voiceSelect.querySelector(`option[value="${voiceUsed}"]`);
                        const voiceDisplayName = voiceOption ? voiceOption.textContent.split('(')[0].trim() : (TTS_VOICE_CHOICES_FROM_SCRIPT.find(v => v[0] === voiceUsed)?.[1] || voiceUsed.replace('_narrator', '').replace(/([A-Z])/g, ' $1').trim());
                        displayFilenameText += ` (Voice: ${voiceDisplayName})`;
                    }
                    lockedFilenameSpan.textContent = displayFilenameText;
                    
                    voiceSelect.value = voiceUsed; 
                    inputTypeHidden.value = 'generated_tts'; 
                    lockedDisplay.classList.remove('hidden');
                    this.classList.add('hidden'); 
                    if(playerContainer) playerContainer.classList.add('hidden');
                    messageEl.textContent = 'Previewed audio selected for this new chapter.';
                    messageEl.className = 'new-chapter-tts-message text-xs my-1.5 min-h-[16px] text-green-700 font-semibold';
                }
            });
        }
    }

    // --- Initialize Controls for EACH "Edit Existing Chapter" Form ---
    document.querySelectorAll('.edit-chapter-form-js').forEach(form => {
        const chapterId = form.dataset.chapterId;
        const inputTypeHidden = form.querySelector(`.edit-chapter-input-type-hidden-js`);
        const fileUploadControls = form.querySelector(`.edit-chapter-file-upload-controls`);
        const ttsGenerationControls = form.querySelector(`.edit-chapter-tts-generation-controls`);
        const lockedDisplay = form.querySelector('.locked-generated-audio-display');
        const generatedUrlInput = form.querySelector(`.edit-chapter-generated-tts-url-input-js`);
        const lockedFilenameSpan = lockedDisplay?.querySelector('.chapter-generated-tts-filename-js');
        const audioInput = fileUploadControls?.querySelector(`#chapter_audio_${chapterId}`);
        const textInput = ttsGenerationControls?.querySelector(`#chapter_text_content_${chapterId}`);
        const voiceSelect = ttsGenerationControls?.querySelector(`#chapter_tts_voice_${chapterId}`);
        const fileNameSpan = fileUploadControls?.querySelector('.chapter-filename-js'); 

        function toggleEditChapterFields(type) { 
            if (inputTypeHidden) inputTypeHidden.value = type;
            fileUploadControls?.classList.add('hidden');
            ttsGenerationControls?.classList.add('hidden');
            lockedDisplay?.classList.add('hidden');

            if(audioInput) audioInput.required = false; 
            if(textInput) textInput.required = false;
            if(voiceSelect) voiceSelect.required = false;

            if (type === 'file') {
                fileUploadControls?.classList.remove('hidden');
            } else if (type === 'tts') {
                ttsGenerationControls?.classList.remove('hidden');
                if (generatedUrlInput && generatedUrlInput.value) { 
                    lockedDisplay?.classList.remove('hidden');
                    if (inputTypeHidden) inputTypeHidden.value = 'generated_tts';
                } else { 
                    if(textInput) textInput.required = true;
                    if(voiceSelect) voiceSelect.required = true;
                }
            }
        }

        form.querySelectorAll('.edit-chapter-input-type-toggle-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const type = this.dataset.type;
                form.querySelectorAll('.edit-chapter-input-type-toggle-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                if (type === 'file' && generatedUrlInput && generatedUrlInput.value) {
                    generatedUrlInput.value = ''; 
                    if(lockedFilenameSpan) lockedFilenameSpan.textContent = "Generated Audio";
                    const confirmBtn = form.querySelector('.confirm-use-generated-audio-btn');
                    if(confirmBtn) confirmBtn.classList.add('hidden');
                    const playerContainer = form.querySelector('.chapter-tts-preview-player-container');
                    if(playerContainer) playerContainer.classList.add('hidden');
                    const messageEl = form.querySelector('.chapter-tts-message');
                    if(messageEl) messageEl.textContent = '';
                }
                toggleEditChapterFields(type);
            });
        });

        const initialEditType = inputTypeHidden ? (inputTypeHidden.value === 'generated_tts' ? 'tts' : inputTypeHidden.value) : 'file';
        form.querySelectorAll('.edit-chapter-input-type-toggle-btn').forEach(btn => {
            const btnType = btn.dataset.type;
            if (btnType === initialEditType) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        toggleEditChapterFields(initialEditType);

        const generateBtn = form.querySelector('.generate-chapter-tts-preview-btn');
        const playerContainer = form.querySelector('.chapter-tts-preview-player-container');
        const player = playerContainer?.querySelector('.chapter-tts-preview-player');
        const messageEl = form.querySelector('.chapter-tts-message');
        const confirmUseBtn = form.querySelector('.confirm-use-generated-audio-btn');

        if (generateBtn && textInput && voiceSelect && playerContainer && player && messageEl && confirmUseBtn) {
            generateBtn.addEventListener('click', function() {
                 generateChapterTtsPreview({
                    textContentInput: textInput, voiceSelect, playerContainer, player, messageEl, 
                    confirmUseBtn, generateBtn: this, generatedUrlInputForChapter: generatedUrlInput, 
                    lockedDisplayForChapter: lockedDisplay, lockedFilenameSpanForChapter: lockedFilenameSpan,
                    inputTypeHiddenForChapter: inputTypeHidden
                });
            });
        }
        if (confirmUseBtn && generatedUrlInput && lockedDisplay && lockedFilenameSpan && voiceSelect && inputTypeHidden && messageEl) {
            confirmUseBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const filenameUsed = this.dataset.generatedFilename;
                if (urlToUse) {
                    generatedUrlInput.value = urlToUse;
                    let displayFilenameText = filenameUsed;
                     if (voiceUsed && voiceUsed !== 'default') {
                        const voiceOption = voiceSelect.querySelector(`option[value="${voiceUsed}"]`);
                        const voiceDisplayName = voiceOption ? voiceOption.textContent.split('(')[0].trim() : (TTS_VOICE_CHOICES_FROM_SCRIPT.find(v => v[0] === voiceUsed)?.[1] || voiceUsed.replace('_narrator', '').replace(/([A-Z])/g, ' $1').trim());
                        displayFilenameText += ` (Voice: ${voiceDisplayName})`;
                    }
                    lockedFilenameSpan.textContent = displayFilenameText;
                    voiceSelect.value = voiceUsed; 
                    inputTypeHidden.value = 'generated_tts'; 
                    lockedDisplay.classList.remove('hidden');
                    this.classList.add('hidden'); 
                    if(playerContainer) playerContainer.classList.add('hidden');
                    messageEl.textContent = 'Previewed audio selected for this chapter.';
                    messageEl.className = 'chapter-tts-message text-xs my-1.5 min-h-[16px] text-green-700 font-semibold';
                }
            });
        }
        
        if (audioInput && fileNameSpan) {
            audioInput.addEventListener('change', function(e) {
                const audioErrorEl = form.querySelector('.chapter-audio-error-js'); 
                if(audioErrorEl) audioErrorEl.textContent = ''; 

                if (e.target.files.length > 0) {
                    const file = e.target.files[0];
                    const maxAudioSize = 50 * 1024 * 1024; 
                    const allowedAudioTypes = ['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a'];

                    if (file.size > maxAudioSize) {
                        if(audioErrorEl) audioErrorEl.textContent = `File too large (Max 50MB).`;
                        e.target.value = ''; 
                        fileNameSpan.textContent = 'Choose new audio file... (too large)';
                        return;
                    }
                    if (!allowedAudioTypes.includes(file.type)) {
                         if(audioErrorEl) audioErrorEl.textContent = "Invalid audio file type.";
                        e.target.value = ''; 
                        fileNameSpan.textContent = 'Choose new audio file... (invalid type)';
                        return;
                    }
                    fileNameSpan.textContent = file.name; 
                } else {
                    fileNameSpan.textContent = 'Choose new audio file...'; 
                }
            });
        }
    });
    
    document.querySelectorAll('[id^="editChapterFormContainer_"]').forEach(container => {
        const chapterId = container.id.split('_').pop();
        if (formErrors && formErrors.edit_chapter_errors && formErrors.edit_chapter_errors[`edit_chapter_${chapterId}`] && 
            Object.keys(formErrors.edit_chapter_errors[`edit_chapter_${chapterId}`]).length > 0) {
            container.classList.remove('hidden');
            // container.scrollIntoView({ behavior: 'smooth', block: 'center' }); // Scroll if errors
        }
    });

    const statusSelect = document.getElementById('status_only_select_html');
    const statusUpdateForm = document.getElementById('statusUpdateFormHtml'); 
    if (statusSelect && statusUpdateForm) { 
        const statusUpdateButton = statusUpdateForm.querySelector('button[type="submit"]'); 
        const initialAudiobookStatus = statusSelect.dataset.initialStatus || statusSelect.value; 

        function toggleStatusButtonState() {
            if (statusUpdateButton && statusSelect) { 
                statusUpdateButton.disabled = (statusSelect.value === initialAudiobookStatus);
            }
        }
        if (!statusSelect.dataset.initialStatus) {
            statusSelect.dataset.initialStatus = statusSelect.value;
        }
        toggleStatusButtonState(); 
        statusSelect.addEventListener('change', toggleStatusButtonState);
    }

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
            let formIsValid = true;
            form.querySelectorAll('input[required]:not([type="file"]), select[required], textarea[required]').forEach(requiredField => {
                // Only check visible fields or fields not within a hidden parent
                let parent = requiredField.parentElement;
                let isVisible = true;
                while(parent) {
                    if (parent.classList.contains('hidden')) {
                        isVisible = false;
                        break;
                    }
                    parent = parent.parentElement;
                }
                if (isVisible && !requiredField.value.trim()) {
                    formIsValid = false;
                }
            });
             // Special check for required file inputs that are visible
            form.querySelectorAll('input[type="file"][required]').forEach(fileInput => {
                let parent = fileInput.parentElement;
                let isVisible = true;
                while(parent) {
                    if (parent.classList.contains('hidden')) {
                        isVisible = false;
                        break;
                    }
                    parent = parent.parentElement;
                }
                if (isVisible && fileInput.files.length === 0) {
                     // If it's an edit form, an existing file might be okay.
                     // This basic check is more for new uploads.
                     // For edit, backend handles if a new file is truly required.
                    if (form.id === 'addChapterForm') { // Be more strict for add chapter form
                        formIsValid = false;
                    }
                }
            });


            if (!formIsValid) {
                console.warn("Basic client-side validation failed for a form. Submission halted by JS.");
                 // Optionally, prevent loader and default submission
                // event.preventDefault(); 
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

    const djangoMessagesJsonScript = document.getElementById('django_messages_json');
    if (djangoMessagesJsonScript && typeof Swal !== 'undefined') {
        try {
            const messagesData = JSON.parse(djangoMessagesJsonScript.textContent || '[]');
            if (messagesData.length > 0) {
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
});

window.toggleEditChapterForm = (chapterId) => {
    console.log("toggleEditChapterForm called with ID:", chapterId); // For debugging
    const formContainer = document.getElementById(`editChapterFormContainer_${chapterId}`);
    if (formContainer) {
        console.log("Form container found:", formContainer); // For debugging
        const isCurrentlyHidden = formContainer.classList.contains('hidden');
        // Hide all other edit forms first to avoid multiple open forms
        document.querySelectorAll('[id^="editChapterFormContainer_"]').forEach(otherContainer => {
            if (otherContainer.id !== formContainer.id) {
                otherContainer.classList.add('hidden');
            }
        });
        // Then toggle the target one
        if(isCurrentlyHidden) {
            formContainer.classList.remove('hidden');
            formContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
            formContainer.classList.add('hidden');
        }
    } else {
        console.error("Edit chapter form container not found for ID:", chapterId); // For debugging
    }
};

window.confirmDeleteChapter = (chapterName) => {
    return Swal.fire({
        title: 'Delete Chapter?',
        html: `Are you sure you want to delete chapter: "<strong>${chapterName}</strong>"?<br/>This action cannot be undone.`,
        icon: 'warning', iconColor: THEME_COLOR_ERROR, showCancelButton: true,
        confirmButtonText: 'Yes, Delete It!', confirmButtonColor: THEME_COLOR_ERROR, 
        cancelButtonText: 'Keep Chapter', reverseButtons: true,
        customClass: {
            popup: 'rounded-xl shadow-2xl font-sans text-sm',
            title: 'text-lg font-semibold text-slate-800',
            htmlContainer: 'text-slate-600 pt-1 leading-normal',
            confirmButton: 'px-5 py-2.5 rounded-lg text-sm font-semibold text-white shadow-md hover:shadow-lg transition-shadow',
            cancelButton: 'px-5 py-2.5 rounded-lg text-sm font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 hover:border-slate-400 transition-colors'
        }
    }).then((result) => result.isConfirmed);
};