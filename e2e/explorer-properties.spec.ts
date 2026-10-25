import { expect, test, type Page } from "@playwright/test";

/**
 * Element and relationship properties in the Explorer's details panel
 * (PP-203).
 *
 * The server's half — which properties are sent, and that `c4studio.*`
 * settings are not — is pinned by `tests/test_webapp/test_properties.py`.
 * What only a browser shows is how a value is drawn: a one-line value as
 * written, a bare URL as a link that leaves the Studio open, a multi-line
 * value as Markdown, and none of it able to put markup on the page.
 *
 * The values are added to the served model graph here, so no sample has
 * to carry them, and the hostile ones are exactly what a sample never
 * would.
 */
const RUNBOOK = [
  "## Restart",
  "",
  "1. Drain **all** traffic",
  "2. See [the wiki](https://wiki.example/orders)",
  "3. Not [a script](javascript:alert(1))",
  "",
  '<img src="x" onerror="window.__pwned = true">',
].join("\n");

type Element = { id: string; name: string; properties?: Record<string, string> };
type Rel = { source_id: string; properties?: Record<string, string> };

async function openExplorer(page: Page): Promise<{ id: string; name: string }> {
  let chosen = { id: "", name: "" };
  await page.route(/\/api\/model\/graph(\?.*)?$/, async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    // An element the graph draws, so it can be clicked, with a
    // relationship of its own.
    const drawn = new Set<string>(data.nodes.map((n: { id: string }) => n.id));
    const element = (data.elements as Element[]).find(
      (e) => drawn.has(e.id) && (data.relationships as Rel[]).some((r) => r.source_id === e.id),
    )!;
    chosen = { id: element.id, name: element.name };
    element.properties = {
      owner: "team-*payments*",
      repo: "https://github.com/acme/orders",
      runbook: RUNBOOK,
    };
    (data.relationships as Rel[]).find((r) => r.source_id === element.id)!.properties = {
      sla: "99.9%",
    };
    return route.fulfill({ response, json: data });
  });

  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("internet_banking.dsl");
  await page.getByRole("button", { name: "internet_banking.dsl", exact: true }).click();
  await page.locator(".topbar__tab", { hasText: "Explorer" }).click();
  await expect.poll(() => chosen.id).not.toBe("");
  const node = page.locator(`.react-flow__node[data-id="${chosen.id}"]`);
  await expect(node).toBeVisible({ timeout: 20_000 });
  await node.click();
  return chosen;
}

test.describe("Explorer properties", () => {
  test("values are drawn as written, as links, or as Markdown", async ({ page }) => {
    const { name } = await openExplorer(page);
    const props = page.locator(`dl[aria-label="Properties of ${name}"]`);
    await expect(props).toBeVisible();

    // One line: as written, asterisks and all.
    const owner = props.locator(".properties__row", { hasText: "owner" });
    await expect(owner.locator("dd")).toHaveText("team-*payments*");

    // A bare URL: a link that opens beside the Studio, not over it.
    const repo = props.getByRole("link", { name: "https://github.com/acme/orders" });
    await expect(repo).toHaveAttribute("href", "https://github.com/acme/orders");
    await expect(repo).toHaveAttribute("target", "_blank");

    // Several lines: Markdown.
    const runbook = props.locator(".properties__row", { hasText: "runbook" }).locator("dd");
    await expect(runbook.locator("h2")).toHaveText("Restart");
    await expect(runbook.locator("strong")).toHaveText("all");
    await expect(runbook.getByRole("link", { name: "the wiki" })).toHaveAttribute(
      "target",
      "_blank",
    );
  });

  test("a value cannot put markup or script on the page", async ({ page }) => {
    const { name } = await openExplorer(page);
    const runbook = page
      .locator(`dl[aria-label="Properties of ${name}"] .properties__row`, { hasText: "runbook" })
      .locator("dd");
    await expect(runbook.locator("h2")).toBeVisible();

    // Raw HTML is text, not an element.
    await expect(runbook.locator("img")).toHaveCount(0);
    await expect(runbook).toContainText('<img src="x"');
    expect(await page.evaluate(() => (window as { __pwned?: boolean }).__pwned)).toBeUndefined();

    // A javascript: link keeps its words and loses the link.
    await expect(runbook).toContainText("a script");
    await expect(runbook.locator('a[href^="javascript"]')).toHaveCount(0);
  });

  test("a relationship's properties sit under it", async ({ page }) => {
    await openExplorer(page);
    const rels = page.locator(".details__rels");
    await expect(rels.locator(".properties__row", { hasText: "sla" })).toContainText("99.9%");
  });
});
