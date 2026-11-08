from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "dist"
DEFAULT_SCAN = ROOT / "data" / "scan" / "canonical"


def clean_number(value: object) -> str:
    text = re.sub(r"^No\.\s*", "", str(value or "").strip(), flags=re.I)
    return text.split("/")[0].strip().lstrip("0") or "0"


def read_json(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: {error}") from error


def read_jsonl(path: Path):
    rows = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    raise SystemExit(f"{path}:{line_number}: {error}") from error
                if not isinstance(row, dict):
                    raise SystemExit(f"{path}:{line_number}: expected a JSON object")
                rows.append(row)
    except OSError as error:
        raise SystemExit(f"{path}: {error}") from error
    return rows


def write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def build_records(source: dict, canonical_set_id: str, source_set_id: int, language: str):
    used: set[str] = set()
    records = []
    for card in source.get("cards") or []:
        card_name = card.get("name")
        if not isinstance(card_name, str) or not card_name.strip():
            raise SystemExit(f"card {card.get('id')!r} in set {source_set_id} has no name")
        source_card_id = card.get("id")
        if source_card_id is None:
            raise SystemExit(f"card {card_name!r} in set {source_set_id} has no source id")
        number = str(card.get("number") or "")
        if not number.strip():
            raise SystemExit(f"card {card_name!r} in set {source_set_id} has no number")
        base = f"{canonical_set_id}-{clean_number(number)}"
        card_id = base
        suffix = 1
        while card_id in used:
            suffix += 1
            card_id = f"{base}-{suffix}"
        used.add(card_id)
        records.append(
            {
                "id": card_id,
                "setId": canonical_set_id,
                "number": number,
                "name": card_name,
                "rarity": card.get("rarity"),
                "image": card.get("image_url") or None,
                "language": language,
                "sourceId": source_card_id,
                "sourceSetId": source_set_id,
            }
        )
    return records


def replace_set_records(existing: list[dict], canonical_set_id: str, records: list[dict]):
    result = []
    inserted = False
    for row in existing:
        if row.get("setId") == canonical_set_id:
            if not inserted:
                result.extend(records)
                inserted = True
            continue
        result.append(row)
    if not inserted:
        result.extend(records)
    return result


def validate_records(records: list[dict]) -> None:
    ids = set()
    for record in records:
        card_id = record.get("id")
        if not isinstance(card_id, str) or not card_id:
            raise SystemExit(f"canonical card has no id: {record!r}")
        if card_id in ids:
            raise SystemExit(f"duplicate canonical card id: {card_id}")
        ids.add(card_id)
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SystemExit(f"canonical card {card_id} has no name")


def run(args) -> None:
    dist = Path(args.dist)
    scan = Path(args.scan)
    source_path = dist / "sets" / f"{args.set_id}.json"
    if not source_path.exists():
        raise SystemExit(f"{source_path} does not exist; export the set before updating canonical data")
    source = read_json(source_path)
    source_set = source.get("set")
    if not isinstance(source_set, dict):
        raise SystemExit(f"{source_path}: missing set object")
    if source_set.get("id") != args.set_id:
        raise SystemExit(f"{source_path}: set id {source_set.get('id')!r} does not match {args.set_id}")
    if not isinstance(source.get("cards"), list):
        raise SystemExit(f"{source_path}: missing cards array")

    canonical_set_map = read_json(scan / "canonical-set-map.json")
    if not isinstance(canonical_set_map, dict):
        raise SystemExit(f"{scan / 'canonical-set-map.json'}: expected a JSON object")
    canonical_set_id = canonical_set_map.get(str(args.set_id))
    if not canonical_set_id:
        raise SystemExit(
            f"no canonical-set-map entry for set {args.set_id}; register the set before updating"
        )
    sources = [key for key, value in canonical_set_map.items() if value == canonical_set_id]
    if len(sources) != 1:
        raise SystemExit(
            f"canonical set {canonical_set_id} is shared by {len(sources)} PKMNDB sets; "
            "this updater only supports 1:1 mappings"
        )

    canonical_sets = read_json(scan / "canonical-sets.json")
    if not isinstance(canonical_sets, list):
        raise SystemExit(f"{scan / 'canonical-sets.json'}: expected a JSON array")
    set_entry = next((item for item in canonical_sets if item.get("id") == canonical_set_id), None)
    if set_entry is None:
        raise SystemExit(f"canonical set {canonical_set_id} is missing from canonical-sets.json")

    language = source_set.get("language")
    if language not in {"en", "ja", "zh"}:
        raise SystemExit(f"set {args.set_id} has unsupported language {language!r}")
    entry_language = set_entry.get("language")
    if entry_language and entry_language != language:
        raise SystemExit(
            f"set {args.set_id} language {language!r} does not match "
            f"canonical set language {entry_language!r}"
        )

    existing = read_jsonl(scan / "canonical-cards.jsonl")
    records = build_records(source, canonical_set_id, args.set_id, language)
    existing_for_set = [row for row in existing if row.get("setId") == canonical_set_id]
    if not records and existing_for_set and not getattr(args, "allow_empty", False):
        raise SystemExit(
            f"refusing to empty {canonical_set_id}: source set {args.set_id} has no cards"
        )
    all_records = replace_set_records(existing, canonical_set_id, records)
    validate_records(all_records)

    if args.dry_run:
        print(
            f"would update {canonical_set_id} from set {args.set_id}: "
            f"{len(records)} cards, {len(existing)} -> {len(all_records)} canonical cards, "
            f"first={records[0]['id'] if records else None}, "
            f"last={records[-1]['id'] if records else None}"
        )
        return

    set_entry["total"] = len(records)
    write_atomic(
        scan / "canonical-cards.jsonl",
        "\n".join(json.dumps(record) for record in all_records) + "\n",
    )
    write_atomic(
        scan / "canonical-sets.json",
        json.dumps(canonical_sets, indent=2) + "\n",
    )
    write_atomic(
        scan / "canonical-catalog.json",
        json.dumps({"cards": all_records}, separators=(",", ":")),
    )
    print(
        f"updated {canonical_set_id} from set {args.set_id}: "
        f"{len(records)} cards, {len(existing)} -> {len(all_records)} canonical cards"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set-id", type=int, required=True)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--scan", type=Path, default=DEFAULT_SCAN)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
