import { describe, expect, it } from "vitest";
import { isReadableEvent } from "./util";

describe("isReadableEvent", () => {
  it("keeps system info messages out of the player chronicle", () => {
    expect(isReadableEvent({ type: "info", text: "修为精进，已至筑基初期。" })).toBe(false);
    expect(isReadableEvent({ type: "narrative", text: "山门外的风声已传入洞府。" })).toBe(true);
  });
});
