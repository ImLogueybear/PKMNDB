/**
 * Build the CardTable-compatible scan catalogue from PKMNDB dist data.
 *
 * Inputs:
 *   data/scan/cardtable-set-map.json  PKMNDB set id -> CardTable app set id
 *   dist/sets.json                    canonical set metadata
 *   dist/sets/<set id>.json           canonical set card list
 *
 * Output:
 *   data/scan/cardtable-catalog.json  { cards: [{ id, setId, number, name, image }] }
 *
 * The card ids match CardTable's mapPkmndbCard: legacy-mapped sets reuse
 * `<appSetId>-<printed number>`; PKMNDB-only sets use `pkmndb-<card id>` or
 * `ja-pkmndb-<card id>`.
 *
 * Usage: node scripts/build-scan-catalog.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SET_MAP = JSON.parse(
  fs.readFileSync(path.join(ROOT, "data", "scan", "cardtable-set-map.json"), "utf8"),
);
const SETS = JSON.parse(fs.readFileSync(path.join(ROOT, "dist", "sets.json"), "utf8"));

const keylessNumber = (value) => {
  const trimmed = String(value ?? "").trim();
  return /^\d+$/.test(trimmed) ? trimmed.replace(/^0+(?=\d)/, "") : trimmed;
};

const normalizeNumber = (value, language) => {
  const trimmed = String(value ?? "")
    .trim()
    .replace(/^No\.\s*/i, "")
    .split("/")[0]
    .trim();
  return language === "en" ? keylessNumber(trimmed) : trimmed;
};

const setMap = new Map(SET_MAP.map((entry) => [entry.id, entry.appSetId]));
const cards = [];
const usedBySet = new Map();
const missing = [];

for (const set of SETS) {
  const appSetId = setMap.get(set.id);
  if (!appSetId) {
    missing.push(set.id);
    continue;
  }
  const file = path.join(ROOT, "dist", "sets", `${set.id}.json`);
  if (!fs.existsSync(file)) {
    missing.push(set.id);
    continue;
  }
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  const language = set.language === "ja" ? "ja" : "en";
  const namespaced =
    language === "ja" ? `ja-pkmndb-${set.id}` : `pkmndb-${set.id}`;
  const keyless = appSetId !== namespaced;
  const used = usedBySet.get(appSetId) ?? new Set();
  usedBySet.set(appSetId, used);

  for (const raw of data.cards ?? []) {
    const number = normalizeNumber(raw.number, language);
    let id;
    if (keyless) {
      const base = `${appSetId}-${language === "en" ? keylessNumber(number) : number}`;
      id = base;
      let suffix = 2;
      while (used.has(id)) id = `${base}-${raw.id}-${suffix++}`;
      used.add(id);
    } else {
      id = language === "ja" ? `ja-pkmndb-${raw.id}` : `pkmndb-${raw.id}`;
    }
    cards.push({
      id,
      setId: appSetId,
      number,
      name: raw.name,
      image: raw.image_url,
    });
  }
}

fs.writeFileSync(
  path.join(ROOT, "data", "scan", "cardtable-catalog.json"),
  JSON.stringify({ cards }),
);
console.log(
  `Wrote ${cards.length} cards across ${usedBySet.size} sets` +
    `${missing.length ? `; ${missing.length} sets had no mapping` : ""}.`,
);
