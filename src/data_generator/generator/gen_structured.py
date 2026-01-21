from __future__ import annotations

import random
import datetime as dt
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .utils import (
    clamp, choice_weighted, gamma, iso_date, poisson,
    sample_date, sample_time_of_day, fake_person, fake_policy_number,
    fake_vehicle_reg, fake_vin, fake_crime_ref, safe_money
)
from .fraud import choose_fraud_label, choose_scenarios, fraud_score_for

@dataclass
class GenConfig:
    n_claims: int = 1000
    seed: int = 42
    start_date: dt.date = dt.date(2024, 1, 1)
    end_date: dt.date = dt.date(2025, 12, 31)
    base_fraud_rate: float = 0.02
    hitl_threshold_gbp: float = 8000.0
    inject_phi_rate: float = 0.005

VEHICLE_GROUPS = [
    ("SMALL_HATCH", 0.28),
    ("FAMILY_SALOON", 0.24),
    ("SUV", 0.18),
    ("VAN", 0.12),
    ("PREMIUM", 0.10),
    ("EV", 0.08),
]

COVER_TYPES = [
    ("COMPREHENSIVE", 0.72),
    ("TPFT", 0.20),
    ("TPO", 0.08),
]

INCIDENT_TYPES = [
    ("REAR_END", 0.22),
    ("PARKING_SCRAPE", 0.18),
    ("SIDE_IMPACT", 0.14),
    ("SINGLE_VEHICLE", 0.12),
    ("THEFT", 0.06),
    ("VANDALISM", 0.08),
    ("WINDSCREEN", 0.12),
    ("WEATHER", 0.08),
]

CAUSE_TEXT = {
    "REAR_END": "Rear-end collision in slow-moving traffic.",
    "PARKING_SCRAPE": "Scrape damage while parked in a public car park.",
    "SIDE_IMPACT": "Side impact at a junction; other vehicle failed to give way.",
    "SINGLE_VEHICLE": "Single-vehicle incident involving a barrier/ditch.",
    "THEFT": "Vehicle reported stolen overnight.",
    "VANDALISM": "Vehicle vandalised while parked.",
    "WINDSCREEN": "Windscreen damage from road debris.",
    "WEATHER": "Weather-related damage (hail/flood).",
}

SEVERITY_BY_INCIDENT = {
    "PARKING_SCRAPE": [("LOW", 0.80), ("MED", 0.18), ("HIGH", 0.02)],
    "WINDSCREEN":     [("LOW", 0.85), ("MED", 0.14), ("HIGH", 0.01)],
    "REAR_END":       [("LOW", 0.35), ("MED", 0.55), ("HIGH", 0.10)],
    "SIDE_IMPACT":    [("LOW", 0.30), ("MED", 0.55), ("HIGH", 0.15)],
    "SINGLE_VEHICLE": [("LOW", 0.22), ("MED", 0.53), ("HIGH", 0.25)],
    "WEATHER":        [("LOW", 0.35), ("MED", 0.40), ("HIGH", 0.25)],
    "VANDALISM":      [("LOW", 0.55), ("MED", 0.38), ("HIGH", 0.07)],
    "THEFT":          [("LOW", 0.05), ("MED", 0.20), ("HIGH", 0.75)],
}

AGE_BANDS = [
    ("17_24", 0.18),
    ("25_34", 0.22),
    ("35_49", 0.28),
    ("50_64", 0.22),
    ("65_PLUS", 0.10),
]

def sample_vehicle_value(rng: random.Random, group: str) -> float:
    if group == "SMALL_HATCH":
        v = gamma(rng, 2.2, 3500)
        return clamp(v, 3000, 14000)
    if group == "FAMILY_SALOON":
        v = gamma(rng, 2.2, 5200)
        return clamp(v, 5000, 20000)
    if group == "SUV":
        v = gamma(rng, 2.4, 6500)
        return clamp(v, 10000, 35000)
    if group == "VAN":
        v = gamma(rng, 2.0, 6000)
        return clamp(v, 6000, 30000)
    if group == "PREMIUM":
        v = gamma(rng, 2.0, 11000)
        return clamp(v, 15000, 55000)
    if group == "EV":
        v = gamma(rng, 2.0, 12000)
        return clamp(v, 18000, 55000)
    v = gamma(rng, 2.2, 5000)
    return clamp(v, 3000, 40000)

