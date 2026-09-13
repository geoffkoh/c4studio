import type { ViewInfo } from "../types";

interface ViewListProps {
  views: ViewInfo[];
  selectedKey: string | null;
  onSelect: (view: ViewInfo) => void;
}

/**
 * Lists the views in the loaded workspace. Unsupported views are disabled
 * and badged with a "not renderable yet" tooltip.
 */
export function ViewList({ views, selectedKey, onSelect }: ViewListProps) {
  return (
    <section className="section">
      <h2 className="section__title">Views</h2>
      {views.length === 0 ? (
        <p className="muted">Load a file to see its views.</p>
      ) : (
        <ul className="list section__scroll section__scroll--views">
          {views.map((view) => {
            const isActive = view.key === selectedKey;
            const disabled = !view.supported;
            return (
              <li key={view.key}>
                <button
                  type="button"
                  className={
                    "list__item" +
                    (isActive ? " list__item--active" : "") +
                    (disabled ? " list__item--disabled" : "")
                  }
                  onClick={() => !disabled && onSelect(view)}
                  disabled={disabled}
                  title={disabled ? "not renderable yet" : view.title}
                >
                  <span>
                    {view.title || view.key}
                    <span className="list__meta">{view.type}</span>
                  </span>
                  {disabled ? <span className="badge">unsupported</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
