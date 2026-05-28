from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from config import CONFIG
from services import AudioInputService, ChatSession, SetupRequest, SetupService, SpeechOutputService


class FakeLLM:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.reset_called = False

    def chat(self, message: str) -> str:
        self.messages.append(message)
        return f"reply to {message}"

    def reset_history(self) -> None:
        self.reset_called = True


class FakeTTS:
    def __init__(self, output_device: int | None = None, playback_backend: str | None = None) -> None:
        self.output_device = output_device
        self.playback_backend = playback_backend
        self.spoken: list[str] = []

    def speak(self, text: str) -> bool:
        self.spoken.append(text)
        return True


class FakeSetupService(SetupService):
    def __init__(self, base_dir: Path, running: bool = False, models: set[str] | None = None) -> None:
        super().__init__(base_dir=base_dir, resource_dir=base_dir)
        self.running = running
        self.models = models or set()

    def find_ollama_bin(self) -> Path | None:
        path = self.local_ollama_bin
        return path if path.exists() else None

    def find_python_bin(self) -> Path | None:
        path = self.local_python_bin
        return path if path.exists() else None

    def is_ollama_running(self) -> bool:
        return self.running

    def is_model_available(self, model_name: str) -> bool:
        return model_name in self.models


class ChatSessionTests(unittest.TestCase):
    def test_send_message_delegates_to_llm(self) -> None:
        fake = FakeLLM()
        session = ChatSession(llm_factory=lambda: fake)

        self.assertEqual(session.send_message(" hello "), "reply to hello")
        self.assertEqual(fake.messages, ["hello"])

    def test_empty_message_is_rejected(self) -> None:
        session = ChatSession(llm_factory=FakeLLM)

        with self.assertRaises(ValueError):
            session.send_message("   ")

    def test_reset_delegates_to_llm(self) -> None:
        fake = FakeLLM()
        session = ChatSession(llm_factory=lambda: fake)

        session.reset()

        self.assertTrue(fake.reset_called)


class AudioInputServiceTests(unittest.TestCase):
    def test_capture_once_emits_states_and_transcribes(self) -> None:
        states: list[str] = []
        service = AudioInputService(
            record_fn=lambda: np.array([0.1, 0.2], dtype=np.float32),
            transcribe_fn=lambda audio: "hello",
        )

        self.assertEqual(service.capture_once(status_callback=states.append), "hello")
        self.assertEqual(states, ["listening", "transcribing", "idle"])

    def test_empty_audio_returns_empty_transcript(self) -> None:
        states: list[str] = []
        service = AudioInputService(record_fn=lambda: np.array([], dtype=np.float32))

        self.assertEqual(service.capture_once(status_callback=states.append), "")
        self.assertEqual(states, ["listening", "idle"])


class SpeechOutputServiceTests(unittest.TestCase):
    def test_speech_output_loads_tts_lazily(self) -> None:
        states: list[str] = []
        created: list[FakeTTS] = []

        def factory(**kwargs: object) -> FakeTTS:
            tts = FakeTTS(**kwargs)
            created.append(tts)
            return tts

        service = SpeechOutputService(output_device=3, playback_backend="afplay", tts_factory=factory)
        self.assertEqual(created, [])

        service.speak("hi", status_callback=states.append)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].spoken, ["hi"])
        self.assertEqual(created[0].output_device, 3)
        self.assertEqual(created[0].playback_backend, "afplay")
        self.assertIn("Loading voice model...", states)
        self.assertIn("Speaking...", states)

    def test_reconfigure_resets_cached_tts(self) -> None:
        created: list[FakeTTS] = []

        def factory(**kwargs: object) -> FakeTTS:
            tts = FakeTTS(**kwargs)
            created.append(tts)
            return tts

        service = SpeechOutputService(tts_factory=factory)
        service.speak("one")
        service.configure(5, "sounddevice")
        service.speak("two")

        self.assertEqual(len(created), 2)
        self.assertEqual(created[1].output_device, 5)
        self.assertEqual(created[1].playback_backend, "sounddevice")


class SetupServiceTests(unittest.TestCase):
    def test_check_status_reports_ready_when_all_artifacts_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            service = FakeSetupService(
                base,
                running=True,
                models={CONFIG.OLLAMA_BASE_MODEL, CONFIG.OLLAMA_MODEL_NAME},
            )
            service.local_ollama_bin.parent.mkdir(parents=True)
            service.local_ollama_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            service.local_ollama_bin.chmod(0o755)
            service.local_python_bin.parent.mkdir(parents=True)
            service.local_python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            service.local_python_bin.chmod(0o755)
            service.venv_python.parent.mkdir(parents=True)
            service.venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
            service.persona_text_path.write_text("hello\n", encoding="utf-8")
            service.voice_sample_path.parent.mkdir(parents=True)
            service.voice_sample_path.write_bytes(b"wav")

            status = service.check_status()

            self.assertTrue(status.ready)
            self.assertTrue(all(step.state == "ready" for step in status.steps))

    def test_check_status_reports_missing_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            status = FakeSetupService(Path(temp)).check_status()

            self.assertFalse(status.ready)
            self.assertIn("Ollama", status.summary)
            self.assertTrue(any(step.state == "action_needed" for step in status.steps))

    def test_ensure_persona_text_writes_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            service = FakeSetupService(Path(temp))

            service.ensure_persona_text(SetupRequest(persona_text="hi there"))

            self.assertEqual(service.persona_text_path.read_text(encoding="utf-8"), "hi there\n")


if __name__ == "__main__":
    unittest.main()
