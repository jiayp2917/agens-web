import { FormEvent, useState } from "react";
import { CheckCircle2, ChevronRight, Dice5, Home, Sparkles } from "lucide-react";
import type { Session } from "../lib/api";
import {
  manualAttributeBudget,
} from "../lib/catalog";
import { CatalogGroup } from "../components/CatalogGroup";
import { AttributeAllocator } from "../components/AttributeAllocator";
import { useCatalogs } from "../hooks/useCatalogs";
import { useCharacterFormReducer } from "../hooks/useCharacterFormReducer";

type FateGroupKey = "talent" | "root" | "family";

export function CharacterCreatePage({
  session,
  runTurn,
  busy,
  onBack,
}: {
  session: Session;
  runTurn: (path: string, body: unknown) => Promise<void>;
  busy: boolean;
  onBack: () => void;
}) {
  const catalogs = useCatalogs();
  const [openFateGroup, setOpenFateGroup] = useState<FateGroupKey | "">("talent");
  const {
    state,
    manualTalents,
    randomTalents,
    manualRoots,
    randomRoots,
    manualFamilies,
    randomFamilies,
    attrTotal,
    remainingPoints,
    rollRandom,
    setChoiceMode,
    setTalent,
    setSpiritRoot,
    setFamilyBackground,
    setDifficulty,
    setAttr,
    adjustAttr,
  } = useCharacterFormReducer(catalogs);
  const { choiceMode, talent, spiritRoot, familyBackground, difficulty, attrValues } = state;

  const fateGroups = [
    {
      key: "talent" as FateGroupKey,
      title: "天赋",
      description: "影响修行节奏、突破叙事与关键事件。",
      manual: manualTalents,
      random: randomTalents,
      selectedName: talent,
      onSelect: setTalent,
      icon: <Sparkles size={18} />,
    },
    {
      key: "root" as FateGroupKey,
      title: "灵根",
      description: "影响境界突破、机缘类型与修炼取向。",
      manual: manualRoots,
      random: randomRoots,
      selectedName: spiritRoot,
      onSelect: setSpiritRoot,
    },
    {
      key: "family" as FateGroupKey,
      title: "家世",
      description: "决定出生叙事、初始关系与外界牵连。",
      manual: manualFamilies,
      random: randomFamilies,
      selectedName: familyBackground,
      onSelect: setFamilyBackground,
    },
  ];

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const randomizeAttributes = choiceMode === "random";
    await runTurn(`/api/sessions/${session.session_id}/start`, {
      char_name: String(form.get("char_name") || ""),
      talent,
      spirit_root: spiritRoot,
      family_background: familyBackground,
      difficulty,
      randomize_attributes: randomizeAttributes,
      attributes: randomizeAttributes ? {} : attrValues,
    });
  };

  return (
    <section className="character-page">
      <form className="character-form creation-layout" onSubmit={submit}>
        <div className="creation-hero-bar">
          <a className="page-brand creation-brand" href="https://www.jiayp2917.xyz/" target="_blank" rel="noreferrer">jiayp</a>
          <button className="plain-btn" type="button" onClick={onBack}><Home size={16} />返回首页</button>
        </div>

        <section className="creation-panel character-panel">
          <header>
            <h2>主角<span className="seal">始</span></h2>
          </header>
          <label className="field-block">角色名<input name="char_name" placeholder="留空则自动生成" /></label>
          <div className="difficulty-list" aria-label="难度选择">
            {catalogs.difficulties.map((item) => (
              <button type="button" key={item.name} className={difficulty === item.name ? "is-selected" : ""} onClick={() => setDifficulty(item.name)}>
                <span>{item.name}</span>
                {difficulty === item.name && <CheckCircle2 size={18} />}
              </button>
            ))}
          </div>
          <div className="creation-mode" aria-label="开局方式">
            <button type="button" className={choiceMode === "manual" ? "selected-tool" : ""} onClick={() => setChoiceMode("manual")}>自行选择</button>
            <button type="button" className={choiceMode === "random" ? "selected-tool" : ""} onClick={rollRandom}><Dice5 size={16} />随机角色</button>
          </div>
          <div className="selection-preview" aria-live="polite">
            <span>手选最高：紫；随机可出：白 / 绿 / 蓝 / 紫 / 橙 / 红</span>
            <span>当前难度：{difficulty}</span>
          </div>
          <button className="primary-btn start-btn" disabled={busy || (choiceMode === "manual" && attrTotal > manualAttributeBudget)} type="submit">
            {busy ? "进入中..." : <>开始修行<ChevronRight size={22} /></>}
          </button>
        </section>

        <section className="creation-panel fate-panel">
          <header>
            <h2>命数<span className="seal">命</span></h2>
          </header>
          {fateGroups.map((group) => (
            <CatalogGroup
              key={group.key}
              title={group.title}
              description={group.description}
              items={choiceMode === "manual" ? group.manual : group.random}
              selectedName={group.selectedName}
              onSelect={group.onSelect}
              disabled={choiceMode === "random"}
              icon={group.icon}
              open={openFateGroup === group.key}
              onToggle={() => setOpenFateGroup((current) => current === group.key ? "" : group.key)}
            />
          ))}
          <p className="unlock-note">当前：{talent} · {spiritRoot} · {familyBackground}</p>
        </section>

        <section className="creation-panel attribute-panel">
          <AttributeAllocator
            choiceMode={choiceMode}
            values={attrValues}
            remainingPoints={remainingPoints}
            setAttr={setAttr}
            adjustAttr={adjustAttr}
          />
        </section>
      </form>
    </section>
  );
}
