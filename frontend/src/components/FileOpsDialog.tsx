import { useEffect, useRef, useState } from "react";

/** Which operation the dialog is collecting confirmation for. */
export type FileOpKind = "new-file" | "new-folder" | "rename" | "delete";

export interface FileOpRequest {
  kind: FileOpKind;
  /** The file or folder the menu was opened on. */
  target: string;
  /** Folder the new entry goes in, for the two create operations. */
  parent: string;
  /** True when `target` is a folder. */
  isFolder: boolean;
}

interface FileOpsDialogProps {
  request: FileOpRequest;
  /** Resolve to run the operation; reject to report why it was refused. */
  onConfirm: (value: string) => Promise<void>;
  onClose: () => void;
}

function describe(request: FileOpRequest): {
  title: string;
  confirm: string;
  initial: string;
  prompt?: string;
} {
  const inFolder = request.parent ? ` in ${request.parent}/` : " in the root";
  switch (request.kind) {
    case "new-file":
      return {
        title: "New file",
        confirm: "Create",
        initial: "",
        prompt: `Name the file${inFolder}`,
      };
    case "new-folder":
      return {
        title: "New folder",
        confirm: "Create",
        initial: "",
        prompt: `Name the folder${inFolder}`,
      };
    case "rename":
      return {
        title: "Rename",
        confirm: "Rename",
        initial: request.target.split("/").pop() ?? "",
        prompt: `Rename ${request.target} to`,
      };
    case "delete":
      return { title: "Delete", confirm: "Delete", initial: "" };
  }
}

/**
 * One dialog for all four file operations: a name prompt for the three
 * that need one, a confirmation for the one that destroys something.
 *
 * The error line is the important part. Every refusal the server makes —
 * "already exists", "not a listed source file", "cannot delete the loaded
 * workspace" — is a deliberate guard, and a guard the user never sees is
 * indistinguishable from a bug.
 */
export function FileOpsDialog({
  request,
  onConfirm,
  onClose,
}: FileOpsDialogProps) {
  const { title, confirm, initial, prompt } = describe(request);
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const destructive = request.kind === "delete";
  const submit = () => {
    if (busy) return;
    const trimmed = value.trim();
    if (!destructive && !trimmed) return;
    setBusy(true);
    setError(null);
    onConfirm(trimmed)
      .then(onClose)
      .catch((err: unknown) => {
        setBusy(false);
        setError(err instanceof Error ? err.message : "The operation failed");
      });
  };

  return (
    <div className="dialog__backdrop" role="presentation">
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="dialog__title">{title}</div>
        {destructive ? (
          <p className="dialog__body">
            Delete <strong>{request.target}</strong>
            {request.isFolder ? " (folder)" : ""}? This cannot be undone from
            here — only from version control.
          </p>
        ) : (
          <>
            <label className="dialog__body" htmlFor="file-op-input">
              {prompt}
            </label>
            <input
              id="file-op-input"
              ref={inputRef}
              className="dialog__input"
              value={value}
              disabled={busy}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submit();
              }}
            />
          </>
        )}
        {error ? <div className="dialog__error">{error}</div> : null}
        <div className="dialog__actions">
          <button className="dialog__button" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className={
              "dialog__button dialog__button--primary" +
              (destructive ? " dialog__button--destructive" : "")
            }
            onClick={submit}
            disabled={busy || (!destructive && !value.trim())}
          >
            {busy ? "Working…" : confirm}
          </button>
        </div>
      </div>
    </div>
  );
}
