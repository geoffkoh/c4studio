// Completion for the Structurizr DSL editor.
//
// There is no parse tree to ask — `dslLanguage` is a StreamLanguage, and a
// real grammar stays rejected (docs/roadmap.md). So context comes from a
// cheap look at the line the cursor is on, which is enough to tell the four
// places worth completing apart from ordinary keyword typing.
//
// The vocabulary comes from `highlight.ts` and the identifiers from the
// loaded workspace, so nothing here restates either.

import type { Completion, CompletionContext, CompletionResult } from "@codemirror/autocomplete";

import { DSL_KEYWORDS, DSL_PROPERTIES } from "./highlight";
import type { ViewInfo, Workspace } from "./types";

/** What the loaded workspace contributes: identifiers and view keys. */
export interface DslCompletionModel {
  /** Element identifiers — the DSL alias, when the element declared one. */
  elements: Completion[];
  /** View keys, for the `filtered <baseKey> …` form. */
  viewKeys: Completion[];
}

/** Expression starters accepted by `include` / `exclude` inside a view. */
const EXPRESSIONS: Completion[] = [
  { label: "*", type: "constant", detail: "everything in scope" },
  { label: "element.tag==", type: "property", detail: "by tag" },
  { label: "element.type==", type: "property", detail: "by type" },
  { label: "element.parent==", type: "property", detail: "by parent" },
  { label: "relationship.tag==", type: "property", detail: "relationships by tag" },
];

/** What a completion keeps matching as more is typed. */
const VALID_FOR = /^[A-Za-z0-9_.*-]*$/;

/** Directives whose first argument is an element identifier. Not a
    vocabulary for completing directive *names* — those stay unoffered, so
    there is nothing here to keep in step with docs/dsl-support.md. */
const IDENTIFIER_DIRECTIVES = new Set([
  "!element",
  "!elements",
  "!relationship",
  "!relationships",
]);

const KEYWORDS: Completion[] = [
  ...[...DSL_KEYWORDS].map(
    (label): Completion => ({ label, type: "keyword" }),
  ),
  ...[...DSL_PROPERTIES].map(
    (label): Completion => ({ label, type: "property" }),
  ),
];

/**
 * Flatten the workspace into completions.
 *
 * `dsl.py` sets `elem_id = alias or slug`, so an element's id **is** the
 * identifier you type in the DSL whenever one was declared — which is why
 * this needs no endpoint of its own.
 */
export function completionModel(
  workspace: Workspace | null,
  views: ViewInfo[],
): DslCompletionModel {
  const elements: Completion[] = [];
  const add = (id: string, name: string, kind: string, parent?: string) => {
    if (!id) return;
    elements.push({
      label: id,
      type: "variable",
      detail: kind,
      info: parent ? `${name} — in ${parent}` : name,
    });
  };

  for (const person of workspace?.model.people ?? []) {
    add(person.id, person.name, "person");
  }
  for (const system of workspace?.model.software_systems ?? []) {
    add(system.id, system.name, "software system");
    for (const container of system.containers ?? []) {
      add(container.id, container.name, "container", system.name);
      for (const component of container.components ?? []) {
        add(component.id, component.name, "component", container.name);
      }
    }
  }

  return {
    elements,
    viewKeys: views.map((view) => ({
      label: view.key,
      type: "enum",
      detail: view.type,
      info: view.title,
    })),
  };
}

/** The word being typed, and whether completion was explicitly asked for. */
function currentWord(context: CompletionContext) {
  // `*` and `.` are part of an include expression rather than separators.
  return context.matchBefore(/[A-Za-z0-9_.*-]*/);
}

/**
 * Build the completion source for a workspace.
 *
 * Returned as a factory rather than a constant so the editor can be
 * reconfigured when the workspace reloads, without rebuilding the view.
 */
export function dslCompletionSource(model: DslCompletionModel) {
  return (context: CompletionContext): CompletionResult | null => {
    const word = currentWord(context);
    if (!word) return null;
    if (word.from === word.to && !context.explicit) return null;

    const line = context.state.doc.lineAt(context.pos);
    const before = line.text.slice(0, context.pos - line.from);

    // Never complete inside a string or a comment: quoted text is prose
    // (names, descriptions, technologies), not vocabulary.
    const quotes = (before.match(/"/g) ?? []).length;
    if (quotes % 2 === 1) return null;
    if (/(^|\s)(\/\/|#)/.test(before)) return null;
    // Mid-directive. `!` is outside the word pattern, so completing here
    // would offer the whole keyword list against `!inc`. The directive
    // names are not offered at all: they would be a second vocabulary to
    // keep in step with docs/dsl-support.md, which Principle 4 exists to
    // avoid.
    if (/(^|\s)![A-Za-z]*$/.test(before)) return null;

    // The tokens already on this line, ignoring the one being typed.
    const tokens = before.trim().split(/\s+/).filter(Boolean);
    const typing = word.from < context.pos;
    const settled = typing ? tokens.slice(0, -1) : tokens;
    const head = (settled[0] ?? "").toLowerCase();

    // A directive line's argument is not DSL vocabulary — the highlighter
    // blanks keyword colouring there for the same reason. The four that
    // take an identifier are the exception, and are worth completing.
    if (head.startsWith("!")) {
      return IDENTIFIER_DIRECTIVES.has(head) && model.elements.length > 0
        ? { from: word.from, options: model.elements, validFor: VALID_FOR }
        : null;
    }

    let options: Completion[];
    if (/->\s*[A-Za-z0-9_.-]*$/.test(before)) {
      // A relationship destination.
      options = model.elements;
    } else if (head === "filtered") {
      // `filtered <baseKey> <include|exclude> <tags>` — only the base key
      // is completable; the tags after it are the user's own vocabulary.
      options =
        settled.length === 1
          ? model.viewKeys
          : settled.length === 2
            ? [
                { label: "include", type: "keyword" },
                { label: "exclude", type: "keyword" },
              ]
            : [];
    } else if (head === "include" || head === "exclude") {
      // Inside a view: element identifiers and expressions. `!include` is
      // a directive and never reaches here — `!` is not in the word
      // pattern, so `head` would be "!include".
      options = [...model.elements, ...EXPRESSIONS];
    } else if (settled.length === 0) {
      // Start of a statement: a keyword, or the source of a relationship.
      options = [...KEYWORDS, ...model.elements];
    } else {
      options = KEYWORDS;
    }

    if (options.length === 0) return null;
    return { from: word.from, options, validFor: VALID_FOR };
  };
}
