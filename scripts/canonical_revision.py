import hashlib
import json


def revision_for_cards(cards):
    payload = json.dumps(
        cards,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
