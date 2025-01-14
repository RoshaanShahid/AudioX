document.addEventListener('DOMContentLoaded', function() {
    function activateTab(tabId) {
        // Deactivate all tabs
        document.querySelectorAll('.nav-link').forEach(tab => {
            tab.classList.remove('active');
        });

        // Hide all tab panes
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('active', 'show');
        });

        // Activate the clicked tab
        const activeTab = document.querySelector(`.nav-link[data-department="${tabId}"]`);
        if (activeTab) {
            activeTab.classList.add('active');
        }

        // Show the corresponding tab pane
        const activePane = document.getElementById(tabId);
        if (activePane) {
            activePane.classList.add('active', 'show');
        }
    }

    // Add click event listeners to tabs
    document.querySelectorAll('.nav-link').forEach(tab => {
        tab.addEventListener('click', function(event) {
            event.preventDefault();
            activateTab(this.dataset.department);
        });
    });

    // Activate the first tab and its content on page load
    activateTab('cofounders');
});