// CodeMirror 6 language support for the Structurizr DSL.
//
// A StreamLanguage rather than a grammar: ANTLR/tree-sitter is explicitly
// rejected in docs/roadmap.md, and a line-at-a-time tokenizer is all the
// editor needs for colour. Every keyword, property and token shape comes
// from `highlight.ts` so the SPA keeps exactly one copy of the vocabulary.

import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import type { StringStream } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { tags } from "@lezer/highlight";

import { DSL_PATTERNS, classifyDslWord, type DslTokenClass } from "./highlight";

interface DslState {
  /** Inside a block comment that opened on an earlier line. */
  inComment: boolean;
  /** After a `!directive` on this line: the rest of it is a path, not DSL. */
  inDirective: boolean;
}

/** Consume up to the end of a block comment, or to the end of the line. */
function blockComment(stream: StringStream, state: DslState): DslTokenClass {
  while (!stream.eol()) {
    if (stream.match(DSL_PATTERNS.blockCommentClose)) {
      state.inComment = false;
      return "comment";
    }
    stream.next();
  }
  return "comment";
}

function token(stream: StringStream, state: DslState): DslTokenClass | null {
  if (stream.sol()) state.inDirective = false;
  if (state.inComment) return blockComment(stream, state);
  if (stream.eatSpace()) return null;

  if (stream.match(DSL_PATTERNS.lineComment)) return "comment";
  if (stream.match(DSL_PATTERNS.blockCommentOpen)) {
    state.inComment = true;
    return blockComment(stream, state);
  }
  if (stream.match(DSL_PATTERNS.string)) return "string";
  if (stream.peek() === '"') {
    // Unterminated string: paint the rest of the line rather than leaving
    // the quote bare while someone is still typing the closing one.
    stream.skipToEnd();
    return "string";
  }
  if (stream.match(DSL_PATTERNS.color)) return "color";
  if (stream.match(DSL_PATTERNS.arrow)) return "arrow";
  if (stream.match(DSL_PATTERNS.directive)) {
    state.inDirective = true;
    return "directive";
  }

  if (stream.match(DSL_PATTERNS.word)) {
    // `!include model/oms.dsl` must not paint "model" as a keyword.
    if (state.inDirective) return null;
    const cls = classifyDslWord(stream.current());
    if (cls) return cls;
    return stream.match(DSL_PATTERNS.assignment, false) ? "def" : null;
  }
  if (stream.match(DSL_PATTERNS.number)) return "number";

  stream.next();
  return null;
}

/** The DSL as a CodeMirror language. */
export const dslLanguage = StreamLanguage.define<DslState>({
  name: "structurizr-dsl",
  startState: () => ({ inComment: false, inDirective: false }),
  token,
  copyState: (state) => ({ ...state }),
  blankLine: (state) => {
    state.inDirective = false;
  },
  languageData: {
    commentTokens: { line: "//", block: { open: "/*", close: "*/" } },
  },
  tokenTable: {
    comment: tags.comment,
    string: tags.string,
    color: tags.color,
    keyword: tags.keyword,
    property: tags.propertyName,
    def: tags.definition(tags.variableName),
    arrow: tags.operator,
    directive: tags.meta,
    number: tags.number,
  },
});

// Paint through the same `dsl-*` classes the source viewer has always used,
// so the colours stay defined once, in index.css.
const dslHighlightStyle = HighlightStyle.define([
  { tag: tags.comment, class: "dsl-comment" },
  { tag: tags.string, class: "dsl-string" },
  { tag: tags.color, class: "dsl-color" },
  { tag: tags.keyword, class: "dsl-keyword" },
  { tag: tags.propertyName, class: "dsl-property" },
  { tag: tags.definition(tags.variableName), class: "dsl-def" },
  { tag: tags.operator, class: "dsl-arrow" },
  { tag: tags.meta, class: "dsl-directive" },
  { tag: tags.number, class: "dsl-number" },
]);

export const dslHighlighting = syntaxHighlighting(dslHighlightStyle);

/** Editor chrome, matched to the metrics the source viewer used. */
export const dslEditorTheme = EditorView.theme({
  "&": {
    height: "100%",
    fontSize: "12.5px",
    backgroundColor: "var(--panel)",
    color: "var(--text)",
  },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": {
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    lineHeight: "1.55",
  },
  ".cm-content": { padding: "12px 0 48px" },
  ".cm-gutters": {
    backgroundColor: "var(--panel)",
    border: "none",
    color: "#b3bcc7",
  },
  ".cm-lineNumbers .cm-gutterElement": { padding: "0 12px 0 8px" },
  ".cm-activeLine": { backgroundColor: "rgba(0, 0, 0, 0.03)" },
  ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--muted)" },
  ".cm-flash-line": { animation: "src-focus 2.2s ease-out" },
});
