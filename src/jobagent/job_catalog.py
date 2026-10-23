"""A checked-in snapshot of public recruitment role and city catalogs."""

import json
from pathlib import Path

CATALOG = json.loads(
    (Path(__file__).parent / "data" / "job_catalog.json").read_text(encoding="utf-8")
)
ROLE_OPTIONS = CATALOG["roles"]
CITY_OPTIONS = CATALOG["cities"]
ROLES = {item["id"]: (item["label"], item["keyword"], item["liepin_path"]) for item in ROLE_OPTIONS}
CITIES = {
    item["id"]: (item["label"], item["liepin_slug"], item["zhilian_code"]) for item in CITY_OPTIONS
}
