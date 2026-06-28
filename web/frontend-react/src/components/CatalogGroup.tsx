import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import type { CatalogItem } from "../lib/catalog";
import { rarityToColor } from "../lib/util";
import { RarityDot, rarityClassName } from "./RarityDot";

const colorOrder = new Map([
  ["白", 0],
  ["绿", 1],
  ["蓝", 2],
  ["紫", 3],
  ["橙", 4],
  ["红", 5],
]);

const sortedByColor = (items: CatalogItem[]) =>
  [...items].sort((left, right) => {
    const leftColor = rarityToColor(left.rarity || left.grade);
    const rightColor = rarityToColor(right.rarity || right.grade);
    const colorDiff = (colorOrder.get(leftColor) ?? 0) - (colorOrder.get(rightColor) ?? 0);
    return colorDiff || left.name.localeCompare(right.name, "zh-Hans-CN");
  });

export function CatalogGroup({
  title,
  description,
  items,
  selectedName,
  onSelect,
  disabled,
  icon,
  open,
  onToggle,
}: {
  title: string;
  description: string;
  items: CatalogItem[];
  selectedName: string;
  onSelect: (name: string) => void;
  disabled: boolean;
  icon?: ReactNode;
  open: boolean;
  onToggle: () => void;
}) {
  const selected: CatalogItem = items.find((item) => item.name === selectedName) || { name: selectedName };
  const selectedColor = rarityToColor(selected.rarity || selected.grade);
  const orderedItems = sortedByColor(items);
  return (
    <section className={`catalog-group ${open ? "is-open" : ""}`}>
      <button type="button" className="catalog-summary" onClick={onToggle} aria-expanded={open}>
        <span className="summary-copy">
          <strong>{icon}{title}</strong>
          <small>{description}</small>
        </span>
        <span className="selected-pill">
          <RarityDot color={selectedColor} />
          <span>{selected.name}</span>
        </span>
        <span className="catalog-chevron" aria-hidden="true"><ChevronDown size={16} /></span>
      </button>
      {open && <div className="catalog-list">
        {orderedItems.map((item) => (
          <CatalogOption
            key={item.name}
            item={item}
            selected={item.name === selectedName}
            onSelect={onSelect}
            disabled={disabled}
          />
        ))}
      </div>}
    </section>
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
      className={`catalog-row ${rarityClassName(color)} ${selected ? "is-selected" : ""}`}
      onClick={() => onSelect(item.name)}
      disabled={disabled}
    >
      <span className="selection-check" aria-hidden="true" />
      <span>{item.name}</span>
    </button>
  );
}
