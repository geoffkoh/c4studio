"""The icon library the Studio's picker browses (PP-233).

An icon pack is just files: AWS Architecture Icons, Font Awesome Free or
Simple Icons, downloaded and unzipped into an ``icons/`` folder beside the
workspace and committed with it. Nothing here downloads anything; the
Studio is local-first, and packs' licences are the user's to accept.

Packs are noisy to browse as they ship. AWS gives every service at 16, 32,
48 and 64 px, as SVG and PNG, under names like ``Arch_AWS-Lambda_48.svg``.
So the library collapses each icon's size and format variants into one
entry, preferring SVG and then the 48 px drawing, and names it the way a
person would ("Lambda"). Light and dark variants, and Font Awesome's
solid/regular/brands styles, look different and stay apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from c4studio.icons import MAX_ICON_BYTES

#: The folder beside the workspace file the picker lists.
ICON_FOLDER = "icons"

#: Image types every surface can draw, as ``icons.file_data_uri`` reads.
IMAGE_SUFFIXES = frozenset({".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"})

#: Enough for several full packs; past it the folder is probably not one.
MAX_ICONS = 20_000

#: Font Awesome keeps each style in a folder of its own name.
_STYLE_FOLDERS = frozenset({"solid", "regular", "brands", "light", "thin", "duotone"})

_SIZE = re.compile(r"[_-](\d{2,3})$")
_SHADE = re.compile(r"[_-](light|dark)$", re.IGNORECASE)
_PREFIX = re.compile(r"^(?:Arch-Category|Arch|Res)_")
_VENDOR = re.compile(r"^(?:AWS|Amazon)[-_]")
_SEPARATORS = re.compile(r"[-_\s]+")


@dataclass(frozen=True)
class LibraryIcon:
    """One icon the picker offers."""

    #: Relative to the directory the library was listed against, POSIX.
    path: str
    #: What a person would call it: ``Lambda``, ``database (solid)``.
    name: str
    #: The first folder under ``icons/`` (``aws``), or ``""`` for loose files.
    pack: str


def friendly_name(path: PurePosixPath) -> str:
    """Name an icon file the way a person would.

    ``Arch_AWS-Lambda_48.svg`` is ``Lambda``; ``svgs/solid/database.svg``
    is ``database (solid)``; ``Res_..._48_Dark.svg`` keeps ``(dark)``.
    """
    stem = path.stem
    qualifier = ""
    shade = _SHADE.search(stem)
    if shade:
        qualifier = shade.group(1).lower()
        stem = stem[: shade.start()]
    stem = _SIZE.sub("", stem)
    stem = _VENDOR.sub("", _PREFIX.sub("", stem))
    name = _SEPARATORS.sub(" ", stem).strip() or path.stem
    if not qualifier and path.parent.name.lower() in _STYLE_FOLDERS:
        qualifier = path.parent.name.lower()
    return f"{name} ({qualifier})" if qualifier else name


def _preference(path: PurePosixPath) -> tuple[int, int]:
    """Lower is better: SVG first, then the drawing nearest 48 px."""
    match = _SIZE.search(_SHADE.sub("", path.stem))
    size = int(match.group(1)) if match else 48
    return (0 if path.suffix.lower() == ".svg" else 1, abs(size - 48))


def scan(folder: Path, relative_to: Path) -> tuple[list[LibraryIcon], bool]:
    """List the icons under ``folder``, one entry per icon.

    Args:
        folder: The icon folder; a missing one lists nothing.
        relative_to: The directory each entry's ``path`` is relative to.

    Returns:
        The icons sorted by pack and name, and whether the listing stopped
        at :data:`MAX_ICONS`. Hidden files, other file types and images too
        large to embed are left out.
    """
    if not folder.is_dir():
        return [], False
    best: dict[tuple[str, str], tuple[tuple[int, int], LibraryIcon]] = {}
    seen = 0
    truncated = False
    for file in sorted(folder.rglob("*")):
        inner = file.relative_to(folder)
        if any(part.startswith(".") for part in inner.parts):
            continue
        if file.suffix.lower() not in IMAGE_SUFFIXES or not file.is_file():
            continue
        if file.stat().st_size > MAX_ICON_BYTES:
            continue
        seen += 1
        if seen > MAX_ICONS:
            truncated = True
            break
        posix = PurePosixPath(inner.as_posix())
        pack = posix.parts[0] if len(posix.parts) > 1 else ""
        icon = LibraryIcon(
            path=file.relative_to(relative_to).as_posix(),
            name=friendly_name(posix),
            pack=pack,
        )
        key = (pack, icon.name.lower())
        rank = _preference(posix)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, icon)
    icons = sorted(
        (icon for _, icon in best.values()),
        key=lambda icon: (icon.pack, icon.name.lower()),
    )
    return icons, truncated
