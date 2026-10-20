"""Command-line entry point for the synthetic model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import ensure_supported_runtime
from .domain.schema import validate
from .services.model_service import run


def main() -> int:
    try:
        ensure_supported_runtime()
    except RuntimeError as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--input",
        type=Path,
        help="synthetic JSON model input; do not use identifiable health data",
    )
    group.add_argument("--demo", action="store_true", help="run a synthetic example")
    args = parser.parse_args()
    try:
        if args.demo:
            source = {
                "age_years": 45,
                "height_m": 1.68,
                "weight_kg": 72,
                "alt_u_l": 42,
                "ast_u_l": 35,
                "platelets_10e9_l": 220,
                "cap_db_m": 285,
                "lsm_kpa": 6.8,
                "reduce_uptake": True,
            }
        else:
            source = json.loads(args.input.read_text(encoding="utf-8"))
        print(json.dumps(run(validate(source)), indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
