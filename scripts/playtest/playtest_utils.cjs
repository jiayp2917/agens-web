"use strict";

function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function unique(values) {
  return Array.from(new Set((values || []).filter(Boolean)));
}

function numberMetric(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

function parseAge(value) {
  const text = String(value || "");
  const match = text.match(/(\d+)\s*岁/u);
  if (match) return Number(match[1]);
  const chineseMatch = text.match(/([零〇一二三四五六七八九十百]+)\s*岁/u);
  return chineseMatch ? chineseNumber(chineseMatch[1]) : 0;
}

function chineseNumber(value) {
  const digits = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
  };
  const text = String(value || "");
  if (!text) return 0;
  if (text === "十") return 10;
  const hundred = text.split("百");
  if (hundred.length === 2) {
    const left = hundred[0] ? digits[hundred[0]] || 0 : 1;
    return left * 100 + chineseNumber(hundred[1]);
  }
  const ten = text.split("十");
  if (ten.length === 2) {
    const left = ten[0] ? digits[ten[0]] || 0 : 1;
    const right = ten[1] ? digits[ten[1]] || 0 : 0;
    return left * 10 + right;
  }
  return Array.from(text).reduce((total, char) => total * 10 + (digits[char] || 0), 0);
}

function normalizeForCompare(value) {
  return cleanText(value)
    .replace(/[，。、“”‘’；：:,.!?！？\s]/gu, "")
    .replace(/[一二三四五六七八九十百千万零〇\d]+岁/gu, "X岁")
    .replace(/\d+/g, "N");
}

function textSimilarity(left, right) {
  const a = normalizeForCompare(left);
  const b = normalizeForCompare(right);
  if (!a || !b) return 0;
  if (a === b) return 1;
  const grams = (text) => {
    const set = new Set();
    for (let index = 0; index < text.length - 1; index += 1) {
      set.add(text.slice(index, index + 2));
    }
    return set.size ? set : new Set([text]);
  };
  const leftSet = grams(a);
  const rightSet = grams(b);
  let overlap = 0;
  for (const gram of leftSet) {
    if (rightSet.has(gram)) overlap += 1;
  }
  return overlap / Math.max(1, Math.min(leftSet.size, rightSet.size));
}

module.exports = {
  chineseNumber,
  cleanText,
  normalizeForCompare,
  numberMetric,
  parseAge,
  textSimilarity,
  unique,
};
