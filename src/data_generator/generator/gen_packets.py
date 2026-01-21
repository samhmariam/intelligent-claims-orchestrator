from __future__ import annotations

import random
import shutil
from pathlib import Path
from typing import Any, Dict, List
import datetime as dt

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .utils import ensure_dir, write_json, maybe_inject_phi

try:
    from PIL import Image, ImageDraw, ImageFilter
    PIL_OK = True
except Exception:
    PIL_OK = False

DOC_IDS = ["FNOL", "POLICE_REPORT", "REPAIR_ESTIMATE", "INVOICE", "ADJUSTER_NOTES"]

def _pdf_header(c: canvas.Canvas, title: str) -> None:
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 800, title)
    c.setFont("Helvetica", 10)
    c.drawString(50, 785, "Synthetic motor claim document (SAFE / fake).")

def _pdf_kv(c: canvas.Canvas, y: float, k: str, v: str) -> float:
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, f"{k}:")
    c.setFont("Helvetica", 10)
    c.drawString(170, y, str(v))
    return y - 14

def _pdf_paragraph(c: canvas.Canvas, y: float, text: str) -> float:
    c.setFont("Helvetica", 10)
    words = text.split()
    line = ""
    lines = []
    for w in words:
        if len(line) + len(w) + 1 > 85:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(line)
    for ln in lines:
        c.drawString(50, y, ln)
        y -= 12
    return y

def render_fnol_pdf(claim: Dict[str, Any], path: Path) -> str:
    c = canvas.Canvas(str(path), pagesize=A4)
    _pdf_header(c, "First Notification of Loss (FNOL)")
    y = 760
    y = _pdf_kv(c, y, "Claim Ref", claim["claim_id"])
    y = _pdf_kv(c, y, "Policy Number", claim["policy_number"])
    y = _pdf_kv(c, y, "Insured", f"{claim['insured_first_name']} {claim['insured_last_name']}")
    y = _pdf_kv(c, y, "Contact", f"{claim['insured_phone']} | {claim['insured_email']}")
    y = _pdf_kv(c, y, "Address", claim["insured_address"])
    y -= 8
    y = _pdf_kv(c, y, "Vehicle Reg", claim["vehicle_reg"])
    y = _pdf_kv(c, y, "VIN", claim["vin"])
    y = _pdf_kv(c, y, "Vehicle Group", claim["vehicle_group"])
    y = _pdf_kv(c, y, "Cover Type", claim["cover_type"])
    y = _pdf_kv(c, y, "Excess (GBP)", str(claim["excess_gbp"]))
    y -= 8
    y = _pdf_kv(c, y, "Incident Date", claim["incident_date"])
    y = _pdf_kv(c, y, "Incident Time", claim["incident_time"])
    y = _pdf_kv(c, y, "Report Date", claim["report_date"])
    y = _pdf_kv(c, y, "Incident Type", claim["incident_type"])
    y = _pdf_kv(c, y, "Injuries", "YES" if claim["injuries_flag"] else "NO")
    y = _pdf_kv(c, y, "Police Attended", "YES" if claim["police_attended_flag"] else "NO")
    if claim.get("crime_ref"):
        y = _pdf_kv(c, y, "Crime Ref", claim["crime_ref"])
    y -= 10
    y = _pdf_paragraph(c, y, f"Description: {claim['description']}")
    c.showPage()
    c.save()

    extract = "\n".join([
        f"Claim Ref: {claim['claim_id']}",
        f"Policy Number: {claim['policy_number']}",
        f"Insured: {claim['insured_first_name']} {claim['insured_last_name']}",
        f"Contact: {claim['insured_phone']} | {claim['insured_email']}",
        f"Address: {claim['insured_address']}",
        f"Vehicle Reg: {claim['vehicle_reg']}",
        f"VIN: {claim['vin']}",
        f"Cover Type: {claim['cover_type']}",
        f"Excess (GBP): {claim['excess_gbp']}",
        f"Incident Date: {claim['incident_date']} {claim['incident_time']}",
        f"Report Date: {claim['report_date']}",
        f"Incident Type: {claim['incident_type']}",
        f"Injuries: {'YES' if claim['injuries_flag'] else 'NO'}",
        f"Police Attended: {'YES' if claim['police_attended_flag'] else 'NO'}",
        f"Crime Ref: {claim.get('crime_ref','')}",
        f"Description: {claim['description']}",
    ])
    return extract

