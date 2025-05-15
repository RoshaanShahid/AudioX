// Wait for the DOM to be fully loaded before executing the script
document.addEventListener('DOMContentLoaded', function() {
    // Get references to the form and its elements
    const form = document.getElementById('update-profile-form');
    const fileInput = document.getElementById('creator_profile_pic_input');
    const profilePicPreview = document.getElementById('profile-pic-preview');
    const profilePicPlaceholder = document.getElementById('profile-pic-placeholder');
    let removePicBtn = document.getElementById('remove-pic-btn'); // This might be re-assigned if the button is cloned
    const removePicInput = document.getElementById('remove_profile_pic'); // Hidden input to signal profile pic removal
    const previewContainer = document.getElementById('profile-pic-preview-container');

    // Get references to name input fields and their initial values
    const creatorNameInput = document.getElementById('creator_name');
    const uniqueNameInput = document.getElementById('creator_unique_name');
    // Retrieve initial values stored in data attributes, defaulting to empty strings if not present
    const initialCreatorName = creatorNameInput ? creatorNameInput.dataset.initialValue : '';
    const initialUniqueName = uniqueNameInput ? uniqueNameInput.dataset.initialValue : '';

    // Get references to modal elements
    const modal = document.getElementById('confirmation-modal');
    const modalPanel = modal ? modal.querySelector('.relative') : null; // The actual content panel of the modal
    const modalMessage = document.getElementById('modal-message'); // Element to display messages within the modal
    const confirmButton = document.getElementById('confirm-button'); // Button to confirm changes in the modal
    const cancelButton = document.getElementById('cancel-button'); // Button to cancel changes in the modal

    // Flag to track if a name change has been confirmed via the modal
    let nameChangeConfirmed = false;

    /**
     * Shows the confirmation modal with a transition.
     */
    function showModal() {
        if (!modal || !modalPanel) return; // Do nothing if modal elements are not found
        modal.classList.remove('hidden'); // Make the modal backdrop visible
        modal.classList.add('flex'); // Use flex to center the modal content
        // Force a reflow before adding the 'active' class to ensure the transition plays
        void modalPanel.offsetWidth;
        modalPanel.dataset.active = true; // Trigger the scale and opacity transition for the panel
    }

    /**
     * Hides the confirmation modal with a transition.
     */
    function hideModal() {
        if (!modal || !modalPanel) return; // Do nothing if modal elements are not found
        delete modalPanel.dataset.active; // Trigger the reverse transition for the panel

        // Fallback to hide the modal if transitionend event doesn't fire (e.g., if transitions are disabled)
        const timeoutId = setTimeout(() => {
            if (!modal.classList.contains('hidden')) { // Check if it's not already hidden by the event listener
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        }, 350); // A bit longer than the transition duration (300ms)

        // Listen for the end of the transition on the modal panel
        modalPanel.addEventListener('transitionend', () => {
            clearTimeout(timeoutId); // Clear the fallback timeout
            if (!modalPanel.dataset.active) { // Ensure it's being hidden
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        }, { once: true }); // Remove the event listener after it fires once
    }

    /**
     * Updates the visibility of the "remove picture" button based on whether a profile picture is displayed.
     */
    function updateRemoveButtonVisibility() {
        removePicBtn = document.getElementById('remove-pic-btn'); // Re-fetch in case it was replaced
        if (removePicBtn) {
            // Check if the preview image is visible and has a valid source (not ending with '/')
            const hasImage = (profilePicPreview && !profilePicPreview.classList.contains('hidden') && profilePicPreview.src && !profilePicPreview.src.endsWith('/'));
            if (hasImage) {
                removePicBtn.classList.remove('hidden');
            } else {
                removePicBtn.classList.add('hidden');
            }
        }
    }

    // Event listener for the profile picture file input
    if (fileInput && profilePicPreview && previewContainer) {
        fileInput.addEventListener('change', function(event) {
            const file = event.target.files[0];
            if (file && file.type.startsWith('image/')) { // Check if a file is selected and it's an image
                const maxSize = 2 * 1024 * 1024; // 2MB in bytes
                if (file.size > maxSize) {
                    // TODO: Show a user-friendly error message about file size
                    console.warn('File size exceeds 2MB limit.');
                    fileInput.value = ''; // Clear the file input
                    return;
                }

                const reader = new FileReader();
                reader.onload = function(e) {
                    // Display the selected image in the preview element
                    profilePicPreview.src = e.target.result;
                    profilePicPreview.classList.remove('hidden');
                    if (profilePicPlaceholder) {
                        profilePicPlaceholder.classList.add('hidden'); // Hide the placeholder
                    }
                    if (removePicInput) removePicInput.value = '0'; // Signal that the picture is not to be removed
                    updateRemoveButtonVisibility(); // Show the remove button
                    addRemoveListener(); // Re-add listener to the (potentially new) remove button
                }
                reader.readAsDataURL(file); // Read the file as a data URL
            } else if (file) {
                // TODO: Show a user-friendly error message for invalid file type
                console.warn('Invalid file type selected.');
                fileInput.value = ''; // Clear the file input if not an image
            }
        });
    }

    /**
     * Adds or re-adds the event listener to the "remove picture" button.
     * This is necessary because the button might be dynamically shown/hidden or replaced.
     * It clones the button to ensure any old listeners are removed before adding a new one.
     */
    function addRemoveListener() {
        removePicBtn = document.getElementById('remove-pic-btn'); // Get the current remove button
        if (removePicBtn) {
            // Clone the button and replace the old one to remove previous event listeners
            const newBtn = removePicBtn.cloneNode(true);
            removePicBtn.parentNode.replaceChild(newBtn, removePicBtn);
            removePicBtn = newBtn; // Update the reference to the new button

            removePicBtn.addEventListener('click', function() {
                if (profilePicPreview) {
                    profilePicPreview.src = ''; // Clear the image source
                    profilePicPreview.classList.add('hidden'); // Hide the preview
                }
                if (profilePicPlaceholder) {
                    profilePicPlaceholder.classList.remove('hidden'); // Show the placeholder
                }
                if (fileInput) fileInput.value = ''; // Clear the file input
                if (removePicInput) removePicInput.value = '1'; // Signal that the picture should be removed on submit
                updateRemoveButtonVisibility(); // Hide the remove button
            });
        }
    }

    // Initial setup for the remove button visibility and listener
    updateRemoveButtonVisibility();
    addRemoveListener();

    // Event listener for form submission
    if (form && creatorNameInput && uniqueNameInput) {
        form.addEventListener('submit', function(event) {
            const currentCreatorName = creatorNameInput.value.trim();
            const currentUniqueName = uniqueNameInput.value.trim();
            // Use initial values from data attributes, defaulting to empty strings
            const initialName = initialCreatorName || '';
            const initialUnique = initialUniqueName || '';

            // Check if the display name or unique handle has changed and is not read-only
            const nameChanged = initialName !== currentCreatorName && !creatorNameInput.readOnly;
            const uniqueNameChanged = initialUnique !== currentUniqueName && !uniqueNameInput.readOnly;

            // If either name changed and confirmation is not yet given, show the modal
            if ((nameChanged || uniqueNameChanged) && !nameChangeConfirmed) {
                event.preventDefault(); // Prevent form submission

                // Construct the message for the modal
                let message = "Please confirm the following changes:<br><ul class='list-none mt-2 space-y-1.5 text-gray-800'>";
                if (nameChanged) {
                    message += `<li class="flex items-start p-2 bg-gray-50 rounded border border-gray-200"><i class="fas fa-user text-[#091e65]/70 w-4 pt-1 mr-2.5 flex-shrink-0"></i><span class="flex-grow">Display Name:<br>"<span class="font-medium text-gray-500 line-through">${initialName || '(empty)'}</span>" <i class="fas fa-arrow-right fa-xs mx-1 text-gray-400"></i> "<b class="text-[#091e65]">${currentCreatorName}</b>"</span></li>`;
                }
                if (uniqueNameChanged) {
                    message += `<li class="flex items-start p-2 bg-gray-50 rounded border border-gray-200"><i class="fas fa-at text-[#091e65]/70 w-4 pt-1 mr-2.5 flex-shrink-0"></i><span class="flex-grow">Unique Handle:<br>"<span class="font-medium text-gray-500 line-through">@${initialUnique || '(empty)'}</span>" <i class="fas fa-arrow-right fa-xs mx-1 text-gray-400"></i> "<b class="text-[#091e65]">@${currentUniqueName}</b>"</span></li>`;
                }
                message += "</ul>";

                if (modalMessage) modalMessage.innerHTML = message; // Set the modal message
                showModal(); // Display the modal
            } else {
                // If no name changes requiring confirmation, or if already confirmed, proceed with submission
                nameChangeConfirmed = false; // Reset confirmation flag for future edits
                const submitButton = form.querySelector('button[type="submit"]');
                if(submitButton) {
                    // Update submit button to show a loading state
                    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Saving...';
                    submitButton.disabled = true; // Disable button to prevent multiple submissions
                }
                // No explicit form.submit() here, allow default behavior unless it was a modal-confirmed submission
            }
        });
    }

    // Event listener for the modal's confirm button
    if (confirmButton) {
        confirmButton.addEventListener('click', function() {
            nameChangeConfirmed = true; // Set the confirmation flag
            hideModal(); // Hide the modal

            const submitButton = form.querySelector('button[type="submit"]');
            if(submitButton) {
                // Update submit button to show a loading state
                submitButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Saving...';
                submitButton.disabled = true;
            }
            // Programmatically submit the form after a short delay to allow UI updates
            setTimeout(() => {
                if (form) form.submit();
            }, 50); // 50ms delay
        });
    }

    // Event listener for the modal's cancel button
    if (cancelButton) {
        cancelButton.addEventListener('click', function() {
            hideModal(); // Hide the modal
            nameChangeConfirmed = false; // Reset the confirmation flag
        });
    }

    // Event listener to close the modal if the backdrop (outside the panel) is clicked
    if (modal) {
        modal.addEventListener('click', function(event) {
            if (event.target === modal) { // Check if the click was directly on the modal backdrop
                hideModal();
                nameChangeConfirmed = false; // Reset the confirmation flag
            }
        });
    }
});
