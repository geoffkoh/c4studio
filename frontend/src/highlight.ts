// The Structurizr DSL vocabulary and token shapes, shared by everything in
// the SPA that has to make sense of DSL text.
//
// No mainstream highlighter ships a Structurizr grammar, so this mirrors the
// backend parser's tokenizer (dsl.py _TOKEN_RE). It is deliberately the SPA's
// only copy: `dslLanguage.ts` builds the CodeMirror StreamLanguage from these
// patterns rather than restating them, so adding a keyword is one edit here.

/** How a token is painted. Names match the `dsl-*` CSS classes. */
export type DslTokenClass =
  | "comment"
  | "string"
  | "color"
  | "keyword"
  | "property"
  | "def"
  | "arrow"
  | "directive"
  | "number";

export const DSL_KEYWORDS: ReadonlySet<string> = new Set([
  "workspace",
  "model",
  "views",
  "person",
  "softwaresystem",
  "container",
  "component",
  "deploymentnode",
  "infrastructurenode",
  "softwaresysteminstance",
  "containerinstance",
  "deploymentenvironment",
  "enterprise",
  "group",
  "systemlandscape",
  "systemcontext",
  "dynamic",
  "deployment",
  "filtered",
  "styles",
  "element",
  "relationship",
  "theme",
  "themes",
  "branding",
  "terminology",
]);

export const DSL_PROPERTIES: ReadonlySet<string> = new Set([
  "include",
  "exclude",
  "autolayout",
  "background",
  "color",
  "colour",
  "stroke",
  "shape",
  "border",
  "icon",
  "fontsize",
  "opacity",
  "width",
  "height",
  "thickness",
  "dashed",
]);

/**
 * Token shapes, each anchored so it can be fed straight to CodeMirror's
 * `StringStream.match`. Order matters at the call site: `color` must be
 * tried before punctuation, `arrow` before `-`, and both comment forms
 * before `/`.
 */
export const DSL_PATTERNS = {
  lineComment: /^\/\/[^\n]*/,
  /**
   * `#` to end of line — but **only** valid where nothing but whitespace
   * precedes it, which this pattern cannot express on its own. The caller
   * has to check that; see `hashCommentStartsHere`.
   *
   * Mid-line a `#` is a colour (`background #1a2b3c`), so matching this
   * unguarded would swallow the rest of every style line.
   */
  hashComment: /^#[^\n]*/,
  blockCommentOpen: /^\/\*/,
  blockCommentClose: /^\*\//,
  string: /^"(?:[^"\\]|\\.)*"/,
  color: /^#[0-9A-Fa-f]{3,8}/,
  arrow: /^->/,
  directive: /^![A-Za-z]+/,
  word: /^[A-Za-z_][A-Za-z0-9_]*/,
  number: /^[0-9]+/,
  /** Lookahead marking `name` in `name = element` as a definition. */
  assignment: /^[ \t]*=/,
} as const;

/**
 * Whether a `#` at `index` in `line` opens a comment.
 *
 * True only when nothing but whitespace precedes it, which is the rule the
 * parser applies (`HASH_COMMENT` is anchored `^[ \t]*#`) and the rule
 * structurizr-java applies (`COMMENT_PATTERN` is `^\s*?(//|#)`). Mid-line,
 * a `#` is the start of a hex colour instead.
 *
 * Lives here beside the pattern rather than in the tokenizer so the two
 * halves of one rule cannot drift apart.
 */
export function hashCommentStartsHere(line: string, index: number): boolean {
  return line.slice(0, index).trim() === "";
}

/** Classify a bare word: a keyword, a style property, or neither. */
export function classifyDslWord(word: string): DslTokenClass | null {
  const lower = word.toLowerCase();
  if (DSL_KEYWORDS.has(lower)) return "keyword";
  if (DSL_PROPERTIES.has(lower)) return "property";
  return null;
}
