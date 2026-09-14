import { expect, test, type Page } from "@playwright/test";

/**
 * DSL syntax highlighting in the editor, for the one rule with a guard.
 *
 * `#` is a comment only where nothing but whitespace precedes it on the
 * line; mid-line it is a hex colour. The parser has enforced that since
 * PP-112 (`HASH_COMMENT`, anchored `^[ \t]*#`, matching structurizr-java's
 * `^\s*?(//|#)`), but the editor had no `#` rule at all — so a comment got
 * no comment colour and the words inside it were still classified as
 * keywords (PP-164).
 *
 * Both halves are asserted here because a fix for either one alone is
 * wrong: a pattern without the guard turns `background #08427b` into a
 * comment from the `#` onward, which is worse than the bug.
 *
 * This drives the real CodeMirror instance. `highlight.ts` is pure and
 * would be cheaper to test directly, but there is no JS unit runner in
 * this repo and adding one is a dependency decision.
 */

/** Open samples/c4studio/workspace.dsl on the Source page.
 *
 * That file rather than hedge_fund because it carries both cases in one
 * buffer — a `#` comment in `model` and `#08427b` in `styles`. Via the
 * search box for the reason layout.spec.ts gives: the backend holds the
 * loaded workspace, so clicking through the tree works once per server. */
async function openC4studioSource(page: Page) {
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page
    .getByRole("searchbox", { name: "Search files" })
    .fill("c4studio/workspace.dsl");
  await page.getByRole("button", { name: "workspace.dsl", exact: true }).click();
  await page.getByRole("button", { name: "Source" }).click();
  await expect(page.locator(".editor__surface .cm-editor")).toBeVisible();
  await page.getByRole("searchbox", { name: "Search files" }).fill("");
}

/** Scroll the editor until `text` is rendered.
 *
 * CodeMirror only renders its viewport plus a margin, so a token 100 lines
 * down does not exist in the DOM on load. The first version of this test
 * asserted against it anyway and failed with "Received: 0" — which looks
 * exactly like the bug it was meant to catch. */
async function scrollTo(page: Page, text: string) {
  const scroller = page.locator(".editor__surface .cm-scroller");
  for (let i = 0; i < 40; i++) {
    if (await page.locator(".cm-line", { hasText: text }).count()) return;
    await scroller.evaluate((el) => {
      el.scrollTop += el.clientHeight;
    });
  }
  throw new Error(`never rendered a line containing ${JSON.stringify(text)}`);
}

test.describe("DSL highlighting", () => {
  test("a full-line # is a comment, and nothing in it is a keyword", async ({
    page,
  }) => {
    await openC4studioSource(page);

    const line = page.locator(".cm-line", { hasText: "Split across model/" });
    await expect(line).toHaveCount(1);
    await expect(line.locator(".dsl-comment")).toHaveCount(1);

    // The sharp half. That comment contains the word `model`, which is a
    // DSL keyword — before the fix the tokenizer classified it as one,
    // mid-prose, because no rule consumed the `#`.
    await expect(line.locator(".dsl-keyword")).toHaveCount(0);
    await expect(line.locator(".dsl-property")).toHaveCount(0);
  });

  test("a mid-line # is still a colour", async ({ page }) => {
    await openC4studioSource(page);
    await scrollTo(page, "background #08427b");

    const line = page.locator(".cm-line", { hasText: "background #08427b" });
    // If the comment pattern were added without the start-of-line guard,
    // this line would paint as a comment from the `#` onward — worse than
    // the bug being fixed.
    await expect(line.locator(".dsl-color")).toHaveCount(1);
    await expect(line.locator(".dsl-comment")).toHaveCount(0);
  });
});
