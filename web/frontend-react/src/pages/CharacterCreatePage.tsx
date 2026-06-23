import { FormEvent, useEffect, useMemo, useState } from "react";
import { Home, Sparkles } from "lucide-react";
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
  itemLabel,
  pickRandom,
  randomBetween,
  uniqueByName,
} from "../lib/util";

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
    () => uniqueByName([...fallbackCatalogs.talents.filter((item) => manualTalentNames.has(item.name)), ...talents.filter(isManualRarity)]),
    [talents],
  );
  const randomTalents = useMemo(() => talents.length ? talents : fallbackCatalogs.talents, [talents]);
  const manualRoots = useMemo(
    () => uniqueByName([
      ...fallbackCatalogs.spiritRoots.filter((item) => manualSpiritRootNames.has(item.name)),
      ...spiritRoots.filter((item) => !randomOnlySpiritRootNames.has(item.name)),
    ]),
    [spiritRoots],
  );
  const randomRoots = useMemo(() => spiritRoots.length ? spiritRoots : fallbackCatalogs.spiritRoots, [spiritRoots]);
  const manualFamilies = useMemo(
    () => uniqueByName([...fallbackCatalogs.families.filter((item) => manualFamilyNames.has(item.name)), ...families.filter(isManualRarity)]),
    [families],
  );
  const randomFamilies = useMemo(() => families.length ? families : fallbackCatalogs.families, [families]);
  const attrTotal = attributes.reduce((sum, [key]) => sum + attrValues[key], 0);
  const remainingPoints = manualAttributeBudget - attrTotal;

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

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const randomizeAttributes = choiceMode === "random";
    await runTurn(`/api/sessions/${session.session_id}/start`, {
      game_name: String(form.get("game_name") || ""),
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
      <form className="character-form" onSubmit={submit}>
        <div className="form-topline">
          <p className="eyebrow">开局设定</p>
          <button className="plain-btn" type="button" onClick={onBack}><Home size={16} />返回首页</button>
        </div>
        <h2>角色信息<span className="seal">始</span></h2>
        <div className="mode-grid" aria-label="游玩模式">
          <button type="button" className="active-mode">游戏模式 Alpha</button>
          <button type="button" disabled>小说模式</button>
          <button type="button" disabled>引导模式</button>
        </div>
        <div className="creation-mode" aria-label="开局方式">
          <button type="button" className={choiceMode === "manual" ? "selected-tool" : ""} onClick={() => setChoiceMode("manual")}>自行选择</button>
          <button type="button" className={choiceMode === "random" ? "selected-tool" : ""} onClick={rollRandom}><Sparkles size={16} />随机生成</button>
        </div>
        <div className="form-grid">
          <label>游戏名称<input name="game_name" placeholder="本局世界种子" /></label>
          <label>角色名<input name="char_name" placeholder="留空则自动生成" /></label>
          <label>天赋<select name="talent" value={talent} disabled={choiceMode === "random"} onChange={(event) => setTalent(event.target.value)}>
            {(choiceMode === "manual" ? manualTalents : randomTalents).map((item) => <option key={item.name} value={item.name}>{itemLabel(item)}</option>)}
          </select></label>
          <label>灵根<select name="spirit_root" value={spiritRoot} disabled={choiceMode === "random"} onChange={(event) => setSpiritRoot(event.target.value)}>
            {(choiceMode === "manual" ? manualRoots : randomRoots).map((item) => <option key={item.name} value={item.name}>{itemLabel(item)}</option>)}
          </select></label>
          <label>家世<select name="family_background" value={familyBackground} disabled={choiceMode === "random"} onChange={(event) => setFamilyBackground(event.target.value)}>
            {(choiceMode === "manual" ? manualFamilies : randomFamilies).map((item) => <option key={item.name} value={item.name}>{itemLabel(item)}</option>)}
          </select></label>
          <label>难度<select name="difficulty" value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
            {difficulties.map((item) => <option key={item.name}>{item.name}</option>)}
          </select></label>
        </div>
        <div className="selection-preview" aria-live="polite">
          <span className="rarity-chip rarity-purple">手选最高：紫</span>
          <span className="rarity-chip rarity-red">随机可出：白/绿/蓝/紫/橙/红</span>
          <span>难度：{difficulty}</span>
          <span>当前：{talent} · {spiritRoot} · {familyBackground}</span>
        </div>
        <div className="unlock-note">通关和结局奖励会逐步解锁更高阶天赋、家世和灵根。</div>
        <div className="attr-budget">
          <strong>{choiceMode === "manual" ? `手动点数 ${attrTotal}/${manualAttributeBudget}` : "随机属性已生成"}</strong>
          <span>{choiceMode === "manual" ? `单项 ${manualAttributeMin}-${manualAttributeMax}` : "随机不占用手动点数预算"}</span>
          {choiceMode === "manual" && <span>{remainingPoints >= 0 ? `剩余 ${remainingPoints}` : `超出 ${Math.abs(remainingPoints)}`}</span>}
        </div>
        <div className="attr-grid">
          {attributes.map(([key, label]) => (
            <label key={key}>
              <span className="attr-label"><span>{label}</span><output>{attrValues[key]}</output></span>
              <input
                disabled={choiceMode === "random"}
                name={key}
                type="range"
                min={manualAttributeMin}
                max={manualAttributeMax}
                value={Math.min(manualAttributeMax, attrValues[key])}
                onChange={(event) => setAttr(key, Number(event.target.value))}
              />
            </label>
          ))}
        </div>
        <button className="primary-btn start-btn" disabled={busy || (choiceMode === "manual" && attrTotal > manualAttributeBudget)} type="submit">
          {busy ? "进入中..." : "开始修行"}
        </button>
      </form>
    </section>
  );
}