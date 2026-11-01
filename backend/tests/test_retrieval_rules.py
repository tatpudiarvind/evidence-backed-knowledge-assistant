"""Hybrid search's pure rules (P7-03, P7-06; D-81): a question's keyword query, and reciprocal
rank fusion."""

import pytest

from app.domain.retrieval import RETRIEVAL_MODES, Fused, keyword_query, reciprocal_rank_fusion


def test_the_modes_are_vector_hybrid_and_hybrid_rerank() -> None:
    assert RETRIEVAL_MODES == ("vector", "hybrid", "hybrid_rerank")


@pytest.mark.parametrize(
    ("question", "query"),
    [
        (
            "How long are project records kept?",
            "How or long or are or project or records or kept",
        ),
        # Quotes, dashes, and other punctuation only separate words, so none becomes an operator.
        ('"seven years" -deleted', "seven or years or deleted"),
        ("Form ZX-41's purpose?", "Form or ZX or 41 or s or purpose"),
        ("snake_case (a) & b | !c <-> d:*", "snake or case or a or b or c or d"),
        # "or" is websearch_to_tsquery's one operator word, and a stop word too.
        ("Tea or coffee OR milk", "Tea or coffee or milk"),
        # A repeated word is kept once, in the form it first appears in.
        ("Records RECORDS records?", "Records"),
        # Only stop words: the query is kept, and PostgreSQL finds nothing for it.
        ("What is it?", "What or is or it"),
        ("Café naïve résumé", "Café or naïve or résumé"),
        ("会议 什么时候 开始", "会议 or 什么时候 or 开始"),
        ("Records of 2024", "Records or of or 2024"),
    ],
    ids=[
        "words",
        "quotes-and-dashes",
        "apostrophes",
        "operators",
        "or",
        "repeats",
        "stop-words",
        "accents",
        "other-scripts",
        "digits",
    ],
)
def test_a_question_becomes_its_words_joined_with_or(question: str, query: str) -> None:
    assert keyword_query(question) == query


@pytest.mark.parametrize("question", ["", "   ", "?!", "-- '' \"\" ()", "or OR Or", "_"])
def test_a_question_without_words_has_no_query(question: str) -> None:
    assert keyword_query(question) == ""


def test_fusion_adds_one_over_k_plus_rank_from_each_ranking() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "d"]], 60)

    scores = {entry.item: entry.score for entry in fused}
    assert scores == pytest.approx(
        {"a": 1 / 61, "b": 1 / 62, "c": 1 / 63 + 1 / 61, "d": 1 / 62}, abs=1e-15
    )
    assert [entry.item for entry in fused] == ["c", "a", "b", "d"]
    assert {entry.item: entry.ranks for entry in fused} == {
        "a": (1, None),
        "b": (2, None),
        "c": (3, 1),
        "d": (None, 2),
    }


def test_equal_scores_go_to_the_better_best_rank() -> None:
    # With k = 1: "late" scores 1/8 + 1/8 and "early" 1/4, exactly equal. "late" is seen first,
    # but "early" ranks 3rd somewhere, and "late" 7th at best.
    first = ["x1", "x2", "x3", "x4", "x5", "x6", "late"]
    second = ["y1", "y2", "early", "y4", "y5", "y6", "late"]

    fused = reciprocal_rank_fusion([first, second], 1)

    by_item = {entry.item: entry for entry in fused}
    assert by_item["early"].score == by_item["late"].score == 0.25
    order = [entry.item for entry in fused]
    assert order.index("early") < order.index("late")


def test_remaining_ties_keep_the_order_first_seen() -> None:
    assert [entry.item for entry in reciprocal_rank_fusion([["a"], ["b"]], 60)] == ["a", "b"]
    assert [entry.item for entry in reciprocal_rank_fusion([["b"], ["a"]], 60)] == ["b", "a"]


def test_the_same_ranks_give_the_same_score_in_any_order() -> None:
    forward = reciprocal_rank_fusion([["a", "b"], ["b", "a"]], 60)
    backward = reciprocal_rank_fusion([["b", "a"], ["a", "b"]], 60)

    assert forward[0].score == forward[1].score == backward[0].score == backward[1].score


def test_an_item_listed_twice_keeps_its_first_rank() -> None:
    [entry, other] = reciprocal_rank_fusion([["a", "b", "a"]], 60)

    assert entry == Fused("a", 1 / 61, (1,))
    assert other == Fused("b", 1 / 62, (2,))


def test_an_item_in_only_one_ranking_has_no_rank_in_the_other() -> None:
    [only] = reciprocal_rank_fusion([[], ["a"]], 60)

    assert only.ranks == (None, 1)
    assert only.best_rank == 1


@pytest.mark.parametrize("rankings", [[], [[]], [[], []]])
def test_fusing_nothing_gives_nothing(rankings: list[list[str]]) -> None:
    assert reciprocal_rank_fusion(rankings, 60) == []


@pytest.mark.parametrize("k", [0, -1])
def test_k_must_be_at_least_1(k: int) -> None:
    with pytest.raises(ValueError, match="k must be at least 1"):
        reciprocal_rank_fusion([["a"]], k)
