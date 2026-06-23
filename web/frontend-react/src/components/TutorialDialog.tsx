export function TutorialDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-label="教程">
      <div className="settings-dialog compact-dialog">
        <header><h2>教程</h2><button className="icon-btn" onClick={onClose} aria-label="关闭">×</button></header>
        <section className="settings-grid">
          <p>A/B/C/D 是当前回合固定选项：A 稳妥、B 机遇、C 风险、D 气运。D 代表随缘与天命路线，不是自由输入。</p>
          <p>模型暂不可用时，本局会切到本地故事继续；访客局仍可继续玩，但不提供云端存档。</p>
          <button className="primary-btn" onClick={onClose}>知道了</button>
        </section>
      </div>
    </div>
  );
}