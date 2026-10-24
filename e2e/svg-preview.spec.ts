import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/**
 * The VS Code preview's webview document.
 *
 * The preview stopped embedding the SPA and now paints an SVG from
 * `c4 render`. That moves the risk somewhere new: the webview's CSP.
 *
 * `default-src 'none'` covers `img-src`, and `render.py` inlines theme
 * icons as `data:` URIs so a diagram renders identically offline. Get the
 * CSP wrong and those icons vanish **with no error in the UI** — and most
 * views carry none, so they look perfect. That is why the icon tests
 * render a view that is guaranteed to have one.
 *
 * That view comes from a fixture with a **file-based** theme
 * (`e2e/fixtures/file-theme/`, PP-199), not from hedge_fund's AWS theme:
 * the AWS theme is fetched from static.structurizr.com, and when that host
 * stopped resolving (October 2026) these tests failed on every PR for a
 * reason that had nothing to do with the CSP.
 *
 * The head below is a copy of `head()` in `editors/vscode/src/preview.ts`.
 * If that changes, change this.
 */

const CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline';";

function previewHtml(svg: string, csp: string = CSP): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy" content="${csp}" />
  <style>
    html, body { margin: 0; padding: 0; height: 100%; }
    main { margin: auto; padding: 12px; width: 100%; box-sizing: border-box; }
    svg { width: 100%; height: auto; max-height: calc(100vh - 24px); display: block; }
  </style>
</head>
<body><main>${svg}</main></body>
</html>`;
}

/** Render one view the way the extension does — `c4 render --view`. */
function render(
  view: string,
  workspace: string = "samples/hedge_fund/workspace.dsl",
): string {
  return execFileSync("uv", ["run", "c4", "render", workspace, "--view", view], {
    encoding: "utf8",
    maxBuffer: 8 * 1024 * 1024,
  });
}

/** A view with a theme icon in it, rendered with no network involved. */
const ICON_WORKSPACE = "e2e/fixtures/file-theme/workspace.dsl";
const renderWithIcon = () => render("Containers", ICON_WORKSPACE);

/** Console messages that mean the CSP refused to load something. */
function watchForRefusals(page: import("@playwright/test").Page): string[] {
  const refusals: string[] = [];
  page.on("console", (message) => {
    if (/Content Security Policy|Refused to/i.test(message.text())) {
      refusals.push(message.text());
    }
  });
  page.on("pageerror", (error) => refusals.push(String(error)));
  return refusals;
}

test.describe("the SVG preview document", () => {
  test("a plain view paints, at panel width", async ({ page }) => {
    await page.setViewportSize({ width: 420, height: 900 });
    const refusals = watchForRefusals(page);

    await page.setContent(previewHtml(render("OmsContext")));

    const svg = page.locator("svg").first();
    await expect(svg).toBeVisible();
    const box = await svg.boundingBox();
    // Width-filling and not collapsed: the CSS overrides c4 render's own
    // width/height and leans on the viewBox, which is what lets one
    // picture serve a 400px panel and a half-screen editor group.
    expect(box!.width).toBeGreaterThan(380);
    expect(box!.height).toBeGreaterThan(50);
    expect(refusals, refusals.join("\n")).toEqual([]);
  });

  test("a view's data: icons actually load", async ({ page }) => {
    await page.setViewportSize({ width: 420, height: 900 });
    const refusals = watchForRefusals(page);
    const svg = renderWithIcon();
    // Guard the premise: if the sample stops embedding icons this test
    // silently stops testing anything.
    expect(svg).toContain("data:image");

    await page.setContent(previewHtml(svg));
    await expect(page.locator("svg").first()).toBeVisible();

    // `<image>` elements resolve their href lazily, so ask the DOM whether
    // each one actually decoded rather than trusting that it rendered.
    const decoded = await page.locator("svg image").evaluateAll((nodes) =>
      nodes.map((node) => {
        const box = node.getBoundingClientRect();
        return { w: Math.round(box.width), h: Math.round(box.height) };
      }),
    );
    expect(decoded.length).toBeGreaterThan(0);
    for (const size of decoded) {
      expect(size.w, `icon ${JSON.stringify(size)}`).toBeGreaterThan(0);
      expect(size.h, `icon ${JSON.stringify(size)}`).toBeGreaterThan(0);
    }
    expect(refusals, refusals.join("\n")).toEqual([]);
  });

  test("dropping img-src is what breaks the icons", async ({ page }) => {
    // The assertion above only means something if the CSP is load-bearing.
    // This is that proof, in the suite rather than in a commit message.
    const refusals = watchForRefusals(page);
    await page.setContent(
      previewHtml(renderWithIcon(), "default-src 'none'; style-src 'unsafe-inline';"),
    );
    await expect(page.locator("svg").first()).toBeVisible();
    expect(refusals.join("\n")).toMatch(/Refused to load the image|Content Security Policy/i);
  });
});
