# Development notes

Follow [AGENTS.md](AGENTS.md) for repository conventions and [README.md](README.md) for setup and configuration. Python 3.12 is required.

## Architecture

- `realtime_voice_assistant.py` owns the shared music handler, wake detector, Realtime client, logging handler, and signal handlers. Wake detection and conversation alternate because they use different microphone sample rates.
- `wake_word_detector.py` feeds 16 kHz PCM16 into the pinned English sherpa-onnx model. Its SentencePiece tokenizer must match the model. `wake_word_model.py` verifies the downloaded archive before publishing allowlisted regular files.
- `realtime_voice_client.py` uses the GA OpenAI Realtime WebSocket protocol and 24 kHz mono PCM16. It waits for session configuration acknowledgement before opening the microphone. Each conversation owns and awaits its input, event receiver, playback, silence monitor, and stop tasks.
- `audio_io.py` runs short blocking device reads/writes in worker threads. Cancellation waits for the in-flight operation before closing its stream. Speaker output is queued in 20 ms chunks; interruption drops queued chunks and sends `conversation.item.truncate`.
- `music_commands.py` validates tool arguments and returns structured results. Calls execute from `response.done`, once all arguments are complete. A successful play returns to wake detection without asking the model to speak over music.
- `youtube_music_player.py` controls pygame's existing playback engine. There is no extra Python playback thread or playlist queue. Paused tracks remain loaded. Explicit pause clears the conversation auto-resume flag; stop invalidates pending search/download results.
- `album_art.py` handles thumbnail download, image validation, and optional iTerm2/tmux or ANSI display. Redirected output skips images.
- `configuration.py` centralizes paths, timeout validation, and dotenv parsing. Shell environment takes precedence over `.env`, then the optional JSON API key.

## Validation

Run `make dev-deps` once, then `make check` for compilation, Ruff (including tests and the audio generator), and offline pytest checks. Use `bash -n run.sh` after runner changes. CI runs these on Linux; never require credentials or physical audio devices in unit tests.

For live integration, follow the headless command in README. It uses the real keyword model, OpenAI, YouTube Music, and SDL's silent mixer, with prerecorded audio replacing PortAudio devices. Keep personal recordings, reports, cache, logs, and keys out of Git. Do not equate digital audio tests with room-acoustic validation.

## Invariants to preserve

- Cancel and await conversation workers before closing audio devices or sockets.
- The assistant owns shared music cleanup; a Realtime client only cleans a player it created itself.
- Shutdown must not resume conversation-paused music.
- An explicit pause persists across subsequent conversations.
- Pygame reports `get_busy() == False` while paused; this does not mean the track ended.
- Never report play success until mixer load/play succeeds, or start a stale download after stop.
- Keep network and audio failures visible, and let the outer loop recover to wake detection after a failed conversation.
- The conversation timeout must cover the active work, including connection setup and tools.
- There is no acoustic echo cancellation. Loud music can mask the wake word.