def sample_vehicle_age_years(rng: random.Random) -> int:
    band = choice_weighted(rng, [("0_2",0.22),("3_6",0.34),("7_10",0.26),("11_PLUS",0.18)])
    if band == "0_2":
        return rng.randint(0, 2)
    if band == "3_6":
        return rng.randint(3, 6)
    if band == "7_10":
        return rng.randint(7, 10)
    return rng.randint(11, 18)

def sample_excess(rng: random.Random, cover: str) -> float:
    if cover != "COMPREHENSIVE":
        return 0.0
    return float(choice_weighted(rng, [(250,0.35),(350,0.30),(500,0.25),(750,0.10)]))

def gross_loss_for(rng: random.Random, severity: str) -> float:
    if severity == "LOW":
        return gamma(rng, 2.0, 450.0)
    if severity == "MED":
        return gamma(rng, 2.2, 1300.0)
    return gamma(rng, 2.5, 4200.0)

def coverage_allows_payout(cover: str, incident_type: str) -> bool:
    if cover == "COMPREHENSIVE":
        return True
    if cover == "TPFT":
        return incident_type in ("THEFT",)
    return False

def settlement_days(rng: random.Random, severity: str) -> int:
    if severity == "LOW":
        return rng.randint(3, 21)
    if severity == "MED":
        return rng.randint(14, 60)
    return rng.randint(30, 180)

def report_delay_days(rng: random.Random) -> int:
    r = rng.random()
    if r < 0.65:
        return rng.randint(0, 1)
    if r < 0.90:
        return rng.randint(2, 7)
    return rng.randint(8, 45)

