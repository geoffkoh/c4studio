// Shared helpers for keyboard shortcut handling.

/** Whether a key event originated in a text-entry element and must be ignored. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  );
}

/** The shortcut list shown by the `?` help overlay. */
export const SHORTCUTS: readonly { keys: string; action: string }[] = [
  { keys: "j / k", action: "Next / previous view" },
  { keys: "u", action: "Up one level (breadcrumb)" },
  { keys: "f", action: "Fit diagram to window" },
  { keys: "p", action: "Export diagram as PNG" },
  { keys: "s", action: "Export diagram as SVG" },
  { keys: "h", action: "Toggle hover emphasis" },
  { keys: "g", action: "Toggle snap to grid" },
  { keys: "?", action: "Show / hide this help" },
  { keys: "Esc", action: "Close this help" },
];
