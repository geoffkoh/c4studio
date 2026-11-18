import { expect, test, type Page } from "@playwright/test";

/**
 * A layout from Structurizr workspace JSON (PP-220), in the Studio.
 *
 * Structurizr stores a position and a size for every element and nothing
 * for a boundary. The Studio used to re-run auto-layout whenever *any*
 * node lacked a position, so a JSON layout with a single boundary in it
 * was thrown away, and an element's stored size never reached its box.
 *
 * The Studio serves `samples/`, which holds no such JSON, so the graph
 * response is rewritten into that shape: every element in one column,
 * 450x300 and 400px apart with Structurizr's 24px text (PP-228), and
 * every boundary without position or size.
 */
const VIEW = /^E-Commerce – Containers container$/;
const STEP = 400;

type Box = { x: number; y: number; width: number; height: number };

/** Ids of the rewritten payload: elements in column order, and each
    boundary's children. */
interface Shape {
  column: string[];
  children: Map<string, string[]>;
}

async function open(page: Page): Promise<Shape> {
  const shape: Shape = { column: [], children: new Map() };
  await page.route(/\/api\/views\/[^/]+\/(expansion|layout|line-style)$/, async (route) => {
    if (route.request().method() === "GET") return route.fallback();
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
  await page.route(/\/api\/views\/EcommerceContainers\/graph/, async (route) => {
    const payload = await (await route.fetch()).json();
    shape.column = [];
    shape.children = new Map();
    for (const node of payload.nodes) {
      if (node.data.kind === "boundary") {
        delete node.position;
        delete node.size;
      } else {
        node.position = { x: 0, y: STEP * shape.column.length };
        node.size = { width: 450, height: 300 };
        node.data.fontSize = 24;
        shape.column.push(node.id);
      }
      if (node.parentId) {
        shape.children.set(node.parentId, [
          ...(shape.children.get(node.parentId) ?? []),
          node.id,
        ]);
      }
    }
    for (const edge of payload.edges) delete edge.waypoints;
    delete payload.chrome;
    await route.fulfill({ json: payload });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const rail = page.locator(".rail--left");
  if (await rail.isVisible()) await rail.click();
  await page.getByRole("searchbox", { name: "Search files" }).fill("ecommerce_platform.dsl");
  await page.getByRole("button", { name: "ecommerce_platform.dsl", exact: true }).click();
  await page.getByRole("button", { name: VIEW }).click();
  await expect(page.locator(".react-flow__node-element").first()).toBeVisible({
    timeout: 20_000,
  });
  // Let a same-view tween settle before measuring.
  await page.waitForTimeout(800);
  return shape;
}

const box = async (page: Page, id: string): Promise<Box> =>
  (await page.locator(`.react-flow__node[data-id="${id}"]`).boundingBox())!;

test("a JSON layout is drawn as stored, boundaries fitted around it", async ({ page }) => {
  const shape = await open(page);
  expect(shape.column.length).toBeGreaterThan(2);
  expect(shape.children.size).toBeGreaterThan(0);

  // On screen, so through the canvas zoom: the stored geometry shows as
  // ratios. Every element is 450:300, all in one column, tops 400 apart —
  // which an auto-layout would not produce.
  const boxes = await Promise.all(shape.column.map((id) => box(page, id)));
  const zoom = boxes[0].height / 300;
  for (const [i, b] of boxes.entries()) {
    expect(b.width / b.height).toBeCloseTo(1.5, 2);
    expect(b.x).toBeCloseTo(boxes[0].x, 0);
    expect((b.y - boxes[0].y) / zoom).toBeCloseTo(STEP * i, 0);
  }

  // Each boundary was fitted around its children — none of which it was
  // given a position or size for — rather than sending the view to a
  // fresh layout.
  for (const [boundaryId, childIds] of shape.children) {
    const outer = await box(page, boundaryId);
    for (const childId of childIds) {
      const inner = await box(page, childId);
      expect(inner.x).toBeGreaterThan(outer.x);
      expect(inner.y).toBeGreaterThan(outer.y);
      expect(inner.x + inner.width).toBeLessThan(outer.x + outer.width);
      expect(inner.y + inner.height).toBeLessThan(outer.y + outer.height);
    }
  }
});

test("an element box fills its stored size, a person's under its head", async ({ page }) => {
  const shape = await open(page);
  for (const id of shape.column) {
    const node = page.locator(`.react-flow__node[data-id="${id}"]`);
    const outer = (await node.boundingBox())!;
    const body = (await node.locator(".node").boundingBox())!;
    // The drawn box, not just React Flow's wrapper, is the stored size.
    expect(body.width).toBeCloseTo(outer.width, 0);
    const isPerson = (await node.locator(".person").count()) > 0;
    if (!isPerson) expect(body.height).toBeCloseTo(outer.height, 0);
    else expect(body.y + body.height).toBeCloseTo(outer.y + outer.height, 0);
  }
});

test("an element is drawn in Structurizr's type, centred in its box", async ({ page }) => {
  // At 450x300, c4studio's own 10px description reads as an empty box
  // (PP-228). Name 1.4x, metadata 0.7x, description at the 24px base.
  await open(page);
  const node = page.locator(".react-flow__node-element .node", { hasText: "Catalog Service" });
  await expect(node.locator(".node__label")).toHaveCSS("font-size", "33.6px");
  await expect(node.locator(".node__kind")).toHaveCSS("font-size", "16.8px");
  await expect(node.locator(".node__desc")).toHaveCSS("font-size", "24px");

  // Centred: as much room above the name as below the description.
  const outer = (await node.boundingBox())!;
  const first = (await node.locator(".node__label").boundingBox())!;
  const last = (await node.locator(".node__desc").boundingBox())!;
  const above = first.y - outer.y;
  const below = outer.y + outer.height - (last.y + last.height);
  expect(above).toBeGreaterThan(outer.height * 0.1);
  expect(Math.abs(above - below)).toBeLessThan(outer.height * 0.05);
});
