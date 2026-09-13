import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";

const RATIO_STORAGE_KEY = "c4studio.splitRatio";
const OPEN_STORAGE_KEY = "c4studio.splitOpen";

/** Neither half may be squeezed below this fraction of the container. */
const MIN_RATIO = 0.2;
const MAX_RATIO = 0.8;

/** ...nor below this many px, which a ratio alone cannot express.

    The ratio was written for a browser window. In the VS Code preview the
    whole SPA lives in a panel around 500px wide, where 0.2 is a 100px pane
    — narrower than the editor's own gutter. Below twice this (plus the
    divider) there is no honest split to draw, so one pane takes the width
    and the other becomes the rail it already knows how to be. */
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

function storedRatio(): number {
  const raw = Number(window.localStorage.getItem(RATIO_STORAGE_KEY));
  return Number.isFinite(raw) && raw >= MIN_RATIO && raw <= MAX_RATIO ? raw : 0.5;
}

/** Open unless explicitly collapsed: side by side is the point of the page. */
function storedOpen(): boolean {
  return window.localStorage.getItem(OPEN_STORAGE_KEY) !== "closed";
}

interface SplitPaneProps {
  left: ReactNode;
  right: ReactNode;
  /** Lower-case name of the right pane, for the collapse control. */
  rightLabel: string;
}

/**
 * Two panes side by side with a draggable divider, the right one
 * collapsible.
 *
 * Deliberately knows nothing about either child: the editor and the
 * diagram are passed in as nodes, so neither learns about the other and
 * `GraphPane` stays reusable outside this page.
 *
 * The drag listens on `window`, not on the handle, so moving fast — or off
 * the edge of the window — does not drop the gesture. Ratio and collapsed
 * state are per-user UI state in `localStorage`, where the diagram's own
 * toggles already live.
 */
export function SplitPane({ left, right, rightLabel }: SplitPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [ratio, setRatio] = useState(storedRatio);
  const [open, setOpen] = useState(storedOpen);
  const [dragging, setDragging] = useState(false);
  // The container, not the viewport. The VS Code panel is dragged
  // independently of the window, so a media query would miss it entirely.
  const [width, setWidth] = useState(0);
  // Which pane has the width when there is only room for one. Not
  // persisted: it is a momentary answer to "which am I looking at now",
  // not a preference, and it must not survive back to a wide window.
  const [narrowPane, setNarrowPane] = useState<"left" | "right">("left");

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
    window.localStorage.setItem(RATIO_STORAGE_KEY, String(ratio));
  }, [ratio]);

  useEffect(() => {
    window.localStorage.setItem(OPEN_STORAGE_KEY, open ? "open" : "closed");
  }, [open]);

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
  }, []);

  /** Collapse without the mousedown also starting a drag. */
  const onCollapse = useCallback((event: ReactMouseEvent) => {
    event.stopPropagation();
    setOpen(false);
  }, []);

  // The user's choice is honoured only when it is drawable. It is never
  // rewritten, so widening the panel restores the split they asked for.
  const roomy = fits(width);
  const showBoth = open && roomy;
  const effectiveRatio = clamp(ratio, width);

  return (
    <div className="split" ref={containerRef}>
      {/* Narrow: one pane at a time, with the other as a rail to swap to.
          The rail is the same affordance as the collapsed diagram, so
          there is one thing to learn rather than two. */}
      {!roomy && narrowPane === "right" ? (
        <button
          className="rail rail--left"
          onClick={() => setNarrowPane("left")}
          title="Back to the editor"
        >
          <span className="rail__label">editor</span>
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
      ) : !roomy && narrowPane === "right" ? (
        <div className="split__pane split__pane--right">{right}</div>
      ) : (
        <button
          className="rail rail--right"
          onClick={() => (roomy ? setOpen(true) : setNarrowPane("right"))}
          title={
            roomy
              ? `Show the ${rightLabel}`
              : `Show the ${rightLabel} — only one fits at this width`
          }
        >
          <span className="rail__label">{rightLabel}</span>
        </button>
      )}
    </div>
  );
}
