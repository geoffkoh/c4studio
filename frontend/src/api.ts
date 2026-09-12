// Centralized, typed API client for the c4studio backend.
// All network access goes through these wrappers so error handling and the
// URL scheme live in exactly one place. In dev, "/api" is proxied to the
// FastAPI server (see vite.config.ts); in production the SPA is served from
// the same origin as the backend.

import type {
  Capabilities,
  CheckResult,
  ExplorerLevel,
  GraphData,
  LayoutResult,
  LoadResult,
  ModelGraphData,
  SaveConflict,
  SaveSourceResult,
  SingleFile,
  SourceEntry,
  SourceResult,
  StatusResult,
  ViewInfo,
  Workspace,
} from "./types";

/** Raised for any non-2xx API response, carrying the HTTP status. */
export class ApiError extends Error {
  readonly status: number;
  /** The response's `detail`, undecoded. A string for most errors; an
      object for the ones a client has to act on rather than just show —
      see {@link saveConflict}. */
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Build the ApiError for a failed response, message and detail together. */
async function failure(response: Response): Promise<ApiError> {
  const fallback = response.statusText || `HTTP ${response.status}`;
  try {
    const body = (await response.json()) as unknown;
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    const message =
      typeof detail === "string" ? detail : JSON.stringify(detail) || fallback;
    return new ApiError(response.status, message, detail);
  } catch {
    return new ApiError(response.status, fallback);
  }
}

/** The structured body of a 409 from {@link saveSource}, or null if the
    error is anything else. Carries the on-disk text, so showing both sides
    of the conflict needs no second round trip. */
export function saveConflict(error: unknown): SaveConflict | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const detail = error.detail;
  if (
    detail &&
    typeof detail === "object" &&
    (detail as { code?: unknown }).code === "conflict"
  ) {
    return detail as SaveConflict;
  }
  return null;
}

/** Perform a fetch and decode JSON, throwing ApiError on failure. */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (cause) {
    throw new ApiError(
      0,
      cause instanceof Error ? cause.message : "Network request failed",
    );
  }
  if (!response.ok) {
    throw await failure(response);
  }
  return (await response.json()) as T;
}

/** GET /api/files -> every source under the root, each with its kind.

    Includes `!include` fragments, which are not loadable but are editable;
    callers that want only what `POST /api/load` accepts filter on
    `kind === "workspace"`. */
export function listFiles(): Promise<SourceEntry[]> {
  return request<SourceEntry[]>("/api/files");
}

/** GET /api/file -> one source file under the root, loaded or not. */
export function getFile(path: string): Promise<SingleFile> {
  return request<SingleFile>(`/api/file?path=${encodeURIComponent(path)}`);
}

/** POST /api/load -> load the workspace at the given relative path. */
export function loadFile(path: string): Promise<LoadResult> {
  return request<LoadResult>("/api/load", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
}

/** GET /api/status -> live-reload heartbeat for the loaded workspace. */
export function getStatus(): Promise<StatusResult> {
  return request<StatusResult>("/api/status");
}

/** GET /api/source -> DSL files and element definition locations. */
export function getSource(): Promise<SourceResult> {
  return request<SourceResult>("/api/source");
}

/** GET /api/workspace -> the full loaded workspace model. */
export function getWorkspace(): Promise<Workspace> {
  return request<Workspace>("/api/workspace");
}

/** POST /api/check -> diagnostics for text that may not be on disk.

    `path` is the root-relative file the buffer belongs to; a buffer that
    is part of the loaded workspace is checked in its root's context, so a
    fragment reports its own problems rather than "no workspace block".
    Writes nothing and changes no server state. */
export function checkSource(
  path: string,
  content: string,
  root?: string,
): Promise<CheckResult> {
  return request<CheckResult>("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content, ...(root ? { root } : {}) }),
  });
}

/** PUT /api/source -> write DSL text to a file under the root.

    `fingerprint` is the file as this client last saw it; pass `null` to
    assert the file does not exist yet (creating one). A mismatch throws
    ApiError with status 409, whose message carries the on-disk content so
    the caller can show both sides. `force` overwrites regardless, and
    should only be set after a person has seen the conflict and chosen. */
export function saveSource(
  path: string,
  content: string,
  fingerprint: string | null,
  force = false,
): Promise<SaveSourceResult> {
  return request<SaveSourceResult>("/api/source", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content, fingerprint, force }),
  });
}

/** GET /api/capabilities -> what this server allows. Needs no workspace. */
export function getCapabilities(): Promise<Capabilities> {
  return request<Capabilities>("/api/capabilities");
}

/** GET /api/views -> the index of views in the loaded workspace. */
export function listViews(): Promise<ViewInfo[]> {
  return request<ViewInfo[]>("/api/views");
}

/** GET /api/model/graph -> the full-model explorer graph at a level. */
export function getModelGraph(level: ExplorerLevel): Promise<ModelGraphData> {
  return request<ModelGraphData>(`/api/model/graph?level=${level}`);
}

/** GET /api/views/{key}/graph -> React Flow graph data for a view.

    `null` omits a parameter, telling the server to apply the state saved
    in the layout sidecar; an array — even an empty one — is sent
    explicitly and overrides what is saved. */
export function getViewGraph(
  key: string,
  expand: string[] | null = null,
  collapse: string[] | null = null,
): Promise<GraphData> {
  const params = new URLSearchParams();
  if (expand !== null) params.set("expand", expand.join(","));
  if (collapse !== null) params.set("collapse", collapse.join(","));
  const query = params.size ? `?${params.toString()}` : "";
  return request<GraphData>(
    `/api/views/${encodeURIComponent(key)}/graph${query}`,
  );
}

/** POST /api/views/{key}/expansion -> persist expand/collapse UI state. */
export function saveExpansion(
  key: string,
  expanded: string[],
  collapsed: string[],
): Promise<LayoutResult> {
  return request<LayoutResult>(
    `/api/views/${encodeURIComponent(key)}/expansion`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expanded, collapsed }),
    },
  );
}

/** DELETE /api/views/{key}/layout -> discard saved positions for a view. */
export function deleteLayout(key: string): Promise<{ reset: string }> {
  return request<{ reset: string }>(
    `/api/views/${encodeURIComponent(key)}/layout`,
    { method: "DELETE" },
  );
}

/** POST /api/views/{key}/layout -> persist node positions and boundary sizes. */
export function saveLayout(
  key: string,
  positions: Record<string, [number, number]>,
  sizes: Record<string, [number, number]> = {},
  waypoints: Record<string, [number, number][]> = {},
  labels: Record<string, [number, number]> = {},
  chrome: Record<string, [number, number]> = {},
): Promise<LayoutResult> {
  return request<LayoutResult>(
    `/api/views/${encodeURIComponent(key)}/layout`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ positions, sizes, waypoints, labels, chrome }),
    },
  );
}
