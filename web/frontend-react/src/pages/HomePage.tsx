import { BookOpen, KeyRound, ScrollText, Settings, Upload } from "lucide-react";
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
          <h1>文字修仙模拟器<span className="seal">修</span></h1>
          <div className="hero-rule" aria-hidden="true" />
          <div className="home-actions">
            <button className="primary-btn home-action-main" onClick={onStart}><BookOpen size={22} />新游戏</button>
            <button onClick={onLoad}><Upload size={20} />读档</button>
            <button onClick={onTutorial}><ScrollText size={20} />教程</button>
            <button onClick={onSettings}><Settings size={20} />设置</button>
            <button onClick={() => onAuth("register")}><KeyRound size={20} />邀请码注册</button>
          </div>
          <aside className="community-card" aria-label="玩家交流群">
            <img className="qq-icon" src={assetUrl("assets/xian-game-icon-256.png")} alt="" aria-hidden="true" loading="lazy" />
            <div>
              <strong>QQ群：985776771</strong>
              <span>与道友交流心得，获取最新资讯</span>
            </div>
            <img src={assetUrl("assets/qq_group.png")} alt="文字修仙模拟器 QQ 群二维码" loading="lazy" />
            <small>扫码加入</small>
          </aside>
        </div>
      </div>
    </section>
  );
}
