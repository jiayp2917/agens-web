import { eventText } from "./util";

export type ChronicleRecord = {
  key: string;
  year: string;
  age: string;
  text: string;
  latest?: boolean;
};

type ChronicleEvent = Record<string, unknown>;

type ChronicleBuildInput = {
  events: ChronicleEvent[];
  age: number;
  currentTurn: number;
  explicitChronicleYear: number;
};

const positiveNumber = (value: unknown) => {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
};

const recordAge = (event: ChronicleEvent) =>
  positiveNumber(event.age ?? event.end_age ?? event.age_after);

const recordYear = (event: ChronicleEvent) =>
  positiveNumber(event.year ?? event.calendar_year);

const recordTurn = (event: ChronicleEvent) => {
  const number = Number(event.turn);
  return Number.isFinite(number) && number >= 0 ? number : -1;
};

export const cleanChronicleText = (text: string) =>
  text
    .replace(/```(?:json)?/giu, "")
    .replace(/<\/?(?:choices|state_update)\b[^>]*>/giu, "")
    .replace(/(^|\n)\s*(?:玄元历|玄历|玄历元年)\s*[元一二三四五六七八九十百千万\d]*\s*年?[，,、：:\s]*/gu, "$1")
    .trim();

const normalizedChronicleText = (event: ChronicleEvent) =>
  cleanChronicleText(eventText(event)).replace(/\s+/g, "");

export function buildChronicleRecords({
  events,
  age,
  currentTurn,
  explicitChronicleYear,
}: ChronicleBuildInput): ChronicleRecord[] {
  const visibleEvents = events.slice(-12).filter((event, index, list) => {
    const text = normalizedChronicleText(event);
    if (!text) return false;
    if (index === 0) return true;
    return text !== normalizedChronicleText(list[index - 1]);
  }).slice(-8);
  const firstKnownStartAge = events.find((event) => recordAge(event) > 0 && recordTurn(event) <= 0);
  const chronicleStartAge = firstKnownStartAge ? recordAge(firstKnownStartAge) : 0;
  const baseAge = Math.max(1, age - Math.max(currentTurn, visibleEvents.length - 1, 0));

  if (!events.length) {
    return [{
      key: "empty",
      year: `玄元历 ${explicitChronicleYear} 年`,
      age: `${age}岁`,
      text: "叙事将在这里展开。",
      latest: true,
    }];
  }

  const ages = visibleEvents.map((event, index) => recordAge(event) || Math.max(1, baseAge + index));
  return visibleEvents.map((event, index, list) => {
    const text = cleanChronicleText(eventText(event));
    const eventAge = ages[index] || Math.max(1, baseAge + index);
    const eventYear = recordYear(event);
    const eventTurn = recordTurn(event);
    const inferredTurn = Math.max(0, currentTurn - (list.length - 1 - index));
    const ageYear = chronicleStartAge > 0 && eventAge >= chronicleStartAge
      ? eventAge - chronicleStartAge + 1
      : 0;
    const yearCandidates = [
      ageYear,
      eventYear,
      eventTurn >= 0 ? eventTurn + 1 : 0,
      inferredTurn + 1,
    ].filter((year) => year > 0);
    const displayYear = Math.max(...yearCandidates);

    return {
      key: `${index}-${text.slice(0, 12)}`,
      year: `玄元历 ${displayYear} 年`,
      age: `${eventAge}岁`,
      text,
      latest: index === list.length - 1,
    };
  });
}

export const getCurrentChronicleYear = (records: ChronicleRecord[], fallbackYear: number) =>
  Number(records[records.length - 1]?.year.match(/\d+/)?.[0] || fallbackYear);
