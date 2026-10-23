# PKMNDB

Pokemon TCG set and card data for English/international, Japanese, and
Simplified Chinese releases.

## Snapshot

Last updated: 2026-10-23

- 930 source sets (926 released, 4 upcoming)
  - 333 English/international sets
  - 451 Japanese sets
  - 146 Simplified Chinese sets
- 67,260 source set-card memberships
- 62,807 unique cards (21,891 English, 27,961 Japanese, 12,955 Chinese)
- `dist/canonical` app catalogue: **945 sets / 69,898 card memberships**
  (348 English, 451 Japanese, 146 Chinese), including the 15 TCG Pocket
  app-only sets (2,480 cards) and 158 PocketVault-only variants
- Unnumbered Energies excluded from all catalogs; Topps Series excluded from
  the English catalog
- French and German set releases excluded
- Traditional Chinese, Korean, and Indonesian set releases are not included

## Japanese Catalog

- 451 sets, 27,961 unique cards, 28,522 set-card memberships
- Original Base Set is listed as `Expansion Pack` (`11182`)
- Jungle is `11201`; Fossil is `Mystery of the Fossils` (`11172`)
- Japanese collector numbers use `No. 001`; `printed_total` is usually unknown
- Card fronts are JPG, up to 356px wide; English fronts are WebP, up to 733px
- Set logos and symbols use a mix of WebP and PNG
- `25th Anniversary Creatures Deck` (`11651`) was filled from Bulbapedia's
  30-card deck list and PokeDataVault card fronts; the upstream source has no
  card list. Its `001`-`030` numbers are checklist positions (the physical
  cards are unnumbered except `011/008` on three cards).
- Japanese rows are marked `language = 'ja'`
- The manually imported Creatures Deck rows use ids `2000001`-`2000030`, a
  reserved range above TCG Collector's card ids, so they cannot collide with
  scraped English/Japanese/Chinese rows.

## Simplified Chinese Catalog

- 146 sets, 12,955 unique cards, 13,027 set-card memberships
- Sourced from TCG Collector's China region; set codes end in `C` (`CSV10C`,
  `CSVH6C`, `CBB6C`, `30thC`)
- Set and card names are English, the same convention as the Japanese catalog
- Collector numbers use `001/222`; `printed_total` is populated when printed
- Card fronts are WebP, usually 300px wide
- 143 released sets are populated; 3 upcoming sets have no card list yet
- `Happy Set: Trainer's Pokémon` (`111243`) has no card art on the source, so
  its 59 cards are stored as metadata with `image_status = 'missing'`
- Chinese rows are marked `language = 'zh'`

## Image Gaps

- 872/930 sets have a logo and 797/930 have a symbol.
- 58 sets are missing a logo and 133 are missing a symbol.
- 16 sets have neither; 914 have at least one usable asset.
- `logo_fallback_url` and `symbol_fallback_url` in `sets.json` let applications
  use the other asset when one is missing.
- 400 cards only have the generic card-back image. They are marked
  `image_status = 'card_back'` and do not expose an `image_url`.
- 62,348 cards have verified front images and are marked
  `image_status = 'front'`.
- 59 Chinese cards have no image on the source. They are marked
  `image_status = 'missing'` and do not expose an `image_url`.
- `dist/art_issues.json` lists every affected set and card.

## Files

- `data/pkmndb.sqlite3` — canonical SQLite database.
- `dist/sets.json` — set catalog.
- `dist/cards.jsonl` — one unique card per line, including `set_ids`.
- `dist/sets/<set_id>.json` — set metadata plus its ordered card list.
- `dist/canonical/` — app-facing canonical catalogue (see "Canonical IDs").
  `sets.json`, `cards.jsonl`, `sets/<id>.json` (941 sets with cards), and
  `manifest.json`.
- `dist/manifest.json` — snapshot counts and schema version.
- `dist/art_issues.json` — sets missing art, cards using the card back, and
  cards with no image URL.
- `dist/scan-index.json` — pointer to the R2-hosted CardTable scan index.
- `dist/scan-index-pocketvault.json` — pointer to the PocketVault scan index.
- `data/sources/creatures-deck.json` — curated 30-card source list for set
  11651.
