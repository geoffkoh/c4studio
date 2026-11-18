// The key to merged lines (PP-229).
//
// Collapsing a group merges every line between its members and one other
// element into a single line. When their descriptions differ, the line
// reads "3 relationships [1]" and the legend lists what [1] stands for.
// An exported image has no hover and no details card, so the key is the
// only place those relationships can be read; the Studio, the export and
// `c4 render` all word it here so they cannot disagree.

/** One of the relationships a merged line stands for. */
export interface MergedRelationship {
  /** Element names, not ids: the members the line was lifted from. */
  source: string;
  target: string;
  description: string;
  technology: string;
}

/** What one numbered marker on a merged line stands for. */
export interface MergedNote {
  marker: number;
  relationships: MergedRelationship[];
}

/** `Order Service → Kafka: Publishes events [Avro]`, leaving out the
    parts a relationship does not have. */
export function noteLine(relationship: MergedRelationship): string {
  const ends = `${relationship.source} → ${relationship.target}`;
  const description = relationship.description ? `: ${relationship.description}` : "";
  const technology = relationship.technology ? ` [${relationship.technology}]` : "";
  return `${ends}${description}${technology}`;
}

/** The marker as the line's label prints it. */
export const noteMarker = (marker: number): string => `[${marker}]`;
