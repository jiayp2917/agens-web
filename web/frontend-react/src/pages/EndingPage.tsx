import { useEffect, useState } from "react";
import { ScrollText } from "lucide-react";
import { fetchDeathSummary, type Session } from "../lib/api";

export function EndingPage({ session, onHome, onRestart }: { session: Session; onHome: () => void; onRestart: () => void }) {
  const character = session.character || {};
  const recap = session.events.filter((event) => event.text).slice(-6);
  const [summary, setSummary] = useState<{
    death_cause: string;
    achievements: Array<{ key: string; name: string; description: string }>;
    rewards: Array<{ type: string; value: string; label: string }>;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDeathSummary(session.session_id).then((data) => {
      if (cancelled) return;
      const payload = data?.summary;
      if (!payload) {
        setSummary(null);
        return;
      }
      const achievements = Array.isArray(payload.achievements) ? payload.achievements : [];
      const rewards = Array.isArray(payload.rewards) ? payload.rewards : [];
      if (!achievements.length && !rewards.length && !payload.death_cause) {
        setSummary(null);
        return;
      }
      setSummary({
        death_cause: payload.death_cause || "",
        achievements,
        rewards,
      });
    }).catch(() => {
      if (!cancelled) setSummary(null);
    });
    return () => {
      cancelled = true;
    };
  }, [session.session_id]);

  return (
    <section className="ending-page">
      <div className="ending-card">
        <ScrollText size={36} />
        <h2>{session.finale ? "飞升" : "本局结束"}</h2>
        <p>{session.error || "尘埃落定。"}</p>
        <dl>
          <dt>角色</dt><dd>{character.name || "无名"}</dd>
          <dt>境界</dt><dd>{character.realm || "练气"}{character.realm_stage || 1}层</dd>
          <dt>回合</dt><dd>{session.turn_count}</dd>
        </dl>
        <div className="ending-actions">
          <button className="primary-btn" onClick={onRestart}>再开一局</button>
          <button onClick={onHome}>回首页</button>
        </div>
      </div>
      <aside className="ending-recap">
        <h3>本局记录</h3>
        {summary && (
          <div className="ending-summary">
            {summary.death_cause && <p className="ending-cause">结局：{summary.death_cause}</p>}
            {summary.achievements.length > 0 && (
              <>
                <h4>成就</h4>
                <dl>
                  {summary.achievements.map((achievement) => (
                    <div key={achievement.key || achievement.name}>
                      <dt>{achievement.name}</dt>
                      <dd>{achievement.description}</dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
            {summary.rewards.length > 0 && (
              <>
                <h4>奖励</h4>
                <dl>
                  {summary.rewards.map((reward, idx) => (
                    <div key={`${reward.type}-${idx}`}>
                      <dt>{reward.label || reward.type}</dt>
                      <dd>{reward.value}</dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
          </div>
        )}
        {recap.length ? recap.map((event, index) => <article key={index}>{event.text}</article>) : <p>暂无记录。</p>}
      </aside>
    </section>
  );
}