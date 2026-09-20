"""CLI: resolve a messy supplier CSV into a multi-tier graph for one company."""

from __future__ import annotations

import argparse
from pathlib import Path

from supply_graph.pipeline import run_pipeline
from supply_graph.sentinels import print_sentinels

DEFAULT_CSV = Path(__file__).resolve().parent / "sentinel-supply-chain.csv"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize, resolve, and map the upstream supplier chain for a company."
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Path to the relationship CSV")
    parser.add_argument(
        "--company",
        default="Global Alloys SARL",
        help="Company to map upstream from (fuzzy-matched to a resolved entity). "
        "This file has no 'NorthGate Textiles S.A. (España)'; closest analogue is "
        "NORTHGATE TRADING SARL or Global Alloys SARL.",
    )
    parser.add_argument("--out", default="output", help="Directory for graph.json and graph.mmd")
    parser.add_argument("--skip-sentinels", action="store_true")
    args = parser.parse_args()

    if not args.skip_sentinels:
        print_sentinels()
        print()

    run_pipeline(args.csv, company=args.company, out_dir=args.out)


if __name__ == "__main__":
    main()
