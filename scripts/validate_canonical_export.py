import argparse
import json
import string
from collections import Counter
from pathlib import Path

from canonical_revision import revision_for_cards

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "dist" / "canonical"
EXPECTED_SETS = 945
EXPECTED_CARDS = 69898
EXPECTED_SET_FILES = 941
LANGUAGES = {"en", "ja", "zh"}
REQUIRED_CARD_FIELDS = ("id", "name", "set_id", "number", "language")


def fail(message):
    raise SystemExit(f"canonical export invalid: {message}")


def non_empty_text(value):
    return isinstance(value, str) and bool(value.strip())


def read_json(path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{path}: {error}")


def read_jsonl(path):
    rows = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as error:
                    fail(f"{path}:{line_number}: {error}")
                if not isinstance(row, dict):
                    fail(f"{path}:{line_number}: expected a JSON object")
                rows.append(row)
    except OSError as error:
        fail(f"{path}: {error}")
    return rows


def require_card_fields(card, source):
    for field in REQUIRED_CARD_FIELDS:
        if not non_empty_text(card.get(field)):
            fail(f"{source}: card {card.get('id')!r} has an empty {field}")
    if card["language"] not in LANGUAGES:
        fail(f"{source}: card {card['id']} has unknown language {card['language']!r}")


def validate(dist):
    manifest = read_json(dist / "manifest.json")
    sets = read_json(dist / "sets.json")
    cards = read_jsonl(dist / "cards.jsonl")

    if not isinstance(sets, list):
        fail("sets.json must be a bare JSON array")
    if manifest.get("schema_version") != 1:
        fail(f"manifest schema_version is {manifest.get('schema_version')!r}, expected 1")
    if len(sets) != EXPECTED_SETS:
        fail(f"sets.json has {len(sets)} sets, expected {EXPECTED_SETS}")
    if len(cards) != EXPECTED_CARDS:
        fail(f"cards.jsonl has {len(cards)} cards, expected {EXPECTED_CARDS}")
    if manifest.get("sets") != len(sets):
        fail(f"manifest sets={manifest.get('sets')} but sets.json has {len(sets)}")
    if manifest.get("cards") != len(cards):
        fail(f"manifest cards={manifest.get('cards')} but cards.jsonl has {len(cards)}")

    set_by_id = {}
    for set_ in sets:
        set_id = set_.get("id")
        if not non_empty_text(set_id):
            fail("sets.json contains a set without an id")
        if set_id in set_by_id:
            fail(f"duplicate set id {set_id}")
        if not non_empty_text(set_.get("name")):
            fail(f"set {set_id} has an empty name")
        if set_.get("language") not in LANGUAGES:
            fail(f"set {set_id} has unknown language {set_.get('language')!r}")
        card_count = set_.get("card_count")
        if not isinstance(card_count, int) or card_count < 0:
            fail(f"set {set_id} has invalid card_count {card_count!r}")
        revision = set_.get("revision")
        if (
            not isinstance(revision, str)
            or len(revision) != 64
            or not set(revision) <= set(string.hexdigits.lower())
        ):
            fail(f"set {set_id} has invalid revision {revision!r}")
        set_by_id[set_id] = set_

    card_ids = set()
    by_set = Counter()
    for card in cards:
        require_card_fields(card, "cards.jsonl")
        card_id = card["id"]
        if card_id in card_ids:
            fail(f"duplicate card id {card_id}")
        card_ids.add(card_id)
        if card["set_id"] not in set_by_id:
            fail(f"card {card_id} belongs to unknown set {card['set_id']}")
        by_set[card["set_id"]] += 1

    languages = Counter(card["language"] for card in cards)
    if manifest.get("languages") != dict(languages):
        fail(f"manifest languages={manifest.get('languages')} but cards.jsonl has {dict(languages)}")

    set_files = sorted((dist / "sets").glob("*.json"))
    if len(set_files) != EXPECTED_SET_FILES:
        fail(f"found {len(set_files)} per-set files, expected {EXPECTED_SET_FILES}")

    file_counts = {}
    seen = set()
    for path in set_files:
        data = read_json(path)
        set_ = data.get("set")
        file_cards = data.get("cards")
        if not isinstance(set_, dict) or not isinstance(file_cards, list):
            fail(f"{path}: expected {{set, cards}}")
        set_id = set_.get("id")
        if set_id != path.stem:
            fail(f"{path}: set id {set_id!r} does not match the filename")
        if set_id not in set_by_id:
            fail(f"{path}: unknown set id {set_id!r}")
        for card in file_cards:
            require_card_fields(card, str(path))
            if card["set_id"] != set_id:
                fail(f"{path}: card {card['id']} has set_id {card['set_id']}")
            if card["id"] in seen:
                fail(f"{path}: duplicate card {card['id']}")
            seen.add(card["id"])
        if set_.get("card_count") != len(file_cards):
            fail(f"{path}: card_count {set_.get('card_count')} but {len(file_cards)} cards")
        if set_by_id[set_id]["card_count"] != len(file_cards):
            fail(
                f"{path}: sets.json card_count {set_by_id[set_id]['card_count']} "
                f"but {len(file_cards)} cards"
            )
        if set_.get("revision") != set_by_id[set_id]["revision"]:
            fail(f"{path}: revision does not match sets.json")
        if revision_for_cards(file_cards) != set_["revision"]:
            fail(f"{path}: revision does not match its card records")
        file_counts[set_id] = len(file_cards)

    if seen != card_ids:
        missing = sorted(card_ids - seen)[:5]
        extra = sorted(seen - card_ids)[:5]
        fail(f"per-set files do not match cards.jsonl (missing={missing}, extra={extra})")

    for set_id, set_ in set_by_id.items():
        expected = file_counts.get(set_id, 0)
        if set_["card_count"] != expected:
            fail(f"set {set_id} card_count {set_['card_count']} but files have {expected}")
        if by_set[set_id] != expected:
            fail(f"set {set_id} has {by_set[set_id]} cards in cards.jsonl but {expected} in files")

    print(
        f"validated {len(sets)} sets, {len(cards)} cards, "
        f"{len(set_files)} set files, languages={dict(languages)}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    validate(parser.parse_args().dist)


if __name__ == "__main__":
    main()
