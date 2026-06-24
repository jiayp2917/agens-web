import type { ChronicleRecord } from "../lib/chronicle";

export function ChronicleItem({ record }: { record: ChronicleRecord }) {
  return (
    <article className={`chronicle-item ${record.latest ? "latest" : ""}`}>
      <span className="timeline-pin" aria-hidden="true" />
      <div className="chronicle-card">
        <header>
          <strong>{record.year}</strong>
          <span>{record.age}</span>
          {record.latest && <em>最新</em>}
        </header>
        <p>{record.text}</p>
      </div>
    </article>
  );
}
