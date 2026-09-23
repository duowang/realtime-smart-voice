"""Optional terminal album art; independent of music playback state."""

import asyncio
import base64
import io
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image

MAX_THUMBNAIL_BYTES = 8 * 1024 * 1024
MAX_THUMBNAIL_PIXELS = 16_000_000
THUMBNAIL_HOSTS = ("ytimg.com", "ggpht.com", "googleusercontent.com")
IMAGE_FORMATS = ("JPEG", "PNG", "WEBP")
NATIVE_IMAGE_COLUMNS = 32
NATIVE_IMAGE_ROWS = 16
KITTY_CHUNK_SIZE = 4096
KITTY_IMAGE_PIXELS = 640


def validate_thumbnail_url(url: str) -> None:
    """Only fetch provider artwork; arbitrary hosts and redirects are unnecessary."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not any(host == domain or host.endswith("." + domain) for domain in THUMBNAIL_HOSTS)
    ):
        raise ValueError("Artwork must use an HTTPS YouTube/Google image URL")


def check_image_size(image: Image.Image) -> None:
    if image.width * image.height > MAX_THUMBNAIL_PIXELS:
        raise ValueError("Artwork exceeds the pixel limit")


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
        if not isinstance(song_id, str) or not re.fullmatch(r"[0-9a-f]{12}", song_id):
            return None
        path = self.cache_dir / f"{song_id}_thumb.jpg"

        def fetch():
            validate_thumbnail_url(thumbnail_url)
            if path.is_file() and path.stat().st_size <= MAX_THUMBNAIL_BYTES:
                try:
                    with Image.open(path, formats=IMAGE_FORMATS) as image:
                        check_image_size(image)
                        if image.width >= 1000:
                            return str(path)
                except (OSError, ValueError):
                    pass
            deadline = time.monotonic() + 30
            with requests.get(
                thumbnail_url, timeout=(5, 10), stream=True, allow_redirects=False
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("Artwork redirects are not allowed")
                if int(response.headers.get("Content-Length", "0")) > MAX_THUMBNAIL_BYTES:
                    raise ValueError("Artwork exceeds the download limit")
                with tempfile.TemporaryDirectory(dir=self.cache_dir) as staging:
                    downloaded = Path(staging) / "download"
                    size = 0
                    with downloaded.open("wb") as output:
                        for chunk in response.iter_content(64 * 1024):
                            size += len(chunk)
                            if size > MAX_THUMBNAIL_BYTES or time.monotonic() > deadline:
                                raise ValueError("Artwork exceeds the download size/time limit")
                            output.write(chunk)
                    with Image.open(downloaded, formats=IMAGE_FORMATS) as image:
                        check_image_size(image)
                        image.verify()
                    converted = Path(staging) / "thumbnail.jpg"
                    with Image.open(downloaded, formats=IMAGE_FORMATS) as image:
                        check_image_size(image)
                        image.convert("RGB").save(converted, format="JPEG")
                    if converted.stat().st_size > MAX_THUMBNAIL_BYTES:
                        raise ValueError("Converted artwork exceeds the size limit")
                    converted.replace(path)
            return str(path)

        try:
            return await asyncio.to_thread(fetch)
        except Exception as error:
            self._log("THUMB_ERROR", f"Cannot download album art: {error}")
            return None

    @staticmethod
    def _is_iterm2() -> bool:
        """Check terminals that support iTerm2's inline image protocol."""
        term_program = os.getenv("TERM_PROGRAM", "").lower()
        lc_terminal = os.getenv("LC_TERMINAL", "")
        return (
            term_program in {"iterm.app", "wezterm", "vscode"}
            or lc_terminal.lower() == "iterm2"
            or bool(os.getenv("ITERM_SESSION_ID"))
        )

    @staticmethod
    def _is_kitty_graphics() -> bool:
        """Check terminals known to implement the Kitty graphics protocol."""
        term_program = os.getenv("TERM_PROGRAM", "").lower()
        term = os.getenv("TERM", "").lower()
        return (
            term_program in {"ghostty", "kitty"}
            or term in {"xterm-ghostty", "xterm-kitty"}
            or bool(os.getenv("KITTY_WINDOW_ID"))
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

    def _emit_iterm2_inline_image(self, image_path: str, width_columns: int):
        """Emit iTerm2 inline image escape sequence.

        Uses tmux passthrough when running inside tmux.
        """
        with open(image_path, "rb") as image_file:
            image_b64 = base64.b64encode(image_file.read()).decode("ascii")

        name_b64 = base64.b64encode(os.path.basename(image_path).encode("utf-8")).decode("ascii")
        payload = (
            f"\033]1337;File=name={name_b64};inline=1;preserveAspectRatio=1;"
            f"width={width_columns};height=auto:{image_b64}\a"
        )

        # iTerm2 image escape codes need tmux passthrough wrapping.
        if os.getenv("TMUX"):
            tmux_payload = payload.replace("\033", "\033\033")
            sys.stdout.write(f"\033Ptmux;{tmux_payload}\033\\")
        else:
            sys.stdout.write(payload)
        sys.stdout.flush()

    @staticmethod
    def _native_image_size() -> tuple[int, int]:
        """Keep native artwork compact and inside the current terminal window."""
        try:
            terminal = os.get_terminal_size()
            return (
                max(1, min(NATIVE_IMAGE_COLUMNS, terminal.columns - 2)),
                max(1, min(NATIVE_IMAGE_ROWS, terminal.lines - 4)),
            )
        except OSError:
            return NATIVE_IMAGE_COLUMNS, NATIVE_IMAGE_ROWS

    @staticmethod
    def _emit_kitty_inline_image(image_path: str, columns: int, rows: int) -> None:
        """Send a bounded PNG using Kitty's chunked direct-transfer protocol."""
        with Image.open(image_path, formats=IMAGE_FORMATS) as source:
            image = source.convert("RGB")
            image.thumbnail((KITTY_IMAGE_PIXELS, KITTY_IMAGE_PIXELS), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG")
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        for offset in range(0, len(encoded), KITTY_CHUNK_SIZE):
            chunk = encoded[offset : offset + KITTY_CHUNK_SIZE]
            more = int(offset + KITTY_CHUNK_SIZE < len(encoded))
            controls = (
                f"a=T,f=100,t=d,c={columns},r={rows},q=2,m={more}"
                if offset == 0
                else f"m={more},q=2"
            )
            sys.stdout.write(f"\033_G{controls};{chunk}\033\\")
        sys.stdout.flush()

    def _render_thumbnail_native(self, thumb_path: str, title: str, artist: str) -> bool:
        """Render full-color pixels using the active terminal's image protocol."""
        protocol = (
            "iterm" if self._is_iterm2() else "kitty" if self._is_kitty_graphics() else None
        )
        if protocol is None:
            return False

        # Kitty images need more tmux support than simple escape passthrough.
        if protocol == "kitty" and os.getenv("TMUX"):
            return False

        if protocol == "iterm" and os.getenv("TMUX") and not self._tmux_allows_passthrough():
            if not self._logged_tmux_passthrough_hint:
                self._logged_tmux_passthrough_hint = True
                self._log(
                    "THUMB_INFO",
                    "tmux inline image passthrough is off. Enable with: set -g allow-passthrough on",
                )
            return False

        try:
            columns, rows = self._native_image_size()
            print("")  # blank line before
            if protocol == "iterm":
                self._emit_iterm2_inline_image(thumb_path, width_columns=columns)
            else:
                self._emit_kitty_inline_image(thumb_path, columns, rows)
                sys.stdout.write("\r")
            print(f"  \033[1m{title}\033[0m - {artist}")
            print("")  # blank line after
            return True
        except Exception as e:
            self._log("THUMB_ERROR", f"Failed to render native terminal image: {e}")
            return False

    def render(self, thumb_path: str, title: str, artist: str):
        """Render a thumbnail natively or with ANSI colored half-blocks."""
        if not self.is_visible():
            return
        title = "".join(character for character in title if character.isprintable())
        artist = "".join(character for character in artist if character.isprintable())
        try:
            if Path(thumb_path).stat().st_size > MAX_THUMBNAIL_BYTES:
                raise ValueError("Cached artwork exceeds the size limit")
            with Image.open(thumb_path, formats=IMAGE_FORMATS) as source:
                check_image_size(source)
            if self._render_thumbnail_native(thumb_path, title, artist):
                return

            with Image.open(thumb_path, formats=IMAGE_FORMATS) as source:
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
