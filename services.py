"""Reusable services for the CLI and desktop GUI."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import requests

from config import CONFIG, RESOURCE_DIR


StatusCallback = Callable[[str], None]


def _emit(callback: StatusCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _path_has_content(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


@dataclass(frozen=True)
class AudioDeviceInfo:
    """Summary of one sounddevice input/output device."""

    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    is_default_input: bool = False
    is_default_output: bool = False

    @property
    def label(self) -> str:
        markers: list[str] = []
        if self.is_default_input:
            markers.append("default input")
        if self.is_default_output:
            markers.append("default output")
        if self.max_input_channels > 0:
            markers.append(f"in:{self.max_input_channels}")
        if self.max_output_channels > 0:
            markers.append(f"out:{self.max_output_channels}")
        suffix = f" ({', '.join(markers)})" if markers else ""
        return f"{self.index}: {self.name}{suffix}"


@dataclass(frozen=True)
class SetupStep:
    """One setup checklist row."""

    key: str
    label: str
    state: str
    message: str


@dataclass(frozen=True)
class SetupStatus:
    """Current first-run setup state."""

    steps: list[SetupStep]
    ready: bool

    @property
    def summary(self) -> str:
        if self.ready:
            return "Ready to chat"
        missing = [step.label for step in self.steps if step.state != "ready"]
        return "Needs setup: " + ", ".join(missing)


@dataclass(frozen=True)
class SetupRequest:
    """Inputs collected by the first-run setup GUI."""

    persona_name: str = "Persona"
    persona_text: str = ""
    chat_export_path: Path | None = None
    speaker_name: str = ""
    voice_sample_paths: list[Path] = field(default_factory=list)
    force_rebuild_model: bool = False


@dataclass
class AppState:
    """Runtime preferences shared by the GUI widgets."""

    input_mode: str = CONFIG.DEFAULT_INPUT_MODE
    output_mode: str = CONFIG.DEFAULT_OUTPUT_MODE
    playback_backend: str = CONFIG.PLAYBACK_BACKEND
    output_device: int | None = CONFIG.AUDIO_OUTPUT_DEVICE
    status: str = "Idle"


class ChatSession:
    """Conversation wrapper around the local persona model."""

    def __init__(self, llm_factory: Callable[[], object] | None = None) -> None:
        if llm_factory is None:
            from llm import PersonaLLM

            llm_factory = PersonaLLM
        self._llm = llm_factory()

    def send_message(self, text: str) -> str:
        message = text.strip()
        if not message:
            raise ValueError("Message is empty.")

        reply = self._llm.chat(message)  # type: ignore[attr-defined]
        if not reply:
            raise RuntimeError("The persona did not return a reply. Check Ollama and try again.")
        return str(reply)

    def reset(self) -> None:
        self._llm.reset_history()  # type: ignore[attr-defined]


class AudioInputService:
    """Voice recording and transcription service."""

    def __init__(
        self,
        record_fn: Callable[[], np.ndarray] | None = None,
        transcribe_fn: Callable[[np.ndarray], str] | None = None,
    ) -> None:
        self._record_fn = record_fn
        self._transcribe_fn = transcribe_fn

    def capture_once(self, status_callback: StatusCallback | None = None) -> str:
        _emit(status_callback, "listening")
        record_fn = self._record_fn
        if record_fn is None:
            import vad

            record_fn = vad.record_until_silence

        audio = record_fn()
        if audio.size == 0:
            _emit(status_callback, "idle")
            return ""

        _emit(status_callback, "transcribing")
        transcribe_fn = self._transcribe_fn
        if transcribe_fn is None:
            import stt

            transcribe_fn = stt.transcribe

        transcript = transcribe_fn(audio).strip()
        _emit(status_callback, "idle")
        return transcript


class SpeechOutputService:
    """Lazy TTS and audio diagnostics service."""

    def __init__(
        self,
        output_device: int | None = None,
        playback_backend: str | None = None,
        tts_factory: Callable[..., object] | None = None,
    ) -> None:
        self.output_device = output_device
        self.playback_backend = playback_backend or CONFIG.PLAYBACK_BACKEND
        self._tts_factory = tts_factory
        self._tts: object | None = None

    def configure(self, output_device: int | None, playback_backend: str | None) -> None:
        backend = playback_backend or CONFIG.PLAYBACK_BACKEND
        if output_device != self.output_device or backend != self.playback_backend:
            self.output_device = output_device
            self.playback_backend = backend
            self._tts = None

    def _ensure_tts(self, status_callback: StatusCallback | None = None) -> object:
        if self._tts is not None:
            return self._tts

        _emit(status_callback, "Loading voice model...")
        factory = self._tts_factory
        if factory is None:
            from tts import PersonaTTS

            factory = PersonaTTS
        self._tts = factory(output_device=self.output_device, playback_backend=self.playback_backend)
        _emit(status_callback, "Voice ready")
        return self._tts

    def speak(self, text: str, status_callback: StatusCallback | None = None) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        tts = self._ensure_tts(status_callback=status_callback)
        _emit(status_callback, "Speaking...")
        ok = tts.speak(cleaned)  # type: ignore[attr-defined]
        if ok is False:
            raise RuntimeError("Text-to-speech failed. Check the voice sample and audio output.")
        _emit(status_callback, "Idle")

    def test_beep(self) -> None:
        from tts import play_test_beep

        play_test_beep(output_device=self.output_device, playback_backend=self.playback_backend)

    @staticmethod
    def list_devices() -> list[AudioDeviceInfo]:
        import sounddevice as sd

        devices = sd.query_devices()
        default_input, default_output = sd.default.device
        results: list[AudioDeviceInfo] = []
        for index, device in enumerate(devices):
            results.append(
                AudioDeviceInfo(
                    index=index,
                    name=str(device.get("name", "Unknown device")),
                    max_input_channels=int(device.get("max_input_channels", 0)),
                    max_output_channels=int(device.get("max_output_channels", 0)),
                    is_default_input=index == default_input,
                    is_default_output=index == default_output,
                )
            )
        return results


class SetupService:
    """First-run setup checks and actions for the desktop app."""

    PYTHON_DOWNLOAD_URL = (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        "20241008/cpython-3.11.10%2B20241008-aarch64-apple-darwin-install_only.tar.gz"
    )
    OLLAMA_DOWNLOAD_URL = "https://github.com/ollama/ollama/releases/latest/download/Ollama-darwin.zip"

    def __init__(self, base_dir: Path | None = None, resource_dir: Path | None = None) -> None:
        self.base_dir = base_dir or CONFIG.BASE_DIR
        self.resource_dir = resource_dir or RESOURCE_DIR
        self.tools_dir = self.base_dir / "tools"
        self.temp_dir = self.base_dir / "temp"
        self.venv_dir = self.base_dir / ".venv"
        self._ollama_process: subprocess.Popen[str] | None = None

    @property
    def local_ollama_bin(self) -> Path:
        return self.tools_dir / "Ollama.app" / "Contents" / "Resources" / "ollama"

    @property
    def local_python_bin(self) -> Path:
        return self.tools_dir / "python" / "bin" / "python3.11"

    @property
    def venv_python(self) -> Path:
        return self.venv_dir / "bin" / "python"

    @property
    def persona_text_path(self) -> Path:
        return self.base_dir / "persona.txt"

    @property
    def voice_sample_path(self) -> Path:
        return self.base_dir / "voice_samples" / "speaker.wav"

    @property
    def modelfile_path(self) -> Path:
        return self.base_dir / "Modelfile"

    def find_ollama_bin(self) -> Path | None:
        candidates = [
            self.local_ollama_bin,
            Path("/Applications/Ollama.app/Contents/Resources/ollama"),
            Path.home() / "Applications/Ollama.app/Contents/Resources/ollama",
        ]
        for candidate in candidates:
            if _path_exists(candidate) and os.access(candidate, os.X_OK):
                return candidate
        path = shutil.which("ollama")
        return Path(path) if path else None

    def find_python_bin(self) -> Path | None:
        if _path_exists(self.local_python_bin) and os.access(self.local_python_bin, os.X_OK):
            return self.local_python_bin
        path = shutil.which("python3.11")
        return Path(path) if path else None

    def is_ollama_running(self) -> bool:
        try:
            response = requests.get(f"{CONFIG.OLLAMA_HOST}/api/tags", timeout=2)
            response.raise_for_status()
        except requests.RequestException:
            return False
        return True

    def is_model_available(self, model_name: str) -> bool:
        try:
            response = requests.get(f"{CONFIG.OLLAMA_HOST}/api/tags", timeout=2)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            return False

        models = payload.get("models", [])
        short_names = {str(model.get("name", "")).split(":", 1)[0] for model in models}
        full_names = {str(model.get("name", "")) for model in models}
        return model_name in short_names or model_name in full_names

    def check_status(self) -> SetupStatus:
        ollama_bin = self.find_ollama_bin()
        python_bin = self.find_python_bin()
        ollama_running = self.is_ollama_running()
        base_model_ready = self.is_model_available(CONFIG.OLLAMA_BASE_MODEL) if ollama_running else False
        persona_model_ready = self.is_model_available(CONFIG.OLLAMA_MODEL_NAME) if ollama_running else False
        persona_ready = _path_has_content(self.persona_text_path)
        voice_ready = _path_has_content(self.voice_sample_path)

        steps = [
            self._step("ollama", "Ollama", ollama_bin is not None, "Installed locally or available on PATH"),
            self._step("python", "Python 3.11", python_bin is not None, "Installed locally or available on PATH"),
            self._step("venv", "Python dependencies", _path_exists(self.venv_python), "Project virtual environment exists"),
            self._step("server", "Ollama server", ollama_running, "Server is reachable on localhost"),
            self._step("base_model", "Base model", base_model_ready, f"{CONFIG.OLLAMA_BASE_MODEL} is available"),
            self._step("persona_text", "Persona text", persona_ready, "persona.txt exists"),
            self._step("voice", "Voice sample", voice_ready, "speaker.wav exists"),
            self._step("persona_model", "Persona model", persona_model_ready, f"{CONFIG.OLLAMA_MODEL_NAME} is available"),
        ]
        return SetupStatus(steps=steps, ready=all(step.state == "ready" for step in steps))

    @staticmethod
    def _step(key: str, label: str, ready: bool, ready_message: str) -> SetupStep:
        state = "ready" if ready else "action_needed"
        message = ready_message if ready else "Needs setup"
        return SetupStep(key=key, label=label, state=state, message=message)

    def run_guided_setup(
        self,
        request: SetupRequest,
        status_callback: StatusCallback | None = None,
    ) -> SetupStatus:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.tools_dir.mkdir(parents=True, exist_ok=True)

        if self.find_ollama_bin() is None:
            self.install_local_ollama(status_callback=status_callback)

        if self.find_python_bin() is None:
            self.install_local_python(status_callback=status_callback)

        self.create_or_update_venv(status_callback=status_callback)
        self.start_ollama(status_callback=status_callback)

        if not self.is_model_available(CONFIG.OLLAMA_BASE_MODEL):
            self.pull_base_model(status_callback=status_callback)

        self.ensure_persona_text(request, status_callback=status_callback)
        self.ensure_voice_sample(request, status_callback=status_callback)

        if request.force_rebuild_model or not self.is_model_available(CONFIG.OLLAMA_MODEL_NAME):
            self.build_persona_model(request.persona_name, status_callback=status_callback)

        return self.check_status()

    def install_local_ollama(self, status_callback: StatusCallback | None = None) -> None:
        _emit(status_callback, "Installing local Ollama...")
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        zip_path = self.tools_dir / "Ollama-darwin.zip"
        download_url = os.environ.get("OLLAMA_DOWNLOAD_URL", self.OLLAMA_DOWNLOAD_URL)
        self._run_command(["curl", "--fail", "--show-error", "--location", "-o", str(zip_path), download_url], status_callback)
        if (self.tools_dir / "Ollama.app").exists():
            shutil.rmtree(self.tools_dir / "Ollama.app")
        self._run_command(["unzip", "-q", str(zip_path), "-d", str(self.tools_dir)], status_callback)
        if not _path_exists(self.local_ollama_bin):
            raise RuntimeError(f"Ollama binary was not found at {self.local_ollama_bin}")

    def install_local_python(self, status_callback: StatusCallback | None = None) -> None:
        _emit(status_callback, "Installing local Python 3.11...")
        python_dir = self.tools_dir / "python"
        archive_path = self.tools_dir / "cpython-3.11-aarch64-apple-darwin.tar.gz"
        download_url = os.environ.get("PYTHON_STANDALONE_URL", self.PYTHON_DOWNLOAD_URL)
        if python_dir.exists():
            shutil.rmtree(python_dir)
        python_dir.mkdir(parents=True, exist_ok=True)
        self._run_command(["curl", "--fail", "--show-error", "--location", "-o", str(archive_path), download_url], status_callback)
        self._run_command(["tar", "-xzf", str(archive_path), "-C", str(python_dir), "--strip-components=1"], status_callback)
        if not _path_exists(self.local_python_bin):
            raise RuntimeError(f"Python binary was not found at {self.local_python_bin}")

    def create_or_update_venv(self, status_callback: StatusCallback | None = None) -> None:
        python_bin = self.find_python_bin()
        if python_bin is None:
            raise RuntimeError("Python 3.11 is not installed.")

        requirements_path = self.resource_dir / "requirements.txt"
        if not _path_exists(requirements_path):
            raise RuntimeError("requirements.txt was not found in the app resources.")

        if not _path_exists(self.venv_python):
            _emit(status_callback, "Creating Python virtual environment...")
            self._run_command([str(python_bin), "-m", "venv", str(self.venv_dir)], status_callback)

        _emit(status_callback, "Installing Python dependencies...")
        self._run_command([str(self.venv_python), "-m", "pip", "install", "--upgrade", "pip"], status_callback)
        self._run_command([str(self.venv_python), "-m", "pip", "install", "-r", str(requirements_path)], status_callback)

    def start_ollama(self, status_callback: StatusCallback | None = None) -> None:
        if self.is_ollama_running():
            _emit(status_callback, "Ollama server is already running.")
            return

        ollama_bin = self.find_ollama_bin()
        if ollama_bin is None:
            raise RuntimeError("Ollama is not installed.")

        _emit(status_callback, "Starting Ollama server...")
        log_path = self.temp_dir / "ollama-gui.log"
        log_file = log_path.open("a", encoding="utf-8")
        self._ollama_process = subprocess.Popen(
            [str(ollama_bin), "serve"],
            cwd=self.base_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for _ in range(30):
            if self.is_ollama_running():
                _emit(status_callback, "Ollama server is ready.")
                return
            time.sleep(0.5)
        raise RuntimeError(f"Ollama did not become ready. See {log_path}")

    def pull_base_model(self, status_callback: StatusCallback | None = None) -> None:
        ollama_bin = self.find_ollama_bin()
        if ollama_bin is None:
            raise RuntimeError("Ollama is not installed.")
        _emit(status_callback, f"Pulling {CONFIG.OLLAMA_BASE_MODEL}...")
        self._run_command([str(ollama_bin), "pull", CONFIG.OLLAMA_BASE_MODEL], status_callback)

    def ensure_persona_text(
        self,
        request: SetupRequest,
        status_callback: StatusCallback | None = None,
    ) -> None:
        self.persona_text_path.parent.mkdir(parents=True, exist_ok=True)
        if request.chat_export_path and request.speaker_name.strip():
            _emit(status_callback, "Extracting persona text from WhatsApp export...")
            from scripts.extract_whatsapp_persona import extract_messages

            messages = extract_messages(request.chat_export_path.expanduser(), request.speaker_name.strip())
            if not messages:
                raise RuntimeError(f"No messages found for speaker `{request.speaker_name}`.")
            self.persona_text_path.write_text("\n".join(messages) + "\n", encoding="utf-8")
            return

        persona_text = request.persona_text.strip()
        if persona_text:
            _emit(status_callback, "Writing persona text...")
            self.persona_text_path.write_text(persona_text + "\n", encoding="utf-8")
            return

        if _path_has_content(self.persona_text_path):
            _emit(status_callback, "Using existing persona.txt.")
            return

        raise RuntimeError("Add persona text or choose a WhatsApp export before running setup.")

    def ensure_voice_sample(
        self,
        request: SetupRequest,
        status_callback: StatusCallback | None = None,
    ) -> None:
        if request.voice_sample_paths:
            from tts import preprocess_voice_sample

            _emit(status_callback, "Preparing voice sample...")
            if not preprocess_voice_sample(request.voice_sample_paths, self.voice_sample_path):
                raise RuntimeError("Voice sample preprocessing failed.")
            return

        if _path_has_content(self.voice_sample_path):
            _emit(status_callback, "Using existing speaker.wav.")
            return

        raise RuntimeError("Choose at least one voice sample file before running setup.")

    def build_persona_model(
        self,
        persona_name: str,
        status_callback: StatusCallback | None = None,
    ) -> None:
        _emit(status_callback, "Building persona model...")
        from persona_builder import build_system_prompt

        if not _path_exists(self.persona_text_path):
            raise RuntimeError("persona.txt does not exist.")
        text_data = self.persona_text_path.read_text(encoding="utf-8").strip()
        if not text_data:
            raise RuntimeError("persona.txt is empty.")

        prompt = build_system_prompt(text_data, persona_name=persona_name.strip() or "Persona")
        self._create_modelfile(prompt)
        self._register_with_ollama(status_callback=status_callback)

    def _create_modelfile(self, system_prompt: str) -> None:
        escaped_prompt = system_prompt.replace('"""', '\\"\\"\\"')
        content = f'''FROM {CONFIG.OLLAMA_BASE_MODEL}
PARAMETER temperature 0.85
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
SYSTEM """{escaped_prompt}"""
'''
        self.modelfile_path.write_text(content, encoding="utf-8")

    def _register_with_ollama(self, status_callback: StatusCallback | None = None) -> None:
        ollama_bin = self.find_ollama_bin()
        if ollama_bin is None:
            raise RuntimeError("Ollama is not installed.")
        self._run_command(
            [str(ollama_bin), "create", CONFIG.OLLAMA_MODEL_NAME, "-f", str(self.modelfile_path)],
            status_callback=status_callback,
            cwd=self.base_dir,
        )

    def _run_command(
        self,
        command: list[str],
        status_callback: StatusCallback | None = None,
        cwd: Path | None = None,
    ) -> None:
        _emit(status_callback, "$ " + " ".join(command))
        process = subprocess.Popen(
            command,
            cwd=cwd or self.base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            _emit(status_callback, line.rstrip())
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(f"Command failed with exit code {return_code}: {' '.join(command)}")


def format_audio_devices(devices: Iterable[AudioDeviceInfo]) -> str:
    """Format device labels for terminal output."""

    return "\n".join(device.label for device in devices)


def write_temp_file(prefix: str, suffix: str, text: str) -> Path:
    """Write text to a temp file under the app temp directory."""

    CONFIG.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=CONFIG.TEMP_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    return Path(path)
