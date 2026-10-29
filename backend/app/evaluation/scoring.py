"""Scoring (P5-02): what retrieval found and what the app answered, judged against the
reviewed questions. Pure functions, so the rules are easy to read and to test.

A passage is *relevant* to a question when it states one of the question's expected facts. The
dataset's consistency check makes sure no other part of the corpus states them, so a relevant
passage also comes from one of the question's expected sources.
"""

import statistics
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Self

from app.domain.questions import AnswerMode, AnswerRecord, Passage
from app.evaluation.dataset import EvalQuestion, MatchText

Json = dict[str, Any]

# Passages retrieved for each question; retrieval metrics are reported at these cut-offs.
SEARCH_LIMIT = 10
K_VALUES = (1, 3, 5, 10)
# The evidence thresholds tried: 0.30, 0.35, and so on up to 0.90.
THRESHOLD_GRID = tuple(round(0.30 + 0.05 * step, 2) for step in range(13))
# How far below the highest threshold that loses no expected fact the recommendation goes,
# because a small question set can't show how close the next question's passages will score.
THRESHOLD_MARGIN = 0.05
_DECIMALS = 4


@dataclass(frozen=True)
class FoundPassage:
    """A retrieved passage, identified by where it comes from rather than by database IDs."""

    document: str
    page_number: int | None
    section: str | None
    text: str
    similarity: float

    @classmethod
    def of(cls, passage: Passage) -> Self:
        return cls(
            passage.document_name,
            passage.page_number,
            passage.section,
            passage.text,
            passage.similarity,
        )


@dataclass(frozen=True)
class JudgedPassage:
    passage: FoundPassage
    # The passage comes from one of the question's expected sources.
    expected_source: bool
    # The indexes of the question's expected facts that the passage states.
    facts: frozenset[int]

    @property
    def relevant(self) -> bool:
        return bool(self.facts)

    def to_json(self) -> Json:
        return {
            "document": self.passage.document,
            "page": self.passage.page_number,
            "section": self.passage.section,
            "similarity": round(self.passage.similarity, _DECIMALS),
            "expected_source": self.expected_source,
            "facts": sorted(self.facts),
        }


def stated_facts(question: EvalQuestion, text: str | None) -> frozenset[int]:
    """The indexes of the question's expected facts that the text states."""
    if not text:
        return frozenset()
    match = MatchText(text)
    return frozenset(
        index for index, group in enumerate(question.expected_facts) if match.contains_any(group)
    )


def judge(question: EvalQuestion, passages: Iterable[FoundPassage]) -> tuple[JudgedPassage, ...]:
    return tuple(
        JudgedPassage(
            passage,
            question.expects(passage.document, passage.page_number, passage.section),
            stated_facts(question, passage.text),
        )
        for passage in passages
    )


@dataclass(frozen=True)
class Retrieval:
    """The passages retrieved for one question, closest first."""

    question: EvalQuestion
    passages: tuple[JudgedPassage, ...]

    def evidence(self, k: int, threshold: float | None = None) -> list[JudgedPassage]:
        """What the app would treat as evidence: the closest `k`, without those below
        `threshold`, compared exactly as the app compares them."""
        return [
            passage
            for passage in self.passages[:k]
            if threshold is None or passage.passage.similarity >= threshold
        ]

    def facts_found(self, k: int, threshold: float | None = None) -> frozenset[int]:
        return frozenset().union(*(passage.facts for passage in self.evidence(k, threshold)))

    def complete(self, k: int, threshold: float | None = None) -> bool:
        return len(self.facts_found(k, threshold)) == len(self.question.expected_facts)

    @property
    def first_relevant_rank(self) -> int | None:
        return next(
            (rank for rank, passage in enumerate(self.passages, 1) if passage.relevant), None
        )


