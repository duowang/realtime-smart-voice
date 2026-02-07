# Repository Guidelines

## Project Structure & Module Organization
The assistant runtime lives in `src/`, with `realtime_voice_assistant.py` orchestrating wake-word detection, OpenAI realtime streaming, and music control via `music_commands.py`, `realtime_voice_client.py`, and `wake_word_detector.py`. `youtube_music_player.py` handles audio download/playback, thumbnail caching (hi-res album art stored as `*_thumb.jpg`), and ANSI true-color terminal rendering. Configuration defaults sit in `config/config.json`, audio prompts in `audio/`, and cached media (audio + thumbnails) under `music_cache/`. Logs land in `logs/`, while wake-word templates for Picovoice ship in `wake_word_templates/`. Use `run.sh` for end-to-end setup, and keep large assets out of Git—store them in `audio/` or external storage.

## Build, Test, and Development Commands
- `python3 -m venv venv && source venv/bin/activate` — create/enter the project virtualenv.
- `pip install -r requirements.txt` — install runtime dependencies (OpenAI, Porcupine, YouTube Music helpers, Pillow for thumbnails).
- `./run.sh` — bootstrap dependencies, load `.env`, and launch the realtime assistant.
- `python src/realtime_voice_assistant.py` — run the core loop when the environment is already prepared.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indents, snake_case functions, and CapWords classes. Prefer explicit type hints (mirroring existing constructors) and module-level logging over prints. Keep configuration constants in JSON or top-level module scopes; avoid sprinkling magic numbers. Before pushing, run `python -m compileall src` to catch syntax issues and ensure docstrings explain tricky asynchronous flows.

## Testing Guidelines
Automated tests are not yet checked in—add them under `tests/` using `pytest` or the standard `unittest` runner. Focus on deterministic components such as wake-word thresholds and music command parsing; mock audio hardware and network traffic. Run `python -m unittest discover -s tests` (or `pytest`) locally and include coverage notes in PRs. Smoke-test the voice loop with `./run.sh` and a short “Hi Taco” interaction before merging.

## Commit & Pull Request Guidelines
Recent history favors short, present-tense commit subjects (for example, `add audio file`, `make wakup detection less sensitive`). Group related changes and avoid WIP commits. Each PR should describe user-facing impact, note how you validated the change, and link relevant issues. Attach screenshots or terminal logs for audio or configuration tweaks. Request review from a maintainer before merging and wait for CI/test sign-off.

## Environment & API Keys
Store secrets in `.env` (auto-copied from `.env.example`) and never commit keys. Ensure `OPENAI_API_KEY` and `PORCUPINE_ACCESS_KEY` are set before running. Adjust model, wake-word, and audio thresholds through `config/config.json`; keep defaults conservative to prevent false activations. If you rotate keys, update the shared vault and the configuration template promptly.
