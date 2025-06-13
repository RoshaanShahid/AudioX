document.addEventListener('DOMContentLoaded', function() {
    const THEME_COLOR_PRIMARY = '#091e65';
    const THEME_COLOR_ERROR = '#ef4444';
    const THEME_COLOR_SUCCESS = '#10b981';
    const THEME_COLOR_WARNING = '#f97316';
    const GENRE_OTHER_VALUE = '_OTHER_';

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

    // --- CSRF Token definition: Define as a function to ensure it's always fresh ---
    function getCsrfToken() {
        const tokenElement = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenElement) {
            return tokenElement.value.trim();
        }
        console.error("CSRF token element not found!");
        return '';
    }

    const form = document.getElementById('audiobookUploadForm');
    const coverImageInput = document.getElementById('cover_image');
    const coverImagePreview = document.getElementById('coverImagePreview');
    const coverImageNameDisplay = document.getElementById('coverImageNameDisplay');
    const coverUploadPlaceholder = document.getElementById('coverUploadPlaceholder');
    const coverUploadInitialText = document.getElementById('coverUploadInitialText');
    const coverChangeText = document.getElementById('coverChangeText');
    const coverPreviewContainer = document.getElementById('coverPreviewContainer');

    const pricingTypeFreeBtn = document.getElementById('pricingTypeFreeBtn');
    const pricingTypePaidBtn = document.getElementById('pricingTypePaidBtn');
    const pricingTypeFreeRadio = document.getElementById('pricing_type_free_radio');
    const pricingTypePaidRadio = document.getElementById('pricing_type_paid_radio');
    const priceInputContainer = document.getElementById('priceInputContainer');
    const priceInput = document.getElementById('price');

    const languageSelect = document.getElementById('language');
    const genreInputContainer = document.getElementById('genreInputContainer');

    const addChapterBtn = document.getElementById('addChapterBtn');
    const chaptersListContainer = document.getElementById('chaptersListContainer');
    const chapterTemplate = document.getElementById('chapterTemplate');
    const noChaptersMessage = document.getElementById('noChaptersMessage');

    const publishButton = document.getElementById('publishButton');
    const publishButtonText = document.getElementById('publishButtonText');
    const publishingSpinner = document.getElementById('publishingSpinner');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const loaderMessageElement = document.getElementById('loaderMessage');

    const generateTtsPreviewUrl = document.getElementById('generate-tts-preview-url')?.textContent.trim();
    const generateDocumentTtsPreviewUrl = document.getElementById('generate-document-tts-preview-url')?.textContent.trim();

    let edgeTtsVoicesByLang = {};
    let ALL_EDGE_TTS_VOICES_MAP = {};
    let languageGenreMapping = {};

    try {
        const ttsVoicesDataElement = document.getElementById('edge-tts-voices-data');
        if (ttsVoicesDataElement) {
            edgeTtsVoicesByLang = JSON.parse(ttsVoicesDataElement.textContent || '{}');
            for (const lang in edgeTtsVoicesByLang) {
                if (edgeTtsVoicesByLang.hasOwnProperty(lang)) {
                    edgeTtsVoicesByLang[lang].forEach(voice => {
                        ALL_EDGE_TTS_VOICES_MAP[voice.id] = voice;
                    });
                }
            }
        }
        const genreMappingDataElement = document.getElementById('language-genre-mapping-data');
        if (genreMappingDataElement) {
            languageGenreMapping = JSON.parse(genreMappingDataElement.textContent || '{}');
        }
    } catch (e) {
        console.error("Error parsing initial JSON data (TTS voices or Genres):", e);
    }
    let currentAudiobookLanguage = document.getElementById('current-audiobook-language-data')?.textContent.trim() || '';

    let nextChapterIndex = 0;
    let isSubmittingAfterDelay = false;

    let formErrors = {};
    let submittedValues = {};
    try {
        const errorsDataElement = document.getElementById('form-errors-data');
        if (errorsDataElement && errorsDataElement.textContent) formErrors = JSON.parse(errorsDataElement.textContent || '{}');
        const submittedDataElement = document.getElementById('submitted-values-data');
        if (submittedDataElement && submittedDataElement.textContent) {
            submittedValues = JSON.parse(submittedDataElement.textContent || '{}');
        }
    } catch (e) {
        console.error("Error parsing initial form data from script tags:", e);
    }

    if (submittedValues.language) {
        currentAudiobookLanguage = submittedValues.language;
    }

    if (coverImageInput && coverImagePreview && coverImageNameDisplay && coverUploadInitialText && coverChangeText && coverPreviewContainer) {
        coverImageInput.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file) {
                if (file.size > 2 * 1024 * 1024) { // Max 2MB
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
    updatePricingUI(submittedValues.pricing_type || (pricingTypePaidRadio && pricingTypePaidRadio.checked ? 'paid' : 'free'));

    function updateGenreField(selectedLanguage) {
        if (!genreInputContainer) return;
        genreInputContainer.innerHTML = '';

        const label = document.createElement('label');
        label.htmlFor = 'genre';
        label.className = 'block text-sm font-medium text-slate-700 mb-1.5';
        label.innerHTML = 'Genre <span class="text-red-600">*</span>';
        genreInputContainer.appendChild(label);

        const genresForLanguage = languageGenreMapping[selectedLanguage];
        const helperTextElement = document.createElement('p');
        helperTextElement.className = 'text-xs text-slate-500 mt-1';
        helperTextElement.id = 'genre_helper_text';

        const errorTextElement = document.createElement('p');
        errorTextElement.className = 'text-red-500 text-sm mt-1';
        errorTextElement.id = 'genre_error_message';

        const otherInputContainer = document.createElement('div');
        otherInputContainer.id = 'genre_other_input_container';
        otherInputContainer.className = 'mt-2 hidden';

        const otherInput = document.createElement('input');
        otherInput.type = 'text';
        otherInput.name = 'genre_other_text';
        otherInput.id = 'genre_other_text_input';
        otherInput.className = 'block w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-[#091e65]/70 focus:border-[#091e65] sm:text-sm placeholder-slate-400 transition duration-150 ease-in-out shadow-sm';
        otherInput.placeholder = 'Specify other genre';
        otherInputContainer.appendChild(otherInput);

        if (selectedLanguage && genresForLanguage && Array.isArray(genresForLanguage) && genresForLanguage.length > 0) {
            const select = document.createElement('select');
            select.name = 'genre';
            select.id = 'genre';
            select.required = true;
            select.className = 'block w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-[#091e65]/70 focus:border-[#091e65] sm:text-sm appearance-none bg-no-repeat transition duration-150 ease-in-out text-slate-700 shadow-sm';

            const defaultOption = document.createElement('option');
            defaultOption.value = "";
            defaultOption.textContent = "Select Genre...";
            defaultOption.disabled = true;
            select.appendChild(defaultOption);

            genresForLanguage.forEach(genreInfo => {
                const option = document.createElement('option');
                option.value = genreInfo.value;
                option.textContent = genreInfo.text;
                select.appendChild(option);
            });

            const otherOption = document.createElement('option');
            otherOption.value = GENRE_OTHER_VALUE;
            otherOption.textContent = "Others";
            select.appendChild(otherOption);

            genreInputContainer.appendChild(select);
            helperTextElement.textContent = `Select the most fitting genre for your ${selectedLanguage} audiobook, or choose "Others".`;

            select.addEventListener('change', function() {
                if (this.value === GENRE_OTHER_VALUE) {
                    otherInputContainer.classList.remove('hidden');
                    otherInput.required = true;
                    otherInput.focus();
                } else {
                    otherInputContainer.classList.add('hidden');
                    otherInput.required = false;
                    otherInput.value = '';
                }
            });

            if (submittedValues.genre_other_text && submittedValues.genre === GENRE_OTHER_VALUE) {
                select.value = GENRE_OTHER_VALUE;
                otherInput.value = submittedValues.genre_other_text;
                otherInputContainer.classList.remove('hidden');
                otherInput.required = true;
            } else if (submittedValues.genre) {
                select.value = submittedValues.genre;
                if(select.value === GENRE_OTHER_VALUE) {
                    otherInputContainer.classList.remove('hidden');
                    otherInput.required = true;
                }
            } else {
                select.value = "";
            }
        } else if (selectedLanguage) {
            const textField = document.createElement('input');
            textField.type = 'text';
            textField.name = 'genre';
            textField.id = 'genre';
            textField.required = true;
            textField.className = 'block w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-[#091e65]/70 focus:border-[#091e65] sm:text-sm placeholder-slate-400 transition duration-150 ease-in-out shadow-sm';
            textField.placeholder = `Enter genre for ${selectedLanguage}`;
            genreInputContainer.appendChild(textField);
            helperTextElement.textContent = `Please specify the genre for your ${selectedLanguage} audiobook.`;
            if (submittedValues.genre && !languageGenreMapping[selectedLanguage]) {
                textField.value = submittedValues.genre;
            }
        } else {
            const placeholderInput = document.createElement('input');
            placeholderInput.type = 'text';
            placeholderInput.id = 'genre_placeholder';
            placeholderInput.name = 'genre_placeholder';
            placeholderInput.className = 'block w-full px-4 py-3 border border-slate-300 rounded-xl focus:ring-2 focus:ring-[#091e65]/70 focus:border-[#091e65] sm:text-sm placeholder-slate-400 transition duration-150 ease-in-out shadow-sm bg-slate-50 cursor-not-allowed';
            placeholderInput.placeholder = 'Select language first';
            placeholderInput.disabled = true;
            genreInputContainer.appendChild(placeholderInput);
            helperTextElement.textContent = 'Please select a language to see genre options.';
        }

        genreInputContainer.appendChild(helperTextElement);
        genreInputContainer.appendChild(otherInputContainer);
        genreInputContainer.appendChild(errorTextElement);

        if (formErrors.genre && errorTextElement) {
            errorTextElement.textContent = formErrors.genre;
        }
        if (formErrors.genre_other_text && errorTextElement) {
            errorTextElement.textContent += (errorTextElement.textContent ? " " : "") + formErrors.genre_other_text;
        }
    }

    function updateChapterPreviewButtonState(chapterCardDiv) {
        const inputTypeHidden = chapterCardDiv.querySelector('.chapter-input-type-hidden-js');
        if (!inputTypeHidden) return;
        const currentInputType = inputTypeHidden.value;

        const textInput = chapterCardDiv.querySelector('.chapter-text-content-input-js');
        const voiceSelect = chapterCardDiv.querySelector('.chapter-tts-voice-select-js');
        const previewBtn = chapterCardDiv.querySelector('.generate-chapter-tts-preview-btn');

        const docInput = chapterCardDiv.querySelector('.chapter-document-input-js');
        const docTtsVoiceSelect = chapterCardDiv.querySelector('.chapter-doc-tts-voice-select-js');
        const docPreviewBtn = chapterCardDiv.querySelector('.generate-document-tts-preview-btn');

        // Logic for Text-to-Speech (manual text)
        if (currentInputType === 'tts') {
            if (previewBtn && textInput && voiceSelect) {
                const isLangSelected = currentAudiobookLanguage && currentAudiobookLanguage !== "";
                const voicesForLang = isLangSelected ? edgeTtsVoicesByLang[currentAudiobookLanguage] : null;
                const areVoicesAvailable = !!(voicesForLang && voicesForLang.length > 0);
                const isVoiceSelected = voiceSelect.value && voiceSelect.value !== 'default' && voiceSelect.value !== "";
                const isTextValid = textInput.value.trim().length >= 10 && textInput.value.trim().length <= 5000;
                previewBtn.disabled = !(isLangSelected && areVoicesAvailable && isVoiceSelected && isTextValid);
            } else if (previewBtn) {
                previewBtn.disabled = true;
            }
        } else if (previewBtn) {
            previewBtn.disabled = true;
        }

        // Logic for Document-to-Speech
        if (currentInputType === 'document_tts') {
            if (docPreviewBtn && docInput && docTtsVoiceSelect) {
                const isLangSelected = currentAudiobookLanguage && currentAudiobookLanguage !== "";
                const voicesForLang = isLangSelected ? edgeTtsVoicesByLang[currentAudiobookLanguage] : null;
                const areVoicesAvailable = !!(voicesForLang && voicesForLang.length > 0);
                const isDocVoiceSelected = docTtsVoiceSelect.value && docTtsVoiceSelect.value !== 'default' && docTtsVoiceSelect.value !== "";
                const isDocFileSelected = docInput.files && docInput.files.length > 0;
                docPreviewBtn.disabled = !(isLangSelected && areVoicesAvailable && isDocVoiceSelected && isDocFileSelected);
            } else if (docPreviewBtn) {
                docPreviewBtn.disabled = true;
            }
        } else if (docPreviewBtn) {
            docPreviewBtn.disabled = true;
        }
    }

    function populateChapterTtsVoices(chapterCardDiv, audiobookLang, selectedTtsVoiceId, isForDocument = false) {
        const voiceSelectClass = isForDocument ? '.chapter-doc-tts-voice-select-js' : '.chapter-tts-voice-select-js';
        const unavailableMsgClass = isForDocument ? '.chapter-doc-tts-unavailable-message-js' : '.chapter-tts-unavailable-message-js';

        const ttsVoiceSelect = chapterCardDiv.querySelector(voiceSelectClass);
        const unavailableMsg = chapterCardDiv.querySelector(unavailableMsgClass);

        if (!ttsVoiceSelect || !unavailableMsg) return;

        ttsVoiceSelect.innerHTML = '';
        unavailableMsg.classList.add('hidden');
        ttsVoiceSelect.disabled = true;

        if (!audiobookLang) {
            const defaultOpt = document.createElement('option');
            defaultOpt.value = "";
            defaultOpt.textContent = "Select Audiobook Language First...";
            ttsVoiceSelect.appendChild(defaultOpt);
            updateChapterPreviewButtonState(chapterCardDiv);
            return;
        }

        const voicesForLang = edgeTtsVoicesByLang[audiobookLang];

        if (!voicesForLang) {
            const errOpt = document.createElement('option');
            errOpt.value = ""; errOpt.textContent = "TTS Error: Lang not configured";
            ttsVoiceSelect.appendChild(errOpt);
            updateChapterPreviewButtonState(chapterCardDiv);
            return;
        }

        if (voicesForLang.length === 0) {
            const noTtsOpt = document.createElement('option');
            noTtsOpt.value = ""; noTtsOpt.textContent = "TTS Not Available for this Language";
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
                option.dataset.gender = voice.gender; // Store gender for validation if needed
                ttsVoiceSelect.appendChild(option);
            });

            if (selectedTtsVoiceId && voicesForLang.some(v => v.id === selectedTtsVoiceId)) {
                ttsVoiceSelect.value = selectedTtsVoiceId;
            } else {
                ttsVoiceSelect.value = "default";
            }
        }
        updateChapterPreviewButtonState(chapterCardDiv);
    }

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
        const baseMessageClasses = 'text-xs my-2 min-h-[16px]';

        messageEl.textContent = '';
        playerContainer.classList.add('hidden');
        player.src = '';
        if (confirmUseBtn) confirmUseBtn.classList.add('hidden');
        if (generatedUrlInputForChapter) generatedUrlInputForChapter.value = '';
        if (lockedDisplayForChapter) {
            lockedDisplayForChapter.classList.add('hidden');
        }

        let isValid = true;
        let errorMessages = [];
        if (!text) { errorMessages.push('Text is required.'); isValid = false; }
        else if (text.length < 10) { errorMessages.push('Text too short (min 10 chars).'); isValid = false; }
        else if (text.length > 5000) { errorMessages.push('Text too long (max 5000 chars for preview).'); isValid = false; }
        if (voiceOptionId === 'default' || !voiceOptionId) {
            errorMessages.push('Select a voice.');
            isValid = false;
        }

        if (!isValid) {
            messageEl.textContent = errorMessages.join(' ');
            messageEl.className = `chapter-tts-message ${baseMessageClasses} text-red-600`;
            return;
        }

        generateBtn.disabled = true;
        if(btnTextEl) btnTextEl.classList.add('hidden');
        if(spinnerEl) spinnerEl.classList.remove('hidden');
        messageEl.textContent = 'Generating preview...';
        messageEl.className = `chapter-tts-message ${baseMessageClasses} text-indigo-600`;

        const formData = new FormData();
        formData.append('text_content', text);
        formData.append('tts_voice_id', voiceOptionId);
        formData.append('audiobook_language', currentAudiobookLanguage);
        formData.append('csrfmiddlewaretoken', getCsrfToken()); // Use the getCsrfToken function here

        try {
            if (!generateTtsPreviewUrl) throw new Error("TTS Preview URL is not defined.");
            const response = await fetch(generateTtsPreviewUrl, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCsrfToken() // Use the getCsrfToken function here
                }
            });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                player.src = data.audio_url;
                playerContainer.classList.remove('hidden');
                messageEl.textContent = `Preview ready! (${data.filename || 'Generated Audio'})`;
                messageEl.className = `chapter-tts-message ${baseMessageClasses} text-green-600`;
                if (confirmUseBtn) {
                    confirmUseBtn.classList.remove('hidden');
                    confirmUseBtn.dataset.generatedUrl = data.audio_url;
                    confirmUseBtn.dataset.generatedVoiceId = data.voice_id_used;
                    confirmUseBtn.dataset.generatedFilename = data.filename || "Generated_Audio.mp3";
                }
            } else {
                messageEl.textContent = `Error: ${data.message || 'Unknown TTS error.'}`;
                messageEl.className = `chapter-tts-message ${baseMessageClasses} text-red-600`;
            }
        } catch (error) {
            messageEl.textContent = 'Network error during TTS preview.';
            messageEl.className = `chapter-tts-message ${baseMessageClasses} text-red-600`;
        } finally {
            generateBtn.disabled = false;
            if(btnTextEl) btnTextEl.classList.remove('hidden');
            if(spinnerEl) spinnerEl.classList.add('hidden');
            updateChapterPreviewButtonState(chapterForm);
        }
    }

    async function generateChapterDocumentTtsPreview(params) {
        const {
            chapterForm,
            documentInput, docVoiceSelect,
            playerContainer, player, messageEl,
            confirmUseBtn, generateBtn,
            lockedDisplay, lockedFilenameSpan
        } = params;

        const docFile = documentInput.files[0];
        const voiceOptionId = docVoiceSelect.value;
        const selectedVoiceDetails = ALL_EDGE_TTS_VOICES_MAP[voiceOptionId];
        const narratorGender = selectedVoiceDetails ? selectedVoiceDetails.gender.toLowerCase() : '';

        const btnTextEl = generateBtn.querySelector('.btn-text');
        const spinnerEl = generateBtn.querySelector('.spinner');
        const baseMessageClasses = 'text-xs my-2 min-h-[16px]';

        messageEl.textContent = '';
        playerContainer.classList.add('hidden');
        player.src = '';
        if (confirmUseBtn) confirmUseBtn.classList.add('hidden');
        if (lockedDisplay) {
            lockedDisplay.classList.add('hidden');
        }

        let isValid = true;
        let errorMessagesDoc = [];
        if (!docFile) { errorMessagesDoc.push('Please select a document file.'); isValid = false; }
        if (voiceOptionId === 'default' || !voiceOptionId) {
            errorMessagesDoc.push('Select a narrator voice.');
            isValid = false;
        }
        if (currentAudiobookLanguage && ['English', 'Urdu', 'Punjabi', 'Sindhi'].includes(currentAudiobookLanguage)) {
             if (!selectedVoiceDetails || !selectedVoiceDetails.gender) {
                errorMessagesDoc.push(`A voice with a defined gender must be selected for ${currentAudiobookLanguage}.`);
                isValid = false;
            }
        }


        if (docFile) {
            const maxSize = 10 * 1024 * 1024;
            const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
            const allowedExtensions = ['.pdf', '.doc', '.docx'];
            const fileExtension = docFile.name.substring(docFile.name.lastIndexOf('.')).toLowerCase();
            if (docFile.size > maxSize) { errorMessagesDoc.push('Document too large (Max 10MB).'); isValid = false;}
            if (!allowedTypes.includes(docFile.type) && !allowedExtensions.includes(fileExtension)) { errorMessagesDoc.push('Invalid document type (PDF, DOC, DOCX).'); isValid = false;}
        }

        if (!isValid) {
            messageEl.textContent = errorMessagesDoc.join(' ');
            messageEl.className = `chapter-document-tts-message ${baseMessageClasses} text-red-600`;
            return;
        }

        generateBtn.disabled = true;
        if(btnTextEl) btnTextEl.classList.add('hidden');
        if(spinnerEl) spinnerEl.classList.remove('hidden');
        messageEl.textContent = 'Processing document & generating preview...';
        messageEl.className = `chapter-document-tts-message ${baseMessageClasses} text-indigo-600`;

        const formData = new FormData();
        formData.append('document_file', docFile);
        formData.append('tts_voice_id', voiceOptionId); // This is the actual voice ID
        formData.append('language', currentAudiobookLanguage);
        formData.append('narrator_gender', narratorGender); // Pass gender explicitly if needed by backend API.
        // Using the global csrfToken variable
        formData.append('csrfmiddlewaretoken', getCsrfToken());


        try {
            const urlToFetch = generateDocumentTtsPreviewUrl;
            if (!urlToFetch) {
                throw new Error("Document TTS Preview URL is not defined.");
            }
            const response = await fetch(urlToFetch, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-CSRFToken': getCsrfToken() // Use the getCsrfToken function here
                }
            });
            const data = await response.json(); // Expect JSON response

            if (response.ok && data.status === 'success') {
                player.src = data.audio_url; // Use URL from JSON
                playerContainer.classList.remove('hidden');
                messageEl.textContent = `Preview ready! (From: ${data.source_filename || docFile.name || 'document'})`;
                messageEl.className = `chapter-document-tts-message ${baseMessageClasses} text-green-600`;
                if (confirmUseBtn) {
                    confirmUseBtn.classList.remove('hidden');
                    confirmUseBtn.dataset.generatedUrl = data.audio_url; // Store server URL
                    confirmUseBtn.dataset.generatedVoiceId = data.voice_id_used;
                    confirmUseBtn.dataset.generatedFilename = data.filename;
                    confirmUseBtn.dataset.sourceDocumentName = data.source_filename || docFile.name;
                }
            } else {
                let backendErrorMsg = data.message || 'Unknown document TTS error.';
                if (data.errors && typeof data.errors === 'object') {
                    const errorKey = Object.keys(data.errors)[0];
                    if (errorKey && data.errors[errorKey] && Array.isArray(data.errors[errorKey]) && data.errors[errorKey].length > 0) {
                        const firstError = data.errors[errorKey][0];
                        if (typeof firstError === 'string') { backendErrorMsg = firstError; }
                        else if (firstError && firstError.message) { backendErrorMsg = firstError.message; }
                    }
                }
                messageEl.textContent = `Error: ${backendErrorMsg}`;
                messageEl.className = `chapter-document-tts-message ${baseMessageClasses} text-red-600`;
            }
        } catch (error) {
            console.error("Error in generateChapterDocumentTtsPreview fetch:", error);
            messageEl.textContent = 'Network error or issue processing request for document TTS preview.';
            messageEl.className = `chapter-document-tts-message ${baseMessageClasses} text-red-600`;
        } finally {
            generateBtn.disabled = false;
            if(btnTextEl) btnTextEl.classList.remove('hidden');
            if(spinnerEl) spinnerEl.classList.add('hidden');
            updateChapterPreviewButtonState(chapterForm);
        }
    }

    function setupChapterCard(chapterDiv, indexForNames, chapterData = {}) {
        const visualOrder = chapterData.order || (chaptersListContainer.querySelectorAll('.chapter-card').length + (chapterData.isNew ? 0 : 1));
        chapterDiv.dataset.indexJs = indexForNames;

        const chapterNumberSpan = chapterDiv.querySelector('.chapter-number-js');
        const chapterTitleDisplay = chapterDiv.querySelector('.chapter-title-display-js');
        const titleInput = chapterDiv.querySelector('.chapter-title-input-js');

        const audioInput = chapterDiv.querySelector('.chapter-audio-input-js');
        const fileNameSpan = chapterDiv.querySelector('.chapter-filename-js');

        const textContentInput = chapterDiv.querySelector('.chapter-text-content-input-js');
        const ttsVoiceSelect = chapterDiv.querySelector('.chapter-tts-voice-select-js');

        const documentInput = chapterDiv.querySelector('.chapter-document-input-js');
        const documentFileNameSpan = chapterDiv.querySelector('.chapter-document-filename-js');
        const docTtsVoiceSelect = chapterDiv.querySelector('.chapter-doc-tts-voice-select-js');

        const inputTypeHidden = chapterDiv.querySelector('.chapter-input-type-hidden-js');
        const generatedTtsUrlInput = chapterDiv.querySelector('.chapter-generated-tts-url-input-js');
        const generatedDocUrlInput = chapterDiv.querySelector('.chapter-generated-document-tts-url-input-js');

        const lockedGeneratedAudioDisplay = chapterDiv.querySelector('.locked-generated-audio-display');
        const lockedGeneratedAudioFilenameSpan = chapterDiv.querySelector('.chapter-generated-tts-filename-js');

        const fileUploadControls = chapterDiv.querySelector('.file-upload-controls');
        const ttsGenerationControls = chapterDiv.querySelector('.tts-generation-controls');
        const documentTtsControls = chapterDiv.querySelector('.document-tts-controls');

        const generateChapterPreviewBtn = chapterDiv.querySelector('.generate-chapter-tts-preview-btn');
        const chapterTtsPlayerContainer = chapterDiv.querySelector('.chapter-tts-preview-player-container');
        const chapterTtsPlayer = chapterDiv.querySelector('.chapter-tts-preview-player');
        const confirmUseGeneratedAudioBtn = chapterDiv.querySelector('.confirm-use-generated-audio-btn');
        const chapterTtsMessage = chapterDiv.querySelector('.chapter-tts-message');

        const generateDocumentPreviewBtn = chapterDiv.querySelector('.generate-document-tts-preview-btn');
        const documentTtsPlayerContainer = chapterDiv.querySelector('.document-tts-preview-player-container');
        const documentTtsPlayer = chapterDiv.querySelector('.document-tts-preview-player');
        const confirmUseDocumentAudioBtn = chapterDiv.querySelector('.confirm-use-document-audio-btn');
        const documentTtsMessage = chapterDiv.querySelector('.chapter-document-tts-message');

        const orderInput = chapterDiv.querySelector('.chapter-order-input-js');
        const removeBtn = chapterDiv.querySelector('.remove-chapter-btn');

        if (chapterNumberSpan) chapterNumberSpan.textContent = visualOrder;
        if (chapterTitleDisplay) chapterTitleDisplay.textContent = chapterData.title || `Chapter ${visualOrder}`;

        if (titleInput) {
            titleInput.name = `chapters[${indexForNames}][title]`;
            titleInput.id = `chapter_title_${indexForNames}`;
            titleInput.value = chapterData.title || '';
            titleInput.addEventListener('input', function() {
                if (chapterTitleDisplay) chapterTitleDisplay.textContent = this.value || `Chapter ${visualOrder}`;
            });
        }

        if (audioInput) {
            audioInput.name = `chapters[${indexForNames}][audio_file]`;
            audioInput.id = `chapter_audio_${indexForNames}`;
        }
        if (fileNameSpan) {
            fileNameSpan.textContent = (chapterData.audio_filename && chapterData.audio_filename !== "No file chosen") ? chapterData.audio_filename : 'Choose audio file...';
        }

        if (textContentInput) {
            textContentInput.name = `chapters[${indexForNames}][text_content]`;
            textContentInput.id = `chapter_text_content_${indexForNames}`;
            textContentInput.value = chapterData.text_content || '';
            textContentInput.addEventListener('input', () => updateChapterPreviewButtonState(chapterDiv));
        }

        if (ttsVoiceSelect) {
            ttsVoiceSelect.name = `chapters[${indexForNames}][tts_voice]`;
            ttsVoiceSelect.id = `chapter_tts_voice_${indexForNames}`;
            populateChapterTtsVoices(chapterDiv, currentAudiobookLanguage, chapterData.tts_voice, false);
            ttsVoiceSelect.addEventListener('change', () => updateChapterPreviewButtonState(chapterDiv));
        }

        if (documentInput) {
            documentInput.name = `chapters[${indexForNames}][document_file]`;
            documentInput.id = `chapter_document_${indexForNames}`;
            documentInput.addEventListener('change', () => updateChapterPreviewButtonState(chapterDiv));
        }
        if (documentFileNameSpan) {
            documentFileNameSpan.textContent = chapterData.document_filename || 'No document chosen';
        }
        if (docTtsVoiceSelect) {
            docTtsVoiceSelect.name = `chapters[${indexForNames}][doc_tts_voice]`;
            docTtsVoiceSelect.id = `chapter_doc_tts_voice_${indexForNames}`;
            populateChapterTtsVoices(chapterDiv, currentAudiobookLanguage, chapterData.doc_tts_voice, true);
            docTtsVoiceSelect.addEventListener('change', () => updateChapterPreviewButtonState(chapterDiv));
        }

        if (inputTypeHidden) {
            inputTypeHidden.name = `chapters[${indexForNames}][input_type]`;
            let initialInputType = chapterData.input_type || 'file';
            if (chapterData.input_type === 'None') initialInputType = 'file';
            if (chapterData.generated_tts_audio_url && (initialInputType === 'tts' || initialInputType === 'generated_tts')) {
                initialInputType = 'generated_tts';
            } else if (chapterData.generated_document_tts_audio_url && (initialInputType === 'document_tts' || initialInputType === 'generated_document_tts')) {
                initialInputType = 'generated_document_tts';
            }
            inputTypeHidden.value = initialInputType;
        }

        if (generatedTtsUrlInput) {
            generatedTtsUrlInput.name = `chapters[${indexForNames}][generated_tts_audio_url]`;
            generatedTtsUrlInput.value = chapterData.generated_tts_audio_url || '';
        }
        if (generatedDocUrlInput) {
            generatedDocUrlInput.name = `chapters[${indexForNames}][generated_document_tts_audio_url]`;
            generatedDocUrlInput.value = chapterData.generated_document_tts_audio_url || '';
        }

        if (lockedGeneratedAudioFilenameSpan && (chapterData.generated_tts_audio_url || chapterData.generated_document_tts_audio_url)) {
            let displayFilename = "Generated Audio";
            let voiceForDisplay = null;
            let sourcePrefix = "";
            let originalDocName = chapterData.document_filename || 'document';

            if (chapterData.generated_tts_audio_url) {
                try {
                    const urlParts = chapterData.generated_tts_audio_url.split('/');
                    displayFilename = decodeURIComponent(urlParts.pop() || urlParts.pop() || "Generated_Audio.mp3");
                    voiceForDisplay = chapterData.tts_voice;
                    sourcePrefix = "(from Text): ";
                } catch(e) { console.warn("Error parsing filename from manual TTS URL:", chapterData.generated_tts_audio_url, e); }
            } else if (chapterData.generated_document_tts_audio_url) {
                   try {
                    voiceForDisplay = chapterData.doc_tts_voice; // This is the ID like ur-PK-UzmaNeural
                    sourcePrefix = `(from Doc: ${originalDocName}): `;
                    const urlParts = chapterData.generated_document_tts_audio_url.split('/');
                    displayFilename = decodeURIComponent(urlParts.pop() || urlParts.pop() || "Doc_Generated_Audio.mp3");
                } catch(e) { console.warn("Error processing document TTS display info:", e); }
            }

            if (voiceForDisplay && voiceForDisplay !== 'default') {
                const voiceDetail = ALL_EDGE_TTS_VOICES_MAP[voiceForDisplay];
                if (voiceDetail) {
                    displayFilename = chapterData.generated_document_tts_audio_url ? `${originalDocName} (Voice: ${voiceDetail.name})` : `${displayFilename} (Voice: ${voiceDetail.name})`;
                } else {
                    displayFilename = chapterData.generated_document_tts_audio_url ? `${originalDocName} (Voice ID: ${voiceForDisplay})` : `${displayFilename} (Voice ID: ${voiceForDisplay})`;
                }
            }
            lockedGeneratedAudioFilenameSpan.textContent = sourcePrefix + displayFilename;
        }

        function localToggleInputFields(type) {
            fileUploadControls?.classList.add('hidden');
            ttsGenerationControls?.classList.add('hidden');
            documentTtsControls?.classList.add('hidden');
            lockedGeneratedAudioDisplay?.classList.add('hidden');

            // Reset required attributes
            if (audioInput) audioInput.required = false;
            if (textContentInput) textContentInput.required = false;
            if (ttsVoiceSelect) ttsVoiceSelect.required = false; // Required is handled by populateChapterTtsVoices and updateChapterPreviewButtonState
            if (documentInput) documentInput.required = false;
            if (docTtsVoiceSelect) docTtsVoiceSelect.required = false; // Required is handled by populateChapterTtsVoices and updateChapterPreviewButtonState

            if (type === 'file') {
                fileUploadControls?.classList.remove('hidden');
                if (audioInput) audioInput.required = true;
                if (inputTypeHidden) inputTypeHidden.value = 'file';
            } else if (type === 'tts') {
                ttsGenerationControls?.classList.remove('hidden');
                lockedGeneratedAudioDisplay?.classList.add('hidden');
                if (textContentInput) textContentInput.required = true;
                if (inputTypeHidden) inputTypeHidden.value = 'tts';
            } else if (type === 'document_tts') {
                documentTtsControls?.classList.remove('hidden');
                lockedGeneratedAudioDisplay?.classList.add('hidden');
                if (documentInput) documentInput.required = true;
                if (inputTypeHidden) inputTypeHidden.value = 'document_tts';
            } else if (type === 'generated_tts' || type === 'generated_document_tts') {
                lockedGeneratedAudioDisplay?.classList.remove('hidden');
                ttsGenerationControls?.classList.add('hidden');
                fileUploadControls?.classList.add('hidden');
                documentTtsControls?.classList.add('hidden');
                if (inputTypeHidden) inputTypeHidden.value = type;
            }
            updateChapterPreviewButtonState(chapterDiv);
        }

        chapterDiv.querySelectorAll('.input-type-toggle-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const currentType = this.dataset.type;
                chapterDiv.querySelectorAll('.input-type-toggle-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');

                if (currentType !== 'generated_tts' && generatedTtsUrlInput) {
                    generatedTtsUrlInput.value = '';
                }
                if (currentType !== 'generated_document_tts' && generatedDocUrlInput) {
                    generatedDocUrlInput.value = '';
                }
                if (currentType !== 'tts' && currentType !== 'generated_tts') {
                    if(chapterTtsPlayerContainer) chapterTtsPlayerContainer.classList.add('hidden');
                    if(chapterTtsPlayer) chapterTtsPlayer.src = '';
                    if(chapterTtsMessage) chapterTtsMessage.textContent = '';
                    if(confirmUseGeneratedAudioBtn) confirmUseGeneratedAudioBtn.classList.add('hidden');
                }
                if (currentType !== 'document_tts' && currentType !== 'generated_document_tts') {
                    if(documentTtsPlayerContainer) documentTtsPlayerContainer.classList.add('hidden');
                    if(documentTtsPlayer) documentTtsPlayer.src = '';
                    if(documentTtsMessage) documentTtsMessage.textContent = '';
                    if(confirmUseDocumentAudioBtn) confirmUseDocumentAudioBtn.classList.add('hidden');
                }
                localToggleInputFields(currentType);
            });
        });

        let initialTypeForToggleUI = inputTypeHidden ? inputTypeHidden.value : 'file';
        if (initialTypeForToggleUI === 'generated_tts') {
            initialTypeForToggleUI = 'tts';
        } else if (initialTypeForToggleUI === 'generated_document_tts') {
            initialTypeForToggleUI = 'document_tts';
        }

        chapterDiv.querySelectorAll('.input-type-toggle-btn').forEach(btn => {
            if (btn.dataset.type === initialTypeForToggleUI) btn.classList.add('active');
            else btn.classList.remove('active');
        });
        localToggleInputFields(inputTypeHidden ? inputTypeHidden.value : 'file');


        if (audioInput && fileNameSpan) {
            audioInput.addEventListener('change', function(e) {
                const titleErrorEl = chapterDiv.querySelector('.chapter-title-error-js');
                const audioErrorEl = chapterDiv.querySelector('.chapter-audio-error-js');
                if (titleErrorEl) titleErrorEl.textContent = '';
                if (audioErrorEl) audioErrorEl.textContent = '';

                if (e.target.files.length > 0) {
                    const file = e.target.files[0];
                    if (file.size > 50 * 1024 * 1024) { // Max 50MB
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

        if (documentInput && documentFileNameSpan) {
            documentInput.addEventListener('change', function(e) {
                const docErrorEl = chapterDiv.querySelector('.document-tts-controls .chapter-document-error-js');
                if (docErrorEl) docErrorEl.textContent = '';

                if (e.target.files.length > 0) {
                    const file = e.target.files[0];
                    const maxSize = 10 * 1024 * 1024;
                    const allowedTypes = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
                    const allowedExtensions = ['.pdf', '.doc', '.docx'];
                    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

                    if (file.size > maxSize) {
                        if(docErrorEl) docErrorEl.textContent = `File too large (Max 10MB).`;
                        e.target.value = ''; documentFileNameSpan.textContent = 'No document chosen (too large)';
                        updateChapterPreviewButtonState(chapterDiv); return;
                    }
                    if (!allowedTypes.includes(file.type) && !allowedExtensions.includes(fileExtension)) {
                        if(docErrorEl) docErrorEl.textContent = "Invalid document type (PDF, DOC, DOCX).";
                        e.target.value = ''; documentFileNameSpan.textContent = 'No document chosen (invalid type)';
                        updateChapterPreviewButtonState(chapterDiv); return;
                    }
                    documentFileNameSpan.textContent = file.name;
                } else {
                    documentFileNameSpan.textContent = 'No document chosen';
                }
                updateChapterPreviewButtonState(chapterDiv);
            });
        }

        if (generateChapterPreviewBtn && chapterTtsPlayer && textContentInput && ttsVoiceSelect && chapterTtsMessage && confirmUseGeneratedAudioBtn && chapterTtsPlayerContainer) {
            generateChapterPreviewBtn.addEventListener('click', function() {
                generateChapterTtsPreview({
                    chapterForm: chapterDiv,
                    textContentInput, voiceSelect: ttsVoiceSelect, playerContainer: chapterTtsPlayerContainer, player: chapterTtsPlayer, messageEl: chapterTtsMessage,
                    confirmUseBtn: confirmUseGeneratedAudioBtn, generateBtn: this, generatedUrlInputForChapter: generatedTtsUrlInput,
                    lockedDisplayForChapter: lockedGeneratedAudioDisplay, lockedFilenameSpanForChapter: lockedGeneratedAudioFilenameSpan,
                });
            });
        }
        if (confirmUseGeneratedAudioBtn && generatedTtsUrlInput && lockedGeneratedAudioDisplay && lockedGeneratedAudioFilenameSpan && ttsVoiceSelect && inputTypeHidden) {
            confirmUseGeneratedAudioBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const filenameUsed = this.dataset.generatedFilename;
                if (urlToUse) {
                    generatedTtsUrlInput.value = urlToUse;
                    if(generatedDocUrlInput) generatedDocUrlInput.value = '';
                    let displayFilenameText = filenameUsed;
                    const voiceDetail = ALL_EDGE_TTS_VOICES_MAP[voiceUsed];
                    if (voiceDetail) displayFilenameText += ` (Voice: ${voiceDetail.name})`;
                    lockedGeneratedAudioFilenameSpan.textContent = `(from Text): ${displayFilenameText}`;
                    ttsVoiceSelect.value = voiceUsed;
                    if(chapterTtsMessage) {
                        chapterTtsMessage.textContent = 'Audio selected for this chapter!';
                        chapterTtsMessage.className = 'chapter-tts-message text-xs my-2 min-h-[16px] text-green-700 font-semibold';
                    }
                    this.classList.add('hidden');
                    if(chapterTtsPlayerContainer) chapterTtsPlayerContainer.classList.add('hidden');
                    localToggleInputFields('generated_tts');
                }
            });
        }

        if (generateDocumentPreviewBtn && documentTtsPlayer && documentInput && docTtsVoiceSelect && documentTtsMessage && confirmUseDocumentAudioBtn && documentTtsPlayerContainer) {
            generateDocumentPreviewBtn.addEventListener('click', function() {
                generateChapterDocumentTtsPreview({
                    chapterForm: chapterDiv,
                    documentInput, docVoiceSelect: docTtsVoiceSelect,
                    playerContainer: documentTtsPlayerContainer, player: documentTtsPlayer, messageEl: documentTtsMessage,
                    confirmUseBtn: confirmUseDocumentAudioBtn, generateBtn: this,
                    lockedDisplay: lockedGeneratedAudioDisplay,
                    lockedFilenameSpan: lockedGeneratedAudioFilenameSpan,
                });
            });
        }
        if (confirmUseDocumentAudioBtn && generatedDocUrlInput && lockedGeneratedAudioDisplay && lockedGeneratedAudioFilenameSpan && docTtsVoiceSelect && inputTypeHidden) {
            confirmUseDocumentAudioBtn.addEventListener('click', function() {
                const urlToUse = this.dataset.generatedUrl;
                const voiceUsed = this.dataset.generatedVoiceId;
                const sourceDocName = this.dataset.sourceDocumentName || "document";
                // const generatedFilename = this.dataset.generatedFilename || "Generated_Audio_from_Doc.mp3"; // Filename of the temp .mp3

                if (urlToUse) { // This will be the server URL to the temp audio
                    if (generatedDocUrlInput) generatedDocUrlInput.value = urlToUse;
                    if (generatedTtsUrlInput) generatedTtsUrlInput.value = '';

                    let displayFilenameText;
                    const voiceDetail = ALL_EDGE_TTS_VOICES_MAP[voiceUsed]; // voiceUsed is ID like 'ur-PK-UzmaNeural'
                    if (voiceDetail) {
                        displayFilenameText = `${sourceDocName} (Voice: ${voiceDetail.name})`;
                    } else {
                        displayFilenameText = `${sourceDocName} (Voice ID: ${voiceUsed})`;
                    }
                    lockedGeneratedAudioFilenameSpan.textContent = `(from Doc): ${displayFilenameText}`;

                    docTtsVoiceSelect.value = voiceUsed;
                    if(documentTtsMessage) {
                        documentTtsMessage.textContent = 'Document audio selected!';
                        documentTtsMessage.className = 'chapter-document-tts-message text-xs my-2 min-h-[16px] text-green-700 font-semibold';
                    }
                    this.classList.add('hidden');
                    if(documentTtsPlayerContainer) documentTtsPlayerContainer.classList.add('hidden');
                    localToggleInputFields('generated_document_tts');
                } else {
                    console.error("Confirm button (Doc TTS) clicked but no generated URL found in dataset.");
                    if(documentTtsMessage) {
                        documentTtsMessage.textContent = 'Error: Could not confirm audio. Please try generating again.';
                        documentTtsMessage.className = 'chapter-document-tts-message text-xs my-2 min-h-[16px] text-red-600 font-semibold';
                    }
                }
            });
        }

        if (orderInput) {
            orderInput.name = `chapters[${indexForNames}][order]`;
            orderInput.value = visualOrder;
        }

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
        const ttsGeneralErrorEl = chapterDiv.querySelector('.chapter-tts-general-error-js');
        const generatedTtsErrorEl = chapterDiv.querySelector('.chapter-generated-tts-error-js');
        const inputTypeErrorEl = chapterDiv.querySelector('.chapter-input-type-error-js');
        const documentErrorEl = chapterDiv.querySelector('.chapter-document-error-js');
        const docVoiceErrorEl = chapterDiv.querySelector('.chapter-doc-voice-error-js');
        const docTtsGeneralErrorEl = chapterDiv.querySelector('.chapter-document-tts-general-error-js');
        const generatedDocTtsErrorEl = chapterDiv.querySelector('.chapter-generated-document-tts-error-js');

        if (chapterData.errors) {
            if (titleErrorEl && chapterData.errors.title) titleErrorEl.textContent = chapterData.errors.title;
            if (audioErrorEl && chapterData.errors.audio_file) audioErrorEl.textContent = chapterData.errors.audio_file;
            if (textErrorEl && chapterData.errors.text_content) textErrorEl.textContent = chapterData.errors.text_content;
            if (voiceErrorEl && chapterData.errors.tts_voice) voiceErrorEl.textContent = chapterData.errors.tts_voice;
            if (ttsGeneralErrorEl && chapterData.errors.tts_general) ttsGeneralErrorEl.textContent = chapterData.errors.tts_general;
            if (generatedTtsErrorEl && chapterData.errors.generated_tts) generatedTtsErrorEl.textContent = chapterData.errors.generated_tts;
            if (inputTypeErrorEl && chapterData.errors.input_type) inputTypeErrorEl.textContent = chapterData.errors.input_type;
            if (documentErrorEl && chapterData.errors.document_file) documentErrorEl.textContent = chapterData.errors.document_file;
            if (docVoiceErrorEl && chapterData.errors.doc_tts_voice) docVoiceErrorEl.textContent = chapterData.errors.doc_tts_voice;
            if (docTtsGeneralErrorEl && chapterData.errors.document_tts_general) docTtsGeneralErrorEl.textContent = chapterData.errors.document_tts_general;
            if (generatedDocTtsErrorEl && chapterData.errors.generated_document_tts) generatedDocTtsErrorEl.textContent = chapterData.errors.generated_document_tts;
        }
        updateChapterPreviewButtonState(chapterDiv);
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
                chapDiv.dataset.indexJs = newNameIndex;
                chapDiv.querySelectorAll('input[name^="chapters["], textarea[name^="chapters["], select[name^="chapters["]').forEach(inputEl => {
                    const oldName = inputEl.name;
                    const fieldNamePart = oldName.substring(oldName.lastIndexOf('['));
                    inputEl.name = `chapters[${newNameIndex}]${fieldNamePart}`;
                    if (inputEl.id) {
                        const oldId = inputEl.id;
                        const idPrefix = oldId.substring(0, oldId.lastIndexOf('_') + 1);
                        if (oldId.substring(oldId.lastIndexOf('_') + 1).match(/^\d+$/) || oldId.substring(oldId.lastIndexOf('_') + 1).startsWith('repop_')) {
                            inputEl.id = idPrefix + newNameIndex;
                        }
                    }
                });
                currentGlobalIndex++;
            }
        });
        nextChapterIndex = currentGlobalIndex;
        updateNoChaptersMessage();
    }

    function updateNoChaptersMessage() {
        if (!chaptersListContainer || !noChaptersMessage) return;
        const chapterCards = chaptersListContainer.querySelectorAll('.chapter-card');
        noChaptersMessage.classList.toggle('hidden', chapterCards.length > 0);
    }

    if (languageSelect) {
        languageSelect.addEventListener('change', function() {
            currentAudiobookLanguage = this.value;
            updateGenreField(currentAudiobookLanguage);
            chaptersListContainer.querySelectorAll('.chapter-card').forEach(card => {
                const ttsVoiceSelect = card.querySelector('.chapter-tts-voice-select-js');
                const docTtsVoiceSelect = card.querySelector('.chapter-doc-tts-voice-select-js');
                if (ttsVoiceSelect) {
                    const currentSelectedVoiceInChapter = ttsVoiceSelect.value;
                    populateChapterTtsVoices(card, currentAudiobookLanguage, currentSelectedVoiceInChapter, false);
                }
                if (docTtsVoiceSelect) {
                    const currentSelectedDocVoice = docTtsVoiceSelect.value;
                    populateChapterTtsVoices(card, currentAudiobookLanguage, currentSelectedDocVoice, true);
                }
                updateChapterPreviewButtonState(card);
            });
        });
        updateGenreField(currentAudiobookLanguage || languageSelect.value);

        chaptersListContainer.querySelectorAll('.chapter-card').forEach(card => {
            const ttsVoiceSelect = card.querySelector('.chapter-tts-voice-select-js');
            const docTtsVoiceSelect = card.querySelector('.chapter-doc-tts-voice-select-js');
            const chapterIndex = card.dataset.indexJs;
            let repopulatedVoice = null;
            let repopulatedDocVoice = null;

            if (submittedValues.chapters) {
                const repopChapterData = submittedValues.chapters.find(ch => String(ch.original_index) === String(chapterIndex));
                if (repopChapterData) {
                    repopulatedVoice = repopChapterData.tts_voice;
                    repopulatedDocVoice = repopChapterData.doc_tts_voice;
                }
            }
            if (ttsVoiceSelect) {
                populateChapterTtsVoices(card, currentAudiobookLanguage, repopulatedVoice || ttsVoiceSelect.value, false);
            }
            if (docTtsVoiceSelect) {
                populateChapterTtsVoices(card, currentAudiobookLanguage, repopulatedDocVoice || docTtsVoiceSelect.value, true);
            }
        });
    }

    if (addChapterBtn) {
        addChapterBtn.addEventListener('click', function() {
            createAndAppendChapter(nextChapterIndex, { input_type: 'file' });
            renumberChaptersInDOM();
        });
    }

    if (submittedValues && submittedValues.chapters && Array.isArray(submittedValues.chapters)) {
        const sortedSubmittedChapters = [...submittedValues.chapters].sort((a, b) => (parseInt(a.order) || 0) - (parseInt(b.order) || 0));
        chaptersListContainer.innerHTML = '';
        sortedSubmittedChapters.forEach((chapterData) => {
            const indexToUse = typeof chapterData.original_index !== 'undefined' ? chapterData.original_index : nextChapterIndex;
            createAndAppendChapter(indexToUse, chapterData);
            if (typeof chapterData.original_index !== 'undefined' && chapterData.original_index >= nextChapterIndex) {
                nextChapterIndex = parseInt(chapterData.original_index) + 1;
            }
        });
        renumberChaptersInDOM();
    }
    updateNoChaptersMessage();

    function validateFormClientSide() {
        let isValid = true;
        let firstErrorField = null;
        const validationMessages = [];
        function setFirstError(element) { if (!firstErrorField && element) firstErrorField = element; }

        const requiredFields = [
            { name: 'title', label: 'Audiobook Title', input: form.querySelector('#title') },
            { name: 'author', label: 'Author Name', input: form.querySelector('#author') },
            { name: 'narrator', label: 'Narrator Name', input: form.querySelector('#narrator') },
            { name: 'language', label: 'Language', input: form.querySelector('#language') },
            { name: 'description', label: 'Description', input: form.querySelector('#description') },
        ];

        const genreSelect = genreInputContainer.querySelector('#genre');
        const genreOtherTextInput = genreInputContainer.querySelector('#genre_other_text_input');

        if (genreSelect) {
            if (genreSelect.required && !genreSelect.value) {
                isValid = false; validationMessages.push(`Please select or enter the Genre.`); setFirstError(genreSelect);
            } else if (genreSelect.tagName === 'SELECT' && genreSelect.value === GENRE_OTHER_VALUE) {
                if (genreOtherTextInput && genreOtherTextInput.required && !genreOtherTextInput.value.trim()) {
                    isValid = false; validationMessages.push(`Please specify the "Other" genre.`); setFirstError(genreOtherTextInput);
                }
            }
        } else if (languageSelect && languageSelect.value) {
            isValid = false; validationMessages.push(`Genre information is missing. Please re-select the language.`); setFirstError(languageSelect);
        }

        requiredFields.forEach(field => {
            if (field.input) {
                if (field.input.required && !field.input.value.trim()) {
                    isValid = false; validationMessages.push(`Please provide the ${field.label}.`); setFirstError(field.input);
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
                const documentInput = card.querySelector('.chapter-document-input-js');
                const docVoiceSelect = card.querySelector('.chapter-doc-tts-voice-select-js');
                const inputType = card.querySelector('.chapter-input-type-hidden-js')?.value;
                const generatedTtsUrlInput = card.querySelector('.chapter-generated-tts-url-input-js');
                const generatedDocUrlInput = card.querySelector('.chapter-generated-document-tts-url-input-js'); // Get this input field
                const currentMainLang = languageSelect.value;
                const voicesForCurrentLang = edgeTtsVoicesByLang[currentMainLang];

                if (titleInput && !titleInput.value.trim()) {
                    isValid = false; validationMessages.push(`Please enter a title for Chapter ${index + 1}.`); setFirstError(titleInput);
                }

                if (inputType === 'file') {
                    const existingFileNameSpan = card.querySelector('.chapter-filename-js');
                    const hasExistingFile = existingFileNameSpan &&
                                                 existingFileNameSpan.textContent !== 'Choose audio file...' &&
                                                 !existingFileNameSpan.textContent.includes('(too large)') &&
                                                 !existingFileNameSpan.textContent.includes('(invalid type)');

                    if (audioInput && audioInput.required && audioInput.files.length === 0 && !hasExistingFile) {
                        isValid = false; validationMessages.push(`Please select an audio file for Chapter ${index + 1}.`); setFirstError(audioInput.closest('label'));
                    }
                } else if (inputType === 'tts') {
                    if (voicesForCurrentLang && voicesForCurrentLang.length > 0) {
                        if (textInput && textInput.required && !textInput.value.trim()) {
                            isValid = false; validationMessages.push(`Please enter text for TTS for Chapter ${index + 1}.`); setFirstError(textInput);
                        }
                        if (voiceSelect && voiceSelect.required && (voiceSelect.value === 'default' || !voiceSelect.value)) {
                            isValid = false; validationMessages.push(`Please select a narrator voice for TTS for Chapter ${index + 1}.`); setFirstError(voiceSelect);
                        }
                    } else if (voicesForCurrentLang && voicesForCurrentLang.length === 0) {
                        isValid = false; validationMessages.push(`TTS is not available for ${currentMainLang} in Chapter ${index + 1}. Please upload an audio file.`);
                        setFirstError(card.querySelector('.input-type-toggle-btn[data-type="file"]'));
                    } else if (!voicesForCurrentLang && currentMainLang) {
                           isValid = false; validationMessages.push(`TTS configuration error for ${currentMainLang} in Chapter ${index + 1}.`);
                           setFirstError(languageSelect);
                    }
                } else if (inputType === 'document_tts') {
                    const existingDocNameSpan = card.querySelector('.chapter-document-filename-js');
                    const hasExistingDoc = existingDocNameSpan && existingDocNameSpan.textContent !== 'No document chosen' && !existingDocNameSpan.textContent.includes('(too large)') && !existingDocNameSpan.textContent.includes('(invalid type)');

                    if (documentInput && documentInput.required && documentInput.files.length === 0 && !hasExistingDoc) {
                        isValid = false; validationMessages.push(`Please select a document (PDF/Word) for Chapter ${index + 1}.`); setFirstError(documentInput.closest('label'));
                    }
                     if (docVoiceSelect && docVoiceSelect.required && (docVoiceSelect.value === 'default' || !docVoiceSelect.value)) {
                           isValid = false; validationMessages.push(`Please select a narrator voice for the document in Chapter ${index + 1}.`); setFirstError(docVoiceSelect);
                    }
                } else if (inputType === 'generated_tts') {
                    if (!generatedTtsUrlInput || !generatedTtsUrlInput.value) {
                        isValid = false; validationMessages.push(`Confirmed Text-to-Speech audio URL is missing for Chapter ${index + 1}. Please re-generate and confirm the audio.`);
                        setFirstError(card.querySelector('.generate-chapter-tts-preview-btn') || card);
                    }
                     if (voiceSelect && (voiceSelect.value === 'default' || !voiceSelect.value)) {
                           isValid = false; validationMessages.push(`Narrator voice for the confirmed TTS audio is missing for Chapter ${index + 1}.`); setFirstError(voiceSelect);
                    }
                } else if (inputType === 'generated_document_tts') {
                    if (!generatedDocUrlInput || !generatedDocUrlInput.value) { // This check is now correct
                        isValid = false; validationMessages.push(`Confirmed Document TTS audio URL is missing for Chapter ${index + 1}. Please re-generate and confirm the audio.`);
                        setFirstError(card.querySelector('.generate-document-tts-preview-btn') || card);
                    }
                     if (docVoiceSelect && (docVoiceSelect.value === 'default' || !docVoiceSelect.value)) {
                           isValid = false; validationMessages.push(`Narrator voice for the confirmed Document TTS audio is missing for Chapter ${index + 1}.`); setFirstError(docVoiceSelect);
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

    if (form) {
        form.addEventListener('submit', function(event) {
            if (isSubmittingAfterDelay) { return; }
            event.preventDefault();
            renumberChaptersInDOM();

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

            setTimeout(() => {
                if (loaderMessageIntervalId) {
                    clearInterval(loaderMessageIntervalId);
                }
                isSubmittingAfterDelay = true;
                form.submit();
            }, 2000);
        });
    }

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