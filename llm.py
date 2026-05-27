"""Local Ollama chat interface for the persona model."""

from __future__ import annotations

from typing import Any

import requests

from config import CONFIG


LOCAL_OLLAMA_BIN = CONFIG.BASE_DIR / "tools" / "Ollama.app" / "Contents" / "Resources" / "ollama"


class PersonaLLM:
    """Chat client for a locally registered Ollama persona model."""

    def __init__(self) -> None:
        """Initialize chat history and verify that Ollama is ready.

        Args:
            None.

        Returns:
            None.

        Raises:
            RuntimeError: If Ollama is unreachable or the persona model is missing.
        """

        self.history: list[dict[str, str]] = []
        self._verify_ollama()

    def _verify_ollama(self) -> None:
        """Check that the Ollama server is running and has the persona model.

        Args:
            None.

        Returns:
            None.

        Raises:
            RuntimeError: If the local Ollama server or configured model is unavailable.
        """

        try:
            response = requests.get(f"{CONFIG.OLLAMA_HOST}/api/tags", timeout=5)
            response.raise_for_status()
        except requests.ConnectionError as exc:
            local_hint = (
                f"`{LOCAL_OLLAMA_BIN} serve`"
                if LOCAL_OLLAMA_BIN.exists()
                else "`ollama serve`"
            )
            raise RuntimeError(
                "Ollama is not running. Start the local server in another terminal with "
                f"{local_hint}, then try again."
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Ollama check failed: {exc}") from exc

        payload = response.json()
        models = payload.get("models", [])
        names = {model.get("name", "").split(":", 1)[0] for model in models}
        full_names = {model.get("name", "") for model in models}
        if CONFIG.OLLAMA_MODEL_NAME not in names and CONFIG.OLLAMA_MODEL_NAME not in full_names:
            raise RuntimeError(
                f"Persona model `{CONFIG.OLLAMA_MODEL_NAME}` was not found. "
                "Run `python persona_builder.py` first."
            )

    def _trim_history(self) -> None:
        """Trim chat history to the configured recent-message limit.

        Returns:
            None.
        """

        limit = CONFIG.CONVERSATION_HISTORY_LIMIT
        if len(self.history) <= limit:
            return

        system_messages = [message for message in self.history if message.get("role") == "system"]
        non_system = [message for message in self.history if message.get("role") != "system"]
        remaining_slots = max(limit - len(system_messages), 0)
        recent_non_system = non_system[-remaining_slots:] if remaining_slots else []
        self.history = system_messages + recent_non_system

    def chat(self, user_message: str) -> str:
        """Send a user message to Ollama and return the persona reply.

        Args:
            user_message: The transcribed user utterance.

        Returns:
            The assistant reply text. If Ollama fails, returns an empty string.
        """

        self.history.append({"role": "user", "content": user_message})
        self._trim_history()

        payload: dict[str, Any] = {
            "model": CONFIG.OLLAMA_MODEL_NAME,
            "messages": self.history,
            "stream": False,
            "options": {"temperature": 0.85, "top_p": 0.9},
        }

        try:
            response = requests.post(f"{CONFIG.OLLAMA_HOST}/api/chat", json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            reply = str(data.get("message", {}).get("content", "")).strip()
        except requests.ConnectionError:
            print("LLM error: Ollama is not reachable. Start Ollama and try again.")
            self.history.pop()
            return ""
        except requests.RequestException as exc:
            print(f"LLM error: Ollama request failed: {exc}")
            self.history.pop()
            return ""
        except ValueError as exc:
            print(f"LLM error: Ollama returned invalid JSON: {exc}")
            self.history.pop()
            return ""

        if not reply:
            print("LLM error: Ollama returned an empty response.")
            return ""

        self.history.append({"role": "assistant", "content": reply})
        self._trim_history()
        return reply

    def reset_history(self) -> None:
        """Clear all conversation history.

        Returns:
            None.
        """

        self.history.clear()
