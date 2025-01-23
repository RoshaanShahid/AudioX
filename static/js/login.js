document.addEventListener('DOMContentLoaded', function () {
    const form = document.querySelector('form');
    const loginButton = document.querySelector('.btn');
    const togglePassword = document.getElementById('togglePassword'); // Get the icon
    const passwordField = document.getElementById('password'); // Get the password field

    form.addEventListener('submit', function () {
        // Disable the button and add a loading spinner
        loginButton.disabled = true;
        loginButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    });

    // Show/Hide Password Functionality
    if (togglePassword && passwordField) { // Check if both elements exist
        togglePassword.addEventListener('click', function () {
            // Toggle the type attribute of the password field
            const type = passwordField.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordField.setAttribute('type', type);

            // Toggle the eye icon class (for visual feedback)
            this.classList.toggle('fa-eye');
            this.classList.toggle('fa-eye-slash');
        });
    }
});