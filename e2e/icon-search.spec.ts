import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import {
  groupVariants,
  queryWords,
  score,
  tokenise,
  variantRank,
  variantSuffixes,
  type Searchable,
} from "../frontend/src/iconSearch";

/**
 * The icon browser's ranking (PP-247), over the real Tabler pack: no
 * page, only the pure functions the picker calls.
 */
const pack = JSON.parse(
  readFileSync(join(__dirname, "../src/c4studio/icon_packs/tabler/icons.json"), "utf-8"),
) as { icons: Record<string, [string, string[], string]> };

const icons: Searchable[] = Object.entries(pack.icons).map(([name, [category, tags]]) => ({
  name,
  tokens: tokenise(name),
  tags: tags.flatMap(tokenise),
  category,
  own: false,
}));
const names = new Set(icons.map((icon) => icon.name));
const suffixes = variantSuffixes(names);

function search(query: string) {
  const words = queryWords(query);
  const phrase = query.trim().toLowerCase();
  return icons
    .map((item) => ({ item, score: score(item, words, phrase) }))
    .filter((r): r is { item: Searchable; score: number } => r.score !== null)
    .sort(
      (a, b) =>
        a.score - b.score ||
        variantRank(a.item) - variantRank(b.item) ||
        a.item.name.length - b.item.name.length ||
        a.item.name.localeCompare(b.item.name),
    );
}

const group = (query: string) =>
  groupVariants(search(query), () => ({ key: "tabler", names, suffixes }));

test("an icon matching the word typed ranks above one matching only a synonym", () => {
  // queue's synonyms are stack and message. Those two icons, named exactly,
  // are the curated answer and lead; stack-x and message-2-x are not.
  const ranked = search("queue").filter((r) => !["stack", "message"].includes(r.item.name));
  const literal = (icon: Searchable) =>
    icon.tokens.some((t) => t.startsWith("queue")) ||
    icon.tags.some((t) => t.startsWith("queue")) ||
    icon.category.toLowerCase().startsWith("queue");
  const firstSynonym = ranked.findIndex((r) => !literal(r.item));
  const lastLiteral = ranked.map((r) => literal(r.item)).lastIndexOf(true);
  expect(lastLiteral).toBeGreaterThanOrEqual(0);
  expect(firstSynonym).toBeGreaterThan(lastLiteral);
  // A synonym that is a whole name still comes first: db is database.
  expect(search("db")[0].item.name).toBe("database");
});

test("variant suffixes are read from the pack's names", () => {
  for (const suffix of ["off", "2", "plus", "minus", "x", "check"]) expect(suffixes).toContain(suffix);
  // Rare endings are names in their own right.
  for (const suffix of ["push", "database", "computing", "group"]) expect(suffixes).not.toContain(suffix);
});

test("a variant folds under the furthest base icon in the results", () => {
  const message = group("message").find((g) => g.item.name === "message");
  const folded = message?.variants.map((v) => v.name) ?? [];
  expect(folded).toContain("message-2-x");
  expect(folded).toContain("message-off");
  expect(folded).not.toContain("message-chatbot");
  // Every match is still there, drawn or folded.
  const all = group("message").flatMap((g) => [g.item, ...g.variants]);
  expect(all).toHaveLength(search("message").length);
});

test("a variant that ranks above its base is not hidden under it", () => {
  const groups = group("cloud computing");
  expect(groups[0].item.name).toBe("cloud-computing");
  expect(groups.flatMap((g) => g.variants).map((v) => v.name)).not.toContain("cloud-computing");
});
