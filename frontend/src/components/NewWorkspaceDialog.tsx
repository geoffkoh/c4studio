import { useEffect, useState } from "react";

import { ApiError, getTemplate, listTemplates } from "../api";
import type { TemplateInfo } from "../types";

interface NewWorkspaceDialogProps {
  /** Folders already in the tree, offered as the place to put it. */
  folders: string[];
  /** Writes the rendered DSL. The caller supplies the write so this
      dialog never learns the save path — creation is a normal save. */
  onCreate: (path: string, content: string) => Promise<void>;
  onClose: () => void;
}

/** `My Workspace` -> `my-workspace.dsl`, so the filename follows the name. */
function suggestFilename(workspaceName: string): string {
  const slug = workspaceName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "workspace"}.dsl`;
}

/**
 * Create a workspace from one of the shipped starter templates.
 *
 * There is no "create workspace" endpoint behind this. The template is
 * rendered by `GET /api/templates/{name}` — so the name substitution
 * keeps the single implementation `c4 new` uses — and then written
 * through the ordinary save path, which is what gives it conflict
 * detection and the Viewer guard without restating either.
 */
export function NewWorkspaceDialog({
  folders,
  onCreate,
  onClose,
}: NewWorkspaceDialogProps) {
  const [available, setAvailable] = useState<TemplateInfo[] | null>(null);
  const [template, setTemplate] = useState("minimal");
  const [name, setName] = useState("My Workspace");
  const [folder, setFolder] = useState("");
  const [filename, setFilename] = useState("my-workspace.dsl");
  const [touchedFilename, setTouchedFilename] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTemplates()
      .then((entries) => {
        setAvailable(entries);
        if (entries.length > 0) setTemplate(entries[0].name);
      })
      .catch(() => setAvailable([]));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  // The filename follows the workspace name until the user edits it, at
  // which point it is theirs and stops moving under them.
  const changeName = (value: string) => {
    setName(value);
    if (!touchedFilename) setFilename(suggestFilename(value));
  };

  const path = folder ? `${folder}/${filename}` : filename;

  const submit = () => {
    if (busy || !filename.trim()) return;
    setBusy(true);
    setError(null);
    getTemplate(template, name.trim() || undefined)
      .then((rendered) => onCreate(path, rendered.content))
      .then(onClose)
      .catch((err: unknown) => {
        setBusy(false);
        setError(
          err instanceof ApiError && err.status === 409
            ? `${path} already exists.`
            : err instanceof Error
              ? err.message
              : "Could not create the workspace",
        );
      });
  };

  return (
    <div className="dialog__backdrop" role="presentation">
      <div
        className="dialog dialog--wide"
        role="dialog"
        aria-modal="true"
        aria-label="New workspace"
      >
        <div className="dialog__title">New workspace</div>

        <div className="dialog__field">
          <span className="dialog__label">Template</span>
          {available === null ? (
            <p className="muted">Loading templates…</p>
          ) : available.length === 0 ? (
            <p className="muted">No templates available on this server.</p>
          ) : (
            <div className="template-list">
              {available.map((entry) => (
                <label
                  key={entry.name}
                  className={
                    "template-list__item" +
                    (entry.name === template ? " template-list__item--active" : "")
                  }
                >
                  <input
                    type="radio"
                    name="template"
                    value={entry.name}
                    checked={entry.name === template}
                    onChange={() => setTemplate(entry.name)}
                  />
                  <span>
                    <strong>{entry.name}</strong>
                    <span className="template-list__summary">{entry.summary}</span>
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="dialog__field">
          <label className="dialog__label" htmlFor="ws-name">
            Workspace name
          </label>
          <input
            id="ws-name"
            className="dialog__input"
            value={name}
            disabled={busy}
            onChange={(event) => changeName(event.target.value)}
          />
        </div>

        <div className="dialog__field">
          <label className="dialog__label" htmlFor="ws-file">
            File
          </label>
          <div className="dialog__row">
            <select
              className="dialog__select"
              value={folder}
              disabled={busy}
              onChange={(event) => setFolder(event.target.value)}
            >
              <option value="">(root)</option>
              {folders.map((entry) => (
                <option key={entry} value={entry}>
                  {entry}/
                </option>
              ))}
            </select>
            <input
              id="ws-file"
              className="dialog__input"
              value={filename}
              disabled={busy}
              onChange={(event) => {
                setTouchedFilename(true);
                setFilename(event.target.value);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") submit();
              }}
            />
          </div>
        </div>

        {error ? <div className="dialog__error">{error}</div> : null}

        <div className="dialog__actions">
          <button className="dialog__button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="dialog__button dialog__button--primary"
            onClick={submit}
            disabled={busy || !filename.trim() || !available?.length}
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
