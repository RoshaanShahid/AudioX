/**
 * Custom Modal and Withdrawal Request Script
 *
 * Handles the display and interaction of a custom modal component
 * and the validation and submission of a withdrawal request form,
 * including countdown timers for cancellable requests.
 */

document.addEventListener('DOMContentLoaded', function() {

    // --- Modal Elements ---
    // Select elements related to the custom modal
    const modal = document.getElementById('customModal');
    const modalTitleEl = document.getElementById('modalTitle');
    const modalBodyEl = document.getElementById('modalBody');
    const modalIconContainerEl = document.getElementById('modalIconContainer');
    const modalFooterEl = document.getElementById('modalFooter');
    const modalCloseBtnEl = document.getElementById('modalCloseBtn');
    const modalContentWrapper = modal ? modal.querySelector('.modal-content-wrapper') : null;

    /**
     * Shows the custom modal with specified content and behavior.
     * @param {string} title - The title of the modal.
     * @param {string} htmlContent - The HTML content for the modal body.
     * @param {string} [type='info'] - Type of modal ('success', 'error', 'warning', 'question', 'info').
     * @param {Array<Object>} [buttons=[]] - Array of button configurations.
     * Each button object: { text: 'Button Text', class: 'confirm'|'danger'|'cancel', onClick: function }
     */
    window.showModal = function(title, htmlContent, type = 'info', buttons = []) {
        // Check if essential modal elements exist
        if (!modal || !modalTitleEl || !modalBodyEl || !modalIconContainerEl || !modalFooterEl || !modalContentWrapper) {
            // Fallback to browser's alert if modal elements are missing
            alert(title + "\n" + htmlContent.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, ""));
            return;
        }

        // Set modal title and body content
        modalTitleEl.textContent = title;
        modalBodyEl.innerHTML = htmlContent;

        // Clear previous icon and set new icon based on modal type
        modalIconContainerEl.innerHTML = '';
        let iconClass = '';
        let iconColor = 'text-slate-100';

        if (type === 'success') { iconClass = 'fas fa-check-circle'; iconColor = 'text-green-300'; }
        else if (type === 'error') { iconClass = 'fas fa-times-circle'; iconColor = 'text-red-300'; }
        else if (type === 'warning') { iconClass = 'fas fa-exclamation-triangle'; iconColor = 'text-amber-300'; }
        else if (type === 'question') { iconClass = 'fas fa-question-circle'; iconColor = 'text-blue-300'; }
        else { iconClass = 'fas fa-info-circle'; iconColor = 'text-sky-300';}

        // Append the icon element if an icon class is determined
        if (iconClass) {
            const i = document.createElement('i');
            i.className = `${iconClass} ${iconColor}`;
            modalIconContainerEl.appendChild(i);
        }

        // Clear previous footer buttons and create new ones based on configuration
        modalFooterEl.innerHTML = '';
        buttons.forEach(btnConfig => {
            const button = document.createElement('button');
            button.textContent = btnConfig.text;
            // Apply base and type-specific button classes for styling
            button.className = 'px-5 py-2 text-sm font-semibold rounded-lg shadow-sm transition-all duration-150 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2';

            if (btnConfig.class === 'confirm') {
                button.classList.add('bg-[#091e65]', 'text-white', 'hover:bg-[#071852]', 'focus-visible:ring-[#091e65]');
            } else if (btnConfig.class === 'danger') {
                button.classList.add('bg-red-600', 'text-white', 'hover:bg-red-700', 'focus-visible:ring-red-600');
            } else {
                button.classList.add('bg-slate-200', 'text-slate-700', 'hover:bg-slate-300', 'focus-visible:ring-slate-400');
            }

            // Add click event listener to the button
            button.addEventListener('click', () => {
                if (btnConfig.onClick) btnConfig.onClick();
                closeModal(); // Close modal after button click
            });
            modalFooterEl.appendChild(button);
        });

        // Show modal with transition effects
        modal.classList.remove('opacity-0', 'invisible');
        modal.classList.add('opacity-100', 'visible');
        modalContentWrapper.classList.remove('scale-95');
        modalContentWrapper.classList.add('scale-100');
    };

    /**
     * Closes the custom modal with transition effects.
     */
    window.closeModal = function() {
        if (modal && modalContentWrapper) {
            // Apply transition classes
            modal.classList.add('opacity-0');
            modalContentWrapper.classList.add('scale-95');
            modalContentWrapper.classList.remove('scale-100');

            // Hide the modal after the transition completes
            setTimeout(() => {
                modal.classList.add('invisible');
                modal.classList.remove('opacity-100', 'visible');
            }, 300); // Match CSS transition duration
        }
    };

    // Add event listener for the modal's close button
    if (modalCloseBtnEl) modalCloseBtnEl.addEventListener('click', closeModal);

    // Add event listener to close modal when clicking outside the content (backdrop)
    if (modal) {
        modal.addEventListener('click', function(event) {
            if (event.target === modal) {
                closeModal();
            }
        });
    }

    // --- Withdrawal Form Logic ---
    // Select elements related to the withdrawal form
    const withdrawalForm = document.getElementById('requestWithdrawalForm');
    const amountErrorDiv = document.getElementById('amountError');
    const accountErrorDiv = document.getElementById('accountError');

    /**
     * Displays inline error messages for form fields.
     * @param {HTMLElement} element - The div element to display errors in.
     * @param {Array<string>} messages - Array of error messages.
     */
    function showInlineError(element, messages) {
        if (!element) return;
        if (messages && messages.length > 0) {
            element.innerHTML = '<ul class="list-none p-0 m-0">' + messages.map(msg => `<li class="mb-1 last:mb-0">${msg}</li>`).join('') + '</ul>';
            element.classList.remove('hidden');
        } else {
            element.innerHTML = '';
            element.classList.add('hidden');
        }
    }

    // Add event listener for the withdrawal form submission
    if (withdrawalForm) {
        withdrawalForm.addEventListener('submit', function(event) {
            event.preventDefault(); // Prevent default form submission

            const amountInput = document.getElementById('amount');
            const accountSelect = document.getElementById('withdrawal_account_id');
            const submitButton = document.getElementById('submitWithdrawalBtn');

            let isValid = true;
            let amountErrorMessages = [];
            let accountErrorMessages = [];

            // Clear previous errors and reset input styles
            showInlineError(amountErrorDiv, []);
            showInlineError(accountErrorDiv, []);
            amountInput.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500/40');
            accountSelect.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500/40');
            amountInput.classList.add('border-slate-300', 'focus:border-[#091e65]', 'focus:ring-[#091e65]/40');
            accountSelect.classList.add('border-slate-300', 'focus:border-[#091e65]', 'focus:ring-[#091e65]/40');

            // Check for active withdrawal request using a global variable (assumed from Django context)
            if (typeof DJANGO_HAS_ACTIVE_REQUEST !== 'undefined' && DJANGO_HAS_ACTIVE_REQUEST) {
                let messageForPopup = "You already have a withdrawal request that is being processed or is pending.";
                // Use a global variable for the reason if available (assumed from Django context)
                if (typeof DJANGO_REASON_CANT_REQUEST !== 'undefined' && DJANGO_REASON_CANT_REQUEST && DJANGO_REASON_CANT_REQUEST.toLowerCase().includes("already have a withdrawal request")) {
                    messageForPopup = DJANGO_REASON_CANT_REQUEST;
                }
                // Show a warning modal
                showModal(
                    'Withdrawal Not Available',
                    messageForPopup,
                    'warning',
                    [{ text: 'OK', class: 'cancel' }]
                );
                return;
            }

            // Validate amount using global variables for min/max (assumed from Django context)
            const amountValue = parseFloat(amountInput.value);
            const minAmount = typeof DJANGO_MIN_WITHDRAWAL_AMOUNT !== 'undefined' ? DJANGO_MIN_WITHDRAWAL_AMOUNT : 0;
            const maxAmount = typeof DJANGO_AVAILABLE_BALANCE !== 'undefined' ? DJANGO_AVAILABLE_BALANCE : 0;


            if (!amountInput.value || isNaN(amountValue) || amountValue <= 0) {
                amountErrorMessages.push("Please enter a valid withdrawal amount.");
                isValid = false;
            } else {
                if (minAmount > 0 && amountValue < minAmount) {
                    amountErrorMessages.push(`Withdrawal amount must be at least Rs. ${minAmount.toFixed(2)}.`);
                    isValid = false;
                }
                if (maxAmount >= 0 && amountValue > maxAmount) {
                    amountErrorMessages.push(`Withdrawal amount cannot exceed your available balance of Rs. ${maxAmount.toFixed(2)}.`);
                    isValid = false;
                }
            }

            // Validate account selection
            if (!accountSelect.value) {
                accountErrorMessages.push("Please select a payout account.");
                isValid = false;
            }

            // If validation fails, show inline errors and focus the first invalid field
            if (!isValid) {
                showInlineError(amountErrorDiv, amountErrorMessages);
                showInlineError(accountErrorDiv, accountErrorMessages);
                if (amountErrorMessages.length > 0 && amountInput) {
                    amountInput.classList.add('border-red-500', 'focus:border-red-500', 'focus:ring-red-500/40');
                    amountInput.classList.remove('border-slate-300', 'focus:border-[#091e65]', 'focus:ring-[#091e65]/40');
                    amountInput.focus();
                } else if (accountErrorMessages.length > 0 && accountSelect) {
                    accountSelect.classList.add('border-red-500', 'focus:border-red-500', 'focus:ring-red-500/40');
                    accountSelect.classList.remove('border-slate-300', 'focus:border-[#091e65]', 'focus:ring-[#091e65]/40');
                    accountSelect.focus();
                }
                return;
            }

            // If valid, show a confirmation modal before submitting the form
            const amount = parseFloat(amountInput.value).toFixed(2);
            const accountText = accountSelect.options[accountSelect.selectedIndex].text;

            showModal(
                'Confirm Withdrawal',
                `You are about to request a withdrawal of <strong class="text-[#091e65] font-semibold">Rs. ${amount}</strong> to the account:<br/><p class="mt-2 p-2 bg-slate-100 rounded-md text-sm text-slate-700">${accountText}</p><p class="mt-3 text-xs text-slate-500">This action cannot be undone once submitted. Please ensure the details are correct.</p>`,
                'question',
                [
                    {
                        text: 'Yes, Request Withdrawal!',
                        class: 'confirm',
                        onClick: () => {
                            // Disable the submit button and show processing state before submitting
                            if(submitButton) {
                                submitButton.disabled = true;
                                submitButton.innerHTML = `
                                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    Processing...`;
                            }
                            withdrawalForm.submit(); // Submit the form
                        }
                    },
                    { text: 'Cancel', class: 'cancel' }
                ]
            );
        });
    }

    // --- Cancellation Logic for Pending Withdrawals ---
    // Define the cancellation window duration
    const CANCELLATION_WINDOW_MS = 30 * 60 * 1000; // 30 minutes in milliseconds

    /**
     * Formats milliseconds into a MM:SS string.
     * @param {number} milliseconds - The time in milliseconds.
     * @returns {string} Formatted time string (MM:SS).
     */
    function formatTimeRemaining(milliseconds) {
        if (milliseconds < 0) milliseconds = 0;
        let totalSeconds = Math.floor(milliseconds / 1000);
        let minutes = Math.floor(totalSeconds / 60);
        let seconds = totalSeconds % 60;
        return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    }

    /**
     * Initializes and updates countdown timers for cancellable withdrawal requests.
     */
    function initializeCountdownTimers() {
        const requestRows = document.querySelectorAll('.withdrawal-request-row');
        requestRows.forEach(row => {
            const requestDateStr = row.dataset.requestDate; // ISO format date string from Django
            const requestId = row.dataset.requestId;
            const status = row.dataset.status;

            // Only process pending requests with a request date
            if (status !== 'pending' || !requestDateStr) return;

            const requestDate = new Date(requestDateStr);
            const expirationTime = requestDate.getTime() + CANCELLATION_WINDOW_MS;

            const countdownElement = document.getElementById(`countdown-${requestId}`);
            const cancelForm = row.querySelector(`.cancel-form[data-request-id="${requestId}"]`);

            if (!countdownElement || !cancelForm) return;

            // Function to update the countdown display
            function updateCountdown() {
                const now = new Date().getTime();
                const timeRemaining = expirationTime - now;

                if (timeRemaining > 0) {
                    countdownElement.textContent = `Cancellable for: ${formatTimeRemaining(timeRemaining)}`;
                    cancelForm.style.display = 'inline-block'; // Show cancel button
                } else {
                    countdownElement.textContent = 'Cancellation window expired';
                    countdownElement.classList.remove('text-slate-600');
                    countdownElement.classList.add('text-slate-400', 'italic');
                    cancelForm.style.display = 'none'; // Hide cancel button
                    clearInterval(intervalId); // Stop the timer
                }
            }
            // Start the countdown timer
            const intervalId = setInterval(updateCountdown, 1000);
            updateCountdown(); // Initial call to set timer immediately
        });
    }

    // Initialize countdown timers on page load
    initializeCountdownTimers();
});

