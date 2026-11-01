"""Retrieval rules (Phase 7, D-81): a keyword query from a question, and reciprocal rank fusion.

Hybrid search runs a vector search and a keyword search over the same passages and merges
their rankings. Both steps are pure functions, so their edge cases are tested without a
database.
"""

import math
import re
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from typing import Literal, get_args

# "vector" compares meanings only, as in Phases 4 to 6. "hybrid" also matches the question's
# words and merges both rankings. "hybrid_rerank" then has a cross-encoder reorder the result.
RetrievalMode = Literal["vector", "hybrid", "hybrid_rerank"]
RETRIEVAL_MODES: tuple[RetrievalMode, ...] = get_args(RetrievalMode)

# Runs of letters and digits, in any script. Quotes, dashes, and other punctuation only separate
# words, so nothing typed in a question can become a text-search operator.
_WORD = re.compile(r"[^\W_]+")
# The only word that PostgreSQL's websearch_to_tsquery reads as an operator. It's an English
# stop word as well, so leaving it out loses nothing.
_OPERATOR_WORDS = frozenset({"or"})


def keyword_query(question: str) -> str:
    """The question's words joined with `or`, for websearch_to_tsquery; empty if it has none.

    A passage then matches if it contains any of the words, after stemming and without stop
    words. A repeated word is kept once, in the form it first appears in.
    """
    words: dict[str, str] = {}
    for word in _WORD.findall(question):
        key = word.casefold()
        if key not in _OPERATOR_WORDS:
            words.setdefault(key, word)
    return " or ".join(words.values())


@dataclass(frozen=True)
class Fused[T: Hashable]:
    item: T
    # The sum of 1 / (k + rank) over the rankings that list the item.
    score: float
    # The item's rank in each ranking, from 1, or None where it isn't listed.
    ranks: tuple[int | None, ...]

    @property
    def best_rank(self) -> int:
        return min(rank for rank in self.ranks if rank is not None)


def reciprocal_rank_fusion[T: Hashable](rankings: Sequence[Sequence[T]], k: int) -> list[Fused[T]]:
    """Merge rankings by reciprocal rank fusion (Cormack, Clarke, and Büttcher, 2009).

    Each item scores the sum of 1 / (k + rank) over the rankings that list it, and the best
    score comes first. Equal scores go to the better best rank, then to the item seen first,
    reading the rankings in order. An item listed twice in one ranking keeps its first rank.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    ranks: dict[T, list[int | None]] = {}
    for position, ranking in enumerate(rankings):
        for rank, item in enumerate(ranking, 1):
            item_ranks = ranks.setdefault(item, [None] * len(rankings))
            if item_ranks[position] is None:
                item_ranks[position] = rank
    fused = [
        # fsum is exact, so the same ranks give the same score whatever their order.
        Fused(item, math.fsum(1 / (k + rank) for rank in found if rank is not None), tuple(found))
        for item, found in ranks.items()
    ]
    # A stable sort, so remaining ties keep the order in which the items were first seen.
    fused.sort(key=lambda entry: (-entry.score, entry.best_rank))
    return fused
