"""Element style properties that go nowhere say so (PP-108).

The project contract is that unsupported DSL fails soft but *loudly* —
skipped whole and recorded as a structured :class:`Diagnostic`. Element
style properties broke that contract twice over: a property no renderer
draws was stored in silence, and a misspelled one vanished without a
trace, which is the worse of the two because the author believes they
styled something.
"""

from __future__ import annotations

from c4studio.diagnostics import Severity
from c4studio.models import Workspace
from c4studio.parser.dsl import parse_dsl


def _workspace(styles: str) -> Workspace:
    return parse_dsl(
        f"""
        workspace "W" {{
            model {{
                s = softwareSystem "S" {{
                    api = container "API"
                }}
            }}
            views {{
                container s "cont" {{ include * }}
                styles {{
                    {styles}
                }}
            }}
        }}
        """
    )


def _codes(workspace: Workspace) -> list[str]:
    return [d.code for d in workspace.diagnostics]


class TestUnpaintedProperties:
    def test_width_is_reported(self) -> None:
        workspace = _workspace('element "Element" { width 300 }')
        assert _codes(workspace) == ["ignored-style-property"]
        diagnostic = workspace.diagnostics[0]
        assert diagnostic.severity is Severity.WARNING
        # The message must name both halves, or it is not actionable.
        assert "'width'" in diagnostic.message
        assert "'Element'" in diagnostic.message

    def test_each_unpainted_property_is_reported(self) -> None:
        workspace = _workspace(
            'element "Element" { width 300 height 200 fontSize 18 iconPosition top }'
        )
        assert _codes(workspace) == ["ignored-style-property"] * 4

    def test_painted_properties_stay_silent(self) -> None:
        workspace = _workspace(
            """
            element "Element" {
                background #2e7d32
                color #ffffff
                stroke #000000
                strokeWidth 3
                border dashed
                opacity 55
                shape Cylinder
                metadata false
                description false
            }
            """
        )
        assert workspace.diagnostics == []

    def test_the_property_is_still_parsed(self) -> None:
        """Warning is not dropping — JSON export still round-trips it."""
        workspace = _workspace('element "Element" { width 300 }')
        style = workspace.views.configuration.styles.element_styles[0]
        assert style.width == 300


class TestUnknownProperties:
    def test_a_typo_is_reported(self) -> None:
        workspace = _workspace('element "Element" { backgroud #ff0000 }')
        assert _codes(workspace) == ["unknown-style-property"]
        assert "'backgroud'" in workspace.diagnostics[0].message

    def test_it_points_at_the_property(self) -> None:
        workspace = parse_dsl(
            """
            workspace "W" {
                model { s = softwareSystem "S" }
                views {
                    styles {
                        element "Element" {
                            backgroud #ff0000
                        }
                    }
                }
            }
            """
        )
        diagnostic = workspace.diagnostics[0]
        assert diagnostic.line == 7
        assert diagnostic.column is not None
        assert diagnostic.end_column is not None

    def test_a_typo_does_not_swallow_its_neighbours(self) -> None:
        """A skipped property must not consume the rest of the block."""
        workspace = _workspace(
            'element "Element" { backgroud #ff0000 background #2e7d32 }'
        )
        style = workspace.views.configuration.styles.element_styles[0]
        assert style.background == "#2e7d32"

    def test_light_and_dark_blocks_are_not_mistaken_for_properties(self) -> None:
        workspace = _workspace(
            'element "Element" { light { background #ffffff } dark { background #000000 } }'
        )
        assert workspace.diagnostics == []


class TestRelationshipStylesAreOutOfScope:
    def test_relationship_properties_stay_silent_for_now(self) -> None:
        """Deliberate: relationship styles deserve the same pass separately."""
        workspace = _workspace('relationship "Relationship" { fontSize 18 }')
        assert workspace.diagnostics == []
