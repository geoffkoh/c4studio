import { expect, test, type Page } from "@playwright/test";

/**
 * The Diagrams page's details card (PP-205).
 *
 * It opens on request — the toolbar's Details button or `i` — and then
 * follows the selection, because selecting is also how a drag starts and
 * a card thrown up by every drag would fight the page's main job. It
 * overlays the canvas rather than narrowing it, so nothing moves when it
 * opens; the geometry tests hold it clear of the toolbar and the MiniMap.
 *
 * `e2e/layout.spec.ts` masks `.graph` in its screenshots, so it cannot
 * see the card at all — these assert where it sits instead.
 *
 * Properties are added to the served graph here, so the test does not
 * depend on which sample elements carry any; layout writes are answered
 * here because the server serves `samples/`.
 */
const PROPS = { owner: "team-dispatch", runbook: "## Restart\n\n1. Drain" };
const REL_PROPS = { sla: "99.9%" };

type Payload = {
  nodes: { id: string; data: { kind: string; label: string; properties?: object } }[];
  edges: {
    id: string;
    source: string;
    target: string;
    relationship?: { description: string; technology: string; properties: object };
  }[];
};

async function open(
  page: Page,
  { width = 1440, height = 900, details = "closed" } = {},
): Promise<{ element: { id: string; label: string }; edgeIds: string[] }> {
  const found = { element: { id: "", label: "" }, edgeIds: [] as string[] };
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route(/\/api\/views\/PlatformContainers\/graph(\?.*)?$/, async (route) => {
    const response = await route.fetch();
    const data = (await response.json()) as Payload;
    // Every line that draws one relationship gets the same properties, so
    // a test can click whichever is on screen; the element is the source
    // of the first.
    const edges = data.edges.filter((e) => e.relationship);
    for (const edge of edges) edge.relationship!.properties = REL_PROPS;
    const node = data.nodes.find((n) => n.id === edges[0].source)!;
    node.data.properties = PROPS;
    found.element = { id: node.id, label: node.data.label };
    found.edgeIds = edges.map((e) => e.id);
    return route.fulfill({ response, json: data });
  });
  await page.addInitScript((state) => {
    window.localStorage.setItem("c4studio.details", state);
    window.localStorage.removeItem("c4studio.detailsHint");
    window.localStorage.removeItem("c4studio.hoverEmphasis");
  }, details);
  await page.setViewportSize({ width, height });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  await expect.poll(() => found.element.id).not.toBe("");
  await expect(page.locator(`.react-flow__node[data-id="${found.element.id}"]`)).toBeVisible({
    timeout: 20_000,
  });
  return found;
}

const card = (page: Page) => page.getByRole("complementary", { name: "Details" });
const detailsButton = (page: Page) => page.getByRole("button", { name: "Details" });

async function clickNode(page: Page, id: string) {
  await page.locator(`.react-flow__node[data-id="${id}"]`).click();
}

/**
 * Click one of `edgeIds` where the line itself is on top. Not at a fixed
 * point: the label sits mid-line and takes the click for dragging, an
 * end can be under a node or the card, and a line can be off-screen.
 */
async function clickEdge(page: Page, edgeIds: string[]) {
  const point = await page.evaluate((ids) => {
    for (const id of ids) {
      const path = document.getElementById(id) as SVGPathElement | null;
      const group = path?.closest(".react-flow__edge");
      const m = path?.getScreenCTM();
      if (!path || !group || !m) continue;
      const length = path.getTotalLength();
      for (let i = 1; i < 40; i++) {
        const p = path.getPointAtLength((length * i) / 40);
        const x = p.x * m.a + p.y * m.c + m.e;
        const y = p.x * m.b + p.y * m.d + m.f;
        const hit = document.elementFromPoint(x, y);
        if (hit && group.contains(hit) && !hit.closest("foreignObject")) return { x, y };
      }
    }
    return null;
  }, edgeIds);
  expect(point, "no line with an uncovered point").not.toBeNull();
  await page.mouse.click(point!.x, point!.y);
}

