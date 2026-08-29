"""Implied-relationship creation for ``!impliedRelationships``.

Mirrors structurizr-java's default
``CreateImpliedRelationshipsUnlessAnyRelationshipExistsStrategy``: for every
relationship, parent-level relationships are created for each combination of
the endpoints' ancestors, unless any relationship already exists between
that pair or the pair is related by ancestry.
"""

from __future__ import annotations

from c4studio.models import Relationship, Workspace


def _parent_ids(workspace: Workspace) -> dict[str, str]:
    parents: dict[str, str] = {}
    for system in workspace.software_systems:
        for container in system.containers:
            parents[container.id] = system.id
            for component in container.components:
                parents[component.id] = container.id
    return parents


def _lineage(element_id: str, parents: dict[str, str]) -> list[str]:
    """The element id followed by its ancestors, innermost first."""
    line = [element_id]
    while line[-1] in parents:
        line.append(parents[line[-1]])
    return line


def apply_implied_relationships(workspace: Workspace) -> None:
    """Materialise parent-level relationships implied by lower-level ones.

    Created relationships copy the description, technology, and tags of the
    original and carry its id in ``linked_relationship_id`` (originals
    without an id are assigned one first). Pairs that already have any
    relationship — explicit or previously implied — are skipped.
    """
    parents = _parent_ids(workspace)
    existing = {(r.source_id, r.destination_id) for r in workspace.relationships}
    next_id = 1

    def ensure_id(rel: Relationship) -> str:
        nonlocal next_id
        taken = {r.id for r in workspace.relationships if r.id}
        if not rel.id:
            while str(next_id) in taken:
                next_id += 1
            rel.id = str(next_id)
            next_id += 1
        return rel.id

    implied: list[Relationship] = []
    for rel in list(workspace.relationships):
        source_line = _lineage(rel.source_id, parents)
        destination_line = _lineage(rel.destination_id, parents)
        for src in source_line:
            for dst in destination_line:
                if (src, dst) == (rel.source_id, rel.destination_id):
                    continue
                # skip self-pairs and ancestry-related pairs
                if src == dst or src in destination_line or dst in source_line:
                    continue
                if (src, dst) in existing:
                    continue
                implied.append(
                    Relationship(
                        source_id=src,
                        destination_id=dst,
                        description=rel.description,
                        technology=rel.technology,
                        tags=list(rel.tags),
                        linked_relationship_id=ensure_id(rel),
                    )
                )
                existing.add((src, dst))
    workspace.relationships.extend(implied)
