// This script handles client-side interactions for the Creator Earnings Dashboard,
// primarily managing the Alpine.js component for filtering and loading states.

document.addEventListener('DOMContentLoaded', function() {
    // Event listener to update the main content loading state for the Alpine.js component
    window.addEventListener('setmainloading', (event) => {
        // Find the Alpine.js component root element that controls 'mainContentLoading'
        const mainContentAlpine = document.querySelector('[x-data*="mainContentLoading"]');
        if (mainContentAlpine && mainContentAlpine.__x) { // Check if Alpine has initialized on the element
            mainContentAlpine.__x.$data.mainContentLoading = event.detail; // Update the Alpine data property
        } else {
            console.warn("Alpine.js component for 'mainContentLoading' not found or not initialized.");
        }
    });

    // Event listener to update the book list loading state for the Alpine.js component
    window.addEventListener('setbooklistloading', (event) => {
        // Find the Alpine.js component root element that controls 'bookListLoadingState'
        // This might be the same component as above or a different one depending on your HTML structure.
        // Assuming it's on the same main component for this example.
        const mainContentAlpine = document.querySelector('[x-data*="mainContentLoading"]'); 
        if (mainContentAlpine && mainContentAlpine.__x) { // Check if Alpine has initialized
            mainContentAlpine.__x.$data.bookListLoadingState = event.detail; // Update the Alpine data property
        } else {
            console.warn("Alpine.js component for 'bookListLoadingState' not found or not initialized.");
        }
    });

    // You can add more page-specific JavaScript for creator_myearnings.html here if needed.
    console.log("creator_myearnings.js loaded"); 
});
