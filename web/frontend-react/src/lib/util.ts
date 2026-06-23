import { CatalogItem, visibleEventTypes, hiddenEventTexts } from "./catalog";

export const randomBetween = (min: number, max: number) => Math.floor(Math.random() * (max - min + 1)) + min;
export const pickRandom = <T,>(items: T[]) => items[Math.floor(Math.random() * items.length)];
export const isManualRarity = (item: CatalogItem) => !["紫", "橙", "红"].includes(String(item.rarity || item.grade || ""));
export const uniqueByName = (items: CatalogItem[]) => Array.from(new Map(items.map((item) => [item.name, item])).values());
export const itemLabel = (item: CatalogItem) => {
  const mark = item.rarity || item.grade;
  return mark ? `${item.name} · ${mark}` : item.name;
};
export const toPositiveNumber = (value: unknown, fallback: number) => {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : fallback;
};
export const eventText = (event: Record<string, any>) => String(event.text || "").trim();
export const isReadableEvent = (event: Record<string, any>) => {
  const text = eventText(event);
  if (!text || !visibleEventTypes.has(String(event.type || ""))) return false;
  if (hiddenEventTexts.includes(text)) return false;
  if (/^[\s"'`.,，。:：;；<>{}\[\]\/\\]+$/.test(text)) return false;
  if (/<\/?(choices|state_update)\b/i.test(text)) return false;
  if (/^(choices|state_update|meta|character|world)$/i.test(text)) return false;
  return true;
};

export function formatTime(value: number) {
  if (!value) return "未更新";
  return new Date(value * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}