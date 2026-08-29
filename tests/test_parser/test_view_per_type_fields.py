"""Per-type view fields must survive a workspace JSON round-trip.

Field names, types and defaults follow structurizr-core: SystemContextView
and SystemLandscapeView default enterpriseBoundaryVisible to true,
ModelView defaults mergeFromRemote to true, and the rest default to false,
empty or null.
"""

from __future__ import annotations

import json
from typing import Any, cast

from c4studio.generators.json_export import export_json
from c4studio.models import Dimensions, View, ViewType
from c4studio.parser.json_parser import parse_json

JsonDict = dict[str, Any]


def _round_trip(view: View) -> View:
    """Export a workspace holding ``view`` and parse it back."""
    from c4studio.models import Workspace

    workspace = Workspace(name="T")
    workspace.views.append(view)
    return list(parse_json(export_json(workspace)).views)[0]


def _exported_view(view: View) -> JsonDict:
    from c4studio.models import Workspace

    workspace = Workspace(name="T")
    workspace.views.append(view)
    exported = json.loads(export_json(workspace))
    views = exported["workspace"]["views"]
    for collection in views.values():
        if isinstance(collection, list) and collection:
            return cast(JsonDict, collection[0])
    raise AssertionError("no view in the export")


def test_defaults_match_structurizr_java() -> None:
    view = View(type=ViewType.SYSTEM_CONTEXT, key="k")

    assert view.enterprise_boundary_visible is True
    assert view.merge_from_remote is True
    assert view.external_software_system_boundaries_visible is False
    assert view.external_container_boundaries_visible is False
    assert view.generated_key is False
    assert view.container_id == ""
    assert view.dimensions is None


def test_enterprise_boundary_visible_round_trips_when_disabled() -> None:
    view = View(
        type=ViewType.SYSTEM_CONTEXT, key="k", enterprise_boundary_visible=False
    )

    assert _exported_view(view)["enterpriseBoundaryVisible"] is False
    assert _round_trip(view).enterprise_boundary_visible is False


def test_default_true_fields_are_not_written_when_unchanged() -> None:
    """Defaults stay out of the export, as with every other field here."""
    exported = _exported_view(View(type=ViewType.SYSTEM_CONTEXT, key="k"))

    assert "enterpriseBoundaryVisible" not in exported
    assert "mergeFromRemote" not in exported


def test_container_view_boundary_flag_round_trips() -> None:
    view = View(
        type=ViewType.CONTAINER,
        key="k",
        external_software_system_boundaries_visible=True,
    )

    assert _exported_view(view)["externalSoftwareSystemBoundariesVisible"] is True
    assert _round_trip(view).external_software_system_boundaries_visible is True


def test_component_view_container_id_and_boundary_flag_round_trip() -> None:
    view = View(
        type=ViewType.COMPONENT,
        key="k",
        container_id="c1",
        external_container_boundaries_visible=True,
    )

    exported = _exported_view(view)
    assert exported["containerId"] == "c1"
    assert exported["externalContainerBoundariesVisible"] is True

    parsed = _round_trip(view)
    assert parsed.container_id == "c1"
    assert parsed.external_container_boundaries_visible is True


def test_generated_key_round_trips() -> None:
    view = View(type=ViewType.SYSTEM_LANDSCAPE, key="k", generated_key=True)

    assert _exported_view(view)["generatedKey"] is True
    assert _round_trip(view).generated_key is True


def test_dimensions_round_trip() -> None:
    view = View(
        type=ViewType.SYSTEM_LANDSCAPE,
        key="k",
        dimensions=Dimensions(width=1600, height=1200),
    )

    assert _exported_view(view)["dimensions"] == {"width": 1600, "height": 1200}

    parsed = _round_trip(view)
    assert parsed.dimensions is not None
    assert (parsed.dimensions.width, parsed.dimensions.height) == (1600, 1200)


def test_merge_from_remote_round_trips_when_disabled() -> None:
    view = View(type=ViewType.SYSTEM_LANDSCAPE, key="k", merge_from_remote=False)

    assert _exported_view(view)["mergeFromRemote"] is False
    assert _round_trip(view).merge_from_remote is False
