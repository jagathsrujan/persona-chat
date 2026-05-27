"""Extract one speaker's messages from a WhatsApp chat export."""

from __future__ import annotations

import re
import sys
from pathlib import Path


LINE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}\s+-\s+([^:]+):\s?(.*)$")
SYSTEM_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4},\s+\d{1,2}:\d{2}\s+-\s+")
ARTIFACT_RE = re.compile(r"<(?:Media omitted|This message was edited|This message was deleted)>")


def clean_message(text: str) -> str:
    """Remove WhatsApp export artifacts from a message body.

    Args:
        text: Raw message body from the WhatsApp export.

    Returns:
        Cleaned message text with export-only markers removed.
    """

    cleaned = ARTIFACT_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_messages(chat_path: Path, speaker: str) -> list[str]:
    """Extract messages sent by one WhatsApp participant.

    Args:
        chat_path: Path to the WhatsApp exported .txt file.
        speaker: Exact participant display name to extract.

    Returns:
        A list of cleaned message strings for the requested speaker.
    """

    messages: list[str] = []
    current_speaker: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        """Append the current buffered message if it belongs to the target speaker.

        Args:
            None.

        Returns:
            None.
        """

        nonlocal current_speaker, current_parts
        if current_speaker == speaker and current_parts:
            message = clean_message("\n".join(part.strip() for part in current_parts))
            if message:
                messages.append(message)
        current_speaker = None
        current_parts = []

    for raw_line in chat_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        match = LINE_RE.match(line)
        if match:
            flush()
            current_speaker = match.group(1).strip()
            body = clean_message(match.group(2))
            if body:
                current_parts.append(body)
            continue

        if SYSTEM_RE.match(line):
            flush()
            continue

        if current_speaker is not None and line:
            body = clean_message(line)
            if body:
                current_parts.append(body)

    flush()
    return messages


def main() -> int:
    """Run the WhatsApp persona extraction command.

    Args:
        None.

    Returns:
        Process exit code.
    """

    if len(sys.argv) != 4:
        print("Usage: extract_whatsapp_persona.py CHAT_EXPORT OUTPUT_TEXT SPEAKER_NAME")
        return 2

    chat_path = Path(sys.argv[1]).expanduser()
    output_path = Path(sys.argv[2]).expanduser()
    speaker = sys.argv[3]

    if not chat_path.exists():
        print(f"Missing chat export: {chat_path}")
        return 1

    messages = extract_messages(chat_path, speaker)
    if not messages:
        print(f"No messages found for speaker `{speaker}`.")
        return 1

    output_path.write_text("\n".join(messages) + "\n", encoding="utf-8")
    print(f"✓ Extracted {len(messages)} messages for {speaker} into {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
