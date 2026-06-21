export type User = {
  id: string;
  username: string;
  is_admin: boolean;
  created_at?: number;
};

export type Session = {
  session_id: string;
  user_id: string;
  guest?: boolean;
  turn_count: number;
  game_started: boolean;
  game_over: boolean;
  finale: boolean;
  error?: string;
  choices: string[];
  fallback_prompt?: { active: boolean; text: string };
  character: Record<string, any>;
  world: Record<string, any>;
  events: Array<Record<string, any>>;
  panels: Record<string, string>;
};

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
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // keep status text
    }
    throw new Error(String(detail));
  }
  return response.json() as Promise<T>;
}
