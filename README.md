# Realtime Smart Voice Assistant

A voice assistant powered by OpenAI's Realtime API for direct audio-to-audio conversations — no speech-to-text pipeline, just natural low-latency voice interaction. Runs on Raspberry Pi or any macOS/Linux machine.

## Features

- **Direct voice-to-voice** via OpenAI Realtime API over WebSocket
- **Offline wake word** ("Hi Taco" default) via sherpa-onnx, with no account or access key
- **YouTube Music** playback with voice commands and smart local caching
- **Album art** displayed in terminal during playback (ANSI true-color)
- **Async architecture** — non-blocking audio throughout

## Quick Start

### 1. Install Python 3.12 and system audio libraries

```bash
# macOS
brew install python@3.12 portaudio ffmpeg

# Raspberry Pi / Ubuntu / Debian
sudo apt install -y portaudio19-dev ffmpeg
```

On Linux, install Python 3.12 and its venv support using your distribution's package manager. The runner requires Python 3.12; existing environments created with another Python version must be moved aside and recreated.

### 2. Clone and set up

```bash
git clone https://github.com/duowang/realtime-smart-voice.git
cd realtime-smart-voice
./run.sh --setup-only
```

Manual alternative:

```bash
python3.12 -m venv venv && source venv/bin/activate
python -m pip install -r requirements.txt
python src/wake_word_model.py
```

### 3. Configure the OpenAI API key

```bash
cp .env.example .env
# Edit .env and add:
#   OPENAI_API_KEY=your_key_here
```

Get your key from [OpenAI](https://platform.openai.com/api-keys). Wake-word detection needs no API key.

### 4. Set up wake word

Setup downloads the pinned [sherpa-onnx keyword-spotting model](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html) (`sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01`, approximately 18 MB download), verifies its SHA-256 checksum, and caches the required files under `models/`. The model files are excluded from Git.

After that download, wake-word detection runs locally without network access or a vendor account. OpenAI conversations and music searches still require internet access. The wake-word model is English-only and uses its bundled SentencePiece tokenizer to encode **Hi Taco**; no phrase training is needed. Conversation language support is unchanged.

### 5. Run

```bash
./run.sh
```

## Usage

1. Say **"Hi Taco"** to start a conversation
2. Speak naturally — the conversation is real-time with low latency
3. Say "goodbye", "stop", etc. to end, or it times out after silence

### Music Commands

| Command | Examples |
|---------|----------|
| Play | "Play Bohemian Rhapsody", "Play something by Adele" |
| Pause / Resume | "Pause", "Resume", "Continue playing" |
| Stop | "Stop music" |
| Skip | "Next song", "Skip" |

Say **"Hi Taco"** while music is playing, wait for the greeting, then say **"pause the music"**. Music pauses immediately on wake-up. It resumes after ordinary conversations, but an explicit pause keeps it paused until you request resume. Songs and album art are cached locally in `music_cache/`.

Playback defaults to 35% volume so the microphone can hear the wake phrase over the speakers. Set `music_volume` in `config/config.json` between `0.0` and `1.0` to adjust it. Loud music can still mask speech; this application does not perform acoustic echo cancellation.

## Development Setup

Install development tooling:

```bash
source venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run checks:

```bash
python -m compileall src
ruff check src
pytest
```

Or with make targets:

```bash
make setup
make dev-deps
make check
```

### Headless integration test

Use prerecorded speech to test wake → play → wake → pause → wake → resume → wake → stop. This runs the actual sherpa model, OpenAI Realtime command routing, YouTube Music search, and pygame decoding with SDL's silent output device. It needs the normal API key and internet connection, and uses no microphone or speakers.

Provide a mono PCM16 wake recording at 16 kHz, plus `play.wav`, `pause.wav`, `resume.wav`, and `stop.wav` at 24 kHz containing the corresponding spoken commands:

```bash
venv/bin/python tests/headless_smoke.py \
  --wake-audio /path/to/hi-taco.wav \
  --commands-dir /path/to/commands \
  --report tmp/headless-smoke.json
```

Add `--background-audio /path/to/music-16k.wav --snr-db 5` to mix music into the wake input during playback. The test checks that playback advances, pause remains effective after the conversation, resume advances again, stop releases the track, and wake detection still works afterward. Reports and personal recordings should stay out of Git. Digital mixtures test masking, but do not reproduce room acoustics or microphone hardware.

## Configuration

Set the API key in `.env` (recommended):

```
OPENAI_API_KEY=...
```

Set runtime options in `config/config.json`. Conversation timeout defaults to 120 seconds, silence timeout to 8 seconds, and the pause after an assistant response to 6 seconds. Override these with `conversation_timeout`, `silence_timeout`, and `post_response_timeout`, respectively.

The default Realtime stack uses `gpt-realtime-2.1` with the `marin` voice. You can override it in `config/config.json`:
```json
{
  "realtime_model": "gpt-realtime-2.1",
  "realtime_voice": "marin",
  "transcription_model": "gpt-4o-mini-transcribe",
  "transcription_language": null
}
```

Set `"transcription_language"` to an ISO-639-1 code like `"en"` or `"zh"` if you want to force one language. Leave it as `null` to let the Realtime stack auto-detect multilingual speech.

Configure English wake phrases and detection confidence in `config/config.json`:

```json
{
  "wake_keywords": ["Hi Taco"],
  "wake_word_threshold": 0.1
}
```

Wake phrases are tokenized with the English model’s bundled vocabulary, using letters, apostrophes, and spaces. Higher thresholds reduce false activations but may miss more wake words; lower thresholds increase sensitivity. Valid thresholds are greater than 0 and at most 1. An optional `wake_word_model_dir` selects a cache directory (relative paths resolve from the project root).

## Project Structure

```
src/
  realtime_voice_assistant.py  # Main orchestrator
  wake_word_detector.py        # Offline sherpa-onnx wake word detection
  wake_word_model.py           # Pinned model download and cache
  realtime_voice_client.py     # OpenAI Realtime API (WebSocket)
  music_commands.py            # Music command handler
  youtube_music_player.py      # YouTube Music player, caching, thumbnail rendering
config/config.json             # App configuration
models/                        # Downloaded wake-word model (ignored by Git)
music_cache/                   # Cached audio (*.mp3), thumbnails (*_thumb.jpg), metadata
logs/                          # Application logs
```

## Troubleshooting

**Audio not working:**
```bash
# Test mic (Linux/Pi)
arecord -d 5 test.wav && aplay test.wav

# List audio devices
python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)}') for i in range(p.get_device_count())]"
```

**Wake word not triggering:**
- Run `./run.sh --setup-only` to download any missing model files
- Verify microphone permission and input level, then say the configured phrase clearly
- Lower `wake_word_threshold` slightly if it misses phrases, or raise it if unrelated speech triggers it
- If a download fails its checksum, rerun setup with a working connection; unverified files are not installed

**Music not playing:**
- Check internet connection (needed for YouTube Music search)
- Clear corrupted cache: `rm -rf music_cache/`
- Test audio: `python -c "import pygame; pygame.mixer.init(); print('OK')"`

**Dependencies broken:**
```bash
rm -rf venv && ./run.sh --setup-only && ./run.sh
```

## License

MIT License - see [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution steps and [AGENTS.md](AGENTS.md) for repository guidelines.
