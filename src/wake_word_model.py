"""Download the pinned sherpa-onnx keyword model once for offline detection."""

import hashlib
import logging
import shutil
import tarfile
import tempfile
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
MODEL_URL = (
    f"https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/{MODEL_NAME}.tar.bz2"
)
MODEL_SHA256 = "f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / MODEL_NAME
MODEL_FILES = {
    "encoder": "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder": "decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
    "joiner": "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "tokens": "tokens.txt",
    "tokenizer": "bpe.model",
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
    try:
        model_dir.parent.mkdir(parents=True, exist_ok=True)
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
