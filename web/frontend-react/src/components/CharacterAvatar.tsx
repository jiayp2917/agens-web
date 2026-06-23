export function CharacterAvatar({ name, compact = false }: { name?: string; compact?: boolean }) {
  const initial = String(name || "修").trim().slice(0, 1) || "修";
  return (
    <div className={`character-avatar ${compact ? "compact-avatar" : ""}`} aria-label={`${name || "角色"}头像`}>
      <span>{initial}</span>
    </div>
  );
}
