import { useCallback, useEffect, useRef } from "react";
import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
} from "@codemirror/autocomplete";
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
} from "@codemirror/commands";
import { bracketMatching } from "@codemirror/language";
import { lintGutter, setDiagnostics, type Diagnostic } from "@codemirror/lint";
import { Compartment, EditorState, StateEffect, StateField } from "@codemirror/state";
import {
  Decoration,
  EditorView,
  type DecorationSet,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
  rectangularSelection,
} from "@codemirror/view";

import { dslCompletionSource, type DslCompletionModel } from "../dslComplete";
import { dslEditorTheme, dslHighlighting, dslLanguage } from "../dslLanguage";
import type { DslDiagnostic } from "../types";

/** A line to scroll to and flash, e.g. an element's definition. */
export interface EditorFlash {
  line: number;
  /** Changes on every request so flashing the same line twice re-runs. */
  nonce: number;
}

interface DslEditorProps {
  /** Buffer identity. Changing it swaps the document and resets undo. */
  docKey: string;
  value: string;
  readOnly: boolean;
  /** Diagnostics for *this* file, already filtered by the caller. */
  diagnostics: DslDiagnostic[];
  /** Identifiers and view keys the loaded workspace offers to completion. */
  completions: DslCompletionModel;
  flash: EditorFlash | null;
  onChange: (text: string) => void;
  onSave: () => void;
}

/** Highlight one line until a later flash effect clears it. */
const setFlash = StateEffect.define<number | null>();

const flashField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, transaction) {
    value = value.map(transaction.changes);
    for (const effect of transaction.effects) {
      if (!effect.is(setFlash)) continue;
      value =
        effect.value === null
          ? Decoration.none
          : Decoration.set([
              Decoration.line({ class: "cm-flash-line" }).range(effect.value),
            ]);
    }
    return value;
  },
  provide: (field) => EditorView.decorations.from(field),
});

/** Translate a backend diagnostic into a CodeMirror one.

    Backend lines and columns are 1-based with `endColumn` exclusive, and
    either column may be null for a whole-line problem. Positions are
    clamped: the buffer may have been edited since the check was sent. */
function toCmDiagnostic(
  state: EditorState,
  diagnostic: DslDiagnostic,
): Diagnostic | null {
  if (diagnostic.line === null) return null;
  const lineNumber = Math.min(Math.max(diagnostic.line, 1), state.doc.lines);
  const line = state.doc.line(lineNumber);
  const from =
    diagnostic.column === null
      ? line.from
      : Math.min(line.from + diagnostic.column - 1, line.to);
  let to =
    diagnostic.endColumn === null
      ? line.to
      : Math.min(line.from + diagnostic.endColumn - 1, line.to);
  if (to <= from) to = Math.min(from + 1, line.to);
  return {
    from,
    to,
    severity: diagnostic.severity,
    source: diagnostic.code,
    message: diagnostic.message,
  };
}

/**
 * CodeMirror 6 editing surface for Structurizr DSL.
 *
 * Owns nothing but the text: the parent holds the buffer, decides when to
 * save and runs `/api/check`, then hands the results back down. That keeps
 * the editor a plain controlled component and leaves the save and lint
 * policy in one place.
 */
