import type { ReactNode } from "react";

import { PropertyList } from "./PropertyList";

/** Human label per element kind, for search results and the details panel. */
export const KIND_LABELS: Record<string, string> = {
  person: "Person",
  "person-external": "Person",
  system: "Software System",
  "system-external": "Software System",
  container: "Container",
  component: "Component",
  custom: "Custom Element",
};

/** One relationship of the element, from its side. */
export interface DetailsRelationship {
  key: string;
  outgoing: boolean;
  /** The element at the other end. */
  peer: string;
  /** Show the peer instead; absent when it cannot be shown here. */
  onPeer?: () => void;
  description: string;
  properties?: Record<string, string>;
}

/** A view the element appears in. */
export interface DetailsView {
  key: string;
  label: string;
  /** Absent for the view already on screen: a link to itself goes nowhere. */
  onOpen?: () => void;
}

interface ElementDetailsProps {
  name: string;
  /** Already a label: "Container", "Relationship". */
  kind: string;
  technology?: string;
  parent?: string;
  description?: string;
  tags?: string[];
  properties?: Record<string, string>;
  relationships?: DetailsRelationship[];
  views?: DetailsView[];
  /** Below the rest, for what only one surface has. */
  children?: ReactNode;
  onShowDefinition?: () => void;
  onClose: () => void;
}

/**
 * What is known about one element (or one relationship), as the
 * Explorer's panel and the Diagrams page's card both show it (PP-205).
 * One component so the two cannot drift: each surface passes the
 * sections it has data for, and a section with nothing in it is left out.
 */
export function ElementDetails({
  name,
  kind,
  technology,
  parent,
  description,
  tags = [],
  properties = {},
  relationships = [],
  views = [],
  children,
  onShowDefinition,
  onClose,
}: ElementDetailsProps) {
  return (
    <>
      <button className="details__close" title="Close" onClick={onClose}>
        ×
      </button>
      <h3 className="details__name">{name}</h3>
      <div className="details__kind">
        [{kind}
        {technology ? `: ${technology}` : ""}]
      </div>
      {parent ? <div className="details__parent">{parent}</div> : null}
      {description ? <p className="details__desc">{description}</p> : null}
      {tags.length > 0 ? (
        <div className="details__tags">
          {tags.map((tag) => (
            <span key={tag} className="details__tag">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {Object.keys(properties).length > 0 ? (
        <>
          <h4 className="details__heading">Properties</h4>
          <PropertyList properties={properties} label={`Properties of ${name}`} />
        </>
      ) : null}

      {relationships.length > 0 ? (
        <>
          <h4 className="details__heading">Relationships</h4>
          <ul className="details__rels">
            {relationships.map((rel) => (
              <li key={rel.key}>
                <span className="details__arrow">{rel.outgoing ? "→" : "←"}</span>
                {rel.onPeer ? (
                  <button className="details__link" onClick={rel.onPeer}>
                    {rel.peer}
                  </button>
                ) : (
                  <span>{rel.peer}</span>
                )}
                {rel.description ? <em> — {rel.description}</em> : null}
                <PropertyList
                  properties={rel.properties ?? {}}
                  label={`Properties of ${rel.description || "relationship"}`}
                />
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {views.length > 0 ? (
        <>
          <h4 className="details__heading">Appears in</h4>
          <ul className="details__views">
            {views.map((view) => (
              <li key={view.key}>
                {view.onOpen ? (
                  <button className="details__link" onClick={view.onOpen}>
                    {view.label}
                  </button>
                ) : (
                  <span>{view.label}</span>
                )}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {children}

      {onShowDefinition ? (
        <button className="details__definition" onClick={onShowDefinition}>
          Open in Source ↗
        </button>
      ) : null}
    </>
  );
}
