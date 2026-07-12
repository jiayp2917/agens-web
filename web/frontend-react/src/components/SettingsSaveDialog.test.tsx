import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { Session, User } from "../lib/api";
import { SettingsSaveDialog } from "./SettingsSaveDialog";

const session: Session = {
  session_id: "s1",
  version: 3,
  user_id: "u1",
  guest: false,
  turn_count: 2,
  game_started: true,
  game_over: false,
  finale: false,
  choices: ["稳妥", "机遇", "风险", "气运"],
  character: { name: "许满", realm: "练气", realm_stage: 1, age: 18, lifespan: 100 },
  world: { current_scene: "山门" },
  events: [],
};

const user: User = { id: "u1", username: "tester", is_admin: false };

it("refreshes a stale session and reports a recoverable save conflict", async () => {
  const refreshed = { ...session, version: 4 };
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/api/saves") return Promise.resolve(new Response("[]", { status: 200 }));
    if (path === "/api/settings/model") {
      return Promise.resolve(new Response(JSON.stringify({
        provider: "Agens",
        base_url: "",
        model: "test",
        api_key_set: false,
        api_key_masked: "",
        source: "system",
      }), { status: 200 }));
    }
    if (path === "/api/sessions/s1/save") {
      return Promise.resolve(new Response(JSON.stringify({ detail: "局面已更新" }), { status: 409 }));
    }
    if (path === "/api/sessions/s1") {
      return Promise.resolve(new Response(JSON.stringify(refreshed), { status: 200 }));
    }
    throw new Error(`unexpected request: ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const setSession = vi.fn();
  render(
    <SettingsSaveDialog
      mode="saves"
      session={session}
      user={user}
      onClose={vi.fn()}
      setSession={setSession}
      setView={vi.fn()}
      onAuth={vi.fn()}
    />,
  );

  await userEvent.click(await screen.findAllByRole("button", { name: "保存到此档" }).then((items) => items[0]));

  expect(await screen.findByRole("status")).toHaveTextContent("已加载最新进度，请再次存档");
  expect(setSession).toHaveBeenCalledWith(refreshed);
});
