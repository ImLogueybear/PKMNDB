/**
 * Audit and repair missing PKMNDB images.
 *
 * Three classes of gaps are handled:
 *   1. cards whose image is the Pokemon card back (placeholder hash)
 *   2. sets with no logo (logo_path / logo_public_url NULL)
 *   3. sets with no symbol (symbol_path / symbol_public_url NULL)
 *
 * Candidate artwork is resolved from, in order:
 *   - pokemontcg.io static CDN  (English set logos/symbols + card fronts)
 *   - Limitless TCG            (Japanese set logos + Japanese card fronts)
 *   - TCG Collector            (set logos/symbols, and card fronts)
 *
 * Resolved binaries are downloaded, hashed, uploaded to the public R2 bucket and
 * written into the SQLite database plus the dist exports. Nothing is applied
 * unless a source returns real artwork: every candidate is rejected when it is
 * byte-identical to the card back or to the source's default placeholder.
 *
 * Usage:
 *   node scripts/fill-missing-images.mjs --audit          report only
 *   node scripts/fill-missing-images.mjs --dry            resolve + download, no writes
 *   node scripts/fill-missing-images.mjs                  apply
 *   node scripts/fill-missing-images.mjs --only=logo,symbol,cards
 */
import { createHash, createHmac } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const ARGS = new Set(process.argv.slice(2));
const AUDIT = ARGS.has("--audit");
const DRY = ARGS.has("--dry") || AUDIT;
const ONLY = (process.argv.find((a) => a.startsWith("--only=")) ?? "--only=logo,symbol,cards")
  .split("=")[1]
  .split(",")
  .map((s) => s.trim());

const R2_CONFIG = join(homedir(), ".config", "pkmndb", "r2.json");
const R2 = existsSync(R2_CONFIG) ? JSON.parse(readFileSync(R2_CONFIG, "utf8")) : null;
const PUBLIC_BASE = (R2?.public_base_url ?? "https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev").replace(/\/+$/, "");

const CARD_BACK_SHA =
  "fd7c3800f9b8ebadf4b31a735f569a180e66201741b00fafa17879967884ad2c";
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const hmac = (key, value) => createHmac("sha256", key).update(value).digest();
const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- sources ---

async function fetchBytes(url, { attempts = 3, allowError = true } = {}) {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const res = await fetch(url, { headers: { "User-Agent": UA } });
      if (res.status === 429) {
        await sleep(1200 * attempt);
        continue;
      }
      if (!res.ok) {
        if (allowError) return null;
        throw new Error(`GET ${url} -> HTTP ${res.status}`);
      }
      return Buffer.from(await res.arrayBuffer());
    } catch (err) {
      if (attempt === attempts) {
        if (allowError) return null;
        throw err;
      }
      await sleep(800 * attempt);
    }
  }
  return null;
}

async function fetchText(url, { attempts = 3 } = {}) {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const res = await fetch(url, { headers: { "User-Agent": UA } });
      if (res.status === 429) {
        await sleep(2000 * attempt);
        continue;
      }
      if (!res.ok) return null;
      return await res.text();
    } catch {
      await sleep(800 * attempt);
    }
  }
  return null;
}

const IMAGE_MAGIC = new Set(["89504e47", "52494646", "47494638", "ffd8ffe0", "ffd8ffe1"]);

/** Read width/height from a PNG, WebP or GIF header. */
function imageSize(buf) {
  if (!buf || buf.length < 32) return null;
  const magic = buf.subarray(0, 4).toString("hex");
  if (magic === "89504e47") {
    return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
  }
  if (magic === "47494638") {
    return { width: buf.readUInt16LE(6), height: buf.readUInt16LE(8) };
  }
  if (magic === "52494646" && buf.subarray(12, 16).toString() === "VP8X") {
    return { width: 1 + buf.readUIntLE(24, 3), height: 1 + buf.readUIntLE(27, 3) };
  }
  if (magic === "52494646" && buf.subarray(12, 16).toString() === "VP8 ") {
    return { width: buf.readUInt16LE(26) & 0x3fff, height: buf.readUInt16LE(28) & 0x3fff };
  }
  return null;
}

