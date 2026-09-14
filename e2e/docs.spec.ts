import { expect, test } from "@playwright/test";

/**
 * The Docs page, which is the only consumer of `marked`.
 *
 * Added while bumping marked 15 → 18 (three majors), on discovering that
 * nothing covered it. The build passing says only that marked resolved;
 * it says nothing about whether markdown still reaches the page as
 * elements. `marked.parse` output was separately diffed across the version
 * change and was byte-identical over all 11 sample documents — this is the
 * other half, that the result is actually rendered.
 *
 * Deliberately not a screenshot: the assertion is "markdown became HTML",
 * which survives a wording change in the samples. A baseline would not.
 */
test("workspace documentation renders as HTML, not as escaped text", async ({
  page,
}) => {
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("hedge_fund/workspace.dsl");
  await page.getByRole("button", { name: "workspace.dsl", exact: true }).click();

  // The tab carries a count — "Documentation (3)" — so match the prefix.
  await page.getByRole("button", { name: /^Documentation/ }).click();
  const pane = page.locator(".docs");
  await expect(pane).toBeVisible();

  // marked's whole job: real elements rather than text that looks like
  // markup. Both halves matter — a renderer that escaped its output would
  // still produce plenty of text.
  await expect(pane.locator("h1, h2, h3").first()).toBeVisible();
  await expect(pane.locator("p").first()).toBeVisible();

  const text = await pane.innerText();
  expect(text.length).toBeGreaterThan(200);
  expect(text).not.toContain("<h2");
  expect(text).not.toContain("&lt;");
});
