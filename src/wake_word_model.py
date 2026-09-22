"""Download the pinned sherpa-onnx keyword model once for offline detection."""

import hashlib
import logging
import shutil
import tarfile
import tempfile
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
MODEL_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/"
    f"{MODEL_NAME}.tar.bz2"
)
MODEL_SHA256 = "68447f4fbc67e70eee3a93961f36e81e98f47aef73ce7e7ca00885c6cd3616a6"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / MODEL_NAME
MODEL_FILES = {
    "encoder": "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
    "decoder": "decoder-epoch-13-avg-2-chunk-16-left-64.onnx",
    "joiner": "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
    "tokens": "tokens.txt",
    "lexicon": "en.phone",
}


def ensure_wake_word_model(model_dir: Path = DEFAULT_MODEL_DIR) -> dict[str, Path]:
    """Validate a download before publishing its selected files to the cache.

    An existing complete cache needs no network. Only the known regular files
    are extracted, so archive paths and links cannot write outside the cache.
    """
    paths = {role: model_dir / name for role, name in MODEL_FILES.items()}
    if all(path.is_file() and path.stat().st_size > 0 for path in paths.values()):
        return paths

    logging.getLogger(__name__).info("Downloading wake-word model from %s", MODEL_URL)
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix=".wake-model-", dir=model_dir.parent) as tmp:
            staging = Path(tmp)
            archive = staging / "model.tar.bz2"
            digest = hashlib.sha256()
            with requests.get(MODEL_URL, stream=True, timeout=(15, 60)) as response:
                response.raise_for_status()
                with archive.open("wb") as output:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        digest.update(block)
                        output.write(block)
            if digest.hexdigest() != MODEL_SHA256:
                raise ValueError("Wake-word model download failed its SHA-256 check")

            with tarfile.open(archive) as bundle:
                for name in MODEL_FILES.values():
                    member = bundle.getmember(f"{MODEL_NAME}/{name}")
                    if not member.isfile() or member.size == 0:
                        raise ValueError(f"Invalid wake-word model file: {name}")
                    with bundle.extractfile(member) as src, (staging / name).open("wb") as dst:
                        shutil.copyfileobj(src, dst)

            model_dir.mkdir(parents=True, exist_ok=True)
            for name in MODEL_FILES.values():
                (staging / name).replace(model_dir / name)
    except (OSError, requests.RequestException, tarfile.TarError, KeyError, ValueError) as error:
        raise RuntimeError(
            f"Could not prepare the wake-word model in {model_dir}: {error}. "
            "Check your internet connection and rerun ./run.sh --setup-only."
        ) from error
    return paths


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ensure_wake_word_model()
    print(f"Offline wake-word model ready: {DEFAULT_MODEL_DIR}")
