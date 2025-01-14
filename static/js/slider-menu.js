document.addEventListener('DOMContentLoaded', function () {
    const menuToggle = document.getElementById('menu-toggle');
    const sliderMenu = document.getElementById('slider-menu');
    const closeButton = document.getElementById('close-slider');
    const hasSubmenuItems = document.querySelectorAll('.has-submenu');

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

    // Add event listeners to toggle submenus
    hasSubmenuItems.forEach(item => {
        item.addEventListener('click', function(event) {
            // Prevent the click from propagating to the document click listener
            event.stopPropagation();

            // Toggle the 'open' class on the clicked item
            this.classList.toggle('open');

            // Find the associated submenu and toggle its 'open' class
            const submenu = this.nextElementSibling;
            if (submenu && submenu.classList.contains('sub-menu')) {
                submenu.classList.toggle('open');
            }
        });
    });
});