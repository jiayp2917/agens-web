import { RotateCcw, Save, Upload } from "lucide-react";
import { SaveRow, Session, User, type AuthMode } from "../lib/api";
import { formatTime } from "../lib/util";

export function SaveSlotsPanel({
  user,
  saves,
  session,
  onSave,
  onLoad,
  onAuth,
}: {
  user: User | null;
  saves: SaveRow[];
  session: Session;
  onSave: (name: string) => void;
  onLoad: (name: string) => void;
  onAuth: (mode: AuthMode) => void;
}) {
  if (!user) {
    return (
      <div className="guest-save-state">
        <Save size={22} />
        <strong>访客游玩不提供云端存档</strong>
        <p>当前局可以继续玩；登录或使用邀请码注册后的新局可保存和读档。</p>
        <div className="inline-actions">
          <button onClick={() => onAuth("login")}>登录读档</button>
          <button className="primary-btn" onClick={() => onAuth("register")}>邀请码注册</button>
        </div>
      </div>
    );
  }

  return (
    <div className="save-list">
      {[1, 2, 3, 4, 5].map((slot) => {
        const name = `slot_${slot}`;
        const row = saves.find((item) => item.name === name);
        return (
          <div className="save-row" key={name}>
            <Save size={18} />
            <div>
              <strong>{`档位 ${slot}`}</strong>
              <small>{row ? `${row.char_name} · ${row.realm} · 回合 ${row.turn_count} · ${formatTime(row.updated_at)}` : "空档"}</small>
            </div>
            <div className="save-row-actions">
              {row && <button onClick={() => onLoad(name)}><Upload size={16} />读档</button>}
              <button onClick={() => onSave(name)}>{row ? <RotateCcw size={16} /> : <Save size={16} />}{row ? "覆盖保存" : "保存到此档"}</button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
