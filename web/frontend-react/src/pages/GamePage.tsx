import { useMemo, useState } from "react";
import { Home, Save, Settings } from "lucide-react";
import type { DialogMode, Session } from "../lib/api";
import { choiceSemantics, realmLifespanCap } from "../lib/catalog";
import { eventText, isReadableEvent, toPositiveNumber } from "../lib/util";
import { FallbackBanner } from "../components/FallbackBanner";
import { CharacterAvatar } from "../components/CharacterAvatar";
import { ChoiceButton } from "../components/ChoiceButton";
import { ChronicleItem, type ChronicleRecord } from "../components/ChronicleItem";
import { LifespanBar } from "../components/LifespanBar";
import { RarityDot } from "../components/RarityDot";

const positiveNumber = (value: unknown) => {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
};

const recordAge = (event: Record<string, unknown>) =>
  positiveNumber(event.age ?? event.end_age ?? event.age_after);

const recordYear = (event: Record<string, unknown>) =>
  positiveNumber(event.year ?? event.calendar_year);

const recordTurn = (event: Record<string, unknown>) => {
  const number = Number(event.turn);
  return Number.isFinite(number) && number >= 0 ? number : -1;
};

const cleanChronicleText = (text: string) =>
  text
    .replace(/(^|\n)\s*(?:玄元历|玄历|玄历元年)\s*[元一二三四五六七八九十百千万\d]*\s*年?[，,、：:\s]*/gu, "$1")
    .trim();

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
  const explicitChronicleYear = positiveNumber(world.calendar_year ?? world.year ?? world.day_count) || 1;
  const age = Number(character.age) || 16;
  const currentTurn = Math.max(0, Number(session.turn_count) || 0);
  const realm = `${character.realm || "练气"}${character.realm_stage || 1}层`;
  const luck = character.attributes?.luck ?? character.luck ?? "平稳";
  const cleanChoiceText = (choice: string) => String(choice || "").replace(/^【(?:稳妥|机遇|风险|气运)】\s*/, "").trim();
  const chronicleRecords = useMemo<ChronicleRecord[]>(() => {
    const visibleEvents = events.slice(-8);
    const firstKnownStartAge = events.find((event) => recordAge(event) > 0 && recordTurn(event) <= 0);
    const chronicleStartAge = firstKnownStartAge ? recordAge(firstKnownStartAge) : 0;
    const baseAge = Math.max(1, age - Math.max(currentTurn, visibleEvents.length - 1, 0));
    if (!events.length) {
      return [{
        key: "empty",
        year: `玄元历 ${explicitChronicleYear} 年`,
        age: `${age}岁`,
        text: "叙事将在这里展开。",
        latest: true,
      }];
    }
    const ages = visibleEvents.map((event, index) => recordAge(event) || Math.max(1, baseAge + index));
    return visibleEvents.map((event, index, list) => {
      const text = cleanChronicleText(eventText(event));
      const eventAge = ages[index] || Math.max(1, baseAge + index);
      const eventYear = recordYear(event);
      const eventTurn = recordTurn(event);
      const inferredTurn = Math.max(0, currentTurn - (list.length - 1 - index));
      const ageYear = chronicleStartAge > 0 && eventAge >= chronicleStartAge
        ? eventAge - chronicleStartAge + 1
        : 0;
      const displayYear = ageYear || eventYear || (eventTurn >= 0 ? eventTurn + 1 : inferredTurn + 1);
      return {
        key: `${index}-${text.slice(0, 12)}`,
        year: `玄元历 ${displayYear} 年`,
        age: `${eventAge}岁`,
        text,
        latest: index === list.length - 1,
      };
    });
  }, [age, currentTurn, explicitChronicleYear, events]);
  const latestRecord = chronicleRecords[chronicleRecords.length - 1];
  const currentChronicleYear = Number(latestRecord?.year.match(/\d+/)?.[0] || explicitChronicleYear);

  return (
    <section className="game-page">
      <header className="game-summary game-topbar">
        <a className="brand game-brand" href="https://www.jiayp2917.xyz/" target="_blank" rel="noreferrer">jiayp</a>
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
              <dt>位置</dt><dd>{world.location || "山门"}</dd>
              <dt>回合</dt><dd>{session.turn_count}</dd>
              <dt>寿元</dt><dd>{remainingLifespan}/{lifespanMax} 年</dd>
              <dt>气运</dt><dd>{luck}</dd>
            </dl>
          ) : (
            <pre className="panel-output">{String(session.panels?.[panel] || "暂无内容。")}</pre>
          )}
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
