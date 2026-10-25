import { useMemo } from "react";
import { Marked } from "marked";

/** A URL that names its scheme. One without is relative, and safe. */
const SCHEME = /^([A-Za-z][A-Za-z0-9+.-]*):/;
const LINK_SCHEMES = new Set(["http", "https", "mailto"]);
const IMAGE_SCHEMES = new Set(["http", "https"]);
const URL_ONLY = /^https?:\/\/\S+$/;

function safeUrl(url: string, image = false): boolean {
  const scheme = SCHEME.exec(url);
  if (!scheme) return true;
  if ((image ? IMAGE_SCHEMES : LINK_SCHEMES).has(scheme[1].toLowerCase())) return true;
  return image && url.toLowerCase().startsWith("data:image/");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Markdown for property values. Unlike `!docs` (DocsPane), a value is
 * model data — it may come from a workspace JSON written anywhere — so
 * raw HTML is shown as text and a link or image may only use the schemes
 * the published site allows (`c4studio/markdown.py`, PP-204). A link
 * opens in a new tab: followed in place, it would navigate away from the
 * Studio. Returning `false` hands a safe image to marked's own renderer.
 */
const markdown = new Marked({
  renderer: {
    html: ({ text }) => escapeHtml(text),
    link(token) {
      const text = this.parser.parseInline(token.tokens);
      if (!safeUrl(token.href)) return text;
      return `<a href="${escapeHtml(token.href)}" target="_blank" rel="noreferrer">${text}</a>`;
    },
    image: ({ href, text }) => (safeUrl(href, true) ? false : escapeHtml(text)),
  },
});

/**
 * One value. Written over several lines — a text block — it is Markdown;
 * on one line it is shown as written, apart from a bare URL becoming a
 * link. `"owner" "*team*"` is a name with asterisks in it far more often
 * than it is emphasis. The same rule as the published site.
 */
function PropertyValue({ value }: { value: string }) {
  const html = useMemo(
    () => (value.includes("\n") ? markdown.parse(value, { async: false }) : null),
    [value],
  );
  if (html !== null) {
    return <div className="properties__markdown" dangerouslySetInnerHTML={{ __html: html }} />;
  }
  if (URL_ONLY.test(value)) {
    return (
      <a href={value} target="_blank" rel="noreferrer">
        {value}
      </a>
    );
  }
  return <>{value}</>;
}

/**
 * An element's or relationship's `properties`, as the server sends them:
 * in source order, without the `c4studio.*` settings (PP-203).
 */
export function PropertyList({
  properties,
  label,
}: {
  properties: Record<string, string>;
  label: string;
}) {
  const entries = Object.entries(properties);
  if (entries.length === 0) return null;
  return (
    <dl className="properties" aria-label={label}>
      {entries.map(([key, value]) => (
        <div key={key} className="properties__row">
          <dt className="properties__key">{key}</dt>
          <dd className="properties__value">
            <PropertyValue value={value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
