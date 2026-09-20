"""What changed between two versions of a model (PP-190).

A pull request that changes the architecture should say what it changed,
in the place the review happens. That is the reason to keep a model in
git rather than a wiki, and it only pays off if the diff is readable:
elements and relationships added, removed and changed, and **which views
a reviewer has to look at again**.

**Identity is the hard part, and it is the one thing to understand here.**
An element's id comes from its DSL alias, or from a slug of its name when
it has none. So renaming an aliased element is a *change*, and renaming an
unaliased one reads as a delete plus an add — the model gives us nothing
to tie them together. Rather than guess at similarity, a rename that looks
like delete+add is reported as delete+add, and the pair is flagged when a
removal and an addition share a name or a description. Guessing quietly
would be worse: a diff that invents a rename hides a deletion.
"""

from __future__ import annotations

import subprocess
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from c4studio.models import Workspace


class DiffError(Exception):
    """Raised when a revision cannot be read."""


@dataclass(frozen=True)
class ElementFacts:
    """The fields of an element a diff compares."""

    id: str
    name: str
    kind: str
    description: str
    technology: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RelationshipFacts:
    """The fields of a relationship a diff compares."""

    source: str
    destination: str
    description: str
    technology: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Change:
    """One field that differs between the two versions.

    Attributes:
        field: Which field changed.
        before: Its value in the older version.
        after: Its value in the newer one.
    """

    field: str
    before: str
    after: str


@dataclass(frozen=True)
class ChangedElement:
    """An element present in both versions, with differences."""

    id: str
    name: str
    kind: str
    changes: tuple[Change, ...]


@dataclass(frozen=True)
class ChangedRelationship:
    """A relationship present in both versions, with differences."""

    source: str
    destination: str
    changes: tuple[Change, ...]


@dataclass
class Diff:
    """Everything that changed between two workspaces."""

    added_elements: list[ElementFacts] = field(default_factory=list)
    removed_elements: list[ElementFacts] = field(default_factory=list)
    changed_elements: list[ChangedElement] = field(default_factory=list)
    added_relationships: list[RelationshipFacts] = field(default_factory=list)
    removed_relationships: list[RelationshipFacts] = field(default_factory=list)
    changed_relationships: list[ChangedRelationship] = field(default_factory=list)
    #: Added/removed pairs that share a name — a rename the ids could not
    #: express. Reported, never assumed.
    possible_renames: list[tuple[str, str]] = field(default_factory=list)
    #: View keys a reviewer should look at again.
    affected_views: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        """Whether the two versions describe the same model."""
        return not (
            self.added_elements
            or self.removed_elements
            or self.changed_elements
            or self.added_relationships
            or self.removed_relationships
            or self.changed_relationships
        )


def _elements(workspace: Workspace) -> Iterator[ElementFacts]:
    for person in workspace.model.people:
        yield ElementFacts(
            person.id, person.name, "person", person.description, "", tuple(person.tags)
        )
    for system in workspace.model.software_systems:
        yield ElementFacts(
            system.id,
            system.name,
            "softwareSystem",
            system.description,
            "",
            tuple(system.tags),
        )
        for container in system.containers:
            yield ElementFacts(
                container.id,
                container.name,
                "container",
                container.description,
                container.technology,
                tuple(container.tags),
            )
            for component in container.components:
                yield ElementFacts(
                    component.id,
                    component.name,
                    "component",
                    component.description,
                    component.technology,
                    tuple(component.tags),
                )


def _relationships(workspace: Workspace) -> Iterator[RelationshipFacts]:
    for relationship in workspace.relationships:
        if relationship.linked_relationship_id:
            continue  # implied; it follows from the ones written down
        yield RelationshipFacts(
            relationship.source_id,
            relationship.destination_id,
            relationship.description,
            relationship.technology,
            tuple(relationship.tags),
        )


def _compare(before: object, after: object, fields: tuple[str, ...]) -> list[Change]:
    """The fields that differ between two records."""
    changes: list[Change] = []
    for name in fields:
        old = getattr(before, name)
        new = getattr(after, name)
        if old != new:
            changes.append(
                Change(
                    name,
                    ", ".join(old) if isinstance(old, tuple) else str(old),
                    ", ".join(new) if isinstance(new, tuple) else str(new),
                )
            )
    return changes


