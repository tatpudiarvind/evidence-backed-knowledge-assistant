"""The evaluation's results (P5-02): a JSON file to keep and compare, and a short summary.

Timings depend on the computer and on whatever else it was doing, so the file keeps only their
median and maximum, never a single question's.
"""

import json
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

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
        "recommendation": recommend_settings(retrievals, run.max_k),
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
        "threshold_sweep": threshold_sweep(retrievals, run.max_k),
        "questions": [_question(result, settings.retrieval_top_k) for result in results],
    }


def write_report(path: Path, report: Json) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written as bytes, so the line endings are the same on every system.
    path.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


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
    lines = [
        f"{report['run']['mode'].replace('_', ' ').capitalize()}: {questions['total']} questions "
        f"({categories}) over {len(data['documents'])} documents in {chunks} chunks.",
        f"Retrieval, for the {retrieval['questions']} questions with expected facts:",
        "  a passage states a fact: "
        + ", ".join(f"top {k} {_fraction(values['hit'])}" for k, values in at_k.items()),
        "  passages state every fact: "
        + ", ".join(f"top {k} {_fraction(values['all_facts'])}" for k, values in at_k.items()),
        f"  mean reciprocal rank: {retrieval['mrr']}",
        f"Current settings (top {current['k']}, minimum similarity {current['threshold']}): "
        f"every fact kept for {_fraction(current['with_facts']['kept_all_facts'])}, "
        f"{_fraction(current['with_facts']['declined'])} declined; "
        f"{_fraction(current['without_facts']['declined'])} questions without facts declined.",
        f"The rules pick top {recommendation['top_k']} and minimum similarity "
        f"{recommendation['min_similarity']}. The weakest passage needed scored "
        f"{recommendation['lowest_needed_similarity']}; the best passage for a question "
        f"without facts scored {recommendation['highest_similarity_without_facts']}.",
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


def _question(result: QuestionResult, top_k: int) -> Json:
    retrieval = result.retrieval
    question = retrieval.question
    return {
        "id": question.id,
        "category": question.category.value,
        "question": question.question,
        "expected_facts": len(question.expected_facts),
        "first_relevant_rank": retrieval.first_relevant_rank,
        "facts_found_in_top_k": sorted(retrieval.facts_found(top_k)),
        "index_order_matches_exact": result.comparison.index == result.comparison.exact,
        "evidence_matches_search": result.evidence_matches,
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
