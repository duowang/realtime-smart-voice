# Security and safety review — 2026-09-22

Reviewed the runtime, setup/runner, tool handlers, persistent data, downloads, CI, dependencies, Git history, and GitHub repository controls. Baseline: `a5af7bf`. No live microphone, speaker, OpenAI conversation, or music playback was used for this review. Scanner artifacts stay in ignored `tmp/security-sweep/`.

## Findings and fixes

| Finding | Change |
| --- | --- |
| Transcripts, model responses, search queries, and tool arguments were persisted by default; ordinary log permissions depended on the shell's umask. | Content events are omitted by default. Explicit `log_conversation_content: true` enables them. The log directory is owner-only; active and newly rotated files are owner-readable/writable only. Configured API keys and OpenAI-shaped keys are redacted, control characters removed, and message lengths bounded. Old logs are not deleted. |
| Artwork URLs from search results/cache were fetched without a host restriction; redirects, buffered bodies, and arbitrary Pillow formats increased exposure. | HTTPS YouTube/Google image hosts only, no credentials/nonstandard ports/redirects, an 8 MiB streamed-byte cap, a 16-million-pixel cap, and JPEG/PNG/WebP only. Cache identifiers are validated. Failed downloads preserve existing files. Socket timeouts and an elapsed-time check between chunks limit normal recovery. |
| Streaming assistant text and timer labels could emit terminal control sequences. | Terminal output is sanitized; new timer labels must be printable. Existing stored labels are sanitized when displayed. |
| Downloads lacked application-level size limits. | Wake-model archives are capped at 64 MiB before SHA-256 verification/extraction. Music rejects live streams and known durations over two hours; source downloads and converted MP3s are capped at 200 MiB. Playlists remain disabled. |
| Music calls tolerated unknown arguments and unbounded queries. | Explicit argument allowlists and a 300-character query limit complement the model-facing schemas. Existing strict timer argument, duration, ambiguity, count, and persistence controls remain in place. Model instructions treat returned metadata as untrusted data. |
| Minimum requirements permitted known vulnerable releases, despite the installed environment being current. | Raised SentencePiece to 0.2.2, python-dotenv to 1.2.2, Requests to 2.33.0, and Pillow to 12.3.0. These are package-level advisory findings, not claims that every affected code path was reachable in this application. |
| CI used mutable action tags and had no recurring dependency/secret scan. | Actions are pinned to verified commit SHAs, checkout credentials are not persisted, permissions remain read-only, and jobs time out. Added pip-audit, Bandit medium/high checks, checksum-pinned Gitleaks history scanning, a weekly run, and Dependabot update configuration. These workflow changes take effect when pushed. |
| Public security reporting and dependency alerts were disabled. | Enabled and verified GitHub private vulnerability reporting and Dependabot alerts. Added `SECURITY.md`. Existing secret scanning and push protection were already enabled. |

Personal JSON configs (except the shipped default), common recording formats, local state, logs, caches, and virtual environments are ignored by Git. Ignore rules do not remove files already tracked in history.

## Verification

- Gitleaks 8.30.1 scanned all 14 reachable commits across local refs with redacted output: **no detected secrets**. Remote branch/tag inspection confirmed only `main`, matching the audited baseline. The only historical config/environment paths were `config/config.json` and `.env.example`; no tracked runtime logs, timers, or music cache were found. The local `.env` already had owner-only permissions.
- pip-audit 2.10.1 checked the 40 installed packages: **no known advisories**. A separate scan of the old direct dependency minimums flagged four packages; rechecking the raised minimums found **none**. The minimum scan intentionally excludes transitive dependencies; the installed-environment scan includes them.
- Bandit 1.9.4 found **no medium/high issues**. Its three low-severity warnings concern importing `subprocess` and the fixed `tmux show -gv allow-passthrough` command. That call has a one-second timeout, uses an argument list, receives no voice/model input, and does not invoke a shell. It relies on the user's trusted PATH.
- `make check`: **213 tests passed**, compilation and Ruff clean. The tests cover rejected thumbnail hosts/redirects, oversized bodies and images, parser restrictions, cache traversal, log privacy/redaction/rotation, terminal controls, tool argument boundaries, and model download limits, alongside wake detection, music controls, timers, and shutdown. Ten cached synthetic clips also passed through the real wake detector without opening audio devices. The live headless harness now observes tool names without requiring argument/transcript logging; live API testing was not rerun.
- A separate Gitleaks scan of the final public-file snapshot (including new files) found **no detected secrets**. Workflow YAML, pinned action references, shell syntax, and installed dependency compatibility were checked locally. The first Linux CI run passed all 213 tests and flagged the hosted Python environment's old pip 25.0.1; CI now upgrades pip before installing dependencies, and security tooling requires pip 26.2 or newer.

To repeat Python checks after setup:

```bash
make dev-deps security-deps
make check audit
```

`pip-audit` queries public advisory services with package names and versions. Gitleaks scans source/history locally. Raw reports, secrets, audio, and source code are not submitted to an external scanner by these commands.

## Remaining limits

- This is a code review plus automated checks, not a security certification. Pattern scanners can miss secrets, advisory databases can lag, and native/system packages are outside pip-audit's coverage. Git history scanning covers reachable local refs, not deleted remote refs, forks, GitHub issues, or Actions artifacts.
- Wake phrases provide convenience, not identity or consent verification. Bystanders and speaker audio can trigger low-impact tools or incur API usage. There is no voice authentication, acoustic echo cancellation, or spending cap in the app.
- The WebSocket receive loop still awaits music search/download work. Spoken interruption can be delayed until that work finishes or the conversation timeout expires; Ctrl+C requests shutdown. Cancelling a Python task cannot forcibly terminate every blocking native/network operation.
- Metadata instructions are a defense in depth measure, not a prompt-injection guarantee. The executable tool surface remains limited to music and countdown timers; stronger authorization is required before adding messaging, purchases, arbitrary file access, or device controls.
- The music cache has per-download limits but no aggregate quota/automatic eviction. Config files and existing local model/cache files are trusted local inputs. Do not run from a directory writable by untrusted users.
- Runtime requirements remain version ranges rather than a hash-locked environment. The new CI checks the installed resolution; minimum versions should be re-audited when changing dependency policy. Keep FFmpeg, SDL/PortAudio, and operating-system libraries patched separately.
- `main` has no branch protection. This review preserves the requested direct-to-main workflow; required reviews/status checks would need a workflow decision.

## Sources checked on 2026-09-22

- [Pillow security guidance](https://pillow.readthedocs.io/en/stable/handbook/security.html) and [12.3.0 security fixes](https://pillow.readthedocs.io/en/stable/releasenotes/12.3.0.html): image parser and resource limits, patched dependency floor.
- [SentencePiece 0.2.2 release](https://github.com/google/sentencepiece/releases/tag/v0.2.2): tokenizer model validation and other hardening.
- [python-dotenv changelog](https://github.com/theskumar/python-dotenv/blob/main/CHANGELOG.md) and [Requests security history](https://github.com/psf/requests/blob/main/HISTORY.md): dependency minimum changes.
- [pip-audit](https://github.com/pypa/pip-audit) and [Gitleaks](https://github.com/gitleaks/gitleaks): scanner capabilities and limitations.
- [GitHub repository security quickstart](https://docs.github.com/en/code-security/getting-started/quickstart-for-securing-your-repository) and [private reporting configuration](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository): repository controls and reporting.
