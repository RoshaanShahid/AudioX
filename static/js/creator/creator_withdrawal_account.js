/**
 * Configuration for SweetAlert2 modals with a light theme.
 * @param {string} [iconColorParam] - The color for the icon (e.g., '#ef4444' for red).
 * @returns {object} SweetAlert2 configuration object.
 */
const swalLightConfig = (iconColorParam) => {
    let iconColor = iconColorParam || '#6b7280'; // Default to a neutral gray color
    let confirmBgColor = 'bg-[#091e65]'; // Default confirm button background (theme color)
    let confirmRingColor = 'focus-visible:ring-[#091e65]'; // Default confirm button ring color

    // Adjust confirm button color for specific icon colors (e.g., danger actions)
    if (iconColor === '#ef4444') { // Red, typically for warnings or errors
        confirmBgColor = 'bg-red-600'; // Use red for delete confirmation
        confirmRingColor = 'focus-visible:ring-red-600';
    } else if (iconColor === '#f59e0b') { // Amber, for informational warnings
         confirmBgColor = 'bg-[#091e65]'; // Keep confirm button as theme color
    }
    // Add more conditions here if other icon colors require different button styling

    return {
        iconColor: iconColor,
        buttonsStyling: false, // Use custom classes for buttons
        showClass: { popup: 'animate__animated animate__fadeIn animate__faster' }, // Animation for showing modal
        hideClass: { popup: 'animate__animated animate__fadeOut animate__faster' }, // Animation for hiding modal
        background: '#ffffff', // White background for the modal
        customClass: {
            popup: 'bg-white text-gray-700 rounded-xl border border-gray-200 shadow-lg', // Modal container
            title: 'text-gray-900 text-lg font-semibold', // Modal title
            htmlContainer: 'text-gray-600 text-sm', // Modal content area
            confirmButton: `${confirmBgColor} text-white rounded-md px-4 py-2.5 text-sm font-medium transition-colors duration-150 ease-in-out shadow-sm ${confirmRingColor} hover:opacity-90`, // Confirm button styling
            cancelButton: 'bg-white text-gray-700 border border-gray-300 rounded-md px-4 py-2.5 text-sm font-medium transition-colors duration-150 ease-in-out shadow-sm hover:bg-gray-50', // Cancel button styling
            actions: 'space-x-3', // Spacing for action buttons
            icon: 'mt-2 mb-1 scale-95' // Styling for the icon
        }
    };
};

/**
 * Handles the deletion of a payout method with a confirmation dialog.
 * @param {Event} event - The form submission event.
 * @param {HTMLFormElement} formElement - The form being submitted.
 * @param {string} accountDetails - A string describing the account to be deleted.
 */
function handleDelete(event, formElement, accountDetails) {
    event.preventDefault(); // Prevent default form submission
    Swal.fire({
        ...swalLightConfig('#ef4444'), // Red icon for warning
        title: 'Delete Payout Method?',
        html: `Are you sure you want to delete the <strong>${accountDetails}</strong>?<br>This action cannot be undone.`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonText: 'Yes, delete it!',
        cancelButtonText: 'Cancel',
    }).then((result) => {
        if (result.isConfirmed) {
            formElement.submit(); // Submit the form if confirmed
        }
    });
}

/**
 * Handles setting a payout method as primary with a confirmation dialog.
 * @param {Event} event - The form submission event.
 * @param {HTMLFormElement} formElement - The form being submitted.
 * @param {string} accountDetails - A string describing the account to be set as primary.
 */
function handleSetPrimary(event, formElement, accountDetails) {
    event.preventDefault(); // Prevent default form submission
    Swal.fire({
        ...swalLightConfig('#091e65'), // Theme color icon for question
        title: 'Set as Primary?',
        html: `Set the <strong>${accountDetails}</strong> as your primary payout method?`,
        icon: 'question', // Using 'info' or 'question' icon
        showCancelButton: true,
        confirmButtonText: 'Yes, set as primary',
        cancelButtonText: 'Cancel',
    }).then((result) => {
        if (result.isConfirmed) {
            formElement.submit(); // Submit the form if confirmed
        }
    });
}

/**
 * Handles adding a new payout account with client-side validation and a confirmation dialog.
 * @param {Event} event - The form submission event.
 * @param {HTMLFormElement} formElement - The form being submitted.
 */
