"""The assistant: the one part of c4studio that leaves the machine.

Everything else here is local-first by design. This module is not, and the
whole shape of it follows from saying so out loud:

* **Off unless asked for.** ``c4 webapp --assistant``; the default is off,
  and ``GET /api/capabilities`` reports which, so the UI cannot offer what
  the server will not do.
* **The key is read at the moment of use** from ``ANTHROPIC_API_KEY``. It
  is never stored on :class:`AppState`, never logged, never echoed back in
  a response, and never read from a config file — `CLAUDE.md` is explicit
  that a credential belongs in the environment.
* **The SDK is an optional extra.** ``pip install c4studio[assistant]``,
  imported lazily, so a wheel installed without it is byte-identical in
  behaviour to one built before this existed.
* **It returns text and executes nothing.** The reply is DSL for a person
  to read, diff and accept. Principle 1 again: the assistant is just
  another producer of text.

What is sent is the workspace source — every DSL file, with the caller's
unsaved buffer substituted for the file it belongs to. That is a
deliberate choice, made by the person running it, and the UI says so
before the first request rather than in a footnote.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# The one model this asks for. Named here rather than threaded through the
# API so a request cannot select a model — that would be a way to spend
# someone's budget by crafting a request.
MODEL = "claude-opus-5"
MAX_TOKENS = 16000

_SYSTEM = """\
You are helping someone edit a Structurizr DSL workspace in c4studio.

You will be given every DSL file in their workspace and told which one
they are editing. Reply with the complete, updated contents of that one
file and nothing else — no prose, no explanation, no markdown fence. The
reply is diffed against their editor buffer and shown for them to accept
or reject, so it must be the whole file, not a fragment or a patch.

Rules that matter:
- Preserve their comments, ordering and formatting wherever you can. A
  diff that rewrites untouched lines is one they cannot review.
- Keep `!include` directives exactly as they are. Fragments are separate
  files; you are only rewriting the one named.
- If what they asked for does not make sense, or you would have to guess
  at something important, return the file unchanged with a `//` comment
  at the top saying why. An unchanged file is a clear answer.
"""


class AssistantError(RuntimeError):
    """Raised when a request cannot be made, or the API refuses it."""


class AssistantUnavailableError(AssistantError):
    """Raised when the optional dependency or the API key is missing.

    Separate from :class:`AssistantError` because the fix is different:
    this one is the operator's to make, not a failure of the request.
    """


@dataclass(frozen=True)
class AssistantFile:
    """One file of workspace context."""

    path: str
    content: str


@dataclass(frozen=True)
class AssistantReply:
    """What came back. No key, no request id, nothing to leak."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    # Set when the model declined rather than answered, so the UI can say
    # so plainly instead of showing an empty diff.
    refused: bool = False
    refusal_reason: str = ""


@dataclass(frozen=True)
class AssistantRequest:
    """Everything one call sends.

    Attributes:
        instruction: What the person asked for, in their words.
        target: Root-relative path of the file to rewrite.
        files: The workspace source, buffer already substituted.
    """

    instruction: str
    target: str
    files: list[AssistantFile] = field(default_factory=list)


def sdk_installed() -> bool:
    """Whether the optional ``anthropic`` extra is importable."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def key_present() -> bool:
    """Whether an API key is in the environment. The value is never read."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _render_context(request: AssistantRequest) -> str:
    """Lay the workspace out for the model, target named explicitly."""
    parts = [
        f"The file to rewrite is: {request.target}",
        "",
        (
            "The workspace source follows. Each file is preceded by its "
            "root-relative path."
        ),
    ]
    for file in request.files:
        parts += ["", f"--- {file.path} ---", file.content]
    parts += ["", "What they asked for:", request.instruction]
    return "\n".join(parts)


def propose(request: AssistantRequest) -> AssistantReply:
    """Ask for a rewritten file. Returns text; executes nothing.

    Raises:
        AssistantUnavailableError: The optional dependency or the key is missing.
        AssistantError: The request failed, or produced no usable text.
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - exercised via sdk_installed
        raise AssistantUnavailableError(
            "The assistant needs the optional dependency: "
            "pip install 'c4studio[assistant]'"
        ) from exc

    if not key_present():
        raise AssistantUnavailableError(
            "ANTHROPIC_API_KEY is not set. The assistant reads it from the "
            "environment at the moment of use and never stores it."
        )

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": _render_context(request)}],
        )
    except anthropic.APIStatusError as exc:
        # Deliberately the message only. An exception repr can carry request
        # headers, and these are rendered straight into the editor.
        raise AssistantError(f"The API rejected the request: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise AssistantError(
            "Could not reach the API. This is the one feature that needs a "
            "network; everything else in c4studio works offline."
        ) from exc

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        return AssistantReply(
            content="",
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            refused=True,
            refusal_reason=getattr(details, "explanation", "") or "",
        )

    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
    if not text:
        raise AssistantError("The assistant returned nothing to apply.")

    return AssistantReply(
        content=_strip_fence(text),
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def _strip_fence(text: str) -> str:
    """Drop a markdown fence if one came back despite the instruction.

    Asked for bare DSL and told not to fence it — but a fence that reaches
    the editor becomes a diff full of ``` lines, so this is cheaper to
    tolerate than to be strict about.
    """
    lines = text.splitlines()
    if lines and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip() + "\n"
    return text if text.endswith("\n") else text + "\n"
