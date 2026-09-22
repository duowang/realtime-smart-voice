#!/usr/bin/env python3
"""Generate the greeting WAV, or compare the original six TTS voices."""

import argparse
import sys
from pathlib import Path

from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from configuration import get_api_key, load_config  # noqa: E402

VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")


def generate_greetings(compare: bool = False) -> list[Path]:
    config = load_config()
    output_dir = PROJECT_ROOT / "audio"
    output_dir.mkdir(exist_ok=True)
    paths = []
    with OpenAI(api_key=get_api_key(config)) as client:
        for voice in VOICES if compare else ("shimmer",):
            response = client.audio.speech.create(
                model="tts-1-hd",
                voice=voice,
                input="Hi there!",
                response_format="wav",
                speed=1.0,
            )
            path = output_dir / (f"hi_there_{voice}.wav" if compare else "hi_there.wav")
            # Publish only a complete response; a failed API request leaves the old greeting intact.
            path.write_bytes(response.content)
            paths.append(path)
            print(f"Saved {path}")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="Generate a WAV for each voice")
    args = parser.parse_args()
    try:
        generate_greetings(args.compare)
    except Exception as error:
        print(f"Audio generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
