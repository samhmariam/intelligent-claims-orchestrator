# Synthetic UK Motor Claims Generator

Creates:
- Structured "claims-shaped" CSV tables in `out/tables/`
- Synthetic claim packets (PDFs + photos + extracted txt) per claim in `out/claims/`
- `out/index.jsonl` with one line per claim

## Run

```bash
python -m generator --n 1000 --out out --seed 42
```

## Notes
- PDFs are generated with `reportlab`.
- Photos are generated with Pillow if available. If Pillow is missing, placeholder `.jpg` files are still created.
- PHI injection (default 0.5%) is synthetic and forces `expected_route=QUARANTINE` in `golden.json`.
