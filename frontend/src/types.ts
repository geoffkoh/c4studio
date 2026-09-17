// Type definitions mirroring the FastAPI backend contract exactly.
// The backend (src/c4studio/webapp/server.py + graph.py) is the source
// of truth; keep these shapes in sync with it.

/** One entry from GET /api/views. */
export interface ViewInfo {
  key: string;
  type: string;
  title: string;
  element_id: string;
  /** Only systemContext/container/component views are renderable. */
  supported: boolean;
}

/** Response body from POST /api/load. */
export interface LoadResult {
  path: string;
  name: string;
  views: ViewInfo[];
}

/** Node kinds emitted by the graph builder (data.kind). */
export type NodeKind =
  | "person"
  | "person-external"
  | "system"
  | "system-external"
  | "container"
  | "component"
  | "boundary"
  | "infrastructure"
  | "container-instance"
  | "system-instance";

/** A React Flow node as returned by GET /api/views/{key}/graph. */
export interface GNode {
  id: string;
  data: {
    label: string;
    kind: string;
    color: string | null;
    technology: string;
    description: string;
    tags: string[];
    /** On boundary nodes: what the boundary is (e.g. "Deployment Node"). */
    boundaryLabel?: string;
    /** Tag-based style overrides (DSL styles block), when defined. */
    background?: string;
    textColor?: string;
    /** Structurizr shape name, e.g. "Cylinder", "Box", "Person". */
    shape?: string;
    /** Outline from the element style: "Solid" | "Dashed" | "Dotted". */
    border?: string;
    stroke?: string;
    strokeWidth?: number;
    /** Percentage, as Structurizr spells it. */
    opacity?: number;
    /** False when an element style declares `metadata false`. */
    showMetadata?: boolean;
    /** On containers that can be expanded in place (container views). */
    expandable?: boolean;
    /** On boundary nodes produced by expanding a container. */
    expanded?: boolean;
    /** The element's perspectives, own then inherited (instances). */
    perspectives?: GPerspective[];
  };
  /** Present on nodes nested inside a boundary group node. */
  parentId?: string;
  /** Usually ABSENT; when missing the frontend runs its own layout. */
  position?: { x: number; y: number };
  /** Persisted boundary dimensions, when the user resized it. */
  size?: { width: number; height: number };
}

/** One legend row. `kind` says which half of the shape applies: an
    element row draws a swatch of the node, a relationship row draws the
    line with an arrowhead. A relationship row carries only what a style
    set — the renderers supply the rest from the line defaults. */
export interface GLegendEntry {
  kind: "element" | "relationship";
  label: string;
  colour?: string;
  shape?: string;
  border?: string;
  lineStyle?: string;
  thickness?: number;
}

/** One perspective on a node or edge, with any `Perspective:` style
    already resolved by the server. Paint fields are absent when no style
    set them. */
export interface GPerspective {
  name: string;
  description: string;
  value: string;
  /** Set when the value is read from here rather than written in the DSL
      — a dynamic perspective, refreshed by the server (PP-179). */
  url?: string;
  /** Element paint. */
  background?: string;
  textColor?: string;
  stroke?: string;
  /** Relationship paint. */
  color?: string;
}

/** A React Flow edge as returned by GET /api/views/{key}/graph. */
export interface GEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  /** 1-based step number; only present on dynamic-view edges. */
  order?: number;
  /** Manual bend points in flow coordinates, from the layout sidecar. */
  waypoints?: [number, number][];
  /** Dragged label offset from its default place, from the sidecar. */
  labelOffset?: [number, number];
  /** Resolved relationship-style paint; absent fields use the defaults
      (dashed, per upstream Structurizr). */
  color?: string;
  lineStyle?: string;
  thickness?: number;
  opacity?: number;
  /** Present only on an edge that is one relationship, not a lift of
      several. */
  perspectives?: GPerspective[];
}

