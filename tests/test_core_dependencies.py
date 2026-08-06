"""The core must import with no third-party packages installed (PP-97).

`click`, `pydantic`, `fastapi` and `uvicorn` are for the CLI and the web
app; parsing, generation, export and rendering are stdlib-only. That was
true by accident of layering rather than by declaration until the wheel
turned out to be uninstallable under Pyodide (PP-96), so it is asserted
here: the modules are hidden with an import hook and the core is exercised
without them.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

#: Packages the core must never need at import or run time.
FORBIDDEN = ("pydantic", "fastapi", "uvicorn", "click")

_PROGRAM = """
import sys

class Blocker:
    def find_module(self, name, path=None):
        return self.find_spec(name, path)

    def find_spec(self, name, path=None, target=None):
        root = name.split(".")[0]
        if root in {forbidden!r}:
            raise ImportError(f"blocked by the test: {{root}}", name=root)
        return None

sys.meta_path.insert(0, Blocker())

# The whole core path: parse, export, generate, and build view graphs.
from pystructurizr.parser.dsl import parse_dsl
from pystructurizr.generators.json_export import export_json
from pystructurizr.generators.mermaid import MermaidGenerator
from pystructurizr.generators.flowchart import FlowchartGenerator
from pystructurizr.graph.view_graph import build_view_graph
from pystructurizr.webapp.graph import react_flow_graph
from pystructurizr.icons import inline_icons

workspace = parse_dsl(open({source!r}).read())
view = workspace.views[0]
assert export_json(workspace)
assert MermaidGenerator(workspace).generate_view(view).startswith("C4")
assert FlowchartGenerator(workspace).generate_view(view).startswith("---")
assert build_view_graph(workspace, view)["nodes"]
assert react_flow_graph(workspace, view)["nodes"]

for blocked in {forbidden!r}:
    assert blocked not in sys.modules, blocked

print("core ok")
"""


def _run_without(source: Path) -> subprocess.CompletedProcess[str]:
    program = _PROGRAM.format(forbidden=FORBIDDEN, source=str(source))
    return subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_core_imports_and_runs_without_third_party_packages() -> None:
    result = _run_without(ROOT / "samples" / "internet_banking.dsl")
    assert result.returncode == 0, result.stderr[-2000:]
    assert "core ok" in result.stdout


def test_render_module_needs_no_third_party_packages() -> None:
    """`render` shells out to node; nothing it imports may need the extras."""
    program = _PROGRAM.split("# The whole core path")[0] + (
        "from pystructurizr.render import render_view, renderer_script\n"
        "assert renderer_script().name.endswith('.mjs')\n"
        "print('core ok')\n"
    ).replace("{forbidden!r}", repr(FORBIDDEN))
    result = subprocess.run(
        [sys.executable, "-c", program.format(forbidden=FORBIDDEN, source="")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr[-2000:]


@pytest.fixture(scope="module")
def pyproject() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        data: dict[str, object] = tomllib.load(handle)
    return data


class TestDistribution:
    def test_base_dependencies_are_pure_python(
        self, pyproject: dict[str, object]
    ) -> None:
        """Anything here must install under micropip in a browser."""
        project = pyproject["project"]
        assert isinstance(project, dict)
        names = {str(d).split(">")[0].split("[")[0] for d in project["dependencies"]}
        assert names == {"click"}, (
            f"base dependencies grew to {names}; anything beyond pure-Python "
            "packages breaks the wheel under Pyodide (PP-96/PP-97)"
        )

    def test_the_web_stack_is_an_extra(self, pyproject: dict[str, object]) -> None:
        project = pyproject["project"]
        assert isinstance(project, dict)
        extras = project["optional-dependencies"]
        assert isinstance(extras, dict)
        webapp = {str(d).split(">")[0].split("[")[0] for d in extras["webapp"]}
        assert webapp == {"pydantic", "fastapi", "uvicorn"}
