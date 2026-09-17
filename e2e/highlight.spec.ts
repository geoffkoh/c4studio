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
async function openSource(
  page: Page,
  path = "c4studio/workspace.dsl",
  marker = "workspace \"c4studio\"",
) {
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill(path);
  const file = path.split("/").pop() as string;
  await page.getByRole("button", { name: file, exact: true }).click();
  await page.getByRole("button", { name: "Source" }).click();
  await expect(page.locator(".editor__surface .cm-editor")).toBeVisible();
  // Switching files while another workspace is loaded swaps the buffer
  // under the same editor, and the first paint can be the new text with
  // the old (or no) tokens. Waiting for a line this file alone contains
  // means the assertions below are about highlighting rather than about
  // catching the editor mid-swap.
  await expect(
    page.locator(".editor__surface .cm-line", { hasText: marker }).first(),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByRole("searchbox", { name: "Search files" }).fill("");
}

/** The c4studio sample, which carries both `#` cases in one buffer. */
const openC4studioSource = (page: Page) => openSource(page);

/** Scroll the editor until `text` is rendered.
 *
 * CodeMirror only renders its viewport plus a margin, so a token 100 lines
 * down does not exist in the DOM on load. The first version of this test
 * asserted against it anyway and failed with "Received: 0" — which looks
 * exactly like the bug it was meant to catch. */
async function scrollTo(page: Page, text: string) {
  const scroller = page.locator(".editor__surface .cm-scroller");
  const line = page.locator(".editor__surface .cm-line", { hasText: text });

  // Two passes, because the first can start before the editor has
  // finished settling on the newly opened file: the buffer swaps under
  // one CodeMirror instance and its scroll position is restored
  // asynchronously, so a search that begins mid-swap scrolls the wrong
  // content and finds nothing. This failed in the full suite and passed
  // alone more than once before it was pinned down.
  for (let pass = 0; pass < 2; pass++) {
    // Back to the top through the editor's own Mod-Home binding, not by
    // assigning scrollTop: a raw assignment is undone a frame later.
    await page.locator(".editor__surface .cm-content").click();
    await page.keyboard.press("ControlOrMeta+Home");
    // Near the top, not exactly at it: the binding moves the cursor to
    // the document start and CodeMirror leaves a few pixels of padding
    // above the first line. Anything under a line height is "the top".
    await expect
      .poll(() => scroller.evaluate((el) => el.scrollTop))
      .toBeLessThan(40);

    for (let i = 0; i < 40; i++) {
      if (await line.count()) return;
      await scroller.evaluate((el) => {
        el.scrollTop += el.clientHeight;
      });
    }
  }
  throw new Error(`never rendered a line containing ${JSON.stringify(text)}`);
}

/** How many `cls` tokens the line containing `text` is painted with.
 *
 * Re-scrolls on every attempt. CodeMirror only renders its viewport and
 * restores its own scroll position asynchronously, so a line found once
 * can be gone from the DOM a moment later — which counts as zero tokens
 * and reads exactly like the missing-keyword bug this asserts against.
 * Polling with the scroll inside the loop is what makes the answer mean
 * "not painted" rather than "not on screen". */
async function paintedTokens(
  page: Page,
  text: string,
  cls: string,
): Promise<number> {
  let count = 0;
  for (let attempt = 0; attempt < 10; attempt++) {
    await scrollTo(page, text);
    count = await page
      .locator(".editor__surface .cm-line", { hasText: text })
      .first()
      .locator(cls)
      .count();
    if (count > 0) return count;
    await page.waitForTimeout(200);
  }
  return count;
}

test.describe("DSL highlighting", () => {
  test("a full-line # is a comment, and nothing in it is a keyword", async ({
    page,
  }) => {
    await openC4studioSource(page);

    const line = page.locator(".editor__surface .cm-line", { hasText: "Split across model/" });
    await expect(line).toHaveCount(1);
    await expect(line.locator(".dsl-comment")).toHaveCount(1);

    // The sharp half. That comment contains the word `model`, which is a
    // DSL keyword — before the fix the tokenizer classified it as one,
    // mid-prose, because no rule consumed the `#`.
    await expect(line.locator(".dsl-keyword")).toHaveCount(0);
    await expect(line.locator(".dsl-property")).toHaveCount(0);
  });

  test("the perspective vocabulary is painted (PP-177)", async ({ page }) => {
    // `logistics_network.dsl` is the sample carrying perspectives. The
    // editor knew none of these words: `highlight.ts` is the SPA's only
    // copy of the vocabulary, so a keyword missing there is a keyword the
    // editor cannot see — the same shape of drift as PP-164.
    await openSource(
      page,
      "logistics_network.dsl",
      'workspace "NorthWind Logistics"',
    );

    // `url` went in with the perspective words: it is a model-item body
    // property the vocabulary had never carried, so a `perspective` block
    // would have been lit half way. Line 49, one screenful from the
    // `perspectives` block below — asserting against a line 70 further
    // down failed on CI while passing locally.
    expect(
      await paintedTokens(page, 'url "https://api.northwind.example', ".dsl-property"),
    ).toBe(1);

    expect(
      await paintedTokens(page, "perspectives {", ".dsl-keyword"),
    ).toBe(1);
  });

  test("a mid-line # is still a colour", async ({ page }) => {
    await openC4studioSource(page);
    await scrollTo(page, "background #08427b");

    const line = page.locator(".editor__surface .cm-line", { hasText: "background #08427b" });
    // If the comment pattern were added without the start-of-line guard,
    // this line would paint as a comment from the `#` onward — worse than
    // the bug being fixed.
    await expect(line.locator(".dsl-color")).toHaveCount(1);
    await expect(line.locator(".dsl-comment")).toHaveCount(0);
  });
});
