"""Audio utility helpers for setup and diagnostics."""

from __future__ import annotations

import numpy as np
import sounddevice as sd

from config import CONFIG


def list_audio_devices() -> None:
    """Print available input and output audio devices.

    Args:
        None.

    Returns:
        None.
    """

    devices = sd.query_devices()
    default_input, default_output = sd.default.device
    print("Audio devices:")
    for index, device in enumerate(devices):
        markers: list[str] = []
        if index == default_input:
            markers.append("default input")
        if index == default_output:
            markers.append("default output")
        if device.get("max_output_channels", 0) > 0:
            markers.append(f"out:{device['max_output_channels']}")
        if device.get("max_input_channels", 0) > 0:
            markers.append(f"in:{device['max_input_channels']}")
        suffix = f" ({', '.join(markers)})" if markers else ""
        print(f"{index}: {device['name']}{suffix}")


def test_tts(tts_instance: object) -> None:
    """Speak a short phrase to verify TTS and playback.

    Args:
        tts_instance: A PersonaTTS-like object with a speak(text) method.

    Returns:
        None.
    """

    tts_instance.speak("Hello, this is a voice test.")


def test_microphone(seconds: int = 3) -> None:
    """Record microphone audio for a few seconds and play it back.

    Args:
        seconds: Number of seconds to record before playback.

    Returns:
        None.
    """

    print(f"Recording microphone for {seconds} seconds...")
    audio = sd.rec(int(seconds * CONFIG.SAMPLE_RATE), samplerate=CONFIG.SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    print("Playing recording...")
    sd.play(np.asarray(audio).reshape(-1), CONFIG.SAMPLE_RATE)
    sd.wait()
