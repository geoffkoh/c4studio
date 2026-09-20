"""Model diff between two revisions (PP-190).

The comparison is straightforward; what needs pinning is the judgement:
what counts as a change rather than a delete plus an add, what a
comment-only edit produces, and that a rename is *reported* rather than
guessed at.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from c4studio.cli.main import cli
from c4studio.diff import Diff, DiffError, diff_workspaces, workspace_at
from c4studio.parser.dsl import parse_dsl

BASE = """
workspace "Shop" {
    model {
        u = person "User" "Buys"
        s = softwareSystem "Shop" "Sells" {
            web = container "Web" "UI" "React"
            api = container "API" "Logic" "Python"
            web -> api "Calls"
        }
        u -> web "Uses"
    }
    views {
        container s "Containers" {
            include *
        }
    }
}
"""


def _diff(before: str, after: str) -> Diff:
    return diff_workspaces(parse_dsl(before), parse_dsl(after))


class TestElements:
    def test_added_and_removed(self) -> None:
        after = BASE.replace(
            '            web -> api "Calls"',
            '            db = container "DB" "Store" "PostgreSQL"\n'
            '            web -> api "Calls"',
        )
        result = _diff(BASE, after)
        assert [e.id for e in result.added_elements] == ["db"]
        assert result.removed_elements == []
        assert [e.id for e in _diff(after, BASE).removed_elements] == ["db"]

    def test_a_field_change_is_a_change_not_a_replacement(self) -> None:
        after = BASE.replace('"UI" "React"', '"UI" "TypeScript, React"')
        result = _diff(BASE, after)
        assert result.added_elements == []
        assert result.removed_elements == []
        [changed] = result.changed_elements
        assert changed.id == "web"
        assert [(c.field, c.before, c.after) for c in changed.changes] == [
            ("technology", "React", "TypeScript, React")
        ]

    def test_tags_are_compared(self) -> None:
        after = BASE.replace(
            '            api = container "API" "Logic" "Python"',
            '            api = container "API" "Logic" "Python" "Critical"',
        )
        [changed] = _diff(BASE, after).changed_elements
        assert changed.changes[0].field == "tags"

    def test_renaming_an_aliased_element_is_a_change(self) -> None:
        """The alias is the id, so the rename has somewhere to hang."""
        after = BASE.replace('container "Web" "UI"', 'container "Web App" "UI"')
        result = _diff(BASE, after)
        [changed] = result.changed_elements
        assert (changed.changes[0].before, changed.changes[0].after) == (
            "Web",
            "Web App",
        )
        assert result.added_elements == result.removed_elements == []


class TestRelationships:
    def test_added_and_removed(self) -> None:
        after = BASE.replace(
            '        u -> web "Uses"\n', '        u -> api "Calls directly"\n'
        )
        result = _diff(BASE, after)
        assert [(r.source, r.destination) for r in result.added_relationships] == [
            ("u", "api")
        ]
        assert [(r.source, r.destination) for r in result.removed_relationships] == [
            ("u", "web")
        ]

    def test_rewording_one_is_a_change_not_a_swap(self) -> None:
        """Matched on the pair first, so the reviewer sees one line."""
        after = BASE.replace('web -> api "Calls"', 'web -> api "Calls over HTTPS"')
        result = _diff(BASE, after)
        assert result.added_relationships == result.removed_relationships == []
        [changed] = result.changed_relationships
        assert (changed.source, changed.destination) == ("web", "api")
        assert changed.changes[0].after == "Calls over HTTPS"

    def test_two_relationships_between_one_pair_stay_distinguishable(self) -> None:
        both = BASE.replace(
            '            web -> api "Calls"',
            '            web -> api "Calls"\n            web -> api "Polls"',
        )
        result = _diff(BASE, both)
        assert [r.description for r in result.added_relationships] == ["Polls"]


class TestRenames:
    def test_an_unaliased_rename_is_reported_not_assumed(self) -> None:
        """Its id is a slug of its name, so the two cannot be tied
        together — and inventing the link would hide a deletion."""
        before = BASE.replace(
            '            api = container "API" "Logic" "Python"',
            '            container "Reporting" "Figures" "Python"',
        )
        after = before.replace('"Reporting" "Figures"', '"Reports" "Figures"')
        result = _diff(before, after)
        assert [e.name for e in result.added_elements] == ["Reports"]
        assert [e.name for e in result.removed_elements] == ["Reporting"]
        # Different names, so not even a candidate.
        assert result.possible_renames == []

    def test_a_moved_element_keeping_its_name_is_flagged(self) -> None:
        before = BASE
        after = BASE.replace(
            "            web = container", "            www = container"
        )
        result = _diff(before, after)
        assert result.possible_renames == [("web", "www")]


class TestNoise:
    def test_a_comment_only_change_produces_nothing(self) -> None:
        """The signal a reviewer wants: the model did not move."""
        after = BASE.replace("    model {", "    model {\n        // a note")
        assert _diff(BASE, after).empty

    def test_reordering_declarations_produces_nothing(self) -> None:
        after = BASE.replace(
            '            web = container "Web" "UI" "React"\n'
            '            api = container "API" "Logic" "Python"',
            '            api = container "API" "Logic" "Python"\n'
            '            web = container "Web" "UI" "React"',
        )
        assert _diff(BASE, after).empty

    def test_implied_relationships_are_not_diffed(self) -> None:
        after = BASE.replace(
            "    model {", "    model {\n        !impliedRelationships true"
        )
        assert _diff(BASE, after).empty


class TestAffectedViews:
    def test_it_names_the_views_to_look_at_again(self) -> None:
        after = BASE.replace('"UI" "React"', '"UI" "Vue"')
        assert _diff(BASE, after).affected_views == ["Containers"]

    def test_a_removed_element_is_found_in_the_older_version(self) -> None:
        """It is gone from the new one, so only the old model can say
        which diagrams used to draw it."""
        after = BASE.replace(
            '            api = container "API" "Logic" "Python"\n', ""
        ).replace('            web -> api "Calls"\n', "")
        assert _diff(BASE, after).affected_views == ["Containers"]


class TestGit:
    def _repo(self, tmp_path: Path, text: str) -> Path:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        source = tmp_path / "ws.dsl"
        source.write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(tmp_path),
                "-c",
                "user.email=t@example.com",
                "-c",
                "user.name=t",
                "commit",
                "-qm",
                "base",
            ],
            check=True,
        )
        return source

    def test_a_revision_is_materialised_with_its_neighbours(
        self, tmp_path: Path
    ) -> None:
        """A whole directory, because a workspace can be split across
        !include-ed fragments."""
        (tmp_path / "model").mkdir()
        (tmp_path / "model" / "people.dsl").write_text(
            'u = person "User" "Buys"\n', encoding="utf-8"
        )
        source = self._repo(
            tmp_path,
            'workspace "W" {\n    model {\n        !include model/people.dsl\n'
            "    }\n    views {\n        systemLandscape L {\n            include *\n"
            "        }\n    }\n}\n",
        )
        at_head = workspace_at("HEAD", source)
        assert at_head.is_file()
        assert (at_head.parent / "model" / "people.dsl").is_file()

    def test_an_unknown_revision_says_so(self, tmp_path: Path) -> None:
        source = self._repo(tmp_path, BASE)
        with pytest.raises(DiffError, match="Could not read revision"):
            workspace_at("no-such-branch", source)

    def test_outside_a_repository_says_so(self, tmp_path: Path) -> None:
        source = tmp_path / "loose.dsl"
        source.write_text(BASE, encoding="utf-8")
        with pytest.raises(DiffError, match="not inside a git repository"):
            workspace_at("HEAD", source)

    def test_the_cli_compares_the_working_tree_against_head(
        self, tmp_path: Path
    ) -> None:
        source = self._repo(tmp_path, BASE)
        source.write_text(BASE.replace('"UI" "React"', '"UI" "Vue"'), encoding="utf-8")
        result = CliRunner().invoke(cli, ["diff", str(source)])
        assert result.exit_code == 0
        assert "Elements changed" in result.output
        assert "'React' -> 'Vue'" in result.output

    def test_the_cli_says_when_nothing_changed(self, tmp_path: Path) -> None:
        source = self._repo(tmp_path, BASE)
        result = CliRunner().invoke(cli, ["diff", str(source)])
        assert "No model changes" in result.output

    def test_json_is_shaped_for_a_pr_comment(self, tmp_path: Path) -> None:
        source = self._repo(tmp_path, BASE)
        source.write_text(BASE.replace('"UI" "React"', '"UI" "Vue"'), encoding="utf-8")
        result = CliRunner().invoke(cli, ["diff", str(source), "--json"])
        payload = json.loads(result.output)
        assert payload["elements"]["changed"][0]["id"] == "web"
        assert payload["affectedViews"] == ["Containers"]
