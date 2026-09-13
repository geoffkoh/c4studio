import { useState } from "react";

import { ApiError, askAssistant } from "../api";
import { collapseUnchanged, diffLines, diffStats } from "../lineDiff";
import type { AssistantResult } from "../types";

interface AssistantPanelProps {
  /** Root-relative path of the file the assistant would rewrite. */
  path: string;
  /** The buffer as it stands, saved or not. */
  content: string;
  /** Replaces the buffer with the proposal. An ordinary edit. */
  onApply: (content: string) => void;
  onClose: () => void;
}

/**
 * Ask for a change, review it as a diff, apply or reject it.
 *
 * Nothing AI-specific touches the editor: applying is
 * `onApply(proposal.content)`, which is the same thing typing does. That is
 * Principle 1 paying off — the assistant is one more producer of text, so
 * it needs no special path through the buffer, the save, or the reload.
 *
 * The panel names the files that were sent, from the reply's `filesSent`
 * rather than a sentence written here, because a disclosure that is
 * maintained by hand is one that eventually stops being true.
 */
export function AssistantPanel({
  path,
  content,
  onApply,
  onClose,
}: AssistantPanelProps) {
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [proposal, setProposal] = useState<AssistantResult | null>(null);

  const submit = () => {
    if (busy || !instruction.trim()) return;
    setBusy(true);
    setError(null);
    setProposal(null);
    askAssistant(instruction.trim(), path, content)
      .then(setProposal)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "The request failed"),
      )
      .finally(() => setBusy(false));
  };

  const lines = proposal ? diffLines(content, proposal.content) : [];
  const stats = diffStats(lines);
  const rows = collapseUnchanged(lines, 3);
  const unchanged = proposal !== null && stats.added === 0 && stats.removed === 0;

  return (
    <div className="assistant">
      <div className="assistant__bar">
        <strong className="assistant__title">Assistant</strong>
        <span className="assistant__note" title="This is the only feature that uses the network">
          sends your workspace to an external API
        </span>
        <span className="editor__spacer" />
        <button className="assistant__close" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      <div className="assistant__ask">
        <input
          className="dialog__input"
          value={instruction}
          disabled={busy}
          placeholder={`Change ${path}…`}
          aria-label="What should the assistant change?"
          onChange={(event) => setInstruction(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") submit();
          }}
        />
        <button
          className="dialog__button dialog__button--primary"
          onClick={submit}
          disabled={busy || !instruction.trim()}
        >
          {busy ? "Asking…" : "Ask"}
        </button>
      </div>

      {error ? <div className="dialog__error">{error}</div> : null}

      {proposal?.refused ? (
        <div className="dialog__error">
          The assistant declined this request.
          {proposal.refusalReason ? ` ${proposal.refusalReason}` : ""}
        </div>
      ) : null}

      {proposal && !proposal.refused ? (
        <>
          <div className="assistant__summary">
            <span className="assistant__added">+{stats.added}</span>
            <span className="assistant__removed">−{stats.removed}</span>
            <span className="assistant__sent">
              sent {proposal.filesSent.length}{" "}
              {proposal.filesSent.length === 1 ? "file" : "files"}:{" "}
              {proposal.filesSent.join(", ")}
            </span>
          </div>

          {unchanged ? (
            <p className="muted assistant__unchanged">
              It returned the file unchanged — which it is told to do rather
              than guess.
            </p>
          ) : (
            <div className="assistant__diff">
              {rows.map((row, index) =>
                row.kind === "gap" ? (
                  <div key={index} className="assistant__gap">
                    ⋯ {row.hidden} unchanged{" "}
                    {row.hidden === 1 ? "line" : "lines"}
                  </div>
                ) : (
                  <div key={index} className={`assistant__line assistant__line--${row.kind}`}>
                    <span className="assistant__gutter">{row.before ?? ""}</span>
                    <span className="assistant__gutter">{row.after ?? ""}</span>
                    <span className="assistant__mark">
                      {row.kind === "added" ? "+" : row.kind === "removed" ? "−" : " "}
                    </span>
                    <span className="assistant__text">{row.text || " "}</span>
                  </div>
                ),
              )}
            </div>
          )}

          <div className="assistant__actions">
            <span className="assistant__model">{proposal.model}</span>
            <span className="editor__spacer" />
            <button className="dialog__button" onClick={() => setProposal(null)}>
              Reject
            </button>
            <button
              className="dialog__button dialog__button--primary"
              disabled={unchanged}
              onClick={() => {
                onApply(proposal.content);
                setProposal(null);
              }}
            >
              Apply to buffer
            </button>
          </div>
          <p className="muted assistant__footnote">
            Applying only changes the editor. Nothing is written until you
            save.
          </p>
        </>
      ) : null}
    </div>
  );
}
