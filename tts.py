"""Text-to-speech helpers using local XTTS-v2 voice cloning."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import sounddevice as sd
import soundfile as sf
import numpy as np

from config import CONFIG


def _allow_xtts_checkpoint_globals() -> None:
    """Allowlist trusted XTTS classes for PyTorch 2.6 checkpoint loading.

    Args:
        None.

    Returns:
        None.
    """

    try:
        import torch
        from TTS.config.shared_configs import BaseDatasetConfig
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import XttsArgs, XttsAudioConfig

        torch.serialization.add_safe_globals(
            [XttsConfig, XttsAudioConfig, XttsArgs, BaseDatasetConfig]
        )
    except Exception as exc:
        print(f"TTS warning: could not configure PyTorch checkpoint allowlist: {exc}")


class PersonaTTS:
    """XTTS-v2 speaker-cloned text-to-speech wrapper."""

    def __init__(self, output_device: int | None = None, playback_backend: str | None = None) -> None:
        """Load the local TTS model and verify the voice sample.

        Args:
            output_device: Optional sounddevice output device index for playback.
            playback_backend: Playback backend: auto, sounddevice, or afplay.

        Returns:
            None.

        Raises:
            FileNotFoundError: If CONFIG.VOICE_SAMPLE_PATH does not exist.
        """

        _allow_xtts_checkpoint_globals()
        from TTS.api import TTS

        print("Loading TTS model... (first run downloads ~2GB)")
        if not CONFIG.VOICE_SAMPLE_PATH.exists():
            raise FileNotFoundError(
                f"Voice sample not found at {CONFIG.VOICE_SAMPLE_PATH}. "
                "Add or preprocess a sample before running main.py."
            )
        CONFIG.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.output_device = output_device if output_device is not None else CONFIG.AUDIO_OUTPUT_DEVICE
        self.playback_backend = playback_backend or CONFIG.PLAYBACK_BACKEND
        self.tts = TTS(CONFIG.TTS_MODEL)
        print("✓ TTS ready")

    @staticmethod
    def clean_text(text: str) -> str:
        """Prepare LLM text for speech synthesis.

        Args:
            text: Raw LLM response text.

        Returns:
            Cleaned text with markdown, emojis, newlines, and extra spacing removed.
        """

        cleaned = PersonaTTS.normalize_chat_speech(text)
        cleaned = re.sub(r"[*_#`]", "", cleaned)
        cleaned = cleaned.replace("\n", " ")
        cleaned = re.sub(
            "["
            "\U0001F300-\U0001FAFF"
            "\U00002700-\U000027BF"
            "\U00002600-\U000026FF"
            "]+",
            "",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    @staticmethod
    def normalize_chat_speech(text: str) -> str:
        """Convert chat abbreviations into more natural spoken words.

        Args:
            text: Raw LLM response text in chat style.

        Returns:
            Text with common chat abbreviations expanded for TTS only.
        """

        replacements = {
            "abt": "about",
            "bc": "because",
            "bcz": "because",
            "brb": "be right back",
            "btw": "by the way",
            "cuz": "because",
            "fr": "for real",
            "gng": "going",
            "gonna": "going to",
            "gotta": "got to",
            "gtg": "got to go",
            "hv": "have",
            "idk": "I don't know",
            "ig": "I guess",
            "ik": "I know",
            "ikr": "I know right",
            "lemme": "let me",
            "lmao": "",
            "lol": "",
            "rn": "right now",
            "stfu": "shut up",
            "tho": "though",
            "tmr": "tomorrow",
            "u": "you",
            "ur": "your",
            "wanna": "want to",
            "wyd": "what are you doing",
            "ye": "yeah",
        }

        normalized = text
        for source, target in replacements.items():
            normalized = re.sub(rf"\b{re.escape(source)}\b", target, normalized, flags=re.IGNORECASE)

        normalized = re.sub(r"\b([a-zA-Z])\s+\1\s+\1+\b", "", normalized)
        normalized = re.sub(r"\s+([?.!,])", r"\1", normalized)
        return normalized

    def speak(self, text: str) -> bool:
        """Synthesize text to a WAV file and play it through the speakers.

        Args:
            text: Persona reply text to synthesize.

        Returns:
            True when synthesis and playback completed, otherwise False.
        """

        cleaned = self.clean_text(text)
        if not cleaned:
            return True

        CONFIG.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.tts.tts_to_file(
                text=cleaned,
                speaker_wav=str(CONFIG.VOICE_SAMPLE_PATH),
                language=CONFIG.TTS_LANGUAGE,
                file_path=str(CONFIG.TTS_OUTPUT_PATH),
            )
            self._play_audio(CONFIG.TTS_OUTPUT_PATH)
            return True
        except Exception as exc:
            print(f"TTS error: {exc}")
            print(f"Generated audio is still saved at: {CONFIG.TTS_OUTPUT_PATH}")
            print("Run `python main.py --list-devices` to inspect audio output devices.")
            return False

    def _play_audio(self, wav_path: Path) -> None:
        """Play a synthesized WAV file using the configured playback backend.

        Args:
            wav_path: Path to the synthesized WAV file.

        Returns:
            None.

        Raises:
            RuntimeError: If the selected playback backend is unavailable.
        """

        backend = self.playback_backend
        if backend == "auto":
            backend = "afplay" if sys.platform == "darwin" and shutil.which("afplay") else "sounddevice"

        if backend == "afplay":
            if not shutil.which("afplay"):
                raise RuntimeError("afplay was not found. Use --playback sounddevice instead.")
            subprocess.run(["afplay", str(wav_path)], check=True)
            return

        if backend != "sounddevice":
            raise RuntimeError(f"Unknown playback backend: {backend}")

        audio, sample_rate = sf.read(wav_path, dtype="float32")
        sd.play(audio, sample_rate, device=self.output_device)
        sd.wait()


def play_test_beep(
    output_device: int | None = None,
    playback_backend: str = "sounddevice",
    frequency_hz: float = 880.0,
    duration_seconds: float = 0.35,
) -> None:
    """Play a short beep to identify the current output route.

    Args:
        output_device: Optional sounddevice output device index.
        playback_backend: Playback backend: sounddevice, afplay, or auto.
        frequency_hz: Sine wave frequency for the beep.
        duration_seconds: Beep duration in seconds.

    Returns:
        None.
    """

    sample_rate = 24000
    timeline = np.linspace(0.0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    envelope = np.minimum(np.linspace(0.0, 1.0, timeline.size), 1.0)
    envelope *= np.minimum(np.linspace(1.0, 0.0, timeline.size), 1.0)
    beep = (0.2 * np.sin(2.0 * np.pi * frequency_hz * timeline) * envelope).astype(np.float32)

    CONFIG.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    beep_path = CONFIG.TEMP_DIR / "test_beep.wav"
    sf.write(beep_path, beep, sample_rate)

    player = PersonaTTS.__new__(PersonaTTS)
    player.output_device = output_device
    player.playback_backend = playback_backend
    player._play_audio(beep_path)


def preprocess_voice_sample(raw_audio_paths: Path | Iterable[Path], output_path: Path) -> bool:
    """Convert and normalize one or more raw voice samples for XTTS-v2.

    Args:
        raw_audio_paths: One path, or multiple ffmpeg-readable source audio files.
        output_path: Destination path for a 22050 Hz mono WAV file.

    Returns:
        True on success, False when ffmpeg fails.
    """

    if isinstance(raw_audio_paths, Path):
        sources = [raw_audio_paths]
    else:
        sources = list(raw_audio_paths)
    if not sources:
        print("No voice sample files were provided.")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if len(sources) == 1:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(sources[0]),
            "-ar",
            "22050",
            "-ac",
            "1",
            "-af",
            "silenceremove=1:0:-50dB,loudnorm",
            str(output_path),
        ]
    else:
        concat_path = CONFIG.TEMP_DIR / "voice_sources.txt"
        CONFIG.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        concat_path.write_text(
            "".join(f"file '{source}'\n" for source in sources),
            encoding="utf-8",
        )
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-ar",
            "22050",
            "-ac",
            "1",
            "-af",
            "silenceremove=1:0:-50dB,loudnorm",
            str(output_path),
        ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("ffmpeg was not found. Install it with `brew install ffmpeg` and try again.")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"ffmpeg failed while preprocessing the voice sample:\n{exc.stderr}")
        return False

    print(f"✓ Voice sample ready: {output_path}")
    return True
