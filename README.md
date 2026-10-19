# PKMNDB

Pokemon TCG set and card data for English/international and Japanese releases.

## Snapshot

Last updated: 2026-10-19

- 784 sets (783 released, 1 upcoming)
  - 333 English/international sets
  - 451 Japanese sets
- 54,203 set-card memberships
- 49,822 unique cards (21,891 English, 27,931 Japanese)
- Unnumbered Energies excluded from both catalogs; Topps Series excluded from
  the English catalog
- French and German set releases excluded

## Japanese Catalog

- 451 sets, 27,931 unique cards, 28,492 set-card memberships
- Original Base Set is listed as `Expansion Pack` (`11182`)
- Jungle is `11201`; Fossil is `Mystery of the Fossils` (`11172`)
- Japanese collector numbers use `No. 001`; `printed_total` is usually unknown
- Card fronts are JPG, up to 356px wide; English fronts are WebP, up to 733px
- Set logos and symbols use a mix of WebP and PNG
- `25th Anniversary Creatures Deck` (`11651`) has no card list on the source
- Japanese rows are marked `language = 'ja'`

## Files

- `data/pkmndb.sqlite3` — canonical SQLite database.
- `dist/sets.json` — set catalog.
- `dist/cards.jsonl` — one unique card per line, including `set_ids`.
- `dist/sets/<set_id>.json` — set metadata plus its ordered card list.
- `dist/manifest.json` — snapshot counts and schema version.

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

## Notes

Unofficial Pokemon TCG data index. Card names and artwork remain the property
of their respective owners. No affiliation or endorsement is claimed.
