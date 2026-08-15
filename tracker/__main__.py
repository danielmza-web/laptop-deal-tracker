from __future__ import annotations

import argparse
from pathlib import Path

from tracker.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Laptop Deal Tracker.")
    parser.add_argument("--mode", choices=("all", "watchlist", "discovery"), default="all")
    parser.add_argument("--output", type=Path, default=Path("build-data"))
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--offline", action="store_true", help="Generate the dashboard without network requests.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    dashboard = run_pipeline(root, args.output, args.previous, args.mode, args.offline)
    summary = dashboard["summary"]
    print(f"Sources checked: {len(dashboard['source_health'])}")
    print(f"Tracked laptops: {summary['tracked_laptops']}")
    print(f"Active offers: {summary['active_offers']}")
    print(f"Strong deals: {summary['major_deals']}")


if __name__ == "__main__":
    main()

