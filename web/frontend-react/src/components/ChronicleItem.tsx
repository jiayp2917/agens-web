import type { ChronicleRecord } from "../lib/chronicle";

export function ChronicleItem({ record }: { record: ChronicleRecord }) {
  return (
    <article className={`chronicle-item ${record.latest ? "latest" : ""}`}>
      <strong className="chronicle-age">{record.age}：</strong>
      <p>{record.text}</p>
    </article>
  );
}