/**
 * Handles the submission of a cancel withdrawal request form.
 * This function is exposed globally to be called by onsubmit attribute.
 * @param {Event} event - The form submission event.
 * @param {string} amount - The amount of the withdrawal request to be displayed in the confirmation modal.
 * @param {HTMLFormElement} formElement - The cancel form element to be submitted after confirmation.
 */
window.handleCancelSubmit = function(event, amount, formElement) {
    event.preventDefault(); // Prevent default form submission initially

    // Show a confirmation modal before proceeding with cancellation
    showModal(
        'Cancel Withdrawal Request?',
        `Are you sure you want to cancel the withdrawal request for <strong class="text-red-600 font-semibold">Rs. ${amount}</strong>? This action cannot be undone.`,
        'warning',
        [
            {
                text: 'Yes, Cancel It',
                class: 'danger',
                onClick: () => {
                    // Disable the cancel button and provide feedback before submitting the form
                    const cancelButtonInForm = formElement.querySelector('button[type="submit"]');
                    if(cancelButtonInForm) {
                        cancelButtonInForm.disabled = true;
                        cancelButtonInForm.innerHTML = 'Cancelling...';
                    }
                    formElement.submit(); // Submit the cancel form
                }
            },
            { text: 'No, Keep It', class: 'cancel' }
        ]
    );
};
