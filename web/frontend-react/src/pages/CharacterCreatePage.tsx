import { FormEvent } from "react";
import { CheckCircle2, ChevronRight, Dice5, Home, Sparkles } from "lucide-react";
import type { Session } from "../lib/api";
import {
  manualAttributeBudget,
} from "../lib/catalog";
import { colorLabel } from "../lib/util";
import { CatalogGroup } from "../components/CatalogGroup";
import { AttributeAllocator } from "../components/AttributeAllocator";
import { useCatalogs } from "../hooks/useCatalogs";
import { useCharacterFormReducer } from "../hooks/useCharacterFormReducer";

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
    selectedTalent,
    selectedRoot,
    selectedFamily,
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
          <a className="brand creation-brand" href="https://www.jiayp2917.xyz/" target="_blank" rel="noreferrer">jiayp</a>
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
          <CatalogGroup title="天赋" items={choiceMode === "manual" ? manualTalents : randomTalents} selectedName={talent} onSelect={setTalent} disabled={choiceMode === "random"} icon={<Sparkles size={18} />} />
          <CatalogGroup title="灵根" items={choiceMode === "manual" ? manualRoots : randomRoots} selectedName={spiritRoot} onSelect={setSpiritRoot} disabled={choiceMode === "random"} />
          <CatalogGroup title="家世" items={choiceMode === "manual" ? manualFamilies : randomFamilies} selectedName={familyBackground} onSelect={setFamilyBackground} disabled={choiceMode === "random"} />
          <p className="unlock-note">当前：{colorLabel(selectedTalent || { name: talent })} · {colorLabel(selectedRoot || { name: spiritRoot })} · {colorLabel(selectedFamily || { name: familyBackground })}</p>
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
