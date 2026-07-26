import { useEffect, useRef } from "react";

/** One entry in the edge context menu. */
export interface MenuAction {
  label: string;
  onSelect: () => void;
  /** Destructive entries are tinted and separated from the rest. */
  destructive?: boolean;
}

export interface EdgeMenuState {
  /** Screen coordinates of the click that opened the menu. */
  x: number;
  y: number;
  edgeId: string;
  /** Set when the click landed on a bend point rather than the line. */
  waypointIndex?: number;
  /** Flow coordinates of the click, where a new bend point would go. */
  flowX: number;
  flowY: number;
}

interface EdgeContextMenuProps {
  state: EdgeMenuState;
  actions: MenuAction[];
  onClose: () => void;
}

/**
 * Right-click menu for a relationship. Rendered in screen coordinates
 * outside the flow viewport so it neither pans nor scales with the
 * diagram, and dismissed by Escape, scroll, or any click elsewhere.
 */
export function EdgeContextMenu({
  state,
  actions,
  onClose,
}: EdgeContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    // Capture phase: close before the click reaches the canvas underneath.
    window.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("wheel", onClose, { passive: true });
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("wheel", onClose);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="edge-menu"
      style={{ left: state.x, top: state.y }}
      role="menu"
    >
      {actions.map((action) => (
        <button
          key={action.label}
          role="menuitem"
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
