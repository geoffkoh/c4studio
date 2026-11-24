/**
 * Search and suggestions for the icon browser (PP-244). Pure, so the
 * ranking can be read and changed without the component around it.
 */

/** Words people type for an architecture diagram, and what icons call them. */
export const SYNONYMS: Record<string, string[]> = {
  db: ["database"],
  sql: ["database", "table"],
  rdbms: ["database"],
  k8s: ["kubernetes", "container"],
  mq: ["queue", "message"],
  queue: ["queue", "stack", "message"],
  kafka: ["stream", "queue", "message"],
  bus: ["message", "arrows-exchange"],
  fn: ["function"],
  lambda: ["function", "lambda"],
  person: ["user"],
  people: ["users"],
  actor: ["user"],
  customer: ["user"],
  web: ["browser", "world"],
  ui: ["app-window", "browser"],
  frontend: ["browser", "app-window"],
  spa: ["browser"],
  mobile: ["device-mobile"],
  phone: ["device-mobile"],
  service: ["server", "api"],
  microservice: ["server", "api"],
  backend: ["server"],
  vm: ["server", "cpu"],
  cache: ["bolt", "cache"],
  storage: ["storage", "archive", "database"],
  bucket: ["bucket", "archive"],
  blob: ["file", "archive"],
  email: ["mail"],
  smtp: ["mail"],
  notification: ["bell"],
  cron: ["clock", "calendar"],
  scheduler: ["clock", "calendar"],
  job: ["clock", "settings"],
  auth: ["lock", "key", "shield"],
  security: ["shield", "lock"],
  gateway: ["router", "api"],
  lb: ["arrows-split", "router"],
  dns: ["world"],
  cdn: ["world", "cloud"],
  search: ["search"],
  analytics: ["chart-bar", "report-analytics"],
  ml: ["brain", "robot"],
  ai: ["brain", "robot", "sparkles"],
  payment: ["credit-card"],
  config: ["settings"],
};

/** Tabler names for the roles a C4 box usually plays, shown before a search. */
export const SUGGESTED: { group: string; names: string[] }[] = [
  { group: "People", names: ["user", "users", "users-group", "user-circle", "user-shield", "building", "building-store"] },
  { group: "Apps", names: ["browser", "app-window", "device-desktop", "device-mobile", "device-tablet", "terminal-2", "code"] },
  { group: "Services", names: ["api", "server", "server-2", "cpu", "plug-connected", "webhook", "puzzle"] },
  { group: "Data", names: ["database", "database-cog", "table", "file-database", "archive", "folders", "file-text"] },
  { group: "Messaging", names: ["message", "mail", "inbox", "bell", "send", "arrows-exchange", "stack-2"] },
  { group: "Infrastructure", names: ["cloud", "cloud-computing", "network", "router", "world", "shield-lock", "lock", "key"] },
  { group: "Work", names: ["function", "clock", "calendar-event", "refresh", "bolt", "settings", "chart-bar", "search"] },
];

/** What a search is matched against, worked out once per icon. */
export interface Searchable {
  name: string;
  /** Lower-cased name split on `-`, `_`, spaces and brackets. */
  tokens: string[];
  tags: string[];
  category: string;
  /** From the workspace's own `icons/`, ranked before built-in icons. */
  own: boolean;
}

export function tokenise(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[\s\-_()/.]+/)
    .filter(Boolean);
}

/**
 * What a synonym's match costs over the word typed (PP-247): enough that
 * an icon matching only through a synonym ranks below every icon matching
 * the word itself, even by category (3). "queue" matched 160 stack-* and
 * message-* icons ahead of what it said.
 */
const SYNONYM_PENALTY = 2.5;

/** The query as words, each with the words it stands for; the word itself first. */
export function queryWords(query: string): string[][] {
  return tokenise(query).map((word) => [word, ...(SYNONYMS[word] ?? []).flatMap(tokenise)]);
}

/**
 * Lower is better; `null` does not match. Every word must start a name
 * token (1), a tag (2) or the category (3), plus `SYNONYM_PENALTY` when
 * only a synonym does; the icon ranks by its worst word, and an exact
 * name beats everything. A synonym that is a whole name ("db" is
 * "database") ranks just after an exact name.
 */
