import { ShieldAlert } from "lucide-react";
import type { Session } from "../lib/api";

export function FallbackBanner({ session, busy, runTurn }: { session: Session; busy: boolean; runTurn: (path: string, body: unknown) => Promise<void> }) {
  return (
    <aside className="fallback fallback-notice">
      <ShieldAlert size={20} />
      <span>{session.fallback_prompt?.text || "本回合记录暂未续上，请稍后重试或按当前局面继续。"}</span>
      <button disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/action`, { action: "继续本局" })}>继续本局</button>
      <button disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/end`, { reason: "玩家结束本局。" })}>结束本局</button>
    </aside>
  );
}
