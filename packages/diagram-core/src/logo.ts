/**
 * The workspace logo beside a diagram's title (PP-237): the icon of the
 * `Workspace:Icon` element style, as upstream draws it beside its title
 * block. One rule for every surface, so the Studio's title node and the
 * headless renderer size it the same way.
 */

/** The logo as the graph payload carries it. */
export interface WorkspaceLogo {
  /** A `data:` URI for a file; a theme's URL until it is embedded. */
  src: string;
  /** Width over height, read from the image; a square when unknown. */
  aspect?: number;
}

/** Drawn height: a little taller than the 18px title it sits beside. */
export const LOGO_HEIGHT = 28;
/** Between the logo and the title text. */
export const LOGO_GAP = 10;
/** A wordmark can be very wide; past this it would crowd the title out. */
const LOGO_MAX_WIDTH = 240;

/** Drawn width for a logo of this aspect, at `LOGO_HEIGHT`. */
export function logoWidth(logo: WorkspaceLogo): number {
  const aspect = logo.aspect && logo.aspect > 0 ? logo.aspect : 1;
  return Math.min(LOGO_HEIGHT * aspect, LOGO_MAX_WIDTH);
}
