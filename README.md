# Realtime Smart Voice Assistant

A voice assistant powered by OpenAI's Realtime API for direct audio-to-audio conversations — no speech-to-text pipeline, just natural low-latency voice interaction. Runs on Raspberry Pi or any macOS/Linux machine.

## Features

- **Direct voice-to-voice** via OpenAI Realtime API over WebSocket
- **Custom wake word** ("Hi Taco" default) via Picovoice Porcupine
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

The runner uses Porcupine 4. On first launch, it generates a compatible **Hi Taco** model using your Picovoice access key. This requires internet access; the generated model is reused locally afterward.

Alternatively, download a Porcupine 4 model for **Hi Taco** and your platform from [Picovoice Console](https://console.picovoice.ai/) and place it in the project root as `Hi-Taco_en_<platform>_v4_0_0.ppn`. Platform names include `mac_apple`, `mac`, `raspberry-pi`, and `linux-x86_64`. The legacy `v3_0_0` files are not used by the current runtime.

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

Set API keys in `.env` (recommended):

```
OPENAI_API_KEY=...
PORCUPINE_ACCESS_KEY=...
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

The current detector uses **Hi Taco**. Changing only `wake_keywords` in the configuration does not change the trained phrase; a different phrase also requires updating the detector's phrase/model selection and supplying a matching model.

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
- Verify the Porcupine 4 `.ppn` file is in the project root and matches your platform
- If automatic model generation fails, check that your Picovoice key is active or download the model manually
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

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution steps and [AGENTS.md](AGENTS.md) for repository guidelines.
