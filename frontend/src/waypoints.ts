// Shared geometry for relationship bend points.

type Point = [number, number];

/** Distance from a point to a line segment (not to the infinite line). */
function distanceToSegment(a: Point, b: Point, x: number, y: number): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const lengthSquared = dx * dx + dy * dy;
  // Degenerate segment: fall back to the distance to its single point.
  if (lengthSquared === 0) return Math.hypot(x - a[0], y - a[1]);
  // Projection of the point onto the segment, clamped to its ends.
  const t = Math.max(
    0,
    Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / lengthSquared),
  );
  return Math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy));
}

/**
 * Where a new bend point belongs in the existing list so the line keeps
 * visiting its bends in order: the index of the segment of the routed
 * polyline (source → b0 → … → bn → target) that passes closest to the
 * click.
 *
 * Measuring against whole segments, endpoints included, is what makes this
 * correct for a single existing bend — comparing midpoints between bends
 * alone leaves the two candidate slots indistinguishable, and every new
 * point lands in front of the old one.
 */
export function insertionIndex(
  source: Point,
  target: Point,
  bends: Point[],
  x: number,
  y: number,
): number {
  const points: Point[] = [source, ...bends, target];
  let best = 0;
  let bestDistance = Infinity;
  for (let i = 0; i < points.length - 1; i += 1) {
    const distance = distanceToSegment(points[i], points[i + 1], x, y);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = i;
    }
  }
  return best;
}
