"""A hosted model's daily call limit, and which provider an answer records (P9-02, P9-03).

`HostedModel` stands in for a hosted provider: it says it is one, but nothing leaves the
computer.
"""

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import select

from app.db.models import LlmUsage
from app.domain.grounding import ChatMessage
from app.providers.llm import Generation
from tests.support import ScriptedLanguageModel, Workspace

pytestmark = pytest.mark.integration

RETENTION_TEXT = "Project records are kept for seven years."
QUESTION = "How long are project records kept?"
REPLY = "Project records are kept for seven years [S1]."


class HostedModel(ScriptedLanguageModel):
    provider = "openai_compatible"
    hosted = True

    def generate(self, messages: Any) -> Generation:
        generation = super().generate(messages)
        return Generation(generation.text, generation.model_name, 100, 7)


class LocalModel(ScriptedLanguageModel):
    provider = "ollama"
    hosted = False


def usage_rows(workspace: Workspace) -> list[LlmUsage]:
    with workspace.app.state.session_factory() as session:
        return list(session.scalars(select(LlmUsage)))


def test_an_answer_records_its_provider_and_a_local_one_counts_no_calls(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace(language_model=LocalModel(REPLY))
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    answer = workspace.ask(QUESTION)["answer"]

    assert answer["model_provider"] == "ollama"
    assert usage_rows(workspace) == []
    listed = workspace.client.get(f"/api/v1/workspaces/{workspace.id}/questions").json()
    assert listed["items"][0]["answer"]["model_provider"] == "ollama"


def test_a_hosted_call_is_counted_with_its_tokens(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace(language_model=HostedModel(REPLY, REPLY))
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    workspace.ask(QUESTION)
    answer = workspace.ask(QUESTION)["answer"]

    assert answer["model_provider"] == "openai_compatible"
    (row,) = usage_rows(workspace)
    assert (row.calls, row.prompt_tokens, row.completion_tokens) == (2, 200, 14)


def test_past_the_daily_limit_nothing_is_sent_and_the_passages_are_shown(
    make_workspace: Callable[..., Workspace],
) -> None:
    model = HostedModel(REPLY, REPLY, REPLY)
    workspace = make_workspace(language_model=model, llm_daily_call_limit=2)
    workspace.add("retention.txt", RETENTION_TEXT.encode())

    first = workspace.ask(QUESTION)["answer"]
    workspace.ask(QUESTION)
    third = workspace.ask(QUESTION)["answer"]

    assert first["mode"] == "generated"
    assert third["mode"] == "search_only"
    assert third["abstained"] is False
    assert third["citations"]
    assert len(model.prompts) == 2
    assert usage_rows(workspace)[0].calls == 2


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        (
            HostedModel(name="hosted-one"),
            {
                "provider": "openai_compatible",
                "model_name": "hosted-one",
                "sends_text_off_device": True,
            },
        ),
        (
            LocalModel(name="local-one"),
            {"provider": "ollama", "model_name": "local-one", "sends_text_off_device": False},
        ),
        (None, {"provider": None, "model_name": None, "sends_text_off_device": False}),
    ],
)
def test_the_model_endpoint_says_whether_text_leaves_the_computer(
    make_workspace: Callable[..., Workspace], model: Any, expected: dict[str, Any]
) -> None:
    workspace = make_workspace(language_model=model)
    assert workspace.client.get("/api/v1/model").json() == expected


def test_the_model_endpoint_needs_a_signed_in_user(
    make_workspace: Callable[..., Workspace],
) -> None:
    workspace = make_workspace(language_model=HostedModel())
    workspace.client.cookies.clear()
    assert workspace.client.get("/api/v1/model").status_code == 401


_ = ChatMessage
