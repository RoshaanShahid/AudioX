document.addEventListener('DOMContentLoaded', function() {
    // Modal elements
    const modal = document.getElementById('customModal');
    const modalTitleEl = document.getElementById('modalTitle');
    const modalBodyEl = document.getElementById('modalBody');
    const modalIconContainerEl = document.getElementById('modalIconContainer');
    const modalFooterEl = document.getElementById('modalFooter');
    const modalCloseBtnEl = document.getElementById('modalCloseBtn');
    const modalContentWrapper = modal ? modal.querySelector('.modal-content-wrapper') : null;

    /**
     * Shows the custom modal.
     * @param {string} title - The title of the modal.
     * @param {string} htmlContent - The HTML content for the modal body.
     * @param {string} [type='info'] - Type of modal (success, error, warning, question, info).
     * @param {Array<Object>} [buttons=[]] - Array of button configurations.
     * Each button object: { text: 'Button Text', class: 'confirm'|'danger'|'cancel', onClick: function }
     */
    window.showModal = function(title, htmlContent, type = 'info', buttons = []) {
        if (!modal || !modalTitleEl || !modalBodyEl || !modalIconContainerEl || !modalFooterEl || !modalContentWrapper) {
            // Fallback if modal elements are not found
            alert(title + "\n" + htmlContent.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, ""));
            return;
        }
        modalTitleEl.textContent = title;
        modalBodyEl.innerHTML = htmlContent; 
        
        modalIconContainerEl.innerHTML = ''; 
        let iconClass = '';
        let iconColor = 'text-slate-100';

        if (type === 'success') { iconClass = 'fas fa-check-circle'; iconColor = 'text-green-300'; }
        else if (type === 'error') { iconClass = 'fas fa-times-circle'; iconColor = 'text-red-300'; }
        else if (type === 'warning') { iconClass = 'fas fa-exclamation-triangle'; iconColor = 'text-amber-300'; }
        else if (type === 'question') { iconClass = 'fas fa-question-circle'; iconColor = 'text-blue-300'; }
        else { iconClass = 'fas fa-info-circle'; iconColor = 'text-sky-300';}
        
        if (iconClass) {
            const i = document.createElement('i');
            i.className = `${iconClass} ${iconColor}`;
            modalIconContainerEl.appendChild(i);
        }

        modalFooterEl.innerHTML = ''; 
        buttons.forEach(btnConfig => {
            const button = document.createElement('button');
            button.textContent = btnConfig.text;
            button.className = 'px-5 py-2 text-sm font-semibold rounded-lg shadow-sm transition-all duration-150 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2';
            
            if (btnConfig.class === 'confirm') {
                button.classList.add('bg-[#091e65]', 'text-white', 'hover:bg-[#071852]', 'focus-visible:ring-[#091e65]');
            } else if (btnConfig.class === 'danger') {
                button.classList.add('bg-red-600', 'text-white', 'hover:bg-red-700', 'focus-visible:ring-red-600');
            } else { 
                button.classList.add('bg-slate-200', 'text-slate-700', 'hover:bg-slate-300', 'focus-visible:ring-slate-400');
            }
            
            button.addEventListener('click', () => {
                if (btnConfig.onClick) btnConfig.onClick();
                closeModal(); 
            });
            modalFooterEl.appendChild(button);
        });
        
        modal.classList.remove('opacity-0', 'invisible');
        modal.classList.add('opacity-100', 'visible');
        modalContentWrapper.classList.remove('scale-95');
        modalContentWrapper.classList.add('scale-100');
    }

    /**
     * Closes the custom modal.
     */
    window.closeModal = function() {
        if (modal && modalContentWrapper) {
            modal.classList.add('opacity-0'); 
            modalContentWrapper.classList.add('scale-95'); 
            modalContentWrapper.classList.remove('scale-100');
            
            setTimeout(() => {
                modal.classList.add('invisible');
                modal.classList.remove('opacity-100', 'visible');
            }, 300); 
        }
    }
    
    if (modalCloseBtnEl) modalCloseBtnEl.addEventListener('click', closeModal);

    if (modal) {
        modal.addEventListener('click', function(event) {
            if (event.target === modal) { 
                closeModal();
            }
        });
    }

    const withdrawalForm = document.getElementById('requestWithdrawalForm');
    const amountErrorDiv = document.getElementById('amountError');
    const accountErrorDiv = document.getElementById('accountError'); 

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

    if (withdrawalForm) {
        withdrawalForm.addEventListener('submit', function(event) {
            event.preventDefault(); 

            const amountInput = document.getElementById('amount');
            const accountSelect = document.getElementById('withdrawal_account_id');
            const submitButton = document.getElementById('submitWithdrawalBtn');

            let isValid = true;
            let amountErrorMessages = [];
            let accountErrorMessages = [];

            showInlineError(amountErrorDiv, []);
            showInlineError(accountErrorDiv, []);
            amountInput.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500/40');
            accountSelect.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500/40');
            amountInput.classList.add('border-slate-300', 'focus:border-[#091e65]', 'focus:ring-[#091e65]/40');
            accountSelect.classList.add('border-slate-300', 'focus:border-[#091e65]', 'focus:ring-[#091e65]/40');

            const amountValue = parseFloat(amountInput.value);
            const minAmount = DJANGO_MIN_WITHDRAWAL_AMOUNT; 
            const maxAmount = DJANGO_AVAILABLE_BALANCE;

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
            
            if (!accountSelect.value) {
                accountErrorMessages.push("Please select a payout account.");
                isValid = false;
            }

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
                            if(submitButton) {
                                submitButton.disabled = true; 
                                submitButton.innerHTML = `
                                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    Processing...`;
                            }
                            withdrawalForm.submit(); 
                        }
                    },
                    { text: 'Cancel', class: 'cancel' } 
                ]
            );
        });
    }

    // Removed CANCELLATION_WINDOW_MS, formatTime, initializeCountdownTimers functions
    // as the cancellation feature by creator is removed.
}); 
