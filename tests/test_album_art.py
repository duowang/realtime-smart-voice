import asyncio
import io
from unittest.mock import Mock

from PIL import Image

import album_art as module
from album_art import AlbumArt


def test_bad_download_preserves_cached_thumbnail(tmp_path, monkeypatch):
    art = AlbumArt(tmp_path, Mock())
    path = tmp_path / "test_thumb.jpg"
    Image.new("RGB", (8, 8), "red").save(path)
    original = path.read_bytes()
    response = Mock(content=b"not an image")
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(module.requests, "get", Mock(return_value=response))
    assert asyncio.run(art.download("https://example.test/image", "test")) is None
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_valid_download_is_converted_and_reused(tmp_path, monkeypatch):
    data = io.BytesIO()
    Image.new("RGBA", (1000, 10), "blue").save(data, format="PNG")
    response = Mock(content=data.getvalue())
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    request = Mock(return_value=response)
    monkeypatch.setattr(module.requests, "get", request)
    art = AlbumArt(tmp_path, Mock())
    path = asyncio.run(art.download("https://example.test/image", "test"))
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.mode == "RGB"
    assert asyncio.run(art.download("https://example.test/image", "test")) == path
    request.assert_called_once()


def test_redirected_output_never_emits_terminal_sequences(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(AlbumArt, "is_visible", lambda _: False)
    monkeypatch.setattr(AlbumArt, "_is_iterm2", lambda _: True)
    AlbumArt(tmp_path, Mock()).render("missing.jpg", "Title", "Artist")
    assert capsys.readouterr().out == ""
