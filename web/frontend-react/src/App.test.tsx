import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./main";
import type { Session } from "./lib/api";

const activeSession = {
  session_id: "s1",
  version: 3,
  user_id: "u1",
  guest: false,
  turn_count: 2,
  game_started: true,
  game_over: false,
  finale: false,
  choices: ["稳住气息", "寻找机缘", "探查险地", "随缘而行"],
  fallback_prompt: { active: false, text: "" },
  character: { name: "许满", realm: "练气", realm_stage: 1, age: 18, lifespan: 100 },
  world: { current_scene: "山门", day_count: 3 },
  events: [{ type: "narrative", text: "你来到山门。", age: 16, turn: 0 }],
} satisfies Session;

describe("App session mutations", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("blocks a second click while the first mutation is in flight", async () => {
    localStorage.setItem("agens-web.active-session-id", "s1");
    let resolveChoice: ((response: Response) => void) | undefined;
    const pendingChoice = new Promise<Response>((resolve) => {
      resolveChoice = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/auth/me") return Promise.resolve(new Response("{}", { status: 401 }));
      if (path === "/api/sessions/s1") {
        return Promise.resolve(new Response(JSON.stringify(activeSession), { status: 200 }));
      }
      if (path === "/api/sessions/s1/choice") return pendingChoice;
      throw new Error(`unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const choice = await screen.findByRole("button", { name: /A：稳住气息/ });

    await userEvent.dblClick(choice);
    expect(fetchMock.mock.calls.filter(([path]) => path === "/api/sessions/s1/choice")).toHaveLength(1);

    resolveChoice?.(new Response(JSON.stringify({ ...activeSession, version: 4, turn_count: 3 }), { status: 200 }));
    await waitFor(() => expect(screen.getByText(/回合 3/)).toBeInTheDocument());
  });

  it("refreshes the current session after a version conflict", async () => {
    localStorage.setItem("agens-web.active-session-id", "s1");
    const refreshed = { ...activeSession, version: 4, turn_count: 3 };
    let sessionReads = 0;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/auth/me") return Promise.resolve(new Response("{}", { status: 401 }));
      if (path === "/api/sessions/s1") {
        sessionReads += 1;
        const body = sessionReads === 1 ? activeSession : refreshed;
        return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
      }
      if (path === "/api/sessions/s1/choice") {
        return Promise.resolve(new Response(JSON.stringify({ detail: "局面已更新" }), { status: 409 }));
      }
      throw new Error(`unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /A：稳住气息/ }));

    await waitFor(() => expect(screen.getByText(/回合 3/)).toBeInTheDocument());
    expect(sessionReads).toBe(2);
    expect(fetchMock.mock.calls.filter(([path]) => path === "/api/sessions/s1/choice")).toHaveLength(1);
  });
});
