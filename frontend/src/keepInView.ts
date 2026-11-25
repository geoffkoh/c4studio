/**
 * Where to pan so a box shows beside a card that covers part of the
 * canvas (PP-249). Pure, so the arithmetic can be read and tested without
 * a canvas.
 */

/** Pixels, relative to the canvas's top-left corner. */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/**
 * The pan, in screen pixels, that brings `box` into `free` with `margin`
 * to spare, or `null` when it is already there or cannot be: a box wider
 * or taller than the room is left where it is rather than half shown. An
 * axis the box already sits within is not moved, so a box only partly
 * hidden moves sideways and nowhere else.
 */
export function panToReveal(box: Rect, free: Rect, margin = 24): { dx: number; dy: number } | null {
  const fits = (lo: number, hi: number, from: number, to: number) => lo >= from + margin && hi <= to - margin;
  const room = (size: number, from: number, to: number) => size + 2 * margin <= to - from;
  const width = box.right - box.left;
  const height = box.bottom - box.top;
  if (!room(width, free.left, free.right) || !room(height, free.top, free.bottom)) return null;
  const dx = fits(box.left, box.right, free.left, free.right)
    ? 0
    : (free.left + free.right) / 2 - (box.left + box.right) / 2;
  const dy = fits(box.top, box.bottom, free.top, free.bottom)
    ? 0
    : (free.top + free.bottom) / 2 - (box.top + box.bottom) / 2;
  return dx === 0 && dy === 0 ? null : { dx, dy };
}
