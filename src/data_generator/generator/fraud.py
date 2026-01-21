from __future__ import annotations

import random
from typing import List

from .utils import choice_weighted, clamp

DEFAULT_SCENARIO_WEIGHTS = [
    ("DUPLICATE_PHOTOS_ACROSS_CLAIMS", 0.30),
    ("INVOICE_INFLATION", 0.25),
    ("VIN_OR_REG_MISMATCH", 0.20),
    ("TIMELINE_INCONSISTENCY", 0.15),
    ("PHOTO_TAMPER_LIGHT", 0.10),
    ("PHANTOM_REPAIRS", 0.10),
    ("STAGED_THEFT_SIGNAL", 0.08),
]

def choose_fraud_label(rng: random.Random, base_rate: float) -> str:
    if rng.random() >= base_rate:
        return "none"
    return "suspected" if rng.random() < 0.70 else "confirmed"

def choose_scenarios(rng: random.Random, fraud_label: str, incident_type: str) -> List[str]:
    if fraud_label == "none":
        return []
    weights = list(DEFAULT_SCENARIO_WEIGHTS)
    if incident_type == "THEFT":
        weights = [(k, w * (1.6 if k == "STAGED_THEFT_SIGNAL" else 1.0)) for k, w in weights]
    n = 1 if rng.random() < 0.70 else 2
    chosen: List[str] = []
    for _ in range(n):
        pick = choice_weighted(rng, weights)
        if pick not in chosen:
            chosen.append(pick)
    return chosen

def fraud_score_for(scenarios: List[str], fraud_label: str, rng: random.Random) -> float:
    if fraud_label == "none":
        return clamp(rng.random() * 0.35, 0.0, 0.40)
    base = 0.62 if fraud_label == "suspected" else 0.78
    bump = 0.0
    for s in scenarios:
        bump += {
            "DUPLICATE_PHOTOS_ACROSS_CLAIMS": 0.10,
            "INVOICE_INFLATION": 0.08,
            "VIN_OR_REG_MISMATCH": 0.08,
            "TIMELINE_INCONSISTENCY": 0.06,
            "PHOTO_TAMPER_LIGHT": 0.05,
            "PHANTOM_REPAIRS": 0.07,
            "STAGED_THEFT_SIGNAL": 0.08,
        }.get(s, 0.04)
    noise = (rng.random() - 0.5) * 0.06
    return clamp(base + bump + noise, 0.0, 0.98)
