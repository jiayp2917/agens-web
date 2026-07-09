export type CatalogItem = {
  name: string;
  rarity?: string;
  grade?: string;
  description?: string;
};

export const attributes = [
  ["root_bone", "根骨"],
  ["comprehension", "悟性"],
  ["luck", "气运"],
  ["willpower", "心性"],
  ["physique", "体魄"],
  ["soul", "神魂"],
] as const;

export const fallbackCatalogs = {
  talents: [
    { name: "平平无奇", rarity: "白" },
    { name: "草木亲和", rarity: "绿" },
    { name: "剑心微明", rarity: "蓝" },
    { name: "惊雷骨", rarity: "紫" },
    { name: "天命道胎", rarity: "橙" },
  ],
  spiritRoots: [
    { name: "金灵根", grade: "白" },
    { name: "木灵根", grade: "绿" },
    { name: "水灵根", grade: "蓝" },
    { name: "火灵根", grade: "紫" },
    { name: "冰灵根", grade: "橙" },
    { name: "雷灵根", grade: "红" },
  ],
  families: [
    { name: "农家", rarity: "白" },
    { name: "寒门", rarity: "绿" },
    { name: "小族", rarity: "蓝" },
    { name: "宗门旁支", rarity: "紫" },
    { name: "隐世仙族", rarity: "橙" },
  ],
  difficulties: [{ name: "简单" }, { name: "普通" }, { name: "困难" }],
} satisfies Record<string, CatalogItem[]>;

export const manualTalentNames = new Set(["平平无奇", "草木亲和", "剑心微明", "惊雷骨"]);
export const manualSpiritRootNames = new Set(["金灵根", "木灵根", "水灵根", "火灵根", "土灵根", "冰灵根", "雷灵根", "风灵根"]);
export const manualFamilyNames = new Set(["农家", "寒门", "小族", "宗门旁支"]);
export const randomOnlySpiritRootNames = new Set(["阴阳灵根", "混沌灵根"]);
export const manualAttributeBudget = 30;
export const manualAttributeMin = 2;
export const manualAttributeMax = 8;
export const randomAttributeMax = 10;
export const choiceSemantics = [
  { key: "A", label: "稳妥", hint: "闭关、修炼、整顿，低风险推进" },
  { key: "B", label: "机遇", hint: "外出、结交、寻访，中风险探索" },
  { key: "C", label: "风险", hint: "突破、斗法、禁地，高风险结算" },
  { key: "D", label: "气运", hint: "随缘、天命、未知机缘，强受气运影响" },
] as const;

export const realmLifespanCap: Record<string, number> = {
  练气: 100,
  筑基: 200,
  金丹: 500,
  元婴: 1000,
  化神: 2000,
  合体: 4000,
  大乘: 5000,
  渡劫: 6000,
  飞升: 9999,
};

export function formatRealmName(realmValue: unknown, stageValue: unknown) {
  const realm = String(realmValue || "练气");
  const stage = Math.max(1, Number(stageValue) || 1);
  if (realm === "练气") return `${realm}${Math.min(9, stage)}层`;
  if (realm === "飞升") return realm;
  const labels = ["初期", "中期", "后期", "圆满"];
  return `${realm}${labels[Math.min(4, stage) - 1]}`;
}

export const modelPresets = [
  { provider: "Agens", base_url: "https://apihub.agnes-ai.com/v1", model: "agnes-2.0-flash" },
  { provider: "DeepSeek", base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { provider: "Qwen", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { provider: "GLM", base_url: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
] as const;

export const visibleEventTypes = new Set(["narrative", "info", "error", "model_failure", "game_over", "finale"]);
export const hiddenEventTexts = [
  "新会话已创建。",
  "推演天道，生成世界中...",
  "天道推演开局中...",
  "开场叙事已在上方输出。",
  "模型暂不可用，当前以本地故事继续。",
  "模型暂不可用，当前以本地故事继续",
  "模型已返回叙事，但未返回可用 A/B/C/D 选项。",
  "模型已返回叙事，但未返回可用 A/B/C/D 选项",
  "此事未入正史，按本局因果结算。",
  "本回合已按当前局面补齐下一步选择。",
];
