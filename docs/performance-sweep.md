# Performance sweep — September 22, 2026

The baseline was `027cfe6` on macOS arm64 with Python 3.12. This sweep targets
measured local overhead without changing the wake model, sensitivity, audio frame
sizes, OpenAI model, or conversational behavior.

## Measurements

`tests/performance_sweep.py` uses five samples per measurement and reports medians.
Timer samples each perform 1,000 polls with 100 completed history records. Greeting
samples decode the real prompt into a mock device. Music samples use a cached-file
placeholder, a mock mixer, and a simulated 200 ms artwork fetch. No network or
physical audio device is used. The idle scheduler is observed separately for 1.1 s.

| Local measurement | Before | After |
| --- | ---: | ---: |
| Timer poll with 100 history records | 227.14 µs | 48.26 µs |
| Idle scheduler ticks in 1.1 s, including startup | 5 | 1 |
| Greeting overhead, excluding device playback | 306.64 ms | 2.42 ms |
| Cached music call → mixer play, with 200 ms artwork fetch | 202.66 ms | 0.13 ms |
| Cached music call → successful result, same fixture | 205.60 ms | 0.84 ms |

These are isolated application measurements, not end-to-end speech latency or a
claim that hardware plays audio in fractions of a millisecond. Small timings vary
with machine load. The substantive changes remove a fixed delay and a network
dependency from the critical path, and eliminate periodic timer work while idle.
`cProfile` identified deep copying as the dominant CPU work in the original timer
benchmark; the scheduler no longer copies unchanged history.

## Changes and invariants

- **Greetings:** removed the unconditional 300 ms sleep after writing each prompt.
  PortAudio's stop operation already drains queued output before returning, per
  the [official stream API](https://portaudio.com/docs/v19-doxydocs/portaudio_8h.html)
  (checked September 22, 2026). Draining now runs through the cancellation-safe
  audio worker so the event loop remains available. The prompt remains marked
  active until draining finishes; cancellation cannot terminate its device early.
- **Timers:** sleep until the earliest deadline or a committed state change.
  The 250 ms tick is retained only while an alert is ringing or waiting for speech
  to finish. Published timer records are immutable by convention: operations copy
  only changed entries, then publish after the atomic disk write succeeds. Failed
  saves preserve memory and disk state. Shutdown still joins pending transactions.
  Allowed arguments come from the existing tool schemas instead of a second map
  rebuilt for every request.
- **Music:** start playback and return the tool result before fetching optional
  artwork. The player owns that task; stop, replacement, and application shutdown
  cancel it. Generation checks discard stale results, including a newer play
  request arriving while old artwork is being cancelled. Artwork errors cannot
  turn successful music playback into a failure.
- **Shutdown:** `AsyncExitStack` replaces nested cleanup blocks while retaining
  timer → alert → voice → wake detector → music → logging order. Music's async
  close joins artwork before releasing the mixer and logging owner; synchronous
  cleanup remains available for partial construction failures.

## Validation

- `make check`: compilation, Ruff, and **144 offline tests passed**. New cases cover
  timer rescheduling and real deadline expiry, failed state-change transactions,
  delayed/cancelled artwork, overlapping play requests, prompt-drain cancellation,
  alert activity reporting, and cleanup after component failure.
- A local integration replay passed all **nine wake/play/pause/resume/stop checks**
  using the real cached sherpa model, cached MP3 decoding, and SDL silent playback.
  Active-playback wake input mixed recorded speech with music at +5 dB.
  OpenAI responses and music search were simulated, with networking disabled.
  All streams, mixer resources, and async tasks were closed afterward.
- The live headless test also passed all **nine checks** with real OpenAI Realtime
  command routing, YouTube Music search, the sherpa model, and cached MP3 playback.
  Wake input during playback included music at +5 dB speech/music ratio. Playback
  advanced during play/resume, remained stationary during pause, and unloaded on
  stop. Wake detection worked afterward without restarting music. All audio
  streams and the mixer closed cleanly. The report is saved locally as
  `tmp/performance-sweep/headless-music.json`.
- Physical room acoustics, device latency, Linux audio, and Raspberry Pi hardware were not tested.
  Personal recordings and machine-specific replay reports remain ignored.

## Reproduce

```bash
make check
make benchmark
# Optional CPU profile, separate from unprofiled timing measurements:
venv/bin/python -m cProfile -o tmp/performance-sweep/current.pstats \
  tests/performance_sweep.py --output tmp/performance-sweep/profile.json
```

## Remaining performance limits

Connection setup, model response latency, music search, and uncached audio
downloads still depend on external services. Tool calls currently execute inside
the Realtime receive loop, so slow search/download work can delay incoming voice
events. Moving tools into a separate worker needs explicit response ordering and
interruption semantics; it is not part of these local optimizations.

Terminal image rendering still executes on the event loop after the image is
ready. Artwork fetch cancellation prevents stale display but cannot instantly stop
an already running HTTP worker; its existing timeout still applies. Cancelling the
async task also cannot prevent that worker from finishing a cache write. No worker
can start music playback.
