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
