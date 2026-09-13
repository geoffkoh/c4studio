import { expect, test } from "@playwright/test";

/**
 * The VS Code preview, as close as this can get without VS Code.
 *
 * The narrow-layout work was verified at a 500px *viewport*, which is a
 * proxy for the CSS and nothing else. The extension does something more
 * specific: it embeds the SPA in an `<iframe>` inside a webview whose CSP
 * is `default-src 'none'`, and that boundary had never been exercised.
 *
 * What this covers: the iframe, the CSP, and the app being usable at panel
 * width inside it. What it still does not: the real `vscode` host, the
 * panel being dragged, and the extension spawning the server itself. Those
 * need a `.vsix` and a human — this narrows the gap rather than closing it.
 *
 * The shell below is a copy of `iframeHtml` in
 * `editors/vscode/src/preview.ts`. If that changes, change this.
 */

const PORT = 8099;

/** Byte-for-byte the extension's webview shell, with the port filled in. */
function webviewShell(origin: string): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; frame-src ${origin}; style-src 'unsafe-inline';" />
  <style>
    html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; }
    iframe { border: none; width: 100%; height: 100%; }
  </style>
</head>
<body>
  <iframe src="${origin}/" allow="clipboard-read; clipboard-write"></iframe>
</body>
</html>`;
}

test.describe("VS Code webview shell", () => {
  test.beforeEach(async ({ page }) => {
    const origin = `http://127.0.0.1:${PORT}`;
    await page.route(`${origin}/__webview`, (route) =>
      route.fulfill({ contentType: "text/html", body: webviewShell(origin) }),
    );
  });

  test("the app loads inside the webview's iframe and CSP", async ({ page }) => {
    // A VS Code side panel, roughly.
    await page.setViewportSize({ width: 520, height: 800 });

    const failures: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") failures.push(message.text());
    });
    page.on("pageerror", (error) => failures.push(String(error)));

    await page.goto(`http://127.0.0.1:${PORT}/__webview`);
    const app = page.frameLocator("iframe");

    // If the CSP or the iframe broke the app, this never appears.
    await expect(app.locator(".topbar")).toBeVisible({ timeout: 15_000 });
    // The sidebar stays in the DOM when collapsed (`hidden`, so the file
    // tree keeps its expansion), so assert the state rather than counting.
    await expect(app.locator(".rail--left")).toBeVisible();
    await expect(app.locator(".sidebar")).toBeHidden();

    // A blocked stylesheet or script shows up here, and would otherwise be
    // invisible: the page would simply look wrong.
    const blocked = failures.filter((f) => /Content Security Policy|Refused to/i.test(f));
    expect(blocked, `CSP violations inside the webview:\n${blocked.join("\n")}`).toEqual([]);
  });

  test("at panel width the chrome does not eat the panel", async ({ page }) => {
    await page.setViewportSize({ width: 520, height: 800 });
    await page.goto(`http://127.0.0.1:${PORT}/__webview`);
    const app = page.frameLocator("iframe");
    await expect(app.locator(".topbar")).toBeVisible({ timeout: 15_000 });

    // The original complaint, measured where it actually happens: fixed
    // chrome once exceeded 100% of this width, so the panes computed to a
    // negative size.
    const railWidth = await app
      .locator(".rail--left")
      .evaluate((el) => el.getBoundingClientRect().width)
      .catch(() => 0);
    expect(railWidth, "the sidebar should start as a rail here").toBeLessThan(40);
    expect(railWidth).toBeGreaterThan(0);

    // And nothing may scroll sideways inside the frame.
    const overflow = await app.locator("body").evaluate(
      (el) => el.scrollWidth - el.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
