// A line diff, for reviewing what the assistant proposes.
//
// Hand-written rather than a dependency: it is one classic algorithm over
// arrays of strings, the no-new-dependencies rule in CLAUDE.md applies to
// npm too, and keeping it pure means it can be exercised headlessly —
// which matters more here than usual, because a diff that is subtly wrong
// is a diff someone accepts without noticing.

/** One line of the rendered diff. */
export interface DiffLine {
  kind: "same" | "added" | "removed";
  text: string;
  /** 1-based line number in the original, for removed and unchanged. */
  before: number | null;
  /** 1-based line number in the proposal, for added and unchanged. */
  after: number | null;
}

export interface DiffStats {
  added: number;
  removed: number;
}

function splitLines(text: string): string[] {
  const trimmed = text.replace(/\n$/, "");
  return trimmed === "" ? [] : trimmed.split("\n");
}

/** Longest common subsequence lengths, as a (n+1) x (m+1) table. */
function lcsTable(a: readonly string[], b: readonly string[]): number[][] {
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] =
        a[i] === b[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

/**
 * Diff two texts by line.
 *
 * Removals come before additions at the same position, which is what makes
 * a changed line read as one edit rather than two unrelated ones.
 */
export function diffLines(before: string, after: string): DiffLine[] {
  // A trailing newline would otherwise show as an empty last line on both
  // sides of every diff; empty text is no lines, not one blank one, or a
  // new file would open with a phantom deletion.
  const a = splitLines(before);
  const b = splitLines(after);
  const table = lcsTable(a, b);

  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i], before: i + 1, after: j + 1 });
      i++;
      j++;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      out.push({ kind: "removed", text: a[i], before: i + 1, after: null });
      i++;
    } else {
      out.push({ kind: "added", text: b[j], before: null, after: j + 1 });
      j++;
    }
  }
  while (i < a.length) {
    out.push({ kind: "removed", text: a[i], before: i + 1, after: null });
    i++;
  }
  while (j < b.length) {
    out.push({ kind: "added", text: b[j], before: null, after: j + 1 });
    j++;
  }
  return out;
}

export function diffStats(lines: readonly DiffLine[]): DiffStats {
  return {
    added: lines.filter((line) => line.kind === "added").length,
    removed: lines.filter((line) => line.kind === "removed").length,
  };
}

/**
 * Drop runs of unchanged lines longer than `context` either side of a
 * change, replacing each with a gap marker.
 *
 * A whole-file diff of a large workspace is unreviewable, and an
 * unreviewable diff gets accepted unread — which is the failure this
 * whole screen exists to prevent.
 */
export function collapseUnchanged(
  lines: readonly DiffLine[],
  context = 3,
): (DiffLine | { kind: "gap"; hidden: number })[] {
  const changed = lines.map((line) => line.kind !== "same");
  const keep = lines.map((_, index) =>
    changed
      .slice(Math.max(0, index - context), index + context + 1)
      .some(Boolean),
  );

  const out: (DiffLine | { kind: "gap"; hidden: number })[] = [];
  let hidden = 0;
  lines.forEach((line, index) => {
    if (keep[index]) {
      if (hidden > 0) {
        out.push({ kind: "gap", hidden });
        hidden = 0;
      }
      out.push(line);
    } else {
      hidden++;
    }
  });
  if (hidden > 0) out.push({ kind: "gap", hidden });
  return out;
}
