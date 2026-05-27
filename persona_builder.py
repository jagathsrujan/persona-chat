"""Build an Ollama persona model from raw message text."""

from __future__ import annotations

import re
import subprocess
import os
from collections import Counter
from pathlib import Path

from config import CONFIG


STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "also",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "but",
    "by",
    "can",
    "did",
    "do",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "him",
    "his",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "just",
    "like",
    "me",
    "my",
    "no",
    "not",
    "of",
    "ok",
    "on",
    "or",
    "our",
    "she",
    "so",
    "that",
    "the",
    "then",
    "there",
    "this",
    "to",
    "too",
    "u",
    "ur",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "who",
    "why",
    "will",
    "with",
    "would",
    "yeah",
    "you",
    "your",
}


def _split_sentences(text_data: str) -> list[str]:
    """Split raw text into sentence-like chunks.

    Args:
        text_data: Raw persona text.

    Returns:
        A list of non-empty sentence-like strings.
    """

    pieces = re.split(r"(?<=[.!?])\s+|\n+", text_data)
    return [piece.strip() for piece in pieces if piece.strip()]


def _words(text_data: str) -> list[str]:
    """Extract lowercase word tokens from raw text.

    Args:
        text_data: Raw persona text.

    Returns:
        A list of lowercase tokens including apostrophe contractions.
    """

    return re.findall(r"[A-Za-z][A-Za-z']*", text_data.lower())


def _average_sentence_length(sentences: list[str]) -> float:
    """Calculate average sentence length in words.

    Args:
        sentences: Sentence-like strings extracted from the corpus.

    Returns:
        Average words per sentence, or 0.0 when no sentences are present.
    """

    if not sentences:
        return 0.0
    lengths = [len(_words(sentence)) for sentence in sentences]
    return sum(lengths) / len(lengths)