test.describe("diagram details card", () => {
  test("closed until asked for; a first click says how to open it", async ({ page }) => {
    const { element } = await open(page);
    await expect(card(page)).toHaveCount(0);
    await expect(detailsButton(page)).toHaveAttribute("aria-pressed", "false");

    await clickNode(page, element.id);
    await expect(page.getByRole("status").filter({ hasText: "for details" })).toBeVisible();
    await expect(card(page)).toHaveCount(0);

    await page.keyboard.press("i");
    await expect(card(page)).toBeVisible();
    await expect(detailsButton(page)).toHaveAttribute("aria-pressed", "true");
    expect(await page.evaluate(() => localStorage.getItem("c4studio.details"))).toBe("open");

    await page.keyboard.press("i");
    await expect(card(page)).toHaveCount(0);
  });

  test("it follows the selection: element, relationship, nothing", async ({ page }) => {
    const { element, edgeIds } = await open(page, { details: "open" });
    await expect(card(page)).toContainText("Select an element or a relationship");

    await clickNode(page, element.id);
    await expect(card(page).getByRole("heading", { level: 3 })).toHaveText(element.label);
    const props = card(page).locator(`dl[aria-label="Properties of ${element.label}"]`);
    await expect(props).toContainText("team-dispatch");
    await expect(props.locator("h2")).toHaveText("Restart");
    await expect(card(page).locator(".details__rels")).toContainText("99.9%");

    await clickEdge(page, edgeIds);
    await expect(card(page)).toContainText("[Relationship");
    await expect(card(page)).toContainText("99.9%");

    await page.locator(".react-flow__pane").click({ position: { x: 20, y: 300 } });
    await expect(card(page)).toContainText("Select an element or a relationship");
  });

  test("a peer in its relationships is selected on the canvas", async ({ page }) => {
    const { element } = await open(page, { details: "open" });
    await clickNode(page, element.id);
    const peer = card(page).locator(".details__rels .details__link").first();
    const name = (await peer.textContent()) ?? "";
    await peer.click();
    await expect(card(page).getByRole("heading", { level: 3 })).toHaveText(name);
  });

  test("Escape inside the card closes it", async ({ page }) => {
    const { element } = await open(page, { details: "open" });
    await clickNode(page, element.id);
    await card(page).getByRole("button", { name: "Open in Source ↗" }).focus();
    await page.keyboard.press("Escape");
    await expect(card(page)).toHaveCount(0);
  });

  for (const [width, height] of [
    [1440, 900],
    [1024, 768],
    [700, 800],
  ]) {
    test(`at ${width}px it clears the toolbar and the MiniMap`, async ({ page }) => {
      const { element } = await open(page, { width, height, details: "open" });
      await clickNode(page, element.id);
      await expect(card(page)).toBeVisible();

      const box = (await card(page).boundingBox())!;
      const toolbar = (await page.locator(".edge-style").boundingBox())!;
      // The toolbar stays inside the canvas too: it wraps rather than
      // running off the left edge.
      expect(toolbar.x).toBeGreaterThanOrEqual((await page.locator(".graph").boundingBox())!.x);
      const minimap = (await page.locator(".react-flow__minimap").boundingBox())!;
      const canvas = (await page.locator(".graph").boundingBox())!;

      expect(box.y).toBeGreaterThanOrEqual(toolbar.y + toolbar.height);
      expect(box.y + box.height).toBeLessThanOrEqual(minimap.y);
      expect(box.x).toBeGreaterThanOrEqual(canvas.x);
      expect(box.x + box.width).toBeLessThanOrEqual(canvas.x + canvas.width);
      // A narrow canvas gets a full-width sheet rather than a 320px card.
      if (canvas.width <= 640) expect(box.width).toBeGreaterThan(320);
      else expect(box.width).toBe(320);

      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
    });
  }
});
