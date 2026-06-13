"""Tests for full 9-realm breakthrough support + ascension finale."""

from __future__ import annotations

from unittest.mock import patch

from agens_novel.game.realm import RealmSystem
from agens_novel.repl.game_session import GameSession


def _make_session_at_final_stage(realm: str, **overrides) -> GameSession:
    """Create a GameSession at the final stage of a given realm, with enough exp."""
    rs = RealmSystem()
    cfg = rs.get_realm_config(realm)
    assert cfg is not None, f"No config for realm {realm}"
    s = GameSession(
        realm=realm,
        realm_stage=cfg.stages,
        experience=cfg.experience_required + 100,
        experience_to_next=cfg.experience_required,
        hp=cfg.hp_base,
        hp_max=cfg.hp_base,
        mp=cfg.mp_base,
        mp_max=cfg.mp_base,
        game_started=True,
        **overrides,
    )
    return s


class TestFullRealmBreakthrough:
    """All 9 realms should allow breakthrough attempts."""

    def test_can_attempt_from_huati(self) -> None:
        """合体 (index 5) should now be eligible for breakthrough."""
        rs = RealmSystem()
        s = _make_session_at_final_stage("合体")
        can, reason = rs.can_attempt_breakthrough(s)
        assert can, f"Should allow breakthrough from 合体: {reason}"

    def test_can_attempt_from_dacheng(self) -> None:
        rs = RealmSystem()
        s = _make_session_at_final_stage("大乘")
        can, reason = rs.can_attempt_breakthrough(s)
        assert can, f"Should allow breakthrough from 大乘: {reason}"

    def test_can_attempt_from_dujie(self) -> None:
        rs = RealmSystem()
        s = _make_session_at_final_stage("渡劫")
        can, reason = rs.can_attempt_breakthrough(s)
        assert can, f"Should allow breakthrough from 渡劫: {reason}"

    def test_cannot_attempt_from_feisheng(self) -> None:
        """飞升 is the final realm — no further breakthrough."""
        rs = RealmSystem()
        s = _make_session_at_final_stage("飞升")
        can, reason = rs.can_attempt_breakthrough(s)
        assert not can, "飞升 should be the max realm"
        assert "最高" in reason or "飞升" in reason

    def test_unknown_realm_rejected(self) -> None:
        rs = RealmSystem()
        s = GameSession(realm="超级赛亚人", realm_stage=1, game_started=True)
        can, reason = rs.can_attempt_breakthrough(s)
        assert not can
        assert "未知" in reason


class TestAscensionFinale:
    """Breakthrough to 飞升 triggers the finale flag."""

    def test_breakthrough_to_feisheng_sets_finale(self) -> None:
        rs = RealmSystem()
        s = _make_session_at_final_stage("渡劫")
        # Force success by patching random.
        with patch("agens_novel.game.realm.random.random", return_value=0.0):
            delta = rs.attempt_breakthrough(s)
        meta = delta.get("meta", {})
        assert meta.get("breakthrough_result") == "success"
        assert meta.get("finale") is True, "飞升 breakthrough should set finale=True"
        assert meta.get("game_over") is True, "飞升 should set game_over"
        assert "飞升" in meta.get("game_over_reason", "")

    def test_non_feisheng_breakthrough_no_finale(self) -> None:
        rs = RealmSystem()
        s = _make_session_at_final_stage("化神")
        with patch("agens_novel.game.realm.random.random", return_value=0.0):
            delta = rs.attempt_breakthrough(s)
        meta = delta.get("meta", {})
        assert meta.get("breakthrough_result") == "success"
        assert "finale" not in meta, "Non-飞升 breakthrough should NOT set finale"
        assert meta.get("game_over") is not True

    def test_failure_does_not_set_finale(self) -> None:
        rs = RealmSystem()
        s = _make_session_at_final_stage("渡劫")
        # Force failure.
        with patch("agens_novel.game.realm.random.random", return_value=1.0):
            delta = rs.attempt_breakthrough(s)
        meta = delta.get("meta", {})
        assert meta.get("breakthrough_result") == "failure"
        assert "finale" not in meta
