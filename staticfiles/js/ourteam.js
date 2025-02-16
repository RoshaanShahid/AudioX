document.addEventListener('DOMContentLoaded', function() {
    const tabList = document.querySelector('.tab-list');
    const teamGrid = document.getElementById('teamGrid');

    function displayTeamMembers(tab) {
        // Hide all tab contents
        const tabContents = teamGrid.querySelectorAll('.tab-content');
        tabContents.forEach(content => content.classList.remove('active'));

        // Show the selected tab content
        const selectedTabContent = document.getElementById(tab);
        if (selectedTabContent) {
            selectedTabContent.classList.add('active');
        }
    }

    // Event delegation for tab clicks
    tabList.addEventListener('click', (event) => {
        if (event.target.tagName === 'LI') {
            const selectedTab = event.target.dataset.tab;

            // Remove active class from all tabs
            const tabs = tabList.querySelectorAll('li');
            tabs.forEach(tab => tab.classList.remove('active'));

            // Add active class to the clicked tab
            event.target.classList.add('active');

            displayTeamMembers(selectedTab);
        }
    });

    // Initial display
    displayTeamMembers('cofounders');
});