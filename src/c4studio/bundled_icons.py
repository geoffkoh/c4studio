"""The icon packs c4studio ships, and copying one icon into a workspace (PP-239).

The icon library (``icon_library``) lists what a workspace holds; these
are what the package holds, offered beside it so a workspace with no
``icons/`` folder still has something to pick. Only Tabler Icons for now:
MIT, one-colour outline, drawn in ``currentColor`` so every renderer
paints it in the box's text colour.

A picked icon is never referenced inside the installed package. It is
copied to ``icons/<pack>/`` beside the workspace file, with the pack's
licence, and the style names that copy: the DSL then works upstream, on a
machine without c4studio, and with a later c4studio whose pack changed.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from c4studio.icon_library import ICON_FOLDER

#: The packs, by the folder each is copied into under ``icons/``.
PACKS = ("tabler",)

#: What a pack's ``icons.json`` leaves out of every icon (see
#: ``scripts/vendor_tabler.py``).
_TABLER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">{shapes}</svg>\n'
)

_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class BundledIconError(Exception):
    """No such pack or icon, or the copy cannot be made."""


@dataclass(frozen=True)
class BundledIcon:
    """One icon a pack offers."""

    pack: str
    #: The file name without ``.svg``: ``database``, ``server-2``.
    name: str
    category: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Pack:
    """One bundled pack, as its ``icons.json`` lists it."""

    name: str
    version: str
    licence: str
    #: name -> (category, tags, shapes)
    icons: dict[str, tuple[str, tuple[str, ...], str]]


@lru_cache(maxsize=len(PACKS))
def load(pack: str) -> Pack:
    """Read a pack from the package, once per process.

    Raises:
        BundledIconError: for a pack c4studio does not ship.
    """
    if pack not in PACKS:
        raise BundledIconError(f"No bundled pack {pack!r}")
    folder = importlib.resources.files("c4studio") / "icon_packs" / pack
    data = json.loads((folder / "icons.json").read_text(encoding="utf-8"))
    return Pack(
        name=pack,
        version=data["version"],
        licence=(folder / "LICENSE").read_text(encoding="utf-8"),
        icons={
            name: (category, tuple(tags), shapes)
            for name, (category, tags, shapes) in data["icons"].items()
        },
    )


def icons(pack: str) -> list[BundledIcon]:
    """Every icon in ``pack``, by name."""
    return [
        BundledIcon(pack=pack, name=name, category=category, tags=tags)
        for name, (category, tags, _) in sorted(load(pack).icons.items())
    ]


def svg(pack: str, name: str) -> str:
    """One icon's SVG file, as it is served and copied.

    Raises:
        BundledIconError: for an unknown pack or icon.
    """
    entry = load(pack).icons.get(name) if _NAME.fullmatch(name) else None
    if entry is None:
        raise BundledIconError(f"No icon {name!r} in {pack}")
    return _TABLER_SVG.format(shapes=entry[2])


def copy_into(folder: Path, pack: str, name: str) -> tuple[Path, bool]:
    """Copy one icon, and the pack's licence, under ``folder/icons/<pack>/``.

    An icon already there is left as it is and used: it is either this
    copy made earlier or a file the user put there on purpose.

    Args:
        folder: The workspace file's folder.
        pack: A bundled pack.
        name: An icon in it.

    Returns:
        The icon's file, and whether this call wrote it.

    Raises:
        BundledIconError: for an unknown icon, or a file that cannot be
            written.
    """
    content = svg(pack, name)
    target = folder / ICON_FOLDER / pack / f"{name}.svg"
    licence = target.parent / "LICENSE"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not licence.exists():
            licence.write_text(load(pack).licence, encoding="utf-8")
        if target.exists():
            return target, False
        with target.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return target, False
    except OSError as exc:
        raise BundledIconError(f"Could not write {target.name}: {exc}") from exc
    return target, True
