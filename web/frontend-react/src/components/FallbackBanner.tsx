import { ShieldAlert } from "lucide-react";
import type { Session } from "../lib/api";

export function FallbackBanner({ session, busy, runTurn }: { session: Session; busy: boolean; runTurn: (path: string, body: unknown) => Promise<void> }) {
  const pending = session.pending_model_failure;
  const actionPath = `/api/sessions/${session.session_id}/action`;
  return (
    <aside className="fallback fallback-notice">
      <ShieldAlert size={20} />
      <span>{session.fallback_prompt?.text || "模型暂不可用，请选择处理方式。"}</span>
      {pending && <button disabled={busy} onClick={() => runTurn(actionPath, { action: "retry_model" })}>重试</button>}
      {pending && <button disabled={busy} onClick={() => runTurn(actionPath, { action: "use_local_story" })}>本地故事</button>}
      <button
        disabled={busy}
        onClick={() => runTurn(
          pending ? actionPath : `/api/sessions/${session.session_id}/end`,
          pending ? { action: "end_model_failure" } : { reason: "玩家结束本局。" },
        )}
      >结束本局</button>
    </aside>
  );
}
