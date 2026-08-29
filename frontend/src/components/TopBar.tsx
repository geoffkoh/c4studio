export type AppPage =
  | "diagrams"
  | "explorer"
  | "documentation"
  | "decisions"
  | "source";

interface TopBarProps {
  workspaceName: string | null;
  filePath: string | null;
  page: AppPage;
  onPageChange: (page: AppPage) => void;
  /** Counts drive which tabs appear; docs tabs hide when empty. */
  sectionCount: number;
  decisionCount: number;
}

/**
 * Application header showing the title, the currently loaded file, and —
 * when the workspace carries documentation or ADRs — tabs to switch
 * between the diagram, documentation and decision pages.
 */
export function TopBar({
  workspaceName,
  filePath,
  page,
  onPageChange,
  sectionCount,
  decisionCount,
}: TopBarProps) {
  const tabs: { id: AppPage; label: string }[] = [
    { id: "diagrams", label: "Diagrams" },
    ...(filePath ? [{ id: "explorer" as const, label: "Explorer" }] : []),
    ...(sectionCount > 0
      ? [{ id: "documentation" as const, label: `Documentation (${sectionCount})` }]
      : []),
    ...(decisionCount > 0
      ? [{ id: "decisions" as const, label: `Decisions (${decisionCount})` }]
      : []),
    ...(filePath ? [{ id: "source" as const, label: "Source" }] : []),
  ];

  return (
    <header className="topbar">
      <span className="topbar__title">c4studio</span>
      {tabs.length > 1 ? (
        <nav className="topbar__tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={
                "topbar__tab" + (tab.id === page ? " topbar__tab--active" : "")
              }
              onClick={() => onPageChange(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      ) : null}
      <span className="topbar__file">
        {filePath ? (
          <>
            <strong>{workspaceName ?? filePath}</strong>
            {workspaceName ? ` — ${filePath}` : null}
          </>
        ) : (
          "No file loaded"
        )}
      </span>
    </header>
  );
}
