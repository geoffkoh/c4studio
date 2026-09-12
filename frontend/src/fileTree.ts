// Turning the flat `{path, kind}` listing from GET /api/files into the rows
// a tree renders.
//
// Kept pure and separate from the component on purpose: this is the part
// with the logic — grouping, filtering, ordering, what counts as visible —
// and a pure function can be exercised directly, which a tree of DOM nodes
// cannot.

import type { SourceEntry } from "./types";

/** One visible line of the tree, already flattened and ordered. */
export interface TreeRow {
  /** Directory path for a folder, full file path for a file. Unique. */
  path: string;
  /** Last segment — what is actually shown. */
  name: string;
  depth: number;
  kind: "dir" | "workspace" | "fragment";
  /** Folders only: whether this row is open. */
  expanded?: boolean;
  /** Folders only: how many files it contains, filtering included. */
  count?: number;
}

interface Node {
  name: string;
  path: string;
  kind: "dir" | "workspace" | "fragment";
  children: Map<string, Node>;
  /** Files in this subtree, so a collapsed folder can still say how many. */
  fileCount: number;
}

function emptyNode(name: string, path: string): Node {
  return { name, path, kind: "dir", children: new Map(), fileCount: 0 };
}

/** Folders first, then files; each group alphabetical and case-insensitive. */
function compare(a: Node, b: Node): number {
  if ((a.kind === "dir") !== (b.kind === "dir")) return a.kind === "dir" ? -1 : 1;
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

function insert(root: Node, entry: SourceEntry): void {
  const segments = entry.path.split("/").filter(Boolean);
  let node = root;
  segments.forEach((segment, index) => {
    const isLeaf = index === segments.length - 1;
    const path = segments.slice(0, index + 1).join("/");
    let child = node.children.get(segment);
    if (!child) {
      child = emptyNode(segment, path);
      node.children.set(segment, child);
    }
    if (isLeaf) child.kind = entry.kind;
    node.fileCount += 1;
    node = child;
  });
}

/** Every ancestor directory path of a file path, outermost first. */
export function ancestorsOf(path: string): string[] {
  const segments = path.split("/").filter(Boolean);
  // The last segment is the file itself, so it is not an ancestor.
  return segments
    .slice(0, -1)
    .map((_, index) => segments.slice(0, index + 1).join("/"));
}

export interface TreeOptions {
  /** Case-insensitive substring match against the whole path. */
  query?: string;
  /** Directory paths the user has opened. */
  expanded?: ReadonlySet<string>;
}

/**
 * Flatten the listing into the rows a tree should draw.
 *
 * While a query is active every folder is treated as open: the point of
 * searching is to see the matches, and a match hidden inside a collapsed
 * folder would be a search that found nothing. The user's own expansion is
 * left untouched, so clearing the box returns the tree as they had it.
 */
export function buildRows(
  entries: readonly SourceEntry[],
  { query = "", expanded }: TreeOptions = {},
): TreeRow[] {
  const needle = query.trim().toLowerCase();
  const matching = needle
    ? entries.filter((entry) => entry.path.toLowerCase().includes(needle))
    : entries;

  const root = emptyNode("", "");
  for (const entry of matching) insert(root, entry);

  const isOpen = (path: string) => (needle ? true : (expanded?.has(path) ?? false));

  const rows: TreeRow[] = [];
  const walk = (node: Node, depth: number): void => {
    for (const child of [...node.children.values()].sort(compare)) {
      if (child.kind === "dir") {
        const open = isOpen(child.path);
        rows.push({
          path: child.path,
          name: child.name,
          depth,
          kind: "dir",
          expanded: open,
          count: child.fileCount,
        });
        if (open) walk(child, depth + 1);
      } else {
        rows.push({
          path: child.path,
          name: child.name,
          depth,
          kind: child.kind,
        });
      }
    }
  };
  walk(root, 0);
  return rows;
}

/**
 * The expansion to start from: the folders leading to the loaded file.
 *
 * Everything else stays shut. A tree that opens itself completely is the
 * flat list this replaced, which stops being usable at exactly the scale
 * the tree exists for.
 */
export function initialExpansion(currentPath: string | null): Set<string> {
  return new Set(currentPath ? ancestorsOf(currentPath) : []);
}
