// Centralized, typed API client for the pystructurizr backend.
// All network access goes through these wrappers so error handling and the
// URL scheme live in exactly one place. In dev, "/api" is proxied to the
// FastAPI server (see vite.config.ts); in production the SPA is served from
// the same origin as the backend.

import type {
  ExplorerLevel,
  GraphData,
  LayoutResult,
  LoadResult,
  ModelGraphData,
  SourceResult,
  StatusResult,
  ViewInfo,
  Workspace,
} from "./types";

/** Raised for any non-2xx API response, carrying the HTTP status. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Pull a human-readable message out of a failed response body. */
async function extractError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as unknown;
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      return JSON.stringify(detail);
    }
    return JSON.stringify(body);
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
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
    throw new ApiError(response.status, await extractError(response));
  }
  return (await response.json()) as T;
}

/** GET /api/files -> list of source paths relative to the server root. */
export function listFiles(): Promise<string[]> {
  return request<string[]>("/api/files");
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

/** GET /api/views -> the index of views in the loaded workspace. */
export function listViews(): Promise<ViewInfo[]> {
  return request<ViewInfo[]>("/api/views");
}

/** GET /api/model/graph -> the full-model explorer graph at a level. */
export function getModelGraph(level: ExplorerLevel): Promise<ModelGraphData> {
  return request<ModelGraphData>(`/api/model/graph?level=${level}`);
}

/** GET /api/views/{key}/graph -> React Flow graph data for a view. */
export function getViewGraph(
  key: string,
  expand: string[] = [],
): Promise<GraphData> {
  const query = expand.length
    ? `?expand=${encodeURIComponent(expand.join(","))}`
    : "";
  return request<GraphData>(
    `/api/views/${encodeURIComponent(key)}/graph${query}`,
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
): Promise<LayoutResult> {
  return request<LayoutResult>(
    `/api/views/${encodeURIComponent(key)}/layout`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ positions, sizes, waypoints }),
    },
  );
}
