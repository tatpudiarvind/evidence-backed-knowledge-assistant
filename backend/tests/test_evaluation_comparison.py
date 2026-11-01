"""Comparing evaluation results files (P5-05), as CI does with the committed results."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app import cli
from app.cli import EVALUATION_DIR
from app.evaluation.report import (
    FORMAT_VERSION,
    ReportError,
    compare_reports,
    read_report,
    summary_lines,
    write_report,
)

COMMITTED = EVALUATION_DIR / "results" / "retrieval-only.json"
AGREE = "The results agree on the data, the settings, and the summary."


@pytest.fixture(scope="module")
def committed() -> dict[str, Any]:
    return read_report(COMMITTED)


@pytest.fixture
def report(committed: dict[str, Any]) -> dict[str, Any]:
    """A copy of the committed results, to change."""
    return copy.deepcopy(committed)


def test_results_agree_with_a_copy_of_themselves(
    committed: dict[str, Any], report: dict[str, Any]
) -> None:
    assert compare_reports(committed, report) == []


def test_timings_the_environment_and_each_questions_detail_are_not_compared(
    committed: dict[str, Any], report: dict[str, Any]
) -> None:
    report["run"]["started_at"] = "2000-01-01T00:00:00+00:00"
    report["run"]["seconds"] += 100
    report["environment"]["python"] = "3.12.0"
    report["environment"]["os"] = "Linux"
    report["timing"]["answer_seconds"]["median"] += 1
    report["questions"][0]["passages"][0]["similarity"] += 0.0001
    # Generated DOCX files' sizes depend on the zlib build.
    for document in report["data"]["documents"]:
        document["size_bytes"] += 1

    assert compare_reports(committed, report) == []


def test_changed_data_and_settings_are_listed(
    committed: dict[str, Any], report: dict[str, Any]
) -> None:
    report["data"]["questions_sha256"] = "0" * 64
    report["config"]["retrieval_top_k"] += 1
    del report["config"]["search_limit"]
    report["config"]["reranker"] = "synthetic"

    top_k = committed["config"]["retrieval_top_k"]
    assert compare_reports(committed, report) == [
        f'data.questions_sha256: "{committed["data"]["questions_sha256"]}" != "{"0" * 64}"',
        f"config.retrieval_top_k: {top_k} != {top_k + 1}",
        f"config.search_limit: {committed['config']['search_limit']} != (missing)",
        'config.reranker: (missing) != "synthetic"',
    ]


def test_changed_results_show_as_changed_summary_lines(
    committed: dict[str, Any], report: dict[str, Any]
) -> None:
    report["retrieval"]["at_k"]["1"]["hit"]["count"] -= 1
    before, after = summary_lines(committed), summary_lines(report)
    [line] = [
        number
        for number, (old, new) in enumerate(zip(before, after, strict=True), start=1)
        if old != new
    ]

    assert compare_reports(committed, report) == [
        "--- expected",
        "+++ actual",
        f"@@ -{line} +{line} @@",
        f"-{before[line - 1]}",
        f"+{after[line - 1]}",
    ]


def test_results_with_and_without_a_model_differ(committed: dict[str, Any]) -> None:
    with_model = read_report(EVALUATION_DIR / "results" / "with-model.json")

    differences = compare_reports(committed, with_model)

    model = json.dumps(with_model["config"]["language_model"])
    assert f"config.language_model: null != {model}" in differences


HYBRID_CONFIG = (
    "retrieval_mode",
    "retrieval_candidates",
    "rrf_k",
    "reranker_model",
    "reranker_model_revision",
)


def test_results_from_before_phase_7_searched_by_meaning(report: dict[str, Any]) -> None:
    for key in HYBRID_CONFIG:
        report["config"].pop(key, None)
    report.pop("hybrid_search", None)

    assert summary_lines(report)[1] == "Search mode: vector (by meaning)."


def test_hybrid_results_say_how_they_searched(
    committed: dict[str, Any], report: dict[str, Any]
) -> None:
    report["config"] |= {
        "retrieval_mode": "hybrid_rerank",
        "retrieval_candidates": 20,
        "rrf_k": 60,
        "reranker_model": "synthetic-reranker",
        "reranker_model_revision": "0" * 40,
    }
    report["recommendation"] = None
    report["threshold_sweep"] = None
    report["hybrid_search"] = {
        "questions": 66,
        "with_keyword_matches": {"count": 60, "of": 66, "share": 0.9091},
        "keyword_matches": 900,
        "keyword_dropped": 300,
        "evidence_from_keywords_only": {"count": 5, "of": 200, "share": 0.025},
        "rerank_failed": {"count": 1, "of": 66, "share": 0.0152},
    }

    lines = summary_lines(report)

    assert lines[1] == (
        "Search mode: hybrid_rerank (by meaning and by keywords, 20 candidates each, fused with "
        "RRF k 60, reranked by synthetic-reranker)."
    )
    assert lines[2].endswith(", over the passages above the minimum similarity:")
    assert (
        "Keyword search: passages for 60/66 questions, 900 in all, 300 of them below the minimum "
        "similarity; evidence found only by keywords 5/200"
    ) in lines
    assert "Reranker failed: 1/66" in lines
    # The recommended settings come from ranking by meaning alone.
    assert not any(line.startswith("The rules pick") for line in lines)
    assert any(
        line.startswith("config.retrieval_mode: ") and line.endswith(' != "hybrid_rerank"')
        for line in compare_reports(committed, report)
    )


def test_hybrid_results_without_a_reranker_say_nothing_about_one(report: dict[str, Any]) -> None:
    report["config"] |= {"retrieval_mode": "hybrid", "retrieval_candidates": 20, "rrf_k": 60}
    report["recommendation"] = None
    report["hybrid_search"] = {
        "questions": 1,
        "with_keyword_matches": {"count": 0, "of": 1, "share": 0.0},
        "keyword_matches": 0,
        "keyword_dropped": 0,
        "evidence_from_keywords_only": {"count": 0, "of": 0, "share": None},
        "rerank_failed": None,
    }

    lines = summary_lines(report)

    assert lines[1] == (
        "Search mode: hybrid (by meaning and by keywords, 20 candidates each, fused with RRF k 60)."
    )
    assert not any("rerank" in line.lower() for line in lines)


@pytest.mark.parametrize(
    "content",
    [None, b'{"format_version": ', b"\xff\xfe"],
    ids=["missing", "not JSON", "not UTF-8"],
)
def test_unreadable_results_files_are_refused(tmp_path: Path, content: bytes | None) -> None:
    path = tmp_path / "results.json"
    if content is not None:
        path.write_bytes(content)

    with pytest.raises(ReportError) as refused:
        read_report(path)

    assert str(refused.value).startswith(f"Can't read {path}: ")


@pytest.mark.parametrize(
    "content", [b"[]", b'{"format_version": 99}'], ids=["not an object", "another format"]
)
def test_files_in_another_format_are_refused(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "results.json"
    path.write_bytes(content)

    with pytest.raises(ReportError) as refused:
        read_report(path)

    assert str(refused.value) == f"{path} isn't a results file in format {FORMAT_VERSION}."


def test_the_command_says_when_results_agree(
    tmp_path: Path, report: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    report["run"]["seconds"] += 100
    write_report(tmp_path / "results.json", report)

    assert cli.main(["compare-results", str(COMMITTED), str(tmp_path / "results.json")]) == 0

    assert capsys.readouterr().out == f"{AGREE}\n"


def test_the_command_lists_differences(
    tmp_path: Path,
    committed: dict[str, Any],
    report: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    report["config"]["retrieval_top_k"] += 1
    path = tmp_path / "results.json"
    write_report(path, report)

    assert cli.main(["compare-results", str(COMMITTED), str(path)]) == 1

    top_k = committed["config"]["retrieval_top_k"]
    assert capsys.readouterr().out.splitlines() == [
        f"{path} differs from {COMMITTED}:",
        f"  config.retrieval_top_k: {top_k} != {top_k + 1}",
    ]


def test_the_command_refuses_unreadable_and_incomplete_files(
    tmp_path: Path, report: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    del report["retrieval"]
    incomplete = tmp_path / "incomplete.json"
    write_report(incomplete, report)

    assert cli.main(["compare-results", str(COMMITTED), str(tmp_path / "missing.json")]) == 2
    output = capsys.readouterr()
    assert output.err.startswith(f"Can't read {tmp_path / 'missing.json'}: ")
    assert output.out == ""

    assert cli.main(["compare-results", str(COMMITTED), str(incomplete)]) == 2
    output = capsys.readouterr()
    assert output.err == (
        "The results files can't be compared: one is incomplete (KeyError: 'retrieval').\n"
    )
    assert output.out == ""
