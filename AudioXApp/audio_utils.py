import os
import logging
from io import BytesIO

from django.core.files.base import File
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from mutagen.flac import FLAC

try:
    from pydub import AudioSegment
    from pydub.exceptions import CouldntDecodeError
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_duration_with_mutagen(file_source, filename):
    try:
        ext = os.path.splitext(filename)[1].lower()
        audio = None
        if ext in ['.mp3']:
            audio = MP3(file_source)
        elif ext in ['.wav']:
            audio = WAVE(file_source)
        elif ext in ['.m4a', '.mp4', '.m4b', '.aac']:
            audio = MP4(file_source)
        elif ext in ['.ogg', '.oga']:
            audio = OggVorbis(file_source)
        elif ext in ['.flac']:
            audio = FLAC(file_source)
        else:
            return None, "unsupported_format"

        if audio and audio.info and hasattr(audio.info, 'length'):
            return float(audio.info.length), "success"
        else:
            return None, "no_stream_info"
    except Exception as e:
        if hasattr(file_source, 'seek'):
            file_source.seek(0)
        return None, str(e)

def get_duration_with_pydub(file_source):
    if not PYDUB_AVAILABLE:
        return None, "pydub_not_installed"
    try:
        audio = AudioSegment.from_file(file_source)
        return audio.duration_seconds, "success"
    except CouldntDecodeError as e:
        return None, str(e)
    except Exception as e:
        if hasattr(file_source, 'seek'):
            file_source.seek(0)
        return None, str(e)

def get_audio_duration(file_field):
    if not file_field:
        return None

    filename = file_field.name

    file_field.seek(0)

    duration, reason = get_duration_with_mutagen(file_field, filename)
    if duration is not None:
        logger.info(f"Successfully got duration for '{filename}' with Mutagen.")
        file_field.seek(0)
        return duration

    logger.warning(f"Mutagen failed for '{filename}' (Reason: {reason}). Falling back to pydub/ffmpeg.")

    duration, reason = get_duration_with_pydub(file_field)
    if duration is not None:
        logger.info(f"Successfully got duration for '{filename}' with pydub.")
        file_field.seek(0)
        return duration

    logger.error(f"Pydub/ffmpeg also failed for '{filename}' (Reason: {reason}). Cannot determine duration.")
    file_field.seek(0)
    return None