from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "dist"


def read_json(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: {error}") from error


def write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def run(args) -> None:
    manifest = read_json(Path(args.manifest))
    sets = manifest.get("sets")
    count = manifest.get("count")
    generated_at = manifest.get("generatedAt")
    if not isinstance(sets, dict):
        raise SystemExit(f"{args.manifest}: missing sets object")
    if not isinstance(count, int) or count < 0:
        raise SystemExit(f"{args.manifest}: invalid count {count!r}")
    if not isinstance(generated_at, str) or not generated_at:
        raise SystemExit(f"{args.manifest}: missing generatedAt")

    dist = Path(args.dist)
    for filename in ("scan-index.json", "scan-index-pocketvault.json"):
        path = dist / filename
        pointer = read_json(path)
        pointer["sets"] = len(sets)
        pointer["cards"] = count
        pointer["generated_at"] = generated_at
        write_atomic(path, json.dumps(pointer, indent=2) + "\n")
        print(f"updated {path}: sets={pointer['sets']} cards={pointer['cards']} generated_at={generated_at}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
