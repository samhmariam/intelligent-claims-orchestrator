# Synthetic UK Motor Claims Generator

Creates:
- Structured "claims-shaped" CSV tables in `out/tables/`
- Synthetic claim packets (PDFs + photos + extracted txt) per claim in `out/claims/`
- `out/index.jsonl` with one line per claim

## Run

```bash
python -m generator --n 1000 --out out --seed 42
```

### Options

- `--n`: Number of claims to generate (default: 1000)
- `--out`: Output directory (default: `out`)
- `--seed`: Random seed for reproducibility (default: 42)
- `--fraud-rate`: Base rate of fraud cases (default: 0.03)
- `--phi-rate`: Rate of PHI injection to trigger quarantine (default: 0.005)
- `--hitl-threshold`: Gross loss threshold in GBP for Human-in-the-loop routing (default: 8000.0)

## Notes
- PDFs are generated with `reportlab`.
- Photos are generated with Pillow if available. If Pillow is missing, placeholder `.jpg` files are still created.
- PHI injection (default 0.5%) is synthetic and forces `expected_route=QUARANTINE` in `golden.json`.

## Data Dictionary

**`out/claims/CLM-xxxxxx/` — per-claim “packet”:**

- `raw/documents/*.pdf` (FNOL, Police Report, Repair Estimate, Invoice, Adjuster Notes)
- `raw/photos/*.jpg` (synthetic photos; uses Pillow if available)
- `extracts/*.txt` (plain-text “extractions” of those PDFs)
- `claim.json` (canonical claim object)
- `golden.json` (expected routing/decision + evidence map)

**`out/index.jsonl`** — one line per claim with paths + expected outcomes
