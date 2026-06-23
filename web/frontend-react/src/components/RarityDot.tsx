import type { CatalogItem } from "../lib/catalog";
import { rarityToColor } from "../lib/util";

export const rarityClassName = (color: string) => {
  const map: Record<string, string> = {
    白: "white",
    绿: "green",
    蓝: "blue",
    紫: "purple",
    橙: "orange",
    红: "red",
  };
  return `rarity-${map[color] || "white"}`;
};

export function RarityDot({ item, color }: { item?: CatalogItem; color?: string }) {
  const resolved = color || rarityToColor(item?.rarity || item?.grade);
  return <span className={`rarity-dot ${rarityClassName(resolved)}`} aria-hidden="true" />;
}
