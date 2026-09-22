"""Optional terminal album art; independent of music playback state."""

import asyncio
import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from PIL import Image


class AlbumArt:
    def __init__(self, cache_dir: Path, log_function):
        self.cache_dir = cache_dir
        self._log = log_function
        self._tmux_passthrough = None
        self._logged_tmux_passthrough_hint = False

    @staticmethod
    def is_visible() -> bool:
        return sys.stdout.isatty() and os.getenv("TERM") != "dumb"

    async def download(self, thumbnail_url: str, song_id: str) -> str | None:
        """Validate images and replace the cache only after a complete download."""
        path = self.cache_dir / f"{song_id}_thumb.jpg"

        def fetch():
            if path.is_file():
                try:
                    with Image.open(path) as image:
                        if image.width >= 1000:
                            return str(path)
                except (OSError, ValueError):
                    pass
            with requests.get(thumbnail_url, timeout=10) as response:
                response.raise_for_status()
                with tempfile.TemporaryDirectory(dir=self.cache_dir) as staging:
                    downloaded = Path(staging) / "download"
                    downloaded.write_bytes(response.content)
                    with Image.open(downloaded) as image:
                        image.verify()
                    converted = Path(staging) / "thumbnail.jpg"
                    with Image.open(downloaded) as image:
                        image.convert("RGB").save(converted, format="JPEG")
                    converted.replace(path)
            return str(path)

        try:
            return await asyncio.to_thread(fetch)
        except Exception as error:
            self._log("THUMB_ERROR", f"Cannot download album art: {error}")
            return None

    @staticmethod
    def _is_iterm2() -> bool:
        """Check whether output terminal is iTerm2."""
        term_program = os.getenv("TERM_PROGRAM", "")
        lc_terminal = os.getenv("LC_TERMINAL", "")
        return (
            term_program == "iTerm.app"
            or lc_terminal.lower() == "iterm2"
            or bool(os.getenv("ITERM_SESSION_ID"))
        )

    def _tmux_allows_passthrough(self) -> bool:
        """Check tmux allow-passthrough setting (cached)."""
        if not os.getenv("TMUX"):
            return True

        if self._tmux_passthrough is not None:
            return self._tmux_passthrough

        try:
            result = subprocess.run(
                ["tmux", "show", "-gv", "allow-passthrough"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            value = result.stdout.strip().lower()
            self._tmux_passthrough = value in {"on", "all"}
        except Exception:
            self._tmux_passthrough = False

        return self._tmux_passthrough

    def _emit_iterm2_inline_image(self, image_path: str, width_percent: int = 70):
        """Emit iTerm2 inline image escape sequence.

        Uses tmux passthrough when running inside tmux.
        """
        with open(image_path, "rb") as image_file:
            image_b64 = base64.b64encode(image_file.read()).decode("ascii")

        name_b64 = base64.b64encode(os.path.basename(image_path).encode("utf-8")).decode("ascii")
        payload = (
            f"\033]1337;File=name={name_b64};inline=1;preserveAspectRatio=1;"
            f"width={width_percent}%;height=auto:{image_b64}\a"
        )

        # iTerm2 image escape codes need tmux passthrough wrapping.
        if os.getenv("TMUX"):
            tmux_payload = payload.replace("\033", "\033\033")
            sys.stdout.write(f"\033Ptmux;{tmux_payload}\033\\")
        else:
            sys.stdout.write(payload)
        sys.stdout.flush()

    def _render_thumbnail_iterm2(self, thumb_path: str, title: str, artist: str) -> bool:
        """Render thumbnail via iTerm2's native inline image protocol."""
        if not self._is_iterm2():
            return False

        if os.getenv("TMUX") and not self._tmux_allows_passthrough():
            if not self._logged_tmux_passthrough_hint:
                self._logged_tmux_passthrough_hint = True
                self._log(
                    "THUMB_INFO",
                    "tmux inline image passthrough is off. Enable with: set -g allow-passthrough on",
                )
            return False

        try:
            print("")  # blank line before
            self._emit_iterm2_inline_image(thumb_path, width_percent=70)
            print(f"  \033[1m{title}\033[0m - {artist}")
            print("")  # blank line after
            return True
        except Exception as e:
            self._log("THUMB_ERROR", f"Failed to render iTerm2 image: {e}")
            return False

    def render(self, thumb_path: str, title: str, artist: str):
        """Render a thumbnail image in the terminal using ANSI colored half-block characters."""
        if not self.is_visible():
            return
        title = "".join(character for character in title if character.isprintable())
        artist = "".join(character for character in artist if character.isprintable())
        try:
            # Prefer native iTerm2 inline rendering for much higher visual quality.
            if self._render_thumbnail_iterm2(thumb_path, title, artist):
                return

            with Image.open(thumb_path) as source:
                img = source.convert("RGB")

            try:
                term_size = os.get_terminal_size()
                term_width = term_size.columns
                term_height = term_size.lines
            except OSError:
                term_width = 80
                term_height = 24

            aspect = img.height / img.width
            # 50% of terminal width
            width_from_cols = int(term_width * 0.5)
            # 50% of terminal height: each char row = 2 pixel rows
            height_from_rows = int(term_height * 0.5)
            width_from_height = int(height_from_rows * 2 / aspect)
            # Use the smaller constraint so it stays compact in upper-left
            new_width = max(1, min(width_from_cols, width_from_height))

            new_height = max(2, int(new_width * aspect))
            # Make height even for half-block pairing
            if new_height % 2 != 0:
                new_height += 1
            img = img.resize((new_width, new_height), Image.LANCZOS)
            pixels = img.load()

            lines = []
            lines.append("")  # blank line before
            for y in range(0, new_height, 2):
                row = ""
                for x in range(new_width):
                    # Top pixel -> foreground, bottom pixel -> background
                    r1, g1, b1 = pixels[x, y]
                    if y + 1 < new_height:
                        r2, g2, b2 = pixels[x, y + 1]
                    else:
                        r2, g2, b2 = r1, g1, b1
                    # Use upper half block with fg=top, bg=bottom
                    row += f"\033[38;2;{r1};{g1};{b1}m\033[48;2;{r2};{g2};{b2}m\u2580"
                row += "\033[0m"
                lines.append(row)
            lines.append(f"  \033[1m{title}\033[0m - {artist}")
            lines.append("")  # blank line after

            output = "\n".join(lines)
            print(output)
        except Exception as e:
            self._log("THUMB_ERROR", f"Failed to render thumbnail: {e}")
