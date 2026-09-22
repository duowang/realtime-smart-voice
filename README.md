# Realtime Smart Voice Assistant

Say **“Hi Taco”** to talk with an OpenAI Realtime voice assistant in English or Mandarin, play music, or set a timer. Wake-word detection runs locally with sherpa-onnx and needs no account or access key.

- Voice conversations over OpenAI Realtime, with interruption support.
- YouTube Music search, play, pause, resume, and stop; songs are cached locally.
- Named countdown timers that survive conversations and application restarts.
- Optional terminal album art, local timer chimes, and orderly shutdown.

## Install and run

You need a microphone, speakers or headphones, internet access, and an [OpenAI API key](https://platform.openai.com/api-keys) with Realtime access. Conversations and spoken commands use the OpenAI API; wake detection and timer chimes run locally.

The runner supports **macOS and Linux**. macOS Apple Silicon has been tested locally; Ubuntu 24.04 runs the automated tests. For Raspberry Pi, use a **64-bit OS**; real Pi audio hardware has not been validated. Windows is not supported by this runner.

### 1. Install prerequisites once

**macOS** — install [Homebrew](https://brew.sh/) if needed, then:

```bash
brew install git uv portaudio ffmpeg
```

**Ubuntu / Debian / 64-bit Raspberry Pi OS:**

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates build-essential pkg-config portaudio19-dev libsndfile1 ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
```

[uv installs Python](https://docs.astral.sh/uv/guides/install-python/) for this project, so you do not need to replace your system Python. The runner also finds uv in its default `~/.local/bin` location. See the [official uv installation options](https://docs.astral.sh/uv/getting-started/installation/) for other installation methods.

Already have Python 3.12 and its development headers/venv support? You can skip uv. On Ubuntu 24.04, install `python3.12-venv` and `python3.12-dev`. Other Linux distributions need equivalent PortAudio development headers, libsndfile, FFmpeg, and C build tools.

### 2. Download and set up the assistant

```bash
git clone https://github.com/duowang/realtime-smart-voice.git
cd realtime-smart-voice
./run.sh --setup-only
```

Setup creates `venv/`, installs Python dependencies, downloads and verifies the approximately 18 MB wake model, and creates a private `.env` template when a key is missing. It does **not** open the microphone or speakers. Existing `.env` files and settings are preserved. No OpenAI key is needed for setup.

### 3. Add your key and start

Open the new `.env` file in your editor and replace the placeholder:

```dotenv
OPENAI_API_KEY=your_actual_api_key
```

Then run:

```bash
./run.sh --doctor
./run.sh
```

On macOS, allow microphone access for the terminal application when prompted. Choose your microphone and output device in the operating system's sound settings.

When the terminal says **“Listening for Hi Taco”**, say **“Hi Taco”**, wait for the greeting, then ask a question or give a command. Press **Ctrl+C** to stop the application.

For later launches, just run `./run.sh`. You do not need to activate the virtual environment. Normal launches reuse installed dependencies; `--setup-only` can also repair an installation. Run `./run.sh --help` for all options.

## Try it

Start each interaction with **“Hi Taco”** and wait for the greeting.

| What you want | Say |
| --- | --- |
| Conversation | “Explain why the sky is blue.” |
| Mandarin | “给我讲一个简短的笑话。” |
| Play music | “Play Bohemian Rhapsody.” |
| Pause / resume | “Pause the music.” / “Resume the music.” |
| Stop music | “Stop the music.” |
| Skip | “Skip this song.” (stops it; then choose another song) |
| Create a timer | “Set an eight-minute pasta timer.” |
| Check timers | “How much time is left on the pasta timer?” |
| Cancel a timer | “Cancel the pasta timer.” |
| Dismiss an alert | “Dismiss the tea timer.” |
| End a conversation | “Goodbye.” |

### Music behavior

Saying “Hi Taco” pauses music for the conversation. Music resumes afterward unless you explicitly pause or stop it. Songs and artwork are cached in `music_cache/`; artwork loading does not delay playback. There is one current track and no playlist queue.

Playback defaults to 35% volume to help the microphone hear the wake phrase. Loud music can still mask speech; acoustic echo cancellation is not implemented. Lower `music_volume` or move the microphone farther from the speakers if wake detection becomes unreliable.

### Timer behavior

Timers keep running between conversations and while music plays. At expiry, the terminal prints the label and a local chime sounds for up to ten seconds, temporarily lowering music volume. “Hi Taco” hushes the chime; you can then check or dismiss the expired timer. Chimes wait for an ongoing spoken turn to finish. Cancelling or dismissing a timer does not change music playback intent.

Durations range from one second to 24 hours, with up to 20 running or undismissed timers. Timer state is saved in `data/timers.json`. On restart, future timers resume, timers overdue by up to five minutes chime once, and older ones are marked missed. Keep the app running and the computer awake for on-time alerts. These countdowns cannot wake a sleeping computer. Use one assistant process per timer file.

## Update

Stop the assistant with **Ctrl+C**, then run from the repository directory:

```bash
git pull --ff-only
./run.sh --setup-only
./run.sh
```

Setup preserves your existing `.env`, downloaded music, and timers. If you use a custom config, pass the same `--config` to setup, doctor, and run. Git may ask you to resolve local changes to tracked files before updating; keep personal settings in a separate config as shown below.

## Configuration

Defaults live in `config/config.json`. To keep personal settings separate from repository updates:

```bash
cp config/config.json config/local.json
# Edit config/local.json, then:
./run.sh --config config/local.json
```

`config/local.json` is ignored by Git. Custom config paths passed to the runner are relative to the repository root, even when launching from another directory. For example:

```bash
./run.sh --setup-only --config config/local.json
./run.sh --doctor --config config/local.json
```

| Setting | Default | Purpose |
| --- | --- | --- |
| `wake_keywords` | `["Hi Taco"]` | English wake phrases; no phrase training needed |
| `wake_word_threshold` | `0.1` | Higher values reduce false wakes but may miss more speech; range `(0, 1]` |
| `music_volume` | `0.35` | Playback volume, from 0 to 1 |
| `realtime_model` | `gpt-realtime-2.1` | OpenAI Realtime model |
| `realtime_voice` | `marin` | Assistant voice |
| `transcription_model` | `gpt-4o-mini-transcribe` | Input transcription model |
| `transcription_language` | `null` | Automatic detection; use `en` or `zh` to specify a language |
| `conversation_timeout` | `120` | Maximum conversation duration, in seconds |
| `silence_timeout` | `8` | User silence timeout, in seconds |
| `post_response_timeout` | `6` | Wait after a completed response, in seconds |
| `timer_alert_volume` | `0.25` | Chime volume, from 0 to 1 |
| `timer_alert_seconds` | `10` | Chime duration, from 1 to 30 seconds |
| `timer_store_path` | `data/timers.json` | Persistent timer storage |

Keep the API key in `.env`, not in a config you share. A shell `OPENAI_API_KEY` overrides `.env`; `.env` overrides the optional JSON key. `.env` is parsed as data, never executed as shell code.

The English [sherpa-onnx keyword model](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html) uses its bundled tokenizer for wake phrases containing English letters, apostrophes, and spaces. After the verified first download, it runs offline from `models/`. An optional `wake_word_model_dir` changes the model directory. Relative model and timer paths resolve from the repository root.

## Troubleshooting

Start with `./run.sh --doctor`. It checks Python, imports, FFmpeg, prompt files, the selected wake-model cache, and whether a key is configured. It makes no network requests and opens no audio devices; a configured key still needs valid OpenAI access.

| Problem | What to do |
| --- | --- |
| Python 3.12 is missing | Install uv using the instructions above, then rerun setup. |
| Existing `venv` has the wrong Python or is broken | Move it aside (for example, `mv venv venv.bak` if that backup does not exist), then run `./run.sh --setup-only`. |
| `portaudio.h` is missing during installation | Install `portaudio` with Homebrew or `portaudio19-dev` on Debian/Ubuntu. |
| `Python.h` is missing | Install `python3.12-dev` for system Python, or use uv to create a fresh environment. |
| A Python dependency is missing | Rerun `./run.sh --setup-only` to reinstall missing requirements. |
| No microphone input | Allow microphone access for your terminal and check the system's default input device and level. |
| “Hi Taco” is missed | Say it clearly, reduce speaker volume, and check `wake_keywords`. Adjust the threshold cautiously. |
| Model download or checksum fails | Check the connection and rerun setup with the same `--config`. Unverified downloads are not installed. |
| OpenAI rejects the key or session | Check the key, project access, model availability, and API usage limits in your OpenAI account. |
| Music search/download fails | Check connectivity and FFmpeg. YouTube availability can vary; try another track. |
| Timer did not sound on time | Keep the app running and the computer awake; check the timer status for missed alerts. |

Application logs rotate in `logs/`. Logs can contain transcripts; review them before sharing a bug report. Do not share `.env`.

## Development and tests

```bash
./run.sh --setup-only
make dev-deps
make check
make benchmark
```

`make check` compiles code, runs Ruff, and runs the offline pytest suite with audio and network boundaries mocked. GitHub Actions runs the same checks on Python 3.12. `make benchmark` measures local timer, greeting, and music-start overhead without devices or an API key. See the [performance results](docs/performance-sweep.md) and [code review](docs/code-review.md).

For an optional **live headless test**, provide mono PCM16 recordings: a 16 kHz wake phrase and 24 kHz `play.wav`, `pause.wav`, `resume.wav`, and `stop.wav` files. This sends the command audio to OpenAI, searches YouTube Music, and uses silent SDL output. It needs the normal API key and can incur API usage.

```bash
venv/bin/python tests/headless_smoke.py \
  --wake-audio /path/to/hi-taco.wav \
  --commands-dir /path/to/commands \
  --report tmp/headless-smoke.json
```

Add `--background-audio /path/to/music-16k.wav --snr-db 5` to test wake detection in a digital music mix. This verifies controls and cleanup, but does not reproduce physical room acoustics. Keep recordings and reports outside Git.

Runtime code lives in `src/`; configuration in `config/`; prompt audio in `audio/`. The runner and `src/setup_assistant.py` handle installation checks. Generated `venv/`, `models/`, `music_cache/`, `data/`, and logs stay local.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance. Licensed under the [MIT License](LICENSE).
