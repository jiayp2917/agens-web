import { fireEvent, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChoiceButton } from "./ChoiceButton";

describe("ChoiceButton loading state", () => {
  it("swaps the arrow slot for a spinner and disables on click", async () => {
    const onClick = vi.fn();
    const view = render(<ChoiceButton letter="A" text="稳固气息" disabled={false} onClick={onClick} />);
    const button = view.getByRole("button", { name: "A：稳固气息" });

    expect(view.container.querySelector(".choice-spinner")).toBeNull();
    expect(view.container.querySelector(".choice-arrow")).toBeInTheDocument();
    expect(button).toBeEnabled();

    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(view.container.querySelector(".choice-spinner")).toBeInTheDocument();
    expect(view.container.querySelector(".choice-arrow")).toBeNull();
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveClass("is-loading");

    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("clears the spinner once the parent clears busy", () => {
    const onClick = vi.fn();
    const view = render(<ChoiceButton letter="B" text="外出寻机" disabled={false} onClick={onClick} />);
    const button = view.getByRole("button", { name: "B：外出寻机" });

    fireEvent.click(button);
    expect(view.container.querySelector(".choice-spinner")).toBeInTheDocument();

    view.rerender(<ChoiceButton letter="B" text="外出寻机" disabled={true} onClick={onClick} />);
    expect(view.container.querySelector(".choice-spinner")).toBeInTheDocument();

    view.rerender(<ChoiceButton letter="B" text="外出寻机" disabled={false} onClick={onClick} />);
    expect(view.container.querySelector(".choice-spinner")).toBeNull();
    expect(button).toBeEnabled();
    expect(button).toHaveAttribute("aria-busy", "false");
  });
});
