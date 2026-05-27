# Persona Chat Local

Fully local persona voice chat for Apple Silicon Macs.

Pipeline:

```text
Microphone or keyboard -> VAD/STT or text input -> Ollama -> XTTS-v2 -> text or voice output
```

No cloud APIs are used at runtime. First-time setup downloads local dependencies and models.

## Privacy

Private persona assets are intentionally ignored by git:

- `persona.txt`
- `Modelfile`
- `voice_samples/speaker.wav`
- `temp/`
- `tools/`
- `.venv/`

Do not commit chat exports, voice samples, or generated persona prompts unless you have permission and understand the privacy risk.

## Setup

Install local Ollama and Python without touching Homebrew:

```bash
./scripts/install_ollama_local.sh
./scripts/install_python_local.sh
```

Create your persona input:

```bash
cp persona.example.txt persona.txt
```

Add a voice sample:

```bash
mkdir -p voice_samples
# put one or more .ogg/.opus/.wav/.mp3/.m4a/.flac files in voice_samples/raw/
```

For WhatsApp exports, extract one speaker's messages:

```bash
python scripts/extract_whatsapp_persona.py "/path/to/WhatsApp Chat.txt" persona.txt "Speaker Name"
```

Run setup:

```bash
./setup.sh
```

When prompted by `persona_builder.py`, enter the persona name and confirm the generated prompt.

## Start Ollama

In one terminal:

```bash
./tools/Ollama.app/Contents/Resources/ollama serve
```

Leave it open.

## Run

In another terminal:

```bash
source .venv/bin/activate
python main.py --input text --output text
```

Useful modes:

```bash
python main.py --input text --output voice --playback afplay
python main.py --input voice --output text
python main.py --input voice --output voice --playback afplay
```

Test audio routing before voice output:

```bash
python main.py --test-beep --playback afplay
```

List sounddevice devices:

```bash
python main.py --list-devices
```

## Notes

- XTTS-v2 can take several seconds per response.
- `--output text` skips loading XTTS and starts faster.
- On macOS, `--playback afplay` follows the system-selected output device.
