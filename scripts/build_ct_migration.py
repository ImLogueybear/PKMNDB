import json
import re
from collections import defaultdict
from pathlib import Path

import httpx

root = Path(r"C:\Users\blogu\.VisualStudio\Projects\Pokemon Applications")
pkmndb = root / "PKMNDB"
pv = root / "PocketVaultTCG"
out = pkmndb / "data" / "scan" / "canonical"

canon = [
    json.loads(line)
    for line in (out / "canonical-cards.jsonl").read_text(encoding="utf-8").splitlines()
    if line
]
canon_ids = {c["id"] for c in canon}
ct_set_map = json.loads((out / "cardtable-set-map.json").read_text(encoding="utf-8"))
pv_set_map = json.loads((pv / "src" / "data" / "legacy-set-map.json").read_text(encoding="utf-8"))
old_map = json.loads((pv / "src" / "data" / "legacy-card-map.json").read_text(encoding="utf-8"))
ct_catalog = json.loads(
    (pkmndb / "data" / "scan" / "cardtable-catalog.json").read_text(encoding="utf-8")
)["cards"]
index = httpx.get(
    "https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/scan/cardtable/index.json",
    timeout=60,
).json()


def clean_number(value):
    value = re.sub(r"^No\.\s*", "", str(value or "").strip(), flags=re.I)
    return value.split("/")[0].strip().lstrip("0") or "0"


by_set_number = defaultdict(lambda: defaultdict(list))
for card in canon:
    by_set_number[card["setId"]][clean_number(card["number"])].append(card)

# Old cards from both the current catalog and the published index.
old = []
for card in ct_catalog:
    old.append(
        {
            "id": str(card["id"]),
            "setId": str(card["setId"]),
            "number": str(card.get("number") or ""),
            "name": card.get("name") or "",
        }
    )
for set_id, entry in index["sets"].items():
    for card_id, number in zip(entry["ids"], entry.get("numbers", [])):
        old.append(
            {"id": str(card_id), "setId": str(set_id), "number": str(number), "name": ""}
        )

counters = defaultdict(int)
mapping = dict(old_map)
for card in old:
    old_id = card["id"]
    if old_id in canon_ids:
        continue
    canonical_set = (
        ct_set_map.get(card["setId"])
        or pv_set_map.get(card["setId"])
        or card["setId"]
    )
    number = clean_number(card["number"])
    candidates = by_set_number[canonical_set].get(number, [])
    if not candidates:
        continue
    chosen = None
    if card["name"]:
        named = [c for c in candidates if c["name"].lower() == card["name"].lower()]
        if len(named) == 1:
            chosen = named[0]
    if chosen is None:
        key = (canonical_set, number)
        chosen = candidates[counters[key] % len(candidates)]
        counters[key] += 1
    if chosen["id"] != old_id:
        mapping[old_id] = chosen["id"]

(pv / "src" / "data" / "legacy-card-map.json").write_text(
    json.dumps(mapping, separators=(",", ":")), encoding="utf-8"
)
set_map = {k: v for k, v in {**pv_set_map, **ct_set_map}.items() if k != v}
(pv / "src" / "data" / "legacy-set-map.json").write_text(
    json.dumps(set_map, separators=(",", ":")), encoding="utf-8"
)
missing = [
    card["id"]
    for card in old
    if mapping.get(card["id"], card["id"]) not in canon_ids
]
print("old entries", len(old), "mapping", len(mapping), "missing", len(missing), missing[:10])
