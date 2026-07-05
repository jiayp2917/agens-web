"""add Chinese comments for PostgreSQL schema"""

from __future__ import annotations

from alembic import op

revision = "20260705_0007"
down_revision = "20260704_0006"
branch_labels = None
depends_on = None


TABLE_COMMENTS = {
    "users": "注册用户表。保存账号身份、密码哈希、管理员标记和创建/更新时间。",
    "invite_codes": "邀请码表。保存邀请码哈希、角色、使用次数、过期和禁用状态。",
    "sessions": "当前游戏会话表。保存 WebRunner 快照和最近事件，用于继续当前局。",
    "saves": "用户手动存档表。每个用户按存档名唯一保存快照和事件。",
    "model_config": "系统默认模型配置单例。作为用户未配置个人模型时的 Agens 默认兜底。",
    "user_model_configs": "用户个人模型配置表。每个注册用户最多一条，加密保存个人 API Key。",
    "catalog_talents": "天赋目录表。保存可选天赋、稀有度、属性修正和标签。",
    "catalog_family_backgrounds": "家世目录表。保存可选家世、初始资源/风险和故事标签。",
    "catalog_spirit_roots": "灵根目录表。保存灵根元素、品级、修炼/突破加成和事件标签。",
    "catalog_difficulties": "难度目录表。保存风险、奖励、寿元和气运修正。",
    "catalog_story_seeds": "故事种子目录表。保存世界观/开场故事类型和标签。",
    "run_achievements": "单局成就表。记录用户在某局结束时获得的成就。",
    "account_rewards": "账号奖励表。记录终局后沉淀到账户层的奖励。",
    "legacy_bonuses": "跨局传承加成表。记录下局开场可消费的传承奖励。",
    "game_runs": "终局汇总/进度表。记录完成局的结局摘要，并驱动账号进度统计。",
    "game_turns": "回合遥测表。按会话 ID 分组记录已结算回合、选择、状态增量和叙事。",
    "player_progress": "玩家进度表。记录完成局数和飞升次数，用于稀有度解锁。",
}