def render_police_report_pdf(claim: Dict[str, Any], path: Path) -> str:
    c = canvas.Canvas(str(path), pagesize=A4)
    _pdf_header(c, "Incident Report / Police Reference")
    y = 760
    y = _pdf_kv(c, y, "Claim Ref", claim["claim_id"])
    y = _pdf_kv(c, y, "Reference", claim.get("crime_ref") or "N/A")
    y = _pdf_kv(c, y, "Incident Date", claim["incident_date"])
    y = _pdf_kv(c, y, "Incident Time", claim["incident_time"])
    y = _pdf_kv(c, y, "Report Date", claim["report_date"])
    y -= 10
    narrative = f"Summary: {claim['description']} (synthetic reference document)."
    y = _pdf_paragraph(c, y, narrative)
    c.showPage()
    c.save()
    extract = "\n".join([
        f"Claim Ref: {claim['claim_id']}",
        f"Reference: {claim.get('crime_ref') or 'N/A'}",
        f"Incident Date: {claim['incident_date']} {claim['incident_time']}",
        f"Report Date: {claim['report_date']}",
        narrative,
    ])
    return extract

def render_repair_estimate_pdf(claim: Dict[str, Any], path: Path, vendor: Dict[str, Any]) -> str:
    c = canvas.Canvas(str(path), pagesize=A4)
    _pdf_header(c, "Repair Estimate")
    y = 760
    y = _pdf_kv(c, y, "Claim Ref", claim["claim_id"])
    y = _pdf_kv(c, y, "Garage", vendor["name"])
    y = _pdf_kv(c, y, "VAT Number", vendor["vat_number"])
    y = _pdf_kv(c, y, "Vehicle Reg", claim["vehicle_reg"])
    y = _pdf_kv(c, y, "VIN", claim["vin"])
    y = _pdf_kv(c, y, "Severity", claim["severity"])
    y -= 8
    y = _pdf_kv(c, y, "Total Estimate (GBP)", str(claim["estimate_total_gbp"]))
    y -= 10
    y = _pdf_paragraph(c, y, "Notes: standard parts and labour to restore pre-loss condition.")
    c.showPage()
    c.save()
    extract = "\n".join([
        f"Claim Ref: {claim['claim_id']}",
        f"Garage: {vendor['name']} | VAT {vendor['vat_number']}",
        f"Vehicle Reg: {claim['vehicle_reg']}",
        f"VIN: {claim['vin']}",
        f"Total Estimate (GBP): {claim['estimate_total_gbp']}",
    ])
    return extract

def render_invoice_pdf(claim: Dict[str, Any], path: Path, vendor: Dict[str, Any]) -> str:
    c = canvas.Canvas(str(path), pagesize=A4)
    _pdf_header(c, "Final Invoice")
    y = 760
    y = _pdf_kv(c, y, "Invoice No", f"INV-{claim['claim_id']}")
    y = _pdf_kv(c, y, "Claim Ref", claim["claim_id"])
    y = _pdf_kv(c, y, "Garage", vendor["name"])
    y = _pdf_kv(c, y, "Vehicle Reg", claim["vehicle_reg"])
    y = _pdf_kv(c, y, "VIN", claim["vin"])
    y = _pdf_kv(c, y, "Invoice Date", claim.get("invoice_date", claim["report_date"]))
    y -= 8
    y = _pdf_kv(c, y, "Total Invoice (GBP)", str(claim["invoice_total_gbp"]))
    y = _pdf_kv(c, y, "Payment Method", claim.get("invoice_payment_method", "BACS"))
    y -= 10
    y = _pdf_paragraph(c, y, "Line items: parts, labour, paint/materials. Synthetic demo data.")
    c.showPage()
    c.save()
    extract = "\n".join([
        f"Invoice No: INV-{claim['claim_id']}",
        f"Claim Ref: {claim['claim_id']}",
        f"Garage: {vendor['name']}",
        f"Vehicle Reg: {claim['vehicle_reg']}",
        f"VIN: {claim['vin']}",
        f"Invoice Date: {claim.get('invoice_date', claim['report_date'])}",
        f"Total Invoice (GBP): {claim['invoice_total_gbp']}",
    ])
    return extract

def render_adjuster_notes_pdf(claim: Dict[str, Any], path: Path) -> str:
    c = canvas.Canvas(str(path), pagesize=A4)
    _pdf_header(c, "Adjuster Notes")
    y = 760
    y = _pdf_kv(c, y, "Claim Ref", claim["claim_id"])
    y = _pdf_kv(c, y, "Recommendation", claim.get("recommendation", "Proceed to assessment"))
    y = _pdf_kv(c, y, "Fraud Score Target", str(claim.get("fraud_score_target", "")))
    y -= 10
    notes = f"Observed damage consistent with incident type {claim['incident_type']}. Severity assessed as {claim['severity']}. "
    if claim.get("fraud_scenarios"):
        notes += "Flags: " + ", ".join(claim["fraud_scenarios"]) + ". "
    if claim.get("inject_phi"):
        notes += "\n\n" + maybe_inject_phi(random.Random(int(claim["claim_id"][-3:])))
    y = _pdf_paragraph(c, y, notes)
    c.showPage()
    c.save()
    return notes

