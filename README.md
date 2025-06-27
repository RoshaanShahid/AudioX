🎵 AudioX – Multilingual Audiobook Platform

AudioX is a web-based audiobook platform that supports mainstream and regional languages like Urdu, Punjabi, and Sindhi. The platform is built using Django with Jinja templating, PostgreSQL, and several Google Cloud APIs. It provides an inclusive listening experience for diverse audiences and supports audiobook creators through content upload and monetization features.

🚀 Features

👤 User-Centric Features

🔊 Audiobooks in Urdu, Punjabi, Sindhi, and English

🌐 Free & Premium Subscription Model

📥 Offline Download & Listening

💖 Personalized Libraries & Audio Lists

🔍 Smart Search (by Genre, Author, Title, and TTS-based)

⏯️ Playback Customization (speed control, bookmarking, clip saving)

🌟 Trending & Recommended Sections

📅 Listening History & Downloads

🖊️ User Reviews, Ratings, & Support Tickets

🎁 Audiobook Gifting System

🎤 Creator-Centric Features

📅 Chapter-wise Audio Upload

📊 Creator Dashboard with Earnings Report

📃 Wallet and Withdrawal System

💎 Creator Application & Moderation Workflow

💬 Community Chatrooms per Chapter

🛠️ Advanced Tools & Admin Features

📄 Document-to-Audio Conversion

🏆 Top Audiobooks by Category

📉 Audio Summarization

📆 Admin Panel for Moderation, Analytics, and Management

📊 Tech Stack

Backend: Django, Celery, Django Channels

Frontend: Jinja Templating

Database: PostgreSQL

Cloud APIs: Google Cloud Speech-to-Text, Edge TTS ,Text-to-Speech, OpenAI

Task Queue: Celery + Redis

Real-time Features: WebSockets, Channels, Daphne

Payment Gateway: Stripe

📁 Project Structure Overview

AudioX/
├── AudioXApp/
│   ├── templates/         # Jinja Templates (users, creators, admin, features)
│   ├── views/             # Organized views for admin, creator, user, features
│   ├── models.py          # Models for users, audiobooks, etc.
│   ├── tasks.py           # Celery Tasks
│   ├── consumer.py        # WebSocket Consumers
│   └── ...                # Other Django-related files
├── AudioXCore/
│   ├── settings.py        # Django project settings
│   ├── asgi.py, wsgi.py   # Server config
├── static/                # Static files: CSS, JS, Images
├── media/                 # Media uploads
├── templates/             # Base templates
├── requirements.txt       # Python dependencies
├── manage.py              # Django project manager
└── .env                   # Environment variables

📆 Installation & Setup

1. Clone the Repository

git clone https://github.com/RoshaanShahid/AudioX.git
cd AudioX

2. Create & Activate Virtual Environment

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

3. Install Requirements

pip install -r requirements.txt

4. Set Environment Variables

Create a .env file for your local environment:

SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=your-postgres-connection-url
...

5. Run Migrations & Start Server

python manage.py migrate
python manage.py runserver

📑 Requirements

Install dependencies:

pip install -r requirements.txt

This project uses:

Django, channels, celery, djangorestframework

google-cloud-speech, google-cloud-texttospeech, gTTS

ffmpeg-python, PyMuPDF, stripe, openai

Full list in requirements.txt

👨‍💼 Authors

Roshaan Shahid

GitHub: RoshaanShahid

Email: malikrushaan26@gmail.com

LinkedIn: linkedin.com/in/roshaan-shahid-8251bb227

Burhan Aqeel

GitHub: burhanaqee

Email: Iam.burhanaqeel@gmail.com

LinkedIn: linkedin.com/in/burhanaqeel

📄 License

This project is part of a university Final Year Project (FYP) and not licensed for public commercial use. Contact the authors for permission to reuse any part.

