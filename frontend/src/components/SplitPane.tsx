import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";

/** Neither half may be squeezed below this fraction of the container. */
const MIN_RATIO = 0.2;
const MAX_RATIO = 0.8;

/** ...nor below this many px, which a ratio alone cannot express.

    The ratio was written for a browser window. In the VS Code preview the
    whole SPA lives in a panel around 500px wide, where 0.2 is a 100px pane
    — narrower than the editor's own gutter. Below twice this (plus the
    divider) there is no honest split to draw, so one pane takes the width
    and the other becomes the rail it already knows how to be. The VS Code
    preview no longer loads the SPA (PP-170), so this is now a narrow
    browser window's path. */
const MIN_PANE = 320;

function clamp(ratio: number, width = 0): number {
  const bounded = Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio));
  if (width < MIN_PANE * 2) return bounded;
  // Tighten the ratio bounds so neither pane falls under MIN_PANE.
  const floor = MIN_PANE / width;
  return Math.min(1 - floor, Math.max(floor, bounded));
}

/** Whether the container can hold two panes at all. */
function fits(width: number): boolean {
  return width === 0 || width >= MIN_PANE * 2 + DIVIDER_PX;
}

const DIVIDER_PX = 6;

function storedRatio(key: string, fallback: number): number {
  let raw = Number.NaN;
  try {
    raw = Number(window.localStorage.getItem(key) ?? Number.NaN);
  } catch {
    // Private windows and blocked site data throw rather than return null.
  }
  return Number.isFinite(raw) && raw >= MIN_RATIO && raw <= MAX_RATIO
    ? raw
    : fallback;
}

interface SplitPaneProps {
  left: ReactNode;
  right: ReactNode;
  /** Lower-case names of the panes, for the rails and the collapse control. */
  leftLabel: string;
  rightLabel: string;
  /** Whether the right pane is shown. Owned by the caller, because
      something outside the split — "Show definition" — opens it, and an
      open request that only the split knew about could not reach it. */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Marks the right pane's rail, e.g. unsaved work behind it. */
  rightBadge?: string;
  /** Title for the right pane's rail, which says how else to open it. */
  rightTitle?: string;
  /** Where the left pane's share of the width is remembered. */
  ratioKey: string;
  defaultRatio: number;
}

/**
 * Two panes side by side with a draggable divider, the right one
 * collapsible to a rail.
 *
 * Deliberately knows nothing about either child: the editor and the
 * diagram are passed in as nodes, so neither learns about the other and
 * `GraphPane` stays reusable outside this page.
 *
 * The left pane keeps one position in the tree whether or not the right
 * one is open, so opening the editor beside the diagram does not remount
 * it and lose the viewport, the selection and the fetched graph (PP-214).
 *
 * At a width with room for one pane, `open` decides which: the right one
 * with the left as a rail, or the reverse. The drag listens on `window`,
 * not on the handle, so moving fast — or off the edge of the window —
 * does not drop the gesture. The ratio is per-user UI state in
 * `localStorage`, where the diagram's own toggles already live.
 */
export function SplitPane({
  left,
  right,
  leftLabel,
  rightLabel,
  open,
  onOpenChange,
  rightBadge,
  rightTitle,
  ratioKey,
  defaultRatio,
}: SplitPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(() => storedRatio(ratioKey, defaultRatio));
  const [dragging, setDragging] = useState(false);
  // The container, not the viewport: the sidebar takes width from it
  // without the window changing, which a media query would miss.
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const measured = entries[0]?.contentRect.width;
      if (typeof measured === "number") setWidth(measured);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(ratioKey, String(ratio));
    } catch {
      // Nothing to do: the ratio simply will not persist.
    }
  }, [ratioKey, ratio]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (event: MouseEvent) => {
      const box = containerRef.current?.getBoundingClientRect();
      if (!box || box.width === 0) return;
      setRatio(clamp((event.clientX - box.left) / box.width, box.width));
    };
    const onUp = () => setDragging(false);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    // While the pointer is over the diagram it must not select text, nor
    // become an I-beam over the editor it just left.
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
  }, [dragging]);

  /** Resize from the keyboard, so the divider is not a mouse-only control. */
  const onKeyDown = useCallback((event: ReactKeyboardEvent) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const step = event.key === "ArrowLeft" ? -0.02 : 0.02;
    setRatio((value) => clamp(value + step, width));
    event.preventDefault();
  }, [width]);

  /** Collapse without the mousedown also starting a drag. */
  const onCollapse = useCallback(
    (event: ReactMouseEvent) => {
      event.stopPropagation();
      onOpenChange(false);
    },
    [onOpenChange],
  );

  // The user's choice is honoured only when it is drawable. It is never
  // rewritten, so widening the panel restores the split they asked for.
  const roomy = fits(width);
  const showBoth = open && roomy;
  const rightOnly = open && !roomy;
  const effectiveRatio = clamp(ratio, width);

  return (
    <div className="split" ref={containerRef}>
      {/* Narrow: one pane at a time, with the other as a rail to swap to.
          The rail is the same affordance as the collapsed pane, so there
          is one thing to learn rather than two. */}
      {rightOnly ? (
        <button
          className="rail rail--left"
          onClick={() => onOpenChange(false)}
          title={`Back to the ${leftLabel}`}
        >
          <span className="rail__label">{leftLabel}</span>
        </button>
      ) : (
        <div
          className="split__pane"
          style={{ flex: showBoth ? `0 0 ${effectiveRatio * 100}%` : "1 1 0" }}
        >
          {left}
        </div>
      )}

      {showBoth ? (
        <>
          <div
            className={
              "split__divider" + (dragging ? " split__divider--active" : "")
            }
            role="separator"
            aria-orientation="vertical"
            aria-valuenow={Math.round(effectiveRatio * 100)}
            tabIndex={0}
            onMouseDown={() => setDragging(true)}
            onDoubleClick={() => setRatio(0.5)}
            onKeyDown={onKeyDown}
            title="Drag to resize, double-click to even up"
          >
            <button
              className="split__grip"
              onMouseDown={(event) => event.stopPropagation()}
              onClick={onCollapse}
              title={`Hide the ${rightLabel}`}
              aria-label={`Hide the ${rightLabel}`}
            >
              ›
            </button>
          </div>
          <div className="split__pane split__pane--right">{right}</div>
        </>
      ) : rightOnly ? (
        <div className="split__pane split__pane--right">{right}</div>
      ) : (
        <button
          className="rail rail--right"
          onClick={() => onOpenChange(true)}
          aria-expanded={false}
          title={
            (rightTitle ?? `Show the ${rightLabel}`) +
            (roomy ? "" : " — only one fits at this width")
          }
        >
          <span className="rail__label">
            {rightLabel}
            {rightBadge ? (
              <span className="rail__badge" aria-label={rightBadge} title={rightBadge}>
                {" "}●
              </span>
            ) : null}
          </span>
        </button>
      )}
    </div>
  );
}
