# PKMNDB

Pokemon TCG set and card data for English/international, Japanese, and
Simplified Chinese releases.

## Snapshot

Last updated: 2026-10-23

- 930 sets (926 released, 4 upcoming)
  - 333 English/international sets
  - 451 Japanese sets
  - 146 Simplified Chinese sets
- 67,260 set-card memberships
- 62,807 unique cards (21,891 English, 27,961 Japanese, 12,955 Chinese)
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

Use `sets.id` and `cards.id` as the stable keys. Set codes are not unique, and
collector numbers can collide within a set, so neither is safe as a primary key.
The `(set_id, card_id)` pair identifies a set membership.

## Scan index

PKMNDB owns the prebuilt card-scan indexes used by CardTable/PocketVault:

- **CardTable:** `https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/scan/cardtable/index.json`
  — 985 shards, 70,396 packed descriptors, including 142 Chinese shards.
- **PocketVault:** `https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/scan/pocketvault/index.json`
  — 942 shards, 69,290 packed descriptors, including 142 Chinese shards.
- Shard pattern: `<base>/<setId>.bin`; format 2 / scan version 4.
- `dist/scan-index.json` and `dist/scan-index-pocketvault.json` are the small
  pointer manifests committed in this repo.
- The Chinese catalogue adds 142 shards to each index. The 59 no-art cards in
  `Happy Set: Trainer's Pokémon` (`111243`) are not indexed; the renumbered
  Creatures Deck ids (`2000001`-`2000030`) are included in the CardTable shard
  for `11651`.
- The two apps still have their pre-existing English/Japanese catalogue
  differences (CardTable includes legacy sets and PocketVault has its curated
  set list); Chinese set ids and card ids are shared, so 139/142 Chinese shards
  are byte-identical between the indexes. `11721` differs by 72 CardTable
  memberships, and `11824`/`11945` differ only in record order.

The CardTable index is derived from CardTable's app catalogue and PKMNDB card
images; rebuild the catalogue with `node scripts/build-scan-catalog.mjs`. The
PocketVault index is derived from PocketVault's `src/data/cards*.json` plus the
Creatures Deck rows. Both use the shared descriptor builder (`format` 2,
`SCAN_VERSION` 4) and are uploaded to their respective R2 prefixes.

## Notes

Unofficial Pokemon TCG data index. Card names and artwork remain the property
of their respective owners. No affiliation or endorsement is claimed.
