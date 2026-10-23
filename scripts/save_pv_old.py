import subprocess
from pathlib import Path

root = Path(r"C:\Users\blogu\.VisualStudio\Projects\Pokemon Applications\PocketVaultTCG")
out = Path(r"C:\Users\blogu\AppData\Local\Temp\kilo\pv-old")
out.mkdir(parents=True, exist_ok=True)
for name in (
    "src/data/cards.json",
    "src/data/cards.ja.json",
    "src/data/cards.zh.json",
    "src/data/wotcSets.ts",
    "src/data/jpSets.ts",
    "src/data/zhSets.ts",
):
    data = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=root)
    target = out / Path(name).name
    target.write_bytes(data)
    print(name, len(data))
