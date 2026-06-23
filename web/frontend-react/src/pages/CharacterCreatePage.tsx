import { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, ChevronRight, Dice5, Home, Minus, Plus, Sparkles } from "lucide-react";
import { api, type Session } from "../lib/api";
import {
  CatalogItem,
  attributes,
  fallbackCatalogs,
  manualAttributeBudget,
  manualAttributeMax,
  manualAttributeMin,
  manualFamilyNames,
  manualSpiritRootNames,
  manualTalentNames,
  randomOnlySpiritRootNames,
} from "../lib/catalog";
import {
  isManualRarity,
  pickRandom,
  randomBetween,
  uniqueByName,
  colorLabel,
  rarityToColor,
} from "../lib/util";
import { RarityDot, rarityClassName } from "../components/RarityDot";

type ChoiceMode = "manual" | "random";

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
  const [choiceMode, setChoiceMode] = useState<ChoiceMode>("manual");
  const [talents, setTalents] = useState<CatalogItem[]>(fallbackCatalogs.talents);
  const [spiritRoots, setSpiritRoots] = useState<CatalogItem[]>(fallbackCatalogs.spiritRoots);
  const [families, setFamilies] = useState<CatalogItem[]>(fallbackCatalogs.families);
  const [difficulties, setDifficulties] = useState<CatalogItem[]>(fallbackCatalogs.difficulties);
  const [talent, setTalent] = useState("平平无奇");
  const [spiritRoot, setSpiritRoot] = useState("金灵根");
  const [familyBackground, setFamilyBackground] = useState("农家");
  const [difficulty, setDifficulty] = useState("普通");
  const [attrValues, setAttrValues] = useState<Record<(typeof attributes)[number][0], number>>(() =>
    Object.fromEntries(attributes.map(([key]) => [key, 50])) as Record<(typeof attributes)[number][0], number>,
  );
  const manualTalents = useMemo(
    () => uniqueByName([...fallbackCatalogs.talents.filter((item) => manualTalentNames.has(item.name)), ...talents.filter(isManualRarity)])
      .filter((item) => !["橙", "红"].includes(rarityToColor(item.rarity || item.grade))),
    [talents],
  );
  const randomTalents = useMemo(() => talents.length ? talents : fallbackCatalogs.talents, [talents]);
  const manualRoots = useMemo(
    () => uniqueByName([
      ...fallbackCatalogs.spiritRoots.filter((item) => manualSpiritRootNames.has(item.name)),
      ...spiritRoots.filter((item) => !randomOnlySpiritRootNames.has(item.name)),
    ]).filter((item) => !["橙", "红"].includes(rarityToColor(item.rarity || item.grade))),
    [spiritRoots],
  );
  const randomRoots = useMemo(() => spiritRoots.length ? spiritRoots : fallbackCatalogs.spiritRoots, [spiritRoots]);
  const manualFamilies = useMemo(
    () => uniqueByName([...fallbackCatalogs.families.filter((item) => manualFamilyNames.has(item.name)), ...families.filter(isManualRarity)])
      .filter((item) => !["橙", "红"].includes(rarityToColor(item.rarity || item.grade))),
    [families],
  );
  const randomFamilies = useMemo(() => families.length ? families : fallbackCatalogs.families, [families]);
  const attrTotal = attributes.reduce((sum, [key]) => sum + attrValues[key], 0);
  const remainingPoints = manualAttributeBudget - attrTotal;
  const selectedTalent = (choiceMode === "manual" ? manualTalents : randomTalents).find((item) => item.name === talent);
  const selectedRoot = (choiceMode === "manual" ? manualRoots : randomRoots).find((item) => item.name === spiritRoot);
  const selectedFamily = (choiceMode === "manual" ? manualFamilies : randomFamilies).find((item) => item.name === familyBackground);

  const loadCatalog = <T extends CatalogItem>(path: string, fallback: T[], setter: (items: T[]) => void) => {
    api<T[]>(path)
      .then((items) => setter(items.length ? items : fallback))
      .catch(() => setter(fallback));
  };

  useEffect(() => {
    loadCatalog("/api/catalog/talents", fallbackCatalogs.talents, setTalents);
    loadCatalog("/api/catalog/spirit_roots", fallbackCatalogs.spiritRoots, setSpiritRoots);
    loadCatalog("/api/catalog/family_backgrounds", fallbackCatalogs.families, setFamilies);
    loadCatalog("/api/catalog/difficulties", fallbackCatalogs.difficulties, setDifficulties);
  }, []);

  useEffect(() => {
    if (choiceMode === "manual") {
      if (!manualTalents.some((item) => item.name === talent)) setTalent(manualTalents[0]?.name || "平平无奇");
      if (!manualRoots.some((item) => item.name === spiritRoot)) setSpiritRoot(manualRoots[0]?.name || "金灵根");
      if (!manualFamilies.some((item) => item.name === familyBackground)) setFamilyBackground(manualFamilies[0]?.name || "农家");
    }
  }, [choiceMode, manualTalents, manualRoots, manualFamilies, talent, spiritRoot, familyBackground]);

  const rollRandom = () => {
    setChoiceMode("random");
    setTalent(pickRandom(randomTalents).name);
    setSpiritRoot(pickRandom(randomRoots).name);
    setFamilyBackground(pickRandom(randomFamilies).name);
    setAttrValues(Object.fromEntries(attributes.map(([key]) => [key, randomBetween(18, 99)])) as Record<(typeof attributes)[number][0], number>);
  };

  const setAttr = (key: (typeof attributes)[number][0], nextValue: number) => {
    setAttrValues((current) => {
      const value = Math.max(manualAttributeMin, Math.min(manualAttributeMax, nextValue));
      const others = attributes.reduce((sum, [itemKey]) => sum + (itemKey === key ? 0 : current[itemKey]), 0);
      const capped = Math.min(value, manualAttributeBudget - others);
      return { ...current, [key]: Math.max(manualAttributeMin, capped) };
    });
  };

  const adjustAttr = (key: (typeof attributes)[number][0], delta: number) => setAttr(key, attrValues[key] + delta);

  const renderCatalogOption = (
    item: CatalogItem,
    selected: boolean,
    onSelect: (name: string) => void,
    disabled: boolean,
  ) => {
    const color = rarityToColor(item.rarity || item.grade);
    return (
      <button
        type="button"
        key={item.name}
        className={`catalog-row ${selected ? "is-selected" : ""}`}
        onClick={() => onSelect(item.name)}
        disabled={disabled}
      >
        <RarityDot color={color} />
        <span>{item.name}</span>
        <em className={rarityClassName(color)}>{color}</em>
        {selected && <CheckCircle2 size={18} aria-hidden="true" />}
      </button>
    );
  };

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
            {difficulties.map((item) => (
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
            <span className="rarity-chip rarity-purple">手选最高：紫</span>
            <span className="rarity-chip rarity-red">随机可出：白/绿/蓝/紫/橙/红</span>
            <span>难度：{difficulty}</span>
          </div>
          <button className="primary-btn start-btn" disabled={busy || (choiceMode === "manual" && attrTotal > manualAttributeBudget)} type="submit">
            {busy ? "进入中..." : <>开始修行<ChevronRight size={22} /></>}
          </button>
        </section>

        <section className="creation-panel fate-panel">
          <header>
            <h2>命数<span className="seal">命</span></h2>
          </header>
          <div className="catalog-group">
            <h3><Sparkles size={18} />天赋</h3>
            {(choiceMode === "manual" ? manualTalents : randomTalents).map((item) => renderCatalogOption(item, item.name === talent, setTalent, choiceMode === "random"))}
          </div>
          <div className="catalog-group">
            <h3>灵根</h3>
            {(choiceMode === "manual" ? manualRoots : randomRoots).map((item) => renderCatalogOption(item, item.name === spiritRoot, setSpiritRoot, choiceMode === "random"))}
          </div>
          <div className="catalog-group">
            <h3>家世</h3>
            {(choiceMode === "manual" ? manualFamilies : randomFamilies).map((item) => renderCatalogOption(item, item.name === familyBackground, setFamilyBackground, choiceMode === "random"))}
          </div>
          <p className="unlock-note">当前：{colorLabel(selectedTalent || { name: talent })} · {colorLabel(selectedRoot || { name: spiritRoot })} · {colorLabel(selectedFamily || { name: familyBackground })}</p>
        </section>

        <section className="creation-panel attribute-panel">
          <header>
            <h2>六维<span className="seal">体</span></h2>
            <p>可分配点数：<strong>{Math.max(0, remainingPoints)}</strong>/{manualAttributeBudget}</p>
          </header>
          <div className="attr-grid">
            {attributes.map(([key, label]) => (
              <label key={key} className={key === "luck" ? "luck-attr" : ""}>
                <span className="attr-icon" aria-hidden="true">{label.slice(0, 1)}</span>
                <span className="attr-label"><span>{label}</span><output>{attrValues[key]}</output></span>
                <button type="button" disabled={choiceMode === "random"} onClick={() => adjustAttr(key, -1)} aria-label={`${label}减少`}><Minus size={18} /></button>
                <input
                  disabled={choiceMode === "random"}
                  name={key}
                  type="range"
                  min={manualAttributeMin}
                  max={manualAttributeMax}
                  value={Math.min(manualAttributeMax, attrValues[key])}
                  onChange={(event) => setAttr(key, Number(event.target.value))}
                />
                <button type="button" disabled={choiceMode === "random"} onClick={() => adjustAttr(key, 1)} aria-label={`${label}增加`}><Plus size={18} /></button>
              </label>
            ))}
          </div>
          <p className="attr-help">{choiceMode === "manual" ? `单项 ${manualAttributeMin}-${manualAttributeMax}，总和不超过 ${manualAttributeBudget}` : "随机属性已生成，不占用手动点数预算。"}</p>
          {choiceMode === "manual" && remainingPoints < 0 && <p className="attr-error">点数超出 {Math.abs(remainingPoints)}，请降低属性后开始。</p>}
        </section>
      </form>
    </section>
  );
}
