import { expect, test, type Page } from "@playwright/test";

/**
 * A relationship style's `routing Orthogonal` on the canvas (PP-209).
 *
 * The server's half — which edges get `styleRouting` — is pinned by
 * `tests/test_style_routing.py`, along with `c4 render`. What only the
 * canvas shows is that the line is drawn orthogonally whatever the
 * toolbar's line style says, and that saving the layout does not copy
 * the model's choice into the sidecar's `routing` section, which is the
 * record of lines the user re-routed.
 *
 * The flag is added to the served graph here so no sample has to carry
 * the style; layout writes are answered here because the server serves
 * `samples/`.
 */
type Saved = { routing?: Record<string, string> };

async function open(page: Page) {
  const saves: Saved[] = [];
  const styled = { id: "" };
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    if (route.request().url().endsWith("/layout")) {
      saves.push(route.request().postDataJSON() as Saved);
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route(/\/api\/views\/PlatformContainers\/graph(\?.*)?$/, async (route) => {
    const response = await route.fetch();
    const data = (await response.json()) as { edges: { id: string; styleRouting?: string }[] };
    data.edges[0].styleRouting = "orthogonal";
    styled.id = data.edges[0].id;
    return route.fulfill({ response, json: data });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("c4studio.edgeStyle", "straight");
  });
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("logistics_network.dsl");
  await page.getByRole("button", { name: "logistics_network.dsl", exact: true }).click();
  await page.getByRole("button", { name: /Delivery Platform – Containers/ }).click();
  await expect.poll(() => styled.id).not.toBe("");
  await expect(page.locator(`[id="${styled.id}"]`)).toBeAttached({ timeout: 20_000 });
  await settled(page);
  return { saves, styled: styled.id };
}

/** Wait until no edge path changes for a while (see rerouting.spec.ts). */
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

const points = (d: string | null) =>
  [...(d ?? "").matchAll(/([-\d.]+),([-\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);

const orthogonal = (pts: number[][]) =>
  pts.every((p, i) => i === 0 || p[0] === pts[i - 1][0] || p[1] === pts[i - 1][1]);

test("a styled line is orthogonal under any line style, and is not saved as re-routed", async ({
  page,
}) => {
  const { saves, styled } = await open(page);
  const paths = await page
    .locator(".react-flow__edge-path")
    .evaluateAll((els) => els.map((el) => ({ id: el.id, d: el.getAttribute("d") })));

  expect(orthogonal(points(paths.find((p) => p.id === styled)!.d))).toBe(true);
  // The control: under Straight the other lines slant, so the check can fail.
  expect(paths.filter((p) => p.id !== styled).some((p) => !orthogonal(points(p.d)))).toBe(true);

  // A drag saves the whole layout; the styled line is not in `routing`.
  const node = page.locator(".react-flow__node-element").first();
  const box = (await node.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2 + 30, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => saves.length).toBeGreaterThan(0);
  expect(saves.at(-1)!.routing ?? {}).not.toHaveProperty(styled);
});
