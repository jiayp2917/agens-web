import { useMemo } from "react";
import { Home, Save, Settings } from "lucide-react";
import type { DialogMode, Session } from "../lib/api";
import { choiceSemantics, realmLifespanCap } from "../lib/catalog";
import { buildChronicleRecords, getCurrentChronicleYear } from "../lib/chronicle";
import { isReadableEvent, toPositiveNumber } from "../lib/util";
import { FallbackBanner } from "../components/FallbackBanner";
import { CharacterAvatar } from "../components/CharacterAvatar";
import { ChoiceButton } from "../components/ChoiceButton";
import { ChronicleItem } from "../components/ChronicleItem";
import { LifespanBar } from "../components/LifespanBar";
import { RarityDot } from "../components/RarityDot";

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
  const explicitChronicleYear = toPositiveNumber(world.calendar_year ?? world.year ?? world.day_count, 0) || 1;
  const age = Number(character.age) || 16;
  const currentTurn = Math.max(0, Number(session.turn_count) || 0);
  const realm = `${character.realm || "练气"}${character.realm_stage || 1}层`;
  const luck = character.attributes?.luck ?? character.luck ?? "平稳";
  const cleanChoiceText = (choice: string) => String(choice || "").replace(/^【(?:稳妥|机遇|风险|气运)】\s*/, "").trim();
  const chronicleRecords = useMemo(() => buildChronicleRecords({
    events,
    age,
    currentTurn,
    explicitChronicleYear,
  }), [age, currentTurn, explicitChronicleYear, events]);
  const currentChronicleYear = getCurrentChronicleYear(chronicleRecords, explicitChronicleYear);

  return (
    <section className="game-page">
      <header className="game-summary game-topbar">
        <a className="page-brand game-brand" href="https://www.jiayp2917.xyz/" target="_blank" rel="noreferrer">jiayp</a>
        <div className="summary-actions">
          <button className="plain-btn return-home-btn" type="button" onClick={onHome}><Home size={16} />返回首页</button>
          <button className="icon-btn" onClick={() => openDialog("saves")} aria-label="存档"><Save size={20} /></button>
          <button className="icon-btn" onClick={() => openDialog("settings")} aria-label="设置"><Settings size={20} /></button>
        </div>
      </header>
      <section className="mobile-top-summary">
        <CharacterAvatar name={character.name} compact />
        <div>
          <h2>{character.name || "无名"}</h2>
          <p><span>{character.realm || "练气"}</span><span>{age}岁</span><span>寿元 <strong>{remainingLifespan}</strong>/{lifespanMax}</span></p>
        </div>
      </section>
      <div className="game-grid">
        <aside className="status-panel status-rail">
          <CharacterAvatar name={character.name} />
          <h2>{character.name || "无名"}</h2>
          <span className="session-mode">{session.guest ? "访客局 · 不提供云端存档" : "账号局 · 可存档"}</span>
          <div className="rail-stats">
            <span>年龄<strong>{age}岁</strong></span>
            <span>境界<strong>{realm}</strong></span>
          </div>
          <LifespanBar value={remainingLifespan} max={lifespanMax} />
          <dl className="character-meta">
            <dt>天赋</dt><dd><RarityDot />{character.talent || "平平无奇"}</dd>
            <dt>灵根</dt><dd>{character.spirit_root || "未明"}</dd>
            <dt>家世</dt><dd>{character.family_background || "凡俗"}</dd>
            <dt>气运</dt><dd>{luck}</dd>
          </dl>
        </aside>
        <section className="story-panel">
          <header className="chronicle-heading">
            <div>
              <p className="eyebrow">编年史</p>
              <h2>往事时间轴</h2>
            </div>
            <span>玄元历 {currentChronicleYear} 年 · 回合 {session.turn_count}</span>
          </header>
          <div className="story-log chronicle-log" aria-live="polite">
            {chronicleRecords.map((record) => <ChronicleItem key={record.key} record={record} />)}
          </div>
          {session.fallback_prompt?.active && <FallbackBanner session={session} busy={busy} runTurn={runTurn} />}
          <div className="choice-list">
            {session.choices.map((choice, index) => {
              const semantic = choiceSemantics[index];
              const letter = semantic?.key || String.fromCharCode(65 + index);
              return (
                <ChoiceButton
                  key={`${choice}-${index}`}
                  letter={letter}
                  text={cleanChoiceText(choice)}
                  hint={semantic?.hint}
                  disabled={busy}
                  onClick={() => runTurn(`/api/sessions/${session.session_id}/choice`, { choice_index: index })}
                />
              );
            })}
          </div>
        </section>
      </div>
    </section>
  );
}
