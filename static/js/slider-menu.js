document.addEventListener('DOMContentLoaded', function () {
    const menuToggle = document.getElementById('menu-toggle');
    const sliderMenu = document.getElementById('slider-menu');

    // Toggle menu visibility when button is clicked
    menuToggle.addEventListener('click', function () {
        // Check the current position of the menu and toggle
        if (sliderMenu.style.left === '0px') {
            sliderMenu.style.left = '-300px'; // Hide menu
        } else {
            sliderMenu.style.left = '0px'; // Show menu
        }
    });

    // Optional: Close menu if clicked outside
    document.addEventListener('click', function (event) {
        if (!sliderMenu.contains(event.target) && !menuToggle.contains(event.target)) {
            sliderMenu.style.left = '-300px'; // Close menu when clicking outside
        }
    });
});
