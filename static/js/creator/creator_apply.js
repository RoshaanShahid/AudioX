// This script handles client-side interactions for the creator application form,
// including file previews and AJAX form submission with SweetAlert2 notifications.
document.addEventListener('DOMContentLoaded', function() {
    /**
     * Sets up a file input to show a preview of the selected image and its name.
     * Also handles basic client-side validation for file size and type.
     * @param {string} inputId - The ID of the file input element.
     * @param {string} previewContainerId - The ID of the container for the preview.
     * @param {string} previewImgId - The ID of the img tag for the image preview.
     * @param {string} textId - The ID of the span/element to display the chosen file name.
     */
    function setupPreviewV3(inputId, previewContainerId, previewImgId, textId) {
        const input = document.getElementById(inputId);
        const previewContainer = document.getElementById(previewContainerId);
        const previewImg = document.getElementById(previewImgId);
        const textDisplay = document.getElementById(textId); // Renamed from 'text' to avoid conflict
        const errorP = document.getElementById(`error-${inputId.replace('id_', '')}`);

        if (!input || !previewContainer || !previewImg || !textDisplay || !errorP) {
            console.warn(`Preview elements not found for input: ${inputId}. Ensure all IDs (inputId, previewContainerId, previewImgId, textId, error-elementId) are correct.`);
            return;
        }

        input.addEventListener('change', function() {
            errorP.textContent = ''; // Clear previous error message
            const file = this.files[0];

            if (file) {
                const maxSize = 2 * 1024 * 1024; // 2MB
                const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg'];

                if (file.size > maxSize) {
                    errorP.textContent = 'File is too large (Max 2MB).';
                    previewContainer.classList.remove('visible');
                    previewContainer.style.display = 'none'; // Ensure it's hidden
                    textDisplay.textContent = '';
                    this.value = ''; // Clear the invalid file from input
                    return;
                }
                if (!allowedTypes.includes(file.type)) {
                    errorP.textContent = 'Invalid file type (PNG, JPG/JPEG only).';
                    previewContainer.classList.remove('visible');
                    previewContainer.style.display = 'none'; // Ensure it's hidden
                    textDisplay.textContent = '';
                    this.value = ''; // Clear the invalid file from input
                    return;
                }

                // Display file name (truncated if too long)
                textDisplay.textContent = file.name.length > 25 ? file.name.substring(0, 22) + '...' : file.name;
                
                // Display image preview
                const reader = new FileReader();
                reader.onload = function(e) {
                    previewImg.src = e.target.result;
                    previewContainer.style.display = 'flex'; // Make it visible
                    previewContainer.classList.add('visible');
                }
                reader.readAsDataURL(file);
            } else {
                // No file selected or selection cancelled
                previewContainer.classList.remove('visible');
                previewContainer.style.display = 'none'; // Ensure it's hidden
                textDisplay.textContent = '';
            }
        });
    }

    // Setup previews for CNIC front and back images
    setupPreviewV3('id_cnic_front', 'cnic-front-preview-container', 'cnic-front-preview', 'cnic-front-chosen-text');
    setupPreviewV3('id_cnic_back', 'cnic-back-preview-container', 'cnic-back-preview', 'cnic-back-chosen-text');

    // Form submission handling
    const applyForm = document.getElementById('creator-apply-form');
    const submitButton = document.getElementById('submit-button');

    // Mapping of form field names to their corresponding error display element IDs
    const errorFieldMap = {
        creator_name: 'error-creator_name',
        creator_unique_name: 'error-creator_unique_name',
        cnic_front: 'error-cnic_front',
        cnic_back: 'error-cnic_back',
        cnic_files: 'error-cnic_files', // For general errors related to both CNIC files
        agreements: 'error-agreements', // For errors related to checkbox agreements
        __all__: 'error-agreements' // Fallback for general form errors not tied to a specific field
    };

    /**
     * Clears all visible error messages on the form.
     */
    function clearAllErrors() {
        Object.values(errorFieldMap).forEach(errorId => {
            const el = document.getElementById(errorId);
            if (el) el.textContent = '';
        });
        // Hide any server-rendered general message containers if needed
        document.querySelectorAll('.content-area .bg-red-100.border-red-300').forEach(el => el.style.display = 'none');
    }

    /**
     * Displays an error message for a specific form field.
     * @param {string} fieldName - The name of the form field.
     * @param {string} message - The error message to display.
     */
    function showFieldError(fieldName, message) {
        const errorId = errorFieldMap[fieldName] || errorFieldMap.__all__;
        const el = document.getElementById(errorId);
        if (el) {
            el.textContent = message;
            el.style.display = 'block'; // Ensure it's visible
        } else {
            // Fallback or log if a specific error placeholder isn't found
            console.warn(`No error placeholder found for field: ${fieldName}. Displaying in general error area.`);
            const generalErrorEl = document.getElementById(errorFieldMap.__all__);
            if (generalErrorEl) {
                generalErrorEl.textContent += ` ${fieldName.replace(/_/g, ' ')}: ${message}`;
                generalErrorEl.style.display = 'block';
            }
        }
    }

    if (applyForm && submitButton) {
        applyForm.addEventListener('submit', function(event) {
            event.preventDefault(); // Prevent default form submission
            clearAllErrors(); // Clear any existing errors

            // Disable button and show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Submitting...';

            // Chain SweetAlert2 popups for a better user experience
            Swal.fire({
                title: 'Processing Application',
                html: '<p>Submitting your details...</p>',
                allowOutsideClick: false,
                timer: 1500, // First short delay
                timerProgressBar: true,
                didOpen: () => { Swal.showLoading(); }
            }).then(() => {
                return Swal.fire({ // Second popup
                    title: 'Processing Application',
                    html: '<p>Hang on tight, we are almost there...</p>',
                    allowOutsideClick: false,
                    timer: 2000, // Second, slightly longer delay
                    timerProgressBar: true,
                    didOpen: () => { Swal.showLoading(); }
                });
            }).then(() => {
                // Final "sending" popup before actual fetch
                Swal.fire({
                    title: 'Finalizing...',
                    html: '<p>Sending your application to the AudioX team.</p>',
                    allowOutsideClick: false,
                    didOpen: () => { Swal.showLoading(); }
                });

                const formData = new FormData(applyForm);
                const csrfToken = formData.get('csrfmiddlewaretoken'); // Get CSRF token from form

                // Perform the AJAX request
                fetch(applyForm.action, {
                    method: 'POST',
                    headers: { 
                        'X-CSRFToken': csrfToken, // Crucial for Django POST requests
                        'X-Requested-With': 'XMLHttpRequest' // Often used to indicate AJAX
                    },
                    body: formData
                })
                .then(response => response.json().then(data => ({ status: response.status, body: data })))
                .then(({ status, body }) => {
                    Swal.close(); // Close the "Finalizing" popup

                    if (status >= 200 && status < 300 && body.status === 'success') {
                        // Success
                        Swal.fire({
                            title: 'Application Submitted!',
                            html: "<p>Thank you! Your application has been submitted successfully.</p><p>The AudioX team will review your application and you will be notified of the outcome, typically within 24-48 hours.</p>",
                            icon: 'success',
                            confirmButtonText: 'Go to My Profile',
                            confirmButtonColor: '#091e65' // theme-primary
                        }).then((result) => {
                            if (result.isConfirmed && body.redirect_url) { 
                                window.location.href = body.redirect_url; 
                            } else if (result.isConfirmed) {
                                // Fallback redirect if redirect_url is not in response
                                window.location.href = "/my-profile/"; // Adjust as needed
                            }
                        });
                    } else {
                        // Handle errors (validation or server-side)
                        let errorTitle = 'Submission Failed';
                        let errorMessage = body.message || 'An unknown error occurred. Please check the form and try again.';
                        let errorHtml = `<p>${errorMessage}</p>`;

                        if (body.errors) {
                            errorHtml += '<ul class="list-disc list-inside text-left mt-2 text-sm">';
                            Object.keys(body.errors).forEach(field => {
                                const fieldErrorMessage = Array.isArray(body.errors[field]) ? body.errors[field][0] : body.errors[field];
                                showFieldError(field, fieldErrorMessage); // Display error next to the field
                                errorHtml += `<li>${field.replace(/_/g, ' ')}: ${fieldErrorMessage}</li>`;
                            });
                            errorHtml += '</ul>';
                        }
                        Swal.fire({ 
                            title: errorTitle, 
                            html: errorHtml, 
                            icon: 'error', 
                            confirmButtonColor: '#091e65' // theme-primary
                        });
                    }
                })
                .catch(error => {
                    Swal.close();
                    console.error('Error submitting application:', error);
                    Swal.fire({ 
                        title: 'Network Error', 
                        text: 'Could not submit application. Please check your internet connection and try again.', 
                        icon: 'error', 
                        confirmButtonColor: '#091e65' // theme-primary
                    });
                })
                .finally(() => {
                    // Re-enable submit button regardless of outcome (unless redirected)
                    submitButton.disabled = false;
                    submitButton.innerHTML = '<i class="fa-solid fa-rocket fa-fw"></i> Submit Application';
                });
            });
        });

        // Add event listeners to clear individual field errors on input/change
        applyForm.querySelectorAll('input, textarea, select').forEach(input => {
            input.addEventListener('input', () => { // 'input' for immediate feedback
                const fieldName = input.name;
                const errorId = errorFieldMap[fieldName];
                if (errorId) { 
                    const el = document.getElementById(errorId); 
                    if (el) el.textContent = ''; 
                }
            });
            input.addEventListener('change', () => { // 'change' for checkboxes and file inputs
                const fieldName = input.name;
                const errorId = errorFieldMap[fieldName];
                if (errorId) { 
                    const el = document.getElementById(errorId); 
                    if (el) el.textContent = ''; 
                }
                // Specifically clear general agreements error if any checkbox changes
                if(input.type === 'checkbox' && errorFieldMap.agreements){ 
                    const agreeEl = document.getElementById(errorFieldMap.agreements); 
                    if(agreeEl) agreeEl.textContent = ''; 
                }
            });
        });
    }
});
