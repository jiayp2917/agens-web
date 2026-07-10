import { api } from "../api/client";
export { ApiError, api, mutationBody } from "../api/client";
export type {
  CharacterState,
  ModelSettings,
  SaveRow,
  Session,
  SessionEvent,
  User,
  WorldState,
} from "../api/client";

export type View = "home" | "auth" | "character" | "game" | "ending";
export type AuthMode = "login" | "register";
export type DialogMode = "settings" | "saves";

export type DeathSummaryResponse = {
  session_id: string;
  is_guest: boolean;
  summary: {
    death_cause: string;
    achievements: Array<{ key: string; name: string; description: string }>;
    rewards: Array<{ type: string; value: string; label: string }>;
    headline: string;
    final_realm: string;
  };
};

export async function fetchDeathSummary(sessionId: string): Promise<DeathSummaryResponse | null> {
  try {
    return await api<DeathSummaryResponse>(`/api/sessions/${sessionId}/death_summary`);
  } catch {
    return null;
  }
}
