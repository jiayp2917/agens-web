import { ShieldAlert } from "lucide-react";
import type { Session } from "../lib/api";

export function FallbackBanner({ session, busy, runTurn }: { session: Session; busy: boolean; runTurn: (path: string, body: unknown) => Promise<void> }) {
  return (
    <aside className="fallback fallback-notice">
      <ShieldAlert size={20} />
      <span>{session.fallback_prompt?.text || "模型暂不可用，已切换本地故事，请直接选择下方选项继续。"}</span>
      <button disabled={busy} onClick={() => runTurn(`/api/sessions/${session.session_id}/end`, { reason: "玩家结束本局。" })}>结束本局</button>
    </aside>
  );
}
