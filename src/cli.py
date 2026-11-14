"""Command-line entry point for generation, verification, and the optional API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .anomaly_injector import make_anomaly_scenarios
from .config import DEFAULT_SEED, Scale
from .exporter import export_dataset
from .exporter import dataset_hashes
from .generator import generate
from .validator import validate


def build_parser():
    parser = argparse.ArgumentParser(prog="scheduling-lab", description="Generate and validate reproducible production scheduling data")
    sub = parser.add_subparsers(dest="command", required=True)
    generate_cmd = sub.add_parser("generate", help="generate CSV/JSON/SQLite data and labelled edge-case scenarios")
    generate_cmd.add_argument("--seed", type=int, default=DEFAULT_SEED)
    generate_cmd.add_argument("--skus", type=int, default=100)
    generate_cmd.add_argument("--machines", type=int, default=40)
    generate_cmd.add_argument("--orders", type=int, default=500)
    generate_cmd.add_argument("--materials", type=int, default=200)
    generate_cmd.add_argument("--operations-per-order", type=int, default=4)
    generate_cmd.add_argument("--horizon-days", type=int, default=180)
    generate_cmd.add_argument("--output", type=Path, default=Path("data"))
    generate_cmd.add_argument("--verify-reproducibility", action="store_true", help="run the same seed twice and compare table checksums")
    api_cmd = sub.add_parser("serve", help="start the optional FastAPI dashboard and analysis endpoints")
    api_cmd.add_argument("--data", type=Path, default=Path("data"))
    api_cmd.add_argument("--host", default="127.0.0.1")
    api_cmd.add_argument("--port", type=int, default=8000)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        scale = Scale(args.skus, args.machines, args.orders, args.materials, args.operations_per_order, args.horizon_days)
        data = generate(args.seed, scale)
        report = validate(data)
        if not report["valid"]:
            print(json.dumps(report, indent=2), file=sys.stderr)
            return 1
        scenarios, ground_truth = make_anomaly_scenarios(data)
        hashes = dataset_hashes(data)
        reproducibility = {"checked": False, "identical": None, "first_hashes": hashes, "second_hashes": None}
        if args.verify_reproducibility:
            second = dataset_hashes(generate(args.seed, scale))
            reproducibility.update({"checked": True, "identical": hashes == second, "second_hashes": second})
            if hashes != second:
                print("Reproducibility check failed", file=sys.stderr)
                return 1
        params = {
            "skus": scale.skus, "machines": scale.machines, "orders": scale.orders,
            "materials": scale.materials, "operations_per_order": scale.operations_per_order,
            "horizon_days": scale.horizon_days,
        }
        export_dataset(data, args.output, report, scenarios, ground_truth, hashes, args.seed, params, reproducibility)
        print(json.dumps({
            "output": str(args.output.resolve()), "seed": args.seed, "valid": report["valid"],
            "metrics": report["metrics"], "scenario_count": len(scenarios),
            "reproducibility_identical": reproducibility["identical"],
        }, indent=2))
        return 0
    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("Install API dependencies with: python -m pip install -e \".[api]\"", file=sys.stderr)
            return 2
        os.environ["SCHEDULING_DATA_DIR"] = str(args.data.resolve())
        uvicorn.run("src.api:app", host=args.host, port=args.port, factory=False)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
