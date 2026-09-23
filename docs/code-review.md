# Code review and refactor — September 2026

Reviewed every Python source and test file, the shell runner, configuration, dependency constraints, Makefile, ignore rules, and repository documentation. The prerecorded prompts were removed after this review; the assistant now generates a short wake cue.

## Findings addressed

| Area | Previous problem | Result |
| --- | --- | --- |
| Conversation timeout | The timeout wrapped a wait that ran only after the conversation had already finished. | It covers the wake cue, connection setup, tools, and the active conversation. |
| Async lifecycle | Worker exceptions were swallowed; sibling tasks could remain running after a failure. | Any worker finishing ends the session. All workers are cancelled and awaited before devices and the socket close. Repeated cancellation cannot skip finalization. |
| Audio I/O | Blocking microphone reads and speaker writes stalled the event loop. | Short device operations run in workers, with cancellation deferred until native I/O completes. Speaker playback has its own bounded queue. |
| Interruption | Barge-in changed a flag but left queued audio and unheard server context intact. | Queued chunks are discarded and the response is truncated, including an interruption before its first chunk plays. |
| Tool routing | Function output could trigger a new response before the preceding response finished. Invalid arguments could become an unintended empty command. | Completed calls execute from `response.done`; invalid argument types return an error. Successful play returns to wake detection. |
| Silence detection | Raw microphone volume counted music/noise as user activity. A heuristic could discard valid short utterances. | Timeouts use server speech events and monotonic time. Active output and tools do not trigger inactivity shutdown. The overall timeout remains a bound. |
| Music playback | A second Python thread raced with stop, could overwrite newer state, and reported success before mixer load/play succeeded. | Pygame owns playback. Application state stays on the event loop; success follows actual load/play. A generation invalidates stale searches and downloads. |
| Pause and stop | Paused tracks could be mistaken for completed tracks. Conversation auto-resume could undo a user pause. | Paused tracks stay loaded; explicit pause clears auto-resume. Stop unloads the track and invalidates pending play requests. Shutdown does not resume music. |
| Cache | Direct writes could leave partial audio, metadata, or thumbnails. Malformed metadata could break later operations. | Downloads stage privately and publish complete files atomically; metadata and thumbnails preserve existing files on failure. Invalid metadata entries are ignored. Cancelled downloads receive a cooperative stop signal. |
| Resource ownership | Shared music cleanup ran twice; prompt failures leaked streams; partial startup leaked components. | Shared resources have one owner. Cleanup attempts all components even after a failure. Wake-cue streams close in `finally`. |
| Configuration and runner | Missing/broken JSON silently became defaults; `.env` was executed as shell; a custom relative config broke after `cd src`. | Invalid config fails clearly. Python handles dotenv, and the runner stays at the project root. Removed unused legacy configuration fields. |
| Tooling and documentation | Ruff targeted Python 3.9, ignored tests/tools, and dependencies allowed an incompatible WebSocket API. Docs claimed queue/reconnection features that did not exist. | Python 3.12, expanded checks, corrected WebSocket minimum, scoped test doubles, Linux CI, and architecture documentation matching the implementation. |
| Logging | Handlers were discarded without closing and log files grew without a bound. | Owned rotating handlers; rotated logs are ignored by Git. |

Terminal album art, configuration loading, and device I/O now have focused modules. Music commands share one validation/error boundary instead of repeating broad exception handlers for every action.

## Validation

- `make check`: compilation, Ruff across source/tests/generator, and 89 offline tests passed on macOS, Python 3.12 at the time of this review. The generator was later removed.
- `bash -n run.sh`, `./run.sh --setup-only`, `./run.sh --help`, both Python CLI help paths, and `pip check` passed.
- Live headless test: real sherpa model, OpenAI Realtime, YouTube Music search, cached MP3 decoding, and SDL silent playback passed wake → play → wake → pause → wake → resume → wake → stop → wake. Music mixed into active-playback wake input at +5 dB speech/music ratio. Pause kept the mixer clock stationary; resume advanced it; stop unloaded the track. All audio streams and the mixer closed.
- Personal input recordings and machine-specific JSON reports remain outside Git. The reusable harness is `tests/headless_smoke.py`.
- GitHub Actions runs the offline suite without secrets or physical audio hardware. Live API testing remains explicit.

The event handling was checked against the [OpenAI Realtime conversation guide](https://developers.openai.com/api/docs/guides/realtime-conversations). The WebSocket dependency bound follows the documented [14.0 import/API transition](https://websockets.readthedocs.io/en/stable/howto/upgrade.html).

## Remaining limits

- Headless testing does not validate real microphone/speaker latency, room echo, or acoustic cancellation. Loud music can still mask the wake phrase; the detector model and sensitivity were preserved in this refactor.
- Music has one track and no playlist queue. Skip stops the current track.
- Search/download services remain external dependencies. Cancellation cannot instantly interrupt a blocking network request or an ffmpeg operation; finite network timeouts and download progress checks bound normal recovery. A cancelled or superseded operation cannot start playback afterward.
- Playback truncation tracks audio submitted to PortAudio, with device buffering adding a small timing uncertainty.
- Linux CI exercises mocked hardware. Raspberry Pi and real Linux audio hardware were not tested locally.