def retrieval_summary(retrievals: Sequence[Retrieval]) -> Json:
    """Hit rate, fact recall, and mean reciprocal rank, over the questions with expected facts.

    - hit: at least one of the top k passages states an expected fact.
    - source_hit: at least one of them comes from an expected source, stating a fact or not.
    - all_facts: the top k passages state every expected fact between them.
    - fact_recall: the mean share of expected facts stated in the top k passages.
    - mrr: the mean of 1/rank of the first passage stating a fact (0 if none of the 10 does).
    """
    scored = [retrieval for retrieval in retrievals if retrieval.question.expected_facts]
    at_k: Json = {}
    for k in K_VALUES:
        at_k[str(k)] = {
            "hit": count_true(bool(retrieval.facts_found(k)) for retrieval in scored),
            "source_hit": count_true(
                any(passage.expected_source for passage in retrieval.passages[:k])
                for retrieval in scored
            ),
            "all_facts": count_true(retrieval.complete(k) for retrieval in scored),
            "fact_recall": _mean(
                len(retrieval.facts_found(k)) / len(retrieval.question.expected_facts)
                for retrieval in scored
            ),
        }
    reciprocal_ranks = [
        1 / rank if (rank := retrieval.first_relevant_rank) else 0.0 for retrieval in scored
    ]
    return {"questions": len(scored), "at_k": at_k, "mrr": _mean(reciprocal_ranks)}


def evidence_outcome(retrievals: Sequence[Retrieval], k: int, threshold: float | None) -> Json:
    """What the app would do with `k` passages per question and this evidence threshold: how
    often questions with expected facts keep a relevant passage, keep every fact, or are
    declined for weak evidence, and how often questions without expected facts are declined."""
    with_facts = [retrieval for retrieval in retrievals if retrieval.question.expected_facts]
    without_facts = [retrieval for retrieval in retrievals if not retrieval.question.expected_facts]
    return {
        "k": k,
        "threshold": threshold,
        "with_facts": {
            "kept_relevant": count_true(
                bool(retrieval.facts_found(k, threshold)) for retrieval in with_facts
            ),
            "kept_all_facts": count_true(
                retrieval.complete(k, threshold) for retrieval in with_facts
            ),
            "declined": count_true(
                not retrieval.evidence(k, threshold) for retrieval in with_facts
            ),
        },
        "without_facts": {
            "declined": count_true(
                not retrieval.evidence(k, threshold) for retrieval in without_facts
            ),
        },
    }


def threshold_sweep(retrievals: Sequence[Retrieval], max_k: int) -> list[Json]:
    """`evidence_outcome` for each number of passages up to `max_k`, without a threshold and
    with each one on the grid."""
    return [
        evidence_outcome(retrievals, k, threshold)
        for k in range(1, max_k + 1)
        for threshold in (None, *THRESHOLD_GRID)
    ]


