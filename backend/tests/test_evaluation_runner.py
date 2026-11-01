"""Running the evaluation (P5-02, and Phase 7's hybrid modes): the runner on the real corpus with
stand-in models, and the results file it leads to."""

import copy
import hashlib
import json
import math
import platform
import random
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from app.cli import EVALUATION_DIR
from app.domain.questions import AbstentionReason, AnswerMode
from app.evaluation.corpus import CorpusDocument, build_document, load_corpus
from app.evaluation.dataset import EvalQuestion, load_questions, questions_sha256
from app.evaluation.report import (
    FORMAT_VERSION,
    build_report,
    compare_reports,
    summary_lines,
    write_report,
)
from app.evaluation.runner import EvaluationError, chunk_access, max_k, run_evaluation
from app.providers.embeddings import EmbeddingUnavailableError
from tests.support import (
    PDF_MIME,
    HashingEmbeddings,
    LengthReranker,
    ScriptedLanguageModel,
    hashed_vector,
    make_settings,
    pdf_bytes,
    stored_files,
)

INDEX = "ix_document_chunks_embedding"


class DistinctEmbeddings(HashingEmbeddings):
    """`HashingEmbeddings` plus a little noise fixed by each text, so no two passages tie.

    With ties, the evaluation's search and the app's could order equally close passages
    differently, and the runner compares the two.
    """

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.document_batches.append(list(texts))
        return [distinct_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return distinct_vector(text)


def distinct_vector(text: str) -> list[float]:
    noise = random.Random(hashlib.sha256(text.encode()).digest())
    vector = [value + 0.01 * noise.gauss(0.0, 1.0) for value in hashed_vector(text)]
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


class UnavailableEmbeddings(HashingEmbeddings):
    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingUnavailableError("synthetic-model")


def answerable(question_id: str, question: str) -> EvalQuestion:
    return EvalQuestion.model_validate(
        {
            "id": question_id,
            "category": "answerable",
            "question": question,
            "expected_sources": [{"document": "notes.txt"}],
            "expected_facts": [["seven years"]],
        }
    )


NESTED_PLAN: list[dict[str, Any]] = [
    {
        "Plan": {
            "Node Type": "Limit",
            "Plans": [
                {
                    "Node Type": "Nested Loop",
                    "Plans": [
                        {
                            "Node Type": "Index Scan",
                            "Relation Name": "document_chunks",
                            "Index Name": INDEX,
                        },
                        {
                            "Node Type": "Index Scan",
                            "Relation Name": "documents",
                            "Index Name": "pk_documents",
                        },
                    ],
                }
            ],
        }
    }
]


def test_max_k_is_how_many_full_size_chunks_fit_in_the_answer_context() -> None:
    assert max_k(make_settings()) == 6
    # Never more than the evaluation retrieves, and never none.
    assert max_k(make_settings(answer_context_characters=50_000)) == 10
    assert max_k(make_settings(answer_context_characters=1000, chunk_size_characters=4000)) == 1


@pytest.mark.parametrize("plan", [NESTED_PLAN, json.dumps(NESTED_PLAN)])
def test_the_plan_shows_how_the_chunks_were_read(plan: object) -> None:
    assert chunk_access(plan) == f"Index Scan using {INDEX}"


def test_every_way_the_plan_reads_the_chunks_is_listed() -> None:
    plan = [
        {
            "Plan": {
                "Node Type": "Append",
                "Plans": [
                    {"Node Type": "Seq Scan", "Relation Name": "document_chunks"},
                    {
                        "Node Type": "Bitmap Heap Scan",
                        "Relation Name": "document_chunks",
                        "Plans": [{"Node Type": "Bitmap Index Scan", "Index Name": "ix_other"}],
                    },
                ],
            }
        }
    ]

    assert chunk_access(plan) == "Bitmap Heap Scan, Seq Scan"
    assert chunk_access([{"Plan": {"Node Type": "Result"}}]) == "not read"


def test_an_unavailable_embedding_model_stops_the_run_before_the_database() -> None:
    # The settings point at a database nobody can reach, so getting further would fail.
    with pytest.raises(EvaluationError, match="The embedding model isn't available"):
        run_evaluation(
            make_settings(), [], [], embeddings=UnavailableEmbeddings(), language_model=None
        )


def test_a_model_that_does_not_reply_stops_the_run_before_the_database() -> None:
    model = ScriptedLanguageModel(fail=True)

    with pytest.raises(EvaluationError, match="The language model scripted-model didn't reply"):
        run_evaluation(
            make_settings(), [], [], embeddings=HashingEmbeddings(), language_model=model
        )

    assert len(model.prompts) == 1


@pytest.mark.parametrize(
    "reranker", [None, LengthReranker(fail=True)], ids=["none given", "not downloaded"]
)
def test_an_unavailable_reranker_stops_the_run_before_the_database(
    reranker: LengthReranker | None,
) -> None:
    # Otherwise every question would quietly keep the fused order.
    with pytest.raises(
        EvaluationError,
        match=re.escape(
            "The reranker isn't available. Download it with "
            "`python -m app.cli download-reranker-model`."
        ),
    ):
        run_evaluation(
            make_settings(retrieval_mode="hybrid_rerank"),
            [],
            [],
            embeddings=HashingEmbeddings(),
            language_model=None,
            reranker=reranker,
        )


@pytest.mark.integration
def test_the_evaluation_indexes_the_corpus_and_asks_every_question(
    database_url: str, tmp_path: Path
) -> None:
    documents = load_corpus(EVALUATION_DIR / "corpus")
    questions = load_questions(EVALUATION_DIR / "questions.jsonl")
    settings = make_settings(
        database_url=database_url,
        storage_dir=tmp_path / "storage",
        retrieval_min_similarity=0.0,
    )
    messages: list[str] = []

    run = run_evaluation(
        settings,
        documents,
        questions,
        embeddings=DistinctEmbeddings(),
        language_model=None,
        progress=messages.append,
    )

    chunks = sum(document.chunks for document in run.documents)
    assert [document.name for document in run.documents] == [doc.name for doc in documents]
    assert all(document.chunks > 0 for document in run.documents)
    assert messages == [
        f"Indexed {len(documents)} documents into {chunks} chunks",
        *(
            f"Asked {question.id} ({number} of {len(questions)})"
            for number, question in enumerate(questions, start=1)
        ),
    ]
    assert len(stored_files(settings.storage_dir)) == len(documents)
    assert [result.retrieval.question.id for result in run.results] == [
        question.id for question in questions
    ]
    for result in run.results:
        question_id = result.retrieval.question.id
        assert len(result.retrieval.passages) == min(10, chunks), question_id
        assert INDEX in result.comparison.plans["index"], question_id
        assert INDEX not in result.comparison.plans["exact"], question_id
        assert result.evidence_matches, question_id
        assert result.score.outcome.answer.mode is AnswerMode.SEARCH_ONLY, question_id
        assert result.score.outcome.prompt is None
        assert result.model_seconds is None

    report = build_report(
        run,
        command="python -m app.cli evaluate",
        questions_sha256=questions_sha256(EVALUATION_DIR / "questions.jsonl"),
    )
    path = tmp_path / "results" / "retrieval-only.json"
    write_report(path, report)

    written = path.read_bytes()
    assert b"\r\n" not in written
    assert written.endswith(b"}\n")
    assert json.loads(written) == report
    assert report["format_version"] == FORMAT_VERSION
    assert report["run"]["mode"] == "retrieval_only"
    assert report["data"]["questions"] == {
        "total": len(questions),
        **Counter(question.category.value for question in questions),
    }
    assert report["config"]["language_model"] is None
    assert report["checks"] == {
        "evidence_matches_search": {"count": len(questions), "of": len(questions), "share": 1.0},
        "model_unavailable": None,
    }
    assert "all_facts_stated" not in report["answers"]["with_facts"]
    assert "forbidden_text" not in report["answers"]
    assert report["environment"]["pgvector"]
    # Nothing about the computer it ran on beyond what the results depend on.
    text = written.decode()
    assert tmp_path.name not in text
    assert not platform.node() or platform.node() not in text
    lines = summary_lines(report)
    assert lines[0].startswith(f"Retrieval only: {len(questions)} questions (")
    assert any(line.startswith("Search-only answers: ") for line in lines)
    assert not any(line.startswith("Forbidden text") for line in lines)
    assert lines[-1] == f"Evidence matches the search: {len(questions)}/{len(questions)}"


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["hybrid", "hybrid_rerank"])
def test_the_hybrid_modes_judge_the_passages_the_app_ranks(
    database_url: str, tmp_path: Path, mode: str
) -> None:
    documents = load_corpus(EVALUATION_DIR / "corpus")
    questions = load_questions(EVALUATION_DIR / "questions.jsonl")
    settings = make_settings(
        database_url=database_url,
        storage_dir=tmp_path / "storage",
        retrieval_min_similarity=0.0,
        retrieval_mode=mode,
    )
    reranked = mode == "hybrid_rerank"
    reranker = LengthReranker() if reranked else None

    run = run_evaluation(
        settings,
        documents,
        questions,
        embeddings=DistinctEmbeddings(),
        language_model=None,
        reranker=reranker,
    )

    for result in run.results:
        question_id = result.retrieval.question.id
        hybrid = result.hybrid
        assert hybrid is not None, question_id
        # The search-only answer lists the evidence the evaluation ranked, in the same order.
        assert result.evidence_matches, question_id
        assert hybrid.rerank_failed is (False if reranked else None), question_id
        assert 0 <= hybrid.keyword_dropped <= hybrid.keyword_matches, question_id
        assert hybrid.keyword_matches <= settings.retrieval_candidates, question_id
        passages = [judged.passage for judged in result.retrieval.passages]
        assert 0 < len(passages) <= min(10, hybrid.candidates), question_id
        rankings = [passage.ranking for passage in passages]
        assert all(
            ranking is not None
            and ranking.fused_score is not None
            and (ranking.vector_rank is not None or ranking.keyword_rank is not None)
            for ranking in rankings
        ), question_id
        if reranked:
            scores = [ranking.rerank_score for ranking in rankings]
            assert scores == [float(len(passage.text)) for passage in passages], question_id
            assert scores == sorted(scores, reverse=True), question_id
        else:
            fused = [ranking.fused_score for ranking in rankings]
            assert fused == sorted(fused, reverse=True), question_id
            assert all(ranking.rerank_score is None for ranking in rankings), question_id
    assert any(result.hybrid and result.hybrid.keyword_matches for result in run.results)
    if reranker is not None:
        assert reranker.calls[0] == ("A warm-up question?", ["A warm-up passage."])
        # Each question twice: for the evaluation's ranking, and for the answer.
        assert len(reranker.calls) == 1 + 2 * len(questions)

    report = build_report(
        run,
        command=f"python -m app.cli evaluate --retrieval-mode {mode}",
        questions_sha256=questions_sha256(EVALUATION_DIR / "questions.jsonl"),
    )

    assert report["config"]["retrieval_mode"] == mode
    assert report["config"]["retrieval_candidates"] == settings.retrieval_candidates
    assert report["config"]["rrf_k"] == settings.rrf_k
    # The thresholds were tried on passages ranked by meaning alone; here they'd mislead.
    assert report["recommendation"] is None
    assert report["threshold_sweep"] is None
    summary = report["hybrid_search"]
    assert summary["questions"] == len(questions)
    assert summary["keyword_matches"] == sum(
        result.hybrid.keyword_matches for result in run.results if result.hybrid
    )
    assert summary["rerank_failed"] == (
        {"count": 0, "of": len(questions), "share": 0.0} if reranked else None
    )
    for question in report["questions"]:
        assert set(question["hybrid_search"]) == {
            "candidates",
            "keyword_matches",
            "keyword_dropped",
            "rerank_failed",
        }
        for passage in question["passages"]:
            assert {"vector_rank", "keyword_rank", "fused_score", "rerank_score"} <= set(passage)
    assert compare_reports(report, copy.deepcopy(report)) == []
    lines = summary_lines(report)
    assert lines[1].startswith(f"Search mode: {mode} (by meaning and by keywords, ")
    assert lines[2].endswith(", over the passages above the minimum similarity:")
    assert any(line.startswith("Keyword search: passages for ") for line in lines)
    assert any(line.startswith("Reranker failed: ") for line in lines) is reranked
    assert not any(line.startswith("The rules pick") for line in lines)
    assert lines[-1] == f"Evidence matches the search: {len(questions)}/{len(questions)}"