function isImage(buf) {
  if (!buf || buf.length < 512) return false;
  const magic = buf.subarray(0, 4).toString("hex");
  if (!IMAGE_MAGIC.has(magic)) return false;
  return sha256(buf) !== CARD_BACK_SHA;
}

/**
 * A set logo must be wide and reasonably large; TCG Collector also publishes
 * 25x25 set symbols under the same grid, and those are not logos.
 */
function isLogo(buf) {
  if (!isImage(buf)) return false;
  const size = imageSize(buf);
  if (!size) return buf.length > 2000;
  return size.width >= 80 && size.width >= size.height;
}

function isSymbol(buf) {
  if (!isImage(buf)) return false;
  const size = imageSize(buf);
  if (!size) return buf.length > 300;
  const ratio = size.width / size.height;
  return ratio >= 0.5 && ratio <= 2;
}

const norm = (value) =>
  String(value)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/g, "");

const stripParens = (value) => norm(String(value).replace(/\([^)]*\)/g, ""));

const localId = (number) =>
  String(number)
    .replace(/^No\.\s*/i, "")
    .trim()
    .split("/")[0]
    .trim()
    .replace(/^0+(?=\d)/, "");

// ------------------------------------------------------------ r2 uploader ---

async function putR2(key, body) {
  if (!R2) throw new Error(`Missing R2 credentials at ${R2_CONFIG}`);
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
  const stringToSign = `AWS4-HMAC-SHA256\n${timestamp}\n${scope}\n${sha256(canonicalRequest)}`;
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
      Authorization: authorization,
      "x-amz-content-sha256": payloadHash,
      "x-amz-date": timestamp,
    },
    body,
  });
  if (!res.ok) throw new Error(`R2 PUT ${key} -> HTTP ${res.status}: ${await res.text()}`);
}

async function publish(key, bytes, sourceUrl) {
  const url = `${PUBLIC_BASE}/${key}`;
  if (!R2) {
    // No bucket credentials in this environment: point the record at the source
    // asset, which is public and hotlink-friendly, instead of leaving the back.
    return sourceUrl;
  }
  if (DRY) return url;
  const head = await fetch(url, { method: "HEAD" });
  if (!head.ok) await putR2(key, bytes);
  return url;
}

const extFor = (buf) => {
  const magic = buf.subarray(0, 4).toString("hex");
  if (magic === "89504e47") return "png";
  if (magic === "47494638") return "gif";
  if (magic.startsWith("ffd8")) return "jpg";
  return "webp";
};

// --------------------------------------------------------------- database ---

const db = new DatabaseSync(join(ROOT, "data", "pkmndb.sqlite3"));
const setMap = JSON.parse(readFileSync(join(ROOT, "data", "scan", "cardtable-set-map.json"), "utf8"));
const appSetId = new Map(Object.values(setMap).map((v) => [v.id, v.appSetId]));

const sets = db.prepare("SELECT * FROM sets ORDER BY id").all();
const gapCards = db
  .prepare(
    `SELECT c.*, s.name AS set_name, s.language AS set_language, s.code AS set_code
     FROM cards c JOIN sets s ON s.id = c.set_id
     WHERE c.image_sha256 = ? ORDER BY c.set_id, c.number_value, c.number`,
  )
  .all(CARD_BACK_SHA);

// ----------------------------------------------------------- source maps ----

/** pokemontcg.io set ids keyed by PKMNDB set id. */
function ptcgId(set) {
  const app = appSetId.get(set.id) ?? "";
  return app.replace(/^ja-pkmndb-/, "").replace(/^pkmndb-/, "").replace(/^ja-/, "");
}

