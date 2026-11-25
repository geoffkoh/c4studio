import { expect, test } from "@playwright/test";

import { panToReveal } from "../frontend/src/keepInView";

/** The icon browser's pan (PP-249), as arithmetic: no page. */
const free = { left: 0, top: 0, right: 600, bottom: 800 };

test("a box already clear of the card is left where it is", () => {
  expect(panToReveal({ left: 100, top: 100, right: 300, bottom: 200 }, free)).toBeNull();
});

test("a box under the card moves sideways into the room left, and only sideways", () => {
  const pan = panToReveal({ left: 700, top: 300, right: 900, bottom: 400 }, free);
  expect(pan).toEqual({ dx: 300 - 800, dy: 0 });
});

test("a box below the canvas comes up as well", () => {
  const pan = panToReveal({ left: 700, top: 900, right: 900, bottom: 1000 }, free);
  expect(pan).toEqual({ dx: -500, dy: 400 - 950 });
});

test("a box too big for the room is not half shown", () => {
  expect(panToReveal({ left: 700, top: 0, right: 1300, bottom: 100 }, free)).toBeNull();
  expect(panToReveal({ left: 0, top: 0, right: 100, bottom: 100 }, { ...free, right: 80 })).toBeNull();
});
