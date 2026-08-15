from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    required = {
        "dashboard.json": {"schema_version", "generated_at", "summary", "laptops", "source_health"},
        "laptops.json": None,
        "offers.json": None,
        "source_health.json": None,
    }
    for filename, keys in required.items():
        path = args.directory / filename
        if not path.exists():
            raise SystemExit(f"Missing generated file: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if keys and not keys.issubset(value):
            raise SystemExit(f"{filename} is missing: {sorted(keys - set(value))}")
    print(f"Validated {len(required)} generated data files in {args.directory}")


if __name__ == "__main__":
    main()

