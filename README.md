# PKMNDB

Pokemon TCG set and card data for English/international releases, derived from
[TCGCollector](https://www.tcgcollector.com/).

## Snapshot

Last updated: 2026-10-18

- 333 sets (332 released, 1 upcoming)
- 25,711 set-card memberships
- 21,891 unique cards
- Unnumbered Energies and Topps Series sets excluded
- French and German set releases excluded

## Files

- `data/pkmndb.sqlite3` — canonical SQLite database.
- `dist/sets.json` — set catalog.
- `dist/cards.jsonl` — one unique card per line, including `set_ids`.
- `dist/sets/<set_id>.json` — set metadata plus its ordered card list.
- `dist/manifest.json` — snapshot counts and schema version.

Card front image binaries are not stored in this repository because the full
set is over 3 GB. The database includes each card's source image URL, local image
path, SHA-256, and byte size. Consumers can use `image_url` or cache the images
locally using the recorded paths.

## Schema

`sets`:

- `id` — TCGCollector set ID (stable numeric identifier)
- `name`, `code`, `series`
- `release_date`, `date_text`, `released`
- `card_count`
- `logo_url`, `symbol_url`, `logo_path`, `symbol_path`
- `source_url`, `scraped_at`

`cards`:

- `id` — TCGCollector card ID (stable numeric identifier)
- `set_id` — canonical set ID
- `name`, `number`, `number_value`, `printed_total`, `rarity`
- `image_url`, `image_thumb_url`
- `image_path`, `image_sha256`, `image_bytes`
- `source_url`, `scraped_at`

`set_cards`:

- `set_id`, `card_id`, `position`
- A card can belong to multiple sets; set lists must be read through this table.

`meta` stores sync timestamps.

## Identifiers

Use `sets.id` and `cards.id` as the stable keys. Set codes are not unique, and
collector numbers can collide within a set, so neither is safe as a primary key.
The `(set_id, card_id)` pair identifies a set membership.

## Attribution

Pokemon card data, names, and images are the intellectual property of their
respective owners. This repository is an unofficial data index and is not
affiliated with or endorsed by TCGCollector, The Pokemon Company, Nintendo,
Creatures, or Wizards of the Coast.
