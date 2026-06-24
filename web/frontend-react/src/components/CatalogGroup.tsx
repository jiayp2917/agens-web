import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import type { CatalogItem } from "../lib/catalog";
import { rarityToColor } from "../lib/util";
import { RarityDot, rarityClassName } from "./RarityDot";

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
          <em className={rarityClassName(selectedColor)}>{selectedColor}</em>
        </span>
        <span className="catalog-chevron" aria-hidden="true"><ChevronDown size={16} /></span>
      </button>
      {open && <div className="catalog-list">
        {items.map((item) => (
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
