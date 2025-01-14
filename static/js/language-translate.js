document.addEventListener('DOMContentLoaded', function () {
    const languageSelector = document.getElementById('language-selector');

    // Translation object
    const translations = {
        en: {
            //English translations
            menu: "☰",
            audio: "AUDIO",
            x: "X",
            search_placeholder: "Search audiobooks & stories",
            buy_coins: "🪙 Buy Coins",
            login: "Login",
            signup: "Signup",
            login_signup: "Login / Signup",
            login_signup_subtitle: "For a better & personalized experience",
            buy_premium: "Buy Premium",
            for_creators: "For Creators",
            about: "About",
            our_team: "Our Team",
            about_us: "About Us",
            legal: "Legal",
            contact_us: "Contact Us",
            privacy_policy: "Privacy Policy",
            payment_policy: "Payment Policy",
            piracy_policy: "Piracy Policy",
            terms_and_conditions: "Terms and Conditions",
            help_support: "Help & Support",
            made_with_love: "Made with ❤️ in Pakistan",
            footer_about: "AudioX is a unique audiobook platform that provides audiobooks in multiple languages. Our mission is to make reading easier and more accessible for people across Pakistan and beyond, by offering content in various regional languages.",
            follow_us: "FOLLOW US ON",
            company: "COMPANY",
            careers: "Careers",
            contact: "Contact",
            general: "GENERAL",
            faq: "FAQ",
            licensing: "Licensing",
            copyright: "Copyright",
            terms_of_service: "Terms of Service",
            genres: "GENRES",
            fiction: "Fiction",
            non_fiction: "Non-Fiction",
            science: "Science",
            copyright_text: "&copy; 2025 AudioX. All Rights Reserved."
        },
        ur: {
            //Urdu translations
            menu: "☰",
            audio: "آڈیو",
            x: "ایکس",
            search_placeholder: "آڈیو بکس اور کہانیاں تلاش کریں۔",
            buy_coins: " سکے خریدیں",
            login: "لاگ ان",
            signup: "سائن اپ",
            login_signup: "لاگ ان / سائن اپ",
            login_signup_subtitle: "بہتر اور ذاتی نوعیت کے تجربے کے لیے",
            buy_premium: "پریمیم خریدیں",
            for_creators: "تخلیق کاروں کے لیے",
            about: "کے بارے میں",
            our_team: "ہماری ٹیم",
            about_us: "ہمارے بارے میں",
            legal: "قانونی",
            contact_us: "ہم سے رابطہ کریں",
            privacy_policy: "رازداری کی پالیسی",
            payment_policy: "ادائیگی کی پالیسی",
            piracy_policy: "پائریسی پالیسی",
            terms_and_conditions: "شرائط و ضوابط",
            help_support: "مدد اور حمایت",
            made_with_love: "پاکستان میں ❤️ کے ساتھ بنایا گیا",
            footer_about: "AudioX ایک منفرد آڈیو بک پلیٹ فارم ہے جو ایک سے زیادہ زبانوں میں آڈیو بکس فراہم کرتا ہے۔ ہمارا مشن پاکستان اور اس سے باہر کے لوگوں کے لیے پڑھنے کو آسان اور زیادہ قابل رسائی بنانا ہے، مختلف علاقائی زبانوں میں مواد پیش کر کے۔",
            follow_us: "ہمیں فالو کریں",
            company: "کمپنی",
            careers: "کیریئرز",
            contact: "رابطہ کریں۔",
            general: "عمومی",
            faq: "اکثر پوچھے گئے سوالات",
            licensing: "لائسنسنگ",
            copyright: "کاپی رائٹ",
            terms_of_service: "سروس کی شرائط",
            genres: "انواع",
            fiction: "افسانے",
            non_fiction: "نان فکشن",
            science: "سائنس",
            copyright_text: "© 2025 AudioX. جملہ حقوق محفوظ ہیں۔"
        }
    };

    function translatePage(language) {
        const elementsToTranslate = document.querySelectorAll('[data-translate]');

        elementsToTranslate.forEach(element => {
            const key = element.dataset.translate;
            if (translations[language] && translations[language][key]) {
                element.textContent = translations[language][key];
            }
        });
    }

    languageSelector.addEventListener('change', function () {
        const selectedLanguage = languageSelector.value;
        translatePage(selectedLanguage);
    });

    // Initial translation (to English by default)
    translatePage('en');
});