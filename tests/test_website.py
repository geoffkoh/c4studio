"""The project site is built from sources that cannot drift (PP-217).

`website/build.py` assembles the GitHub Pages site. These tests hold it to
the things it claims: every link and anchor resolves, every command and
every `c4studio.*` property is documented, the action's inputs are all in
the CI page, and the Python examples run. A site that documents a flag
the CLI no longer has is worse than no site — it is confidently wrong.

The live example (`c4 publish`) needs Node and is left out here; the
build's own CI job runs it.
"""

from __future__ import annotations

import html
import importlib.util
import os
import re
import shutil
import sys
import warnings
from pathlib import Path
from types import ModuleType

import click
import pytest

from c4studio.cli.main import cli

ROOT = Path(__file__).parent.parent
WEBSITE = ROOT / "website"
CONTENT = WEBSITE / "content"


def _load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "c4studio_site_build", WEBSITE / "build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out: Path = tmp_path_factory.mktemp("site") / "_site"
    builder.build(out, example=False)
    return out


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_page_is_written(site: Path) -> None:
    for page in builder.PAGES:
        assert (site / f"{page.slug}.html").is_file(), page.slug
    for name in ("index.html", "404.html", "sitemap.xml", "robots.txt", ".nojekyll"):
        assert (site / name).is_file(), name
    assert (site / "assets" / "search-index.js").is_file()


def test_the_home_page_keeps_its_search_console_verification(site: Path) -> None:
    """Google re-checks this tag; losing it silently un-verifies the site."""
    assert (
        '<meta name="google-site-verification" '
        'content="Dg6YXgvCsF0Kl9JaQa82lPxGN4vur9pfZDWyUDzWZz8">'
    ) in _text(site / "index.html")


def test_every_internal_link_and_anchor_resolves(site: Path) -> None:
    """A broken link is the commonest way a docs site rots."""
    checked = 0
    for page in sorted(site.glob("*.html")):
        if page.name == "404.html":  # uses <base href> to the live site
            continue
        for attribute, raw in re.findall(r'\b(href|src)="([^"]+)"', _text(page)):
            target = html.unescape(raw)
            if re.match(
                r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE
            ) or target.startswith("example/"):
                continue
            path_part, _, anchor = target.partition("#")
            destination = page if not path_part else (page.parent / path_part)
            assert destination.exists(), f"{page.name}: {attribute}={target!r}"
            if anchor:
                ids = re.findall(r'\bid="([^"]+)"', _text(destination))
                assert anchor in ids, f"{page.name}: no #{anchor} in {destination.name}"
            checked += 1
    assert checked > 100, "the link check matched almost nothing"


def test_the_cli_reference_covers_every_command(site: Path) -> None:
    page = _text(site / "cli.html")
    context = click.Context(cli, info_name="c4")
    for name in cli.list_commands(context):
        assert f'id="c4-{name}"' in page, name
        command = cli.get_command(context, name)
        assert command is not None
        for param in command.params:
            if isinstance(param, click.Option) and not param.hidden:
                assert param.opts[0] in page, f"c4 {name} {param.opts[0]}"


def test_every_c4studio_property_is_on_the_extensions_page() -> None:
    """A new `c4studio.*` key must be documented where users look for it."""
    modules = {
        "c4studio."
        + ".".join(p.relative_to(ROOT / "src" / "c4studio").with_suffix("").parts)
        for p in (ROOT / "src" / "c4studio").rglob("*.py")
    } | {
        "c4studio." + ".".join(p.relative_to(ROOT / "src" / "c4studio").parts)
        for p in (ROOT / "src" / "c4studio").rglob("*")
        if p.is_dir()
    }
    keys: set[str] = set()
    for source in (ROOT / "src" / "c4studio").rglob("*.py"):
        for key in re.findall(r'"(c4studio\.[a-z][\w.]*)"', _text(source)):
            if key not in modules:
                keys.add(key.rstrip("."))
    assert {"c4studio.autolayout", "c4studio.legend", "c4studio.badge"} <= keys
    page = _text(CONTENT / "extensions.md")
    for key in sorted(keys):
        assert key in page, key


def test_every_action_input_is_on_the_ci_page() -> None:
    action = _text(ROOT / "action.yml")
    inputs_block = action.split("\ninputs:\n", 1)[1].split("\noutputs:\n", 1)[0]
    names = re.findall(r"^  ([a-z][\w-]*):\s*$", inputs_block, re.MULTILINE)
    outputs_block = action.split("\noutputs:\n", 1)[1].split("\nruns:\n", 1)[0]
    outputs = re.findall(r"^  ([a-z][\w-]*):\s*$", outputs_block, re.MULTILINE)
    assert len(names) >= 6 and outputs
    page = _text(CONTENT / "ci.md")
    for name in [*names, *outputs]:
        assert f"`{name}`" in page, name


def test_shortcuts_come_from_the_studio_and_reach_the_page(site: Path) -> None:
    lists = builder.studio_shortcuts()
    assert len(lists["SHORTCUTS"]) >= 10 and len(lists["GESTURES"]) >= 5
    page = html.unescape(_text(site / "studio.html"))
    for keys, action in lists["SHORTCUTS"] + lists["GESTURES"]:
        assert keys in page and action in page, keys


def test_the_highlighter_reads_the_spa_vocabulary() -> None:
    keywords, properties = builder.dsl_vocabulary()
    assert {"workspace", "softwaresystem", "container", "perspectives"} <= keywords
    assert {"include", "autolayout", "properties"} <= properties
    painted = builder.Highlighter().highlight(
        "dsl",
        'api = container "API" {\n    properties {\n        "c4studio.badge" "#fff"\n    }\n}',
    )
    assert '<span class="tok-def">api</span>' in painted
    assert '<span class="tok-keyword">container</span>' in painted
    assert '<span class="tok-ext">&quot;c4studio.badge&quot;</span>' in painted or (
        '<span class="tok-ext">"c4studio.badge"</span>' in painted
    )


def test_slugs_match_github_so_docs_links_work_on_both() -> None:
    assert (
        builder.slugify("10. c4studio's own extensions")
        == "10-c4studios-own-extensions"
    )
    assert (
        builder.slugify("What changed (<code>c4 diff</code>)") == "what-changed-c4-diff"
    )


def _python_blocks() -> list[str]:
    text = _text(CONTENT / "python-api.md")
    return re.findall(r"^```python\n(.*?)^```", text, re.DOTALL | re.MULTILINE)


def _has_node() -> bool:
    return bool(os.environ.get("C4STUDIO_NODE") or shutil.which("node"))


@pytest.mark.parametrize(
    "block", _python_blocks(), ids=lambda b: b.splitlines()[0][:40]
)
def test_python_api_examples_run(
    block: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if ("render_view" in block or "publish(" in block) and not _has_node():
        pytest.skip("rendering needs Node")
    shutil.copy(
        ROOT / "samples" / "internet_banking.dsl", tmp_path / "architecture.dsl"
    )
    monkeypatch.chdir(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exec(compile(block, "python-api.md", "exec"), {"__name__": "__example__"})


def test_python_api_has_examples_to_run() -> None:
    assert len(_python_blocks()) >= 6
