document.addEventListener('DOMContentLoaded', function () {
    const menuToggle = document.getElementById('menu-toggle');
    const sliderMenu = document.getElementById('slider-menu');
    const closeButton = document.getElementById('close-slider');

    // Toggle menu visibility when the button is clicked
    function toggleSliderMenu() {
        sliderMenu.classList.toggle('show'); // Toggle 'show' class for smooth visibility
    }

    // Close menu when the close button is clicked
    function closeSliderMenu() {
        sliderMenu.classList.remove('show'); // Remove 'show' class to hide the menu
    }

    // Toggle slider menu on button click
    menuToggle.addEventListener('click', toggleSliderMenu);

    // Close the menu on close button click
    closeButton.addEventListener('click', closeSliderMenu);

    // Optional: Close menu if clicked outside
    document.addEventListener('click', function (event) {
        // Check if the clicked target is neither the menu nor the toggle button
        if (!sliderMenu.contains(event.target) && !menuToggle.contains(event.target)) {
            closeSliderMenu(); // Close menu if clicked outside
        }
    });

    // Add smooth transitions to dropdown items
    const dropdowns = document.querySelectorAll('details');
    dropdowns.forEach(function (dropdown) {
        dropdown.addEventListener('toggle', function () {
            dropdown.querySelector('summary').classList.toggle('open', dropdown.open);
        });
    });
});
