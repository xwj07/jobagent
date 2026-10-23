"""Build the Cloudflare Pages frontend using only Python's standard library."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "cloudflare"
STATIC = ROOT / "src" / "jobagent" / "static"

OUTPUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(STATIC, OUTPUT / "static", dirs_exist_ok=True)
shutil.copy2(STATIC / "index.html", OUTPUT / "index.html")
shutil.copy2(STATIC / "evaluation.html", OUTPUT / "evaluation.html")
shutil.copy2(ROOT / "deploy" / "cloudflare" / "_worker.js", OUTPUT / "_worker.js")
print(f"Cloudflare Pages output: {OUTPUT}")
