from __future__ import annotations

import argparse
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gen_structured import GenConfig, generate
from .gen_packets import render_packet_for_claim
from .utils import ensure_dir, write_csv, write_jsonl

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="generator",
        description="Synthetic UK motor insurance claims generator (structured + packets).",
    )
    p.add_argument("--n", type=int, default=1000, help="Number of claims")
    p.add_argument("--out", type=str, default="out", help="Output directory")
    p.add_argument("--seed", type=int, default=42, help="Random seed")
    p.add_argument("--hitl-threshold", type=float, default=8000.0, help="HITL threshold (gross loss GBP)")
    p.add_argument("--fraud-rate", type=float, default=0.03, help="Base fraud rate (0-1)")
    p.add_argument("--phi-rate", type=float, default=0.005, help="Rate of PHI injection (forces QUARANTINE)")
    return p

def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    out = Path(args.out)
    ensure_dir(out)
    ensure_dir(out / "tables")
    ensure_dir(out / "claims")

    cfg = GenConfig(
        n_claims=args.n,
        seed=args.seed,
        base_fraud_rate=float(args.fraud_rate),
        hitl_threshold_gbp=float(args.hitl_threshold),
        inject_phi_rate=float(args.phi_rate),
    )

    claims, tables = generate(cfg)

    index_rows: List[Dict[str, Any]] = []
    global_photo_pool: List[Path] = []
    vendor_catalog = tables.get("vendors", [])
    rng = random.Random(args.seed + 999)

    for c in claims:
        claim_dir = out / "claims" / c["claim_id"]
        ensure_dir(claim_dir)

        with_police_report = (c["incident_type"] == "THEFT") or bool(c.get("crime_ref")) or (rng.random() < 0.15)
        vendor = rng.choice(vendor_catalog) if vendor_catalog else {"name": "Demo Garage", "vat_number": "GB000000000"}

        row = render_packet_for_claim(
            claim=c,
            claim_dir=claim_dir,
            rng=random.Random(args.seed + int(c["claim_id"][-3:])),
            vendor=vendor,
            global_photo_pool=global_photo_pool,
            with_police_report=with_police_report,
        )
        index_rows.append(row)

    write_jsonl(out / "index.jsonl", index_rows)
    for name, rows in tables.items():
        write_csv(out / "tables" / f"{name}.csv", rows)

    print(f"Wrote {len(index_rows)} claims to {out.resolve()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
