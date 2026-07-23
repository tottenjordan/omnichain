import type {
  AssembleResponse,
  Character,
  CharacterScope,
  FoldersResponse,
  GenerateResponse,
  Session,
} from "./types";

/**
 * Error carrying the backend's structured `{error}` payload so the UI can show
 * the message, type, and correlation id. No failure is ever swallowed.
 */
export class ApiError extends Error {
  readonly type: string;
  readonly detail: string | null;
  readonly correlationId: string | null;
  readonly status: number;

  constructor(
    status: number,
    type: string,
    message: string,
    detail: string | null,
    correlationId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.type = type;
    this.detail = detail;
    this.correlationId = correlationId;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch (cause) {
    throw new ApiError(0, "network_error", "Could not reach the server", String(cause), null);
  }

  if (!resp.ok) {
    // Try to parse the structured error body; fall back to status text.
    let type = "http_error";
    let message = resp.statusText || `Request failed (${resp.status})`;
    let detail: string | null = null;
    let correlationId: string | null = null;
    try {
      const body = await resp.json();
      if (body?.error) {
        type = body.error.type ?? type;
        message = body.error.message ?? message;
        detail = body.error.detail ?? null;
        correlationId = body.error.correlation_id ?? null;
      }
    } catch {
      /* non-JSON error body; keep the status-derived message */
    }
    throw new ApiError(resp.status, type, message, detail, correlationId);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

const jsonBody = (data: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(data),
});

export const api = {
  // --- GCS -----------------------------------------------------------------
  listFolders: (bucket: string) =>
    request<FoldersResponse>(`/api/gcs/folders?bucket=${encodeURIComponent(bucket)}`),
  createFolder: (bucket: string, folder: string) =>
    request<{ bucket: string; folder: string }>("/api/gcs/folders", jsonBody({ bucket, folder })),

  // --- characters ----------------------------------------------------------
  listCharacters: (scope?: CharacterScope) =>
    request<Character[]>(`/api/characters${scope ? `?scope=${scope}` : ""}`),
  createCharacter: (data: Omit<Character, "id">) =>
    request<Character>("/api/characters", jsonBody(data)),
  deleteCharacter: (id: string) =>
    request<void>(`/api/characters/${id}`, { method: "DELETE" }),

  // --- sessions ------------------------------------------------------------
  createSession: (data: {
    concept: string;
    style_tone: string;
    gcs_bucket: string;
    gcs_folder: string;
    master_audio_uri?: string | null;
    character_ids?: string[];
  }) => request<Session>("/api/sessions", jsonBody(data)),
  getSession: (id: string) => request<Session>(`/api/sessions/${id}`),
  storyboard: (id: string, targetSeconds: number) =>
    request<Session>(`/api/sessions/${id}/storyboard`, jsonBody({ target_seconds: targetSeconds })),

  // --- per-shot ------------------------------------------------------------
  generateShot: (sessionId: string, shotId: string) =>
    request<GenerateResponse>(`/api/sessions/${sessionId}/shots/${shotId}/generate`, {
      method: "POST",
    }),
  editShot: (sessionId: string, shotId: string, instruction: string) =>
    request<GenerateResponse>(
      `/api/sessions/${sessionId}/shots/${shotId}/edit`,
      jsonBody({ instruction }),
    ),
  approveShot: (sessionId: string, shotId: string) =>
    request<GenerateResponse>(`/api/sessions/${sessionId}/shots/${shotId}/approve`, {
      method: "POST",
    }),

  // --- assembly ------------------------------------------------------------
  assemble: (sessionId: string) =>
    request<AssembleResponse>(`/api/sessions/${sessionId}/assemble`, { method: "POST" }),
};
