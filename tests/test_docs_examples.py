"""Every DSL example in the docs is parsed (PP-184).

`docs/dsl-reference.md` exists so that someone — a person or an agent —
can write DSL for c4studio without reading the code. A reference that
drifts from the parser is worse than none: it is confidently wrong, and
nothing about reading it reveals that.

So the examples are the test. Each ```dsl block is parsed and must produce
no diagnostics, because a diagnostic means the parser *skipped* something
the example was demonstrating.

Blocks are either whole files (they start with `workspace`) or fragments
marked with a first line of `// in: model` or `// in: views`, which are
wrapped here in the smallest workspace that makes them valid. The marker
is also the reader's cue for where the snippet belongs.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from c4studio.parser.dsl import parse_dsl, parse_dsl_file

DOCS = Path(__file__).parent.parent / "docs"
REFERENCE = DOCS / "dsl-reference.md"

#: A fragment marked `// in: model` is wrapped in this.
MODEL_WRAPPER = """workspace "Example" {{
    model {{
{body}
    }}
    views {{
        systemLandscape "L" {{
            include *
        }}
    }}
}}
"""

#: A fragment marked `// in: views` gets a model with the identifiers the
#: examples reach for (`s`, `u`, `web`, `api`), so a views snippet can be
#: as short as the thing it is showing.
VIEWS_WRAPPER = """workspace "Example" {{
    model {{
        u = person "User"
        s = softwareSystem "Platform" {{
            web = container "Web"
            api = container "API"
        }}
        u -> web "Uses"
        web -> api "Calls"
    }}
    views {{
{body}
    }}
}}
"""


def _blocks(path: Path) -> list[tuple[int, str]]:
    """Every ```dsl block in `path`, with the line it starts on."""
    found: list[tuple[int, str]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    inside = False
    start = 0
    body: list[str] = []
    for number, line in enumerate(lines, start=1):
        if not inside and line.strip() == "```dsl":
            inside, start, body = True, number, []
            continue
        if inside and line.strip() == "```":
            found.append((start, "\n".join(body)))
            inside = False
            continue
        if inside:
            body.append(line)
    assert not inside, f"unclosed ```dsl block opened at line {start}"
    return found


def _wrap(block: str) -> str:
    """Put a fragment in the smallest workspace that makes it valid."""
    first = block.strip().splitlines()[0].strip()
    if first.startswith("// in: model"):
        return MODEL_WRAPPER.format(body=block)
    if first.startswith("// in: views"):
        return VIEWS_WRAPPER.format(body=block)
    assert block.lstrip().startswith("workspace"), (
        "a DSL example must be a whole workspace or start with "
        "`// in: model` or `// in: views`"
    )
    return block


def _ids() -> list[str]:
    return [f"line-{line}" for line, _ in _blocks(REFERENCE)]


def _scaffold(root: Path) -> None:
    """The files the file-context examples reference.

    `!docs`, `!adrs` and `!include` resolve against the DSL file, so an
    example using them can only be checked by parsing a real file with
    real neighbours — which also proves the paths in the reference are the
    shape that works.
    """
    (root / "docs").mkdir()
    (root / "docs" / "01-introduction.md").write_text("# Introduction\n", "utf-8")
    (root / "adrs").mkdir()
    (root / "adrs" / "0001-use-c4.md").write_text(
        "# 1. Use C4\n\nDate: 2026-01-01\n\n## Status\n\nAccepted\n", "utf-8"
    )
    (root / "model").mkdir()
    (root / "model" / "people.dsl").write_text('u = person "User"\n', "utf-8")
    (root / "model" / "systems.dsl").write_text('s = softwareSystem "S"\n', "utf-8")
    (root / "views").mkdir()
    (root / "views" / "context.dsl").write_text(
        'systemLandscape "Included" {\n    include *\n}\n', "utf-8"
    )


@pytest.mark.parametrize("block", [b for _, b in _blocks(REFERENCE)], ids=_ids())
def test_every_reference_example_parses_cleanly(block: str, tmp_path: Path) -> None:
    _scaffold(tmp_path)
    source = tmp_path / "example.dsl"
    source.write_text(_wrap(block), encoding="utf-8")
    with warnings.catch_warnings():
        # A diagnostic also warns; the assertion below is the check.
        warnings.simplefilter("ignore")
        workspace = parse_dsl_file(source)
    assert workspace.diagnostics == [], [
        (d.code, d.message) for d in workspace.diagnostics
    ]


def test_the_reference_has_examples_to_check() -> None:
    """A regex that silently matches nothing would pass every test above."""
    assert len(_blocks(REFERENCE)) >= 15


def test_no_example_claims_a_construct_the_parser_rejects() -> None:
    """The gotchas are real: each names something the parser refuses.

    Pinned so the *prose* cannot rot either — if any of these starts
    working, the reference is wrong and this test says so.
    """
    refused = {
        # An aliased group is skipped whole, contents and all.
        'g = group "X" { a = softwareSystem "A" }': "unsupported-block",
        # description belongs on the `->` line, not in the body.
        'a = softwareSystem "A"\nb = softwareSystem "B"\n'
        'a -> b "x" { description "no" }': "unknown-relationship-property",
        # healthCheck is gated on instances, here and upstream.
        'deploymentEnvironment "Live" {\n deploymentNode "N" {\n'
        ' infrastructureNode "I" {\n healthCheck "p" "https://x"\n }\n }\n}': (
            "unexpected-token"
        ),
    }
    for fragment, code in refused.items():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            workspace = parse_dsl(MODEL_WRAPPER.format(body=fragment))
        assert code in {d.code for d in workspace.diagnostics}, fragment
