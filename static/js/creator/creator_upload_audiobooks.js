// Ensure the DOM is fully loaded before executing the script
document.addEventListener('DOMContentLoaded', function() {
    // Constants for theme colors used in notifications and UI elements
    const THEME_COLOR_PRIMARY = '#091e65';
    const THEME_COLOR_ERROR = '#ef4444';
    const THEME_COLOR_SUCCESS = '#10b981';
    const THEME_COLOR_WARNING = '#f97316';

    const LOADER_MESSAGES = [
        "Initializing upload sequence...", "Connecting to secure server...", "Compressing audio data...",
        "Uploading cover art (looking sharp!)...", "Sending chapter files, one by one...",
        "Almost there, just a few more bytes...", "Validating audiobook details...", "Processing metadata...",
        "Finalizing publication...", "Your audiobook is getting ready for the world!",
        "Patience, great things take time...", "Just a moment more, we're working on it!",
        "Crafting the perfect listening experience...", "Dotting the i's and crossing the t's...",
        "Synchronizing with the digital shelves..."
    ];
    let currentLoaderMessageIndex = 0;
    let loaderMessageIntervalId = null;

    // --- Form and General Page Elements ---
    const form = document.getElementById('audiobookUploadForm');
    const coverImageInput = document.getElementById('cover_image');
    const coverImagePreview = document.getElementById('coverImagePreview');
    const coverImageNameDisplay = document.getElementById('coverImageNameDisplay');
    const coverUploadPlaceholder = document.getElementById('coverUploadPlaceholder');
    const coverUploadInitialText = document.getElementById('coverUploadInitialText');
    const coverChangeText = document.getElementById('coverChangeText');
    const coverPreviewContainer = document.getElementById('coverPreviewContainer');

    // --- Pricing Section Elements ---
    const pricingTypeFreeBtn = document.getElementById('pricingTypeFreeBtn');
    const pricingTypePaidBtn = document.getElementById('pricingTypePaidBtn');
    const pricingTypeFreeRadio = document.getElementById('pricing_type_free_radio');
    const pricingTypePaidRadio = document.getElementById('pricing_type_paid_radio');
    const priceInputContainer = document.getElementById('priceInputContainer');
    const priceInput = document.getElementById('price');

    // --- Audiobook Details Section Elements ---
    const languageSelect = document.getElementById('language');
    const genreInputContainer = document.getElementById('genreInputContainer'); // Container for genre input/select
    // The actual genre input/select will be dynamic, so we get it later or on creation.
    // let genreField = document.getElementById('genre'); // This will be updated

    // --- Chapters Section Elements ---
    const addChapterBtn = document.getElementById('addChapterBtn');
    const chaptersListContainer = document.getElementById('chaptersListContainer');
    const chapterTemplate = document.getElementById('chapterTemplate');
    const noChaptersMessage = document.getElementById('noChaptersMessage');

    // --- Submission and Loading Elements ---
    const publishButton = document.getElementById('publishButton');
    const publishButtonText = document.getElementById('publishButtonText');
    const publishingSpinner = document.getElementById('publishingSpinner');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const loaderMessageElement = document.getElementById('loaderMessage');

    // --- URL for TTS Preview Generation ---
    const generateTtsPreviewUrl = document.getElementById('generate-tts-preview-url')?.textContent.trim();

    // --- State Variables ---
    let nextChapterIndex = 0; 
    let isSubmittingAfterDelay = false;

    // --- Initial Data Parsing ---
    let formErrors = {};
    let submittedValues = {};
    try {
        const errorsDataElement = document.getElementById('form-errors-data-script');
        if (errorsDataElement) formErrors = JSON.parse(errorsDataElement.textContent || '{}');
        const submittedDataElement = document.getElementById('submitted-values-data-script');
        if (submittedDataElement) submittedValues = JSON.parse(submittedDataElement.textContent || '{}');
    } catch (e) {
        console.error("Error parsing initial form data from script tags:", e);
    }

    // --- Cover Image Handling ---
    if (coverImageInput && coverImagePreview && coverImageNameDisplay && coverUploadInitialText && coverChangeText && coverPreviewContainer) {
        coverImageInput.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                if (file.size > 2 * 1024 * 1024) { 
                    Swal.fire({ title: 'Cover Image Too Large', html: `Cover image must be under <strong>2MB</strong>. <br/>Selected file is ${(file.size / (1024*1024)).toFixed(2)}MB.`, icon: 'error', iconColor: THEME_COLOR_ERROR, confirmButtonColor: THEME_COLOR_PRIMARY, customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal' }});
                    event.target.value = '';
                    coverImagePreview.src = 'https://placehold.co/400x300/e2e8f0/64748b?text=Upload+Cover';
                    coverImageNameDisplay.textContent = 'PNG, JPG, JPEG (Max 2MB)';
                    coverUploadInitialText.style.display = 'block';
                    coverChangeText.style.display = 'none';
                    coverUploadPlaceholder.classList.remove('opacity-0', 'group-hover:opacity-100', 'bg-black/70', 'rounded-xl', 'text-white');
                    coverPreviewContainer.classList.remove('border-solid', 'border-[#091e65]', 'ring-2', 'ring-[#091e65]/20');
                    return;
                }
                if (!['image/jpeg', 'image/png', 'image/jpg'].includes(file.type)) {
                    Swal.fire({ title: 'Invalid File Type', text: 'Please select a JPG, JPEG, or PNG image for the cover.', icon: 'error', iconColor: THEME_COLOR_ERROR, confirmButtonColor: THEME_COLOR_PRIMARY, customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal' }});
                    event.target.value = '';
                    return;
                }
                const reader = new FileReader();
                reader.onload = (e) => { coverImagePreview.src = e.target.result; }
                reader.readAsDataURL(file);
                coverImageNameDisplay.textContent = file.name;
                coverUploadInitialText.style.display = 'none';
                coverChangeText.style.display = 'block';
                coverUploadPlaceholder.classList.add('opacity-0', 'group-hover:opacity-100', 'bg-black/70', 'rounded-xl', 'text-white');
                coverPreviewContainer.classList.add('border-solid', 'border-[#091e65]', 'ring-2', 'ring-[#091e65]/20');
            } else {
                coverImagePreview.src = 'https://placehold.co/400x300/e2e8f0/64748b?text=Upload+Cover';
                coverImageNameDisplay.textContent = 'PNG, JPG, JPEG (Max 2MB)';
                coverUploadInitialText.style.display = 'block';
                coverChangeText.style.display = 'none';
                coverUploadPlaceholder.classList.remove('opacity-0', 'group-hover:opacity-100', 'bg-black/70', 'rounded-xl', 'text-white');
                coverPreviewContainer.classList.remove('border-solid', 'border-[#091e65]', 'ring-2', 'ring-[#091e65]/20');
            }
        });
        if (submittedValues.cover_image_filename) {
           coverImageNameDisplay.textContent = submittedValues.cover_image_filename;
           if (!formErrors.cover_image && submittedValues.cover_image_preview_url) { 
                coverImagePreview.src = submittedValues.cover_image_preview_url;
                coverUploadInitialText.style.display = 'none';
                coverChangeText.style.display = 'block';
                coverUploadPlaceholder.classList.add('opacity-0', 'group-hover:opacity-100', 'bg-black/70', 'rounded-xl', 'text-white');
           }
        }
    }

    // --- Pricing Type UI Handling ---
    function updatePricingUI(selectedType) {
        if (pricingTypeFreeBtn && pricingTypePaidBtn && pricingTypeFreeRadio && pricingTypePaidRadio && priceInputContainer && priceInput) {
            if (selectedType === 'free') {
                pricingTypeFreeBtn.classList.add('bg-[#091e65]', 'text-white', 'shadow-md');
                pricingTypeFreeBtn.classList.remove('text-slate-500', 'hover:text-[#091e65]');
                pricingTypePaidBtn.classList.remove('bg-[#091e65]', 'text-white', 'shadow-md');
                pricingTypePaidBtn.classList.add('text-slate-500', 'hover:text-[#091e65]');
                pricingTypeFreeRadio.checked = true;
                priceInputContainer.classList.add('hidden');
                priceInput.required = false;
            } else if (selectedType === 'paid') {
                pricingTypePaidBtn.classList.add('bg-[#091e65]', 'text-white', 'shadow-md');
                pricingTypePaidBtn.classList.remove('text-slate-500', 'hover:text-[#091e65]');
                pricingTypeFreeBtn.classList.remove('bg-[#091e65]', 'text-white', 'shadow-md');
                pricingTypeFreeBtn.classList.add('text-slate-500', 'hover:text-[#091e65]');
                pricingTypePaidRadio.checked = true;
                priceInputContainer.classList.remove('hidden');
                priceInput.required = true;
            }
        }
    }
    if (pricingTypeFreeBtn) pricingTypeFreeBtn.addEventListener('click', () => updatePricingUI('free'));
    if (pricingTypePaidBtn) pricingTypePaidBtn.addEventListener('click', () => updatePricingUI('paid'));
    // Initialize pricing UI based on submitted values or default
    updatePricingUI(submittedValues.pricing_type || 'free');

    // --- Dynamic Genre Field Handling ---
    const englishGenres = [
        { value: "Biography", text: "Biography" },
        { value: "Business", text: "Business" },
        { value: "Fantasy", text: "Fantasy" },
        { value: "Fiction", text: "Fiction" },
        { value: "History", text: "History" },
        { value: "Mystery", text: "Mystery" },
        { value: "Romance", text: "Romance" },
        { value: "Sci-Fi", text: "Sci-Fi" },
        { value: "Self-Help", text: "Self-Help" },
        { value: "Thriller", text: "Thriller" }
    ];

    function updateGenreField(selectedLanguage) {
        if (!genreInputContainer) return;
        
        // Clear previous genre field and messages
        genreInputContainer.innerHTML = ''; 

        const label = document.createElement('label');
        label.htmlFor = 'genre';
        label.className = 'block text-sm font-medium text-slate-700 mb-1.5';
        label.innerHTML = 'Genre <span class="text-red-600">*</span>';
        genreInputContainer.appendChild(label);

        let genreField;
        const helperTextElement = document.createElement('p');
        helperTextElement.className = 'text-xs text-slate-500 mt-1';
        
        const errorTextElement = document.createElement('p');
        errorTextElement.className = 'text-red-500 text-sm mt-1';
        errorTextElement.id = 'genre_error_message_placeholder'; // Keep ID for potential server errors

        if (selectedLanguage === "English") {
            genreField = document.createElement('select');
            genreField.name = 'genre';
            genreField.id = 'genre';
            genreField.required = true;
            genreField.className = 'block w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-[#091e65]/70 focus:border-[#091e65] sm:text-sm appearance-none bg-no-repeat transition duration-150 ease-in-out text-slate-700 shadow-sm';

            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "Select Genre...";
            defaultOption.disabled = true;
            genreField.appendChild(defaultOption);

            englishGenres.forEach(genre => {
                const option = document.createElement('option');
                option.value = genre.value;
                option.textContent = genre.text;
                genreField.appendChild(option);
            });
            helperTextElement.textContent = 'Select the most fitting genre for your English audiobook.';
            if (submittedValues.genre && submittedValues.language === "English") {
                 genreField.value = submittedValues.genre;
            }
            if (!genreField.value) { // Ensure default is selected if submitted value doesn't match
                genreField.value = "";
            }

        } else if (["Urdu", "Punjabi", "Sindhi"].includes(selectedLanguage)) {
            genreField = document.createElement('input');
            genreField.type = 'text';
            genreField.name = 'genre';
            genreField.id = 'genre';
            genreField.required = true;
            genreField.className = 'block w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-[#091e65]/70 focus:border-[#091e65] sm:text-sm placeholder-slate-400 transition duration-150 ease-in-out shadow-sm';
            genreField.placeholder = 'e.g., Poetry, Short Story, Novel';
            helperTextElement.textContent = `Enter the genre for your ${selectedLanguage} audiobook.`;
            if (submittedValues.genre && submittedValues.language === selectedLanguage) {
                genreField.value = submittedValues.genre;
            }
        } else { // No language selected or unknown
            genreField = document.createElement('input');
            genreField.type = 'text';
            genreField.name = 'genre';
            genreField.id = 'genre';
            // Not required if no language is selected, but language itself is required.
            // Validation will catch language first.
            genreField.className = 'block w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-[#091e65]/70 focus:border-[#091e65] sm:text-sm placeholder-slate-400 transition duration-150 ease-in-out shadow-sm bg-slate-50 cursor-not-allowed';
            genreField.placeholder = 'Select language first';
            genreField.disabled = true;
            helperTextElement.textContent = 'Please select a language to see genre options.';
        }

        genreInputContainer.appendChild(genreField);
        genreInputContainer.appendChild(helperTextElement);
        genreInputContainer.appendChild(errorTextElement); // Add error placeholder

        // Re-populate error message if it exists for 'genre' from server-side validation
        if (formErrors.genre && errorTextElement) {
             errorTextElement.textContent = formErrors.genre;
        }
    }

    if (languageSelect) {
        languageSelect.addEventListener('change', function() {
            updateGenreField(this.value);
            // Clear submitted genre if language changes, to avoid mismatch
            if (submittedValues.genre) submittedValues.genre = ''; 
        });
        // Initial call to set up genre field based on current language (e.g., from form repopulation)
        updateGenreField(languageSelect.value);
    }


    // --- Chapter Management ---
    function setupChapterCard(chapterDiv, indexForNames, chapterData = {}) {
        const visualOrder = chapterData.order || (chaptersListContainer.querySelectorAll('.chapter-card').length + (chapterData.isNew ? 0 : 1));
        chapterDiv.dataset.indexJs = indexForNames;

        const chapterNumberSpan = chapterDiv.querySelector('.chapter-number-js');
        if (chapterNumberSpan) chapterNumberSpan.textContent = visualOrder;

        const chapterTitleDisplay = chapterDiv.querySelector('.chapter-title-display-js');
        const titleInput = chapterDiv.querySelector('.chapter-title-input-js');
        if (chapterTitleDisplay) chapterTitleDisplay.textContent = chapterData.title || `Chapter ${visualOrder}`;
        if (titleInput) {
            titleInput.name = `chapters[${indexForNames}][title]`;
            titleInput.id = `chapter_title_${indexForNames}`;
            titleInput.value = chapterData.title || '';
            titleInput.addEventListener('input', function() {
                if (chapterTitleDisplay) chapterTitleDisplay.textContent = this.value || `Chapter ${visualOrder}`;
            });
        }

        const audioInput = chapterDiv.querySelector('.chapter-audio-input-js');
        const fileNameSpan = chapterDiv.querySelector('.chapter-filename-js');
        if (audioInput) {
            audioInput.name = `chapters[${indexForNames}][audio_file]`;
            audioInput.id = `chapter_audio_${indexForNames}`;
        }
        if (fileNameSpan) {
            fileNameSpan.textContent = (chapterData.audio_filename && chapterData.audio_filename !== "No file chosen") ? chapterData.audio_filename : 'Choose audio file...';
        }
        
        const textContentInput = chapterDiv.querySelector('.chapter-text-content-input-js');
        if (textContentInput) {
            textContentInput.name = `chapters[${indexForNames}][text_content]`;
            textContentInput.id = `chapter_text_content_${indexForNames}`;
            textContentInput.value = chapterData.text_content || '';
        }

        const ttsVoiceSelect = chapterDiv.querySelector('.chapter-tts-voice-select-js');
        if (ttsVoiceSelect) {
            ttsVoiceSelect.name = `chapters[${indexForNames}][tts_voice]`;
            ttsVoiceSelect.id = `chapter_tts_voice_${indexForNames}`;
            ttsVoiceSelect.value = chapterData.tts_voice || 'default';
        }

        const inputTypeHidden = chapterDiv.querySelector('.chapter-input-type-hidden-js');
        if (inputTypeHidden) {
            inputTypeHidden.name = `chapters[${indexForNames}][input_type]`;
            inputTypeHidden.value = chapterData.generated_tts_audio_url ? 'generated_tts' : (chapterData.input_type || 'file');
        }

        const generatedTtsUrlInput = chapterDiv.querySelector('.chapter-generated-tts-url-input-js');
        const lockedGeneratedAudioDisplay = chapterDiv.querySelector('.locked-generated-audio-display');
        const lockedGeneratedAudioFilenameSpan = chapterDiv.querySelector('.chapter-generated-tts-filename-js');

        if (generatedTtsUrlInput) {
            generatedTtsUrlInput.name = `chapters[${indexForNames}][generated_tts_audio_url]`;
            generatedTtsUrlInput.value = chapterData.generated_tts_audio_url || '';
        }
        if (lockedGeneratedAudioFilenameSpan && chapterData.generated_tts_audio_url) {
            let displayFilename = "Generated Audio";
            try {
                const urlParts = chapterData.generated_tts_audio_url.split('/');
                displayFilename = decodeURIComponent(urlParts.pop() || urlParts.pop() || "Generated_Audio.mp3");
                if (chapterData.tts_voice_display_name) { // Use pre-processed display name if available
                     displayFilename += ` (Voice: ${chapterData.tts_voice_display_name})`;
                } else if (chapterData.tts_voice && chapterData.tts_voice !== 'default') {
                    const voiceName = chapterData.tts_voice.replace('_narrator', '');
                    displayFilename += ` (Voice: ${voiceName.charAt(0).toUpperCase() + voiceName.slice(1)})`;
                }
            } catch(e) { console.warn("Error parsing filename from URL:", chapterData.generated_tts_audio_url, e); }
            lockedGeneratedAudioFilenameSpan.textContent = displayFilename;
        }
        
        const fileUploadControls = chapterDiv.querySelector('.file-upload-controls');
        const ttsGenerationControls = chapterDiv.querySelector('.tts-generation-controls');

        function toggleInputFields(type) { 
            fileUploadControls?.classList.add('hidden');
            ttsGenerationControls?.classList.add('hidden');
            lockedGeneratedAudioDisplay?.classList.add('hidden'); 

            if (audioInput) audioInput.required = false;
            if (textContentInput) textContentInput.required = false;
            if (ttsVoiceSelect) ttsVoiceSelect.required = false;

            if (type === 'file') {
                fileUploadControls?.classList.remove('hidden');
                if (audioInput) audioInput.required = true;
                if (inputTypeHidden) inputTypeHidden.value = 'file'; 
            } else if (type === 'tts') {
                ttsGenerationControls?.classList.remove('hidden');
                if (generatedTtsUrlInput && generatedTtsUrlInput.value) {
                    lockedGeneratedAudioDisplay?.classList.remove('hidden');
                    if (inputTypeHidden) inputTypeHidden.value = 'generated_tts'; 
                    if (chapterData.text_content && textContentInput) textContentInput.value = chapterData.text_content;
                    if (chapterData.tts_voice && ttsVoiceSelect) ttsVoiceSelect.value = chapterData.tts_voice;
                } else {
                    if (textContentInput) textContentInput.required = true;
                    if (ttsVoiceSelect) ttsVoiceSelect.required = true;
                    if (inputTypeHidden) inputTypeHidden.value = 'tts'; 
                }
            }
        }

        chapterDiv.querySelectorAll('.input-type-toggle-btn').forEach(btn => {
            btn.dataset.targetIndex = indexForNames;
            btn.addEventListener('click', function() {
                const currentType = this.dataset.type; 
                chapterDiv.querySelectorAll('.input-type-toggle-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                
                if (currentType === 'file' && generatedTtsUrlInput && generatedTtsUrlInput.value) {
                    generatedTtsUrlInput.value = ''; 
                    if(lockedGeneratedAudioFilenameSpan) lockedGeneratedAudioFilenameSpan.textContent = "Generated Audio"; 
                    const confirmBtn = chapterDiv.querySelector('.confirm-use-generated-audio-btn');
                    if(confirmBtn) confirmBtn.classList.add('hidden');
                    const previewPlayerContainer = chapterDiv.querySelector('.chapter-tts-preview-player-container');
                    if(previewPlayerContainer) previewPlayerContainer.classList.add('hidden');
                    const chapterTtsMessage = chapterDiv.querySelector('.chapter-tts-message');
                    if(chapterTtsMessage) chapterTtsMessage.textContent = '';
                }
                toggleInputFields(currentType);
            });
        });

        let initialTypeForToggle = chapterData.input_type === 'None' ? 'file' : (chapterData.input_type || 'file');
        if (chapterData.generated_tts_audio_url) {
            initialTypeForToggle = 'tts'; 
        }
        
        chapterDiv.querySelectorAll('.input-type-toggle-btn').forEach(btn => {
            if (btn.dataset.type === initialTypeForToggle) btn.classList.add('active');
            else btn.classList.remove('active');
        });
        toggleInputFields(initialTypeForToggle);


        if (audioInput && fileNameSpan) {
            audioInput.addEventListener('change', function(e) {
                const titleErrorEl = chapterDiv.querySelector('.chapter-title-error-js');
                const audioErrorEl = chapterDiv.querySelector('.chapter-audio-error-js');
                if (titleErrorEl) titleErrorEl.textContent = '';
                if (audioErrorEl) audioErrorEl.textContent = '';

                if (e.target.files.length > 0) {
                    const file = e.target.files[0];
                    if (file.size > 50 * 1024 * 1024) { 
                        Swal.fire({ title: 'Audio File Too Large', html: `Chapter audio file must be under <strong>50MB</strong>. <br/>Selected file is ${(file.size / (1024*1024)).toFixed(2)}MB.`, icon: 'error', iconColor: THEME_COLOR_ERROR, confirmButtonColor: THEME_COLOR_PRIMARY, customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal' }});
                        e.target.value = '';
                        fileNameSpan.textContent = 'Choose audio file... (too large)';
                        return;
                    }
                    if (!['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/x-m4a', 'audio/m4a'].includes(file.type)) {
                         Swal.fire({ title: 'Invalid Audio Type', text: 'Please select an MP3, WAV, M4A or OGG audio file.', icon: 'error', iconColor: THEME_COLOR_ERROR, confirmButtonColor: THEME_COLOR_PRIMARY, customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal' }});
                        e.target.value = '';
                        fileNameSpan.textContent = 'Choose audio file... (invalid type)';
                        return;
                    }
                    fileNameSpan.textContent = file.name;
                } else {
                    fileNameSpan.textContent = 'Choose audio file...';
                }
            });
        }

        const generateChapterPreviewBtn = chapterDiv.querySelector('.generate-chapter-tts-preview-btn');
        const chapterTtsPlayerContainer = chapterDiv.querySelector('.chapter-tts-preview-player-container');
        const chapterTtsPlayer = chapterDiv.querySelector('.chapter-tts-preview-player');
        const confirmUseGeneratedAudioBtn = chapterDiv.querySelector('.confirm-use-generated-audio-btn');
        const chapterTtsMessage = chapterDiv.querySelector('.chapter-tts-message');

        if (generateChapterPreviewBtn && chapterTtsPlayer && textContentInput && ttsVoiceSelect && chapterTtsMessage && confirmUseGeneratedAudioBtn && chapterTtsPlayerContainer) {
            generateChapterPreviewBtn.addEventListener('click', async function() {
                const text = textContentInput.value.trim();
                const voiceId = ttsVoiceSelect.value;
                const btnTextEl = this.querySelector('.btn-text');
                const spinnerEl = this.querySelector('.spinner');

                chapterTtsMessage.textContent = '';
                chapterTtsPlayerContainer.classList.add('hidden');
                chapterTtsPlayer.src = '';
                confirmUseGeneratedAudioBtn.classList.add('hidden');
                if(generatedTtsUrlInput) generatedTtsUrlInput.value = ''; 
                if(lockedGeneratedAudioDisplay) lockedGeneratedAudioDisplay.classList.add('hidden');


                let chapterTtsValid = true;
                if (!text) { chapterTtsMessage.textContent = 'Text is required.'; chapterTtsValid = false; }
                else if (text.length < 10) { chapterTtsMessage.textContent = 'Text too short (min 10 chars).'; chapterTtsValid = false; }
                else if (text.length > 5000) { chapterTtsMessage.textContent = 'Text too long (max 5000 chars for preview).'; chapterTtsValid = false; }
                if (voiceId === 'default') { chapterTtsMessage.textContent = (chapterTtsMessage.textContent ? chapterTtsMessage.textContent + ' ' : '') + 'Select a voice.'; chapterTtsValid = false; }
                
                if (!chapterTtsValid) { chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-red-600'; return; }

                this.disabled = true;
                if(btnTextEl) btnTextEl.classList.add('hidden');
                if(spinnerEl) spinnerEl.classList.remove('hidden');
                chapterTtsMessage.textContent = 'Generating preview...';
                chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-indigo-600';

                const formData = new FormData();
                formData.append('text_content', text);
                formData.append('tts_voice_id', voiceId);
                formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

                try {
                    const response = await fetch(generateTtsPreviewUrl, { method: 'POST', body: formData, headers: {'X-CSRFToken': formData.get('csrfmiddlewaretoken')} });
                    const data = await response.json();

                    if (response.ok && data.status === 'success') {
                        chapterTtsPlayer.src = data.audio_url;
                        chapterTtsPlayerContainer.classList.remove('hidden');
                        chapterTtsMessage.textContent = `Preview ready! (${data.filename || 'Generated Audio'})`;
                        chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-green-600';
                        confirmUseGeneratedAudioBtn.classList.remove('hidden');
                        confirmUseGeneratedAudioBtn.dataset.generatedUrl = data.audio_url;
                        confirmUseGeneratedAudioBtn.dataset.generatedVoiceId = data.voice_id_used; 
                        confirmUseGeneratedAudioBtn.dataset.generatedFilename = data.filename || "Generated_Audio.mp3";

                    } else {
                        chapterTtsMessage.textContent = `Error: ${data.message || 'Unknown TTS error.'}`;
                        chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-red-600';
                    }
                } catch (error) {
                    chapterTtsMessage.textContent = 'Network error during TTS preview.';
                    chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-red-600';
                    console.error('Chapter TTS Preview Fetch Error:', error);
                } finally {
                    this.disabled = false;
                    if(btnTextEl) btnTextEl.classList.remove('hidden');
                    if(spinnerEl) spinnerEl.classList.add('hidden');
                }
            });

            confirmUseGeneratedAudioBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsedForThisAudio = this.dataset.generatedVoiceId;
                const filenameUsed = this.dataset.generatedFilename;

                if (urlToUse && generatedTtsUrlInput && lockedGeneratedAudioDisplay && lockedGeneratedAudioFilenameSpan && ttsVoiceSelect && inputTypeHidden) {
                    generatedTtsUrlInput.value = urlToUse; 
                    
                    let displayFilenameText = filenameUsed;
                     if (voiceUsedForThisAudio && voiceUsedForThisAudio !== 'default') {
                        const voiceName = voiceUsedForThisAudio.replace('_narrator', '');
                        displayFilenameText += ` (Voice: ${voiceName.charAt(0).toUpperCase() + voiceName.slice(1)})`;
                    }
                    lockedGeneratedAudioFilenameSpan.textContent = displayFilenameText;
                    
                    ttsVoiceSelect.value = voiceUsedForThisAudio; 
                    inputTypeHidden.value = 'generated_tts'; 
                    
                    lockedGeneratedAudioDisplay.classList.remove('hidden');
                    this.classList.add('hidden'); 
                    chapterTtsPlayerContainer.classList.add('hidden'); 
                    chapterTtsMessage.textContent = 'Audio selected for this chapter!';
                    chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-green-700 font-semibold';
                } else {
                    chapterTtsMessage.textContent = 'Error applying generated audio. Please try again.';
                    chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-red-600';
                }
            });
        }


        const orderInput = chapterDiv.querySelector('.chapter-order-input-js');
        if (orderInput) {
            orderInput.name = `chapters[${indexForNames}][order]`;
            orderInput.value = visualOrder;
        }

        const removeBtn = chapterDiv.querySelector('.remove-chapter-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                const chapterNameToConfirm = titleInput.value || `Chapter ${chapterNumberSpan ? chapterNumberSpan.textContent : 'this'}`;
                Swal.fire({
                    title: 'Remove Chapter?', html: `Are you sure you want to remove <strong>${chapterNameToConfirm}</strong>? <br/>This action cannot be undone.`,
                    icon: 'warning', iconColor: THEME_COLOR_WARNING, showCancelButton: true,
                    confirmButtonText: 'Yes, Remove It!', confirmButtonColor: THEME_COLOR_ERROR,
                    cancelButtonText: 'Keep Chapter', reverseButtons: true,
                    customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal', confirmButton: 'px-5 py-2.5 rounded-lg text-sm font-semibold text-white shadow-md hover:shadow-lg transition-shadow', cancelButton: 'px-5 py-2.5 rounded-lg text-sm font-semibold border border-slate-300 text-slate-700 hover:bg-slate-100 hover:border-slate-400 transition-colors'}
                }).then((result) => {
                    if (result.isConfirmed) {
                        chapterDiv.remove();
                        renumberChaptersInDOM();
                        Swal.fire({ title: 'Chapter Removed!', icon: 'success', iconColor: THEME_COLOR_SUCCESS, timer: 1800, showConfirmButton: false, customClass: { popup: 'rounded-xl shadow-2xl font-sans text-sm', title: 'text-base font-semibold text-slate-800' }});
                    }
                });
            });
        }

        const titleErrorEl = chapterDiv.querySelector('.chapter-title-error-js');
        const audioErrorEl = chapterDiv.querySelector('.chapter-audio-error-js');
        const textErrorEl = chapterDiv.querySelector('.chapter-text-error-js');
        const voiceErrorEl = chapterDiv.querySelector('.chapter-voice-error-js');
        const generatedTtsErrorEl = chapterDiv.querySelector('.chapter-generated-tts-error-js');
        const inputTypeErrorEl = chapterDiv.querySelector('.chapter-input-type-error-js');

        if (chapterData.errors) {
            if (titleErrorEl && chapterData.errors.title) titleErrorEl.textContent = chapterData.errors.title;
            if (audioErrorEl && chapterData.errors.audio_file) audioErrorEl.textContent = chapterData.errors.audio_file;
            if (textErrorEl && chapterData.errors.text_content) textErrorEl.textContent = chapterData.errors.text_content;
            if (voiceErrorEl && chapterData.errors.tts_voice) voiceErrorEl.textContent = chapterData.errors.tts_voice;
            if (generatedTtsErrorEl && chapterData.errors.generated_tts) generatedTtsErrorEl.textContent = chapterData.errors.generated_tts;
            if (inputTypeErrorEl && chapterData.errors.input_type) inputTypeErrorEl.textContent = chapterData.errors.input_type;
        }
    }

    function createAndAppendChapter(indexForNames, chapterData = {}){
        if (!chapterTemplate || !chaptersListContainer) return;
        const templateNode = chapterTemplate.content.cloneNode(true);
        const chapterDiv = templateNode.firstElementChild;
        if (!chapterDiv) return;

        setupChapterCard(chapterDiv, indexForNames, { ...chapterData, isNew: true });
        chaptersListContainer.appendChild(templateNode);
        updateNoChaptersMessage();
        chapterDiv.querySelector('.chapter-title-input-js')?.focus();
        chapterDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function renumberChaptersInDOM() {
        if (!chaptersListContainer) return;
        const existingChapterCards = chaptersListContainer.querySelectorAll('.chapter-card');
        let currentGlobalIndex = 0;

        existingChapterCards.forEach((chapDiv, domOrder) => {
            const visualOrder = domOrder + 1;
            const chapterNumSpan = chapDiv.querySelector('.chapter-number-js');
            if (chapterNumSpan) chapterNumSpan.textContent = visualOrder;

            const titleInput = chapDiv.querySelector('.chapter-title-input-js');
            const titleDisplay = chapDiv.querySelector('.chapter-title-display-js');
            if (titleDisplay && titleInput) {
                titleDisplay.textContent = titleInput.value || `Chapter ${visualOrder}`;
            }

            const orderInput = chapDiv.querySelector('.chapter-order-input-js');
            if (orderInput) {
                orderInput.value = visualOrder;
                const newNameIndex = currentGlobalIndex;

                chapDiv.querySelectorAll('input[name^="chapters["], textarea[name^="chapters["], select[name^="chapters["]').forEach(inputEl => {
                    const oldName = inputEl.name;
                    const fieldNamePart = oldName.substring(oldName.lastIndexOf('['));
                    inputEl.name = `chapters[${newNameIndex}]${fieldNamePart}`;
                    if (inputEl.id) {
                        const oldId = inputEl.id;
                        const idPrefix = oldId.substring(0, oldId.lastIndexOf('_') + 1);
                        if (oldId.substring(oldId.lastIndexOf('_') + 1).match(/^\d+$/) || oldId.substring(oldId.lastIndexOf('_') + 1).startsWith('repop_')) { // Handle repopulated and new
                            inputEl.id = idPrefix + newNameIndex;
                        }
                    }
                });
                chapDiv.dataset.indexJs = newNameIndex;
                currentGlobalIndex++;
            }
        });
        nextChapterIndex = currentGlobalIndex;
        updateNoChaptersMessage();
    }

    function updateNoChaptersMessage() {
        if (!chaptersListContainer || !noChaptersMessage) return;
        const chapterCards = chaptersListContainer.querySelectorAll('.chapter-card');
        if (chapterCards.length === 0) {
            noChaptersMessage.classList.remove('hidden');
        } else {
            noChaptersMessage.classList.add('hidden');
        }
    }

    if (addChapterBtn) {
        addChapterBtn.addEventListener('click', function() {
            createAndAppendChapter(nextChapterIndex, { input_type: 'file' }); 
            renumberChaptersInDOM();
        });
    }

    if (submittedValues && submittedValues.chapters && Array.isArray(submittedValues.chapters)) {
        const sortedSubmittedChapters = [...submittedValues.chapters].sort((a, b) => (parseInt(a.order) || 0) - (parseInt(b.order) || 0));
        sortedSubmittedChapters.forEach((chapterData) => {
            // Use the original_index from submitted_values for consistent naming if available
            const indexToUse = typeof chapterData.original_index !== 'undefined' ? chapterData.original_index : nextChapterIndex;
            createAndAppendChapter(indexToUse, chapterData);
            if (typeof chapterData.original_index === 'undefined') {
                 nextChapterIndex++; // Only increment if it was a truly new index
            }
        });
         // Ensure nextChapterIndex is correctly set after populating from submittedValues
        const allChapterCards = chaptersListContainer.querySelectorAll('.chapter-card');
        nextChapterIndex = allChapterCards.length; 
        renumberChaptersInDOM(); // Renumber after all submitted chapters are added and indices are potentially harmonized
    }
    updateNoChaptersMessage();

    // --- Client-Side Form Validation ---
    function validateFormClientSide() {
        let isValid = true;
        let firstErrorField = null;
        const validationMessages = [];

        function setFirstError(element) {
            if (!firstErrorField && element) firstErrorField = element;
        }

        const requiredFields = [
            { name: 'title', label: 'Audiobook Title', input: form.querySelector('#title') },
            { name: 'author', label: 'Author Name', input: form.querySelector('#author') },
            { name: 'narrator', label: 'Narrator Name', input: form.querySelector('#narrator') },
            // Genre is now dynamic, so we get it from the container
            { name: 'genre', label: 'Genre', input: genreInputContainer.querySelector('#genre') }, 
            { name: 'language', label: 'Language', input: form.querySelector('#language') },
            { name: 'description', label: 'Description', input: form.querySelector('#description') },
        ];
        requiredFields.forEach(field => {
            // Ensure field.input exists before trying to access properties
            if (field.input) {
                if (field.input.required && !field.input.value.trim()) {
                    isValid = false; validationMessages.push(`Please provide the ${field.label}.`); setFirstError(field.input);
                }
            } else if (field.name === 'genre') { // Special case for genre if it wasn't found (e.g. language not selected yet)
                 const langSelect = form.querySelector('#language');
                 if (langSelect && langSelect.value) { // If language is selected, genre should be too
                    isValid = false; validationMessages.push(`Please provide the ${field.label}.`); 
                    setFirstError(langSelect); // Focus language if genre field is missing/disabled
                 }
            }
        });

        const hasExistingCoverPreview = coverImagePreview && coverImagePreview.src && !coverImagePreview.src.includes('placehold.co');
        if (coverImageInput && coverImageInput.files.length === 0 && !hasExistingCoverPreview) {
             isValid = false; validationMessages.push('Please upload a Cover Image.'); setFirstError(coverImageInput);
        }

        const currentPricingType = pricingTypeFreeRadio.checked ? 'free' : 'paid';
        if (currentPricingType === 'paid') {
            if (!priceInput.value || parseFloat(priceInput.value) <= 0) {
                isValid = false; validationMessages.push('Please enter a valid positive price for paid audiobooks.'); setFirstError(priceInput);
            }
        }

        const chapterCards = chaptersListContainer.querySelectorAll('.chapter-card');
        if (chapterCards.length === 0) {
            isValid = false; validationMessages.push('Your audiobook needs at least one chapter.'); setFirstError(addChapterBtn);
        } else {
            chapterCards.forEach((card, index) => {
                const titleInput = card.querySelector('.chapter-title-input-js');
                const audioInput = card.querySelector('.chapter-audio-input-js');
                const textInput = card.querySelector('.chapter-text-content-input-js');
                const voiceSelect = card.querySelector('.chapter-tts-voice-select-js');
                const inputType = card.querySelector('.chapter-input-type-hidden-js')?.value; 
                const generatedUrlInput = card.querySelector('.chapter-generated-tts-url-input-js');

                if (titleInput && !titleInput.value.trim()) {
                    isValid = false; validationMessages.push(`Please enter a title for Chapter ${index + 1}.`); setFirstError(titleInput);
                }

                if (inputType === 'file') {
                    // Check if a file is selected OR if there's a pre-existing file name (from server repopulation)
                    const existingFileNameSpan = card.querySelector('.chapter-filename-js');
                    const hasExistingFile = existingFileNameSpan && existingFileNameSpan.textContent !== 'Choose audio file...' && existingFileNameSpan.textContent !== 'Choose audio file... (too large)' && existingFileNameSpan.textContent !== 'Choose audio file... (invalid type)';

                    if (audioInput && audioInput.required && audioInput.files.length === 0 && !hasExistingFile) {
                        isValid = false; validationMessages.push(`Please select an audio file for Chapter ${index + 1}.`); setFirstError(audioInput.closest('label'));
                    }
                } else if (inputType === 'tts') { 
                    if (textInput && textInput.required && !textInput.value.trim()) {
                        isValid = false; validationMessages.push(`Please enter text for TTS for Chapter ${index + 1}.`); setFirstError(textInput);
                    }
                    if (voiceSelect && voiceSelect.required && voiceSelect.value === 'default') {
                        isValid = false; validationMessages.push(`Please select a narrator voice for TTS for Chapter ${index + 1}.`); setFirstError(voiceSelect);
                    }
                } else if (inputType === 'generated_tts') { 
                    if (!generatedUrlInput || !generatedUrlInput.value) {
                        isValid = false; validationMessages.push(`Confirmed TTS audio is missing for Chapter ${index + 1}. Please re-generate and confirm, or choose another input method.`);
                        setFirstError(card.querySelector('.generate-chapter-tts-preview-btn') || card);
                    }
                    if (voiceSelect && voiceSelect.value === 'default') { 
                         isValid = false; validationMessages.push(`Narrator voice for the confirmed TTS audio is missing for Chapter ${index + 1}.`); setFirstError(voiceSelect);
                    }
                }
            });
        }

        if (!isValid) {
            Swal.fire({
                title: 'Missing Information',
                html: '<ul class="list-disc list-inside text-left text-sm">' + validationMessages.map(msg => `<li>${msg}</li>`).join('') + '</ul>',
                icon: 'warning', iconColor: THEME_COLOR_WARNING, confirmButtonColor: THEME_COLOR_PRIMARY,
                customClass: { popup: 'rounded-xl shadow-2xl font-sans', title: 'text-lg font-semibold text-slate-800', htmlContainer: 'text-slate-600 pt-1 leading-normal' }
            });
            if (firstErrorField) {
                firstErrorField.focus({ preventScroll: true });
                firstErrorField.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
        return isValid;
    }

    // --- Form Submission Handling ---
    if (form) {
        form.addEventListener('submit', function(event) {
            if (isSubmittingAfterDelay) { return; }
            event.preventDefault();
            renumberChaptersInDOM(); // Ensure chapter order and names are up-to-date

            if (!validateFormClientSide()) {
                if (publishButton) publishButton.disabled = false;
                if (publishButtonText) publishButtonText.classList.remove('hidden');
                if (publishingSpinner) {
                    publishingSpinner.classList.add('hidden');
                    publishingSpinner.classList.remove('inline-flex');
                }
                if (loadingOverlay) loadingOverlay.classList.add('hidden');
                if (loaderMessageIntervalId) clearInterval(loaderMessageIntervalId);
                return;
            }

            if (publishButton) publishButton.disabled = true;
            if (publishButtonText) publishButtonText.classList.add('hidden');
            if (publishingSpinner) {
                publishingSpinner.classList.remove('hidden');
                publishingSpinner.classList.add('inline-flex');
            }
            if (loadingOverlay) loadingOverlay.classList.remove('hidden');

            currentLoaderMessageIndex = 0;
            if (loaderMessageElement) {
                loaderMessageElement.textContent = LOADER_MESSAGES[currentLoaderMessageIndex];
            }
            if (loaderMessageIntervalId) clearInterval(loaderMessageIntervalId);
            loaderMessageIntervalId = setInterval(() => {
                currentLoaderMessageIndex = (currentLoaderMessageIndex + 1) % LOADER_MESSAGES.length;
                if (loaderMessageElement) {
                    loaderMessageElement.textContent = LOADER_MESSAGES[currentLoaderMessageIndex];
                }
            }, 1250);

            // A small delay to allow the user to see the loading message before actual submission
            setTimeout(() => {
                if (loaderMessageIntervalId) {
                    clearInterval(loaderMessageIntervalId);
                }
                isSubmittingAfterDelay = true; // Set flag to prevent re-validation
                form.submit();
            }, 2000); // 2-second delay
        });
    }

    // --- Django Messages Handling ---
    const djangoMessagesElement = document.getElementById('django-messages-data');
    if (djangoMessagesElement && typeof Swal !== 'undefined') {
        try {
            const messages = JSON.parse(djangoMessagesElement.textContent || '[]');
            if (messages.length > 0) {
                const Toast = Swal.mixin({
                    toast: true, position: 'top-end', showConfirmButton: false, timer: 5000, timerProgressBar: true,
                    didOpen: (toast) => {
                        toast.addEventListener('mouseenter', Swal.stopTimer);
                        toast.addEventListener('mouseleave', Swal.resumeTimer);
                    }
                });
                messages.forEach(message => {
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
            console.error("Error parsing or displaying Django messages:", e);
        }
    }
});