def _punctuation_description(text_data: str) -> str:
    """Describe punctuation patterns in the corpus.

    Args:
        text_data: Raw persona text.

    Returns:
        A short natural-language punctuation summary.
    """

    ellipses = text_data.count("...")
    exclamations = text_data.count("!")
    questions = text_data.count("?")
    emoji_count = len(re.findall(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]", text_data))
    parts = [
        f"{questions} question marks",
        f"{exclamations} exclamation marks",
        f"{ellipses} ellipses",
        f"{emoji_count} emoji-like symbols",
    ]
    if exclamations > questions:
        parts.append("leans expressive")
    elif questions > exclamations:
        parts.append("often asks direct questions")
    else:
        parts.append("uses balanced punctuation")
    return "; ".join(parts)


def _formality_description(tokens: list[str]) -> str:
    """Infer casual or formal style from contractions and slang.

    Args:
        tokens: Lowercase word tokens.

    Returns:
        A short style description.
    """

    contractions = [token for token in tokens if "'" in token]
    slang = {"lol", "haha", "lmao", "ig", "idk", "tmr", "abt", "tho", "cuz", "stfu", "fr", "lemme", "gonna", "wanna"}
    slang_hits = sorted(set(tokens).intersection(slang))
    if len(contractions) + len(slang_hits) > 10:
        level = "very casual and chat-like"
    elif slang_hits or contractions:
        level = "casual"
    else:
        level = "fairly plain and direct"
    details = f"; recurring casual markers: {', '.join(slang_hits[:12])}" if slang_hits else ""
    return f"{level}{details}"


def _perspective_description(tokens: list[str]) -> str:
    """Compare first-person and second-person language use.

    Args:
        tokens: Lowercase word tokens.

    Returns:
        A short perspective summary.
    """

    first_person = sum(1 for token in tokens if token in {"i", "me", "my", "mine", "myself"})
    second_person = sum(1 for token in tokens if token in {"you", "u", "your", "ur", "yours"})
    if first_person > second_person * 1.2:
        dominant = "first-person dominant"
    elif second_person > first_person * 1.2:
        dominant = "second-person/direct-address dominant"
    else:
        dominant = "balanced between self-reference and direct address"
    return f"{dominant} ({first_person} first-person markers, {second_person} second-person markers)"


def _top_words(tokens: list[str], limit: int = 50) -> list[str]:
    """Find frequent non-stopword vocabulary.

    Args:
        tokens: Lowercase word tokens.
        limit: Maximum number of words to return.

    Returns:
        A list of common words with counts formatted as strings.
    """

    counts = Counter(token for token in tokens if token not in STOPWORDS and len(token) > 1)
    return [f"{word} ({count})" for word, count in counts.most_common(limit)]


def _repeated_phrases(tokens: list[str], limit: int = 30) -> list[str]:
    """Find repeated two- and three-word phrases.

    Args:
        tokens: Lowercase word tokens.
        limit: Maximum number of phrases to return.

    Returns:
        A list of phrase strings with counts.
    """

    phrases: Counter[str] = Counter()
    for size in (2, 3):
        for index in range(0, max(len(tokens) - size + 1, 0)):
            phrase_tokens = tokens[index : index + size]
            if all(token in STOPWORDS for token in phrase_tokens):
                continue
            phrases[" ".join(phrase_tokens)] += 1
    return [f"{phrase} ({count})" for phrase, count in phrases.items() if count > 2][:limit]


def _tone_description(tokens: list[str], text_data: str) -> str:
    """Infer broad emotional tone from word and marker patterns.

    Args:
        tokens: Lowercase word tokens.
        text_data: Raw persona text.

    Returns:
        A short tone summary.
    """

    token_set = set(tokens)
    humor = token_set.intersection({"lol", "haha", "lmao"}) or re.search(r"[😆😂🤣🤪]", text_data)
    negativity = token_set.intersection({"hate", "annoying", "stressful", "wrong", "sad", "bad", "scared"})
    enthusiasm = token_set.intersection({"damn", "really", "definitely", "happy", "better", "good"})
    empathy = token_set.intersection({"sorry", "care", "understand", "kind", "sweet"})
    sarcasm = token_set.intersection({"sure", "obviously", "delusional", "unpaid", "therapist"})

    traits: list[str] = []
    if humor:
        traits.append("playful humor and teasing")
    if negativity:
        traits.append("direct about discomfort or boundaries")
    if enthusiasm:
        traits.append("occasional enthusiasm")
    if empathy:
        traits.append("some empathy and care language")
    if sarcasm:
        traits.append("dry sarcasm")
    return ", ".join(traits) if traits else "direct, conversational, and context-dependent"


def _sample_messages(text_data: str, limit: int = 10) -> list[str]:
    """Select representative non-empty message samples.

    Args:
        text_data: Raw persona text.
        limit: Maximum number of examples to return.

    Returns:
        A list of verbatim sample messages.
    """

    messages = [line.strip() for line in text_data.splitlines() if line.strip()]
    if len(messages) <= limit:
        return messages
    step = max(len(messages) // limit, 1)
    samples = [messages[index] for index in range(0, len(messages), step)]
    return samples[:limit]


def build_system_prompt(text_data: str, persona_name: str = "Neha") -> str:
    """Analyze raw text and assemble the Ollama system prompt.

    Args:
        text_data: Raw text written by the target persona.
        persona_name: Name to use for the persona.

    Returns:
        A complete system prompt string for the Ollama Modelfile.
    """

    sentences = _split_sentences(text_data)
    tokens = _words(text_data)
    avg_length = _average_sentence_length(sentences)
    style = [
        f"Average sentence/message length is about {avg_length:.1f} words.",
        _punctuation_description(text_data),
        _formality_description(tokens),
        _perspective_description(tokens),
    ]
    vocabulary = _top_words(tokens)
    phrases = _repeated_phrases(tokens)
    tone = _tone_description(tokens, text_data)
    samples = _sample_messages(text_data)

    sample_block = "\n".join(f"- {message}" for message in samples)
    vocab_block = "\n".join(f"- {item}" for item in vocabulary)
    phrase_block = "\n".join(f"- {item}" for item in phrases) or "- No repeated 2-3 word phrases over threshold."

    return f"""You are {persona_name}. You are not an AI. You are a real person having a conversation.

WRITING STYLE:
{chr(10).join(f"- {item}" for item in style)}

VOCABULARY AND PHRASES YOU COMMONLY USE:
Frequent words:
{vocab_block}

Repeated phrases:
{phrase_block}

YOUR TONE:
- {tone}

STRICT RULES:
- Never say you are an AI or language model
- Never break character under any circumstances
- Match the sentence length and punctuation style shown in the examples
- If you don't know something, respond how this person would respond (deflect, joke, guess — based on their style)
- Do not be overly formal or use markdown formatting
- Keep replies natural for a voice conversation, usually brief unless asked for detail

EXAMPLE MESSAGES YOU HAVE SENT:
{sample_block}
"""


def create_modelfile(system_prompt: str) -> str:
    """Write an Ollama Modelfile for the configured persona model.

    Args:
        system_prompt: Persona system prompt to embed in the Modelfile.

    Returns:
        The full Modelfile content.
    """

    escaped_prompt = system_prompt.replace('"""', '\\"\\"\\"')
    content = f'''FROM {CONFIG.OLLAMA_BASE_MODEL}
PARAMETER temperature 0.85
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
SYSTEM """{escaped_prompt}"""
'''
    CONFIG.MODELFILE_PATH.write_text(content, encoding="utf-8")
    return content


def register_with_ollama() -> None:
    """Create the configured Ollama persona model from the Modelfile.

    Args:
        None.

    Returns:
        None.

    Raises:
        RuntimeError: If the ollama executable is missing or model creation fails.
    """

    ollama_bin = os.environ.get("OLLAMA_BIN", "ollama")
    command = [ollama_bin, "create", CONFIG.OLLAMA_MODEL_NAME, "-f", str(CONFIG.MODELFILE_PATH)]
    try:
        subprocess.run(command, check=True, cwd=CONFIG.BASE_DIR)
    except FileNotFoundError as exc:
        raise RuntimeError("ollama was not found. Install it with `brew install ollama`.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Ollama failed to create the persona model. Make sure Ollama is running "
            f"and `{CONFIG.OLLAMA_BASE_MODEL}` has been pulled."
        ) from exc
    print("✓ Persona model created")


def main() -> None:
    """Build and optionally register the persona model from persona.txt.

    Args:
        None.

    Returns:
        None.
    """

    if not CONFIG.PERSONA_TEXT_PATH.exists():
        raise FileNotFoundError(f"Missing persona text file: {CONFIG.PERSONA_TEXT_PATH}")

    text_data = CONFIG.PERSONA_TEXT_PATH.read_text(encoding="utf-8").strip()
    if not text_data:
        raise RuntimeError("persona.txt is empty. Add the person's raw text data first.")

    persona_name = input("Enter the persona's name: ").strip() or "Neha"
    system_prompt = build_system_prompt(text_data, persona_name=persona_name)
    print("\nGenerated system prompt:\n")
    print(system_prompt)
    confirm = input("\nCreate Ollama model with this prompt? (y/n): ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Cancelled. Edit persona.txt and run persona_builder.py again when ready.")
        return

    create_modelfile(system_prompt)
    register_with_ollama()
    print("\nNext steps:")
    print("1. Make sure voice_samples/speaker.wav exists.")
    print("2. Run: python main.py")


if __name__ == "__main__":
    main()
