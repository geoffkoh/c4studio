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

/** The query as words, each with the words it stands for. */
export function queryWords(query: string): string[][] {
  return tokenise(query).map((word) => [word, ...(SYNONYMS[word] ?? []).flatMap(tokenise)]);
}

/**
 * Lower is better; `null` does not match. Every word must start a name
 * token (1), a tag (2) or the category (3); the icon ranks by its worst
 * word, and an exact name beats everything.
 */
export function score(item: Searchable, words: string[][], phrase: string): number | null {
  if (words.length === 0) return null;
  const name = item.name.toLowerCase();
  if (name === phrase || name === phrase.replace(/\s+/g, "-")) return 0;
  let worst = 0;
  for (const alternatives of words) {
    let best = Infinity;
    for (const word of alternatives) {
      if (item.tokens.some((token) => token.startsWith(word))) best = Math.min(best, 1);
      else if (item.tags.some((tag) => tag.startsWith(word))) best = Math.min(best, 2);
      else if (item.category.toLowerCase().startsWith(word)) best = Math.min(best, 3);
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
