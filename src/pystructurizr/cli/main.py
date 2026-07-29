"""pystructurizr CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click

from pystructurizr.diagnostics import Diagnostic, Severity
from pystructurizr.generators.mermaid import MermaidGenerator
from pystructurizr.models import Workspace
from pystructurizr.webapp.loader import WorkspaceLoadError, load_workspace


def _load_workspace(path: Path) -> Workspace:
    """Load a workspace, mapping loader errors to a CLI-friendly message."""
    try:
        workspace = load_workspace(path)
    except WorkspaceLoadError as exc:
        raise click.BadParameter(str(exc)) from exc
    for warning in workspace.parse_warnings:
        click.echo(f"warning: {warning}", err=True)
    return workspace


@click.group()
@click.version_option()
def cli() -> None:
    """pystructurizr – parse Structurizr files and generate C4 diagrams."""


@cli.command("generate")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: print to stdout).",
)
@click.option(
    "--view",
    "-v",
    "view_key",
    default=None,
    help="Only generate for this view key.",
)
@click.option(
    "--format",
    "-f",
    "fmt",
    type=click.Choice(["mermaid"], case_sensitive=False),
    default="mermaid",
    show_default=True,
)
def generate(
    input_file: Path, output: Path | None, view_key: str | None, fmt: str
) -> None:
    """Generate diagrams from INPUT_FILE (DSL or JSON)."""
    workspace = _load_workspace(input_file)
    generator = MermaidGenerator(workspace)

    diagrams = generator.generate_all()
    if view_key:
        if view_key not in diagrams:
            available = ", ".join(diagrams) or "(none)"
            raise click.ClickException(
                f"View '{view_key}' not found. Available: {available}"
            )
        diagrams = {view_key: diagrams[view_key]}

    if output is None:
        for key, content in diagrams.items():
            if len(diagrams) > 1:
                click.echo(f"--- {key} ---")
            click.echo(content)
            if len(diagrams) > 1:
                click.echo()
    else:
        output.mkdir(parents=True, exist_ok=True)
        ext = ".mmd"
        for key, content in diagrams.items():
            out_path = output / f"{key}{ext}"
            out_path.write_text(content, encoding="utf-8")
            click.echo(f"Written: {out_path}")


@cli.command("export")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file (default: print to stdout).",
)
def export(input_file: Path, output: Path | None) -> None:
    """Export INPUT_FILE (DSL or JSON) as Structurizr workspace JSON.

    The output round-trips with structurizr.com, Structurizr Lite, and
    this package's own JSON parser.
    """
    from pystructurizr.generators.json_export import export_json, export_json_file

    workspace = _load_workspace(input_file)
    if output is None:
        click.echo(export_json(workspace), nl=False)
    else:
        if output.parent != Path(""):
            output.parent.mkdir(parents=True, exist_ok=True)
        export_json_file(workspace, output)
        click.echo(f"Written: {output}")


@cli.command("check")
@click.argument("input_file", type=click.Path(allow_dash=True, path_type=Path))
@click.option(
    "--path",
    "source_path",
    type=click.Path(path_type=Path),
    help=(
        "File the source on stdin belongs to. Diagnostics are reported "
        "against it, and relative !include/!docs/!adrs targets resolve "
        "next to it."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit diagnostics as JSON, for editors and other tools.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Exit non-zero on warnings as well as errors.",
)
def check(
    input_file: Path, source_path: Path | None, as_json: bool, strict: bool
) -> None:
    """Report problems in INPUT_FILE without generating anything.

    INPUT_FILE may be ``-`` to read DSL from stdin, which is how an editor
    checks a buffer that has not been saved. Pass ``--path`` with it so
    diagnostics name the real file and relative directives resolve.

    Exits 1 when the file has errors (or, with --strict, warnings), so it
    can gate a CI job. Warnings cover DSL the parser understood but did not
    implement — those constructs are skipped, and this is where that
    becomes visible.
    """
    import json as json_module

    from pystructurizr.parser.dsl import ParseError, parse_dsl, parse_dsl_file

    diagnostics: list[Diagnostic] = []
    from_stdin = str(input_file) == "-"
    try:
        if from_stdin:
            resolved = source_path.resolve() if source_path is not None else None
            workspace = parse_dsl(
                click.get_text_stream("stdin").read(),
                base_dir=resolved.parent if resolved is not None else None,
                path=resolved,
            )
        elif input_file.suffix.lower() == ".json":
            workspace = _load_workspace(input_file)
        else:
            workspace = parse_dsl_file(input_file)
        diagnostics = list(workspace.diagnostics)
    except ParseError as error:
        # Every problem found, not just the one that stopped parsing.
        diagnostics = list(error.diagnostics)

    if as_json:
        click.echo(json_module.dumps([d.to_dict() for d in diagnostics], indent=2))
    else:
        for diagnostic in diagnostics:
            click.echo(f"{diagnostic.severity.value}: {diagnostic}", err=True)
        if not diagnostics:
            label = source_path if from_stdin and source_path else input_file
            click.echo(f"{label}: no problems found")

    errors = [d for d in diagnostics if d.severity is Severity.ERROR]
    if errors or (strict and diagnostics):
        raise SystemExit(1)


@cli.command("list-views")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
def list_views(input_file: Path) -> None:
    """List all views defined in INPUT_FILE."""
    workspace = _load_workspace(input_file)
    if not workspace.views:
        click.echo("No views found.")
        return
    click.echo(f"{'Key':<30} {'Type':<20} {'Element ID'}")
    click.echo("-" * 65)
    for view in workspace.views:
        click.echo(f"{view.key:<30} {view.type:<20} {view.element_id}")


@cli.command("webapp")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--port", default=8090, show_default=True, help="Port to listen on.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Do not open a browser window automatically.",
)
def webapp(path: Path, port: int, host: str, no_browser: bool) -> None:
    """Launch the React web application backend for PATH.

    PATH may be a directory (browsed as the source root) or a single source
    file (loaded eagerly, with its parent directory as the root).
    """
    from pystructurizr.webapp.server import run_server

    if path.is_dir():
        root: Path = path
        initial: Path | None = None
    else:
        root = path.parent
        initial = path

    if not no_browser:
        import threading
        import webbrowser

        url = f"http://{host}:{port}"
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    run_server(root=root, initial=initial, host=host, port=port)
