"""Central configuration for the local persona chat system."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if getattr(sys, "frozen", False):
    APP_DATA_DIR = Path.home() / "Library" / "Application Support" / "Persona Chat"
else:
    APP_DATA_DIR = RESOURCE_DIR

BASE_DIR = APP_DATA_DIR
CACHE_DIR = BASE_DIR / "temp" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(CACHE_DIR / "huggingface"))
os.environ.setdefault("MPLCONFIGDIR", str(CACHE_DIR / "matplotlib"))


@dataclass(frozen=True)
class Config:
    """Container for all user-configurable application settings.

    Attributes:
        BASE_DIR: Absolute path to the project directory.
        RESOURCE_DIR: Read-only bundled source/resource directory.
        OLLAMA_MODEL_NAME: Name of the custom Ollama persona model.
        OLLAMA_BASE_MODEL: Base Ollama model used to build the persona model.
        OLLAMA_HOST: Local Ollama HTTP endpoint.
        WHISPER_MODEL: mlx-whisper model identifier.
        WHISPER_LANGUAGE: Language hint passed to Whisper.
        TTS_MODEL: Coqui TTS model identifier for XTTS-v2.
        TTS_LANGUAGE: Language code used by XTTS-v2.
        VOICE_SAMPLE_PATH: Path to the normalized speaker WAV file.
        TTS_OUTPUT_PATH: Path where generated speech is written.
        DEFAULT_INPUT_MODE: Default interaction input mode, either voice or text.
        DEFAULT_OUTPUT_MODE: Default reply output mode, either voice or text.
        PLAYBACK_BACKEND: Audio playback backend, auto, sounddevice, or afplay.
        AUDIO_OUTPUT_DEVICE: Optional sounddevice output device index.
        SAMPLE_RATE: Microphone recording sample rate for STT.
        VAD_SILENCE_THRESHOLD: RMS level above which speech is detected.
        VAD_SILENCE_DURATION: Seconds of silence before a recording stops.
        VAD_MAX_DURATION: Hard cap on one recorded utterance in seconds.
        VAD_PRE_BUFFER: Seconds of audio retained before speech begins.
        CONVERSATION_HISTORY_LIMIT: Maximum recent chat messages retained.
        TEMP_DIR: Directory for temporary audio files.
        PERSONA_TEXT_PATH: Path to extracted persona text.
        MODELFILE_PATH: Path to the generated Ollama Modelfile.
    """

    BASE_DIR: Path = field(default_factory=lambda: BASE_DIR)
    RESOURCE_DIR: Path = field(default_factory=lambda: RESOURCE_DIR)

    OLLAMA_MODEL_NAME: str = "mypersona"
    OLLAMA_BASE_MODEL: str = "llama3.1:8b"
    OLLAMA_HOST: str = "http://localhost:11434"

    WHISPER_MODEL: str = "mlx-community/whisper-base"
    WHISPER_LANGUAGE: str = "en"

    TTS_MODEL: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    TTS_LANGUAGE: str = "en"
    DEFAULT_INPUT_MODE: str = "voice"
    DEFAULT_OUTPUT_MODE: str = "voice"
    PLAYBACK_BACKEND: str = "auto"
    AUDIO_OUTPUT_DEVICE: int | None = None

    SAMPLE_RATE: int = 16000
    VAD_SILENCE_THRESHOLD: float = 0.01
    VAD_SILENCE_DURATION: float = 1.5
    VAD_MAX_DURATION: int = 30
    VAD_PRE_BUFFER: float = 0.3

    CONVERSATION_HISTORY_LIMIT: int = 20

    @property
    def TEMP_DIR(self) -> Path:
        """Return the directory used for temporary runtime files.

        Args:
            None.

        Returns:
            Path to the temporary files directory.
        """

        return self.BASE_DIR / "temp"

    @property
    def VOICE_SAMPLE_PATH(self) -> Path:
        """Return the normalized XTTS speaker WAV path.

        Args:
            None.

        Returns:
            Path to the XTTS-compatible speaker WAV file.
        """

        return self.BASE_DIR / "voice_samples" / "speaker.wav"

    @property
    def TTS_OUTPUT_PATH(self) -> Path:
        """Return the path where synthesized speech should be written.

        Args:
            None.

        Returns:
            Path to the generated response WAV file.
        """

        return self.TEMP_DIR / "response.wav"

    @property
    def PERSONA_TEXT_PATH(self) -> Path:
        """Return the path to the raw persona text file.

        Args:
            None.

        Returns:
            Path to persona.txt.
        """

        return self.BASE_DIR / "persona.txt"

    @property
    def MODELFILE_PATH(self) -> Path:
        """Return the path to the Ollama Modelfile.

        Args:
            None.

        Returns:
            Path to the generated Ollama Modelfile.
        """

        return self.BASE_DIR / "Modelfile"


CONFIG = Config()
