import json
import re
from collections import Counter
from pathlib import Path

root = Path(r"C:\Users\blogu\.VisualStudio\Projects\Pokemon Applications")
pkmndb = root / "PKMNDB"
vault = root / "PocketVaultTCG"
canon = pkmndb / "data" / "scan" / "canonical"

pkmn_sets = {s["id"]: s for s in json.loads((pkmndb / "dist" / "sets.json").read_text(encoding="utf-8"))}
canon_sets = {s["id"]: s for s in json.loads((canon / "canonical-sets.json").read_text(encoding="utf-8"))}
canon_cards = [
    json.loads(line)
    for line in (canon / "canonical-cards.jsonl").read_text(encoding="utf-8").splitlines()
    if line
]
canon_set_map = json.loads((canon / "canonical-set-map.json").read_text(encoding="utf-8"))
pv_card_map = json.loads((canon / "pocketvault-card-map.json").read_text(encoding="utf-8"))
pv_set_map = json.loads((canon / "pocketvault-set-map.json").read_text(encoding="utf-8"))

# Old PocketVault set metadata (used for TCG Pocket extras and set icons).
wotc_text = (Path(r"C:\Users\blogu\AppData\Local\Temp\kilo\pv-old") / "wotcSets.ts").read_text(encoding="utf-8")
pv_set_meta = {}
for m in re.finditer(
    r'\{ id: "([^"]+)", name: "([^"]+)", series: "([^"]+)", releaseDate: "([^"]+)", total: (\d+)(?:, symbol: "([^"]+)")?(?:, logo: "([^"]+)")? \}',
    wotc_text,
):
    pv_set_meta[m.group(1)] = {
        "name": m.group(2),
        "series": m.group(3),
        "releaseDate": m.group(4),
        "total": int(m.group(5)),
        "symbol": m.group(6),
        "logo": m.group(7),
    }

# Canonical set metadata: PKMNDB values, with PocketVault extras.
canonical_meta = {}
for set_id, info in canon_sets.items():
    canonical_meta[set_id] = {
        "id": set_id,
        "name": info.get("name") or set_id,
        "series": info.get("series") or "Other",
        "releaseDate": info.get("releaseDate") or "",
        "language": info.get("language") or "en",
        "symbol": None,
        "logo": None,
    }
for pid, info in pkmn_sets.items():
    cid = canon_set_map.get(str(pid))
    if cid and cid in canonical_meta:
        canonical_meta[cid].setdefault("name", info.get("name"))
        if not canonical_meta[cid]["releaseDate"]:
            canonical_meta[cid]["releaseDate"] = info.get("release_date") or ""
        canonical_meta[cid]["symbol"] = canonical_meta[cid]["symbol"] or info.get("symbol_url")
        canonical_meta[cid]["logo"] = canonical_meta[cid]["logo"] or info.get("logo_url")
for set_id, meta in pv_set_meta.items():
    if set_id in canonical_meta:
        canonical_meta[set_id]["name"] = meta["name"]
        canonical_meta[set_id]["series"] = meta["series"]
        canonical_meta[set_id]["releaseDate"] = meta["releaseDate"]
        canonical_meta[set_id]["symbol"] = meta["symbol"]
        canonical_meta[set_id]["logo"] = meta["logo"]

by_set = Counter(card["setId"] for card in canon_cards)


def rarity_holo(rarity):
    value = str(rarity or "").lower()
    if not value:
        return False
    if re.search(r"common|uncommon|promo|none|basic|diamond", value):
        return False
    return bool(re.search(r"rare|holo|shiny|classic|legend|prism|radiant|ace spec", value))


def card_record(card):
    return {
        "id": card["id"],
        "setId": card["setId"],
        "number": card["number"],
        "name": card["name"],
        "image": card.get("image"),
        "rarity": card.get("rarity"),
        "holo": rarity_holo(card.get("rarity")),
        "firstEdition": False,
        "language": card.get("language") or "en",
    }


for language, filename in (("en", "cards.json"), ("ja", "cards.ja.json"), ("zh", "cards.zh.json")):
    cards = [card_record(c) for c in canon_cards if (c.get("language") or "en") == language]
    (vault / "src" / "data" / filename).write_text(
        json.dumps(
            {
                "source": "PKMNDB canonical catalogue",
                "generated": "2026-10-23",
                "note": "Canonical PKMNDB ids; English keyless ids preserved.",
                "cards": cards,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def set_lines(set_ids):
    lines = []
    for set_id in set_ids:
        meta = canonical_meta[set_id]
        total = by_set.get(set_id, 0)
        parts = [
            f'id: {json.dumps(set_id)}',
            f'name: {json.dumps(meta["name"])}',
            f'series: {json.dumps(meta["series"])}',
            f'releaseDate: {json.dumps(meta["releaseDate"])}',
            f'total: {total}',
        ]
        if meta["language"]:
            parts.append(f'language: {json.dumps(meta["language"])}')
        if meta["symbol"]:
            parts.append(f'symbol: {json.dumps(meta["symbol"])}')
        if meta["logo"]:
            parts.append(f'logo: {json.dumps(meta["logo"])}')
        lines.append("  { " + ", ".join(parts) + " },")
    return "\n".join(lines)


for language, filename, name in (
    ("en", "wotcSets.ts", "WOTC_SETS"),
    ("ja", "jpSets.ts", "JP_SETS"),
    ("zh", "zhSets.ts", "ZH_SETS"),
):
    set_ids = sorted(
        set_id
        for set_id, meta in canonical_meta.items()
        if meta["language"] == language and by_set.get(set_id, 0) > 0
    )
    (vault / "src" / "data" / filename).write_text(
        f'import type {{ WotcSet }} from "../types";\n\n'
        f"// Generated from the canonical PKMNDB catalogue on 2026-10-23.\n"
        f"export const {name}: WotcSet[] = [\n{set_lines(set_ids)}\n];\n",
        encoding="utf-8",
    )

changed_cards = {k: v for k, v in pv_card_map.items() if k != v}
changed_sets = {k: v for k, v in pv_set_map.items() if k != v}
(vault / "src" / "data" / "legacy-card-map.json").write_text(
    json.dumps(changed_cards, separators=(",", ":")), encoding="utf-8"
)
(vault / "src" / "data" / "legacy-set-map.json").write_text(
    json.dumps(changed_sets, separators=(",", ":")), encoding="utf-8"
)

seed_path = vault / "src" / "lib" / "seed.ts"
seed = seed_path.read_text(encoding="utf-8")
version = "canonical-pkmndb-2026-10-23"
seed = re.sub(r'const DATA_VERSION = "[^"]*";', f'const DATA_VERSION = "{version}";', seed)
seed_path.write_text(seed, encoding="utf-8")

print("wrote PocketVault canonical data")
print("cards", Counter(c["language"] for c in canon_cards))
print("sets", Counter(m["language"] for m in canonical_meta.values() if by_set.get(m["id"], 0) > 0))
print("legacy card map", len(changed_cards), "legacy set map", len(changed_sets))
