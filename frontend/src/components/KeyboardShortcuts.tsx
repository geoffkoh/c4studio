import { useEffect } from "react";
import { useReactFlow } from "reactflow";

import { exportDiagram } from "@pystructurizr/diagram-core";
import { isTypingTarget } from "../shortcuts";

interface KeyboardShortcutsProps {
  viewKey: string;
  /** Toggles the hover-emphasis feature (the toolbar's Hover button). */
  onHoverToggle: () => void;
  /** Toggles snap-to-grid dragging (the toolbar's Snap button). */
  onSnapToggle: () => void;
  /** Flips between pan and select mode (the toolbar's Mouse buttons). */
  onInteractionToggle: () => void;
}

/**
 * Graph-scoped keyboard shortcuts: `f` fits the diagram to the window,
 * `p`/`s` export PNG/SVG, `h` toggles hover emphasis, `g` toggles snap
 * to grid, `v` flips between pan and select mode. Renders nothing;
 * must sit inside the ReactFlow component for `useReactFlow`. App-level
 * shortcuts (view navigation, help overlay) live in App.tsx.
 */
export function KeyboardShortcuts({
  viewKey,
  onHoverToggle,
  onSnapToggle,
  onInteractionToggle,
}: KeyboardShortcutsProps) {
  const { fitView, getNodes } = useReactFlow();

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      switch (event.key) {
        case "f":
          fitView({ duration: 250, padding: 0.15 });
          break;
        case "p":
          void exportDiagram(getNodes(), viewKey, "png");
          break;
        case "s":
          void exportDiagram(getNodes(), viewKey, "svg");
          break;
        case "h":
          onHoverToggle();
          break;
        case "g":
          onSnapToggle();
          break;
        case "v":
          onInteractionToggle();
          break;
        default:
          return;
      }
      event.preventDefault();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    fitView,
    getNodes,
    viewKey,
    onHoverToggle,
    onSnapToggle,
    onInteractionToggle,
  ]);

  return null;
}