def _make_image(path: Path, label: str, severity: str, rng: random.Random) -> None:
    if not PIL_OK:
        path.write_text(f"Synthetic image placeholder: {label} severity={severity}\n", encoding="utf-8")
        return
    img = Image.new("RGB", (1280, 720), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    n = {"LOW": 3, "MED": 7, "HIGH": 12}.get(severity, 5)
    for _ in range(n):
        x1 = rng.randint(50, 1230); y1 = rng.randint(50, 670)
        x2 = x1 + rng.randint(-200, 200); y2 = y1 + rng.randint(-120, 120)
        draw.line((x1, y1, x2, y2), fill=(rng.randint(80,120), rng.randint(80,120), rng.randint(80,120)), width=rng.randint(2, 6))
    draw.rectangle((20, 20, 620, 78), fill=(255,255,255))
    draw.text((30, 40), f"{label} | {severity}", fill=(10,10,10))
    img.save(path, format="JPEG", quality=rng.randint(45, 75), optimize=True)

def _tamper_images(photo_paths: List[Path], rng: random.Random) -> None:
    if not PIL_OK:
        return
    for p in photo_paths:
        try:
            img = Image.open(p)
            if rng.random() < 0.5:
                img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.6, 1.8)))
            if rng.random() < 0.7:
                img = img.rotate(rng.uniform(-2.0, 2.0), expand=False)
            img.save(p, format="JPEG", quality=rng.randint(35, 65), optimize=True)
        except Exception:
            continue

def generate_photos(claim: Dict[str, Any], out_dir: Path, rng: random.Random) -> List[Path]:
    ensure_dir(out_dir)
    severity = claim["severity"]
    if severity == "LOW":
        count = rng.randint(4, 8)
    elif severity == "MED":
        count = rng.randint(8, 14)
    else:
        count = rng.randint(10, 18)
    paths: List[Path] = []
    for i in range(1, count + 1):
        p = out_dir / f"IMG_{i:02d}.jpg"
        _make_image(p, label=f"{claim['claim_id']} photo {i}", severity=severity, rng=rng)
        paths.append(p)
    return paths

def apply_fraud_mutations(claim: Dict[str, Any], claim_dir: Path, rng: random.Random, global_photo_pool: List[Path]) -> None:
    scenarios = set(claim.get("fraud_scenarios") or [])
    photos_dir = claim_dir / "raw" / "photos"
    if "DUPLICATE_PHOTOS_ACROSS_CLAIMS" in scenarios and global_photo_pool:
        existing = sorted(photos_dir.glob("IMG_*.jpg"))
        if existing:
            k = min(len(existing), rng.randint(2, 4))
            picks = rng.sample(global_photo_pool, k=min(k, len(global_photo_pool)))
            for dest, src in zip(existing[:k], picks):
                try:
                    shutil.copyfile(src, dest)
                except Exception:
                    pass
    if "PHOTO_TAMPER_LIGHT" in scenarios:
        _tamper_images(list(photos_dir.glob("IMG_*.jpg")), rng)
    if "PHANTOM_REPAIRS" in scenarios:
        (claim_dir / "raw" / "documents" / "PHANTOM_REPAIR_NOTE.txt").write_text(
            "Note: Invoice includes parts not clearly visible in photos (synthetic test flag).",
            encoding="utf-8",
        )

def build_canonical_claim_object(claim: Dict[str, Any]) -> Dict[str, Any]:
    docs = []
    for doc_id in DOC_IDS:
        docs.append({
            "doc_id": doc_id,
            "doc_type": doc_id,
            "mime_type": "application/pdf",
            "page_count": 1,
            "source": {"uri": f"s3://REPLACE_ME/claims/{claim['claim_id']}/raw/documents/{doc_id}.pdf"},
        })
    return {
        "claim_id": claim["claim_id"],
        "policy_number": claim["policy_number"],
        "incident_date": claim["incident_date"],
        "claim_amount_gbp": claim["gross_loss_gbp"],
        "description": claim["description"],
        "status": claim["expected_decision"],
        "documents": docs,
        "metadata": {
            "cover_type": claim["cover_type"],
            "excess_gbp": claim["excess_gbp"],
            "vehicle_reg": claim["vehicle_reg"],
            "vin": claim["vin"],
            "incident_type": claim["incident_type"],
            "severity": claim["severity"],
        },
    }

