# Security policy

Security fixes target the latest `main` branch. Update both the repository and its dependencies before reporting an issue.

## Report a vulnerability privately

Use [GitHub's private vulnerability reporting](https://github.com/duowang/realtime-smart-voice/security/advisories/new). Include the affected revision, platform, prerequisites, and a minimal reproduction with dummy data. Do not put credentials, recordings, private logs, or exploit details in a public issue. If a credential was exposed, revoke and replace it; removing it from the latest commit does not remove older copies.

## Trust and safety boundaries

- Run this as your own unprivileged local account. Voice commands can play music and manage timers; they cannot execute shell commands, read arbitrary files, or control other devices.
- Wake detection is local, but it is **not speaker authentication**. Anyone nearby, a recording, or audio from a speaker may activate the assistant and issue commands. After waking, microphone audio is sent to OpenAI until that conversation ends. Stop the app with Ctrl+C when privacy matters.
- Timers require the app to remain running and the computer awake. They are not suitable as the sole reminder for medication, emergencies, or other critical deadlines.
- Keep keys in `.env`, and keep private configs and recordings out of Git. Review diagnostic files before sharing them. Timer labels and music history are stored locally in ignored `data/` and `music_cache/` directories.
- Conversation-content logging is off by default. Enabling `log_conversation_content` saves transcripts and tool arguments locally. Existing logs from older versions are not automatically erased; review or remove them locally if no longer needed.
- Treat downloads, cached models, Python dependencies, FFmpeg, and native audio/image libraries as trusted software inputs. Keep OS packages current. Python advisory scanners do not certify these binaries or detect every vulnerability.

See [the security review](docs/security-review.md) for the audited scope, fixes, verification, and remaining limitations.
