# Realtime Smart Voice Assistant

A voice assistant powered by OpenAI's Realtime API for direct audio-to-audio conversations — no speech-to-text pipeline, just natural low-latency voice interaction. Runs on Raspberry Pi or any macOS/Linux machine.

## Features

- **Direct voice-to-voice** via OpenAI Realtime API (GA) over WebSocket
- **Custom wake word** ("Hi Taco" default) via Picovoice Porcupine
- **YouTube Music** playback with voice commands and smart local caching
- **Album art** displayed in terminal during playback (ANSI true-color)
- **Async architecture** — non-blocking audio throughout

## Quick Start

### 1. Install system audio library

```bash
# macOS
brew install portaudio

# Raspberry Pi / Ubuntu / Debian
sudo apt install -y portaudio19-dev python3-pyaudio python3-pip python3-venv
```

### 2. Clone and set up

```bash
git clone https://github.com/your-username/realtime-smart-voice.git
cd realtime-smart-voice
./run.sh --setup-only
```

Manual alternative:

```bash
python3 -m venv venv && source venv/bin/activate
python -m pip install -r requirements.txt
```

### 3. Configure API keys

```bash
cp .env.example .env
# Edit .env and add:
#   OPENAI_API_KEY=your_key_here
#   PORCUPINE_ACCESS_KEY=your_key_here
```

Get your keys from [OpenAI](https://platform.openai.com/api-keys) and [Picovoice Console](https://console.picovoice.ai/).

### 4. Set up wake word

1. In [Picovoice Console](https://console.picovoice.ai/) go to Porcupine > Train Custom Wake Word
2. Train a phrase (e.g. "Hi Taco"), select your platform, download the `.ppn` file
3. Place the `.ppn` file in the project root

### 5. Run

```bash
./run.sh
```

## Usage

1. Say **"Hi Taco"** (or your custom wake word) to start a conversation
2. Speak naturally — the conversation is real-time with low latency
3. Say "goodbye", "stop", etc. to end, or it times out after silence

### Music Commands

| Command | Examples |
|---------|----------|
| Play | "Play Bohemian Rhapsody", "Play something by Adele" |
| Pause / Resume | "Pause", "Resume", "Continue playing" |
| Stop | "Stop music" |
| Skip | "Next song", "Skip" |

Music auto-pauses during conversation and resumes after. Songs and album art are cached locally in `music_cache/`.

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

## Configuration

API keys and settings via `.env` (recommended) or `config/config.json`:

```
OPENAI_API_KEY=...
PORCUPINE_ACCESS_KEY=...
CONVERSATION_TIMEOUT=30    # seconds before returning to wake word
SILENCE_TIMEOUT=15         # seconds of silence to end conversation
LOG_LEVEL=INFO
```

To use a custom wake word, update `config/config.json`:
```json
{ "wake_keywords": ["Your Phrase"] }
```

## Project Structure

```
src/
  realtime_voice_assistant.py  # Main orchestrator
  wake_word_detector.py        # Picovoice wake word detection
  realtime_voice_client.py     # OpenAI Realtime API (WebSocket)
  music_commands.py            # Music command handler
  youtube_music_player.py      # YouTube Music player, caching, thumbnail rendering
config/config.json             # App configuration
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
- Verify `.ppn` file is in project root and matches your platform
- Check that `wake_keywords` in config matches your trained phrase exactly
- Test your Picovoice key: `python -c "import pvporcupine; p = pvporcupine.create(access_key='YOUR_KEY', keywords=['computer']); print('OK'); p.delete()"`

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

See [AGENTS.md](AGENTS.md) for contributor guidelines.
