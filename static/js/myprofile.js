document.addEventListener('DOMContentLoaded', function () {
    const securityLink = document.getElementById('security-link');
    const securityModal = document.getElementById('security-modal');
    const closeModal = document.querySelector('.close-modal');
    const profilePictureContainer = document.getElementById('profile-picture'); // Updated selector
    const profilePictureImg = profilePictureContainer.querySelector('img'); // Select the img element within the container
    const defaultIcon = profilePictureContainer.querySelector('.default-icon'); // Select the default icon within the container
    const photoInput = document.getElementById('photo');
    const saveProfilePicButton = document.getElementById('save-profile-pic');
    const changePasswordForm = document.getElementById('change-password-form');
    const passwordChangeMessage = document.getElementById('password-change-message');
    const customAlert = document.getElementById('custom-alert');
    const customAlertMessage = document.getElementById('custom-alert-message');
    const customAlertClose = document.getElementById('custom-alert-close');
    const updateMessageDiv = document.getElementById('profile-update-message');

    // Get the update profile URL from the data attribute
    const updateProfileURL = document.getElementById('update-profile-url').getAttribute('data-url');

    // Security Modal
    securityLink.addEventListener('click', function (event) {
        event.preventDefault();
        securityModal.style.display = 'block';
    });

    closeModal.addEventListener('click', function () {
        securityModal.style.display = 'none';
    });

    window.addEventListener('click', function (event) {
        if (event.target == securityModal) {
            securityModal.style.display = 'none';
        }
    });

    // Handle password change form submission
    changePasswordForm.addEventListener('submit', function(event) {
        event.preventDefault();

        // Clear previous error messages
        passwordChangeMessage.innerHTML = '';

        // Get the CSRF token from the cookie
        const csrftoken = getCookie('csrftoken');

        fetch(this.action, {
            method: 'POST',
            body: new FormData(this),
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrftoken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Display success message in the custom alert
                customAlertMessage.textContent = data.message;
                customAlert.className = 'success';
                customAlert.classList.remove('hidden');
                changePasswordForm.reset();

                // Close the modal and redirect to login on OK button click
                customAlertClose.onclick = function() {
                    customAlert.classList.add('hidden');
                    securityModal.style.display = 'none';
                    window.location.href = "/login/";
                }
            } else {
                // Handle errors similarly, but do not redirect
                customAlertMessage.textContent = data.message;
                customAlert.className = 'error';
                customAlert.classList.remove('hidden');

                if (data.errors) {
                    for (const field in data.errors) {
                        const errorSpan = document.createElement('div');
                        errorSpan.className = 'error-message';
                        errorSpan.textContent = data.errors[field];
                        passwordChangeMessage.appendChild(errorSpan);
                    }
                }

                customAlertClose.onclick = function() {
                    customAlert.classList.add('hidden');
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
            customAlertMessage.textContent = 'An error occurred. Please try again.';
            customAlert.className = 'error';
            customAlert.classList.remove('hidden');

            customAlertClose.onclick = function() {
                customAlert.classList.add('hidden');
            }
        });
    });


    // Edit Profile Picture
    profilePictureContainer.addEventListener('click', function() {
        photoInput.click();
    });

    photoInput.addEventListener('change', function() {
        if (this.files && this.files[0]) {
            const reader = new FileReader();
            reader.onload = function(e) {
                profilePictureImg.src = e.target.result;
                profilePictureImg.style.display = 'block'; // Show the image
                defaultIcon.style.display = 'none'; // Hide the default icon
                saveProfilePicButton.style.display = 'flex'; // Show save button
            }
            reader.readAsDataURL(this.files[0]);
        }
    });

    // Save Profile Picture Button
    saveProfilePicButton.addEventListener('click', function() {
        let formData = new FormData();
        formData.append('profile_pic', photoInput.files[0]);
        formData.append('csrfmiddlewaretoken', getCookie('csrftoken')); // Correctly get CSRF token

        fetch(updateProfileURL, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken') // Include CSRF token in headers
            },
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                console.log('Profile picture updated successfully');
                saveProfilePicButton.style.display = 'none'; // Hide save button

                // Display success message in the div (no alert)
                updateMessageDiv.textContent = data.message;
                updateMessageDiv.className = 'success-message';

            } else {
                console.error('Error updating profile picture:', data.message);

                // Display error message in the div (no alert)
                updateMessageDiv.textContent = data.message;
                updateMessageDiv.className = 'error-message';
            }
        })
        .catch(error => {
            console.error('There has been a problem with your fetch operation:', error);

            // Display error message in the div (no alert)
            updateMessageDiv.textContent = 'An error occurred while updating the profile picture.';
            updateMessageDiv.className = 'error-message';
        });
    });

    // Edit and Save Icons for Text Fields
    const editIcons = document.querySelectorAll('.edit-icon');
    const saveIcons = document.querySelectorAll('.save-icon');

    editIcons.forEach(icon => {
        icon.addEventListener('click', function() {
            const targetId = this.dataset.target;
            const inputField = document.getElementById(targetId);
            inputField.readOnly = false;
            inputField.focus();
            this.style.display = 'none';
            document.querySelector(`.save-icon[data-target="${targetId}"]`).style.display = 'inline-block';
        });
    });

    // Save Icons for Text Fields
    saveIcons.forEach(icon => {
        icon.addEventListener('click', function() {
            const targetId = this.dataset.target;
            const inputField = document.getElementById(targetId);

            // Check if the field is empty or contains only whitespace
            if (!inputField.value.trim()) {
                console.error('Error: Field cannot be empty.');
                updateMessageDiv.textContent = 'Error: Field cannot be empty.';
                updateMessageDiv.className = 'error-message';
                return; // Stop the save operation
            }

            inputField.readOnly = true;
            this.style.display = 'none';
            document.querySelector(`.edit-icon[data-target="${targetId}"]`).style.display = 'inline-block';

            // Prepare data - No need for FormData if sending individual fields
            const data = {
                [targetId]: inputField.value,
                'csrfmiddlewaretoken': getCookie('csrftoken')
            };

            // Send AJAX request to update the specific field
            fetch(updateProfileURL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json', // Specify content type as JSON
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(data) // Stringify the data object
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.status === 'success') {
                    console.log(targetId + ' updated successfully');
                    updateMessageDiv.textContent = data.message;
                    updateMessageDiv.className = 'success-message';
                } else {
                    console.error('Error updating field:', data.message);
                    updateMessageDiv.textContent = data.message;
                    updateMessageDiv.className = 'error-message';
                }
            })
            .catch(error => {
                console.error('There has been a problem with your fetch operation:', error);
                updateMessageDiv.textContent = 'An error occurred while updating the field.';
                updateMessageDiv.className = 'error-message';
            });
        });
    });
});

// Function to get CSRF token from cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}