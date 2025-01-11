const togglePassword = document.getElementById('togglePassword');
const passwordField = document.getElementById('password');
const usernameField = document.getElementById('username');
const usernameError = document.getElementById('usernameError');
const passwordError = document.getElementById('passwordError');
const form1 = document.getElementById('loginForm');
const form2 = document.getElementById('signupForm');

togglePassword.addEventListener('click', () => {
    const type = passwordField.type === 'password' ? 'text' : 'password';
    passwordField.type = type;
    togglePassword.classList.toggle('fa-eye');
    togglePassword.classList.toggle('fa-eye-slash');
});

form1.addEventListener('submit', function (e) {
    e.preventDefault();

    let valid = true;

    // Validate username
    const usernamePattern = /^[A-Za-z0-9_]{3,15}$/;
    if (!usernamePattern.test(usernameField.value)) {
        usernameError.textContent = 'Username must be 3-15 characters long and contain only letters, numbers, and underscores.';
        valid = false;
    } else {
        usernameError.textContent = '';
    }

    // Validate password
    if (passwordField.value.length < 8) {
        passwordError.textContent = 'Password must be at least 8 characters long.';
        valid = false;
    } else {
        passwordError.textContent = '';
    }

    // If all validations pass, submit the form (for example, sending to a server)
    if (valid) {
        alert("Form submitted successfully!");
    }
});

form2.addEventListener('submit', function (e) {
    e.preventDefault();
    alert("Login successful!");
});