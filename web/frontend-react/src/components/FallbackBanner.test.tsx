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
  fallback_prompt: { active: false, text: "模型暂不可用，请选择处理方式。" },
  pending_model_failure: { failure_id: "f1", stage: "turn", request_no: 1, slot: "A", status: "pending", error_code: "incomplete_output" },
  character: {},
  world: {},
  events: [],
} satisfies Session;

describe("FallbackBanner", () => {
  it("resolves a pending failure through explicit player actions", async () => {
    const runTurn = vi.fn().mockResolvedValue(undefined);
    render(<FallbackBanner session={session} busy={false} runTurn={runTurn} />);

    await userEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(runTurn).toHaveBeenCalledWith(
      "/api/sessions/s1/action",
      { action: "retry_model" },
    );
    await userEvent.click(screen.getByRole("button", { name: "结束本局" }));
    expect(runTurn).toHaveBeenCalledWith(
      "/api/sessions/s1/action",
      { action: "end_model_failure" },
    );
  });
});
