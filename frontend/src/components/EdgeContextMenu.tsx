import { ContextMenu, type MenuAction } from "./ContextMenu";

export type { MenuAction };

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
 * Right-click menu for a relationship.
 *
 * The menu itself is {@link ContextMenu}; what lives here is
 * `EdgeMenuState`, which carries the flow coordinates a bend point needs
 * and which nothing outside the diagram has any use for.
 */
export function EdgeContextMenu({
  state,
  actions,
  onClose,
}: EdgeContextMenuProps) {
  return (
    <ContextMenu x={state.x} y={state.y} actions={actions} onClose={onClose} />
  );
}
