import json
import re
from collections import Counter, defaultdict
from pathlib import Path

root = Path(r"C:\Users\blogu\.VisualStudio\Projects\Pokemon Applications")
pkmndb = root / "PKMNDB"
oldpv = Path(r"C:\Users\blogu\AppData\Local\Temp\kilo\pv-old")
scan = pkmndb / "data" / "scan" / "canonical"

sets = json.loads((pkmndb / "dist" / "sets.json").read_text(encoding="utf-8"))
set_by_id = {s["id"]: s for s in sets}
cmap = json.loads((scan / "canonical-set-map.json").read_text(encoding="utf-8"))
canonical_sets = {
    s["id"]: s for s in json.loads((scan / "canonical-sets.json").read_text(encoding="utf-8"))
}
pv_set_map = json.loads((scan / "pocketvault-set-map.json").read_text(encoding="utf-8"))
ct_set_map = json.loads((scan / "cardtable-set-map.json").read_text(encoding="utf-8"))
vcards = []
for name in ("cards.json", "cards.ja.json", "cards.zh.json"):
    vcards.extend(json.loads((oldpv / name).read_text(encoding="utf-8"))["cards"])
ct_cards = json.loads(
    (pkmndb / "data" / "scan" / "cardtable-catalog.json").read_text(encoding="utf-8")
)["cards"]


def clean_number(value):
    value = re.sub(r"^No\.\s*", "", str(value or "").strip(), flags=re.I)
    return value.split("/")[0].strip().lstrip("0") or "0"


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


by_set = defaultdict(list)
canonical_cards = []
for item in sets:
    pk_id = item["id"]
    cid = cmap.get(str(pk_id))
    if not cid:
        continue
    path = pkmndb / "dist" / "sets" / f"{pk_id}.json"
    if not path.exists():
        continue
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    used = set()
    for card in cards:
        base = f"{cid}-{clean_number(card.get('number'))}"
        card_id = base
        suffix = 1
        while card_id in used:
            suffix += 1
            card_id = f"{base}-{suffix}"
        used.add(card_id)
        record = {
            "id": card_id,
            "setId": cid,
            "number": str(card.get("number") or ""),
            "name": card.get("name") or "",
            "rarity": card.get("rarity"),
            "image": card.get("image_url") or None,
            "language": item.get("language", "en"),
            "sourceId": card.get("id"),
            "sourceSetId": pk_id,
        }
        canonical_cards.append(record)
        by_set[cid].append(record)

# TCG Pocket extras keep their existing ids.
extra_set_ids = {
    old
    for old, canonical in pv_set_map.items()
    if old == canonical
    and old not in set(cmap.values())
    and not old.startswith(("pkmndb-", "ja-pkmndb-", "zh-pkmndb-"))
}
for card in vcards:
    old_set = str(card["setId"])
    if old_set not in extra_set_ids:
        continue
    record = {
        "id": str(card["id"]),
        "setId": old_set,
        "number": str(card.get("number") or ""),
        "name": card.get("name") or "",
        "rarity": card.get("rarity"),
        "image": card.get("image") or None,
        "language": card.get("language", "en"),
        "sourceId": card["id"],
        "sourceSetId": old_set,
    }
    canonical_cards.append(record)
    by_set[old_set].append(record)

# Membership indexes for mapping old app ids.
for set_id, info in canonical_sets.items():
    info["total"] = len(by_set.get(set_id, []))
for set_id in extra_set_ids:
    canonical_sets.setdefault(
        set_id,
        {
            "id": set_id,
            "name": set_id,
            "series": "Pokémon TCG Pocket",
            "releaseDate": "",
            "language": "en",
            "code": set_id,
        },
    )
    canonical_sets[set_id]["total"] = len(by_set.get(set_id, []))

# Membership indexes for mapping old app ids.
members_by_number = defaultdict(lambda: defaultdict(list))
members_by_source = defaultdict(lambda: defaultdict(list))
members_by_name = defaultdict(lambda: defaultdict(list))
for card in canonical_cards:
    members_by_number[card["setId"]][clean_number(card["number"])].append(card)
    if card.get("sourceId") is not None:
        members_by_source[card["setId"]][str(card["sourceId"])].append(card)
    if card.get("name"):
        members_by_name[card["setId"]][norm(card["name"])].append(card)


