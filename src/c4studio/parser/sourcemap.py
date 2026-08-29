"""Mapping flattened DSL lines back to the file they came from.

``!include`` is resolved textually before tokenising, so the parser only
ever sees one flat source and every token's line number refers to *that*.
Without a map, a problem inside an included fragment is reported against a
line of a file that does not contain it — and the fragment is not named at
all.

The map is a list of runs. Each run says "flattened lines from N onwards
came from this file, starting at line M", which is all that is needed
because expansion only ever splices whole lines.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class _Run:
    flat_start: int
    path: Path | None
    origin_start: int


@dataclass
class SourceMap:
    """Resolves a line of the flattened source to ``(path, line)``."""

    runs: list[_Run] = field(default_factory=list)

    def add(self, flat_start: int, path: Path | None, origin_start: int) -> None:
        """Record that a run of flattened lines begins at ``flat_start``."""
        self.runs.append(_Run(flat_start, path, origin_start))

    def resolve(self, flat_line: int) -> tuple[Path | None, int]:
        """Return the file and 1-based line ``flat_line`` originated from.

        Falls back to the flattened line itself when no run covers it,
        which happens only when nothing was ever recorded (a bare string
        parsed with no file context).
        """
        if not self.runs:
            return None, flat_line
        starts = [run.flat_start for run in self.runs]
        index = bisect.bisect_right(starts, flat_line) - 1
        if index < 0:
            return None, flat_line
        run = self.runs[index]
        return run.path, run.origin_start + (flat_line - run.flat_start)
