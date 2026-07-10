import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useDialogA11y } from "./useDialogA11y";

function Dialog({ onClose }: { onClose: () => void }) {
  const { scrimRef, onScrimClick } = useDialogA11y(onClose);
  return (
    <div ref={scrimRef} onClick={onScrimClick} role="dialog" aria-modal="true">
      <button>第一个</button>
      <button>最后一个</button>
    </div>
  );
}

describe("useDialogA11y", () => {
  it("traps tab focus and closes on Escape", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<Dialog onClose={onClose} />);
    const first = screen.getByRole("button", { name: "第一个" });
    const last = screen.getByRole("button", { name: "最后一个" });

    expect(first).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
    await user.tab();
    expect(first).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });
});