/** Response body from GET /api/views/{key}/graph. */
export interface GraphData {
  nodes: GNode[];
  edges: GEdge[];
  /** dagre rank direction from the view's autoLayout: TB, BT, LR or RL. */
  rankDirection: "TB" | "BT" | "LR" | "RL";
  /** Separations from the view's autoLayout; the viewer's defaults when
      the view declares none. */
  rankSeparation?: number;
  nodeSeparation?: number;
  /** Distinct element styles used by this view, for the legend. */
  legend?: GLegendEntry[];
  /** Every perspective name in the model, sorted; offered by the picker. */
  perspectives?: string[];
  /** Expansion state the server applied — the request's explicit lists, or
      the layout sidecar's saved state when the request named none. Clients
      seed their toggles from these on first load of a view. */
  expandedIds?: string[];
  collapsedIds?: string[];
  /** Dragged title/legend positions from the sidecar, keyed "title" /
      "legend"; absent chrome keeps its computed placement. */
  chrome?: Record<string, [number, number]>;
}

/** Response body from POST /api/views/{key}/layout. */
export interface LayoutResult {
  saved: string;
}

/** Response body from GET /api/capabilities — what this server allows.

    `features` is an open map: a newer server may report keys this client
    does not know, and must be free to. Read it defensively. */
export interface Capabilities {
  readOnly: boolean;
  mode: "studio" | "viewer";
  version: string;
  features: Record<string, boolean>;
}

/** Abstraction level rendered by the full-model explorer. */
export type ExplorerLevel = "systems" | "containers" | "components";

/** One entry of the explorer's flat element search index. */
export interface ModelElement {
  id: string;
  name: string;
  kind: string;
  technology: string;
  description: string;
  tags: string[];
  /** Human-readable ancestry path, e.g. "Internet Banking › API". */
  parent: string;
  /** Shallowest explorer level at which this element has its own node. */
  level: ExplorerLevel;
}

/** A declared model relationship (implied ones are excluded). */
export interface ModelRelationship {
  id: string;
  source_id: string;
  destination_id: string;
  description: string;
  technology: string;
}

/** Response body from GET /api/model/graph. */
export interface ModelGraphData {
  nodes: GNode[];
  edges: GEdge[];
  rankDirection: "TB" | "BT" | "LR" | "RL";
  elements: ModelElement[];
  relationships: ModelRelationship[];
  /** Element id -> keys of the supported views the element appears in. */
  views_by_element: Record<string, string[]>;
}

/** Response body from GET /api/status (live-reload heartbeat). */
export interface StatusResult {
  path: string | null;
  /** Increments on every successful server-side reload. */
  generation: number;
  /** Parse error from the last failed reload; old workspace still served. */
  error: string | null;
  /** Constructs the parser understood but skipped in the loaded workspace.
      Absent from servers older than PP-122. */
  diagnostics?: DslDiagnostic[];
}

/** One problem the parser found, positioned so an editor can place it.

    `path` is root-relative, matching the keys `GET /api/source` uses, so a
    diagnostic can be matched to the file it belongs to. `column` is
    1-based and `endColumn` exclusive; both may be null for a whole-line
    diagnostic. Shape matches `c4 check --json`, which the VS Code
    extension already consumes — one contract, not two. */
export interface DslDiagnostic {
  path: string | null;
  line: number | null;
  column: number | null;
  endColumn: number | null;
  severity: "error" | "warning";
  code: string;
  message: string;
}

/** Response body from PUT /api/source. */
export interface SaveSourceResult {
  path: string;
  /** The file's hash after writing — the baseline for the next save. */
  fingerprint: string;
  /** Reload generation after the save. The client adopts this so the poll
      does not treat its own save as someone else's edit. */
  generation: number;
  /** Whether the saved file was part of the loaded workspace. */
  reloaded: boolean;
  /** Parse error, when the saved text does not parse. The file is still
      written; the previous workspace keeps being served. */
  error: string | null;
  diagnostics: DslDiagnostic[];
  views: ViewInfo[];
}

