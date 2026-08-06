"""The published GitHub Action stays consistent with the CLI (PP-95).

The action is YAML calling this package's CLI, so nothing type-checks the
join between them: renaming a CLI flag would break every consumer of the
action silently, and only at run time. These tests are that join.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from pystructurizr.cli.main import cli

ROOT = Path(__file__).parent.parent
ACTION = ROOT / "action.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "diagrams.yml"


@pytest.fixture(scope="module")
def action() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def steps(action: dict[str, Any]) -> str:
    """Every shell script in the action, concatenated."""
    return "\n".join(
        step.get("run", "") for step in action["runs"]["steps"] if "run" in step
    )


def _script(action: dict[str, Any], name: str) -> str:
    """One step's script, by name — prose elsewhere must not match."""
    step = next(s for s in action["runs"]["steps"] if s.get("name") == name)
    script: str = step["run"]
    return script


def _step_index(action: dict[str, Any], name: str) -> int:
    return next(
        i for i, s in enumerate(action["runs"]["steps"]) if s.get("name") == name
    )


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _flags(command_name: str) -> set[str]:
    command = cli.commands[command_name]
    names: set[str] = set()
    for param in command.params:
        names.update(opt for opt in getattr(param, "opts", []) if opt.startswith("--"))
    return names


class TestActionMetadata:
    def test_is_a_composite_action(self, action: dict[str, Any]) -> None:
        assert action["runs"]["using"] == "composite"
        # Composite steps must each declare a shell or the action will not load.
        for step in action["runs"]["steps"]:
            if "run" in step:
                assert step.get("shell") == "bash", step.get("name")

    def test_declares_the_inputs_the_workflow_uses(
        self, action: dict[str, Any]
    ) -> None:
        assert set(action["inputs"]) >= {"workspace", "output", "view", "mode"}
        assert action["inputs"]["workspace"]["required"] is True
        # Everything else must default, so the minimal usage is one input.
        optional = set(action["inputs"]) - {"workspace"}
        for name in optional:
            assert "default" in action["inputs"][name], name

    def test_exposes_the_output_directory(self, action: dict[str, Any]) -> None:
        assert "diagrams-path" in action["outputs"]
        assert "changed" in action["outputs"]


class TestPythonSetup:
    """The runner default is older than this package's floor (PP-95).

    The first Actions run failed on exactly this: `pip install` refused
    the package because the runner's python3 was 3.12 and requires-python
    is >=3.13. The action now sets Python up itself, and these tests keep
    the two versions in step.
    """

    def test_sets_up_python_before_installing(self, action: dict[str, Any]) -> None:
        names = [step.get("name") for step in action["runs"]["steps"]]
        assert names.index("Set up Python") < names.index("Install pystructurizr")

    def test_setup_is_skippable(self, action: dict[str, Any]) -> None:
        step = next(
            s for s in action["runs"]["steps"] if s.get("name") == "Set up Python"
        )
        assert step["uses"].startswith("actions/setup-python@")
        # An empty input lets a workflow that already prepared Python skip it.
        assert step["if"] == "inputs.python-version != ''"

    def test_default_python_satisfies_requires_python(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        floor = re.search(r'requires-python = ">=([\d.]+)"', pyproject)
        assert floor is not None
        action_yaml = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
        default = str(action_yaml["inputs"]["python-version"]["default"])
        assert _version(default) >= _version(floor.group(1)), (
            f"action installs Python {default} but the package needs >={floor.group(1)}"
        )


class TestCliContract:
    """Every CLI flag the action types must actually exist."""

    def test_render_flags_exist(self, action: dict[str, Any]) -> None:
        # Only the lines that build the render command line — the same step
        # also shells out to git, whose flags are not ours to validate.
        argument_lines = [
            line
            for line in _script(action, "Render").splitlines()
            if "args=(" in line or "args+=(" in line
        ]
        used = set(re.findall(r"--[a-z-]+", "\n".join(argument_lines)))
        assert used, "the action no longer passes any render flags"
        assert used <= _flags("render"), used - _flags("render")

    def test_render_and_check_are_real_commands(self, steps: str) -> None:
        invoked = set(re.findall(r"pystructurizr (\w+)", steps))
        assert invoked <= set(cli.commands), invoked - set(cli.commands)
        assert {"render", "check"} <= invoked

    def test_it_checks_before_it_renders(self, action: dict[str, Any]) -> None:
        """A parse error should fail as diagnostics, not a half-render.

        Compared by step order, not by position in the concatenated
        scripts: the prerequisite step's error message mentions
        `pystructurizr render` too.
        """
        assert _step_index(action, "Check the workspace") < _step_index(
            action, "Render"
        )
        assert "pystructurizr check" in _script(action, "Check the workspace")
        assert "pystructurizr render" in _script(action, "Render")

    def test_node_is_verified_with_an_explanation(self, steps: str) -> None:
        assert "command -v node" in steps
        assert "::error::" in steps
        assert "setup-node" in steps  # tells a self-hosted runner what to do


class TestDogfoodWorkflow:
    def test_workflow_uses_the_local_action_and_checkout(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        steps = workflow["jobs"]["render"]["steps"]
        uses = [step.get("uses") for step in steps]
        assert "./" in uses, "the workflow must exercise the action in this repo"
        assert any(u and u.startswith("actions/checkout") for u in uses)

    def test_workflow_renders_a_real_sample(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        step = next(
            s for s in workflow["jobs"]["render"]["steps"] if s.get("uses") == "./"
        )
        workspace = ROOT / step["with"]["workspace"]
        assert workspace.exists(), workspace
        # `local` is what makes the job test this checkout rather than PyPI.
        assert step["with"]["version"] == "local"

    def test_workflow_uploads_what_the_action_produced(self) -> None:
        workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        upload = next(
            s
            for s in workflow["jobs"]["render"]["steps"]
            if (s.get("uses") or "").startswith("actions/upload-artifact")
        )
        assert "outputs.diagrams-path" in upload["with"]["path"]
        assert upload["with"]["if-no-files-found"] == "error"
