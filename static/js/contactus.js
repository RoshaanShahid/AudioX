document.addEventListener('DOMContentLoaded', function() {
    const tabs = document.querySelectorAll('.tab');
    const overlay = document.getElementById('overlay');
    const faqSection = document.getElementById('faqSection');
    const faqQuestions = document.querySelectorAll('.faq-question');
  
    tabs.forEach(tab => {
      tab.addEventListener('click', function() {
        const targetId = this.dataset.target;
  
        // Remove active class from all tabs and tab contents
        tabs.forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));
  
        // Add active class to the clicked tab
        this.classList.add('active');
  
        if (targetId === 'faqSection') {
          // Show FAQ section
          faqSection.classList.add('active');
          overlay.style.display = 'none';
        } else {
          // Hide FAQ section
          faqSection.classList.remove('active');
  
          // For other popups, show overlay
          const targetPopup = document.getElementById(targetId);
          targetPopup.style.display = 'block';
          overlay.style.display = 'block';
        }
      });
    });
  
    faqQuestions.forEach(question => {
      question.addEventListener('click', function() {
        const parentItem = this.closest('.faq-item');
        const answer = parentItem.querySelector('.faq-answer');
  
        // Toggle the active class on the parent FAQ item
        parentItem.classList.toggle('active');
  
        // Toggle the display of the answer
        if (answer.style.display === 'block') {
          answer.style.display = 'none';
        } else {
          answer.style.display = 'block';
        }
      });
    });
  });
  
  function closePopup(popupId) {
    const popup = document.getElementById(popupId);
    popup.style.display = 'none';
    document.getElementById('overlay').style.display = 'none';
  }
  
  function openChat() {
    alert("Chat functionality will be implemented soon!");
  }