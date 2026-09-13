"""The assistant endpoint (PP-140).

The one route that sends data off the machine, so what is pinned here is
the shape of that: it is off unless asked for, the key is never stored or
echoed, and what gets sent is exactly what was disclosed.

No test in this file reaches the network. `propose` is substituted, and
the one test that exercises the real `propose` substitutes the SDK client
underneath it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from c4studio.webapp import assistant as assistant_module
from c4studio.webapp.server import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURES / "split_workspace", tmp_path / "split")
    return tmp_path


def _client(root: Path, **kwargs: Any) -> TestClient:
    client = TestClient(create_app(root=root, **kwargs))
    client.post("/api/load", json={"path": "split/workspace.dsl"})
    return client


def _body(**overrides: Any) -> dict[str, Any]:
    body = {
        "instruction": "add a person called Auditor",
        "path": "split/workspace.dsl",
        "content": "workspace {\n}\n",
    }
    body.update(overrides)
    return body


# --- the gate --------------------------------------------------------------


def test_off_by_default(root: Path) -> None:
    """Not a hidden button: the route itself refuses."""
    response = _client(root).post("/api/assistant", json=_body())
    assert response.status_code == 403
    assert "--assistant" in response.json()["detail"]


def test_capabilities_report_it_off(root: Path) -> None:
    features = _client(root).get("/api/capabilities").json()["features"]
    assert features["assistant"] is False


def test_capabilities_report_it_on(root: Path) -> None:
    features = _client(root, assistant=True).get("/api/capabilities").json()["features"]
    assert features["assistant"] is True


def test_viewer_never_gets_it(root: Path) -> None:
    """Nothing to apply a proposal to, so it is not offered."""
    client = _client(root, assistant=True, read_only=True)
    assert client.get("/api/capabilities").json()["features"]["assistant"] is False


# --- what leaves the machine ----------------------------------------------


def test_sends_the_whole_workspace_and_says_which_files(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disclosure has to be accurate, so it is derived, not written."""
    captured: dict[str, Any] = {}

    def fake_propose(
        request: assistant_module.AssistantRequest,
    ) -> assistant_module.AssistantReply:
        captured["request"] = request
        return assistant_module.AssistantReply(content="workspace {\n}\n", model="m")

    monkeypatch.setattr(assistant_module, "propose", fake_propose)
    response = _client(root, assistant=True).post("/api/assistant", json=_body())
    assert response.status_code == 200

    sent = {file.path for file in captured["request"].files}
    assert "split/workspace.dsl" in sent
    assert any("model/" in path for path in sent), "fragments must be included"
    assert set(response.json()["filesSent"]) == sent


def test_the_unsaved_buffer_wins_over_disk(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The assistant must see what the person is looking at."""
    captured: dict[str, Any] = {}

    def fake_propose(
        request: assistant_module.AssistantRequest,
    ) -> assistant_module.AssistantReply:
        captured["request"] = request
        return assistant_module.AssistantReply(content="x\n", model="m")

    monkeypatch.setattr(assistant_module, "propose", fake_propose)
    _client(root, assistant=True).post(
        "/api/assistant", json=_body(content="// UNSAVED EDIT\n")
    )
    target = next(
        f for f in captured["request"].files if f.path == "split/workspace.dsl"
    )
    assert target.content == "// UNSAVED EDIT\n"
    assert len([f for f in captured["request"].files if f.path == target.path]) == 1


def test_a_path_outside_the_root_is_refused(root: Path) -> None:
    client = _client(root, assistant=True)
    response = client.post("/api/assistant", json=_body(path="../escape.dsl"))
    assert response.status_code == 400


# --- the key ---------------------------------------------------------------


def test_the_key_is_never_in_a_response(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SHOULD-NEVER-APPEAR")
    monkeypatch.setattr(
        assistant_module,
        "propose",
        lambda request: assistant_module.AssistantReply(content="ok\n", model="m"),
    )
    response = _client(root, assistant=True).post("/api/assistant", json=_body())
    assert "SHOULD-NEVER-APPEAR" not in response.text


def test_a_missing_key_is_a_503_naming_the_variable(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """503, not 500: the server works, the operator has something to set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = _client(root, assistant=True).post("/api/assistant", json=_body())
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_key_present_reads_only_the_presence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert assistant_module.key_present() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert assistant_module.key_present() is True


# --- the reply -------------------------------------------------------------


def test_a_fenced_reply_is_unwrapped() -> None:
    """Asked for bare DSL; a fence reaching the editor becomes diff noise."""
    fenced = '```\nworkspace "W" {\n}\n```'
    assert assistant_module._strip_fence(fenced) == 'workspace "W" {\n}\n'


def test_a_plain_reply_gains_a_trailing_newline() -> None:
    assert assistant_module._strip_fence("workspace {\n}") == "workspace {\n}\n"


def test_a_refusal_is_reported_not_raised(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty diff would look like a bug; say what happened instead."""
    monkeypatch.setattr(
        assistant_module,
        "propose",
        lambda request: assistant_module.AssistantReply(
            content="", model="m", refused=True, refusal_reason="declined"
        ),
    )
    body = _client(root, assistant=True).post("/api/assistant", json=_body()).json()
    assert body["refused"] is True
    assert body["refusalReason"] == "declined"


def test_the_context_names_the_target_and_every_file() -> None:
    """What the model is actually shown, since that is the disclosure."""
    rendered = assistant_module._render_context(
        assistant_module.AssistantRequest(
            instruction="do the thing",
            target="a.dsl",
            files=[
                assistant_module.AssistantFile("a.dsl", "AAA"),
                assistant_module.AssistantFile("model/b.dsl", "BBB"),
            ],
        )
    )
    assert "The file to rewrite is: a.dsl" in rendered
    assert "--- model/b.dsl ---" in rendered
    assert "AAA" in rendered and "BBB" in rendered
    assert "do the thing" in rendered


def test_propose_builds_the_request_it_should(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real propose(), with the SDK client substituted underneath it.

    Pins the parameters that are wrong in ways no other test would catch:
    a stale model id, or `budget_tokens`, which Opus 5 rejects with a 400.
    """
    import anthropic

    captured: dict[str, Any] = {}

    class FakeMessages:
        def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return type(
                "Response",
                (),
                {
                    "stop_reason": "end_turn",
                    "model": assistant_module.MODEL,
                    "content": [type("Block", (), {"type": "text", "text": "DSL\n"})()],
                    "usage": type(
                        "Usage", (), {"input_tokens": 7, "output_tokens": 3}
                    )(),
                },
            )()

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.messages = FakeMessages()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)

    reply = assistant_module.propose(
        assistant_module.AssistantRequest(
            instruction="add a person",
            target="a.dsl",
            files=[assistant_module.AssistantFile("a.dsl", "workspace {\n}\n")],
        )
    )

    assert captured["model"] == "claude-opus-5"
    assert captured["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in str(captured["thinking"])
    assert captured["max_tokens"] == assistant_module.MAX_TOKENS
    assert "Structurizr DSL" in captured["system"]
    assert reply.content == "DSL\n"
    assert (reply.input_tokens, reply.output_tokens) == (7, 3)


def test_propose_without_a_key_does_not_construct_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail before any client exists, so nothing can pick up a stray key."""
    import anthropic

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a client was constructed without a key")

    monkeypatch.setattr(anthropic, "Anthropic", explode)
    with pytest.raises(assistant_module.AssistantUnavailable) as excinfo:
        assistant_module.propose(
            assistant_module.AssistantRequest(instruction="x", target="a.dsl")
        )
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)
