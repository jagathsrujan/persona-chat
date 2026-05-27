"""Speech-to-text helpers powered by mlx-whisper."""

from __future__ import annotations

import string

import numpy as np
import soundfile as sf

from config import CONFIG


def _is_empty_transcript(text: str) -> bool:
    """Return whether a transcript is empty or contains punctuation only.

    Args:
        text: Transcript text returned by the speech recognizer.

    Returns:
        True when the text has no alphanumeric content, otherwise False.
    """

    stripped = text.strip()
    if not stripped:
        return True
    return all(char in string.punctuation or char.isspace() for char in stripped)


def transcribe(audio: np.ndarray) -> str:
    """Transcribe recorded microphone audio with mlx-whisper.

    Args:
        audio: Mono float32 audio samples recorded at CONFIG.SAMPLE_RATE.

    Returns:
        A stripped transcript, or an empty string if no useful speech was found.
    """

    import mlx_whisper

    CONFIG.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    input_path = CONFIG.TEMP_DIR / "input.wav"
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    sf.write(input_path, audio, CONFIG.SAMPLE_RATE, subtype="FLOAT")

    result = mlx_whisper.transcribe(
        str(input_path),
        path_or_hf_repo=CONFIG.WHISPER_MODEL,
        language=CONFIG.WHISPER_LANGUAGE,
    )
    text = str(result.get("text", "")).strip()
    if _is_empty_transcript(text):
        return ""
    return text