/** Body of a 409 from PUT /api/source: someone else changed the file. */
export interface SaveConflict {
  code: "conflict";
  path: string;
  /** Hash of what is actually on disk now. */
  fingerprint: string | null;
  /** The on-disk text, so a diff needs no second round trip. */
  content: string | null;
}

/** Response body from POST /api/check. */
export interface CheckResult {
  /** False when any diagnostic is an error; warnings still parse. */
  ok: boolean;
  diagnostics: DslDiagnostic[];
  /** Workspace name from the buffer, or null when it did not parse. */
  name: string | null;
  /** Views the buffer would produce — lets the editor preview a view
      appearing or disappearing before anything is saved. */
  views: ViewInfo[];
}

// ---------------------------------------------------------------------------
// Workspace model (GET /api/workspace). Only the fields used by the element
// tree are declared strictly; the full dataclass asdict payload carries more.
// ---------------------------------------------------------------------------

export interface Person {
  id: string;
  name: string;
  description: string;
}

export interface Component {
  id: string;
  name: string;
  technology: string;
}

export interface Container {
  id: string;
  name: string;
  technology: string;
  components: Component[];
}

export interface SoftwareSystem {
  id: string;
  name: string;
  description: string;
  containers: Container[];
}

export interface Relationship {
  id: string;
  source_id: string;
  destination_id: string;
  description: string;
}

export interface WorkspaceModel {
  people: Person[];
  software_systems: SoftwareSystem[];
  relationships: Relationship[];
}

export interface DocSection {
  content: string;
  format: string;
  title: string;
  filename: string;
  order: number;
}

export interface DocDecision {
  id: string;
  title: string;
  date: string;
  status: string;
  content: string;
  format: string;
}

export interface WorkspaceDocumentation {
  sections: DocSection[];
  decisions: DocDecision[];
}

/** Response body from POST /api/assistant.

    `filesSent` is derived server-side from what was actually sent, so the
    UI can name the files rather than describe them. This is the one
    endpoint whose request leaves the machine. */
export interface AssistantResult {
  content: string;
  model: string;
  refused: boolean;
  refusalReason: string;
  usage: { inputTokens: number; outputTokens: number };
  filesSent: string[];
}

/** One starter workspace from GET /api/templates. */
export interface TemplateInfo {
  name: string;
  summary: string;
}

/** One entry from GET /api/files.

    `kind` says what the file is, not merely whether it is offered: a
    `workspace` can be loaded on its own, a `fragment` only exists to be
    `!include`-ed and can only be edited. Fragments used to be hidden,
    which made them unreachable from the UI despite being valid edit
    targets. */
export interface SourceEntry {
  path: string;
  kind: "workspace" | "fragment";
}

/** Response body from GET /api/file — one source file, loaded or not. */
export interface SingleFile {
  path: string;
  content: string;
  fingerprint: string | null;
  editable: boolean;
}

/** One DSL file from GET /api/source. */
export interface SourceFile {
  path: string;
  content: string;
  /** Content hash, sent back on save so an edit made elsewhere in the
      meantime is a conflict rather than a silent overwrite. Absent from
      servers older than PP-124. */
  fingerprint?: string | null;
  /** False when the file is not valid UTF-8: it is shown with the bad
      bytes replaced, but writing it back would destroy them, so the
      editor must stay read-only for it. */
  editable?: boolean;
}

/** Where an element is defined, from GET /api/source. */
export interface SourceLocation {
  path: string;
  line: number;
}

/** Response body from GET /api/source. */
export interface SourceResult {
  files: SourceFile[];
  locations: Record<string, SourceLocation>;
}

export interface Workspace {
  name: string;
  description: string;
  model: WorkspaceModel;
  documentation: WorkspaceDocumentation;
}
