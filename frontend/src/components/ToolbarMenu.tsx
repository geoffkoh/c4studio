import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

interface ToolbarMenuProps {
  /** The button's text; the popover is named after it too. */
  label: string;
  title: string;
  /** Close after any button inside is pressed — for one-shot actions
      like an export, not for toggles a user may set several of. */
  closeOnClick?: boolean;
  children: ReactNode;
}

/**
 * A toolbar button that opens a small group of controls under it
 * (PP-206): what keeps the toolbar one row long as it gains options.
 * Outside a click or on Escape it closes, as the Layouts menu does.
 *
 * Only controls that are set once in a while belong here — whatever is
 * reached for while arranging a view stays on the toolbar itself.
 */
export function ToolbarMenu({ label, title, closeOnClick = false, children }: ToolbarMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown, true);
    };
  }, [open, close]);

  return (
    <div className="toolbar-menu" ref={ref}>
      <button
        className={"edge-style__option" + (open ? " edge-style__option--active" : "")}
        title={title}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
      >
        {label} ▾
      </button>
      {open ? (
        <div
          id={id}
          className="toolbar-menu__popover"
          role="group"
          aria-label={label}
          onClick={(event) => {
            if (closeOnClick && (event.target as HTMLElement).closest("button")) close();
          }}
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
