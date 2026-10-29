import argparse
import json
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAMES = ROOT / "data" / "scan" / "canonical" / "canonical-cards.jsonl"
DEFAULT_CARDS = ROOT / "dist" / "canonical" / "cards.jsonl"
DEFAULT_SETS = ROOT / "dist" / "canonical" / "sets"
DEFAULT_MANIFEST = ROOT / "dist" / "canonical" / "manifest.json"


def read_names(path):
    names = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            card_id = row.get("id")
            name = row.get("name")
            if not isinstance(card_id, str) or not card_id:
                raise SystemExit(f"{path}:{line_number}: missing card id")
            if card_id in names:
                raise SystemExit(f"{path}:{line_number}: duplicate card id {card_id}")
            if not isinstance(name, str) or not name.strip():
                raise SystemExit(f"{path}:{line_number}: missing name for {card_id}")
            names[card_id] = name
    return names


def add_name(record, names, source):
    card_id = record.get("id")
    if not isinstance(card_id, str) or card_id not in names:
        raise SystemExit(f"{source}: no name for card {card_id!r}")
    record.pop("name", None)
    updated = {}
    for key, value in record.items():
        updated[key] = value
        if key == "id":
            updated["name"] = names[card_id]
    if "name" not in updated:
        updated["name"] = names[card_id]
    return updated


def write_atomic(path, text):
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def run(args):
    names = read_names(args.names)
    cards_path = args.cards
    sets_dir = args.sets
    manifest_path = args.manifest

    records = []
    with cards_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            records.append(add_name(record, names, f"{cards_path}:{line_number}"))

    if len(records) != len(names):
        raise SystemExit(f"card count mismatch: {len(records)} rows, {len(names)} names")
    if len({record["id"] for record in records}) != len(records):
        raise SystemExit("duplicate card ids in canonical cards")

    set_files = sorted(sets_dir.glob("*.json"))
    set_card_ids = set()
    set_card_count = 0
    set_updates = []
    for set_path in set_files:
        data = read_json(set_path)
        set_id = data.get("set", {}).get("id")
        cards = data.get("cards", [])
        if set_id != set_path.stem:
            raise SystemExit(f"{set_path}: set id {set_id!r} does not match filename")
        updated_cards = []
        for index, card in enumerate(cards, 1):
            updated = add_name(card, names, f"{set_path}: card {index}")
            if updated["id"] in set_card_ids:
                raise SystemExit(f"{set_path}: duplicate card {updated['id']}")
            set_card_ids.add(updated["id"])
            updated_cards.append(updated)
        set_card_count += len(updated_cards)
        set_updates.append((set_path, data, updated_cards))

    missing_sets = set(names) - set_card_ids
    if missing_sets:
        sample = ", ".join(sorted(missing_sets)[:5])
        raise SystemExit(f"{len(missing_sets)} cards are missing from set files: {sample}")
    if set_card_count != len(records):
        raise SystemExit(f"set files contain {set_card_count} cards, expected {len(records)}")

    manifest = read_json(manifest_path)
    if manifest.get("cards") != len(records):
        raise SystemExit(
            f"manifest cards={manifest.get('cards')} but found {len(records)} records"
        )

    generated_at = args.generated_at or date.today().isoformat()
    manifest["generated_at"] = generated_at

    if not args.dry_run:
        write_atomic(
            cards_path,
            "\n".join(json.dumps(record) for record in records) + "\n",
        )
        for set_path, data, updated_cards in set_updates:
            data["cards"] = updated_cards
            write_atomic(set_path, json.dumps(data))
        write_atomic(manifest_path, json.dumps(manifest, indent=2) + "\n")

    print(
        f"{'checked' if args.dry_run else 'wrote'} {len(records)} cards, "
        f"{len(set_updates)} set files, {len(names)} names, generated_at={generated_at}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", type=Path, default=DEFAULT_NAMES)
    parser.add_argument("--cards", type=Path, default=DEFAULT_CARDS)
    parser.add_argument("--sets", type=Path, default=DEFAULT_SETS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--generated-at")
    parser.add_argument("--dry-run", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
