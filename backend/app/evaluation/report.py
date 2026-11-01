"""The evaluation's results (P5-02): a JSON file to keep and compare, and a short summary.

Timings depend on the computer and on whatever else it was doing, so the file keeps only their
median and maximum, never a single question's.
"""

import difflib
import json
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.domain.questions import AnswerMode
from app.evaluation.runner import EvaluationRun, QuestionResult
from app.evaluation.scoring import (
    SEARCH_LIMIT,
    THRESHOLD_GRID,
    THRESHOLD_MARGIN,
    Json,
    answer_summary,
    count_true,
    evidence_outcome,
    index_summary,
    recommend_settings,
    retrieval_summary,
    threshold_sweep,
)

FORMAT_VERSION = 1
# What `compare_reports` compares besides the summary: the data and the settings.
_COMPARED_SECTIONS = ("data", "config")
# Generated DOCX files are zip archives, so their size depends on the zlib build: the same text
# made 36,742 bytes on Python 3.14 for Windows (zlib-ng) and 38,084 on 3.12 (zlib 1.3.2).
_UNCOMPARED_KEYS = frozenset({"size_bytes"})
_MISSING = object()


class ReportError(Exception):
    """A results file that can't be read, or isn't in this version's format."""


def build_report(
    run: EvaluationRun,
    *,
    command: str,
    questions_sha256: str,
    model_details: Json | None = None,
) -> Json:
    settings = run.settings
    results = run.results
    retrievals = [result.retrieval for result in results]
    scores = [result.score for result in results]
    categories = Counter(result.retrieval.question.category.value for result in results)
    environment = dict(run.environment)
    if model_details is not None:
        environment["language_model"] = model_details
    mode = settings.retrieval_mode
    hybrid = mode != "vector"
    reranked = mode == "hybrid_rerank"
    return {
        "format_version": FORMAT_VERSION,
        "run": {
            "mode": "with_model" if run.language_model else "retrieval_only",
            "started_at": run.started_at.isoformat(timespec="seconds"),
            "seconds": round(run.seconds, 1),
            "command": command,
        },
        "data": {
            "questions_sha256": questions_sha256,
            "questions": {"total": len(results), **dict(sorted(categories.items()))},
            "corpus_sha256": run.corpus_sha256,
            "documents": [
                {
                    "name": document.name,
                    "type": document.mime_type,
                    "source": document.source_name,
                    "source_sha256": document.source_sha256,
                    "size_bytes": document.size_bytes,
                    "chunks": document.chunks,
                }
                for document in run.documents
            ],
        },
        "config": {
            "embedding_model": settings.embedding_model_name,
            "embedding_model_revision": settings.embedding_model_revision,
            "chunk_size_characters": settings.chunk_size_characters,
            "chunk_overlap_characters": settings.chunk_overlap_characters,
            "retrieval_top_k": settings.retrieval_top_k,
            "retrieval_min_similarity": settings.retrieval_min_similarity,
            "retrieval_mode": mode,
            "retrieval_candidates": settings.retrieval_candidates if hybrid else None,
            "rrf_k": settings.rrf_k if hybrid else None,
            "reranker_model": settings.reranker_model_name if reranked else None,
            "reranker_model_revision": settings.reranker_model_revision if reranked else None,
            "answer_context_characters": settings.answer_context_characters,
            "language_model": run.language_model,
            "ollama_context_tokens": settings.ollama_context_tokens if run.language_model else None,
            "search_limit": SEARCH_LIMIT,
            "max_k": run.max_k,
            "threshold_grid": list(THRESHOLD_GRID),
            "threshold_margin": THRESHOLD_MARGIN,
        },
        "environment": environment,
        "retrieval": retrieval_summary(retrievals),
        "current_settings": evidence_outcome(
            retrievals, settings.retrieval_top_k, settings.retrieval_min_similarity
        ),
        # The hybrid modes drop passages below the minimum similarity before fusing the two
        # rankings, so a threshold tried on their ranked passages isn't what the app would do.
        "recommendation": None if hybrid else recommend_settings(retrievals, run.max_k),
        "hybrid_search": (
            _hybrid_summary(results, settings.retrieval_top_k, reranked) if hybrid else None
        ),
        "index_comparison": index_summary(
            [result.comparison for result in results], settings.retrieval_top_k
        ),
        "answers": answer_summary(scores),
        "checks": {
            "evidence_matches_search": count_true(result.evidence_matches for result in results),
            # Answers that fell back to listing passages because the model didn't reply.
            "model_unavailable": (
                count_true(
                    score.outcome.answer.mode is AnswerMode.SEARCH_ONLY
                    and score.outcome.answer.model_name is not None
                    for score in scores
                )
                if run.language_model
                else None
            ),
        },
        "timing": {
            "answer_seconds": _seconds([score.outcome.seconds for score in scores]),
            "model_seconds": _seconds(
                [result.model_seconds for result in results if result.model_seconds is not None]
            ),
        },
        "threshold_sweep": None if hybrid else threshold_sweep(retrievals, run.max_k),
        "questions": [_question(result, settings.retrieval_top_k) for result in results],
    }


