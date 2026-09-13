import { useEffect, useRef, type ReactNode } from "react";

/** One entry in a context menu. */
export interface MenuAction {
  label: string;
  onSelect: () => void;
  /** Destructive entries are tinted and separated from the rest. */
  destructive?: boolean;
  disabled?: boolean;
}

interface ContextMenuProps {
  /** Screen coordinates of the click that opened the menu. */
  x: number;
  y: number;
  actions: MenuAction[];
  onClose: () => void;
  /** Optional heading, e.g. the path the menu acts on. */
  title?: ReactNode;
}

/**
 * A right-click menu in screen coordinates, dismissed by Escape, scroll,
 * or a pointer down anywhere outside it.
 *
 * Extracted from the relationship menu when the file tree needed the same
 * thing. The dismissal is the part worth having once: it listens on the
 * *capture* phase so the menu closes before the click reaches whatever is
 * underneath, which is what stops a dismissing click from also selecting
 * a node or a file.
 */
export function ContextMenu({
  x,
  y,
  actions,
  onClose,
  title,
}: ContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("wheel", onClose, { passive: true });
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("wheel", onClose);
    };
  }, [onClose]);

  return (
    <div ref={ref} className="edge-menu" style={{ left: x, top: y }} role="menu">
      {title ? <div className="edge-menu__title">{title}</div> : null}
      {actions.map((action) => (
        <button
          key={action.label}
          role="menuitem"
          disabled={action.disabled}
          className={
            "edge-menu__item" +
            (action.destructive ? " edge-menu__item--destructive" : "")
          }
          onClick={() => {
            action.onSelect();
            onClose();
          }}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}
