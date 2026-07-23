import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { GamePage } from "./GamePage";
import type { Session } from "../lib/api";

const session = {
  session_id: "s1",
  version: 3,
  user_id: "u1",
  guest: false,
  turn_count: 2,
  game_started: true,
  game_over: false,
  finale: false,
  choices: ["【稳妥】静心修炼", "【机遇】外出寻机", "【风险】探查险地", "【气运】随缘而行"],
  fallback_prompt: { active: false, text: "" },
  character: {
    name: "许满",
    realm: "练气",
    realm_stage: 1,
    age: 18,
    lifespan: 100,
    remaining_lifespan: 82,
    luck: "平稳",
  },
  world: { current_scene: "山门", day_count: 3 },
  events: [{ type: "narrative", text: "你来到山门。", age: 16, turn: 0 }],
} satisfies Session;

describe("GamePage toolbar", () => {
  it("keeps reachable, labelled icon buttons and fixed-semantic choices", () => {
    render(
      <GamePage
        session={session}
        busy={false}
        runTurn={vi.fn().mockResolvedValue(undefined)}
        openDialog={vi.fn()}
        onHome={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("返回首页")).toBeInTheDocument();
    expect(screen.getByLabelText("存档")).toBeInTheDocument();
    expect(screen.getByLabelText("设置")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "A：静心修炼" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "B：外出寻机" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "C：探查险地" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "D：随缘而行" })).toBeInTheDocument();
  });

  it("routes the save and settings entries through the existing handlers", async () => {
    const openDialog = vi.fn();
    const onHome = vi.fn();
    render(
      <GamePage
        session={session}
        busy={false}
        runTurn={vi.fn().mockResolvedValue(undefined)}
        openDialog={openDialog}
        onHome={onHome}
      />,
    );

    await userEvent.click(screen.getByLabelText("存档"));
    expect(openDialog).toHaveBeenCalledWith("saves");
    await userEvent.click(screen.getByLabelText("设置"));
    expect(openDialog).toHaveBeenCalledWith("settings");
    await userEvent.click(screen.getByLabelText("返回首页"));
    expect(onHome).toHaveBeenCalled();
  });

  it.each([
    [84, 66],
    [100, 82],
    [120, 102],
  ])("uses the authoritative lifespan cap of %i", (lifespan, remainingLifespan) => {
    render(
      <GamePage
        session={{
          ...session,
          character: { ...session.character, lifespan, remaining_lifespan: remainingLifespan },
        }}
        busy={false}
        runTurn={vi.fn().mockResolvedValue(undefined)}
        openDialog={vi.fn()}
        onHome={vi.fn()}
      />,
    );

    expect(screen.getByRole("meter", { name: "寿元" })).toHaveAttribute("aria-valuemax", String(lifespan));
  });

  it("falls back to the realm cap only when the authoritative lifespan is invalid", () => {
    render(
      <GamePage
        session={{
          ...session,
          character: { ...session.character, lifespan: 0, remaining_lifespan: 82 },
        }}
        busy={false}
        runTurn={vi.fn().mockResolvedValue(undefined)}
        openDialog={vi.fn()}
        onHome={vi.fn()}
      />,
    );

    expect(screen.getByRole("meter", { name: "寿元" })).toHaveAttribute("aria-valuemax", "100");
  });
});