def recommend_settings(retrievals: Sequence[Retrieval], max_k: int) -> Json:
    """The retrieval settings that two rules, fixed before any results were seen, pick.

    1. Passages per question (`RETRIEVAL_TOP_K`): the smallest k, up to `max_k`, whose passages
       state every expected fact for as many questions as `max_k` passages do. `max_k` is how
       many full-size chunks fit in the answer's context budget; more would never reach the
       model.
    2. Evidence threshold (`RETRIEVAL_MIN_SIMILARITY`): the highest grid value that removes no
       expected fact from any question's top k passages, minus `THRESHOLD_MARGIN`.

    Also reports the exact similarity below which a fact would be lost, and the highest
    similarity of any passage retrieved for a question without expected facts: a threshold
    between the two would decline those questions without losing a fact.
    """
    if max_k < 1:
        raise ValueError("max_k must be at least 1")
    with_facts = [retrieval for retrieval in retrievals if retrieval.question.expected_facts]
    without_facts = [retrieval for retrieval in retrievals if not retrieval.question.expected_facts]
    complete = {
        k: sum(retrieval.complete(k) for retrieval in with_facts) for k in range(1, max_k + 1)
    }
    top_k = min(k for k, count in complete.items() if count == complete[max_k])
    lossless = [
        threshold
        for threshold in THRESHOLD_GRID
        if all(
            retrieval.facts_found(top_k, threshold) == retrieval.facts_found(top_k)
            for retrieval in with_facts
        )
    ]
    highest = max(lossless) if lossless else None
    # The best passage for each fact found; losing the weakest of those loses a fact.
    needed = [
        max(
            passage.passage.similarity
            for passage in retrieval.passages[:top_k]
            if fact in passage.facts
        )
        for retrieval in with_facts
        for fact in retrieval.facts_found(top_k)
    ]
    unwanted = [
        retrieval.passages[0].passage.similarity
        for retrieval in without_facts
        if retrieval.passages
    ]
    return {
        "max_k": max_k,
        "all_facts_by_k": {str(k): count for k, count in complete.items()},
        "top_k": top_k,
        "highest_lossless_threshold": highest,
        "min_similarity": round(highest - THRESHOLD_MARGIN, 2) if highest is not None else None,
        "lowest_needed_similarity": _round(min(needed)) if needed else None,
        "highest_similarity_without_facts": _round(max(unwanted)) if unwanted else None,
    }


@dataclass(frozen=True)
class AnswerOutcome:
    """What the app answered one question, and what its model was shown and replied."""

    answer: AnswerRecord
    # The prompt's user message, holding the passages and the question, if a model was asked.
    prompt: str | None
    # The model's reply before its citations were checked.
    reply: str | None
    seconds: float


@dataclass(frozen=True)
class AnswerScore:
    question: EvalQuestion
    outcome: AnswerOutcome
    citations: tuple[JudgedPassage, ...]
    facts_stated: frozenset[int]
    forbidden_in_answer: tuple[str, ...]
    forbidden_in_reply: tuple[str, ...]
    forbidden_in_prompt: tuple[str, ...]

    @property
    def abstained(self) -> bool:
        return self.outcome.answer.abstained

    @property
    def facts_supported(self) -> frozenset[int]:
        """Stated facts that a cited passage also states."""
        cited = frozenset().union(*(citation.facts for citation in self.citations))
        return self.facts_stated & cited

    def to_json(self) -> Json:
        answer = self.outcome.answer
        return {
            "mode": answer.mode.value,
            "abstention_reason": (
                answer.abstention_reason.value if answer.abstention_reason else None
            ),
            "text": answer.text,
            "reply": self.outcome.reply,
            "citations": [citation.to_json() for citation in self.citations],
            "facts_stated": sorted(self.facts_stated),
            "facts_supported": sorted(self.facts_supported),
            "forbidden_in_answer": list(self.forbidden_in_answer),
            "forbidden_in_reply": list(self.forbidden_in_reply),
            "forbidden_in_prompt": list(self.forbidden_in_prompt),
        }


def score_answer(question: EvalQuestion, outcome: AnswerOutcome) -> AnswerScore:
    answer = outcome.answer
    return AnswerScore(
        question,
        outcome,
        judge(question, (FoundPassage.of(citation.passage) for citation in answer.citations)),
        stated_facts(question, answer.text),
        _forbidden(question, answer.text),
        _forbidden(question, outcome.reply),
        _forbidden(question, outcome.prompt),
    )