def write_report(path: Path, report: Json) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written as bytes, so the line endings are the same on every system.
    path.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def read_report(path: Path) -> Json:
    try:
        report = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as error:
        raise ReportError(f"Can't read {path}: {error}") from error
    if not isinstance(report, dict) or report.get("format_version") != FORMAT_VERSION:
        raise ReportError(f"{path} isn't a results file in format {FORMAT_VERSION}.")
    return report


def summary_lines(report: Json) -> list[str]:
    """A few lines on what the results file holds, for the terminal."""
    data = report["data"]
    retrieval = report["retrieval"]
    current = report["current_settings"]
    recommendation = report["recommendation"]
    index = report["index_comparison"]
    answers = report["answers"]
    questions = data["questions"]
    categories = ", ".join(
        f"{count} {name}" for name, count in questions.items() if name != "total"
    )
    chunks = sum(document["chunks"] for document in data["documents"])
    at_k = retrieval["at_k"]
    hybrid = report.get("hybrid_search")
    lines = [
        f"{report['run']['mode'].replace('_', ' ').capitalize()}: {questions['total']} questions "
        f"({categories}) over {len(data['documents'])} documents in {chunks} chunks.",
        _search_mode(report["config"]),
        f"Retrieval, for the {retrieval['questions']} questions with expected facts"
        + (", over the passages above the minimum similarity:" if hybrid else ":"),
        "  a passage states a fact: "
        + ", ".join(f"top {k} {_fraction(values['hit'])}" for k, values in at_k.items()),
        "  passages state every fact: "
        + ", ".join(f"top {k} {_fraction(values['all_facts'])}" for k, values in at_k.items()),
        f"  mean reciprocal rank: {retrieval['mrr']}",
        f"Current settings (top {current['k']}, minimum similarity {current['threshold']}): "
        f"every fact kept for {_fraction(current['with_facts']['kept_all_facts'])}, "
        f"{_fraction(current['with_facts']['declined'])} declined; "
        f"{_fraction(current['without_facts']['declined'])} questions without facts declined.",
    ]
    if recommendation is not None:
        lines.append(
            f"The rules pick top {recommendation['top_k']} and minimum similarity "
            f"{recommendation['min_similarity']}. The weakest passage needed scored "
            f"{recommendation['lowest_needed_similarity']}; the best passage for a question "
            f"without facts scored {recommendation['highest_similarity_without_facts']}."
        )
    if hybrid is not None:
        lines.append(
            f"Keyword search: passages for {_fraction(hybrid['with_keyword_matches'])} "
            f"questions, {hybrid['keyword_matches']} in all, {hybrid['keyword_dropped']} of them "
            "below the minimum similarity; evidence found only by keywords "
            f"{_fraction(hybrid['evidence_from_keywords_only'])}"
        )
        if hybrid["rerank_failed"] is not None:
            lines.append(f"Reranker failed: {_fraction(hybrid['rerank_failed'])}")
    lines += [
        "Chunks read by: "
        + "; ".join(
            f"{mode} search {', '.join(f'{plan} ({count})' for plan, count in plans.items())}"
            for mode, plans in index["plans"].items()
        ),
        f"  forced HNSW order equals exact order: {_fraction(index['index_same_order_as_exact'])}",
        f"{'Answers' if report['run']['mode'] == 'with_model' else 'Search-only answers'}: "
        f"{_fraction(answers['with_facts']['answered'])} questions with facts answered, "
        f"{_fraction(answers['with_facts']['cites_relevant'])} citing a passage that states one, "
        f"{_fraction(answers['with_facts']['correct_citations'])} citations correct; "
        f"{_fraction(answers['without_facts']['abstained'])} questions without facts declined.",
    ]
    if "all_facts_stated" in answers["with_facts"]:
        with_facts = answers["with_facts"]
        lines.append(
            f"  every fact stated: {_fraction(with_facts['all_facts_stated'])}; facts stated "
            f"{_fraction(with_facts['facts_stated'])}, of which supported by a citation "
            f"{_fraction(with_facts['facts_supported_by_citations'])}"
        )
    forbidden = answers.get("forbidden_text")
    if forbidden and forbidden["questions"]:
        lines.append(
            f"Forbidden text, over {forbidden['questions']} questions: in answers "
            f"{_fraction(forbidden['in_answer'])}, in model replies "
            f"{_fraction(forbidden['in_reply'])}, in prompts {_fraction(forbidden['in_prompt'])}"
        )
    checks = report["checks"]
    lines.append(f"Evidence matches the search: {_fraction(checks['evidence_matches_search'])}")
    if checks["model_unavailable"] is not None:
        lines.append(f"Model didn't reply: {_fraction(checks['model_unavailable'])}")
    return lines


