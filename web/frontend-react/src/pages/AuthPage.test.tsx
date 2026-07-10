import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthPage } from "./AuthPage";

describe("AuthPage", () => {
  it("hands successful authentication to the owner that clears guest state", async () => {
    const onAuthenticated = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ user: { id: "u1", username: "player", is_admin: false } }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    ));
    render(
      <AuthPage
        mode="login"
        setMode={vi.fn()}
        onAuthenticated={onAuthenticated}
        setView={vi.fn()}
        setError={vi.fn()}
      />,
    );

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("用户名"), "player");
    await user.type(screen.getByLabelText("密码"), "password-123");
    await user.click(screen.getByRole("button", { name: "登录" }));

    expect(onAuthenticated).toHaveBeenCalledWith(
      expect.objectContaining({ id: "u1", username: "player" }),
    );
  });
});
