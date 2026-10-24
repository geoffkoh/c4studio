import { expect, test, type Page } from "@playwright/test";

/**
 * Re-routing a Step / Smooth step line by dragging a segment (PP-196).
 *
 * The interaction is a whiteboard elbow connector's: a hovered line shows
 * a handle on each straight run, and dragging one slides that run sideways
 * while its neighbours stretch. What matters, and what `tsc` cannot see:
 * the line stays orthogonal, the run actually moves, the saved layout says
 * so, and the edge keeps its route when another line style is picked.
 *
 * Layout writes are answered here rather than reaching the server, which
 * serves `samples/` — the developer's working copy.
 */
type Saved = { waypoints?: Record<string, unknown>; routing?: Record<string, string> };

async function open(page: Page): Promise<Saved[]> {
  const saves: Saved[] = [];
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    if (route.request().url().endsWith("/layout")) {
      saves.push(route.request().postDataJSON() as Saved);
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  // Hover emphasis on (its default), deliberately: the hovered edge is
  // raised into another layer, so dragging off the line remounts it —
  // which once ended every drag after its first few pixels.
  await page.addInitScript(() => {
    window.localStorage.removeItem("c4studio.edgeStyle");
    window.localStorage.removeItem("c4studio.hoverEmphasis");
  });
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("logistics_network.dsl");
  await page
    .getByRole("button", { name: "logistics_network.dsl", exact: true })
    .click();
  await page
    .getByRole("button", { name: /Delivery Platform – Containers/ })
    .click();
  await expect(
    page.locator(".react-flow__node", {
      hasText: /^Delivery Platform – Containers$/,
    }),
  ).toBeVisible({ timeout: 20_000 });
  return saves;
}

/** The points of an edge's drawn path (corners only for sharp steps). */
async function pathPoints(page: Page, edgeId: string): Promise<number[][]> {
  const d = await page.locator(`[id="${edgeId}"]`).getAttribute("d");
  return [...(d ?? "").matchAll(/([-\d.]+),([-\d.]+)/g)].map((m) => [
    Number(m[1]),
    Number(m[2]),
  ]);
}

/**
 * Wait until no edge path changes for a while. Just after a view opens, a
 * late re-fetch of the same view tweens every node for ~320ms; a handle
 * located during it has moved (or been replaced) by the time it is
 * grabbed, and a "before" path read during it differs from "after" with
 * no drag at all. Both happened, intermittently, before this wait.
 */
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

const orthogonal = (points: number[][]) =>
  points.every(
    (p, i) => i === 0 || p[0] === points[i - 1][0] || p[1] === points[i - 1][1],
  );

/**
 * A horizontal-run handle that is really on top at its own centre — what
 * a person can see and grab. On a crowded diagram another relationship's
 * label or a node can sit over a handle, and which one varies with the
 * layout; picking blindly made the drag miss intermittently.
 */
async function grabbable(page: Page) {
  await expect(page.locator(".edge-segment-handle--h").first()).toBeAttached();
  const index = await page.evaluate(() => {
    const handles = [...document.querySelectorAll(".edge-segment-handle--h")];
    return handles.findIndex((el) => {
      const box = el.getBoundingClientRect();
      const top = document.elementFromPoint(
        box.x + box.width / 2,
        box.y + box.height / 2,
      );
      return top === el;
    });
  });
  expect(index, "no uncovered horizontal handle").toBeGreaterThanOrEqual(0);
  const handle = page.locator(".edge-segment-handle--h").nth(index);
  const edgeId = await handle.evaluate(
    (el) =>
      el.closest(".react-flow__edge")?.querySelector(".react-flow__edge-path")
        ?.id ?? "",
  );
  return { handle, edgeId };
}

test.describe("re-routing", () => {
  test("a curved style has no segment handles", async ({ page }) => {
    await open(page);
    await expect(page.locator(".edge-segment-handle")).toHaveCount(0);
  });

  test("dragging a run moves it, stays orthogonal, and is saved", async ({
    page,
  }) => {
    const saves = await open(page);
    await page.getByRole("button", { name: "Step", exact: true }).click();
    await settled(page);
    const { handle, edgeId } = await grabbable(page);
    expect(orthogonal(await pathPoints(page, edgeId))).toBe(true);
    const before = await pathPoints(page, edgeId);

    const box = (await handle.boundingBox())!;
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x, y + 40, { steps: 5 });
    await page.mouse.move(x, y + 80, { steps: 5 });
    await page.mouse.up();

    const after = await pathPoints(page, edgeId);
    expect(after).not.toEqual(before);
    expect(orthogonal(after)).toBe(true);

    await expect.poll(() => saves.length).toBeGreaterThan(0);
    const last = saves[saves.length - 1];
    expect(last.routing?.[edgeId]).toBe("orthogonal");
    expect((last.waypoints?.[edgeId] as unknown[]).length).toBeGreaterThan(0);
  });

  test("a re-routed edge keeps its route in a curved style, until reset", async ({
    page,
  }) => {
    const saves = await open(page);
    await page.getByRole("button", { name: "Step", exact: true }).click();
    await settled(page);
    const { handle, edgeId } = await grabbable(page);
    const box = (await handle.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2, box.y + 60, { steps: 5 });
    await page.mouse.up();

    await page.getByRole("button", { name: "Bezier" }).click();
    // Others curve again (a bezier path has a `C`); this one does not.
    await expect
      .poll(() =>
        page
          .locator(".react-flow__edge-path")
          .evaluateAll(
            (paths) => paths.filter((p) => /C/.test(p.getAttribute("d") ?? "")).length,
          ),
      )
      .toBeGreaterThan(0);
    expect(await page.locator(`[id="${edgeId}"]`).getAttribute("d")).not.toMatch(/C/);
    expect(orthogonal(await pathPoints(page, edgeId))).toBe(true);

    // Right-click the line itself; the event bubbles to React Flow's edge.
    await page.locator(`[id="${edgeId}"]`).dispatchEvent("contextmenu", {
      button: 2,
    });
    await page.getByRole("menuitem", { name: "Reset route" }).click();
    await expect(page.locator(`[id="${edgeId}"]`)).toHaveAttribute("d", /C/);
    await expect
      .poll(() => saves[saves.length - 1]?.routing?.[edgeId])
      .toBeUndefined();
  });
});