/** Japanese TCG sets that Limitless indexes, keyed by PKMNDB set id. */
const LIMITLESS_SET = {
  11399: "HS",
  11406: "HSP",
  11658: "HSZ",
  11212: "SM5p",
  11219: "BWP",
  11373: "SP",
  11175: "SMP",
  11184: "XYP",
  11410: "MP",
  11473: "MC",
  11167: "BW1b",
  11202: "BW1w",
  11307: "BW6c",
};

async function limitlessCards(code) {
  const html = await fetchText(`https://limitlesstcg.com/cards/jp/${code}`);
  if (!html) return new Map();
  const map = new Map();
  for (const m of html.matchAll(
    /href="\/cards\/jp\/[^/]+\/([^"]+)"[\s\S]{0,1200}?<img[^>]+src="(https:\/\/limitlesstcg[^"]+\.png)"/g,
  )) {
    const key = localId(m[1]);
    if (!map.has(key)) map.set(key, m[2]);
  }
  return map;
}

/** Pick the largest variant from a `srcset` attribute, falling back to `src`. */
function largestSrc(block) {
  const srcset = (block.match(/srcset="([^"]+)"/) ?? [])[1] ?? "";
  let best = null;
  let bestWidth = -1;
  for (const part of srcset.split(",")) {
    const [url, descriptor] = part.trim().split(/\s+/);
    const width = Number.parseInt(String(descriptor ?? "").replace("w", ""), 10);
    if (!url || !Number.isFinite(width)) continue;
    if (width > bestWidth) {
      bestWidth = width;
      best = url;
    }
  }
  return best ?? (block.match(/<img[^>]+src="([^"]+)"/) ?? [])[1] ?? null;
}

/** TCG Collector set index: set id -> {href, logo}. */
async function tcgCollectorIndex() {
  const html = await fetchText("https://www.tcgcollector.com/sets");
  const out = new Map();
  if (!html) return out;
  const marker = '<div\n    class="set-logo-grid-item set-search-result-item"';
  for (const raw of html.split(marker).slice(1)) {
    const block = raw.split(marker)[0];
    const id = Number((block.match(/data-set-id="(\d+)"/) ?? [])[1]);
    if (!id) continue;
    const href = (block.match(/href="(\/sets\/\d+\/[^"?]+)/) ?? [])[1];
    const logo = largestSrc(block);
    if (!out.has(id)) out.set(id, { href, logo: logo ?? null });
  }
  return out;
}

async function tcgCollectorSymbol(href) {
  if (!href) return null;
  const html = await fetchText(`https://www.tcgcollector.com${href}`);
  if (!html) return null;
  const idx = html.indexOf("cards-page-header-set-symbol");
  if (idx < 0) return null;
  const before = html.slice(Math.max(0, idx - 900), idx);
  return (before.match(/src="(https:\/\/static\.tcgcollector\.com\/content\/images\/[^"]+)"/) ?? [])[1] ?? null;
}

/** PokeDataVault set tiles: normalised set name -> { img } (wide 400px logos). */
async function pokeDataVaultIndex() {
  const html = await fetchText("https://pokedatavault.com/cards/sets");
  const out = new Map();
  if (!html) return out;
  for (const m of html.matchAll(
    /<a class="set-tile" href="([^"]+)">[\s\S]*?<img src="([^"]+)" alt="([^"]+)"/g,
  )) {
    const name = m[3].replace(" Pokemon card set image", "").replace(/&amp;/g, "&");
    const key = norm(name);
    if (!out.has(key)) out.set(key, { href: m[1], img: m[2] });
  }
  return out;
}

// --------------------------------------------------------------- resolvers ---