def pick(cards):
    return cards[0] if len(cards) == 1 else None


def map_old_card(card, set_map, extra_ids):
    old_set = str(card["setId"])
    canonical = set_map.get(old_set, old_set)
    if old_set in extra_ids:
        return str(card["id"])
    old_id = str(card["id"])
    if old_id.startswith(f"{canonical}-"):
        candidate = old_id
        if any(c["id"] == candidate for c in by_set[canonical]):
            return candidate
    raw = re.sub(r"^(?:ja-)?pkmndb-(\d+)$", r"\1", old_id)
    if raw != old_id and members_by_source[canonical].get(raw):
        return pick(members_by_source[canonical][raw])["id"] or old_id
    hits = members_by_number[canonical].get(clean_number(card.get("number")), [])
    if len(hits) > 1 and card.get("name"):
        named = [c for c in hits if norm(c.get("name")) == norm(card.get("name"))]
        if len(named) == 1:
            return named[0]["id"]
    if len(hits) == 1:
        return hits[0]["id"]
    if card.get("name"):
        hits = members_by_name[canonical].get(norm(card.get("name")), [])
        if len(hits) == 1:
            return hits[0]["id"]
    return old_id


pv_card_map = {}
for card in vcards:
    old = str(card["id"])
    new = map_old_card(card, pv_set_map, extra_set_ids)
    if old != new:
        pv_card_map[old] = new
ct_card_map = {}
for card in ct_cards:
    old = str(card["id"])
    new = map_old_card(card, ct_set_map, set())
    if old != new:
        ct_card_map[old] = new

# Add only the old PocketVault variants that have no canonical membership (e.g.
# ecard holo variants), under their canonical set, so collections never orphan.
existing_ids = {card["id"] for card in canonical_cards}
added = 0
for card in vcards:
    old = str(card["id"])
    if pv_card_map.get(old, old) in existing_ids:
        continue
    old_set = str(card["setId"])
    canonical = pv_set_map.get(old_set, old_set)
    if canonical not in canonical_sets:
        continue
    record = {
        "id": old,
        "setId": canonical,
        "number": str(card.get("number") or ""),
        "name": card.get("name") or "",
        "rarity": card.get("rarity"),
        "image": card.get("image") or None,
        "language": card.get("language", "en"),
        "sourceId": card["id"],
        "sourceSetId": old_set,
    }
    canonical_cards.append(record)
    by_set[canonical].append(record)
    existing_ids.add(old)
    added += 1

for set_id, info in canonical_sets.items():
    info["total"] = len(by_set.get(set_id, []))

scan.mkdir(parents=True, exist_ok=True)
(scan / "canonical-cards.jsonl").write_text(
    "\n".join(json.dumps(card) for card in canonical_cards) + "\n", encoding="utf-8"
)
(scan / "canonical-sets.json").write_text(
    json.dumps(list(canonical_sets.values()), indent=2) + "\n", encoding="utf-8"
)
(scan / "pocketvault-card-map.json").write_text(
    json.dumps(pv_card_map, separators=(",", ":")), encoding="utf-8"
)
(scan / "cardtable-card-map.json").write_text(
    json.dumps(ct_card_map, separators=(",", ":")), encoding="utf-8"
)

print("canonical sets", len(canonical_sets), "cards", len(canonical_cards))
print("languages", Counter(c["language"] for c in canonical_cards))
print("extra sets", len(extra_set_ids), json.dumps(sorted(extra_set_ids), ensure_ascii=True))
print("pv map", len(pv_card_map), "ct map", len(ct_card_map))
print("samples", json.dumps({k: pv_card_map.get(k) for k in ("base1-4", "pkmndb-1219-004", "ja-E1-001", "ja-pkmndb-29164", "B2a-001")}, ensure_ascii=True))
