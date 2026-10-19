/**
 * Add the 25th Anniversary Creatures Deck (set 11651) to PKMNDB.
 *
 * The upstream source has the set metadata but no card list. This script uses
 * the CardTable gap audit's Bulbapedia deck list plus PokeDataVault's card
 * fronts, uploads the images to the public R2 bucket, inserts the 30 cards into
 * the canonical SQLite database, and updates the dist exports.
 *
 * Usage:
 *   node scripts/add-creatures-deck.mjs
 *   node scripts/add-creatures-deck.mjs --dry
 */
import { createHash, createHmac } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DRY = process.argv.includes("--dry");
const SET_ID = 11651;
const SOURCE = JSON.parse(readFileSync(join(ROOT, "data", "sources", "creatures-deck.json"), "utf8"));
const R2 = JSON.parse(readFileSync(join(homedir(), ".config", "pkmndb", "r2.json"), "utf8"));

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const hmac = (key, value) => createHmac("sha256", key).update(value).digest();
const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

function r2Key(number, id) {
  return `cards/${SET_ID}/${number}-${id}.webp`;
}

function publicUrl(key) {
  return `${R2.public_base_url.replace(/\/+$/, "")}/${key}`;
}

async function putR2(key, body) {
  const host = `${R2.account_id}.r2.cloudflarestorage.com`;
  const timestamp = new Date().toISOString().replace(/[:-]|\.\d{3}/g, "");
  const date = timestamp.slice(0, 8);
  const payloadHash = sha256(body);
  const canonicalHeaders =
    `host:${host}\n` +
    `x-amz-content-sha256:${payloadHash}\n` +
    `x-amz-date:${timestamp}\n`;
  const signedHeaders = "host;x-amz-content-sha256;x-amz-date";
  const canonicalRequest =
    `PUT\n/${R2.bucket}/${key}\n\n${canonicalHeaders}\n${signedHeaders}\n${payloadHash}`;
  const scope = `${date}/auto/s3/aws4_request`;
  const stringToSign =
    `AWS4-HMAC-SHA256\n${timestamp}\n${scope}\n${sha256(canonicalRequest)}`;
  const kDate = hmac(`AWS4${R2.secret_access_key}`, date);
  const kRegion = hmac(kDate, "auto");
  const kService = hmac(kRegion, "s3");
  const kSigning = hmac(kService, "aws4_request");
  const signature = createHmac("sha256", kSigning).update(stringToSign).digest("hex");
  const authorization =
    `AWS4-HMAC-SHA256 Credential=${R2.access_key_id}/${scope}, ` +
    `SignedHeaders=${signedHeaders}, Signature=${signature}`;
  const res = await fetch(`https://${host}/${R2.bucket}/${key}`, {
    method: "PUT",
    headers: {
      authorization,
      "content-type": "image/webp",
      "x-amz-content-sha256": payloadHash,
      "x-amz-date": timestamp,
    },
    body,
  });
  if (!res.ok) throw new Error(`R2 PUT ${key} -> HTTP ${res.status}: ${await res.text()}`);
}

