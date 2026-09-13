import { useState } from "react";
import type { Container, SoftwareSystem, Workspace } from "../types";

interface ElementTreeProps {
  workspace: Workspace | null;
  /** Double-click on any element opens its definition in the Source tab. */
  onShowDefinition: (elementId: string) => void;
}

const DEFINITION_HINT = "Double-click to view the DSL definition";

/** A collapsible section header row with a chevron. */
function Toggle({
  open,
  label,
  color,
  onToggle,
  onDoubleClick,
}: {
  open: boolean;
  label: string;
  color?: string;
  onToggle: () => void;
  onDoubleClick?: () => void;
}) {
  return (
    <button
      type="button"
      className="tree__toggle"
      onClick={onToggle}
      onDoubleClick={onDoubleClick}
      title={onDoubleClick ? DEFINITION_HINT : undefined}
    >
      <span className={"tree__chevron" + (open ? " tree__chevron--open" : "")}>
        ▶
      </span>
      {color ? (
        <span className="dot" style={{ background: color }} aria-hidden />
      ) : null}
      <span>{label}</span>
    </button>
  );
}

function Leaf({
  color,
  onShowDefinition,
  children,
}: {
  color: string;
  onShowDefinition: () => void;
  children: React.ReactNode;
}) {
  return (
    <li
      className="tree__leaf"
      onDoubleClick={onShowDefinition}
      title={DEFINITION_HINT}
    >
      <span className="dot" style={{ background: color }} /> {children}
    </li>
  );
}

function ContainerNode({
  container,
  onShowDefinition,
}: {
  container: Container;
  onShowDefinition: (elementId: string) => void;
}) {
  // Closed by default. Open, a component-level model renders every
  // component in the sidebar on first paint — samples/c4studio has 42 of
  // them — which buries the sections below and makes the tree unscannable
  // at exactly the scale it exists for.
  const [open, setOpen] = useState(false);
  const hasComponents = container.components.length > 0;
  return (
    <li>
      {hasComponents ? (
        <Toggle
          open={open}
          color="#43a047"
          label={container.name}
          onToggle={() => setOpen((v) => !v)}
          onDoubleClick={() => onShowDefinition(container.id)}
        />
      ) : (
        <Leaf
          color="#43a047"
          onShowDefinition={() => onShowDefinition(container.id)}
        >
          {container.name}
        </Leaf>
      )}
      {hasComponents && open ? (
        <ul>
          {container.components.map((component) => (
            <Leaf
              key={component.id}
              color="#fb8c00"
              onShowDefinition={() => onShowDefinition(component.id)}
            >
              {component.name}
              {component.technology ? (
                <span className="tree__tech"> · {component.technology}</span>
              ) : null}
            </Leaf>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function SystemNode({
  system,
  onShowDefinition,
}: {
  system: SoftwareSystem;
  onShowDefinition: (elementId: string) => void;
}) {
  // Closed by default, for the same reason. The People and Software
  // Systems groups stay open — those are the map, and the map should be
  // visible; what is inside a system is the detail you go looking for.
  const [open, setOpen] = useState(false);
  const hasContainers = system.containers.length > 0;
  return (
    <li>
      {hasContainers ? (
        <Toggle
          open={open}
          color="#1976d2"
          label={system.name}
          onToggle={() => setOpen((v) => !v)}
          onDoubleClick={() => onShowDefinition(system.id)}
        />
      ) : (
        <Leaf
          color="#1976d2"
          onShowDefinition={() => onShowDefinition(system.id)}
        >
          {system.name}
        </Leaf>
      )}
      {hasContainers && open ? (
        <ul>
          {system.containers.map((container) => (
            <ContainerNode
              key={container.id}
              container={container}
              onShowDefinition={onShowDefinition}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * Renders the workspace model as a collapsible tree:
 * people, then software systems -> containers -> components.
 * Double-clicking any element opens its DSL definition.
 */
export function ElementTree({ workspace, onShowDefinition }: ElementTreeProps) {
  const [peopleOpen, setPeopleOpen] = useState(true);
  const [systemsOpen, setSystemsOpen] = useState(true);

  if (!workspace) {
    return (
      <section className="section">
        <h2 className="section__title">Elements</h2>
        <p className="muted">Load a file to explore its elements.</p>
      </section>
    );
  }

  const { people, software_systems } = workspace.model;

  return (
    <section className="section">
      <h2 className="section__title">Elements</h2>
      <ul className="tree section__scroll section__scroll--elements">
        <li>
          <Toggle
            open={peopleOpen}
            label={`People (${people.length})`}
            onToggle={() => setPeopleOpen((v) => !v)}
          />
          {peopleOpen ? (
            <ul>
              {people.length === 0 ? (
                <li className="tree__leaf muted">None</li>
              ) : (
                people.map((person) => (
                  <Leaf
                    key={person.id}
                    color="#0d47a1"
                    onShowDefinition={() => onShowDefinition(person.id)}
                  >
                    {person.name}
                  </Leaf>
                ))
              )}
            </ul>
          ) : null}
        </li>
        <li>
          <Toggle
            open={systemsOpen}
            label={`Software Systems (${software_systems.length})`}
            onToggle={() => setSystemsOpen((v) => !v)}
          />
          {systemsOpen ? (
            <ul>
              {software_systems.length === 0 ? (
                <li className="tree__leaf muted">None</li>
              ) : (
                software_systems.map((system) => (
                  <SystemNode
                    key={system.id}
                    system={system}
                    onShowDefinition={onShowDefinition}
                  />
                ))
              )}
            </ul>
          ) : null}
        </li>
      </ul>
    </section>
  );
}
