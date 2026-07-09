import { useDialogA11y } from "../lib/useDialogA11y";

export function TutorialDialog({ onClose }: { onClose: () => void }) {
  const { scrimRef, onScrimClick } = useDialogA11y(onClose);
  return (
    <div className="modal-scrim" ref={scrimRef} role="dialog" aria-modal="true" aria-label="教程" onClick={onScrimClick}>
      <div className="settings-dialog compact-dialog">
        <header>
          <h2>教程</h2>
          <button className="icon-btn" onClick={onClose} aria-label="关闭">×</button>
        </header>
        <section className="settings-grid">
          <p>游戏以编年史推进。每次选择都会写入一段往事，年龄、寿元和境界由规则引擎结算。</p>
          <p>A/B/C/D 是当前回合固定选项：A 稳妥、B 机遇、C 风险、D 气运。D 代表随缘与天命路线，不是自由输入。</p>
          <p>叙事服务暂未接通时，只显示脱敏提示；访客局仍可继续玩，但不提供云端存档。</p>
          <button className="primary-btn" onClick={onClose}>知道了</button>
        </section>
      </div>
    </div>
  );
}
