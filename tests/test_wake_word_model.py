import hashlib
import io
import sys
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import wake_word_model as model


def install_fake_download(monkeypatch, *, missing=None, link=None):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:bz2") as bundle:
        for name in [*model.MODEL_FILES.values(), "../../unwanted.txt"]:
            if name == missing:
                continue
            member = tarfile.TarInfo(f"{model.MODEL_NAME}/{name}")
            if name == link:
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside.txt"
                bundle.addfile(member)
            else:
                data = name.encode()
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
    data = archive.getvalue()
    monkeypatch.setattr(model, "MODEL_SHA256", hashlib.sha256(data).hexdigest())
    response = Mock()
    response.iter_content.return_value = [data[:20], data[20:]]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    request = Mock(return_value=response)
    monkeypatch.setattr(model.requests, "get", request)
    return request


def test_verified_download_extracts_only_model_files_and_reuses_cache(tmp_path, monkeypatch):
    request = install_fake_download(monkeypatch)
    cache = tmp_path / "models" / "model"
    paths = model.ensure_wake_word_model(cache)
    assert {p.name for p in cache.iterdir()} == set(model.MODEL_FILES.values())
    assert all(path.read_text() == path.name for path in paths.values())
    assert not (tmp_path / "unwanted.txt").exists()
    assert model.ensure_wake_word_model(cache) == paths
    request.assert_called_once()


def test_bad_checksum_does_not_install_or_replace_existing_files(tmp_path, monkeypatch):
    install_fake_download(monkeypatch)
    monkeypatch.setattr(model, "MODEL_SHA256", "0" * 64)
    cache = tmp_path / "model"
    cache.mkdir()
    old = cache / model.MODEL_FILES["tokens"]
    old.write_text("previous file")
    with pytest.raises(RuntimeError, match="SHA-256"):
        model.ensure_wake_word_model(cache)
    assert list(cache.iterdir()) == [old]
    assert old.read_text() == "previous file"
    assert list(tmp_path.iterdir()) == [cache]


@pytest.mark.parametrize("invalid", ["missing", "link"])
def test_incomplete_or_linked_model_is_rejected(tmp_path, monkeypatch, invalid):
    install_fake_download(monkeypatch, **{invalid: model.MODEL_FILES["tokens"]})
    cache = tmp_path / "model"
    with pytest.raises(RuntimeError, match="Could not prepare"):
        model.ensure_wake_word_model(cache)
    assert not cache.exists()


def test_partial_cache_is_repaired(tmp_path, monkeypatch):
    install_fake_download(monkeypatch)
    cache = tmp_path / "model"
    cache.mkdir()
    (cache / model.MODEL_FILES["tokens"]).touch()
    paths = model.ensure_wake_word_model(cache)
    assert all(p.stat().st_size > 0 for p in paths.values())
