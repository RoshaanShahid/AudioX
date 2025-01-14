document.addEventListener('DOMContentLoaded', function () {
    const togglePassword = document.getElementById('togglePassword');
    const passwordField = document.getElementById('password');
    const usernameField = document.getElementById('username');
    const fullNameField = document.getElementById('full-name');
    const phoneField = document.getElementById('phone');
    const emailField = document.getElementById('email');
    const confirmPasswordField = document.getElementById('confirm-password');
    const usernameError = document.getElementById('usernameError');
    const passwordError = document.getElementById('passwordError');
    const confirmPasswordError = document.getElementById('confirmPasswordError');
    const passwordStrengthIndicator = document.getElementById('passwordStrengthIndicator');
    const signupForm = document.getElementById('signupForm');

    let currentStep = 1;
    const totalSteps = 6; // Update total steps to 6
    const nextButton = document.getElementById("nextButton");
    const previousButton = document.getElementById("previousButton");
    const submitButton = document.getElementById("submitButton");

    // Initialize intl-tel-input
    const phoneInput = window.intlTelInput(phoneField, {
        preferredCountries: ['pk'], // Set preferred country to Pakistan
        separateDialCode: true,
        utilsScript: "https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.8/js/utils.js",
    });

    // Function to show a specific step
    function showStep(stepNumber) {
        for (let i = 1; i <= totalSteps; i++) {
            document.getElementById('step' + i).style.display = 'none';
        }
        document.getElementById('step' + stepNumber).style.display = 'block';

        if (stepNumber === totalSteps) {
            nextButton.style.display = 'none';
            submitButton.style.display = 'inline-block';
        } else {
            nextButton.style.display = 'inline-block';
            submitButton.style.display = 'none';
        }

        if (stepNumber === 1) {
            previousButton.style.display = 'none';
        } else {
            previousButton.style.display = 'inline-block';
        }
    }

    // Function to validate the fields of the current step
    function validateCurrentStep() {
        let isValid = true;

        switch (currentStep) {
            case 1: // Full Name
                if (fullNameField.value.trim() === "") {
                    document.getElementById('fullNameError').textContent = 'Full Name cannot be empty';
                    isValid = false;
                } else {
                    document.getElementById('fullNameError').textContent = '';
                }
                break;
            case 2: // Username
                const usernamePattern = /^[a-zA-Z][a-zA-Z0-9_]{2,11}$/;
                if (!usernamePattern.test(usernameField.value)) {
                    usernameError.textContent = 'Username must start with a letter, be 3-12 characters long, and can only include letters, numbers, and underscores.';
                    isValid = false;
                } else {
                    usernameError.textContent = '';
                }
                break;
            case 3: // Phone number
                if (!phoneInput.isValidNumber()) {
                    document.getElementById("phoneError").textContent = "Invalid phone number";
                    isValid = false;
                } else {
                    document.getElementById("phoneError").textContent = "";
                }
                break;
            case 4: // Email 
                const emailPattern = /^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}$/;
                if (!emailPattern.test(emailField.value)) {
                    document.getElementById('emailError').textContent = 'Please enter a valid email address.';
                    isValid = false;
                } else {
                    document.getElementById('emailError').textContent = '';
                }
                break;
            case 5: // Password
                if (passwordField.value.length < 8) {
                    passwordError.textContent = 'Password must be at least 8 characters long.';
                    isValid = false;
                } else {
                    passwordError.textContent = '';
                }
                break;
            case 6: // Confirm Password
                if (passwordField.value !== confirmPasswordField.value) {
                    confirmPasswordError.textContent = 'Passwords do not match.';
                    isValid = false;
                } else {
                    confirmPasswordError.textContent = '';
                }
                break;
        }

        return isValid;
    }

    // Function to calculate password strength
    function calculatePasswordStrength(password) {
        if (password.length < 8) {
            return { label: "Weak", color: "red" };
        }

        let hasAlphabets = password.match(/[a-zA-Z]/);
        let hasNumbers = password.match(/[0-9]/);
        let hasSpecialChars = password.match(/[$@#&!]+/);

        if (hasAlphabets && !hasNumbers && !hasSpecialChars) {
            return { label: "Weak", color: "red" };
        } else if (hasAlphabets && hasNumbers && !hasSpecialChars) {
            return { label: "Good", color: "orange" };
        } else if (hasAlphabets && hasNumbers && hasSpecialChars) {
            return { label: "Strong", color: "green" };
        } else {
            return { label: "Weak", color: "red" };
        }
    }

    // Function to update password strength indicator
    function updatePasswordStrengthIndicator() {
        const password = passwordField.value;
        const strength = calculatePasswordStrength(password);

        const fills = document.querySelectorAll('.password-strength-indicator .bar .fill');
        fills.forEach(fill => {
            fill.style.width = '0%';
        });

        if (password.length > 0) {
            if (strength.label === "Weak") {
                document.querySelector('.password-strength-indicator .bar[data-strength="weak"] .fill').style.width = '100%';
            } else if (strength.label === "Good") {
                document.querySelector('.password-strength-indicator .bar[data-strength="weak"] .fill').style.width = '100%';
                document.querySelector('.password-strength-indicator .bar[data-strength="good"] .fill').style.width = '100%';
            } else if (strength.label === "Strong") {
                fills.forEach(fill => {
                    fill.style.width = '100%';
                });
            }
        }
    }

    // Event listener for Next Button
    nextButton.addEventListener('click', function () {
        if (validateCurrentStep()) {
            currentStep++;
            showStep(currentStep);
        }
    });

    // Event listener for Previous Button
    previousButton.addEventListener('click', function () {
        if (currentStep > 1) {
            currentStep--;
            showStep(currentStep);
        }
    });

    // Event listener for Password toggle
    togglePassword.addEventListener('click', () => {
        const type = passwordField.type === 'password' ? 'text' : 'password';
        passwordField.type = type;
        togglePassword.classList.toggle('fa-eye');
        togglePassword.classList.toggle('fa-eye-slash');
    });

    // Event listener to update password strength indicator
    passwordField.addEventListener('input', updatePasswordStrengthIndicator);

    // Event listener for Form Submission
    signupForm.addEventListener('submit', function (e) {
        e.preventDefault();

        let allStepsValid = true;
        for (let i = 1; i <= totalSteps; i++) {
            currentStep = i;
            if (!validateCurrentStep()) {
                allStepsValid = false;
                showStep(currentStep);
                break;
            }
        }

        if (allStepsValid) {
            const countryData = phoneInput.getSelectedCountryData();
            phoneField.value = '+' + countryData.dialCode + phoneField.value.replace(/\D/g, '');
            alert("Form submitted successfully!");
        }
    });

    // Initialize the form
    showStep(currentStep);
});