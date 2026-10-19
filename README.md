# PKMNDB

Pokemon TCG set and card data for English/international and Japanese releases.

## Snapshot

Last updated: 2026-10-19

- 784 sets (783 released, 1 upcoming)
  - 333 English/international sets
  - 451 Japanese sets
- 54,233 set-card memberships
- 49,852 unique cards (21,891 English, 27,961 Japanese)
- Unnumbered Energies excluded from both catalogs; Topps Series excluded from
  the English catalog
- French and German set releases excluded

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

## Files

- `data/pkmndb.sqlite3` — canonical SQLite database.
- `dist/sets.json` — set catalog.
- `dist/cards.jsonl` — one unique card per line, including `set_ids`.
- `dist/sets/<set_id>.json` — set metadata plus its ordered card list.
- `dist/manifest.json` — snapshot counts and schema version.
- `dist/scan-index.json` — pointer to the R2-hosted card-scan index.
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
- `language` — `en` or `ja`
- `name`, `number`, `number_value`, `printed_total`, `rarity`
- `image_path`, `public_url`, `image_sha256`, `image_bytes`
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

PKMNDB also owns the prebuilt card-scan index used by CardTable/PocketVault:

- Manifest: `https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/scan/cardtable/index.json`
- Shards: `https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/scan/cardtable/<setId>.bin`
- Format 2 / scan version 4; 843 set shards, 57,428 packed descriptors.
- `dist/scan-index.json` is the small pointer manifest committed in this repo.

The shards are derived from CardTable's app catalogue (stable app set/card ids)
and PKMNDB card images. Rebuild the catalogue with
`node scripts/build-scan-catalog.mjs`, then run the PocketVault/PKMNDB
descriptor builder (`format` 2, `SCAN_VERSION` 4) and upload the resulting
shards plus `index.json` to `scan/cardtable/`. The CardTable set-id mapping is
in `data/scan/cardtable-set-map.json`.

## Notes

Unofficial Pokemon TCG data index. Card names and artwork remain the property
of their respective owners. No affiliation or endorsement is claimed.
