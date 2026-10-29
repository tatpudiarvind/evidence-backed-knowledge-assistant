"""Maintenance commands. Run `python -m app.cli --help` from the backend folder."""

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from app.core.config import Settings, get_settings
from app.providers.embeddings import (
    EmbeddingUnavailableError,
    SentenceTransformerEmbeddings,
    configure_hugging_face,
)

# What sentence-transformers needs to run the model with PyTorch. The ONNX and OpenVINO copies
# and the older pickle-format weights are skipped.
MODEL_FILE_PATTERNS = ["*.json", "*.txt", "*.safetensors", "README.md"]
SKIPPED_FILE_PATTERNS = ["onnx/*", "openvino/*"]


def download_embedding_model(settings: Settings) -> int:
    """Download the pinned model revision, then check it loads and works without a network."""
    model_dir = settings.embedding_model_dir
    model_dir.mkdir(parents=True, exist_ok=True)
    configure_hugging_face(model_dir, offline=False)
    # Trust the operating system's certificate store, as browsers do, so downloads also work
    # behind proxies that inspect HTTPS.
    import truststore

    truststore.inject_into_ssl()
    from huggingface_hub import snapshot_download

    name, revision = settings.embedding_model_name, settings.embedding_model_revision
    print(f"Downloading {name} at revision {revision[:12]} into {model_dir}")
    started = time.perf_counter()
    try:
        snapshot = Path(
            snapshot_download(
                name,
                revision=revision,
                cache_dir=model_dir,
                allow_patterns=MODEL_FILE_PATTERNS,
                ignore_patterns=SKIPPED_FILE_PATTERNS,
                token=False,
            )
        )
    except Exception as error:
        print(f"Download failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    files = sorted(path for path in snapshot.rglob("*") if path.is_file())
    total = sum(path.stat().st_size for path in files)
    for path in files:
        print(f"  {path.relative_to(snapshot)} ({path.stat().st_size:,} bytes)")
    print(f"{len(files)} files, {total:,} bytes, in {time.perf_counter() - started:.1f} s")

    started = time.perf_counter()
    try:
        vector = SentenceTransformerEmbeddings(settings).embed_query("A short test question?")
    except EmbeddingUnavailableError:
        print("The downloaded model couldn't be loaded; see the warning above.", file=sys.stderr)
        return 1
    print(
        f"Checked: the model loads offline and makes {len(vector)}-dimensional vectors "
        f"({time.perf_counter() - started:.1f} s)."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "download-embedding-model",
        help="Download the embedding model once, so indexing can run without a network.",
    )
    arguments = parser.parse_args(argv)
    if arguments.command == "download-embedding-model":
        return download_embedding_model(get_settings())
    return 2


if __name__ == "__main__":
    sys.exit(main())
