import { useEffect, useMemo, useReducer } from "react";
import {
  attributes,
  fallbackCatalogs,
  manualAttributeBudget,
  manualAttributeMax,
  manualAttributeMin,
  randomAttributeMax,
  manualFamilyNames,
  manualSpiritRootNames,
  manualTalentNames,
  randomOnlySpiritRootNames,
  type CatalogItem,
} from "../lib/catalog";
import { isManualRarity, pickRandom, rarityToColor, uniqueByName } from "../lib/util";

export type ChoiceMode = "manual" | "random";
export type AttributeKey = (typeof attributes)[number][0];
export type AttributeValues = Record<AttributeKey, number>;

type State = {
  choiceMode: ChoiceMode;
  talent: string;
  spiritRoot: string;
  familyBackground: string;
  difficulty: string;
  attrValues: AttributeValues;
};

type Action =
  | { type: "set-choice-mode"; choiceMode: ChoiceMode }
  | { type: "set-talent"; value: string }
  | { type: "set-spirit-root"; value: string }
  | { type: "set-family-background"; value: string }
  | { type: "set-difficulty"; value: string }
  | { type: "set-attr"; key: AttributeKey; value: number }
  | { type: "roll-random"; talent: string; spiritRoot: string; familyBackground: string; attrValues: AttributeValues }
  | { type: "sync-manual-defaults"; talent: string; spiritRoot: string; familyBackground: string };

const defaultAttributes = () =>
  Object.fromEntries(attributes.map(([key]) => [key, 5])) as AttributeValues;

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "set-choice-mode":
      if (action.choiceMode === "manual" && state.choiceMode !== "manual") {
        return { ...state, choiceMode: action.choiceMode, attrValues: defaultAttributes() };
      }
      return { ...state, choiceMode: action.choiceMode };
    case "set-talent":
      return { ...state, talent: action.value };
    case "set-spirit-root":
      return { ...state, spiritRoot: action.value };
    case "set-family-background":
      return { ...state, familyBackground: action.value };
    case "set-difficulty":
      return { ...state, difficulty: action.value };
    case "set-attr":
      return { ...state, attrValues: setAttributeValue(state.attrValues, action.key, action.value) };
    case "roll-random":
      return {
        ...state,
        choiceMode: "random",
        talent: action.talent,
        spiritRoot: action.spiritRoot,
        familyBackground: action.familyBackground,
        attrValues: action.attrValues,
      };
    case "sync-manual-defaults":
      if (state.choiceMode !== "manual") return state;
      return {
        ...state,
        talent: action.talent,
        spiritRoot: action.spiritRoot,
        familyBackground: action.familyBackground,
      };
  }
}

