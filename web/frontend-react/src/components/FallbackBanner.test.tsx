import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FallbackBanner } from "./FallbackBanner";
import type { Session } from "../lib/api";

const session = {
  session_id: "s1",
  version: 2,
  user_id: "u1",
  turn_count: 1,
  game_started: true,
  game_over: false,
  finale: false,
  choices: ["A", "B", "C", "D"],
  fallback_prompt: { active: true, text: "模型暂不可用，已切换本地故事，请直接选择下方选项继续。" },
  character: {},
  world: {},
  events: [],
} satisfies Session;

describe("FallbackBanner", () => {
  it("does not expose the obsolete no-op continue action", async () => {
    const runTurn = vi.fn().mockResolvedValue(undefined);
    render(<FallbackBanner session={session} busy={false} runTurn={runTurn} />);

    expect(screen.queryByRole("button", { name: "继续本局" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "结束本局" }));
    expect(runTurn).toHaveBeenCalledWith(
      "/api/sessions/s1/end",
      { reason: "玩家结束本局。" },
    );
  });
});