COLUMN_COMMENTS = {
    "users": {
        "id": "用户 UUID。",
        "username": "登录用户名，全局唯一。",
        "password_hash": "密码哈希；不保存明文密码。",
        "is_admin": "是否管理员账号。",
        "created_at": "创建时间，Unix epoch 秒。",
        "updated_at": "更新时间，Unix epoch 秒。",
    },
    "invite_codes": {
        "id": "邀请码记录 UUID。",
        "code_hash": "邀请码哈希；不保存明文邀请码。",
        "role": "邀请码授予角色，通常为 user 或 admin。",
        "max_uses": "最大可使用次数。",
        "uses": "已使用次数。",
        "expires_at": "过期时间，Unix epoch 秒；为空表示不过期。",
        "disabled": "是否已禁用。",
        "created_at": "创建时间，Unix epoch 秒。",
        "created_by": "创建该邀请码的管理员用户 ID。",
    },
    "sessions": {
        "id": "会话 UUID；也是当前局运行时会话标识。",
        "user_id": "所属用户 ID。",
        "title": "会话标题，通常为角色名或新局标题。",
        "snapshot": "当前权威游戏状态快照 JSONB。",
        "events": "最近前端事件/叙事事件 JSONB，仅保留滚动窗口。",
        "created_at": "创建时间，Unix epoch 秒。",
        "updated_at": "更新时间，Unix epoch 秒。",
    },
    "saves": {
        "id": "存档 UUID。",
        "user_id": "所属用户 ID。",
        "name": "存档槽名称；同一用户内唯一。",
        "snapshot": "存档时的权威游戏状态快照 JSONB。",
        "events": "存档时保留的最近事件 JSONB。",
        "created_at": "创建时间，Unix epoch 秒。",
        "updated_at": "更新时间，Unix epoch 秒。",
    },
    "model_config": {
        "id": "单例主键，固定为 1。",
        "provider": "系统默认模型服务商。",
        "base_url": "系统默认 OpenAI-compatible Base URL。",
        "model": "系统默认模型名。",
        "api_key_masked": "脱敏后的系统默认 API Key 展示值。",
        "api_key_set": "系统默认 API Key 是否已配置。",
        "api_key_encrypted": "应用层加密后的系统默认 API Key 密文。",
        "updated_at": "更新时间，Unix epoch 秒。",
    },
    "user_model_configs": {
        "user_id": "所属用户 ID，也是主键。",
        "provider": "用户个人模型服务商。",
        "base_url": "用户个人 OpenAI-compatible Base URL。",
        "model": "用户个人模型名。",
        "api_key_masked": "脱敏后的用户个人 API Key 展示值。",
        "api_key_set": "用户个人 API Key 是否已配置。",
        "api_key_encrypted": "应用层加密后的用户个人 API Key 密文。",
        "updated_at": "更新时间，Unix epoch 秒。",
    },
    "catalog_talents": {
        "id": "天赋 ID。",
        "name": "天赋名称，全局唯一。",
        "rarity": "稀有度。",
        "description": "天赋描述。",
        "attribute_mods": "0-10 属性尺度下的属性修正 JSONB。",
        "tags": "故事/规则标签 JSONB。",
        "created_at": "创建时间，Unix epoch 秒。",
    },
    "catalog_family_backgrounds": {
        "id": "家世 ID。",
        "name": "家世名称，全局唯一。",
        "rarity": "稀有度。",
        "description": "家世描述。",
        "initial_resources": "初始资源 JSONB。",
        "initial_risks": "初始风险 JSONB。",
        "story_tags": "故事标签 JSONB。",
        "created_at": "创建时间，Unix epoch 秒。",
    },
    "catalog_spirit_roots": {
        "id": "灵根 ID。",
        "name": "灵根名称，全局唯一。",
        "element": "灵根元素。",
        "grade": "灵根品级。",
        "cultivation_bonus": "修炼效率加成。",
        "breakthrough_bonus": "突破概率加成。",
        "cultivation_tendency": "修炼倾向描述。",
        "event_tags": "事件标签 JSONB。",
        "created_at": "创建时间，Unix epoch 秒。",
    },
    "catalog_difficulties": {
        "id": "难度 ID。",
        "name": "难度名称，全局唯一。",
        "risk_multiplier": "风险倍率。",
        "reward_multiplier": "奖励倍率。",
        "lifespan_modifier": "寿元倍率/修正。",
        "luck_modifier": "气运修正，使用 0-10 属性尺度的兼容值。",
        "description": "难度描述。",
        "created_at": "创建时间，Unix epoch 秒。",
    },
    "catalog_story_seeds": {
        "id": "故事种子 ID。",
        "name": "故事种子名称。",
        "category": "故事种子分类。",
        "description": "故事种子描述。",
        "tags": "故事标签 JSONB。",
        "created_at": "创建时间，Unix epoch 秒。",
    },
    "run_achievements": {
        "id": "成就记录 UUID。",
        "user_id": "所属用户 ID。",
        "session_id": "来源会话 ID。",
        "achievement_key": "成就稳定键。",
        "achievement_name": "成就展示名称。",
        "description": "成就描述。",
        "death_cause": "触发结局/死亡原因。",
        "achieved_at": "获得时间，Unix epoch 秒。",
    },
    "account_rewards": {
        "id": "奖励记录 UUID。",
        "user_id": "所属用户 ID。",
        "reward_type": "奖励类型。",
        "reward_value": "奖励值。",
        "label": "奖励展示文本。",
        "source_session_id": "来源会话 ID。",
        "granted_at": "发放时间，Unix epoch 秒。",
    },
    "legacy_bonuses": {
        "id": "传承加成记录 UUID。",
        "user_id": "所属用户 ID。",
        "bonus_type": "传承加成类型。",
        "bonus_value": "传承加成值。",
        "label": "传承加成展示文本。",
        "runs_remaining": "剩余可生效局数。",
        "source_session_id": "来源会话 ID。",
        "granted_at": "发放时间，Unix epoch 秒。",
    },
    "game_runs": {
        "id": "终局汇总 ID；通常使用来源 session_id。",
        "user_id": "所属用户 ID。",
        "session_id": "来源会话 ID。",
        "char_name": "角色名。",
        "realm": "终局境界。",
        "death_cause": "死亡/结束原因。",
        "ascended": "是否飞升。",
        "turn_count": "终局累计回合数。",
        "finished_at": "结束时间，Unix epoch 秒。",
    },
    "game_turns": {
        "id": "回合记录 UUID。",
        "run_id": "回合分组 ID；当前等于 session_id，用于局中连续回合遥测。",
        "turn_no": "回合序号，从 1 递增。",
        "start_age": "本回合开始年龄。",
        "elapsed_years": "本回合经过年数。",
        "end_age": "本回合结束年龄。",
        "lifespan": "当前总寿元。",
        "remaining_lifespan": "当前剩余寿元。",
        "choice_taken": "玩家本回合选择文本。",
        "choices": "本回合可选项 JSONB。",
        "state_delta": "本回合权威状态增量 JSONB。",
        "state_after": "本回合结算后的权威状态快照 JSONB。",
        "calendar_summary": "编年史式回合摘要。",
        "narrative": "玩家可见叙事文本。",
        "event_kind": "回合/选项事件分类。",
        "end_reason": "若本回合结束游戏，记录结束原因。",
        "created_at": "记录创建时间，数据库 timestamptz。",
    },
    "player_progress": {
        "user_id": "所属用户 ID，也是主键。",
        "runs_completed": "已完成局数。",
        "ascension_count": "已飞升次数。",
        "updated_at": "更新时间，Unix epoch 秒。",
    },
}


def upgrade() -> None:
    for table, comment in TABLE_COMMENTS.items():
        op.execute(_comment_on_table_sql(table, comment))
    for table, columns in COLUMN_COMMENTS.items():
        for column, comment in columns.items():
            op.execute(_comment_on_column_sql(table, column, comment))


def downgrade() -> None:
    for table, columns in COLUMN_COMMENTS.items():
        for column in columns:
            op.execute(_comment_on_column_sql(table, column, None))
    for table in TABLE_COMMENTS:
        op.execute(_comment_on_table_sql(table, None))


def comment_sql_statements() -> tuple[str, ...]:
    """Return idempotent COMMENT statements for local/test auto-DDL."""
    statements: list[str] = []
    for table, comment in TABLE_COMMENTS.items():
        statements.append(_comment_on_table_sql(table, comment))
    for table, columns in COLUMN_COMMENTS.items():
        for column, comment in columns.items():
            statements.append(_comment_on_column_sql(table, column, comment))
    return tuple(statements)


def _comment_on_table_sql(table: str, comment: str | None) -> str:
    return f"COMMENT ON TABLE {table} IS {_literal(comment)}"


def _comment_on_column_sql(table: str, column: str, comment: str | None) -> str:
    return f"COMMENT ON COLUMN {table}.{column} IS {_literal(comment)}"


def _literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"