def answer_summary(scores: Sequence[AnswerScore]) -> Json:
    """How the app's answers turned out.

    A citation is correct when the passage it points to states one of the question's expected
    facts. Without a language model, the answer is the evidence itself, so there is no answer
    text to check for facts.
    """
    with_facts = [score for score in scores if score.question.expected_facts]
    without_facts = [score for score in scores if not score.question.expected_facts]
    with_text = any(score.outcome.answer.mode is AnswerMode.GENERATED for score in scores)
    citations = [citation for score in with_facts for citation in score.citations]
    stated = sum(len(score.facts_stated) for score in with_facts)
    summary: Json = {
        "with_facts": {
            "questions": len(with_facts),
            "answered": count_true(not score.abstained for score in with_facts),
            "abstention_reasons": _reasons(with_facts),
            "cites_relevant": count_true(
                any(citation.relevant for citation in score.citations) for score in with_facts
            ),
            "correct_citations": count_true(citation.relevant for citation in citations),
        },
        "without_facts": {
            "questions": len(without_facts),
            "abstained": count_true(score.abstained for score in without_facts),
            "abstention_reasons": _reasons(without_facts),
        },
        "forbidden_text": _forbidden_summary(scores),
    }
    if with_text:
        summary["with_facts"] |= {
            "all_facts_stated": count_true(
                len(score.facts_stated) == len(score.question.expected_facts)
                for score in with_facts
            ),
            "facts_stated": ratio(
                stated, sum(len(score.question.expected_facts) for score in with_facts)
            ),
            "facts_supported_by_citations": ratio(
                sum(len(score.facts_supported) for score in with_facts), stated
            ),
        }
    return summary


@dataclass(frozen=True)
class IndexComparison:
    """One question's closest chunks found three ways, and how each search read the chunks:
    the app's own query as the planner runs it, the HNSW index forced, and an exact scan."""

    default: tuple[uuid.UUID, ...]
    index: tuple[uuid.UUID, ...]
    exact: tuple[uuid.UUID, ...]
    plans: dict[str, str]


def index_summary(comparisons: Sequence[IndexComparison], top_k: int) -> Json:
    return {
        "questions": len(comparisons),
        "plans": {
            mode: dict(Counter(comparison.plans[mode] for comparison in comparisons))
            for mode in ("default", "index", "exact")
        },
        "index_same_order_as_exact": count_true(
            comparison.index == comparison.exact for comparison in comparisons
        ),
        "index_same_top_k_as_exact": count_true(
            set(comparison.index[:top_k]) == set(comparison.exact[:top_k])
            for comparison in comparisons
        ),
        "index_mean_overlap_with_exact": _mean(
            len(set(comparison.index) & set(comparison.exact)) / len(comparison.exact)
            for comparison in comparisons
            if comparison.exact
        ),
        "default_same_order_as_exact": count_true(
            comparison.default == comparison.exact for comparison in comparisons
        ),
    }


def _forbidden(question: EvalQuestion, text: str | None) -> tuple[str, ...]:
    if not text or not question.forbidden_text:
        return ()
    match = MatchText(text)
    return tuple(phrase for phrase in question.forbidden_text if match.contains(phrase))


def _forbidden_summary(scores: Sequence[AnswerScore]) -> Json:
    guarded = [score for score in scores if score.question.forbidden_text]
    return {
        "questions": len(guarded),
        "in_answer": count_true(bool(score.forbidden_in_answer) for score in guarded),
        "in_reply": count_true(bool(score.forbidden_in_reply) for score in guarded),
        "in_prompt": count_true(bool(score.forbidden_in_prompt) for score in guarded),
    }


def _reasons(scores: Sequence[AnswerScore]) -> dict[str, int]:
    reasons = Counter(
        score.outcome.answer.abstention_reason.value
        for score in scores
        if score.outcome.answer.abstention_reason
    )
    return dict(sorted(reasons.items()))


def count_true(flags: Iterable[bool]) -> Json:
    """How many of the flags are true, out of how many, and the share."""
    values = list(flags)
    return ratio(sum(values), len(values))


def ratio(count: int, total: int) -> Json:
    """A count out of a total, and the share; the share is None when the total is 0."""
    return {"count": count, "of": total, "share": _round(count / total) if total else None}


def _mean(values: Iterable[float]) -> float | None:
    collected = list(values)
    return _round(statistics.fmean(collected)) if collected else None


def _round(value: float) -> float:
    return round(value, _DECIMALS)
