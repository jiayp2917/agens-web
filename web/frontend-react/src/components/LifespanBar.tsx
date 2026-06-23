export function LifespanBar({ value, max, compact = false }: { value: number; max: number; compact?: boolean }) {
  const safeMax = Math.max(1, Number(max) || 1);
  const safeValue = Math.max(0, Math.min(Number(value) || 0, safeMax));
  const percent = Math.round((safeValue / safeMax) * 100);
  return (
    <div className={`lifespan-bar ${compact ? "compact-lifespan" : ""}`}>
      <span>
        <span>寿元</span>
        <strong>{safeValue}/{safeMax}</strong>
      </span>
      <div className="stat-meter" role="meter" aria-label="寿元" aria-valuenow={safeValue} aria-valuemin={0} aria-valuemax={safeMax}>
        <i style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