@pytest.mark.integration
def test_with_a_model_its_prompts_replies_and_fallbacks_are_kept(
    database_url: str, tmp_path: Path
) -> None:
    documents = [build_document("notes.txt", b"Project records are kept for seven years.\n")]
    questions = [
        answerable("a01", "How long are project records kept?"),
        EvalQuestion.model_validate(
            {"id": "u01", "category": "unanswerable", "question": "Where are project records kept?"}
        ),
        answerable("a02", "For how many years are project records kept?"),
    ]
    # The first reply answers the warm-up; the last question finds the model out of replies.
    model = ScriptedLanguageModel(
        "ready", "Records are kept for seven years [S1].", "INSUFFICIENT_EVIDENCE"
    )
    settings = make_settings(
        database_url=database_url,
        storage_dir=tmp_path / "storage",
        retrieval_min_similarity=0.0,
    )

    run = run_evaluation(
        settings, documents, questions, embeddings=HashingEmbeddings(), language_model=model
    )

    assert len(model.prompts) == 4
    answered, declined, fallback = (result.score for result in run.results)
    assert answered.outcome.answer.mode is AnswerMode.GENERATED
    assert answered.outcome.answer.text == "Records are kept for seven years [1]."
    assert answered.outcome.reply == "Records are kept for seven years [S1]."
    assert answered.outcome.prompt is not None
    assert "Question: How long are project records kept?" in answered.outcome.prompt
    assert answered.facts_supported == {0}
    assert declined.outcome.answer.abstention_reason is AbstentionReason.INSUFFICIENT_EVIDENCE
    assert declined.outcome.reply == "INSUFFICIENT_EVIDENCE"
    assert fallback.outcome.answer.mode is AnswerMode.SEARCH_ONLY
    assert fallback.outcome.answer.model_name == "scripted-model"
    assert fallback.outcome.reply is None
    assert all(result.evidence_matches for result in run.results)
    # Timed even when the model doesn't reply.
    assert all(result.model_seconds is not None for result in run.results)

    report = build_report(
        run, command="python -m app.cli evaluate --with-model", questions_sha256="0" * 64
    )

    assert report["run"]["mode"] == "with_model"
    assert report["config"]["language_model"] == "scripted-model"
    assert report["checks"]["model_unavailable"] == {"count": 1, "of": 3, "share": 0.3333}
    assert report["answers"]["with_facts"]["all_facts_stated"] == {
        "count": 1,
        "of": 2,
        "share": 0.5,
    }
    assert report["timing"]["model_seconds"]["count"] == 3
    lines = summary_lines(report)
    assert lines[0].startswith("With model: 3 questions (2 answerable, 1 unanswerable)")
    # The fallback that lists passages counts as an answer; the last line counts the fallbacks.
    assert any(line.startswith("Answers: 2/2 questions with facts answered") for line in lines)
    assert (
        "  every fact stated: 1/2; facts stated 1/2, of which supported by a citation 1/1" in lines
    )
    # None of these questions has forbidden text to look for.
    assert report["answers"]["forbidden_text"]["questions"] == 0
    assert not any(line.startswith("Forbidden text") for line in lines)
    assert lines[-1] == "Model didn't reply: 1/3"


@pytest.mark.integration
def test_a_document_the_app_refuses_stops_the_run(database_url: str, tmp_path: Path) -> None:
    broken = CorpusDocument("broken.pdf", PDF_MIME, b"Not a PDF.", "broken.pdf.md", "0" * 64)
    settings = make_settings(database_url=database_url, storage_dir=tmp_path / "storage")

    with pytest.raises(
        EvaluationError,
        match=re.escape("broken.pdf wasn't accepted: This file doesn't look like a PDF."),
    ):
        run_evaluation(settings, [broken], [], embeddings=HashingEmbeddings(), language_model=None)

    assert stored_files(settings.storage_dir) == []


@pytest.mark.integration
def test_a_document_that_fails_to_index_stops_the_run(database_url: str, tmp_path: Path) -> None:
    blank = CorpusDocument("blank.pdf", PDF_MIME, pdf_bytes(""), "blank.pdf.md", "0" * 64)
    settings = make_settings(database_url=database_url, storage_dir=tmp_path / "storage")

    with pytest.raises(EvaluationError, match=re.escape("blank.pdf wasn't indexed: No text")):
        run_evaluation(settings, [blank], [], embeddings=HashingEmbeddings(), language_model=None)
