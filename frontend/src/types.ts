// Mirrors the backend pydantic schemas (backend/src/omnichain/models/schemas.py)
// and the router response models. Keep in sync with the API.

export type CharacterScope = "global" | "session";

export type ShotStatus =
  | "pending"
  | "compiled"
  | "generating"
  | "generated"
  | "approved"
  | "failed";

export interface Character {
  id: string;
  name: string;
  physical_traits: string;
  wardrobe: string | null;
  reference_uri: string | null;
  scope: CharacterScope;
}

export interface ShotVersion {
  version: number;
  interaction_id: string;
  clip_uri: string;
  instruction: string | null;
}

export interface Shot {
  id: string;
  index: number;
  duration_s: number;
  draft_text: string;
  compiled_prompt: string | null;
  interaction_id: string | null;
  versions: ShotVersion[];
  status: ShotStatus;
}

export interface Session {
  id: string;
  concept: string;
  style_tone: string;
  gcs_bucket: string;
  gcs_folder: string;
  master_audio_uri: string | null;
  character_ids: string[];
  shots: Shot[];
}

export interface GenerateResponse {
  shot_id: string;
  version: number;
  interaction_id: string;
  clip_uri: string;
  signed_url: string | null;
  status: ShotStatus;
}

export interface AssembleResponse {
  final_uri: string;
  signed_url: string;
  shot_count: number;
}

export interface FoldersResponse {
  bucket: string;
  folders: string[];
}

// Structured error body returned by the backend exception handlers.
export interface ApiErrorBody {
  error: {
    type: string;
    message: string;
    detail: string | null;
    correlation_id: string | null;
  };
}
