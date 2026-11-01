"""Isolated parser child. Receives only a local file path and bounded parse settings."""

import json
import sys
from pathlib import Path

from app.domain.indexing import IndexingError
from app.providers.parsers import ParseLimits, parser_for


def _limit_memory() -> None:
    try:
        from importlib import import_module

        resource = import_module("resource")
    except ImportError:
        return
    limit = 1536 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def main() -> int:
    _limit_memory()
    path, mime, max_pages, max_characters, timeout = sys.argv[1:]
    try:
        with Path(path).open("rb") as source:
            blocks = parser_for(
                mime, ParseLimits(int(max_pages), int(max_characters), float(timeout))
            ).extract(source)
        json.dump(
            [{"text": b.text, "page_number": b.page_number, "section": b.section} for b in blocks],
            sys.stdout,
            ensure_ascii=True,
        )
        return 0
    except IndexingError as error:
        json.dump({"error": error.failure.value}, sys.stdout)
        return 0
    except BaseException:
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