async function resolveSetAsset(set, kind, tccIndex, pdvIndex) {
  const candidates = [];

  // 1. pokemontcg.io: English sets only, using the same ids the app already uses.
  //    Its CDN answers unknown paths with the card back, which isImage rejects.
  if (set.language === "en") {
    const id = ptcgId(set);
    if (id) candidates.push(`https://images.pokemontcg.io/${id}/${kind}.png`);
  }

  // 2. PokeDataVault set tiles: wide 400px logos, mainly for Japanese promos.
  if (kind === "logo") {
    const tile = pdvIndex.get(norm(set.name));
    if (tile) candidates.push(`https://pokedatavault.com${tile.img}`);
  }

  // 3. Limitless TCG: small set icons; they read as symbols rather than logos.
  if (set.language === "ja" && kind === "symbol") {
    const code = LIMITLESS_SET[set.id];
    if (code) candidates.push(`https://s3.limitlesstcg.com/sets/jp/${code}.png`);
  }

  // 4. TCG Collector: exact PKMNDB set ids, so this is the most precise match.
  //    The grid image is the wide set logo; the per-set page carries the symbol.
  const entry = tccIndex.get(set.id);
  if (kind === "logo" && entry?.logo) candidates.push(entry.logo);
  if (kind === "symbol" && entry?.href) {
    const symbol = await tcgCollectorSymbol(entry.href);
    if (symbol) candidates.push(symbol);
  }

  const accept = kind === "logo" ? isLogo : isSymbol;
  for (const url of candidates) {
    const bytes = await fetchBytes(url);
    if (accept(bytes)) return { url, bytes };
  }
  return null;
}

/**
 * World Championship decks reprint cards that already exist with real artwork
 * in their original sets. Those decks have no scans of their own anywhere, so
 * the original printing is the correct picture for the card.
 *
 * Deck card names are stored truncated ("Iono (WC Deck 2025"), so a trailing
 * unbalanced "(" is stripped along with any complete parenthetical.
 */
const decklessName = (value) =>
  norm(
    String(value)
      .replace(/\s*\([^)]*\)\s*$/, "")
      .replace(/\s*\([^)]*$/, ""),
  );

function reprintLookup(cards) {
  const byName = new Map();
  for (const card of cards) {
    if (card.image_sha256 === CARD_BACK_SHA || !card.public_url) continue;
    const key = decklessName(card.name);
    if (!key) continue;
    const list = byName.get(key) ?? [];
    list.push(card);
    byName.set(key, list);
  }
  return byName;
}

/**
 * PokeDataVault set page -> map of normalised card name -> {img, numbers}.
 * Card slugs look like `<name>-<set-slug>-<n>`, where `n` is PokeDataVault's own
 * sequence, while the tile label carries the printed number. A set can hold
 * several distinct cards under one name (alternate arts, promos), so the map
 * keeps every printed number seen for that name and the caller must agree.
 */
