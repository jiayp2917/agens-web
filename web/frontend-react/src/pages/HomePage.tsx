import { BookOpen, Upload, ScrollText, Settings, KeyRound } from "lucide-react";
import type { AuthMode } from "../lib/api";
import { assetUrl } from "../lib/assets";

export function HomePage({
  onStart,
  onLoad,
  onSettings,
  onTutorial,
  onAuth,
}: {
  onStart: () => void;
  onLoad: () => void;
  onSettings: () => void;
  onTutorial: () => void;
  onAuth: (mode: AuthMode) => void;
}) {
  return (
    <section className="home">
      <div className="home-shell">
        <div className="hero">
          <h1>文字修仙模拟器<span className="seal">道</span></h1>
          <div className="play-modes" aria-label="游玩方式">
            <span>访客新局：立即开玩，不提供云端存档</span>
            <span>邀请码账号：登录后可保存和读档</span>
          </div>
          <div className="home-actions">
            <button className="primary-btn" onClick={onStart}><BookOpen size={18} />新游戏</button>
            <button onClick={onLoad}><Upload size={18} />读档</button>
            <button onClick={onTutorial}><ScrollText size={18} />教程</button>
            <button onClick={onSettings}><Settings size={18} />设置</button>
            <button onClick={() => onAuth("register")}><KeyRound size={18} />邀请码注册</button>
          </div>
          <aside className="community-card" aria-label="玩家交流群">
            <div>
              <strong>QQ群：985776771</strong>
              <span>文字修仙模拟器交流与反馈</span>
            </div>
            <img src={assetUrl("assets/qq_group.png")} alt="文字修仙模拟器 QQ 群二维码" loading="lazy" />
          </aside>
        </div>
        <figure className="home-preview">
          <img src={assetUrl("assets/ink_mountain_gate.png")} alt="水墨山门视觉" />
        </figure>
      </div>
    </section>
  );
}
