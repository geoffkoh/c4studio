import { GESTURES, SHORTCUTS } from "../shortcuts";

/** The `?` overlay listing every keyboard shortcut. */
export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  return (
    <div className="shortcut-help" onClick={onClose}>
      <div
        className="shortcut-help__panel"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="shortcut-help__title">Keyboard shortcuts</div>
        <table className="shortcut-help__table">
          <tbody>
            {SHORTCUTS.map((s) => (
              <tr key={s.keys}>
                <td>
                  <kbd>{s.keys}</kbd>
                </td>
                <td>{s.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="shortcut-help__title">Mouse</div>
        <table className="shortcut-help__table">
          <tbody>
            {GESTURES.map((g) => (
              <tr key={g.keys}>
                <td>
                  <kbd>{g.keys}</kbd>
                </td>
                <td>{g.action}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="shortcut-help__close" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