def diff_workspaces(before: Workspace, after: Workspace) -> Diff:
    """Compare two parsed workspaces.

    Args:
        before: The older version.
        after: The newer one.

    Returns:
        What was added, removed and changed, the possible renames, and
        the views a reviewer should look at again.
    """
    old_elements = {element.id: element for element in _elements(before)}
    new_elements = {element.id: element for element in _elements(after)}

    result = Diff()
    for element_id, element in new_elements.items():
        if element_id not in old_elements:
            result.added_elements.append(element)
            continue
        changes = _compare(
            old_elements[element_id],
            element,
            ("name", "description", "technology", "tags"),
        )
        if changes:
            result.changed_elements.append(
                ChangedElement(element_id, element.name, element.kind, tuple(changes))
            )
    for element_id, element in old_elements.items():
        if element_id not in new_elements:
            result.removed_elements.append(element)

    # A rename the ids could not express: same name, different id. Named,
    # not assumed — a diff that invents a rename hides a deletion.
    removed_by_name = {element.name: element.id for element in result.removed_elements}
    for element in result.added_elements:
        previous = removed_by_name.get(element.name)
        if previous and previous != element.id:
            result.possible_renames.append((previous, element.id))

    old_relationships = {
        (r.source, r.destination, r.description): r for r in _relationships(before)
    }
    new_relationships = {
        (r.source, r.destination, r.description): r for r in _relationships(after)
    }

    # Match on the pair first, so a reworded relationship reads as a
    # change rather than as one deletion and one addition.
    old_pairs: dict[tuple[str, str], list[RelationshipFacts]] = {}
    new_pairs: dict[tuple[str, str], list[RelationshipFacts]] = {}
    for relationship in old_relationships.values():
        old_pairs.setdefault(
            (relationship.source, relationship.destination), []
        ).append(relationship)
    for relationship in new_relationships.values():
        new_pairs.setdefault(
            (relationship.source, relationship.destination), []
        ).append(relationship)

    for pair, new_list in new_pairs.items():
        old_list = old_pairs.get(pair, [])
        if len(old_list) == 1 and len(new_list) == 1:
            changes = _compare(
                old_list[0], new_list[0], ("description", "technology", "tags")
            )
            if changes:
                result.changed_relationships.append(
                    ChangedRelationship(pair[0], pair[1], tuple(changes))
                )
            continue
        for relationship in new_list:
            key = (
                relationship.source,
                relationship.destination,
                relationship.description,
            )
            if key not in old_relationships:
                result.added_relationships.append(relationship)
    for pair, old_list in old_pairs.items():
        new_list = new_pairs.get(pair, [])
        if len(old_list) == 1 and len(new_list) == 1:
            continue
        for relationship in old_list:
            key = (
                relationship.source,
                relationship.destination,
                relationship.description,
            )
            if key not in new_relationships:
                result.removed_relationships.append(relationship)

    result.affected_views = _affected_views(before, after, result)
    return result


def _affected_views(before: Workspace, after: Workspace, result: Diff) -> list[str]:
    """Views that draw anything the diff touched, newer version first."""
    from c4studio.impact import views_containing

    touched = {element.id for element in result.added_elements}
    touched.update(element.id for element in result.changed_elements)
    for relationship in result.added_relationships + result.changed_relationships:
        touched.add(relationship.source)
        touched.add(relationship.destination)

    keys: list[str] = []
    for element_id in sorted(touched):
        for key in views_containing(after, element_id):
            if key not in keys:
                keys.append(key)

    # Removed things are only findable in the version that still had them.
    gone = {element.id for element in result.removed_elements}
    for relationship in result.removed_relationships:
        gone.add(relationship.source)
        gone.add(relationship.destination)
    for element_id in sorted(gone):
        for key in views_containing(before, element_id):
            if key not in keys:
                keys.append(key)
    return keys


def workspace_at(revision: str, source: Path) -> Path:
    """Materialise ``source``'s directory at ``revision`` in a temp tree.

    A whole directory rather than the one file, because a workspace can
    be split across ``!include``-ed fragments and carry ``!docs`` beside
    it — reading only the root file would parse a different model from
    the one that revision actually described.

    Args:
        revision: Anything ``git`` resolves — a branch, a tag, a SHA.
        source: The workspace file in the working tree.

    Returns:
        Path to the copy of ``source`` inside the extracted tree. The
        caller is responsible for the temp directory, which is the
        parent of the returned path's repository root.

    Raises:
        DiffError: If git is unavailable, the file is not in a
            repository, or the revision does not exist.
    """
    import tempfile

    source = source.resolve()
    try:
        root = Path(
            subprocess.run(
                ["git", "-C", str(source.parent), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise DiffError(
            f"{source} is not inside a git repository, so there is no "
            "revision to compare against."
        ) from error

    relative = source.relative_to(root)
    subtree = relative.parent.as_posix() or "."
    try:
        archive = subprocess.run(
            ["git", "-C", str(root), "archive", revision, "--", subtree],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr.decode("utf-8", "replace").strip()
        raise DiffError(
            f"Could not read revision {revision!r}: {detail or error}"
        ) from error

    destination = Path(tempfile.mkdtemp(prefix="c4studio-diff-"))
    with tarfile.open(fileobj=BytesIO(archive)) as tar:
        tar.extractall(destination, filter="data")
    return destination / relative


def to_dict(result: Diff) -> dict[str, object]:
    """The diff as JSON-ready data, for a PR comment or a script."""

    def element(item: ElementFacts) -> dict[str, str]:
        return {"id": item.id, "name": item.name, "kind": item.kind}

    def relationship(item: RelationshipFacts) -> dict[str, str]:
        return {
            "source": item.source,
            "destination": item.destination,
            "description": item.description,
        }

    def changes(items: tuple[Change, ...]) -> list[dict[str, str]]:
        return [{"field": c.field, "before": c.before, "after": c.after} for c in items]

    return {
        "elements": {
            "added": [element(e) for e in result.added_elements],
            "removed": [element(e) for e in result.removed_elements],
            "changed": [
                {
                    "id": c.id,
                    "name": c.name,
                    "kind": c.kind,
                    "changes": changes(c.changes),
                }
                for c in result.changed_elements
            ],
        },
        "relationships": {
            "added": [relationship(r) for r in result.added_relationships],
            "removed": [relationship(r) for r in result.removed_relationships],
            "changed": [
                {
                    "source": c.source,
                    "destination": c.destination,
                    "changes": changes(c.changes),
                }
                for c in result.changed_relationships
            ],
        },
        "possibleRenames": [
            {"before": before, "after": after}
            for before, after in result.possible_renames
        ],
        "affectedViews": list(result.affected_views),
    }
