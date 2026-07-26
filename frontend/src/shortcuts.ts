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

/** Mouse gestures shown by the `?` help overlay alongside the keys. */
export const GESTURES: readonly { keys: string; action: string }[] = [
  { keys: "Drag", action: "Pan, or select in a box — whichever mode is on" },
  { keys: "Shift + drag", action: "Select in a box (either mode)" },
  { keys: "⌘ + click", action: "Add / remove one node from the selection" },
  { keys: "Middle drag", action: "Pan the diagram" },
  { keys: "Right-click edge", action: "Bend points menu for a relationship" },
  { keys: "Scroll", action: "Zoom in pan mode, pan in select mode" },
  { keys: "Pinch", action: "Zoom" },
];

/** The shortcut list shown by the `?` help overlay. */
export const SHORTCUTS: readonly { keys: string; action: string }[] = [
  { keys: "j / k", action: "Next / previous view" },
  { keys: "u", action: "Up one level (breadcrumb)" },
  { keys: "f", action: "Fit diagram to window" },
  { keys: "p", action: "Export diagram as PNG" },
  { keys: "s", action: "Export diagram as SVG" },
  { keys: "h", action: "Toggle hover emphasis" },
  { keys: "g", action: "Toggle snap to grid" },
  { keys: "v", action: "Switch pan / select mode" },
  { keys: "?", action: "Show / hide this help" },
  { keys: "Esc", action: "Close this help" },
];
