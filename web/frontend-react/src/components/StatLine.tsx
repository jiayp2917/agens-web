export function StatLine({ label, value, max }: { label: string; value: number; max: number }) {
  const safeMax = Math.max(0, Number(max) || 0);
  const safeValue = Math.max(0, Math.min(Number(value) || 0, safeMax || Number(value) || 0));
  const percent = safeMax ? Math.round((safeValue / safeMax) * 100) : 0;
  return (
    <div className="stat-line">
      <span><span>{label}</span><strong>{safeValue}/{safeMax}</strong></span>
      <div className="stat-meter" role="meter" aria-label={label} aria-valuenow={safeValue} aria-valuemin={0} aria-valuemax={safeMax}>
        <i style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}