def compare_reports(expected: Json, actual: Json) -> list[str]:
    """How two results files differ, one line each; none if they agree.

    Runs of the same code, data, and settings should agree on the data, the settings, and the
    summary, on any computer. Timings and the environment aren't compared, nor is each
    question's detail, whose scores can differ in the last decimal place between computers.
    """
    differences: list[str] = []
    for section in _COMPARED_SECTIONS:
        before = _leaves(expected[section], section)
        after = _leaves(actual[section], section)
        for path in [*before, *(path for path in after if path not in before)]:
            old, new = before.get(path, _MISSING), after.get(path, _MISSING)
            if old != new:
                differences.append(f"{path}: {_shown(old)} != {_shown(new)}")
    differences.extend(
        difflib.unified_diff(
            summary_lines(expected), summary_lines(actual), "expected", "actual", n=0, lineterm=""
        )
    )
    return differences


def _search_mode(config: Json) -> str:
    # Results from before Phase 7 have no retrieval mode: they searched by meaning only.
    mode = config.get("retrieval_mode", "vector")
    if mode == "vector":
        return "Search mode: vector (by meaning)."
    described = (
        f"by meaning and by keywords, {config['retrieval_candidates']} candidates each, "
        f"fused with RRF k {config['rrf_k']}"
    )
    if mode == "hybrid_rerank":
        described += f", reranked by {config['reranker_model']}"
    return f"Search mode: {mode} ({described})."


def _hybrid_summary(results: Sequence[QuestionResult], top_k: int, reranked: bool) -> Json:
    """What hybrid search did over all the questions."""
    details = [result.hybrid for result in results if result.hybrid is not None]
    # In the hybrid modes, the passages judged are already above the minimum similarity, so
    # the first `top_k` are the evidence.
    evidence = [
        passage.passage.ranking
        for result in results
        for passage in result.retrieval.passages[:top_k]
    ]
    return {
        "questions": len(details),
        "with_keyword_matches": count_true(detail.keyword_matches > 0 for detail in details),
        "keyword_matches": sum(detail.keyword_matches for detail in details),
        "keyword_dropped": sum(detail.keyword_dropped for detail in details),
        "evidence_from_keywords_only": count_true(
            ranking is not None and ranking.vector_rank is None for ranking in evidence
        ),
        "rerank_failed": (
            count_true(detail.rerank_failed is True for detail in details) if reranked else None
        ),
    }


def _question(result: QuestionResult, top_k: int) -> Json:
    retrieval = result.retrieval
    question = retrieval.question
    summary: Json = {
        "id": question.id,
        "category": question.category.value,
        "question": question.question,
        "expected_facts": len(question.expected_facts),
        "first_relevant_rank": retrieval.first_relevant_rank,
        "facts_found_in_top_k": sorted(retrieval.facts_found(top_k)),
        "index_order_matches_exact": result.comparison.index == result.comparison.exact,
        "evidence_matches_search": result.evidence_matches,
    }
    if result.hybrid is not None:
        summary["hybrid_search"] = {
            "candidates": result.hybrid.candidates,
            "keyword_matches": result.hybrid.keyword_matches,
            "keyword_dropped": result.hybrid.keyword_dropped,
            "rerank_failed": result.hybrid.rerank_failed,
        }
    return summary | {
        "passages": [passage.to_json() for passage in retrieval.passages],
        "answer": result.score.to_json(),
    }


def _seconds(values: Sequence[float]) -> Json:
    return {
        "count": len(values),
        "median": round(statistics.median(values), 2) if values else None,
        "max": round(max(values), 2) if values else None,
    }


def _fraction(value: Json) -> str:
    return f"{value['count']}/{value['of']}"


def _leaves(value: Any, path: str) -> dict[str, Any]:
    """A JSON value's single values by their path, such as `data.documents.0.chunks`."""
    if isinstance(value, dict):
        items = list(value.items())
    elif isinstance(value, list):
        items = list(enumerate(value))
    else:
        return {path: value}
    leaves: dict[str, Any] = {}
    for key, item in items:
        if key not in _UNCOMPARED_KEYS:
            leaves.update(_leaves(item, f"{path}.{key}"))
    return leaves


def _shown(value: Any) -> str:
    return "(missing)" if value is _MISSING else json.dumps(value, ensure_ascii=False)