def generate_one(i: int, cfg: GenConfig, rng: random.Random) -> Dict[str, Any]:
    claim_id = f"CLM-{i:06d}"
    person = fake_person(rng)
    policy_number = fake_policy_number(rng)

    age_band = choice_weighted(rng, AGE_BANDS)
    age = {
        "17_24": rng.randint(17, 24),
        "25_34": rng.randint(25, 34),
        "35_49": rng.randint(35, 49),
        "50_64": rng.randint(50, 64),
        "65_PLUS": rng.randint(65, 78),
    }[age_band]
    years_licensed = max(0, age - 17 + rng.randint(-1, 2))
    prior_claims = min(4, poisson(rng, 0.30, cap=5))
    convictions = rng.random() < 0.07

    vehicle_group = choice_weighted(rng, VEHICLE_GROUPS)
    vehicle_age = sample_vehicle_age_years(rng)
    vehicle_value = sample_vehicle_value(rng, vehicle_group)

    cover_type = choice_weighted(rng, COVER_TYPES)
    excess = sample_excess(rng, cover_type)

    incident_type = choice_weighted(rng, INCIDENT_TYPES)
    severity = choice_weighted(rng, SEVERITY_BY_INCIDENT[incident_type])

    injuries = (rng.random() < 0.08) and (incident_type in ("REAR_END","SIDE_IMPACT","SINGLE_VEHICLE"))
    police_attended = injuries or (incident_type in ("THEFT",)) or (rng.random() < 0.10)
    crime_ref = fake_crime_ref(rng) if (incident_type == "THEFT" or police_attended) else ""

    incident_date = sample_date(rng, cfg.start_date, cfg.end_date)
    incident_time = sample_time_of_day(rng)
    report_date = incident_date + dt.timedelta(days=report_delay_days(rng))

    gross_loss = gross_loss_for(rng, severity)
    if incident_type == "THEFT" or (severity == "HIGH" and rng.random() < 0.35):
        gross_loss = min(gross_loss, vehicle_value * rng.uniform(0.80, 1.05))

    allowed = coverage_allows_payout(cover_type, incident_type)
    net_payout = 0.0
    decision = "DENY"
    reason_code = ""
    if not allowed:
        decision = "DENY"
        reason_code = "COVERAGE_EXCLUSION"
        net_payout = 0.0
    else:
        net_payout = max(0.0, gross_loss - excess)
        if net_payout <= 0.0:
            decision = "DENY"
            reason_code = "BELOW_EXCESS"
        else:
            decision = "APPROVE"
            reason_code = "STANDARD"

    fraud_label = choose_fraud_label(rng, cfg.base_fraud_rate)
    scenarios = choose_scenarios(rng, fraud_label, incident_type)
    fraud_score = fraud_score_for(scenarios, fraud_label, rng)

    inject_phi = (rng.random() < cfg.inject_phi_rate)
    expected_route = "AUTO"
    if inject_phi:
        expected_route = "QUARANTINE"
    elif (gross_loss >= cfg.hitl_threshold_gbp) or (fraud_score > 0.70):
        expected_route = "HITL"

    if expected_route in ("HITL", "QUARANTINE"):
        expected_decision = "HITL"
    else:
        expected_decision = decision

    vehicle_reg = fake_vehicle_reg(rng)
    vin = fake_vin(rng)

    premium = clamp((vehicle_value / 120.0) * (1.25 if age_band == "17_24" else 1.0) * (1.10 if convictions else 1.0), 250, 2500)

    claim = {
        "claim_id": claim_id,
        "policy_number": policy_number,
        "insured_first_name": person["first_name"],
        "insured_last_name": person["last_name"],
        "insured_phone": person["phone"],
        "insured_email": person["email"],
        "insured_address": person["address"],
        "driver_age": age,
        "driver_age_band": age_band,
        "driver_years_licensed": years_licensed,
        "driver_prior_claims": prior_claims,
        "driver_convictions": convictions,
        "vehicle_group": vehicle_group,
        "vehicle_age_years": vehicle_age,
        "vehicle_value_gbp": safe_money(vehicle_value),
        "vehicle_reg": vehicle_reg,
        "vin": vin,
        "cover_type": cover_type,
        "excess_gbp": safe_money(excess),
        "add_on_courtesy_car": rng.random() < 0.35,
        "add_on_breakdown": rng.random() < 0.28,
        "add_on_legal_cover": rng.random() < 0.42,
        "incident_type": incident_type,
        "severity": severity,
        "injuries_flag": injuries,
        "police_attended_flag": police_attended,
        "crime_ref": crime_ref,
        "incident_date": iso_date(incident_date),
        "incident_time": incident_time.strftime("%H:%M"),
        "report_date": iso_date(report_date),
        "description": CAUSE_TEXT[incident_type],
        "gross_loss_gbp": safe_money(gross_loss),
        "estimate_total_gbp": safe_money(gross_loss * rng.uniform(0.85, 1.05)),
        "invoice_total_gbp": safe_money(gross_loss * rng.uniform(0.82, 1.10)),
        "decision": decision,
        "decision_reason_code": reason_code,
        "expected_route": expected_route,
        "expected_decision": expected_decision,
        "expected_payout_gbp": safe_money(net_payout),
        "fraud_label": fraud_label,
        "fraud_scenarios": scenarios,
        "fraud_score_target": round(float(fraud_score), 2),
        "inject_phi": inject_phi,
        "premium_gbp": round(float(premium), 2),
    }
    return claim

