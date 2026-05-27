"""Pure numpy RMS voice activity detection for microphone recording."""

from __future__ import annotations

from collections import deque

import numpy as np
import sounddevice as sd

from config import CONFIG


def _rms(chunk: np.ndarray) -> float:
    """Compute root-mean-square loudness for an audio chunk.

    Args:
        chunk: Audio samples from the microphone input stream.

    Returns:
        The RMS value as a float.
    """

    samples = np.asarray(chunk, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples))))


def record_until_silence() -> np.ndarray:
    """Record microphone audio until speech is followed by sustained silence.

    Args:
        None.

    Returns:
        A mono float32 numpy array containing the captured utterance.
    """

    chunk_size = 1024
    pre_buffer_chunks = max(1, int(CONFIG.VAD_PRE_BUFFER * CONFIG.SAMPLE_RATE / chunk_size))
    silence_chunks_needed = max(1, int(CONFIG.VAD_SILENCE_DURATION * CONFIG.SAMPLE_RATE / chunk_size))
    max_chunks = max(1, int(CONFIG.VAD_MAX_DURATION * CONFIG.SAMPLE_RATE / chunk_size))

    pre_buffer: deque[np.ndarray] = deque(maxlen=pre_buffer_chunks)
    recorded: list[np.ndarray] = []
    recording = False
    silence_chunks = 0
    total_recorded_chunks = 0

    print("🎙 Listening...")
    with sd.InputStream(samplerate=CONFIG.SAMPLE_RATE, channels=1, dtype="float32", blocksize=chunk_size) as stream:
        while True:
            chunk, overflowed = stream.read(chunk_size)
            if overflowed:
                print("Audio warning: input buffer overflowed.")

            mono_chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
            loudness = _rms(mono_chunk)

            if not recording:
                pre_buffer.append(mono_chunk.copy())
                if loudness > CONFIG.VAD_SILENCE_THRESHOLD:
                    print("● Recording...")
                    recording = True
                    recorded.extend(pre_buffer)
                    total_recorded_chunks = len(recorded)
                continue

            recorded.append(mono_chunk.copy())
            total_recorded_chunks += 1

            if loudness < CONFIG.VAD_SILENCE_THRESHOLD:
                silence_chunks += 1
            else:
                silence_chunks = 0

            if silence_chunks >= silence_chunks_needed or total_recorded_chunks >= max_chunks:
                print("✓ Done.")
                break

    if not recorded:
        return np.array([], dtype=np.float32)
    return np.concatenate(recorded).astype(np.float32)
