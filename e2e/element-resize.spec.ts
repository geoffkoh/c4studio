import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

/**
 * Resizing an element's box (PP-224). Only boundaries used to have
 * handles; an element now shows them when selected, and its size is saved
 * with the layout — for the boxes that were resized, and no others, so
 * the rest keep growing to fit their text.
 *
 * Layout writes are answered here: the server serves `samples/`.
 */
type Saved = { positions: Record<string, number[]>; sizes?: Record<string, number[]> };

async function open(page: Page): Promise<Saved[]> {
  const saves: Saved[] = [];
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    if (route.request().url().endsWith("/layout")) {
      saves.push(route.request().postDataJSON() as Saved);
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("ecommerce_platform.dsl");
  await page.getByRole("button", { name: "ecommerce_platform.dsl", exact: true }).click();
  await page.getByRole("button", { name: /^E-Commerce – Containers container$/ }).click();
  await expect(page.locator(".react-flow__node-element").first()).toBeVisible({
    timeout: 20_000,
  });
  // Let a same-view tween settle before measuring.
  await page.waitForTimeout(800);
  return saves;
}

/** A box with a description, selected so its handles show. */
async function selectBox(page: Page): Promise<string> {
  const node = page
    .locator(".react-flow__node-element", { has: page.locator(".node__desc") })
    .filter({ hasNot: page.locator(".person") })
    .first();
  const id = (await node.getAttribute("data-id"))!;
  await node.locator(".node__label").click();
  await expect(node.locator(".node-resize__handle").first()).toBeVisible();
  return id;
}

/** Drag the box's bottom-right handle by (dx, dy) screen pixels. */
async function dragCorner(page: Page, id: string, dx: number, dy: number) {
  const handle = page.locator(
    `.react-flow__node[data-id="${id}"] .node-resize__handle.bottom.right`,
  );
  const box = (await handle.boundingBox())!;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx / 2, y + dy / 2, { steps: 5 });
  await page.mouse.move(x + dx, y + dy, { steps: 5 });
  await page.mouse.up();
}

/** Wait for the save a resize makes; selecting the box saves one too. */
async function resizeSaved(saves: Saved[], id: string) {
  await expect.poll(() => saves.at(-1)?.sizes?.[id]).toBeDefined();
}

test("a resized box is saved at its new size, and no other box is", async ({ page }) => {
  const saves = await open(page);
  const id = await selectBox(page);
  const node = page.locator(`.react-flow__node[data-id="${id}"]`);
  const before = (await node.locator(".node").boundingBox())!;

  await dragCorner(page, id, 120, 60);
  await resizeSaved(saves, id);
  const sizes = saves.at(-1)!.sizes ?? {};
  const elementIds = await page
    .locator(".react-flow__node-element")
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-id")!));
  expect(Object.keys(sizes).filter((key) => elementIds.includes(key))).toEqual([id]);

  // The drawn box, not only React Flow's wrapper, took the new size.
  const after = (await node.locator(".node").boundingBox())!;
  expect(after.width).toBeGreaterThan(before.width + 60);
  expect(after.height).toBeGreaterThan(before.height + 30);
  const zoom = after.width / sizes[id][0];
  expect(after.height / zoom).toBeCloseTo(sizes[id][1], 0);
});

test("a box cannot be made smaller than its own text", async ({ page }) => {
  const saves = await open(page);
  const id = await selectBox(page);
  await dragCorner(page, id, -400, -400);
  await resizeSaved(saves, id);
  const [width, height] = saves.at(-1)!.sizes![id];
  expect(width).toBeGreaterThanOrEqual(100);

  // Narrower, so the text wraps tighter, and the box still holds all of
  // it: past four lines a description ends in "…" as it does in any box,
  // but nothing is cut off by the box's edge. (Not `scrollHeight`: the
  // connection handles stick out of every box by design.)
  const node = page.locator(`.react-flow__node[data-id="${id}"] .node`);
  const outer = (await node.boundingBox())!;
  const desc = (await node.locator(".node__desc").boundingBox())!;
  expect(desc.y + desc.height).toBeLessThanOrEqual(outer.y + outer.height);
  // And it did get narrower: the floor is the text's, not the old box's.
  expect(width).toBeLessThan(200);
  expect(height).toBeGreaterThan(0);
});

test("an export leaves a selected box's resize handles out", async ({ page }) => {
  await open(page);
  await selectBox(page);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export ▾" }).click();
  await page.getByRole("button", { name: "SVG", exact: true }).click();
  const svg = readFileSync((await (await download).path())!).toString("utf-8");
  expect(svg).toContain("react-flow__node-element");
  expect(svg).not.toContain("node-resize__handle");
  // On screen they are still there.
  await expect(page.locator(".node-resize__handle").first()).toBeVisible();
});
