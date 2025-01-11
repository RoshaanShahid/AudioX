let isRecording = false;  // Flag to track recording state
let recognition;  // Global variable for speech recognition instance
const searchInput = document.getElementById('search-input');
const voiceButton = document.getElementById('voice-search-btn');
const searchButton = document.getElementById('search-btn');

// Initialize voice recognition
function initializeSpeechRecognition() {
    if (!('webkitSpeechRecognition' in window)) {
        console.error('Voice search is not supported on your browser.');
        alert('Voice search is not supported on your browser. Please use Chrome or Edge.');
        return null;
    }

    const recognitionInstance = new webkitSpeechRecognition();
    recognitionInstance.lang = 'en-US';
    recognitionInstance.continuous = false;
    recognitionInstance.interimResults = false;

    recognitionInstance.onstart = function () {
        console.log("Voice recognition started. Speak now.");
        searchInput.placeholder = "Listening...";
    };

    recognitionInstance.onerror = function (event) {
        console.error('Speech recognition error: ', event.error);
        alert('Error occurred in speech recognition: ' + event.error);
        stopRecording(); // Stop on error
    };

    recognitionInstance.onresult = function (event) {
        const transcript = event.results[0][0].transcript;
        console.log('Voice recognition result: ', transcript);

        // Remove the full stop at the end of the transcript if it exists
        const cleanedTranscript = transcript.endsWith('.') ? transcript.slice(0, -1) : transcript;

        searchInput.value = cleanedTranscript;
        searchInput.placeholder = "Search audiobooks & stories";
        searchBooks();  // Perform search after receiving input
    };

    recognitionInstance.onend = function () {
        console.log("Voice recognition ended.");
        stopRecording(); // Clean up after recognition ends
    };

    console.log("Speech recognition initialized.");
    return recognitionInstance;
}

// Start recording
function startRecording() {
    if (!recognition) {
        recognition = initializeSpeechRecognition();
    }
    if (!recognition) return;

    isRecording = true;
    voiceButton.style.backgroundColor = "#4CAF50";  // Indicate recording state
    recognition.start();
    console.log("Recording started...");
}

// Stop recording
function stopRecording() {
    if (recognition) {
        recognition.stop();
        console.log("Recording stopped.");
    }
    isRecording = false;
    voiceButton.style.backgroundColor = "#091e65";  // Reset button color
    searchInput.placeholder = "Search audiobooks & stories";
}

// Handle microphone button click
voiceButton.addEventListener('click', function () {
    console.log('Microphone button clicked');
    if (isRecording) {
        stopRecording();
    } else {
        // Reset search input when microphone is clicked after voice search
        if (searchInput.value.trim() !== '') {
            searchInput.value = ''; // Reset the input
            searchInput.placeholder = 'Search audiobooks & stories'; // Reset placeholder
        }
        startRecording();
    }
});

// Handle tooltip on hover
voiceButton.addEventListener('mouseover', function () {
    voiceButton.setAttribute('title', 'Search by Voice');
});

// Perform search
function searchBooks() {
    const query = searchInput.value.trim();
    if (query === '') {
        alert('Please enter a search term or use the voice search feature.');
        return;
    }

    console.log('Searching books for:', query);

    // Example: Trigger a search in the backend
    fetch(`/search/?query=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            console.log('Search results:', data);
            // Dynamically handle results here
        })
        .catch(error => {
            console.error('Error fetching search results:', error);
        });
}

// Handle search button click
searchButton.addEventListener('click', function () {
    searchBooks();
});

// Toggle slider menu visibility
document.getElementById('menu-toggle').addEventListener('click', function () {
    const sliderMenu = document.getElementById('slider-menu');
    sliderMenu.classList.toggle('open');
});

// Close slider menu when clicking outside
document.addEventListener('click', function (event) {
    const sliderMenu = document.getElementById('slider-menu');
    const menuToggle = document.getElementById('menu-toggle');
    if (!sliderMenu.contains(event.target) && event.target !== menuToggle) {
        sliderMenu.classList.remove('open');
    }
});
