/**
 * The Node entry point `c4 render` drives.
 *
 * Reads a view graph payload as JSON on stdin and writes an SVG document
 * to stdout — one process per diagram, no server, no browser. Python owns
 * parsing and view semantics; this owns layout and painting, so neither
 * side re-implements the other.
 *
 * Usage: node diagram-render.mjs [--title "..."] [--padding 24]
 *                                 [--no-title] [--no-legend] < graph.json
 */

import { renderSvg, type GraphPayload } from "./svg";

interface CliOptions {
  title?: string;
  padding?: number;
  showTitle?: boolean;
  showLegend?: boolean;
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--title") options.title = argv[++i];
    else if (argv[i] === "--padding") options.padding = Number(argv[++i]);
    else if (argv[i] === "--no-title") options.showTitle = false;
    else if (argv[i] === "--no-legend") options.showLegend = false;
  }
  return options;
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const raw = await readStdin();
  if (!raw.trim()) throw new Error("no graph payload on stdin");
  const payload = JSON.parse(raw) as GraphPayload;
  process.stdout.write(await renderSvg(payload, options));
}

main().catch((error: unknown) => {
  process.stderr.write(
    `diagram-render: ${error instanceof Error ? error.message : String(error)}\n`,
  );
  process.exit(1);
});
