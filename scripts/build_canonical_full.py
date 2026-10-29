import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument(
    "--old-pocketvault",
    type=Path,
    default=Path(
        os.environ.get(
            "PKMNDB_OLD_POCKETVAULT",
            r"C:\Users\blogu\AppData\Local\Temp\kilo\pv-old",
        )
    ),
)
parser.add_argument("--generated-at", default=date.today().isoformat())
args = parser.parse_args()

pkmndb = Path(__file__).resolve().parents[1]
oldpv = args.old_pocketvault
canon = pkmndb / "data" / "scan" / "canonical"
out = pkmndb / "dist" / "canonical"
(out / "sets").mkdir(parents=True, exist_ok=True)

sets = {s["id"]: s for s in json.loads((pkmndb / "dist" / "sets.json").read_text(encoding="utf-8"))}
set_map = json.loads((pkmndb / "data" / "scan" / "canonical" / "canonical-set-map.json").read_text(encoding="utf-8"))
canon_sets = {s["id"]: s for s in json.loads((canon / "canonical-sets.json").read_text(encoding="utf-8"))}
canon_cards = [
    json.loads(line)
    for line in (canon / "canonical-cards.jsonl").read_text(encoding="utf-8").splitlines()
    if line
]
pkmn_cards = {
    card["id"]: card
    for card in (
        json.loads(line)
        for line in (pkmndb / "dist" / "cards.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    )
}
vcards = {}
pv_meta = {}
if oldpv.exists():
    for name in ("cards.json", "cards.ja.json", "cards.zh.json"):
        path = oldpv / name
        if not path.exists():
            print(f"warning: legacy PocketVault file not found: {path}")
            continue
        for card in json.loads(path.read_text(encoding="utf-8"))["cards"]:
            vcards[str(card["id"])] = card
    wotc_path = oldpv / "wotcSets.ts"
    if wotc_path.exists():
        wotc_text = wotc_path.read_text(encoding="utf-8")
        for m in re.finditer(
            r'\{ id: "([^"]+)", name: "([^"]+)", series: "([^"]+)", releaseDate: "([^"]+)", total: (\d+)(?:, symbol: "([^"]+)")?(?:, logo: "([^"]+)")? \}',
            wotc_text,
        ):
            pv_meta[m.group(1)] = {
                "name": m.group(2),
                "series": m.group(3),
                "releaseDate": m.group(4),
                "symbol": m.group(6),
                "logo": m.group(7),
            }
    else:
        print(f"warning: legacy PocketVault file not found: {wotc_path}")
else:
    print(
        f"warning: legacy PocketVault data not found at {oldpv}; "
        "using canonical scan fields for fallback cards"
    )


def number_value(value):
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else 0


def clean_number(value):
    value = re.sub(r"^No\.\s*", "", str(value or "").strip(), flags=re.I)
    return value.split("/")[0].strip().lstrip("0") or "0"


by_set = defaultdict(list)
full_cards = []
for card in canon_cards:
    src = None
    if isinstance(card.get("sourceId"), int) or str(card.get("sourceId", "")).isdigit():
        src = pkmn_cards.get(int(card["sourceId"]))
    if src:
        record = {
            "id": card["id"],
            "name": card.get("name") or src.get("name") or "",
            "set_id": card["setId"],
            "set_ids": [card["setId"]],
            "number": str(src.get("number") or card.get("number") or ""),
            "number_value": src.get("number_value") or number_value(src.get("number")),
            "printed_total": src.get("printed_total"),
            "rarity": src.get("rarity") or card.get("rarity"),
            "image_url": src.get("image_url") or card.get("image"),
            "image_thumb_url": src.get("image_thumb_url"),
            "image_sha256": src.get("image_sha256"),
            "image_bytes": src.get("image_bytes"),
            "source_url": src.get("source_url"),
            "language": card.get("language") or src.get("language") or "en",
            "scraped_at": src.get("scraped_at"),
            "position": len(by_set[card["setId"]]) + 1,
        }
    else:
        old = vcards.get(str(card.get("sourceId")))
        record = {
            "id": card["id"],
            "name": card.get("name") or (old.get("name") if old else "") or "",
            "set_id": card["setId"],
            "set_ids": [card["setId"]],
            "number": str(old.get("number") if old else card.get("number") or ""),
            "number_value": number_value(old.get("number") if old else card.get("number")),
            "printed_total": None,
            "rarity": (old.get("rarity") if old else None) or card.get("rarity"),
            "image_url": (old.get("image") if old else None) or card.get("image"),
            "image_thumb_url": None,
            "image_sha256": None,
            "image_bytes": None,
            "source_url": None,
            "language": card.get("language") or "en",
            "scraped_at": None,
            "position": len(by_set[card["setId"]]) + 1,
        }
    by_set[card["setId"]].append(record)
    full_cards.append(record)

missing_names = [
    card["id"]
    for card in full_cards
    if not isinstance(card.get("name"), str) or not card["name"].strip()
]
if missing_names:
    sample = ", ".join(missing_names[:5])
    raise SystemExit(f"{len(missing_names)} canonical cards have no name: {sample}")

full_sets = []
for set_id, info in canon_sets.items():
    pkmn = None
    for pk_id, cid in set_map.items():
        if cid == set_id and int(pk_id) in sets:
            pkmn = sets[int(pk_id)]
            break
    if pkmn:
        full_sets.append(
            {
                "id": set_id,
                "name": info.get("name") or pkmn["name"],
                "code": pkmn.get("code"),
                "series": info.get("series") or pkmn.get("series") or "",
                "release_date": info.get("releaseDate") or pkmn.get("release_date") or "",
                "date_text": pkmn.get("date_text") or "",
                "card_count": len(by_set.get(set_id, [])),
                "logo_url": pkmn.get("logo_url"),
                "symbol_url": pkmn.get("symbol_url"),
                "source_url": pkmn.get("source_url"),
                "released": bool(pkmn.get("released")),
                "language": info.get("language") or "en",
            }
        )
    else:
        meta = pv_meta.get(set_id, {})
        full_sets.append(
            {
                "id": set_id,
                "name": meta.get("name") or info.get("name") or set_id,
                "code": set_id,
                "series": meta.get("series") or "Other",
                "release_date": meta.get("releaseDate") or "",
                "date_text": "",
                "card_count": len(by_set.get(set_id, [])),
                "logo_url": meta.get("logo"),
                "symbol_url": meta.get("symbol"),
                "source_url": None,
                "released": True,
                "language": "en",
            }
        )

(out / "sets.json").write_text(json.dumps(full_sets, indent=2) + "\n", encoding="utf-8")
(out / "cards.jsonl").write_text(
    "\n".join(json.dumps(card) for card in full_cards) + "\n", encoding="utf-8"
)
for set_id, cards in by_set.items():
    set_info = next((s for s in full_sets if s["id"] == set_id), None)
    (out / "sets" / f"{set_id}.json").write_text(
        json.dumps({"set": set_info, "cards": cards}), encoding="utf-8"
    )
(out / "manifest.json").write_text(
    json.dumps(
        {
            "schema_version": 1,
            "generated_at": args.generated_at,
            "sets": len(full_sets),
            "cards": len(full_cards),
            "languages": dict(Counter(card["language"] for card in full_cards)),
            "image_base_url": "https://pub-54a82c9e988c459da62f95d0bd9c78d9.r2.dev/",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("canonical full", len(full_sets), "sets", len(full_cards), "cards")
print("languages", Counter(card["language"] for card in full_cards))