function handleAddAccount(event, formElement) {
    event.preventDefault(); // Prevent default form submission
    let isValid = true;

    // Clear previous error styling and messages
    formElement.querySelectorAll('.border-red-500').forEach(el => {
        el.classList.remove('border-red-500', 'ring-red-500', 'ring-2', 'focus:ring-red-500');
        el.classList.add('border-gray-300', 'focus:ring-[#091e65]', 'focus:border-[#091e65]');
    });
    formElement.querySelectorAll('p[id^="error_"]').forEach(el => el.textContent = '');
    const nonFieldErrorsContainer = formElement.querySelector('#non_field_errors_container');
    if (nonFieldErrorsContainer) nonFieldErrorsContainer.innerHTML = '';


    // Validate required fields
    const requiredInputs = formElement.querySelectorAll('[required]');
    requiredInputs.forEach(input => {
        const errorElement = formElement.querySelector(`#error_${input.name}`);
        // Check if input is visible (offsetParent !== null) and not disabled
        if (!input.disabled && input.offsetParent !== null && !input.value.trim()) {
            isValid = false;
            input.classList.remove('border-gray-300', 'focus:ring-[#091e65]', 'focus:border-[#091e65]');
            input.classList.add('border-red-500', 'ring-red-500', 'ring-2', 'focus:ring-red-500');
            if (errorElement) {
                errorElement.textContent = 'This field is required.';
            }
        }
    });

    if (!isValid) {
        Swal.fire({
            ...swalLightConfig('#f59e0b'), // Amber icon for missing information
            title: 'Missing Information',
            text: 'Please fill out all required fields (marked in red).',
            icon: 'warning',
        });
        return; // Stop if validation fails
    }

    // Gather form data for confirmation dialog
    const formData = new FormData(formElement);
    const accountTypeSelect = formElement.querySelector('select[name="account_type"]');
    const accountTypeText = accountTypeSelect.options[accountTypeSelect.selectedIndex].text;
    const accountTitle = formData.get('account_title');
    const accountIdentifier = formData.get('account_identifier');
    const bankNameSelect = formElement.querySelector('select[name="bank_name"]');
    let bankName = null;
    if (formData.get('account_type') === 'bank' && !bankNameSelect.disabled && bankNameSelect.value) {
        bankName = bankNameSelect.options[bankNameSelect.selectedIndex].text;
    }
    const isPrimary = formElement.querySelector('input[name="is_primary"]').checked;

    // Construct HTML for the confirmation dialog
    let confirmationHtml = `
        <p class="mb-4 text-center text-sm text-gray-500">Please review the details before adding:</p>
        <ul class="space-y-2 text-sm text-left border border-gray-200 rounded-lg p-4 bg-gray-50 divide-y divide-gray-200">
            <li class="flex justify-between items-center py-1.5"><strong class="text-gray-600 pr-2">Type:</strong> <span class="text-gray-800 text-right">${accountTypeText}</span></li>
            <li class="flex justify-between items-center py-1.5"><strong class="text-gray-600 pr-2">Title:</strong> <span class="text-gray-800 text-right">${accountTitle}</span></li>
            <li class="flex justify-between items-center py-1.5"><strong class="text-gray-600 pr-2">Identifier:</strong> <span class="text-gray-800 font-mono text-right">${accountIdentifier}</span></li>
    `;
    if (bankName) {
        confirmationHtml += `<li class="flex justify-between items-center py-1.5"><strong class="text-gray-600 pr-2">Bank:</strong> <span class="text-gray-800 text-right">${bankName}</span></li>`;
    }
    confirmationHtml += `<li class="flex justify-between items-center py-1.5"><strong class="text-gray-600 pr-2">Set as Primary:</strong> <span class="text-gray-800 text-right">${isPrimary ? 'Yes' : 'No'}</span></li>`;
    confirmationHtml += `</ul>`;

    // Show confirmation dialog
    Swal.fire({
        ...swalLightConfig('#091e65'), // Theme color icon for info
        title: 'Confirm Payout Details',
        html: confirmationHtml,
        icon: 'info',
        showCancelButton: true,
        confirmButtonText: 'Confirm & Add Method',
        cancelButtonText: 'Edit Details',
        customClass: {
            ...swalLightConfig('#091e65').customClass, // Inherit base custom classes
            htmlContainer: 'text-sm mb-5', // Specific styling for this modal's HTML container
        }
    }).then((result) => {
        if (result.isConfirmed) {
            // Add a loading state to the submit button before submitting
            const submitButton = formElement.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.innerHTML = `
                    <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Adding...
                `;
            }
            formElement.submit(); // Submit the form if confirmed
        }
    });
}