export function DslEditor({
  docKey,
  value,
  readOnly,
  diagnostics,
  completions,
  flash,
  onChange,
  onSave,
}: DslEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const readOnlyCompartment = useRef(new Compartment());
  const completionCompartment = useRef(new Compartment());
  const flashTimer = useRef<number | null>(null);
  // Props reach the (long-lived) CodeMirror extensions through refs, so a
  // new closure on every render does not mean rebuilding the editor.
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const readOnlyRef = useRef(readOnly);
  const valueRef = useRef(value);
  const docKeyRef = useRef(docKey);
  const completionsRef = useRef(completions);
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;
  readOnlyRef.current = readOnly;
  valueRef.current = value;
  completionsRef.current = completions;

  const buildState = useCallback(
    (doc: string) =>
      EditorState.create({
        doc,
        extensions: [
          lineNumbers(),
          highlightActiveLine(),
          highlightActiveLineGutter(),
          history(),
          drawSelection(),
          rectangularSelection(),
          bracketMatching(),
          closeBrackets(),
          lintGutter(),
          flashField,
          completionCompartment.current.of(
            autocompletion({
              override: [dslCompletionSource(completionsRef.current)],
              // The DSL is short lines of identifiers; an icon column for
              // every entry is more chrome than the list is worth.
              icons: false,
            }),
          ),
          EditorState.allowMultipleSelections.of(true),
          EditorView.lineWrapping,
          keymap.of([
            {
              key: "Mod-s",
              preventDefault: true,
              run: () => {
                onSaveRef.current();
                return true;
              },
            },
            // Before defaultKeymap, so Enter and Escape reach the open
            // completion list rather than inserting a newline.
            ...completionKeymap,
            ...closeBracketsKeymap,
            ...defaultKeymap,
            ...historyKeymap,
            indentWithTab,
          ]),
          dslLanguage,
          dslHighlighting,
          dslEditorTheme,
          readOnlyCompartment.current.of(
            EditorState.readOnly.of(readOnlyRef.current),
          ),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              onChangeRef.current(update.state.doc.toString());
            }
          }),
        ],
      }),
    [],
  );

  // Create the view once; everything after this is a dispatch or a setState.
  useEffect(() => {
    if (!hostRef.current) return;
    const view = new EditorView({
      parent: hostRef.current,
      state: buildState(valueRef.current),
    });
    viewRef.current = view;
    return () => {
      if (flashTimer.current !== null) window.clearTimeout(flashTimer.current);
      view.destroy();
      viewRef.current = null;
    };
  }, [buildState]);

  // Adopt text that changed outside the editor. A new `docKey` is a
  // different file, so it gets a fresh state — undo must not walk backwards
  // into another file's content. Same file, new text (a live reload, a
  // resolved conflict) is a plain edit, which keeps the cursor useful.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    if (docKey !== docKeyRef.current) {
      docKeyRef.current = docKey;
      view.setState(buildState(value));
      return;
    }
    if (value !== view.state.doc.toString()) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value },
        scrollIntoView: false,
      });
    }
  }, [value, docKey, buildState]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: readOnlyCompartment.current.reconfigure(
        EditorState.readOnly.of(readOnly),
      ),
    });
  }, [readOnly]);

  // A reload can rename, add or drop elements, so the identifier list is
  // swapped rather than captured once. A compartment keeps that a
  // reconfigure instead of a rebuild — the document and undo survive.
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: completionCompartment.current.reconfigure(
        autocompletion({
          override: [dslCompletionSource(completions)],
          icons: false,
        }),
      ),
    });
  }, [completions]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const mapped = diagnostics
      .map((diagnostic) => toCmDiagnostic(view.state, diagnostic))
      .filter((diagnostic): diagnostic is Diagnostic => diagnostic !== null)
      .sort((a, b) => a.from - b.from);
    view.dispatch(setDiagnostics(view.state, mapped));
  }, [diagnostics, docKey]);

  // Scroll a definition into view and flash it, the way the read-only
  // source viewer did when the element tree asked for a definition.
  useEffect(() => {
    const view = viewRef.current;
    if (!view || !flash) return;
    const lineNumber = Math.min(Math.max(flash.line, 1), view.state.doc.lines);
    const line = view.state.doc.line(lineNumber);
    view.dispatch({
      selection: { anchor: line.from },
      effects: [
        setFlash.of(line.from),
        EditorView.scrollIntoView(line.from, { y: "center" }),
      ],
    });
    if (flashTimer.current !== null) window.clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => {
      viewRef.current?.dispatch({ effects: setFlash.of(null) });
      flashTimer.current = null;
    }, 2200);
  }, [flash]);

  return <div className="editor__surface" ref={hostRef} />;
}
