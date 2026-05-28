"""PySide6 desktop GUI for Persona Chat."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services import (
    AppState,
    AudioDeviceInfo,
    AudioInputService,
    ChatSession,
    SetupRequest,
    SetupService,
    SetupStatus,
    SpeechOutputService,
)


class WorkerSignals(QObject):
    """Signals emitted by a background worker."""

    status = Signal(str)
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class FunctionWorker(QRunnable):
    """Run one Python callable on the global thread pool."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class PersonaChatWindow(QMainWindow):
    """Main application window with setup and chat tabs."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Persona Chat")
        self.resize(1120, 760)

        self.thread_pool = QThreadPool.globalInstance()
        self.setup_service = SetupService()
        self.app_state = AppState()
        self.chat_session: ChatSession | None = None
        self.audio_input = AudioInputService()
        self.speech_output = SpeechOutputService()
        self.audio_devices: list[AudioDeviceInfo] = []
        self.voice_sample_paths: list[Path] = []
        self.chat_busy = False

        self.tabs = QTabWidget()
        self.setup_tab = self._build_setup_tab()
        self.chat_tab = self._build_chat_tab()
        self.tabs.addTab(self.setup_tab, "Setup")
        self.tabs.addTab(self.chat_tab, "Chat")
        self.setCentralWidget(self.tabs)

        self._apply_styles()
        self.refresh_setup_status()
        self.refresh_audio_devices()

    def _build_setup_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QLabel("First-run setup")
        header.setObjectName("PageTitle")
        layout.addWidget(header)

        self.setup_summary = QLabel("Checking setup...")
        self.setup_summary.setObjectName("Muted")
        layout.addWidget(self.setup_summary)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)

        self.setup_table = QTableWidget(0, 3)
        self.setup_table.setHorizontalHeaderLabels(["Step", "State", "Details"])
        self.setup_table.horizontalHeader().setStretchLastSection(True)
        self.setup_table.verticalHeader().setVisible(False)
        self.setup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setup_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        left_layout.addWidget(self.setup_table)

        setup_actions = QHBoxLayout()
        self.refresh_setup_button = QPushButton("Refresh")
        self.refresh_setup_button.clicked.connect(self.refresh_setup_status)
        self.run_setup_button = QPushButton("Run guided setup")
        self.run_setup_button.setObjectName("PrimaryButton")
        self.run_setup_button.clicked.connect(self.run_guided_setup)
        setup_actions.addWidget(self.refresh_setup_button)
        setup_actions.addStretch()
        setup_actions.addWidget(self.run_setup_button)
        left_layout.addLayout(setup_actions)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)

        input_group = QGroupBox("Persona inputs")
        form = QFormLayout(input_group)
        self.persona_name_edit = QLineEdit()
        self.persona_name_edit.setPlaceholderText("Persona name")
        self.persona_name_edit.setText("Persona")
        form.addRow("Name", self.persona_name_edit)

        self.persona_text_edit = QTextEdit()
        self.persona_text_edit.setPlaceholderText("Paste raw persona messages here, or choose a WhatsApp export below.")
        self.persona_text_edit.setMinimumHeight(130)
        form.addRow("Raw text", self.persona_text_edit)

        chat_export_row = QHBoxLayout()
        self.chat_export_edit = QLineEdit()
        self.chat_export_edit.setPlaceholderText("Optional WhatsApp export .txt")
        browse_chat_button = QPushButton("Choose")
        browse_chat_button.clicked.connect(self.choose_chat_export)
        chat_export_row.addWidget(self.chat_export_edit, 1)
        chat_export_row.addWidget(browse_chat_button)
        form.addRow("WhatsApp", chat_export_row)

        self.speaker_name_edit = QLineEdit()
        self.speaker_name_edit.setPlaceholderText("Exact speaker name in export")
        form.addRow("Speaker", self.speaker_name_edit)

        voice_row = QVBoxLayout()
        self.voice_samples_list = QListWidget()
        self.voice_samples_list.setMinimumHeight(82)
        voice_buttons = QHBoxLayout()
        add_voice_button = QPushButton("Add voice files")
        add_voice_button.clicked.connect(self.choose_voice_samples)
        clear_voice_button = QPushButton("Clear")
        clear_voice_button.clicked.connect(self.clear_voice_samples)
        voice_buttons.addWidget(add_voice_button)
        voice_buttons.addWidget(clear_voice_button)
        voice_buttons.addStretch()
        voice_row.addWidget(self.voice_samples_list)
        voice_row.addLayout(voice_buttons)
        form.addRow("Voice", voice_row)

        self.rebuild_model_check = QCheckBox("Rebuild persona model")
        form.addRow("", self.rebuild_model_check)
        right_layout.addWidget(input_group)

        log_group = QGroupBox("Setup log")
        log_layout = QVBoxLayout(log_group)
        self.setup_log = QTextEdit()
        self.setup_log.setReadOnly(True)
        self.setup_log.setMinimumHeight(170)
        log_layout.addWidget(self.setup_log)
        right_layout.addWidget(log_group, 1)
        splitter.addWidget(right)
        splitter.setSizes([520, 580])

        return root

    def _build_chat_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        title = QLabel("Persona Chat")
        title.setObjectName("PageTitle")
        self.runtime_status = QLabel("Idle")
        self.runtime_status.setObjectName("StatusPill")
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(self.runtime_status)
        layout.addLayout(top_row)

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        self.input_mode_combo = QComboBox()
        self.input_mode_combo.addItems(["text", "voice"])
        self.input_mode_combo.setCurrentText(self.app_state.input_mode)
        self.output_mode_combo = QComboBox()
        self.output_mode_combo.addItems(["text", "voice"])
        self.output_mode_combo.setCurrentText(self.app_state.output_mode)
        self.playback_combo = QComboBox()
        self.playback_combo.addItems(["auto", "afplay", "sounddevice"])
        self.playback_combo.setCurrentText(self.app_state.playback_backend)
        self.output_device_combo = QComboBox()
        self.output_device_combo.setMinimumWidth(280)
        self.refresh_devices_button = QPushButton("Refresh devices")
        self.refresh_devices_button.clicked.connect(self.refresh_audio_devices)
        self.test_beep_button = QPushButton("Test beep")
        self.test_beep_button.clicked.connect(self.test_beep)

        controls.addWidget(QLabel("Input"), 0, 0)
        controls.addWidget(self.input_mode_combo, 0, 1)
        controls.addWidget(QLabel("Output"), 0, 2)
        controls.addWidget(self.output_mode_combo, 0, 3)
        controls.addWidget(QLabel("Playback"), 0, 4)
        controls.addWidget(self.playback_combo, 0, 5)
        controls.addWidget(QLabel("Device"), 1, 0)
        controls.addWidget(self.output_device_combo, 1, 1, 1, 3)
        controls.addWidget(self.refresh_devices_button, 1, 4)
        controls.addWidget(self.test_beep_button, 1, 5)
        layout.addLayout(controls)

        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setObjectName("Transcript")
        self.transcript.setPlaceholderText("Messages will appear here.")
        layout.addWidget(self.transcript, 1)

        input_row = QHBoxLayout()
        self.message_edit = QLineEdit()
        self.message_edit.setPlaceholderText("Type a message")
        self.message_edit.returnPressed.connect(self.send_text_message)
        self.record_button = QPushButton("Record")
        self.record_button.clicked.connect(self.record_voice_message)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("PrimaryButton")
        self.send_button.clicked.connect(self.send_text_message)
        self.reset_button = QPushButton("Reset")
        self.reset_button.clicked.connect(self.reset_chat)
        input_row.addWidget(self.message_edit, 1)
        input_row.addWidget(self.record_button)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.reset_button)
        layout.addLayout(input_row)

        self.input_mode_combo.currentTextChanged.connect(self.update_runtime_preferences)
        self.output_mode_combo.currentTextChanged.connect(self.update_runtime_preferences)
        self.playback_combo.currentTextChanged.connect(self.update_runtime_preferences)
        self.output_device_combo.currentIndexChanged.connect(self.update_runtime_preferences)

        return root

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-size: 14px;
            }
            #PageTitle {
                font-size: 24px;
                font-weight: 700;
            }
            #Muted {
                color: #5f6673;
            }
            #PrimaryButton {
                background: #176b87;
                color: white;
                border: 0;
                padding: 7px 14px;
                border-radius: 5px;
            }
            #PrimaryButton:disabled {
                background: #aeb8c2;
            }
            #StatusPill {
                background: #eef3f6;
                border: 1px solid #cfd9df;
                border-radius: 5px;
                padding: 5px 10px;
            }
            #Transcript {
                background: #fbfcfd;
                border: 1px solid #d6dde3;
                border-radius: 6px;
                padding: 8px;
            }
            QGroupBox {
                font-weight: 600;
                margin-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            """
        )

    def refresh_setup_status(self) -> None:
        status = self.setup_service.check_status()
        self.render_setup_status(status)
        if status.ready:
            self.enable_chat()
        else:
            self.chat_tab.setEnabled(False)

    def render_setup_status(self, status: SetupStatus) -> None:
        self.setup_summary.setText(status.summary)
        self.setup_table.setRowCount(len(status.steps))
        for row, step in enumerate(status.steps):
            state_text = "Ready" if step.state == "ready" else "Needs setup"
            for column, value in enumerate([step.label, state_text, step.message]):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.setup_table.setItem(row, column, item)
        self.setup_table.resizeColumnsToContents()

    def choose_chat_export(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose WhatsApp export", str(Path.home()), "Text files (*.txt);;All files (*)")
        if path:
            self.chat_export_edit.setText(path)

    def choose_voice_samples(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose voice sample files",
            str(Path.home()),
            "Audio files (*.ogg *.opus *.wav *.mp3 *.m4a *.flac);;All files (*)",
        )
        for path in paths:
            resolved = Path(path)
            if resolved not in self.voice_sample_paths:
                self.voice_sample_paths.append(resolved)
                self.voice_samples_list.addItem(str(resolved))

    def clear_voice_samples(self) -> None:
        self.voice_sample_paths.clear()
        self.voice_samples_list.clear()

    def run_guided_setup(self) -> None:
        request = SetupRequest(
            persona_name=self.persona_name_edit.text().strip() or "Persona",
            persona_text=self.persona_text_edit.toPlainText(),
            chat_export_path=Path(self.chat_export_edit.text()).expanduser() if self.chat_export_edit.text().strip() else None,
            speaker_name=self.speaker_name_edit.text().strip(),
            voice_sample_paths=list(self.voice_sample_paths),
            force_rebuild_model=self.rebuild_model_check.isChecked(),
        )

        self.setup_log.clear()
        self.set_setup_busy(True)
        worker = FunctionWorker(self.setup_service.run_guided_setup, request)
        worker.kwargs["status_callback"] = worker.signals.status.emit
        worker.signals.status.connect(self.append_setup_log)
        worker.signals.result.connect(self.on_setup_complete)
        worker.signals.error.connect(self.on_setup_error)
        worker.signals.finished.connect(lambda: self.set_setup_busy(False))
        self.thread_pool.start(worker)

    def append_setup_log(self, message: str) -> None:
        self.setup_log.append(message)
        self.setup_log.moveCursor(QTextCursor.MoveOperation.End)

    def on_setup_complete(self, result: object) -> None:
        if isinstance(result, SetupStatus):
            self.render_setup_status(result)
        else:
            self.refresh_setup_status()
        self.enable_chat()
        self.tabs.setCurrentWidget(self.chat_tab)

    def on_setup_error(self, message: str) -> None:
        self.append_setup_log(f"Error: {message}")
        QMessageBox.warning(self, "Setup failed", message)
        self.refresh_setup_status()

    def set_setup_busy(self, busy: bool) -> None:
        self.run_setup_button.setDisabled(busy)
        self.refresh_setup_button.setDisabled(busy)
        self.run_setup_button.setText("Running setup..." if busy else "Run guided setup")

    def enable_chat(self) -> None:
        self.chat_tab.setEnabled(True)
        if self.chat_session is not None:
            return
        try:
            self.chat_session = ChatSession()
        except Exception as exc:
            self.set_runtime_status(f"Chat startup error: {exc}")
            self.chat_tab.setEnabled(False)
            return
        self.set_runtime_status("Ready")

    def refresh_audio_devices(self) -> None:
        try:
            self.audio_devices = SpeechOutputService.list_devices()
        except Exception as exc:
            self.set_runtime_status(f"Audio device error: {exc}")
            return

        self.output_device_combo.blockSignals(True)
        self.output_device_combo.clear()
        self.output_device_combo.addItem("System default", None)
        for device in self.audio_devices:
            if device.max_output_channels > 0:
                self.output_device_combo.addItem(device.label, device.index)
        self.output_device_combo.blockSignals(False)
        self.update_runtime_preferences()

    def update_runtime_preferences(self) -> None:
        self.app_state.input_mode = self.input_mode_combo.currentText()
        self.app_state.output_mode = self.output_mode_combo.currentText()
        self.app_state.playback_backend = self.playback_combo.currentText()
        self.app_state.output_device = self.output_device_combo.currentData()
        self.speech_output.configure(self.app_state.output_device, self.app_state.playback_backend)
        self.record_button.setEnabled(self.app_state.input_mode == "voice" and not self.chat_busy)

    def set_runtime_status(self, text: str) -> None:
        self.app_state.status = text
        self.runtime_status.setText(text)

    def append_message(self, speaker: str, text: str) -> None:
        label = "You" if speaker == "user" else "Persona"
        color = "#176b87" if speaker == "user" else "#35424c"
        self.transcript.append(f'<p><b style="color:{color};">{label}:</b> {self._escape_html(text)}</p>')
        self.transcript.moveCursor(QTextCursor.MoveOperation.End)

    @staticmethod
    def _escape_html(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("\n", "<br>")
        )

    def send_text_message(self) -> None:
        text = self.message_edit.text().strip()
        if not text:
            return
        self.message_edit.clear()
        self.send_message(text)

    def send_message(self, text: str) -> None:
        if self.chat_session is None:
            self.enable_chat()
        if self.chat_session is None:
            return

        self.append_message("user", text)
        self.set_chat_busy(True)
        self.set_runtime_status("Thinking...")
        worker = FunctionWorker(self.chat_session.send_message, text)
        worker.signals.result.connect(self.on_reply_ready)
        worker.signals.error.connect(self.on_chat_error)
        worker.signals.finished.connect(lambda: self.set_chat_busy(False))
        self.thread_pool.start(worker)

    def on_reply_ready(self, result: object) -> None:
        reply = str(result)
        self.append_message("persona", reply)
        self.set_runtime_status("Ready")
        if self.app_state.output_mode == "voice":
            self.speak_reply(reply)

    def on_chat_error(self, message: str) -> None:
        self.set_runtime_status(f"Chat error: {message}")
        QMessageBox.warning(self, "Chat error", message)

    def speak_reply(self, reply: str) -> None:
        self.set_runtime_status("Speaking...")
        worker = FunctionWorker(self.speech_output.speak, reply)
        worker.kwargs["status_callback"] = worker.signals.status.emit
        worker.signals.status.connect(self.set_runtime_status)
        worker.signals.result.connect(lambda _: self.set_runtime_status("Ready"))
        worker.signals.error.connect(self.on_tts_error)
        self.thread_pool.start(worker)

    def on_tts_error(self, message: str) -> None:
        self.set_runtime_status(f"TTS error: {message}")
        QMessageBox.warning(self, "Voice output error", message)

    def record_voice_message(self) -> None:
        self.set_chat_busy(True)
        self.set_runtime_status("Listening...")
        worker = FunctionWorker(self.audio_input.capture_once)
        worker.kwargs["status_callback"] = worker.signals.status.emit
        worker.signals.status.connect(self.on_voice_status)
        worker.signals.result.connect(self.on_transcript_ready)
        worker.signals.error.connect(self.on_voice_error)
        self.thread_pool.start(worker)

    def on_voice_status(self, status: str) -> None:
        labels = {
            "listening": "Listening...",
            "transcribing": "Transcribing...",
            "idle": "Ready",
        }
        self.set_runtime_status(labels.get(status, status))

    def on_transcript_ready(self, result: object) -> None:
        transcript = str(result).strip()
        if not transcript:
            self.set_runtime_status("No speech detected")
            self.set_chat_busy(False)
            return
        self.set_chat_busy(False)
        self.send_message(transcript)

    def on_voice_error(self, message: str) -> None:
        self.set_runtime_status(f"Voice input error: {message}")
        self.set_chat_busy(False)
        QMessageBox.warning(self, "Voice input error", message)

    def test_beep(self) -> None:
        self.set_runtime_status("Playing test beep...")
        worker = FunctionWorker(self.speech_output.test_beep)
        worker.signals.result.connect(lambda _: self.set_runtime_status("Ready"))
        worker.signals.error.connect(self.on_tts_error)
        self.thread_pool.start(worker)

    def reset_chat(self) -> None:
        if self.chat_session is not None:
            self.chat_session.reset()
        self.transcript.clear()
        self.set_runtime_status("History cleared")

    def set_chat_busy(self, busy: bool) -> None:
        self.chat_busy = busy
        self.send_button.setDisabled(busy)
        self.message_edit.setDisabled(busy)
        self.record_button.setDisabled(busy or self.app_state.input_mode != "voice")
        self.reset_button.setDisabled(busy)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Persona Chat")
    app.setOrganizationName("Persona Chat")
    font = QFont()
    font.setPointSize(13)
    app.setFont(font)
    window = PersonaChatWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