- `scripts/add-creatures-deck.mjs` — imports that deck, uploads its fronts to
  R2, and updates the SQLite database and dist exports.

Card front image binaries are not stored in this repository because the full
set is over 7 GB. The database includes each card's language, local image path,
public image URL, SHA-256, and byte size. English set archives are also
available in the `images-preview-1` GitHub release.

## Image Hosting

Images are hosted in a public Cloudflare R2 bucket:

```text
https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev
```

Public URL patterns:

```text
https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/cards/<set_id>/<number>-<card_id>.<ext>
https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/sets/<set_id>-logo.<ext>
https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/sets/<set_id>-symbol.<ext>
```

The database stores `public_url` for cards and `logo_public_url` /
`symbol_public_url` for sets, so applications do not need to construct paths
themselves. JSON exports expose these as `image_url`, `logo_url`, and
`symbol_url`.

The `r2.dev` endpoint is Cloudflare's development URL and may be rate-limited.
A custom domain is recommended for production applications.

## Schema

`sets`:

- `id` — numeric set ID
- `name`, `code`, `series`
- `release_date`, `date_text`, `released`
- `card_count`
- `logo_path`, `symbol_path`
- `logo_public_url`, `symbol_public_url`
- `scraped_at`

`cards`:

- `id` — numeric card ID
- `set_id` — canonical set ID
- `language` — `en`, `ja`, or `zh`
- `name`, `number`, `number_value`, `printed_total`, `rarity`
- `image_path`, `public_url`, `image_sha256`, `image_bytes`
- `image_status` — `front`, `card_back`, or `missing`
- `scraped_at`

`set_cards`:

- `set_id`, `card_id`, `position`
- A card can belong to multiple sets; set lists must be read through this table.

`meta` stores sync timestamps.

## Identifiers

Use `sets.id` and `cards.id` as the stable database keys. Set codes are not
unique, and collector numbers can collide within a set, so neither is safe as a
primary key. The `(set_id, card_id)` pair identifies a set membership.

`dist/canonical` exposes a separate app-facing ID model built from those
memberships:

- **English:** keyless PocketVault IDs where the set already existed there;
  PKMNDB-only English sets use `pkmndb-<setId>`.
- **Japanese:** every set and card uses `ja-pkmndb-<setId>`.
- **Simplified Chinese:** every set and card uses `zh-pkmndb-<setId>`.
- **TCG Pocket extras:** the 15 app-only sets keep their existing IDs
  (`A1`-`A4a`, `B1`-`B2a`, `P-A`).
- Card IDs are **per-set memberships**: `<canonicalSetId>-<cleanNumber>`, with
  `-2`, `-3`, ... suffixes for duplicate numbers in the same set. This keeps
  reprint and promo memberships (for example Play! Prize Pack) instead of
  collapsing them into one physical card.
- `miscp` is the only canonical set that merges two PKMNDB sets. All other
  canonical sets map 1:1.

## Scan index

PKMNDB owns the prebuilt card-scan index used by PocketVault and CardTable:

- **Canonical index:**
  `https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/scan/canonical/index.json`
  — 933 shards, 69,439 packed descriptors, format 2 / scan version 5.
- Both apps consume this one index. `dist/scan-index.json` (CardTable) and
  `dist/scan-index-pocketvault.json` (PocketVault) point at the same canonical
  `base_url` / `manifest_url` and carry the same `sets`, `cards` and
  `generated_at` values.
- Shard pattern: `<base>/<setId>.bin`. The builder is
  `PocketVaultTCG/scripts/build-scan-index.ts` with
  `--catalog data/scan/canonical/canonical-catalog.json` and
  `--image-root data/images/cards`.
- The 459 canonical cards without an image URL are not indexed: 400 use the
  generic card back and 59 Chinese cards in `111243` have no source art.
- The legacy `scan/pocketvault/` and `scan/cardtable/` v4 indexes remain in R2
  for already-released APKs; they are no longer written by this pipeline.

## Notes

Unofficial Pokemon TCG data index. Card names and artwork remain the property
of their respective owners. No affiliation or endorsement is claimed.
