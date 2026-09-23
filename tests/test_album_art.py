import asyncio
import io
from unittest.mock import Mock

import pytest
from PIL import Image

import album_art as module
from album_art import AlbumArt

SONG_ID = "0123456789ab"
THUMBNAIL_URL = "https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"


def response_for(data: bytes, *, status=200, headers=None):
    response = Mock(status_code=status, headers=headers or {})
    response.iter_content.return_value = [data]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    return response


def test_bad_download_preserves_cached_thumbnail(tmp_path, monkeypatch):
    art = AlbumArt(tmp_path, Mock())
    path = tmp_path / f"{SONG_ID}_thumb.jpg"
    Image.new("RGB", (8, 8), "red").save(path)
    original = path.read_bytes()
    response = response_for(b"not an image")
    monkeypatch.setattr(module.requests, "get", Mock(return_value=response))
    assert asyncio.run(art.download(THUMBNAIL_URL, SONG_ID)) is None
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_valid_download_is_converted_and_reused(tmp_path, monkeypatch):
    data = io.BytesIO()
    Image.new("RGBA", (1000, 10), "blue").save(data, format="PNG")
    response = response_for(data.getvalue())
    request = Mock(return_value=response)
    monkeypatch.setattr(module.requests, "get", request)
    art = AlbumArt(tmp_path, Mock())
    path = asyncio.run(art.download(THUMBNAIL_URL, SONG_ID))
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.mode == "RGB"
    assert asyncio.run(art.download(THUMBNAIL_URL, SONG_ID)) == path
    request.assert_called_once_with(
        THUMBNAIL_URL, timeout=(5, 10), stream=True, allow_redirects=False
    )


def test_redirected_output_never_emits_terminal_sequences(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(AlbumArt, "is_visible", lambda _: False)
    monkeypatch.setattr(AlbumArt, "_is_iterm2", lambda _: True)
    AlbumArt(tmp_path, Mock()).render("missing.jpg", "Title", "Artist")
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://i.ytimg.com/a.jpg",
        "https://127.0.0.1/private",
        "https://169.254.169.254/",
        "https://i.ytimg.com.evil.test/a.jpg",
        "https://user:password@i.ytimg.com/a.jpg",
        "https://i.ytimg.com:444/a.jpg",
        "file:///etc/passwd",
    ],
)
def test_untrusted_artwork_urls_never_make_a_request(tmp_path, monkeypatch, url):
    request = Mock()
    monkeypatch.setattr(module.requests, "get", request)
    assert asyncio.run(AlbumArt(tmp_path, Mock()).download(url, SONG_ID)) is None
    request.assert_not_called()


@pytest.mark.parametrize(
    "status,headers,data",
    [
        (302, {"Location": "http://127.0.0.1/"}, b""),
        (200, {"Content-Length": str(module.MAX_THUMBNAIL_BYTES + 1)}, b""),
        (200, {}, b"0123456789"),
    ],
)
def test_redirects_and_oversized_streams_are_rejected(tmp_path, monkeypatch, status, headers, data):
    monkeypatch.setattr(module, "MAX_THUMBNAIL_BYTES", 8)
    response = response_for(data, status=status, headers=headers)
    monkeypatch.setattr(module.requests, "get", Mock(return_value=response))
    assert asyncio.run(AlbumArt(tmp_path, Mock()).download(THUMBNAIL_URL, SONG_ID)) is None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("image_format,size", [("PNG", (11, 10)), ("BMP", (1, 1))])
def test_excessive_pixels_and_unneeded_parsers_are_rejected(
    tmp_path, monkeypatch, image_format, size
):
    data = io.BytesIO()
    Image.new("RGB", size).save(data, format=image_format)
    monkeypatch.setattr(module, "MAX_THUMBNAIL_PIXELS", 100)
    monkeypatch.setattr(module.requests, "get", Mock(return_value=response_for(data.getvalue())))
    assert asyncio.run(AlbumArt(tmp_path, Mock()).download(THUMBNAIL_URL, SONG_ID)) is None
    assert not list(tmp_path.iterdir())


def test_artwork_id_cannot_escape_cache_directory(tmp_path, monkeypatch):
    request = Mock()
    monkeypatch.setattr(module.requests, "get", request)
    assert asyncio.run(AlbumArt(tmp_path, Mock()).download(THUMBNAIL_URL, "../escape")) is None
    request.assert_not_called()
