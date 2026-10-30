"""Maintenance commands. Run `python -m app.cli --help` from the backend folder."""

import argparse
import logging
import re
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import REPOSITORY_ROOT, Settings, get_settings
from app.providers.embeddings import (
    EmbeddingUnavailableError,
    SentenceTransformerEmbeddings,
    configure_hugging_face,
)
from app.providers.llm import OllamaChatModel

# What sentence-transformers needs to run the model with PyTorch. The ONNX and OpenVINO copies
# and the older pickle-format weights are skipped.
MODEL_FILE_PATTERNS = ["*.json", "*.txt", "*.safetensors", "README.md"]
SKIPPED_FILE_PATTERNS = ["onnx/*", "openvino/*"]
EVALUATION_DIR = REPOSITORY_ROOT / "evals"
# The evaluation empties its database first, so it only uses one named for it.
_EVALUATION_DATABASE = re.compile(r"[A-Za-z0-9_]+_eval")


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


def evaluation_database_url(settings: Settings) -> str:
    """The app's database URL, with `_eval` added to the database's name."""
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_eval").render_as_string(hide_password=False)


def evaluate(settings: Settings, arguments: argparse.Namespace) -> int:
    """Run the evaluation (P5-02) in its own database, and write its results."""
    # Imported here, so the other commands don't load the evaluation and its dependencies.
    from alembic import command
    from app.db.maintenance import create_database_if_missing, empty_tables, run_alembic
    from app.evaluation.corpus import CorpusError, load_corpus, read_blocks
    from app.evaluation.dataset import (
        DatasetError,
        check_consistency,
        load_questions,
        questions_sha256,
    )
    from app.evaluation.report import build_report, summary_lines, write_report
    from app.evaluation.runner import EvaluationError, run_evaluation

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    database_url = arguments.database_url or evaluation_database_url(settings)
    database_name = make_url(database_url).database or ""
    if not _EVALUATION_DATABASE.fullmatch(database_name):
        print(
            "The evaluation empties its database first, so the database's name has to end in "
            "_eval.",
            file=sys.stderr,
        )
        return 2
    output: Path = arguments.output or EVALUATION_DIR / "results" / (
        "with-model.json" if arguments.with_model else "retrieval-only.json"
    )

    try:
        documents = load_corpus(arguments.corpus)
        questions = load_questions(arguments.questions)
        problems = check_consistency(read_blocks(documents, settings), questions)
    except (CorpusError, DatasetError, OSError) as error:
        print(f"Can't read the evaluation data: {error}", file=sys.stderr)
        return 1
    if problems:
        print("The questions don't match the corpus:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"Preparing the database {database_name}", file=sys.stderr)
    try:
        create_database_if_missing(database_url)
        run_alembic(database_url, lambda config: command.upgrade(config, "head"))
        empty_tables(database_url)
    except SQLAlchemyError as error:
        print(
            f"Couldn't prepare the database {database_name} ({_first_line(error)}). "
            "Is PostgreSQL running?",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="evaluation-") as storage_dir:
        run_settings = settings.model_copy(
            update={"database_url": database_url, "storage_dir": Path(storage_dir)}
        )
        model = OllamaChatModel(run_settings) if arguments.with_model else None
        try:
            run = run_evaluation(
                run_settings,
                documents,
                questions,
                embeddings=SentenceTransformerEmbeddings(run_settings),
                language_model=model,
                progress=lambda message: print(message, file=sys.stderr),
            )
        except EvaluationError as error:
            print(error, file=sys.stderr)
            return 1
        except SQLAlchemyError as error:
            print(f"The database failed: {_first_line(error)}", file=sys.stderr)
            return 1

    report = build_report(
        run,
        # The command, without paths or addresses, which say nothing about the results.
        command="python -m app.cli evaluate" + (" --with-model" if arguments.with_model else ""),
        questions_sha256=questions_sha256(arguments.questions),
        model_details=model.describe() if model else None,
    )
    write_report(output, report)
    for line in summary_lines(report):
        print(line)
    print(f"Results: {output}")
    return 0


def compare_results(arguments: argparse.Namespace) -> int:
    """Compare two results files: 0 if they agree, 1 if they differ, 2 if one can't be read."""
    from app.evaluation.report import ReportError, compare_reports, read_report

    try:
        differences = compare_reports(
            read_report(arguments.expected), read_report(arguments.actual)
        )
    except ReportError as error:
        print(error, file=sys.stderr)
        return 2
    except (KeyError, TypeError, AttributeError) as error:
        print(
            f"The results files can't be compared: one is incomplete "
            f"({type(error).__name__}: {error}).",
            file=sys.stderr,
        )
        return 2
    if not differences:
        print("The results agree on the data, the settings, and the summary.")
        return 0
    print(f"{arguments.actual} differs from {arguments.expected}:")
    for difference in differences:
        print(f"  {difference}")
    return 1


def _first_line(error: SQLAlchemyError) -> str:
    """A database error's own message, without the statement and parameters SQLAlchemy adds."""
    cause = getattr(error, "orig", None) or error
    return (str(cause).strip().splitlines() or [type(cause).__name__])[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "download-embedding-model",
        help="Download the embedding model once, so indexing can run without a network.",
    )
    evaluation = commands.add_parser(
        "evaluate",
        help="Measure retrieval and answers against the reviewed questions.",
        description=(
            "Index the evaluation corpus in a separate database, ask every reviewed question, "
            "and write the results. The database is emptied first. See docs/evaluation/."
        ),
    )
    evaluation.add_argument(
        "--with-model",
        action="store_true",
        help="Also have the configured Ollama model write answers (slow).",
    )
    evaluation.add_argument(
        "--output",
        type=Path,
        help="Results file (default: evals/results/retrieval-only.json or with-model.json).",
    )
    evaluation.add_argument(
        "--database-url",
        help="Database to use; its name must end in _eval (default: the app's, plus _eval).",
    )
    evaluation.add_argument(
        "--questions",
        type=Path,
        default=EVALUATION_DIR / "questions.jsonl",
        help="Reviewed questions (default: evals/questions.jsonl).",
    )
    evaluation.add_argument(
        "--corpus",
        type=Path,
        default=EVALUATION_DIR / "corpus",
        help="Corpus sources (default: evals/corpus).",
    )
    comparison = commands.add_parser(
        "compare-results",
        help="Check two evaluation results files agree, apart from timings and the computer.",
        description=(
            "Compare two results files on the data, the settings, and the summary; timings, the "
            "environment, and each question's scores aren't compared. Exits with 1 if they "
            "differ, and 2 if a file can't be read."
        ),
    )
    comparison.add_argument("expected", type=Path, help="Results to compare with.")
    comparison.add_argument("actual", type=Path, help="Results to check.")
    arguments = parser.parse_args(argv)
    if arguments.command == "download-embedding-model":
        return download_embedding_model(get_settings())
    if arguments.command == "evaluate":
        return evaluate(get_settings(), arguments)
    if arguments.command == "compare-results":
        return compare_results(arguments)
    return 2


if __name__ == "__main__":
    sys.exit(main())
