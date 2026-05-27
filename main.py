"""Entry point for the fully local persona chat loop."""

from __future__ import annotations

import argparse
import sys

import stt
import vad
import audio_utils
from config import CONFIG
from llm import PersonaLLM
from tts import PersonaTTS, play_test_beep


def _is_exit_command(text: str) -> bool:
    """Return whether the transcript asks to end the session.

    Args:
        text: Transcribed user speech.

    Returns:
        True when the text contains a supported exit command.
    """

    lowered = text.lower()
    return any(command in lowered for command in ("goodbye", "quit", "exit"))


def _is_reset_command(text: str) -> bool:
    """Return whether the transcript asks to clear chat history.

    Args:
        text: Transcribed user speech.

    Returns:
        True when the transcript contains the reset command.
    """

    return "reset" in text.lower()


def parse_args() -> argparse.Namespace:
    """Parse command-line options for input and output modes.

    Args:
        None.

    Returns:
        Parsed argparse namespace with input_mode and output_mode fields.
    """

    parser = argparse.ArgumentParser(description="Run the local persona chat system.")
    parser.add_argument(
        "--input",
        dest="input_mode",
        choices=("voice", "text"),
        default=CONFIG.DEFAULT_INPUT_MODE,
        help="Use microphone speech or typed terminal input.",
    )
    parser.add_argument(
        "--output",
        dest="output_mode",
        choices=("voice", "text"),
        default=CONFIG.DEFAULT_OUTPUT_MODE,
        help="Play persona replies as voice or print text only.",
    )
    parser.add_argument(
        "--output-device",
        dest="output_device",
        type=int,
        default=CONFIG.AUDIO_OUTPUT_DEVICE,
        help="Optional sounddevice output device index for voice playback.",
    )
    parser.add_argument(
        "--playback",
        dest="playback_backend",
        choices=("auto", "sounddevice", "afplay"),
        default=CONFIG.PLAYBACK_BACKEND,
        help="Audio playback backend for voice output.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input/output devices and exit.",
    )
    parser.add_argument(
        "--test-beep",
        action="store_true",
        help="Play a short routing beep and exit before loading the persona.",
    )
    return parser.parse_args()


def read_user_text(input_mode: str) -> str:
    """Read one user message from the configured input mode.

    Args:
        input_mode: Either voice for microphone input or text for terminal input.

    Returns:
        User message text, or an empty string if no usable input was captured.
    """

    if input_mode == "text":
        try:
            return input("You: ").strip()
        except EOFError:
            return "quit"

    audio = vad.record_until_silence()
    transcription = stt.transcribe(audio)
    if transcription:
        print(f"You: {transcription}")
    return transcription


def main() -> int:
    """Run the local persona conversation loop.

    Args:
        None.

    Returns:
        Process exit code, where 0 indicates a clean shutdown.
    """

    args = parse_args()
    if args.list_devices:
        audio_utils.list_audio_devices()
        return 0
    if args.test_beep:
        play_test_beep(output_device=args.output_device, playback_backend=args.playback_backend)
        print("Played test beep.")
        return 0

    print("═══════════════════════════════")
    print("     PERSONA CHAT  (local)     ")
    print("═══════════════════════════════")

    try:
        llm = PersonaLLM()
        tts = (
            PersonaTTS(output_device=args.output_device, playback_backend=args.playback_backend)
            if args.output_mode == "voice"
            else None
        )
    except Exception as exc:
        print(f"Startup error: {exc}")
        return 1

    if args.input_mode == "voice":
        print("System ready. Start speaking. Say 'goodbye' to exit.")
    else:
        print("System ready. Start typing. Type 'goodbye' to exit.")
    print(f"Mode: input={args.input_mode} | output={args.output_mode}")
    print("Commands: 'reset' clears history | 'quit'/'goodbye' exits")

    try:
        while True:
            user_message = read_user_text(args.input_mode)
            if not user_message:
                print("?")
                continue

            if _is_exit_command(user_message):
                break
            if _is_reset_command(user_message):
                llm.reset_history()
                print("History cleared.")
                continue

            reply = llm.chat(user_message)
            if not reply:
                continue
            print(f"Persona: {reply}")
            if tts is not None:
                tts.speak(reply)
    except KeyboardInterrupt:
        print("\nEnding session.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
