export type User = {
  id: string;
  username: string;
  is_admin: boolean;
  created_at?: number;
};

export type CharacterState = {
  name?: string;
  realm?: string;
  realm_stage?: number;
  age?: number;
  lifespan?: number;
  remaining_lifespan?: number;
  talent?: string;
  spirit_root?: string;
  family_background?: string;
  luck?: number | string;
  attributes?: Record<string, number>;
  legacy_talents?: string[];
  titles?: string[];
  relationships?: Array<{ name: string; relation: string; affinity?: number }>;
};

export type WorldState = {
  calendar_year?: number;
  year?: number;
  day_count?: number;
  current_scene?: string;
  lore_facts?: string[];
  world_profile?: Record<string, unknown>;
};

export type SessionEvent = {
  type: string;
  text?: string;
  age?: number;
  turn?: number;
  [key: string]: unknown;
};

export type Session = {
  session_id: string;
  version: number;
  user_id: string;
  guest?: boolean;
  turn_count: number;
  game_started: boolean;
  game_over: boolean;
  finale: boolean;
  error?: string;
  choices: string[];
  fallback_prompt?: { active: boolean; text: string };
  character: CharacterState;
  world: WorldState;
  events: SessionEvent[];
  panels?: Record<string, string>;
};

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

function publicApiErrorMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) return "请求参数无效。";
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message.trim();
  }
  return fallback || "请求失败。";
}

export type SaveRow = {
  id: string;
  name: string;
  char_name: string;
  realm: string;
  turn_count: number;
  updated_at: number;
};

export type ModelSettings = {
  provider: string;
  base_url: string;
  model: string;
  api_key_set: boolean;
  api_key_masked: string;
  source: "user" | "system";
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
  if (!response.ok) {
    const fallback = response.status === 422 ? "请求参数无效。" : response.statusText || "请求失败。";
    let detail: unknown = fallback;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // keep status text
    }
    throw new ApiError(publicApiErrorMessage(detail, fallback), response.status);
  }
  return response.json() as Promise<T>;
}

export function mutationBody(session: Session, body: Record<string, unknown>) {
  return {
    ...body,
    request_id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`,
    expected_version: session.version,
  };
}
