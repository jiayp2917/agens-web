import type { ReactNode } from "react";
import type { CatalogItem } from "../lib/catalog";
import { rarityToColor } from "../lib/util";
import { RarityDot, rarityClassName } from "./RarityDot";

export function CatalogGroup({
  title,
  items,
  selectedName,
  onSelect,
  disabled,
  icon,
}: {
  title: string;
  items: CatalogItem[];
  selectedName: string;
  onSelect: (name: string) => void;
  disabled: boolean;
  icon?: ReactNode;
}) {
  return (
    <details className="catalog-group" open>
      <summary>
        <span>{icon}{title}</span>
      </summary>
      <div className="catalog-list">
        {items.map((item) => (
          <CatalogOption
            key={item.name}
            item={item}
            selected={item.name === selectedName}
            onSelect={onSelect}
            disabled={disabled}
          />
        ))}
      </div>
    </details>
  );
}

function CatalogOption({
  item,
  selected,
  onSelect,
  disabled,
}: {
  item: CatalogItem;
  selected: boolean;
  onSelect: (name: string) => void;
  disabled: boolean;
}) {
  const color = rarityToColor(item.rarity || item.grade);
  return (
    <button
      type="button"
      className={`catalog-row ${selected ? "is-selected" : ""}`}
      onClick={() => onSelect(item.name)}
      disabled={disabled}
    >
      {selected ? <span className="selection-check selected" aria-hidden="true">✓</span> : <span className="selection-check empty" aria-hidden="true" />}
      <RarityDot color={color} />
      <span>{item.name}</span>
      <em className={rarityClassName(color)}>{color}</em>
    </button>
  );
}