async function pokeDataVaultCards(href) {
  const seen = new Map();
  for (let page = 1; page <= 12; page++) {
    const html = await fetchText(
      `https://pokedatavault.com${href}${page === 1 ? "" : `/page/${page}`}`,
    );
    if (!html) break;
    let tiles = 0;
    for (const block of html.split('<a class="card-tile"').slice(1)) {
      const body = block.split("</a>")[0];
      const slug = (body.match(/href="\/cards\/([a-z0-9-]+)"/) ?? [])[1];
      const img = (body.match(/<img src="(\/assets_mirror\/[^"]+)"/) ?? [])[1];
      const label = (body.match(/<small>\s*([^<]*)/) ?? [])[1] ?? "";
      if (!slug || !img || slug === "sets" || slug === "illustrators") continue;
      tiles += 1;
      const printed = (label.match(/#\s*([A-Za-z0-9/-]+)/) ?? [])[1];
      const name = slug.replace(/-[a-z0-9-]*-[0-9]+$/, "").replace(/-[0-9]+$/, "");
      const key = decklessName(name.replace(/-/g, " "));
      if (!key) continue;
      const entry = seen.get(key) ?? { urls: new Set(), numbers: new Set() };
      entry.urls.add(`https://pokedatavault.com${img}`);
      if (printed) entry.numbers.add(localId(printed));
      seen.set(key, entry);
    }
    const pages = Number((html.match(/page \d+ of (\d+)/) ?? [])[1] ?? 1);
    if (!tiles || page >= pages) break;
  }
  const out = new Map();
  for (const [key, entry] of seen) {
    out.set(key, { urls: [...entry.urls], numbers: entry.numbers });
  }
  return out;
}

async function resolveCardImage(card, caches, reprints) {
  const { limitlessCache, pdvCache } = caches;

  // Japanese sets: Limitless publishes real scans for the gaps we could not
  // reach through any English source.
  const code = LIMITLESS_SET[card.set_id];
  if (code) {
    let map = limitlessCache.get(code);
    if (!map) {
      map = await limitlessCards(code);
      limitlessCache.set(code, map);
    }
    const url = map.get(localId(card.number));
    if (url) {
      const bytes = await fetchBytes(url);
      if (isImage(bytes)) return { url, bytes, source: "limitlesstcg" };
    }
  }

  // PokeDataVault mirrors Japanese card scans per set. The card slug ends with
  // PokeDataVault's own sequence, so match on the set slug plus card name.
  if (card.set_language === "ja") {
    const tile = pdvSetIndex.get(norm(card.set_name));
    if (tile) {
      let cards = pdvCache.get(tile.href);
      if (!cards) {
        cards = await pokeDataVaultCards(tile.href);
        pdvCache.set(tile.href, cards);
      }
      const entry = cards?.get(decklessName(card.name));
      // Only accept when the scan's printed number matches this card, so the
      // four distinct "Koko" promos cannot collapse onto a single image.
      const wanted = localId(card.number);
      if (entry && entry.urls.length === 1 && entry.numbers.has(wanted)) {
        const url = entry.urls[0];
        const bytes = await fetchBytes(url);
        if (isImage(bytes)) return { url, bytes, source: "pokedatavault" };
      }
    }
  }

  // TCG Collector keeps one row per card even when it has no scan, so a card
  // page only counts when it renders a real image rather than the placeholder.
  const html = await fetchText(`https://www.tcgcollector.com/cards/${card.id}`);
  if (html) {
    const idx = html.indexOf("card-image-container");
    if (idx > 0) {
      const src = (html.slice(idx, idx + 900).match(/<img src="([^"]+)"/) ?? [])[1];
      if (src && !src.includes("default-card-image")) {
        const bytes = await fetchBytes(src);
        if (isImage(bytes)) return { url: src, bytes, source: "tcgcollector" };
      }
    }
  }

  // Reprint-only decks (World Championship): reuse the original printing.
  if (/(WC Deck|World Championship)/i.test(card.set_name)) {
    const match = (reprints.get(decklessName(card.name)) ?? []).find((c) => c.public_url);
    if (match) {
      const bytes = await fetchBytes(match.public_url);
      if (isImage(bytes)) {
        return { url: match.public_url, bytes, source: `reprint:${match.set_id}/${match.number}` };
      }
    }
  }
  return null;
}

// ------------------------------------------------------------------ report ---

function audit() {
  const byLanguage = { en: 0, ja: 0 };
  const cardSets = new Map();
  for (const c of gapCards) {
    byLanguage[c.language] += 1;
    const row = cardSets.get(c.set_id) ?? { name: c.set_name, language: c.language, count: 0 };
    row.count += 1;
    cardSets.set(c.set_id, row);
  }

  const missingLogo = sets.filter((s) => !s.logo_public_url);
  const missingSymbol = sets.filter((s) => !s.symbol_public_url);

  console.log("PKMNDB image audit");
  console.log("==================");
  console.log(`cards using the card back : ${gapCards.length} (en ${byLanguage.en}, ja ${byLanguage.ja})`);
  for (const [id, row] of [...cardSets].sort((a, b) => b[1].count - a[1].count)) {
    console.log(`  ${id} ${row.language} ${row.name} -> ${row.count}`);
  }
  console.log(`sets missing logo         : ${missingLogo.length}`);
  console.log(`sets missing symbol       : ${missingSymbol.length}`);
  console.log(`sets missing both         : ${sets.filter((s) => !s.logo_public_url && !s.symbol_public_url).length}`);
}

// -------------------------------------------------------------------- main ---

const timestamp = now();
let stats = { logo: [0, 0], symbol: [0, 0], cards: [0, 0] };
const unresolved = { logo: [], symbol: [], cards: [] };
/** Rows touched by this run, used to keep the dist sync scoped. */
const touchedSets = new Set();
const touchedCards = new Set();

if (AUDIT) {
  audit();
  process.exit(0);
}

const tccIndex = await tcgCollectorIndex();
console.log(`TCG Collector index: ${tccIndex.size} sets`);
const pdvSetIndex = await pokeDataVaultIndex();
console.log(`PokeDataVault index: ${pdvSetIndex.size} sets`);

// ---- set logos + symbols ----
if (ONLY.includes("logo") || ONLY.includes("symbol")) {
  for (const set of sets) {
    for (const kind of ["logo", "symbol"]) {
      if (!ONLY.includes(kind)) continue;
      if (set[`${kind}_public_url`]) continue;
      stats[kind][1] += 1;
      const hit = await resolveSetAsset(set, kind, tccIndex, pdvSetIndex);
      if (!hit) {
        unresolved[kind].push(`${set.id} ${set.language} ${set.name}`);
        continue;
      }
      const ext = extFor(hit.bytes);
      const key = `sets/${set.id}-${kind}.${ext}`;
      const publicUrl = await publish(key, hit.bytes, hit.url);
      const objectPath = R2 ? `images/${key}` : null;
      stats[kind][0] += 1;
      console.log(`${kind.padEnd(6)} ${set.id} ${set.language} ${set.name} <- ${hit.url}`);
      if (!DRY) {
        db.prepare(
          `UPDATE sets SET ${kind}_path = ?, ${kind}_public_url = ?, scraped_at = ? WHERE id = ?`,
        ).run(objectPath, publicUrl, timestamp, set.id);
        touchedSets.add(set.id);
      }
    }
  }
}

// ---- card fronts ----
if (ONLY.includes("cards")) {
  const limitlessCache = new Map();
  const pdvCache = new Map();
  const reprints = reprintLookup(
    db
      .prepare(
        `SELECT c.id, c.set_id, c.name, c.number, c.public_url, c.image_sha256,
                s.name AS set_name, s.language AS set_language
         FROM cards c JOIN sets s ON s.id = c.set_id`,
      )
      .all(),
  );
  for (const card of gapCards) {
    stats.cards[1] += 1;
    const hit = await resolveCardImage(card, { limitlessCache, pdvCache }, reprints);
    if (!hit) {
      unresolved.cards.push(`${card.set_id} ${card.number} ${card.name}`);
      continue;
    }
    const ext = extFor(hit.bytes);
    const key = `cards/${card.set_id}/${card.number}-${card.id}.${ext}`;
    const publicUrl = await publish(key, hit.bytes, hit.url);
    // image_path describes where the bytes live: the bucket key when we upload,
    // otherwise the key of the reused object the public URL points at. A record
    // that points straight at an external source has no bucket object.
    const onBucket = publicUrl.startsWith(`${PUBLIC_BASE}/`);
    const objectPath = R2
      ? `images/${key}`
      : onBucket
        ? `images/${new URL(publicUrl).pathname.replace(/^\//, "")}`
        : null;
    const digest = sha256(hit.bytes);
    stats.cards[0] += 1;
    console.log(`card   ${card.set_id} ${card.number} ${card.name} <- ${hit.source}`);
    if (!DRY) {
      db.prepare(
        `UPDATE cards SET image_path = ?, public_url = ?, image_sha256 = ?, image_bytes = ?,
           image_downloaded_at = ?, scraped_at = ?, source_url = ? WHERE id = ?`,
      ).run(
        objectPath,
        publicUrl,
        digest,
        hit.bytes.length,
        timestamp,
        timestamp,
        hit.url,
        card.id,
      );
      touchedCards.add(card.id);
    }
  }
}

// ------------------------------------------------------------------- dist ----

if (!DRY) {
  const distSetsPath = join(ROOT, "dist", "sets.json");
  const distSets = JSON.parse(readFileSync(distSetsPath, "utf8"));
  const distCards = new Map();
  for (const line of readFileSync(join(ROOT, "dist", "cards.jsonl"), "utf8").split("\n")) {
    if (!line.trim()) continue;
    const card = JSON.parse(line);
    distCards.set(card.id, card);
  }

  for (const row of db
    .prepare(
      "SELECT id, logo_path, symbol_path, logo_public_url, symbol_public_url, scraped_at FROM sets",
    )
    .all()) {
    if (!touchedSets.has(row.id)) continue;
    const target = distSets.find((s) => s.id === row.id);
    if (!target) continue;
    target.logo_path = row.logo_path;
    target.symbol_path = row.symbol_path;
    target.logo_url = row.logo_public_url;
    target.symbol_url = row.symbol_public_url;
    target.scraped_at = row.scraped_at;
  }
  writeFileSync(distSetsPath, `${JSON.stringify(distSets, null, 2)}\n`);

  const cardRow = db.prepare(
    "SELECT id, image_path, public_url, image_sha256, image_bytes, scraped_at FROM cards WHERE id = ?",
  );
  for (const id of touchedCards) {
    const row = cardRow.get(id);
    const card = row ? distCards.get(row.id) : null;
    if (!card) continue;
    card.image_path = row.image_path;
    card.image_url = row.public_url;
    card.image_sha256 = row.image_sha256;
    card.image_bytes = row.image_bytes;
    card.scraped_at = row.scraped_at;
  }
  writeFileSync(
    join(ROOT, "dist", "cards.jsonl"),
    `${[...distCards.values()].map((c) => JSON.stringify(c)).join("\n")}\n`,
  );

  for (const set of distSets) {
    const file = join(ROOT, "dist", "sets", `${set.id}.json`);
    if (!existsSync(file)) continue;
    const payload = JSON.parse(readFileSync(file, "utf8"));
    payload.set = { ...payload.set, ...set };
    payload.cards = payload.cards.map((card) => {
      const fresh = distCards.get(card.id);
      return fresh ? { ...card, ...fresh } : card;
    });
    writeFileSync(file, `${JSON.stringify(payload, null, 2)}\n`);
  }
}

console.log("");
console.log(`${DRY ? "Would fill" : "Filled"} logos   : ${stats.logo[0]}/${stats.logo[1]}`);
console.log(`${DRY ? "Would fill" : "Filled"} symbols : ${stats.symbol[0]}/${stats.symbol[1]}`);
console.log(`${DRY ? "Would fill" : "Filled"} cards   : ${stats.cards[0]}/${stats.cards[1]}`);

for (const kind of ["logo", "symbol", "cards"]) {
  if (!unresolved[kind].length) continue;
  console.log(`\nNo source found (${kind}, ${unresolved[kind].length}):`);
  for (const row of unresolved[kind]) console.log(`  ${row}`);
}

if (!DRY) {
  // Report the state after this run, not just what this run happened to touch.
  const remainingSets = db
    .prepare("SELECT id, language, name, logo_public_url, symbol_public_url FROM sets")
    .all();
  const remainingCards = db
    .prepare(
      "SELECT c.set_id, c.number, c.name FROM cards c WHERE c.image_sha256 = ? ORDER BY c.set_id, c.number_value",
    )
    .all(CARD_BACK_SHA);

  writeFileSync(
    join(ROOT, "data", "sources", "missing-images-report.json"),
    `${JSON.stringify(
      {
        generated_at: timestamp,
        card_back_sha256: CARD_BACK_SHA,
        this_run: {
          logos: stats.logo[0],
          symbols: stats.symbol[0],
          cards: stats.cards[0],
        },
        remaining: {
          cards_using_the_back: remainingCards.length,
          sets_missing_logo: remainingSets.filter((s) => !s.logo_public_url).length,
          sets_missing_symbol: remainingSets.filter((s) => !s.symbol_public_url).length,
        },
        unresolved,
      },
      null,
      2,
    )}\n`,
  );
}
