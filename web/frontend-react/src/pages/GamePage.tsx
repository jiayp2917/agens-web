import { useMemo, useState } from "react";
import { Home, Save, Settings } from "lucide-react";
import type { DialogMode, Session } from "../lib/api";
import { choiceSemantics, realmLifespanCap } from "../lib/catalog";
import { eventText, isReadableEvent, toPositiveNumber } from "../lib/util";
import { StatLine } from "../components/StatLine";
import { FallbackBanner } from "../components/FallbackBanner";

export function GamePage({
  session,
  busy,
  runTurn,
  openDialog,
  onHome,
}: {
  session: Session;
  busy: boolean;
  runTurn: (path: string, body: unknown) => Promise<void>;
  openDialog: (mode: DialogMode) => void;
  onHome: () => void;
}) {
  const character = session.character || {};
  const world = session.world || {};
  const [panel, setPanel] = useState<keyof Session["panels"]>("status");
  const lifespanCap = toPositiveNumber(character.lifespan, realmLifespanCap[String(character.realm || "")] || 100);
  const lifespanMax = Math.max(realmLifespanCap[String(character.realm || "")] || 100, lifespanCap);
  const remainingLifespan = Math.max(
    0,
    Math.min(
      toPositiveNumber(
        character.remaining_lifespan,
        Math.max(0, lifespanCap - (Number(character.age) || 0)),
      ),
      lifespanMax,
    ),
  );
  const events = useMemo(() => session.events.filter(isReadableEvent), [session.events]);
  const chronicleYear = Number(world.day_count || 1);

  return (
    <section className="game-page">
      <header className="game-summary">
        <div>
          <h2>{character.name || "无名"}</h2>
          <p>{character.realm || "练气"}{character.realm_stage || 1}层 · 编年 {chronicleYear} 年 · 回合 {session.turn_count}</p>
          <span className="session-mode">{session.guest ? "访客局 · 不提供云端存档" : "账号局 · 可存档"}</span>
        </div>
        <div className="summary-actions">
          <button className="plain-btn return-home-btn" type="button" onClick={onHome}><Home size={16} />返回首页</button>
          <button className="icon-btn" onClick={() => openDialog("saves")} aria-label="存档"><Save size={20} /></button>
          <button className="icon-btn" onClick={() => openDialog("settings")} aria-label="设置"><Settings size={20} /></button>
        </div>
      </header>
      <div className="game-grid">
        <aside className="status-panel">
          <strong>{world.location || "山门"}</strong>
          <div className="stat-stack">
            <StatLine label="寿元" value={remainingLifespan} max={lifespanMax} />
          </div>
          <dl className="character-meta">
            <dt>年龄</dt><dd>{character.age || 16}</dd>
            <dt>境界</dt><dd>{character.realm || "练气"}{character.realm_stage || 1}层</dd>
            <dt>灵根</dt><dd>{character.spirit_root || "未明"}</dd>
            <dt>天赋</dt><dd>{character.talent || "平平无奇"}</dd>
            <dt>家世</dt><dd>{character.family_background || "凡俗"}</dd>
          </dl>
          <div className="tool-grid">
            {([
              ["status", "状态"],
              ["inventory", "背包"],
              ["skills", "功法"],
              ["map", "地图"],
              ["quests", "任务"],
              ["realm", "境界"],
            ] as Array<[keyof Session["panels"], string]>).map(([key, label]) => (
              <button key={key} className={panel === key ? "selected-tool" : ""} onClick={() => setPanel(key)}>{label}</button>
            ))}
          </div>
          {panel === "status" ? (
            <dl className="panel-summary">
              <dt>境界</dt><dd>{character.realm || "练气"}{character.realm_stage || 1}层</dd>
              <dt>气运</dt><dd>{character.attributes?.luck ?? "平稳"}</dd>
              <dt>寿元</dt><dd>{remainingLifespan}/{lifespanMax} 年</dd>
              <dt>家世</dt><dd>{character.family_background || "凡俗"}</dd>
            </dl>
          ) : (
            <pre className="panel-output">{String(session.panels?.[panel] || "暂无内容。")}</pre>
          )}
        </aside>
        <section className="story-panel">
          {session.fallback_prompt?.active && <FallbackBanner session={session} busy={busy} runTurn={runTurn} />}
          <div className="story-log chronicle-log" aria-live="polite">
            {events.length === 0 ? <p>叙事将在这里展开。</p> : events.map((event, idx) => <article key={idx}>{eventText(event)}</article>)}
          </div>
          <div className="choice-list">
            {session.choices.map((choice, index) => {
              const semantic = choiceSemantics[index];
              const label = semantic ? `${semantic.key} ${semantic.label}` : String.fromCharCode(65 + index);
              return (
              <button key={`${choice}-${index}`} disabled={busy} title={semantic?.hint} aria-label={`${label}：${choice}`} onClick={() => runTurn(`/api/sessions/${session.session_id}/choice`, { choice_index: index })}>
                <span>{semantic?.key || String.fromCharCode(65 + index)}</span>
                <em><strong>{semantic?.label || "行动"}</strong>{choice}</em>
              </button>
              );
            })}
          </div>
        </section>
      </div>
    </section>
  );
}
