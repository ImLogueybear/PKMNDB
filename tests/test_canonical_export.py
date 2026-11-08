import json
import string
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from canonical_revision import revision_for_cards
SCAN = ROOT / "data" / "scan" / "canonical"
DIST = ROOT / "dist" / "canonical"
EXPECTED_CARDS = 70054
EXPECTED_SETS = 946
EXPECTED_SET_FILES = 943
LANGUAGES = {"en", "ja", "zh"}
REQUIRED_CARD_FIELDS = ("id", "name", "set_id", "number", "language")


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


def assert_card_fields(card, source):
    for field in REQUIRED_CARD_FIELDS:
        value = card.get(field)
        assert isinstance(value, str) and value.strip(), f"{source}: empty {field} on {card.get('id')!r}"
    assert card["language"] in LANGUAGES, f"{source}: bad language {card['language']!r}"


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

    set_ids = {set_["id"] for set_ in sets}
    assert set_ids, "sets.json is empty"
    for set_ in sets:
        assert isinstance(set_["id"], str) and set_["id"].strip()
        assert isinstance(set_["name"], str) and set_["name"].strip()
        assert set_["language"] in LANGUAGES
        assert isinstance(set_["card_count"], int) and set_["card_count"] >= 0
    for card in cards:
        assert_card_fields(card, "cards.jsonl")
        assert card["set_id"] in set_ids, f"card {card['id']} belongs to unknown set {card['set_id']}"


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
            assert_card_fields(card, str(path))
            assert card["set_id"] == set_id
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


def test_delta_reign_set_is_complete():
    sets = {set_["id"]: set_ for set_ in read_json(DIST / "sets.json")}
    set_ = sets["pkmndb-111247"]
    assert set_["name"] == "Delta Reign"
    assert set_["language"] == "en"
    assert set_["released"] is True
    assert set_["release_date"] == "2026-11-06"
    assert set_["card_count"] == 141

    data = read_json(DIST / "sets" / "pkmndb-111247.json")
    cards = data["cards"]
    assert len(cards) == 141
    assert [card["id"] for card in cards] == [
        f"pkmndb-111247-{position}" for position in range(1, 142)
    ]
    assert [card["number"] for card in cards] == [
        f"{position:03d}" for position in range(1, 142)
    ]
    assert cards[0]["name"] == "Heracross"
    assert cards[-1]["name"] == "Mega Rayquaza ex"
    assert all(card.get("image_url") for card in cards)


def test_mcdonalds_collection_2026_set_is_complete():
    sets = {set_["id"]: set_ for set_ in read_json(DIST / "sets.json")}
    set_ = sets["pkmndb-111259"]
    assert set_["name"] == "McDonald's Collection 2026"
    assert set_["language"] == "en"
    assert set_["released"] is True
    assert set_["release_date"] == "2026-11-03"
    assert set_["card_count"] == 15
    assert set_["symbol_url"].endswith("/sets/111259-symbol.webp")

    data = read_json(DIST / "sets" / "pkmndb-111259.json")
    cards = data["cards"]
    assert [card["id"] for card in cards] == [
        f"pkmndb-111259-{position}" for position in range(1, 16)
    ]
    assert [card["number"] for card in cards] == [
        f"{position:03d}" for position in range(1, 16)
    ]
    assert cards[0]["name"] == "Decidueye"
    assert cards[-1]["name"] == "Wooloo"
    assert all(card.get("image_url") for card in cards)


def test_bulbapedia_symbols_are_published():
    source = {set_["id"]: set_ for set_ in read_json(ROOT / "dist" / "sets.json")}
    assert source[111254]["symbol_url"].endswith("/sets/111254-symbol.webp")

    canonical = {set_["id"]: set_ for set_ in read_json(DIST / "sets.json")}
    for set_id, source_id in (
        ("zh-pkmndb-111251", 111251),
        ("zh-pkmndb-111252", 111252),
    ):
        assert canonical[set_id]["symbol_url"].endswith(f"/sets/{source_id}-symbol.webp")


def test_set_revisions_are_deterministic():
    sets = read_json(DIST / "sets.json")
    revision_by_id = {}
    hexdigits = set(string.hexdigits.lower())
    for set_ in sets:
        revision = set_["revision"]
        assert isinstance(revision, str)
        assert len(revision) == 64
        assert set(revision) <= hexdigits
        revision_by_id[set_["id"]] = revision

    for path in sorted((DIST / "sets").glob("*.json")):
        data = read_json(path)
        set_id = data["set"]["id"]
        assert data["set"]["revision"] == revision_by_id[set_id]
        assert data["set"]["revision"] == revision_for_cards(data["cards"])
        assert revision_for_cards(data["cards"]) == revision_for_cards(data["cards"])

    empty_revision = revision_for_cards([])
    for set_ in sets:
        if set_["card_count"] == 0:
            assert set_["revision"] == empty_revision
