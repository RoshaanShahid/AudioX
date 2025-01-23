document.addEventListener('DOMContentLoaded', function () {
    const menuToggle = document.getElementById('menu-toggle');
    const sliderMenu = document.getElementById('slider-menu');
    const closeButton = document.getElementById('close-slider');
    const hasSubmenuItems = document.querySelectorAll('.has-submenu');

    // Toggle menu visibility when the button is clicked
    function toggleSliderMenu() {
        sliderMenu.classList.toggle('show');
    }

    // Close menu when the close button is clicked
    function closeSliderMenu() {
        sliderMenu.classList.remove('show');
    }

    // Toggle slider menu on button click
    menuToggle.addEventListener('click', toggleSliderMenu);

    // Close the menu on close button click
    closeButton.addEventListener('click', closeSliderMenu);

    // Prevent clicks within the slider menu from closing it
    sliderMenu.addEventListener('click', function (event) {
        event.stopPropagation();
    });

    // Add event listeners to toggle submenus
    hasSubmenuItems.forEach(item => {
        item.addEventListener('click', function(event) {
            event.stopPropagation();

            // Close other open submenus and their parent items
            hasSubmenuItems.forEach(otherItem => {
                if (otherItem !== this) {
                    otherItem.classList.remove('open');
                    const otherSubmenu = otherItem.nextElementSibling;
                    if (otherSubmenu && otherSubmenu.classList.contains('sub-menu')) {
                        otherSubmenu.classList.remove('open');
                    }
                }
            });

            // Toggle the 'open' class on the clicked item
            this.classList.toggle('open');

            // Find the associated submenu and toggle its 'open' class
            const submenu = this.nextElementSibling;
            if (submenu && submenu.classList.contains('sub-menu')) {
                submenu.classList.toggle('open');
            }
        });
    });

    // Close menu if clicked outside
    document.addEventListener('click', function (event) {
        if (!sliderMenu.contains(event.target) && !menuToggle.contains(event.target)) {
            closeSliderMenu();
        }
    });
});