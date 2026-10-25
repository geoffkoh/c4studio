import { expect, test, type Page } from "@playwright/test";

/**
 * Marching ants on the hovered element's relationships (PP-195).
 *
 * The rule under test is a join the type checker cannot see: the toolbar
 * toggle, the node under the pointer, and which edge paths actually carry
 * a running CSS animation. The expected set comes from the API's own
 * edge list, so the assertion is "exactly the edges touching this node",
 * not "some edges moved".
 */
const VIEW = "PlatformContainers";

async function openContainers(page: Page) {
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
  // Wait for *this* view's title on the canvas, not just a legend: the
  // default view (the landscape) loads first and has a legend too, so
  // waiting on the legend alone passed before this view arrived, and the
  // hover then hunted for a node that was not on screen (seen in CI).
  await expect(
    page.locator(".react-flow__node", {
      hasText: /^Delivery Platform – Containers$/,
    }),
  ).toBeVisible({ timeout: 20_000 });
  await page.getByRole("searchbox", { name: "Search files" }).fill("");
}

/** Edge ids whose path is running the march keyframes right now. */
/** The Animate toggle, which lives in the toolbar's View menu (PP-206). */
async function animateToggle(page: Page) {
  await page.getByRole("button", { name: "View ▾" }).click();
  return page.getByRole("group", { name: "View" }).getByRole("button", { name: "Animate" });
}

async function marchingIds(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll<SVGPathElement>(".react-flow__edge-path")]
      .filter((path) => getComputedStyle(path).animationName === "edge-march")
      .map((path) => path.id)
      .sort(),
  );
}

/** The leaf element with the most relationships, and those relationships. */
async function busiestElement(page: Page) {
  const response = await page.request.get(`/api/views/${VIEW}/graph`);
  const graph = (await response.json()) as {
    nodes: { id: string; parentId?: string }[];
    edges: { id: string; source: string; target: string }[];
  };
  const parents = new Set(graph.nodes.map((n) => n.parentId).filter(Boolean));
  let best = { id: "", edges: [] as string[] };
  for (const node of graph.nodes) {
    if (parents.has(node.id)) continue;
    const touching = graph.edges
      .filter((e) => e.source === node.id || e.target === node.id)
      .map((e) => e.id);
    if (touching.length > best.edges.length) best = { id: node.id, edges: touching };
  }
  return { ...best, total: graph.edges.length, edges: best.edges.sort() };
}

test.describe("marching ants", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1500, height: 950 });
    // Each test starts from the stored default: off.
    await page.addInitScript(() =>
      window.localStorage.removeItem("c4studio.animateEdges"),
    );
  });

  test("off by default: hovering an element animates nothing", async ({
    page,
  }) => {
    await openContainers(page);
    const busiest = await busiestElement(page);
    await page.locator(`.react-flow__node[data-id="${busiest.id}"]`).hover();
    expect(await marchingIds(page)).toEqual([]);
  });

  test("on: exactly the hovered element's relationships march", async ({
    page,
  }) => {
    await openContainers(page);
    const busiest = await busiestElement(page);
    // A node touching every edge could not tell "these" from "all".
    expect(busiest.edges.length).toBeGreaterThan(0);
    expect(busiest.edges.length).toBeLessThan(busiest.total);

    const toggle = await animateToggle(page);
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    // Closed again, so the menu cannot be what the pointer lands on.
    await page.keyboard.press("Escape");

    await page.locator(`.react-flow__node[data-id="${busiest.id}"]`).hover();
    await expect.poll(() => marchingIds(page)).toEqual(busiest.edges);

    // Leaving the node stops them.
    await page.mouse.move(5, 5);
    await expect.poll(() => marchingIds(page)).toEqual([]);
  });

  test("the `a` key toggles it, and the choice is remembered", async ({
    page,
  }) => {
    await openContainers(page);
    await page.locator(".react-flow__pane").click();
    await page.keyboard.press("a");
    const toggle = await animateToggle(page);
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(
      await page.evaluate(() => localStorage.getItem("c4studio.animateEdges")),
    ).toBe("on");
  });

  test("reduced motion stops the animation", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openContainers(page);
    const busiest = await busiestElement(page);
    await (await animateToggle(page)).click();
    await page.keyboard.press("Escape");
    await page.locator(`.react-flow__node[data-id="${busiest.id}"]`).hover();
    // The class is applied (the hover registered) but nothing runs.
    await expect(page.locator(".react-flow__edge.edge--marching")).toHaveCount(
      busiest.edges.length,
    );
    expect(await marchingIds(page)).toEqual([]);
  });
});
