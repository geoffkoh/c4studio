"""Starter workspaces shipped with the package.

The templates are **valid DSL exactly as they sit on disk** — no
placeholder syntax to substitute before they mean anything. That is
deliberate: it lets the test suite parse every shipped template directly
and assert it renders, which is the only thing that stops a starter
workspace shipping broken. A template that must be rendered through a
substitution pass first can only be checked after it, and the check is
easy to skip.

Naming the workspace is therefore a literal replacement of
:data:`DEFAULT_NAME`, not a template language.
"""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass

# The workspace name every template carries, and the exact string `--name`
# replaces. Quoted at the replacement site so a stray occurrence in prose
# cannot be hit by accident.
DEFAULT_NAME = "My Workspace"

_SUFFIX = ".dsl"


@dataclass(frozen=True)
class Template:
    """One starter workspace.

    Attributes:
        name: The identifier passed to ``c4 new --template``.
        summary: One line, from the template's first comment.
        content: The DSL itself.
    """

    name: str
    summary: str
    content: str


class TemplateError(LookupError):
    """Raised when a template name does not exist."""


def _summarise(content: str) -> str:
    """First comment line of a template, used as its one-line description."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            return stripped.lstrip("/").strip()
        if stripped:
            break
    return ""


def _directory() -> importlib.resources.abc.Traversable:
    return importlib.resources.files("c4studio") / "templates"


def list_templates() -> list[Template]:
    """Every shipped template, ordered simplest first.

    The order is explicit rather than alphabetical: someone running
    ``c4 new`` for the first time should meet ``minimal`` before
    ``full-c4``.
    """
    order = ["minimal", "system-context", "full-c4", "deployment"]
    found = {
        entry.name[: -len(_SUFFIX)]
        for entry in _directory().iterdir()
        if entry.name.endswith(_SUFFIX)
    }
    # Anything added to the directory but not to `order` still appears,
    # rather than silently not shipping.
    names = [name for name in order if name in found] + sorted(found - set(order))
    return [get_template(name) for name in names]


def get_template(name: str) -> Template:
    """Load one template by name.

    Raises:
        TemplateError: If no template of that name is shipped.
    """
    entry = _directory() / f"{name}{_SUFFIX}"
    try:
        content = entry.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        available = ", ".join(template.name for template in list_templates())
        raise TemplateError(
            f"Unknown template {name!r}. Available: {available}"
        ) from exc
    return Template(name=name, summary=_summarise(content), content=content)


def render(name: str, workspace_name: str | None = None) -> str:
    """Return a template's DSL, optionally renamed.

    Args:
        name: Template identifier.
        workspace_name: Replaces :data:`DEFAULT_NAME`. ``None`` leaves the
            template exactly as shipped.
    """
    content = get_template(name).content
    if workspace_name is None or workspace_name == DEFAULT_NAME:
        return content
    # Quoted, and only the first: the name appears once, in the workspace
    # declaration, and prose in the comments must not be rewritten.
    return content.replace(f'"{DEFAULT_NAME}"', f'"{workspace_name}"', 1)
