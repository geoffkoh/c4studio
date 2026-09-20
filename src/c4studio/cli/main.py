"""c4studio CLI entry point."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import click

from c4studio import templates
from c4studio.diagnostics import Diagnostic, Severity
from c4studio.generators.flowchart import FlowchartGenerator
from c4studio.generators.mermaid import MermaidGenerator
from c4studio.graph.view_graph import perspective_names
from c4studio.models import Workspace
from c4studio.render import RenderError, render_view
from c4studio.webapp.graph import is_supported, views_index
from c4studio.webapp.loader import WorkspaceLoadError, load_workspace


def _read_stdin_text() -> str:
    """Read the whole of stdin as UTF-8.

    DSL is read from disk as UTF-8 everywhere else (`parse_dsl_file` and the
    `!include` resolver both pass `encoding="utf-8"`), so a piped buffer has
    to be decoded the same way. `sys.stdin.read()` alone would not: its
    encoding follows the locale, so the same DSL that parses from a file
    would mangle non-ASCII when piped under a non-UTF-8 locale.

    This replaces `click.get_text_stream("stdin")`, which did approximately
    this and is deprecated in Click 8.5 for removal in 9.0.
    """
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        # Something has replaced stdin with a text-only object. Nothing to
        # re-decode, so take it as it comes.
        return sys.stdin.read()
    raw: bytes = buffer.read()
    return raw.decode("utf-8")


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
    """c4studio – parse Structurizr files and generate C4 diagrams."""


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
    type=click.Choice(["mermaid", "flowchart"], case_sensitive=False),
    default="mermaid",
    show_default=True,
    help=(
        "mermaid: Mermaid C4 syntax (C4Context/C4Container/C4Component). "
        "flowchart: Mermaid flowchart + subgraph — renders more reliably on "
        "GitHub and dense models, and covers dynamic, deployment and "
        "filtered views too."
    ),
)
def generate(
    input_file: Path, output: Path | None, view_key: str | None, fmt: str
) -> None:
    """Generate diagrams from INPUT_FILE (DSL or JSON)."""
    workspace = _load_workspace(input_file)
    if fmt.lower() == "flowchart":
        diagrams = FlowchartGenerator(workspace).generate_all()
    else:
        diagrams = MermaidGenerator(workspace).generate_all()
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


@cli.command("render")
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
    help="Only render this view key.",
)
@click.option(
    "--padding",
    type=int,
    default=24,
    show_default=True,
    help="Blank margin around the diagram, in pixels.",
)
@click.option(
    "--no-title",
    is_flag=True,
    default=False,
    help="Omit the heading above the diagram (the SVG <title> stays).",
)
@click.option(
    "--no-legend",
    is_flag=True,
    default=False,
    help="Omit the legend of element styles used by the view.",
)
@click.option(
    "--no-layout",
    is_flag=True,
    default=False,
    help=(
        "Ignore the layout sidecar and lay the diagram out afresh. The "
        "sidecar is per-user state, so this is what makes the output the "
        "same on any machine."
    ),
)
@click.option(
    "--perspective",
    default=None,
    help=(
        "Show one perspective: fade what does not carry it, badge what "
        "does, and list its values in the legend."
    ),
)
def render(
    input_file: Path,
    output: Path | None,
    view_key: str | None,
    padding: int,
    no_title: bool,
    no_legend: bool,
    no_layout: bool,
    perspective: str | None,
) -> None:
    """Render diagrams from INPUT_FILE as standalone SVG.

    No browser and no server: the diagrams are laid out and painted by the
    same code the web app runs, bundled for Node. The layout sidecar
    beside INPUT_FILE is honoured when there is one, so a rendered diagram
    matches the arrangement you made in the Studio; ``--no-layout``
    ignores it. This is the only command
    that needs Node.js installed; set C4STUDIO_NODE if it is not on
    PATH. Views the renderer cannot draw (custom, image) are skipped.
    """
    workspace = _load_workspace(input_file)
    if perspective is not None:
        # Fail on a name nothing carries rather than writing a uniformly
        # faded diagram: at the command line there is no picker to show
        # what the model actually offers.
        names = perspective_names(workspace)
        if perspective not in names:
            raise click.ClickException(
                f"No perspective named '{perspective}' in this workspace. "
                f"Available: {', '.join(names) or '(none)'}"
            )
    views = [v for v in workspace.views if is_supported(v)]
    if view_key:
        views = [v for v in views if v.key == view_key]
        if not views:
            available = ", ".join(v.key for v in workspace.views if is_supported(v))
            raise click.ClickException(
                f"View '{view_key}' not found or not renderable. "
                f"Available: {available or '(none)'}"
            )
    if not views:
        raise click.ClickException("this workspace has no renderable views")

    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
    try:
        for view in views:
            svg = render_view(
                workspace,
                view,
                padding=padding,
                show_title=not no_title,
                show_legend=not no_legend,
                perspective=perspective,
                # The arrangement made in the Studio, unless asked for a
                # fresh one. Sidecars sit beside the root source file.
                layout_source=None if no_layout else input_file,
            )
            if output is None:
                click.echo(svg, nl=False)
            else:
                out_path = output / f"{view.key}.svg"
                out_path.write_text(svg, encoding="utf-8")
                click.echo(f"Written: {out_path}")
    except RenderError as exc:
        raise click.ClickException(str(exc)) from exc


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
    from c4studio.generators.json_export import export_json, export_json_file

    workspace = _load_workspace(input_file)
    if output is None:
        click.echo(export_json(workspace), nl=False)
    else:
        if output.parent != Path():
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

    from c4studio.parser.dsl import ParseError, parse_dsl, parse_dsl_file

    diagnostics: list[Diagnostic] = []
    from_stdin = str(input_file) == "-"
    try:
        if from_stdin:
            resolved = source_path.resolve() if source_path is not None else None
            workspace = parse_dsl(
                _read_stdin_text(),
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


@cli.command("lint")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit findings as JSON, for editors and other tools.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "Rule configuration. Defaults to c4studio.lint.json beside "
        "INPUT_FILE when that exists."
    ),
)
@click.option(
    "--ignore",
    "ignored",
    multiple=True,
    help="Rule code to skip. Repeatable; adds to any configured ignores.",
)
@click.option(
    "--select",
    "selected",
    multiple=True,
    help="Run only these rule codes. Repeatable.",
)
@click.option(
    "--exit-zero",
    is_flag=True,
    help="Report findings but exit 0, for a first run on an existing model.",
)
def lint_command(
    input_file: Path,
    as_json: bool,
    config_path: Path | None,
    ignored: tuple[str, ...],
    selected: tuple[str, ...],
    exit_zero: bool,
) -> None:
    """Check INPUT_FILE against the model standards.

    Where ``check`` asks whether the file parses, this asks whether it is
    a good model: elements nothing relates to, missing descriptions and
    technologies, relationships declared twice, styles that match nothing.

    Every finding is a warning — a model that breaks a house style still
    parses and still renders — so the exit code is what makes CI care: 1
    when anything is found, unless ``--exit-zero``.

    Rules are configured in JSON, by default ``c4studio.lint.json`` beside
    INPUT_FILE::

        {"ignore": ["missing-technology"],
         "naming": {"container": "^[A-Z]"}}
    """
    import json as json_module

    from c4studio.lint import LintConfig, lint, load_config
    from c4studio.parser.locations import element_locations

    if config_path is None:
        beside = input_file.parent / "c4studio.lint.json"
        config_path = beside if beside.is_file() else None
    try:
        config = load_config(config_path) if config_path else LintConfig()
    except ValueError as error:
        raise click.ClickException(f"{config_path}: {error}") from error
    config.ignore.update(ignored)
    config.select.update(selected)

    workspace = _load_workspace(input_file)
    findings = lint(workspace, config, element_locations(input_file))

    if as_json:
        click.echo(json_module.dumps([f.to_dict() for f in findings], indent=2))
    else:
        for finding in findings:
            click.echo(str(finding), err=True)
        if findings:
            counted = Counter(f.code for f in findings)
            summary = ", ".join(f"{code} ({n})" for code, n in counted.most_common())
            noun = "finding" if len(findings) == 1 else "findings"
            click.echo(f"{len(findings)} {noun}: {summary}", err=True)
        else:
            click.echo(f"{input_file}: no findings")

    if findings and not exit_zero:
        raise SystemExit(1)


@cli.command("list-views")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the view index as JSON, for tools rather than people.",
)
def list_views(input_file: Path, as_json: bool) -> None:
    """List all views defined in INPUT_FILE.

    ``--json`` emits the same index the web app serves from
    ``GET /api/views`` — the *same function*, so the two cannot drift —
    including which views are renderable and which one the DSL marks
    ``default``. The VS Code extension reads it to populate its view
    picker; the table above it is for reading.
    """
    import json as json_module

    workspace = _load_workspace(input_file)
    if as_json:
        click.echo(json_module.dumps(views_index(workspace), indent=2))
        return
    if not workspace.views:
        click.echo("No views found.")
        return
    click.echo(f"{'Key':<30} {'Type':<20} {'Element ID'}")
    click.echo("-" * 65)
    for view in workspace.views:
        click.echo(f"{view.key:<30} {view.type:<20} {view.element_id}")


@cli.command("list-perspectives")
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the names as a JSON array, for tools rather than people.",
)
def list_perspectives(input_file: Path, as_json: bool) -> None:
    """List the perspective names used anywhere in INPUT_FILE.

    The same set the Studio's perspective picker offers and that
    ``c4 render --perspective`` accepts, from the same function, so a
    caller cannot be offered a name the renderer would refuse. Its own
    command rather than a field on ``list-views --json``: perspectives
    belong to the model, not to a view, and that JSON is an array whose
    shape other tools already read.
    """
    import json as json_module

    workspace = _load_workspace(input_file)
    names = perspective_names(workspace)
    if as_json:
        click.echo(json_module.dumps(names, indent=2))
        return
    if not names:
        click.echo("No perspectives found.")
        return
    for name in names:
        click.echo(name)


@cli.command("new")
@click.argument("output", type=click.Path(path_type=Path), default="workspace.dsl")
@click.option(
    "--template",
    "template_name",
    default="minimal",
    show_default=True,
    help="Which starter workspace to write.",
)
@click.option(
    "--name",
    "workspace_name",
    default=None,
    help="Workspace name. Defaults to the template's own.",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    help="List the available templates and exit.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite OUTPUT if it already exists.",
)
def new(
    output: Path,
    template_name: str,
    workspace_name: str | None,
    list_only: bool,
    force: bool,
) -> None:
    """Write a starter workspace to OUTPUT (default: workspace.dsl)."""
    if list_only:
        for template in templates.list_templates():
            click.echo(f"{template.name:<16} {template.summary}")
        return

    try:
        content = templates.render(template_name, workspace_name)
    except templates.TemplateError as exc:
        raise click.BadParameter(str(exc), param_hint="--template") from exc

    # Never clobber silently: the same rule the webapp's write path holds
    # to, for the same reason — this is someone's work.
    if output.exists() and not force:
        raise click.ClickException(
            f"{output} already exists. Pass --force to overwrite it."
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    click.echo(f"Wrote {output} from the {template_name!r} template.")
    click.echo(f"Next: c4 webapp {output.parent if output.parent != Path() else '.'}")


@cli.command("webapp")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--assistant",
    is_flag=True,
    help=(
        "Enable the DSL assistant. OFF BY DEFAULT: it is the one feature "
        "that sends your workspace source to an external API. Needs "
        "ANTHROPIC_API_KEY in the environment and the optional extra "
        "(pip install 'c4studio[assistant]')."
    ),
)
@click.option(
    "--dynamic-perspectives",
    is_flag=True,
    help=(
        "Let the server read a perspective's url for its live value. OFF "
        "BY DEFAULT: the addresses come from the workspace file, so "
        "opening someone else's model would otherwise make this machine "
        "call their hosts. Only http and https are followed."
    ),
)
@click.option("--port", default=8090, show_default=True, help="Port to listen on.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Do not open a browser window automatically.",
)
@click.option(
    "--viewer",
    is_flag=True,
    default=False,
    help="Serve read-only: the DSL cannot be edited in the browser.",
)
def webapp(
    path: Path,
    port: int,
    host: str,
    no_browser: bool,
    viewer: bool,
    assistant: bool,
    dynamic_perspectives: bool,
) -> None:
    """Launch the React web application backend for PATH.

    PATH may be a directory (browsed as the source root) or a single source
    file (loaded eagerly, with its parent directory as the root).

    Serves the full Studio by default. ``--viewer`` serves Viewer instead:
    the DSL cannot be edited, though diagrams can still be arranged —
    layout is per-user UI state in a gitignored sidecar either way.

    ``--assistant`` additionally enables the DSL assistant, which is the
    one feature that sends your workspace source to an external API. It is
    off unless you ask for it.
    """
    from c4studio.webapp.server import run_server

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

    run_server(
        root=root,
        initial=initial,
        host=host,
        port=port,
        read_only=viewer,
        assistant=assistant,
        dynamic_perspectives=dynamic_perspectives,
    )
