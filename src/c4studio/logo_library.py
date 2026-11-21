"""The images the Studio's logo picker offers (PP-238).

A logo is one file, usually already somewhere in the repository: a
``brand/`` folder, a ``docs/`` image, the README's banner. So unlike the
icon library (``icon_library``), which reads one ``icons/`` folder of
downloaded packs, this lists every image under the workspace's folder and
ranks the likely ones first: anything in ``brand/``, or named like a logo.

Build output and dependencies are left out, both by name (``node_modules``,
``dist`` and the like) and, inside a git checkout, by ``.gitignore``: a
logo the repository does not hold would vanish for the next person to
clone it.

A file picked from elsewhere on the machine is copied in, to ``brand/``,
so the logo travels with the workspace. :func:`plan_copy` decides where,
and finds an existing copy by content first, so picking the same file
twice does not leave two of it.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from c4studio.icon_library import IMAGE_SUFFIXES
from c4studio.icons import MAX_ICON_BYTES

#: Where a copied-in logo goes, beside the workspace file.
BRAND_FOLDER = "brand"

#: Build output, dependencies and caches: never where a logo is kept.
SKIPPED_FOLDERS = frozenset(
    {
        "node_modules",
        "dist",
        "build",
        "out",
        "_site",
        "coverage",
        "target",
        "__pycache__",
        "venv",
    }
)

#: Past this the folder is not a workspace's; the listing says it stopped.
MAX_FILES = 5_000

#: A file named like a logo. ``mark`` only as a whole word, so a
#: ``benchmark.png`` is not suggested.
_LOGO_NAME = re.compile(
    r"logo|brand|wordmark|(?:^|[-_ .])mark(?:$|[-_ .])", re.IGNORECASE
)


class LogoCopyError(Exception):
    """A file that cannot be copied in as a logo."""


@dataclass(frozen=True)
class LogoCandidate:
    """One image the picker lists."""

    #: Relative to the directory the listing was made against, POSIX.
    path: str
    #: Bytes on disk: past :data:`MAX_ICON_BYTES` it is listed, not usable.
    size: int
    #: In ``brand/`` or named like a logo: listed under "Suggested".
    suggested: bool


def is_suggested(inner: PurePosixPath) -> bool:
    """Whether a file at ``inner`` (under the workspace folder) looks like a logo."""
    return (
        bool(inner.parts) and inner.parts[0] == BRAND_FOLDER and len(inner.parts) > 1
    ) or bool(_LOGO_NAME.search(inner.stem))


def _git_ignored(folder: Path, paths: list[str]) -> set[str]:
    """The ``paths`` (relative to ``folder``) git ignores; none outside a checkout."""
    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["git", "-C", str(folder), "check-ignore", "--stdin", "-z"],
            input="\0".join(paths).encode("utf-8"),
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    # 0: some ignored, 1: none, 128: not a repository (or git failed).
    if result.returncode != 0:
        return set()
    return {p for p in result.stdout.decode("utf-8").split("\0") if p}


def _walk(folder: Path) -> tuple[list[Path], bool]:
    """Image files under ``folder``, pruning hidden and build folders."""
    found: list[Path] = []
    for current, dirs, files in os.walk(folder):
        dirs[:] = sorted(
            d for d in dirs if not d.startswith(".") and d not in SKIPPED_FOLDERS
        )
        for name in sorted(files):
            if name.startswith(".") or Path(name).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            found.append(Path(current) / name)
            if len(found) >= MAX_FILES:
                return found, True
    return found, False


def scan(folder: Path, relative_to: Path) -> tuple[list[LogoCandidate], bool]:
    """List the images under ``folder`` a logo could be.

    Args:
        folder: The workspace file's folder.
        relative_to: The directory each entry's ``path`` is relative to.

    Returns:
        The images, suggested first and then by path, and whether the
        listing stopped at :data:`MAX_FILES`.
    """
    if not folder.is_dir():
        return [], False
    files, truncated = _walk(folder)
    inner = [file.relative_to(folder).as_posix() for file in files]
    ignored = _git_ignored(folder, inner)
    candidates: list[LogoCandidate] = []
    for file, rel in zip(files, inner, strict=True):
        if rel in ignored:
            continue
        try:
            size = file.stat().st_size
        except OSError:
            continue
        candidates.append(
            LogoCandidate(
                path=file.relative_to(relative_to).as_posix(),
                size=size,
                suggested=is_suggested(PurePosixPath(rel)),
            )
        )
    candidates.sort(key=lambda c: (not c.suggested, c.path.lower()))
    return candidates, truncated


def _safe_name(name: str) -> str:
    """The file's own name, checked: no folders, no hidden files, an image type.

    Raises:
        LogoCopyError: for anything else.
    """
    base = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not base or base.startswith("."):
        raise LogoCopyError(f"Not a file name: {name!r}")
    if PurePosixPath(base).suffix.lower() not in IMAGE_SUFFIXES:
        raise LogoCopyError("A logo is an image: " + ", ".join(sorted(IMAGE_SUFFIXES)))
    return base


def plan_copy(
    folder: Path, name: str, content: bytes, existing: list[Path]
) -> tuple[Path, bool]:
    """Where a picked file goes in the workspace, and whether it is already there.

    Args:
        folder: The workspace file's folder.
        name: The picked file's name; only its last part is used.
        content: Its bytes.
        existing: Images already in the workspace, compared by content
            first so the same file picked twice is found, not copied again.

    Returns:
        The file to use, and ``True`` when it is one of ``existing``. A new
        file is ``brand/<name>``, numbered when that name is taken by a
        different image.

    Raises:
        LogoCopyError: for a name that is not an image file, or content too
            large to embed.
    """
    base = _safe_name(name)
    if len(content) > MAX_ICON_BYTES:
        raise LogoCopyError(
            f"{base} is {len(content) // 1024} KB; a logo is embedded, "
            f"so at most {MAX_ICON_BYTES // 1024} KB"
        )
    digest = hashlib.sha256(content).digest()
    for path in existing:
        try:
            if path.stat().st_size != len(content):
                continue
            if hashlib.sha256(path.read_bytes()).digest() == digest:
                return path, True
        except OSError:
            continue
    target = folder / BRAND_FOLDER / base
    stem, suffix = PurePosixPath(base).stem, PurePosixPath(base).suffix
    number = 2
    while target.exists():
        target = folder / BRAND_FOLDER / f"{stem}-{number}{suffix}"
        number += 1
    return target, False
