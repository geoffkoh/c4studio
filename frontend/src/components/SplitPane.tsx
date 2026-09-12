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

function clamp(ratio: number): number {
  return Math.min(MAX_RATIO, Math.max(MIN_RATIO, ratio));
}

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
      setRatio(clamp((event.clientX - box.left) / box.width));
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
    setRatio((value) => clamp(value + step));
    event.preventDefault();
  }, []);

  /** Collapse without the mousedown also starting a drag. */
  const onCollapse = useCallback((event: ReactMouseEvent) => {
    event.stopPropagation();
    setOpen(false);
  }, []);

  return (
    <div className="split" ref={containerRef}>
      <div
        className="split__pane"
        style={{ flex: open ? `0 0 ${ratio * 100}%` : "1 1 0" }}
      >
        {left}
      </div>
      {open ? (
        <>
          <div
            className={
              "split__divider" + (dragging ? " split__divider--active" : "")
            }
            role="separator"
            aria-orientation="vertical"
            aria-valuenow={Math.round(ratio * 100)}
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
      ) : (
        <button
          className="split__rail"
          onClick={() => setOpen(true)}
          title={`Show the ${rightLabel}`}
        >
          <span className="split__rail-label">{rightLabel}</span>
        </button>
      )}
    </div>
  );
}
