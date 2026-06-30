import { Minus, Plus } from "lucide-react";
import {
  attributes,
  manualAttributeBudget,
  manualAttributeMax,
  manualAttributeMin,
  randomAttributeMax,
} from "../lib/catalog";
import type { AttributeKey, AttributeValues, ChoiceMode } from "../hooks/useCharacterFormReducer";

export function AttributeAllocator({
  choiceMode,
  values,
  remainingPoints,
  setAttr,
  adjustAttr,
}: {
  choiceMode: ChoiceMode;
  values: AttributeValues;
  remainingPoints: number;
  setAttr: (key: AttributeKey, value: number) => void;
  adjustAttr: (key: AttributeKey, delta: number) => void;
}) {
  return (
    <>
      <header>
        <h2>六维<span className="seal">体</span></h2>
        <p>可分配点数：<strong>{Math.max(0, remainingPoints)}</strong>/{manualAttributeBudget}</p>
      </header>
      <div className="attr-grid">
        {attributes.map(([key, label]) => {
          const value = values[key];
          const meterMax = choiceMode === "random" ? randomAttributeMax : manualAttributeMax;
          return (
            <label key={key} className={key === "luck" ? "luck-attr" : ""}>
              <span className="attr-icon" aria-hidden="true">{label.slice(0, 1)}</span>
              <span className="attr-label"><span>{label}</span><output>{value}</output></span>
              <button type="button" disabled={choiceMode === "random"} onClick={() => adjustAttr(key, -1)} aria-label={`${label}减少`}><Minus size={18} /></button>
              {choiceMode === "random" ? (
                <span
                  className="attr-meter"
                  role="meter"
                  aria-label={label}
                  aria-valuemin={0}
                  aria-valuemax={meterMax}
                  aria-valuenow={value}
                >
                  <span style={{ width: `${Math.max(0, Math.min(100, (value / meterMax) * 100))}%` }} />
                </span>
              ) : (
                <input
                  name={key}
                  type="range"
                  min={manualAttributeMin}
                  max={manualAttributeMax}
                  value={value}
                  onChange={(event) => setAttr(key, Number(event.target.value))}
                />
              )}
              <button type="button" disabled={choiceMode === "random"} onClick={() => adjustAttr(key, 1)} aria-label={`${label}增加`}><Plus size={18} /></button>
            </label>
          );
        })}
      </div>
      <p className="attr-help">
        {choiceMode === "manual"
          ? `单项 ${manualAttributeMin}-${manualAttributeMax}，总和必须等于 ${manualAttributeBudget}`
          : "随机属性为 0-10 浮动，总和固定 30。"}
      </p>
      {choiceMode === "manual" && remainingPoints !== 0 && (
        <p className="attr-error">{remainingPoints > 0 ? `还需分配 ${remainingPoints} 点。` : `点数超出 ${Math.abs(remainingPoints)}，请降低属性后开始。`}</p>
      )}
    </>
  );
}
