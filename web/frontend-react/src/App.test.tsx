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

  it("deduplicates concurrent new-session creation from the home page", async () => {
    let resolveCreate: ((response: Response) => void) | undefined;
    const pendingCreate = new Promise<Response>((resolve) => {
      resolveCreate = resolve;
    });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/auth/me") return Promise.resolve(new Response("{}", { status: 401 }));
      if (path === "/api/sessions") return pendingCreate;
      throw new Error(`unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    const start = await screen.findByRole("button", { name: "新游戏" });
    await userEvent.dblClick(start);

    expect(fetchMock.mock.calls.filter(([path]) => path === "/api/sessions")).toHaveLength(1);
    expect(start).toBeDisabled();
    expect(start).toHaveAttribute("aria-busy", "true");

    resolveCreate?.(new Response(JSON.stringify({ detail: "test stop" }), { status: 500 }));
    await screen.findByRole("alert");
  });

  it("refreshes the current session after a version conflict", async () => {
    const user = userEvent.setup();
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

    const choice = await screen.findByRole("button", { name: /A：稳住气息/ });
    choice.focus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByText(/回合 3/)).toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("已加载最新进度");
    await waitFor(() => expect(screen.getByRole("button", { name: /A：稳住气息/ })).toHaveFocus());
    expect(sessionReads).toBe(2);
    expect(fetchMock.mock.calls.filter(([path]) => path === "/api/sessions/s1/choice")).toHaveLength(1);
  });

  it("shows a natural validation error instead of a structured payload", async () => {
    localStorage.setItem("agens-web.active-session-id", "s1");
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/auth/me") return Promise.resolve(new Response("{}", { status: 401 }));
      if (path === "/api/sessions/s1") {
        return Promise.resolve(new Response(JSON.stringify(activeSession), { status: 200 }));
      }
      if (path === "/api/sessions/s1/choice") {
        return Promise.resolve(new Response(JSON.stringify({ detail: [{ msg: "invalid" }] }), { status: 422 }));
      }
      throw new Error(`unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await userEvent.click(await screen.findByRole("button", { name: /A：稳住气息/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("请求参数无效。");
    expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
  });
});