async function fetchImage(url, attempts = 3) {
  let last;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const bytes = Buffer.from(await res.arrayBuffer());
      if (bytes.length < 1000) throw new Error(`unexpected image size ${bytes.length}`);
      return bytes;
    } catch (err) {
      last = err;
      await new Promise((r) => setTimeout(r, 500 * (i + 1)));
    }
  }
  throw last;
}

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const index = next++;
      results[index] = await fn(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

const db = new DatabaseSync(join(ROOT, "data", "pkmndb.sqlite3"));
const set = db.prepare("SELECT * FROM sets WHERE id = ?").get(SET_ID);
if (!set) throw new Error(`Set ${SET_ID} is missing from the database`);

const existing = db
  .prepare(
    `SELECT c.id, c.number FROM cards c
     JOIN set_cards sc ON sc.card_id = c.id
     WHERE sc.set_id = ? ORDER BY sc.position`,
  )
  .all(SET_ID);
const existingByNumber = new Map(existing.map((row) => [String(row.number), row.id]));

let nextId = Number(db.prepare("SELECT COALESCE(MAX(id), 0) AS id FROM cards").get().id) + 1;
const cards = SOURCE.cards.map((card) => ({
  ...card,
  id: existingByNumber.get(card.number) ?? nextId++,
}));

console.log(`Preparing ${cards.length} cards for set ${SET_ID} (${cards.filter((c) => existingByNumber.has(c.number)).length} existing)`);

const downloaded = await mapLimit(cards, 6, async (card) => {
  const bytes = await fetchImage(card.image_url);
  const key = r2Key(card.number, card.id);
  const url = publicUrl(key);
  if (!DRY) {
    const head = await fetch(url, { method: "HEAD" });
    if (!head.ok) await putR2(key, bytes);
    const check = await fetch(url, { method: "HEAD" });
    if (!check.ok) throw new Error(`Uploaded image is not public: ${url} (${check.status})`);
  }
  return {
    ...card,
    key,
    url,
    sha256: sha256(bytes),
    bytes: bytes.length,
    width: 286,
    height: 400,
  };
});

if (DRY) {
  console.log("--dry: nothing written. Would add:");
  for (const card of downloaded) {
    console.log(`  ${card.number} ${card.name} -> ${card.url} (${card.bytes} bytes)`);
  }
  process.exit(0);
}

const timestamp = now();
const insertCard = db.prepare(`
  INSERT INTO cards (
    id, set_id, name, number, number_value, printed_total, rarity,
    image_url, image_thumb_url, source_url, image_path, image_sha256,
    image_bytes, image_width, image_height, image_downloaded_at, scraped_at,
    language, public_url
  ) VALUES (
    ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'ja', ?
  )
`);
const updateCard = db.prepare(`
  UPDATE cards SET
    name = ?, number = ?, number_value = ?, printed_total = ?, rarity = ?,
    source_url = ?, image_path = ?, image_sha256 = ?, image_bytes = ?,
    image_width = ?, image_height = ?, image_downloaded_at = ?, scraped_at = ?,
    public_url = ?
  WHERE id = ?
`);
const insertMembership = db.prepare(
  "INSERT OR REPLACE INTO set_cards (set_id, card_id, position) VALUES (?, ?, ?)",
);

db.exec("BEGIN");
try {
  for (const card of downloaded) {
    const values = [
      card.name,
      card.number,
      card.position,
      SOURCE.cards.length,
      card.rarity,
      card.detail_url,
      `images/${card.key}`,
      card.sha256,
      card.bytes,
      card.width,
      card.height,
      timestamp,
      timestamp,
      card.url,
      card.id,
    ];
    if (existingByNumber.has(card.number)) updateCard.run(...values);
    else
      insertCard.run(
        card.id,
        SET_ID,
        card.name,
        card.number,
        card.position,
        SOURCE.cards.length,
        card.rarity,
        card.detail_url,
        `images/${card.key}`,
        card.sha256,
        card.bytes,
        card.width,
        card.height,
        timestamp,
        timestamp,
        card.url,
      );
    insertMembership.run(SET_ID, card.id, card.position);
  }
  db.prepare(
    "UPDATE sets SET card_count = ?, source_url = ?, scraped_at = ? WHERE id = ?",
  ).run(SOURCE.cards.length, SOURCE.source_url ?? SOURCE.source, timestamp, SET_ID);
  db.prepare(
    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
  ).run(`set_cards_synced_at:${SET_ID}`, timestamp);
  db.prepare("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_scrape_at', ?)").run(timestamp);
  db.exec("COMMIT");
} catch (err) {
  db.exec("ROLLBACK");
  throw err;
}

// --- dist exports -----------------------------------------------------------
function distCard(card, position) {
  return {
    id: card.id,
    set_id: SET_ID,
    set_ids: [SET_ID],
    language: "ja",
    name: card.name,
    number: card.number,
    number_value: card.position,
    printed_total: SOURCE.cards.length,
    rarity: card.rarity,
    image_path: `images/${card.key}`,
    image_url: card.url,
    image_sha256: card.sha256,
    image_bytes: card.bytes,
    scraped_at: timestamp,
    ...(position == null ? {} : { position }),
  };
}

const setsPath = join(ROOT, "dist", "sets.json");
const sets = JSON.parse(readFileSync(setsPath, "utf8"));
const setIndex = sets.findIndex((s) => s.id === SET_ID);
if (setIndex < 0) throw new Error(`Set ${SET_ID} is missing from dist/sets.json`);
sets[setIndex] = {
  ...sets[setIndex],
  card_count: SOURCE.cards.length,
  cards_loaded: SOURCE.cards.length,
  scraped_at: timestamp,
};
writeFileSync(setsPath, JSON.stringify(sets, null, 2) + "\n");

const perSetPath = join(ROOT, "dist", "sets", `${SET_ID}.json`);
const perSet = JSON.parse(readFileSync(perSetPath, "utf8"));
perSet.set = {
  ...perSet.set,
  card_count: SOURCE.cards.length,
  cards_loaded: SOURCE.cards.length,
  scraped_at: timestamp,
};
perSet.cards = downloaded.map((card) => distCard(card, card.position));
writeFileSync(perSetPath, JSON.stringify(perSet, null, 2) + "\n");

const cardsPath = join(ROOT, "dist", "cards.jsonl");
const rawLines = readFileSync(cardsPath, "utf8").trim().split("\n");
const keptLines = rawLines.filter((line) => {
  const card = JSON.parse(line);
  return !(card.set_ids ?? [card.set_id]).includes(SET_ID);
});
const allCards = [
  ...keptLines.map((line) => JSON.parse(line)),
  ...downloaded.map((card) => distCard(card)),
];
writeFileSync(
  cardsPath,
  `${[...keptLines, ...downloaded.map((card) => JSON.stringify(distCard(card)))].join("\n")}\n`,
);

const manifestPath = join(ROOT, "dist", "manifest.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
manifest.generated_at = now();
manifest.counts = {
  sets: sets.length,
  released_sets: sets.filter((s) => s.released).length,
  cards: allCards.length,
  cards_en: allCards.filter((c) => c.language === "en").length,
  cards_ja: allCards.filter((c) => c.language === "ja").length,
  set_card_memberships: Number(
    db.prepare("SELECT COUNT(*) AS count FROM set_cards").get().count,
  ),
  cards_with_images: allCards.filter((c) => c.image_url).length,
};
writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n");

console.log(`Added ${downloaded.length} cards to set ${SET_ID}.`);
console.log(`Manifest: ${JSON.stringify(manifest.counts)}`);