export function score(item: Searchable, words: string[][], phrase: string): number | null {
  if (words.length === 0) return null;
  const name = item.name.toLowerCase();
  if (name === phrase || name === phrase.replace(/\s+/g, "-")) return 0;
  let worst = 0;
  for (const alternatives of words) {
    let best = Infinity;
    for (const [i, word] of alternatives.entries()) {
      const cost = i === 0 ? 0 : SYNONYM_PENALTY;
      if (item.tokens.some((token) => token.startsWith(word))) best = Math.min(best, 1 + cost);
      else if (item.tags.some((tag) => tag.startsWith(word))) best = Math.min(best, 2 + cost);
      else if (item.category.toLowerCase().startsWith(word)) best = Math.min(best, 3 + cost);
      // A synonym that is a whole name, as "db" is "database".
      if (alternatives.length > 1 && word === name) best = Math.min(best, 0.5);
    }
    if (best === Infinity) return null;
    worst = Math.max(worst, best);
  }
  return worst;
}

/**
 * Tie-breaks after the score: the workspace's own first, a `-off` or
 * numbered variant after its base icon, shorter names first.
 */
export function variantRank(item: Searchable): number {
  const name = item.name.toLowerCase();
  return (item.own ? 0 : 10) + (/-off$/.test(name) ? 2 : 0) + (/-\d+$/.test(name) ? 1 : 0);
}

/**
 * A pack's variant suffixes: a last name segment used on at least `min`
 * icons whose name without it is also an icon (`off`, `2`, `plus`, `x`,
 * `check`...). Read from the names, so a pack's own conventions decide,
 * and rare endings (`stack-push`, `file-database`) are names, not variants.
 */
export function variantSuffixes(names: Iterable<string>, min = 20): Set<string> {
  const all = new Set(names);
  const counts = new Map<string, number>();
  for (const name of all) {
    const cut = name.lastIndexOf("-");
    if (cut > 0 && all.has(name.slice(0, cut))) {
      const suffix = name.slice(cut + 1);
      counts.set(suffix, (counts.get(suffix) ?? 0) + 1);
    }
  }
  return new Set([...counts].filter(([, n]) => n >= min).map(([suffix]) => suffix));
}

/** The icon `name` is a variant of, or `null`: `message-2-x` -> `message-2`. */
export function variantOf(name: string, names: ReadonlySet<string>, suffixes: ReadonlySet<string>): string | null {
  const cut = name.lastIndexOf("-");
  if (cut <= 0 || !suffixes.has(name.slice(cut + 1))) return null;
  const base = name.slice(0, cut);
  return names.has(base) ? base : null;
}

export interface Grouped<T> {
  item: T;
  /** Its variants in the results, in result order; empty for most. */
  variants: T[];
}

/**
 * Ranked results with each variant folded under the furthest ancestor
 * also in them (`message-2-x` under `message`), so a search shows one tile
 * per icon rather than a screen of `-x`, `-plus` and `-off` (PP-247). A
 * variant that ranks better than that ancestor stays where it ranks:
 * searching "cloud computing" must not hide `cloud-computing` under
 * `cloud`. Only icons for which `family` gives one (a pack's names and
 * suffixes) are folded; the rest pass through as they are.
 */
export function groupVariants<T extends { name: string }>(
  ranked: { item: T; score: number }[],
  family: (item: T) => { names: ReadonlySet<string>; suffixes: ReadonlySet<string>; key: string } | null,
): Grouped<T>[] {
  const present = new Map<string, { item: T; score: number }>();
  for (const entry of ranked) {
    const f = family(entry.item);
    if (f) present.set(`${f.key}:${entry.item.name}`, entry);
  }
  const headOf = new Map<T, T>();
  for (const entry of ranked) {
    const f = family(entry.item);
    if (!f) continue;
    let head: { item: T; score: number } | null = null;
    for (let up = variantOf(entry.item.name, f.names, f.suffixes); up; up = variantOf(up, f.names, f.suffixes)) {
      head = present.get(`${f.key}:${up}`) ?? head;
    }
    if (head && head.score <= entry.score) headOf.set(entry.item, head.item);
  }
  const groups = new Map<T, Grouped<T>>();
  const result: Grouped<T>[] = [];
  for (const { item } of ranked) {
    const head = headOf.get(item);
    if (head) continue;
    const group = { item, variants: [] };
    groups.set(item, group);
    result.push(group);
  }
  for (const { item } of ranked) {
    const head = headOf.get(item);
    if (head) groups.get(head)?.variants.push(item);
  }
  return result;
}
