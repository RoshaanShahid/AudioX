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
    const otpField = document.getElementById('otp');
    const verifyOtpButton = document.getElementById("verifyOtpButton");
    const resendOtpButton = document.getElementById('resendOtpButton');
    const otpMessage = document.getElementById('otpMessage');
    const otpError = document.getElementById('otpError');

    let currentStep = 1;
    const totalSteps = 7;
    const nextButton = document.getElementById("nextButton");
    const previousButton = document.getElementById("previousButton");
    const submitButton = document.getElementById("submitButton");

    const phoneInput = window.intlTelInput(phoneField, {
        preferredCountries: ['pk'],
        separateDialCode: true,
        utilsScript: "https://cdnjs.cloudflare.com/ajax/libs/intl-tel-input/17.0.8/js/utils.js",
    });

    function showStep(stepNumber) {
        for (let i = 1; i <= totalSteps; i++) {
            document.getElementById('step' + i).style.display = 'none';
        }
        document.getElementById('step' + stepNumber).style.display = 'block';

        // Adjust button visibility for each step
        if (stepNumber === 4) {
            // On step 4 (Email), show only Verify OTP button
            nextButton.style.display = 'none';
            previousButton.style.display = 'inline-block';
            verifyOtpButton.style.display = 'inline-block';
            resendOtpButton.style.display = 'none';
            submitButton.style.display = 'none';
        } else if (stepNumber === 5) {
            // On step 5 (OTP), show Resend OTP and Next button
            nextButton.style.display = 'inline-block'; // Now showing Next button
            previousButton.style.display = 'inline-block';
            verifyOtpButton.style.display = 'none';
            resendOtpButton.style.display = 'inline-block';
            submitButton.style.display = 'none';
        } else if (stepNumber === totalSteps) {
            // On the last step, show only Submit button
            nextButton.style.display = 'none';
            previousButton.style.display = 'inline-block';
            verifyOtpButton.style.display = 'none';
            resendOtpButton.style.display = 'none';
            submitButton.style.display = 'inline-block';
        } else if (stepNumber === 6) {
            // On step 6 (Password), show Next button
            nextButton.style.display = 'inline-block';
            previousButton.style.display = 'inline-block';
            verifyOtpButton.style.display = 'none';
            resendOtpButton.style.display = 'none';
            submitButton.style.display = 'none';
        }
        else {
            // On other steps, show Next and Previous buttons
            nextButton.style.display = 'inline-block';
            previousButton.style.display = (stepNumber > 1) ? 'inline-block' : 'none';
            verifyOtpButton.style.display = 'none';
            resendOtpButton.style.display = 'none';
            submitButton.style.display = 'none';
        }
    }

    function validateCurrentStep() {
        let isValid = true;

        switch (currentStep) {
            case 1:
                if (fullNameField.value.trim() === "") {
                    document.getElementById('fullNameError').textContent = 'Full Name cannot be empty';
                    isValid = false;
                } else {
                    document.getElementById('fullNameError').textContent = '';
                }
                break;
            case 2:
                const usernamePattern = /^[a-zA-Z][a-zA-Z0-9_]{2,11}$/;
                if (!usernamePattern.test(usernameField.value)) {
                    usernameError.textContent = 'Username must start with a letter, be 3-12 characters long, and can only include letters, numbers, and underscores.';
                    isValid = false;
                } else {
                    usernameError.textContent = '';
                }
                break;
            case 3:
                if (!phoneInput.isValidNumber()) {
                    document.getElementById("phoneError").textContent = "Invalid phone number";
                    isValid = false;
                } else {
                    document.getElementById("phoneError").textContent = "";
                }
                break;
            case 4:
                const emailPattern = /^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}$/;
                if (!emailPattern.test(emailField.value)) {
                    document.getElementById('emailError').textContent = 'Please enter a valid email address.';
                    isValid = false;
                } else {
                    document.getElementById('emailError').textContent = '';
                }
                break;
            case 5:
                if (otpField.value.trim() === "") {
                    otpError.textContent = 'OTP cannot be empty';
                    isValid = false;
                } else {
                    otpError.textContent = '';
                }
                break;
            case 6:
                if (passwordField.value.length < 8) {
                    passwordError.textContent = 'Password must be at least 8 characters long.';
                    isValid = false;
                } else {
                    passwordError.textContent = '';
                }
                break;
            case 7:
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

    function generateOTP() {
        return Math.floor(1000 + Math.random() * 9000);
    }

    function sendOTP(email, otp) {
        const sendOtpUrl = document.getElementById('signupForm').getAttribute('data-send-otp-url');
        $.ajax({
            url: sendOtpUrl,
            type: "POST",
            data: {
                email: email,
                otp: otp,
                csrfmiddlewaretoken: $('input[name=csrfmiddlewaretoken]').val()
            },
            success: function (data) {
                if (data.status === 'success') {
                    otpMessage.textContent = 'OTP sent to your email!';
                    otpMessage.style.color = 'green';
                    currentStep = 5;
                    showStep(currentStep);
                } else {
                    otpMessage.textContent = 'Error sending OTP: ' + data.message;
                    otpMessage.style.color = 'red';
                }
            },
            error: function (xhr, status, error) {
                console.error("Error in sendOTP:", error);
                otpMessage.textContent = 'Error sending OTP. Please check console for details.';
                otpMessage.style.color = 'red';
            }
        });
    }

    nextButton.addEventListener('click', function () {
        if (validateCurrentStep()) {
            if (currentStep === 5) {
                // Validate OTP on 'Next' click in step 5
                const userEnteredOtp = otpField.value;
                const generatedOtp = document.getElementById('generatedOtp').value;

                if (userEnteredOtp !== generatedOtp) {
                    otpError.textContent = 'Invalid OTP. Please try again.';
                    removeLoadingAnimation(nextButton); // Remove animation if OTP is invalid
                    return;
                } else {
                    otpError.textContent = '';
                    currentStep++;
                    showStep(currentStep);
                }
            } else if (currentStep < totalSteps) {
                currentStep++;
                showStep(currentStep);
            }
        }
    });

    previousButton.addEventListener('click', function () {
    });

    verifyOtpButton.addEventListener('click', function () {
        if (validateCurrentStep()) {
            const generatedOtp = generateOTP();
            document.getElementById('generatedOtp').value = generatedOtp;
            sendOTP(emailField.value, generatedOtp);
        }
    });

    resendOtpButton.addEventListener('click', function () {
        const generatedOtp = generateOTP();
        document.getElementById('generatedOtp').value = generatedOtp;
        sendOTP(emailField.value, generatedOtp);
    });

    togglePassword.addEventListener('click', () => {
        const type = passwordField.type === 'password' ? 'text' : 'password';
        passwordField.type = type;
        togglePassword.classList.toggle('fa-eye');
        togglePassword.classList.toggle('fa-eye-slash');
    });

    passwordField.addEventListener('input', updatePasswordStrengthIndicator);

    signupForm.addEventListener('submit', function (e) {
        e.preventDefault();

        const userEnteredOtp = otpField.value;
        const generatedOtp = document.getElementById('generatedOtp').value;

        if (userEnteredOtp !== generatedOtp) {
            otpError.textContent = 'Invalid OTP. Please try again.';
            return;
        } else {
            otpError.textContent = '';
        }

        let allStepsValid = true;
        for (let i = 1; i <= totalSteps; i++) {
            currentStep = i;
            if (!validateCurrentStep()) {
                allStepsValid = false;
                showStep(currentStep);
                return;
            }
        }

        if (allStepsValid) {
            const countryData = phoneInput.getSelectedCountryData();
            phoneField.value = '+' + countryData.dialCode + phoneField.value.replace(/\D/g, '');
            signupForm.submit();
        }
    });

    showStep(currentStep);
});