# AudioXApp/tts_constants.py

"""
This file holds constants related to Text-to-Speech (TTS) voices
and language/genre mappings to avoid circular imports between view files.
"""

# --- TTS Voice and Language/Genre Constants ---

EDGE_TTS_VOICES_BY_LANGUAGE = {
    'English': [
        {'id': 'en-US-AriaNeural', 'name': 'Aria (Female)', 'gender': 'female', 'edge_voice_id': 'en-US-AriaNeural'},
        {'id': 'en-US-GuyNeural', 'name': 'Guy (Male)', 'gender': 'male', 'edge_voice_id': 'en-US-GuyNeural'},
        {'id': 'en-GB-LibbyNeural', 'name': 'Libby (Female, UK)', 'gender': 'female', 'edge_voice_id': 'en-GB-LibbyNeural'},
        {'id': 'en-GB-RyanNeural', 'name': 'Ryan (Male, UK)', 'gender': 'male', 'edge_voice_id': 'en-GB-RyanNeural'},
        {'id': 'en-AU-NatashaNeural', 'name': 'Natasha (Female, AU)', 'gender': 'female', 'edge_voice_id': 'en-AU-NatashaNeural'},
        {'id': 'en-IN-NeerjaNeural', 'name': 'Neerja (Female, IN)', 'gender': 'female', 'edge_voice_id': 'en-IN-NeerjaNeural'},
    ],
    'Urdu': [
        {'id': 'ur-PK-UzmaNeural', 'name': 'Uzma (Female)', 'gender': 'female', 'edge_voice_id': 'ur-PK-UzmaNeural'},
        {'id': 'ur-PK-AsadNeural', 'name': 'Asad (Male)', 'gender': 'male', 'edge_voice_id': 'ur-PK-AsadNeural'},
    ],
    'Punjabi': [],
    'Sindhi': [],
}

ALL_EDGE_TTS_VOICES_MAP = {
    voice['id']: voice
    for lang_voices in EDGE_TTS_VOICES_BY_LANGUAGE.values()
    for voice in lang_voices
}

LANGUAGE_GENRE_MAPPING = {
    "English": [
        {"value": "Fiction", "text": "Fiction"}, {"value": "Mystery", "text": "Mystery"},
        {"value": "Thriller", "text": "Thriller"}, {"value": "Sci-Fi", "text": "Sci-Fi"},
        {"value": "Fantasy", "text": "Fantasy"}, {"value": "Romance", "text": "Romance"},
        {"value": "Biography", "text": "Biography"}, {"value": "History", "text": "History"},
        {"value": "Self-Help", "text": "Self-Help"}, {"value": "Business", "text": "Business"},
        {"value": "Children", "text": "Children's Story"}, {"value": "Poetry", "text": "Poetry"},
        {"value": "Horror", "text": "Horror"}, {"value": "Comedy", "text": "Comedy"},
        {"value": "Education", "text": "Education"}, {"value": "Religion-Spirituality", "text": "Religion & Spirituality"},
        {"value": "Other", "text": "Other"}
    ],
    "Urdu": [
        {"value": "Novel", "text": "Novel (ناول)"}, {"value": "Afsana", "text": "Afsana (افسانہ)"},
        {"value": "Shayari", "text": "Shayari (شاعری)"}, {"value": "Tareekh", "text": "Tareekh (تاریخ)"},
        {"value": "Safarnama", "text": "Safarnama (سفرنامہ)"}, {"value": "Mazah", "text": "Mazah (مزاح)"},
        {"value": "Bachon ka Adab", "text": "Bachon ka Adab (بچوں کا ادب)"},
        {"value": "Mazhabi Adab", "text": "Mazhabi Adab (مذہبی ادب)"}, {"value": "Siyasi Adab", "text": "Siyasi Adab (سیاسی ادب)"},
        {"value": "Falsafa", "text": "Falsafa (فلسفہ)"}, {"value": "Deegar", "text": "Deegar (دیگر)"}
    ],
    "Punjabi": [
        {"value": "Qissa", "text": "Qissa (قصہ)"},
        {"value": "Lok Geet", "text": "Lok Geet (لوک گیت)"},
        {"value": "Kafi", "text": "Kafi (کافی)"},
        {"value": "Punjabi-Other", "text": "Other (ہور)"}
    ],
    "Sindhi": [
        {"value": "Lok Adab", "text": "Lok Adab (لوڪ ادب)"},
        {"value": "Shayari", "text": "Shayari (شاعري)"},
        {"value": "Kahani", "text": "Kahani (ڪهاڻي)"},
        {"value": "Sindhi-Other", "text": "Other (ٻيو)"}
    ]
}