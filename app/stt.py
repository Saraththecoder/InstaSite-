import os
from faster_whisper import WhisperModel
from app.config import WHISPER_MODEL_SIZE

_model = None


def get_whisper_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe_audio(audio_path: str) -> str:
    """
    Takes an audio file path and returns raw transcript string using faster-whisper.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    model = get_whisper_model()
    segments, info = model.transcribe(audio_path, beam_size=5)
    transcript = " ".join(segment.text.strip() for segment in segments).strip()
    return transcript
