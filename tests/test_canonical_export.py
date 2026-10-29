import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "data" / "scan" / "canonical"
DIST = ROOT / "dist" / "canonical"
EXPECTED_CARDS = 69898
EXPECTED_SETS = 945
EXPECTED_SET_FILES = 941


def read_jsonl(path):
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise AssertionError(f"{path}:{line_number}: {error}") from error
    return rows


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_manifest_matches_payload():
    manifest = read_json(DIST / "manifest.json")
    sets = read_json(DIST / "sets.json")
    cards = read_jsonl(DIST / "cards.jsonl")

    assert manifest["schema_version"] == 1
    assert manifest["sets"] == len(sets) == EXPECTED_SETS
    assert manifest["cards"] == len(cards) == EXPECTED_CARDS
    assert len({card["id"] for card in cards}) == len(cards)
    assert len({set_["id"] for set_ in sets}) == len(sets)
    assert manifest["languages"] == dict(Counter(card["language"] for card in cards))


def test_every_canonical_card_has_a_name():
    cards = read_jsonl(DIST / "cards.jsonl")
    names = read_jsonl(SCAN / "canonical-cards.jsonl")
    name_by_id = {card["id"]: card["name"] for card in names}

    assert len(name_by_id) == len(names) == EXPECTED_CARDS
    assert all(isinstance(name, str) and name.strip() for name in name_by_id.values())
    assert set(card["id"] for card in cards) == set(name_by_id)

    missing = [
        card["id"]
        for card in cards
        if not isinstance(card.get("name"), str) or not card["name"].strip()
    ]
    assert not missing, f"nameless canonical cards: {missing[:10]}"
    assert all(card["name"] == name_by_id[card["id"]] for card in cards)


def test_every_set_file_has_names_and_matching_metadata():
    sets = read_json(DIST / "sets.json")
    by_id = {set_["id"]: set_ for set_ in sets}
    set_files = sorted((DIST / "sets").glob("*.json"))
    assert len(set_files) == EXPECTED_SET_FILES

    seen = set()
    file_counts = {}
    for path in set_files:
        data = read_json(path)
        set_id = data["set"]["id"]
        assert set_id == path.stem
        assert set_id in by_id
        cards = data["cards"]
        assert data["set"]["card_count"] == len(cards)
        assert len(cards) == by_id[set_id]["card_count"]
        file_counts[set_id] = len(cards)
        for card in cards:
            assert card["set_id"] == set_id
            assert isinstance(card.get("name"), str) and card["name"].strip()
            assert card["id"] not in seen
            seen.add(card["id"])

    global_ids = {card["id"] for card in read_jsonl(DIST / "cards.jsonl")}
    assert seen == global_ids
    for set_id, set_ in by_id.items():
        assert set_["card_count"] == file_counts.get(set_id, 0)


def test_team_rocket_set_identities_are_stable():
    sets = {set_["id"]: set_ for set_ in read_json(DIST / "sets.json")}
    assert sets["base5"]["name"] == "Team Rocket"
    assert sets["base5"]["card_count"] == 83
    assert sets["ex7"]["name"] == "EX Team Rocket Returns"
    assert sets["ex7"]["card_count"] == 111
