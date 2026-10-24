import { expect, test, type Page } from "@playwright/test";

/**
 * Adding steps to an orthogonal line, and pinning the side of a node it
 * attaches to (PP-201) — the follow-up to segment dragging (PP-196).
 *
 * Double-clicking a run splits it into a jog; right-click offers the same
 * as "Add step here". Each end of the line has a handle that, dragged
 * onto the element, snaps to its nearest side and stays pinned there.
 *
 * Layout writes are answered here: the server serves `samples/`.
 */
type Saved = {
  waypoints?: Record<string, number[][]>;
  routing?: Record<string, string>;
  sides?: Record<string, { source?: string; target?: string }>;
};

const VIEW = "PlatformContainers";

async function open(page: Page): Promise<Saved[]> {
  const saves: Saved[] = [];
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    if (route.request().url().endsWith("/layout")) {
      saves.push(route.request().postDataJSON() as Saved);
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("c4studio.edgeStyle", "step");
    window.localStorage.removeItem("c4studio.hoverEmphasis");
  });
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  await expect(
    page.locator(".react-flow__node", { hasText: /^Delivery Platform – Containers$/ }),
  ).toBeVisible({ timeout: 20_000 });
  await settled(page);
  return saves;
}

/** Wait until no edge path changes for a while (see rerouting.spec.ts). */
async function settled(page: Page) {
  const snapshot = () =>
    page
      .locator(".react-flow__edge-path")
      .evaluateAll((paths) => paths.map((p) => p.getAttribute("d")).join("|"));
  let previous = "";
  await expect
    .poll(
      async () => {
        const now = await snapshot();
        const stable = now === previous && now !== "";
        previous = now;
        return stable;
      },
      { intervals: [200], timeout: 10_000 },
    )
    .toBe(true);
}

async function pathPoints(page: Page, edgeId: string): Promise<number[][]> {
  const d = await page.locator(`[id="${edgeId}"]`).getAttribute("d");
  return [...(d ?? "").matchAll(/([-\d.]+),([-\d.]+)/g)].map((m) => [
    Number(m[1]),
    Number(m[2]),
  ]);
}

const orthogonal = (points: number[][]) =>
  points.every(
    (p, i) => i === 0 || p[0] === points[i - 1][0] || p[1] === points[i - 1][1],
  );

/**
 * An element of `selector` that is really on top at its own centre —
 * one a person could grab. Returns its index, or -1.
 */
async function uncovered(page: Page, selector: string): Promise<number> {
  return page.evaluate((sel) => {
    return [...document.querySelectorAll(sel)].findIndex((el) => {
      const box = el.getBoundingClientRect();
      return (
        document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2) === el
      );
    });
  }, selector);
}

/** A horizontal run's handle a person could grab, and its edge's id. */
async function grabbableRun(page: Page) {
  const index = await uncovered(page, ".edge-segment-handle--h");
  expect(index, "no uncovered horizontal handle").toBeGreaterThanOrEqual(0);
  const handle = page.locator(".edge-segment-handle--h").nth(index);
  const edgeId = await handle.evaluate(
    (el) =>
      el.closest(".react-flow__edge")?.querySelector(".react-flow__edge-path")?.id ?? "",
  );
  return { handle, edgeId };
}

const viewport = (page: Page) =>
  page.locator(".react-flow__viewport").getAttribute("style");

test.describe("route steps and sides", () => {
  test("double-clicking a run adds a step, without zooming", async ({ page }) => {
    const saves = await open(page);
    const { handle, edgeId } = await grabbableRun(page);
    const before = await pathPoints(page, edgeId);
    const zoomBefore = await viewport(page);

    // Beside the handle, on the line itself, not on the handle.
    const box = (await handle.boundingBox())!;
    await page.mouse.dblclick(box.x - 12, box.y + box.height / 2);

    await expect.poll(async () => (await pathPoints(page, edgeId)).length).toBe(before.length + 2);
    expect(orthogonal(await pathPoints(page, edgeId))).toBe(true);
    expect(await viewport(page)).toBe(zoomBefore);
    await expect.poll(() => saves.length).toBeGreaterThan(0);
    const last = saves[saves.length - 1];
    expect(last.routing?.[edgeId]).toBe("orthogonal");
    expect(last.waypoints?.[edgeId]?.length).toBeGreaterThanOrEqual(2);
  });

  test("right-click offers Add step here", async ({ page }) => {
    await open(page);
    const { handle, edgeId } = await grabbableRun(page);
    const before = await pathPoints(page, edgeId);
    const box = (await handle.boundingBox())!;
    await page.mouse.click(box.x - 12, box.y + box.height / 2, { button: "right" });
    await page.getByRole("menuitem", { name: "Add step here" }).click();
    await expect.poll(async () => (await pathPoints(page, edgeId)).length).toBe(before.length + 2);
  });

  test("dragging an end onto another side pins it there, until reset", async ({ page }) => {
    const saves = await open(page);
    const graph = await (await page.request.get(`/api/views/${VIEW}/graph`)).json();
    const sources = new Map<string, string>(
      graph.edges.map((e: { id: string; source: string }) => [e.id, e.source]),
    );

    const index = await uncovered(page, '.edge-end-handle[data-end="source"]');
    expect(index, "no uncovered end handle").toBeGreaterThanOrEqual(0);
    const handle = page.locator('.edge-end-handle[data-end="source"]').nth(index);
    const edgeId = await handle.evaluate(
      (el) =>
        el.closest(".react-flow__edge")?.querySelector(".react-flow__edge-path")?.id ?? "",
    );
    const node = page.locator(`.react-flow__node[data-id="${sources.get(edgeId)}"]`);
    const nodeBox = (await node.boundingBox())!;
    const start = (await pathPoints(page, edgeId))[0];

    // Whichever side it does not leave from now: top, unless it already
    // leaves the top (its handle, just outside the node, is above it).
    const hb = (await handle.boundingBox())!;
    const side = hb.y + hb.height / 2 < nodeBox.y ? "bottom" : "top";
    const aim = {
      x: nodeBox.x + nodeBox.width / 2,
      y: side === "top" ? nodeBox.y - 4 : nodeBox.y + nodeBox.height + 4,
    };

    await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
    await page.mouse.down();
    await page.mouse.move(aim.x, aim.y, { steps: 8 });
    await page.mouse.up();

    await expect.poll(() => saves[saves.length - 1]?.sides?.[edgeId]?.source).toBe(side);
    expect(saves[saves.length - 1].routing?.[edgeId]).toBe("orthogonal");
    const after = await pathPoints(page, edgeId);
    expect(after[0]).not.toEqual(start);
    expect(orthogonal(after)).toBe(true);
    // The route now leaves square-on out of that side: its first run is
    // vertical, heading away from the node.
    expect(after[1][0]).toBe(after[0][0]);
    expect(side === "top" ? after[1][1] < after[0][1] : after[1][1] > after[0][1]).toBe(true);

    await page.locator(`[id="${edgeId}"]`).dispatchEvent("contextmenu", { button: 2 });
    await page.getByRole("menuitem", { name: "Reset route" }).click();
    await expect.poll(() => saves[saves.length - 1]?.sides?.[edgeId]).toBeUndefined();
  });
});
