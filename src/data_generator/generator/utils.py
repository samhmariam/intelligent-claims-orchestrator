from __future__ import annotations

import csv
import json
import math
import random
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import datetime as dt

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def iso_date(d: dt.date) -> str:
    return d.isoformat()

def iso_dt(t: dt.datetime) -> str:
    return t.replace(microsecond=0).isoformat()

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def choice_weighted(rng: random.Random, items: Sequence[Tuple[Any, float]]) -> Any:
    # items: [(value, weight), ...]
    total = sum(w for _, w in items)
    if total <= 0:
        return items[-1][0]
    r = rng.random() * total
    c = 0.0
    for v, w in items:
        c += w
        if r <= c:
            return v
    return items[-1][0]

def sample_date(rng: random.Random, start: dt.date, end: dt.date) -> dt.date:
    if end < start:
        start, end = end, start
    days = (end - start).days
    if days <= 0:
        return start
    return start + dt.timedelta(days=rng.randint(0, days))

def sample_time_of_day(rng: random.Random) -> dt.time:
    # Bias toward commuting + evening
    buckets = [
        ((7, 0), 0.18),
        ((9, 0), 0.12),
        ((12, 0), 0.10),
        ((15, 0), 0.14),
        ((18, 0), 0.20),
        ((21, 0), 0.16),
        ((23, 0), 0.10),
    ]
    (h, m) = choice_weighted(rng, [((h, m), w) for (h, m), w in buckets])
    minute = (m + rng.randint(0, 59)) % 60
    hour = (h + rng.randint(0, 1)) % 24
    return dt.time(hour=hour, minute=minute)

def poisson(rng: random.Random, lam: float, cap: Optional[int] = None) -> int:
    # Knuth algorithm (fine for small lam ~0.3)
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= rng.random()
        if cap is not None and k > cap:
            return cap
    return max(0, k - 1)

def gamma(rng: random.Random, k: float, theta: float) -> float:
    return rng.gammavariate(k, theta)

def safe_money(x: float) -> float:
    return round(float(x) + 1e-9, 2)

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "x"

def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    if not rows:
        with path.open("w", newline="", encoding="utf-8") as f:
            if fieldnames:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
        return
    if fieldnames is None:
        keys = sorted({k for r in rows for k in r.keys()})
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

# --- Synthetic PII/PHI helpers (SAFE / fake) ---

FIRST_NAMES = ["Alex", "Sam", "Jamie", "Taylor", "Jordan", "Casey", "Morgan", "Riley", "Avery", "Cameron"]
LAST_NAMES  = ["Smith", "Jones", "Taylor", "Brown", "Wilson", "Johnson", "Davies", "Patel", "Khan", "Clark"]
STREETS     = ["High Street", "Station Road", "Church Lane", "Victoria Road", "Green Lane", "Manor Road", "Park Road"]
TOWNS       = ["London", "Birmingham", "Leeds", "Glasgow", "Sheffield", "Bristol", "Edinburgh", "Manchester", "Cardiff", "Newcastle"]
POSTCODES   = ["SW1A 1AA", "B1 1AA", "LS1 1AA", "G1 1AA", "S1 1AA", "BS1 1AA", "EH1 1AA", "M1 1AA", "CF10 1AA", "NE1 1AA"]

def fake_person(rng: random.Random) -> Dict[str, str]:
    fn = rng.choice(FIRST_NAMES)
    ln = rng.choice(LAST_NAMES)
    phone = f"07{rng.randint(100000000, 999999999)}"
    email = f"{fn}.{ln}{rng.randint(10,99)}@example.test".lower()
    addr = f"{rng.randint(1, 220)} {rng.choice(STREETS)}, {rng.choice(TOWNS)}, {rng.choice(POSTCODES)}"
    return {"first_name": fn, "last_name": ln, "phone": phone, "email": email, "address": addr}

def fake_policy_number(rng: random.Random) -> str:
    return f"POL-{rng.randint(10000000, 99999999)}"

def fake_vehicle_reg(rng: random.Random) -> str:
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    return f"{rng.choice(letters)}{rng.choice(letters)}{rng.randint(10,99)} {rng.choice(letters)}{rng.choice(letters)}{rng.choice(letters)}"

def fake_vin(rng: random.Random) -> str:
    chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    return "".join(rng.choice(chars) for _ in range(17))

def fake_crime_ref(rng: random.Random) -> str:
    return f"CRN-{rng.randint(100000,999999)}-{rng.randint(10,99)}"

def maybe_inject_phi(rng: random.Random) -> str:
    nhs = f"{rng.randint(100,999)} {rng.randint(100,999)} {rng.randint(1000,9999)}"
    return f"NHS Number: {nhs}\nNotes: Patient reported whiplash symptoms. GP visit scheduled."