def build_golden(claim: Dict[str, Any]) -> Dict[str, Any]:
    ev = [
        {"field": "incident_date", "doc_id": "FNOL", "page": 1},
        {"field": "vin", "doc_id": "FNOL", "page": 1},
        {"field": "invoice_total_gbp", "doc_id": "INVOICE", "page": 1},
    ]
    if claim.get("crime_ref"):
        ev.append({"field": "crime_ref", "doc_id": "POLICE_REPORT", "page": 1})
    return {
        "claim_id": claim["claim_id"],
        "fraud_label": claim.get("fraud_label", "none"),
        "fraud_scenarios": claim.get("fraud_scenarios", []),
        "expected_route": claim.get("expected_route", "AUTO"),
        "expected_decision": claim.get("expected_decision", claim.get("decision", "APPROVE")),
        "expected_payout_gbp": claim.get("expected_payout_gbp", 0.0),
        "payout_tolerance_pct": 0.05,
        "fraud_score_target": claim.get("fraud_score_target", 0.0),
        "evidence_map": ev,
    }

def render_packet_for_claim(
    claim: Dict[str, Any],
    claim_dir: Path,
    rng: random.Random,
    vendor: Dict[str, Any],
    global_photo_pool: List[Path],
    with_police_report: bool,
) -> Dict[str, Any]:
    docs_dir = claim_dir / "raw" / "documents"
    photos_dir = claim_dir / "raw" / "photos"
    extracts_dir = claim_dir / "extracts"
    ensure_dir(docs_dir); ensure_dir(photos_dir); ensure_dir(extracts_dir)

    scenarios = set(claim.get("fraud_scenarios") or [])

    vin_for_invoice = claim["vin"]
    if "VIN_OR_REG_MISMATCH" in scenarios:
        vin_for_invoice = claim["vin"][:-1] + ("9" if claim["vin"][-1] != "9" else "8")

    invoice_total = float(claim["invoice_total_gbp"])
    if "INVOICE_INFLATION" in scenarios:
        invoice_total = invoice_total * rng.uniform(1.20, 1.60)

    claim_render = dict(claim)
    claim_render["invoice_total_gbp"] = round(invoice_total, 2)
    claim_render["invoice_payment_method"] = "BACS"
    claim_render["invoice_date"] = claim["report_date"]

    police_claim = dict(claim_render)
    if "TIMELINE_INCONSISTENCY" in scenarios:
        try:
            inc = dt.date.fromisoformat(claim["incident_date"])
            police_claim["report_date"] = (inc - dt.timedelta(days=rng.randint(1, 5))).isoformat()
        except Exception:
            pass

    fnol_pdf = docs_dir / "FNOL.pdf"
    police_pdf = docs_dir / "POLICE_REPORT.pdf"
    est_pdf = docs_dir / "REPAIR_ESTIMATE.pdf"
    inv_pdf = docs_dir / "INVOICE.pdf"
    adj_pdf = docs_dir / "ADJUSTER_NOTES.pdf"

    fnol_txt = render_fnol_pdf(claim_render, fnol_pdf)
    if with_police_report:
        police_txt = render_police_report_pdf(police_claim, police_pdf)
    else:
        police_txt = ""
        police_pdf.write_bytes(b"")
    est_txt = render_repair_estimate_pdf(claim_render, est_pdf, vendor)

    inv_claim = dict(claim_render)
    inv_claim["vin"] = vin_for_invoice
    inv_txt = render_invoice_pdf(inv_claim, inv_pdf, vendor)

    adj_txt = render_adjuster_notes_pdf(claim_render, adj_pdf)

    (extracts_dir / "FNOL.txt").write_text(fnol_txt, encoding="utf-8")
    (extracts_dir / "POLICE_REPORT.txt").write_text(police_txt, encoding="utf-8")
    (extracts_dir / "REPAIR_ESTIMATE.txt").write_text(est_txt, encoding="utf-8")
    (extracts_dir / "INVOICE.txt").write_text(inv_txt, encoding="utf-8")
    (extracts_dir / "ADJUSTER_NOTES.txt").write_text(adj_txt, encoding="utf-8")

    photo_paths = generate_photos(claim_render, photos_dir, rng)

    apply_fraud_mutations(claim_render, claim_dir, rng, global_photo_pool)

    for p in photo_paths[: min(6, len(photo_paths))]:
        global_photo_pool.append(p)

    canonical = build_canonical_claim_object(claim_render)
    golden = build_golden(claim_render)

    write_json(claim_dir / "claim.json", canonical)
    write_json(claim_dir / "golden.json", golden)

    return {
        "claim_id": claim["claim_id"],
        "expected_route": claim.get("expected_route"),
        "expected_decision": claim.get("expected_decision"),
        "expected_payout_gbp": claim.get("expected_payout_gbp"),
        "fraud_score_target": claim.get("fraud_score_target"),
        "fraud_scenarios": claim.get("fraud_scenarios"),
        "paths": {
            "claim_dir": str(claim_dir),
            "documents_dir": str(docs_dir),
            "photos_dir": str(photos_dir),
        },
    }
