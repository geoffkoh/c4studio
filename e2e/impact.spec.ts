import { expect, test, type Page } from "@playwright/test";

/**
 * The impact overlay on the Diagrams page (PP-193).
 *
 * The details card offers "Show impact" for a selected element; the view
 * then shows what a change to it involves, painted as a perspective of
 * its own — badges on what is involved, the rest faded, the legend
 * rebuilt — and a toolbar chip says what is shown and clears it. The
 * answer itself is the server's (`tests/test_webapp/test_impact_api.py`);
 * what is checked here is that the page paints exactly that answer.
 *
 * Layout writes are answered here because the server serves `samples/`.
 */
const ELEMENT = "routing";

type Hop = { id: string };
type Impact = {
  element: { id: string; name: string };
  dependents: Hop[];
  dependencies: Hop[];
  views: string[];
  family: string[];
};

async function open(page: Page) {
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("c4studio.details", "open");
  });
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  const node = page.locator(`.react-flow__node[data-id="${ELEMENT}"]`);
  await expect(node).toBeVisible({ timeout: 20_000 });
  const impact = (await (await page.request.get(`/api/impact/${ELEMENT}`)).json()) as Impact;
  return { node, impact };
}

const card = (page: Page) => page.getByRole("complementary", { name: "Details" });
const chip = (page: Page) => page.locator(".impact-chip");

/** Ids of the element nodes on screen with each badge, and the faded ones. */
async function painted(page: Page) {
  return page.locator(".react-flow__node-element").evaluateAll((nodes) => {
    const out: Record<string, string[]> = { faded: [] };
    for (const node of nodes) {
      const id = node.getAttribute("data-id") ?? "";
      if (node.classList.contains("perspective-faded")) out.faded.push(id);
      const badge = node.querySelector(".node__perspective")?.textContent;
      if (badge) (out[badge] ??= []).push(id);
    }
    return out;
  });
}

test.describe("impact overlay", () => {
  test("the card shows it, and the view paints exactly the server's answer", async ({
    page,
  }) => {
    const { node, impact } = await open(page);
    await node.click();
    await card(page).getByRole("button", { name: "Show impact" }).click();
    await expect(chip(page)).toContainText(`Impact of ${impact.element.name}`);

    const shown = await painted(page);
    expect(shown["Changed"]).toContain(ELEMENT);
    const dependents = new Set(impact.dependents.map((h) => h.id));
    const dependencies = new Set(impact.dependencies.map((h) => h.id));
    for (const id of shown["Depends on it"] ?? []) expect(dependents.has(id)).toBe(true);
    for (const id of shown["It depends on"] ?? []) expect(dependencies.has(id)).toBe(true);
    // Something is involved and something is not, or the checks above
    // and below could not fail.
    expect((shown["Depends on it"] ?? []).length + (shown["It depends on"] ?? []).length).toBeGreaterThan(0);
    expect(shown.faded.length).toBeGreaterThan(0);
    for (const id of shown.faded) {
      expect(dependents.has(id) || dependencies.has(id) || id === ELEMENT).toBe(false);
    }

    // The legend explains the repaint rather than the styles.
    const legend = page.locator(".legend");
    await expect(legend).toContainText("Changed");
    await expect(legend).toContainText("Not involved");

    // The card gives the model-wide counts.
    const count = impact.dependents.length;
    const reach =
      count === 0
        ? "Nothing depends on it"
        : `${count} ${count === 1 ? "depends" : "depend"} on it`;
    await expect(card(page).getByLabel("Impact summary")).toContainText(
      `${reach} · it depends on ${impact.dependencies.length}`,
    );
    await expect(card(page).getByRole("button", { name: "Hide impact" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("the chip clears it, and so does choosing a perspective", async ({ page }) => {
    const { node } = await open(page);
    await node.click();
    await card(page).getByRole("button", { name: "Show impact" }).click();
    await expect(chip(page)).toBeVisible();

    await page.getByRole("button", { name: "Clear impact" }).click();
    await expect(chip(page)).toHaveCount(0);
    expect((await painted(page)).faded).toEqual([]);

    await card(page).getByRole("button", { name: "Show impact" }).click();
    await expect(chip(page)).toBeVisible();
    const picker = page.getByLabel("Perspective");
    const first = await picker.locator("option").nth(1).getAttribute("value");
    await picker.selectOption(first!);
    // One overlay at a time: the perspective replaces the impact.
    await expect(chip(page)).toHaveCount(0);
    await expect(page.locator(".legend")).not.toContainText("Not involved");
  });

  test("it stays on across views", async ({ page }) => {
    const { node, impact } = await open(page);
    await node.click();
    await card(page).getByRole("button", { name: "Show impact" }).click();
    await expect(chip(page)).toBeVisible();
    // Another view that draws the element.
    const other = impact.views.find((key) => key !== "PlatformContainers");
    test.skip(!other, "the element is drawn in one view only");
    await page.getByRole("button", { name: /Routing Engine – Components/ }).click();
    await expect(chip(page)).toContainText(impact.element.name);
  });
});
