const assert = require("node:assert/strict");
const test = require("node:test");
const { displayedChoiceText } = require("./local_visible_playtest.cjs");

test("normalizes unpunctuated slot prefixes like the game page", () => {
  assert.deepEqual(
    ["A继续温养根基", "B拜访知情修士", "C追查传闻地点", "D随缘听旧签"].map(displayedChoiceText),
    ["继续温养根基", "拜访知情修士", "追查传闻地点", "随缘听旧签"],
  );
});