export function useCharacterFormReducer(catalogs: {
  talents: CatalogItem[];
  spiritRoots: CatalogItem[];
  families: CatalogItem[];
}) {
  const [state, dispatch] = useReducer(reducer, {
    choiceMode: "manual",
    talent: fallbackCatalogs.talents[0]?.name || "",
    spiritRoot: fallbackCatalogs.spiritRoots[0]?.name || "",
    familyBackground: fallbackCatalogs.families[0]?.name || "",
    difficulty: fallbackCatalogs.difficulties[1]?.name || fallbackCatalogs.difficulties[0]?.name || "",
    attrValues: defaultAttributes(),
  });

  const manualTalents = useMemo(
    () => uniqueByName([
      ...fallbackCatalogs.talents.filter((item) => manualTalentNames.has(item.name)),
      ...catalogs.talents.filter(isManualRarity),
    ]).filter(notHighManualRarity),
    [catalogs.talents],
  );
  const randomTalents = useMemo(
    () => catalogs.talents.length ? catalogs.talents : fallbackCatalogs.talents,
    [catalogs.talents],
  );
  const manualRoots = useMemo(
    () => uniqueByName([
      ...fallbackCatalogs.spiritRoots.filter((item) => manualSpiritRootNames.has(item.name)),
      ...catalogs.spiritRoots.filter((item) => !randomOnlySpiritRootNames.has(item.name)),
    ]).filter(notHighManualRarity),
    [catalogs.spiritRoots],
  );
  const randomRoots = useMemo(
    () => catalogs.spiritRoots.length ? catalogs.spiritRoots : fallbackCatalogs.spiritRoots,
    [catalogs.spiritRoots],
  );
  const manualFamilies = useMemo(
    () => uniqueByName([
      ...fallbackCatalogs.families.filter((item) => manualFamilyNames.has(item.name)),
      ...catalogs.families.filter(isManualRarity),
    ]).filter(notHighManualRarity),
    [catalogs.families],
  );
  const randomFamilies = useMemo(
    () => catalogs.families.length ? catalogs.families : fallbackCatalogs.families,
    [catalogs.families],
  );

  useEffect(() => {
    if (state.choiceMode !== "manual") return;
    const nextTalent = manualTalents.some((item) => item.name === state.talent)
      ? state.talent
      : manualTalents[0]?.name || state.talent;
    const nextSpiritRoot = manualRoots.some((item) => item.name === state.spiritRoot)
      ? state.spiritRoot
      : manualRoots[0]?.name || state.spiritRoot;
    const nextFamilyBackground = manualFamilies.some((item) => item.name === state.familyBackground)
      ? state.familyBackground
      : manualFamilies[0]?.name || state.familyBackground;
    if (
      nextTalent !== state.talent
      || nextSpiritRoot !== state.spiritRoot
      || nextFamilyBackground !== state.familyBackground
    ) {
      dispatch({
        type: "sync-manual-defaults",
        talent: nextTalent,
        spiritRoot: nextSpiritRoot,
        familyBackground: nextFamilyBackground,
      });
    }
  }, [
    manualTalents,
    manualRoots,
    manualFamilies,
    state.choiceMode,
    state.talent,
    state.spiritRoot,
    state.familyBackground,
  ]);

  const attrTotal = attributes.reduce((sum, [key]) => sum + state.attrValues[key], 0);
  const remainingPoints = manualAttributeBudget - attrTotal;
  const activeTalents = state.choiceMode === "manual" ? manualTalents : randomTalents;
  const activeRoots = state.choiceMode === "manual" ? manualRoots : randomRoots;
  const activeFamilies = state.choiceMode === "manual" ? manualFamilies : randomFamilies;

  return {
    state,
    dispatch,
    manualTalents,
    randomTalents,
    manualRoots,
    randomRoots,
    manualFamilies,
    randomFamilies,
    activeTalents,
    activeRoots,
    activeFamilies,
    attrTotal,
    remainingPoints,
    selectedTalent: activeTalents.find((item) => item.name === state.talent),
    selectedRoot: activeRoots.find((item) => item.name === state.spiritRoot),
    selectedFamily: activeFamilies.find((item) => item.name === state.familyBackground),
    rollRandom: () => dispatch({
      type: "roll-random",
      talent: pickRandom(randomTalents).name,
      spiritRoot: pickRandom(randomRoots).name,
      familyBackground: pickRandom(randomFamilies).name,
      attrValues: randomAttributePool(),
    }),
    setChoiceMode: (choiceMode: ChoiceMode) => dispatch({ type: "set-choice-mode", choiceMode }),
    setTalent: (value: string) => dispatch({ type: "set-talent", value }),
    setSpiritRoot: (value: string) => dispatch({ type: "set-spirit-root", value }),
    setFamilyBackground: (value: string) => dispatch({ type: "set-family-background", value }),
    setDifficulty: (value: string) => dispatch({ type: "set-difficulty", value }),
    setAttr: (key: AttributeKey, value: number) => dispatch({ type: "set-attr", key, value }),
    adjustAttr: (key: AttributeKey, delta: number) =>
      dispatch({ type: "set-attr", key, value: state.attrValues[key] + delta }),
  };
}

function notHighManualRarity(item: CatalogItem) {
  return !["橙", "红"].includes(rarityToColor(item.rarity || item.grade));
}

function setAttributeValue(current: AttributeValues, key: AttributeKey, nextValue: number): AttributeValues {
  const value = Math.max(manualAttributeMin, Math.min(manualAttributeMax, nextValue));
  const others = attributes.reduce((sum, [itemKey]) => sum + (itemKey === key ? 0 : current[itemKey]), 0);
  const capped = Math.min(value, manualAttributeBudget - others);
  return { ...current, [key]: Math.max(manualAttributeMin, capped) };
}

function randomAttributePool(): AttributeValues {
  let remaining = manualAttributeBudget;
  const values: Partial<AttributeValues> = {};
  attributes.forEach(([key], index) => {
    const slotsLeft = attributes.length - index - 1;
    const value = slotsLeft === 0
      ? remaining
      : Math.floor(Math.random() * (Math.min(randomAttributeMax, remaining) - Math.max(0, remaining - slotsLeft * randomAttributeMax) + 1))
        + Math.max(0, remaining - slotsLeft * randomAttributeMax);
    values[key] = value;
    remaining -= value;
  });
  return values as AttributeValues;
}