def generate(cfg: GenConfig) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    rng = random.Random(cfg.seed)

    claims: List[Dict[str, Any]] = []
    policies: List[Dict[str, Any]] = []
    drivers: List[Dict[str, Any]] = []
    vehicles: List[Dict[str, Any]] = []
    claims_table: List[Dict[str, Any]] = []
    payments: List[Dict[str, Any]] = []
    reserves: List[Dict[str, Any]] = []
    vendors: List[Dict[str, Any]] = []

    vendor_names = [
        ("Northway Auto Repairs", "GB123456789"),
        ("Cityline Bodyshop", "GB987654321"),
        ("M1 Accident Repair Centre", "GB555777333"),
        ("Westfield Garage", "GB222444666"),
        ("EV Specialist Repairs", "GB333666999"),
    ]
    for idx, (name, vat) in enumerate(vendor_names, start=1):
        vendors.append({"vendor_id": f"VND-{idx:03d}", "name": name, "vat_number": vat})

    for i in range(1, cfg.n_claims + 1):
        c = generate_one(i, cfg, rng)
        claims.append(c)

        policy_id = f"PLC-{i:06d}"
        driver_id = f"DRV-{i:06d}"
        vehicle_id = f"VEH-{i:06d}"

        policies.append({
            "policy_id": policy_id,
            "policy_number": c["policy_number"],
            "cover_type": c["cover_type"],
            "excess_gbp": c["excess_gbp"],
            "premium_gbp": c["premium_gbp"],
            "add_on_courtesy_car": c["add_on_courtesy_car"],
            "add_on_breakdown": c["add_on_breakdown"],
            "add_on_legal_cover": c["add_on_legal_cover"],
        })
        drivers.append({
            "driver_id": driver_id,
            "policy_id": policy_id,
            "age": c["driver_age"],
            "age_band": c["driver_age_band"],
            "years_licensed": c["driver_years_licensed"],
            "prior_claims": c["driver_prior_claims"],
            "convictions": c["driver_convictions"],
        })
        vehicles.append({
            "vehicle_id": vehicle_id,
            "policy_id": policy_id,
            "vehicle_reg": c["vehicle_reg"],
            "vin": c["vin"],
            "group": c["vehicle_group"],
            "age_years": c["vehicle_age_years"],
            "value_gbp": c["vehicle_value_gbp"],
        })
        claims_table.append({
            "claim_id": c["claim_id"],
            "policy_id": policy_id,
            "vehicle_id": vehicle_id,
            "driver_id": driver_id,
            "incident_type": c["incident_type"],
            "severity": c["severity"],
            "incident_date": c["incident_date"],
            "report_date": c["report_date"],
            "gross_loss_gbp": c["gross_loss_gbp"],
            "expected_payout_gbp": c["expected_payout_gbp"],
            "decision": c["decision"],
            "expected_decision": c["expected_decision"],
            "fraud_score_target": c["fraud_score_target"],
            "expected_route": c["expected_route"],
        })

        settle_days = settlement_days(rng, c["severity"])
        report_date = dt.date.fromisoformat(c["report_date"])
        settlement_date = report_date + dt.timedelta(days=settle_days)

        n_updates = 2 if rng.random() < 0.55 else (3 if rng.random() < 0.70 else 4)
        base_reserve = float(c["gross_loss_gbp"]) * rng.uniform(0.85, 1.10)
        for u in range(n_updates):
            d = report_date + dt.timedelta(days=int((settle_days / max(1, n_updates)) * u))
            reserves.append({
                "claim_id": c["claim_id"],
                "reserve_update_no": u + 1,
                "reserve_date": iso_date(d),
                "reserve_amount_gbp": round(float(clamp(base_reserve * rng.uniform(0.92, 1.08), 0, float(c["gross_loss_gbp"]) * 1.4)), 2),
            })

        if c["expected_decision"] == "APPROVE" and float(c["expected_payout_gbp"]) > 0:
            payout = float(c["expected_payout_gbp"])
            n_pay = 1 if payout < 1500 else (2 if payout < 7000 else 3)
            remaining = payout
            for p in range(1, n_pay + 1):
                if p == n_pay:
                    amt = remaining
                else:
                    frac = 0.50 if p == 1 else 0.30
                    amt = round(payout * frac * rng.uniform(0.85, 1.10), 2)
                    amt = min(amt, remaining)
                remaining = round(remaining - amt, 2)
                pay_date = settlement_date - dt.timedelta(days=rng.randint(0, max(1, 10 - p*2)))
                payments.append({
                    "claim_id": c["claim_id"],
                    "payment_no": p,
                    "payment_date": iso_date(pay_date),
                    "amount_gbp": round(float(amt), 2),
                    "method": choice_weighted(rng, [("BACS",0.60),("CARD",0.25),("CHEQUE",0.05),("FPS",0.10)]),
                })

    tables = {
        "policies": policies,
        "drivers": drivers,
        "vehicles": vehicles,
        "claims": claims_table,
        "payments": payments,
        "reserves": reserves,
        "vendors": vendors,
    }
    return claims, tables
