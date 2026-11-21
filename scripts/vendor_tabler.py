"""Regenerate the bundled Tabler Icons pack from its npm tarball (PP-239).

The pack ships as one JSON file, ``src/c4studio/icon_packs/tabler/icons.json``,
rather than as five thousand SVG files: one icon per line keeps a version
bump reviewable, and the wheel compresses one file far better than many
small ones. Each icon keeps only what differs between them, its shapes;
``c4studio.bundled_icons`` puts the common ``<svg>`` wrapper back.

Left out:

- ``brand-*``: other companies' logos. The drawings are MIT, the marks are
  trademarks, which is why brand logos come only from the curated Simple
  Icons subset (PP-240).
- the filled style: Tabler is an outline set, and a filled duplicate of a
  fifth of it doubles the list without adding a shape.

Every shape is checked against a short list of SVG elements and
attributes, so nothing that can carry script reaches a file the Studio
serves or copies into a workspace.

Usage::

    curl -sLO https://registry.npmjs.org/@tabler/icons/-/icons-3.50.0.tgz
    uv run python scripts/vendor_tabler.py icons-3.50.0.tgz \\
        --version 3.50.0 --sha1 fb2bdeec8896e173c34789902aeb51ffda139753

``--sha1`` is the ``dist.shasum`` the registry lists for that version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src/c4studio/icon_packs/tabler"

#: The invisible 24x24 box every Tabler icon starts with, for editors.
_BOUNDING_BOX = '<path stroke="none" d="M0 0h24v24H0z" fill="none" />'

_ELEMENT = re.compile(r"<(\w+)((?:\s+[\w-]+=\"[^\"]*\")*)\s*/>")
_ATTRIBUTE = re.compile(r"([\w-]+)=\"([^\"]*)\"")
_SHAPES = frozenset(
    {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}
)
_ATTRIBUTES = frozenset(
    {
        "d",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "width",
        "height",
        "points",
        "fill",
        "stroke",
        "stroke-width",
    }
)
_NUMERIC = re.compile(r"[-\d.,\s]*")


class VendorError(Exception):
    """The tarball is not the one expected, or an icon is not plain shapes."""


def shapes(name: str, svg: str) -> str:
    """The icon's shapes, checked, without the wrapper or the bounding box.

    Raises:
        VendorError: for anything but the expected wrapper and plain shapes.
    """
    head, _, rest = svg.partition(">")
    if 'stroke="currentColor"' not in head or 'viewBox="0 0 24 24"' not in head:
        raise VendorError(f"{name}: not a 24 px outline icon")
    body = rest.rsplit("</svg>", 1)[0].replace(_BOUNDING_BOX, "")
    body = re.sub(r"\s*\n\s*", "", body).strip()
    if _ELEMENT.sub("", body).strip():
        raise VendorError(f"{name}: something other than self-closing shapes")
    for element, attributes in _ELEMENT.findall(body):
        if element not in _SHAPES:
            raise VendorError(f"{name}: <{element}>")
        for attribute, value in _ATTRIBUTE.findall(attributes):
            if attribute not in _ATTRIBUTES:
                raise VendorError(f"{name}: {attribute}=")
            if attribute in {"fill", "stroke"}:
                if value not in {"none", "currentColor"}:
                    raise VendorError(f"{name}: {attribute}={value!r}")
            elif attribute == "d":
                if not re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz\d.,\s-]*", value):
                    raise VendorError(f"{name}: d={value!r}")
            elif not _NUMERIC.fullmatch(value):
                raise VendorError(f"{name}: {attribute}={value!r}")
    return body


def vendor(tarball: Path, version: str, sha1: str) -> int:
    """Write ``icons.json`` and ``LICENSE``; return the number of icons."""
    digest = hashlib.sha1(tarball.read_bytes()).hexdigest()  # noqa: S324
    if digest != sha1:
        raise VendorError(f"sha1 {digest}, expected {sha1}")
    icons: dict[str, list[object]] = {}
    with tarfile.open(tarball) as archive:

        def read(member: str) -> str:
            handle = archive.extractfile(member)
            if handle is None:
                raise VendorError(f"{member} is not a file")
            return handle.read().decode("utf-8")

        meta = json.loads(read("package/icons.json"))
        licence = read("package/LICENSE")
        for member in sorted(archive.getnames()):
            match = re.fullmatch(r"package/icons/outline/([a-z0-9-]+)\.svg", member)
            if match is None or match.group(1).startswith("brand-"):
                continue
            name = match.group(1)
            info = meta.get(name, {})
            icons[name] = [
                info.get("category", ""),
                # Tabler's metadata has some tags as JSON numbers.
                [str(tag) for tag in info.get("tags", [])],
                shapes(name, read(member)),
            ]
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "{",
        f'"version": {json.dumps(version)},',
        f'"source": "https://registry.npmjs.org/@tabler/icons/-/icons-{version}.tgz",',
        f'"sha1": {json.dumps(sha1)},',
        '"icons": {',
        ",\n".join(
            f"{json.dumps(name)}: {json.dumps(entry, ensure_ascii=False)}"
            for name, entry in icons.items()
        ),
        "}",
        "}",
        "",
    ]
    (OUT / "icons.json").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "LICENSE").write_text(licence, encoding="utf-8")
    return len(icons)


def main() -> None:
    """Parse the command line and vendor the pack."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("tarball", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha1", required=True)
    args = parser.parse_args()
    try:
        count = vendor(args.tarball, args.version, args.sha1)
    except VendorError as exc:
        sys.exit(f"vendor_tabler: {exc}")
    print(f"{count} icons -> {OUT / 'icons.json'}")


if __name__ == "__main__":
    main()
