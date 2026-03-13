"""
LabSignal — Firestore seed script
Populates patients, samples, and instrument QC history collections.
Run once: python seed_firestore.py
"""

from google.cloud import firestore
import datetime

db = firestore.Client(project="vital-cedar-456905-q9")

# ── PATIENTS ─────────────────────────────────────────────────────────────────
patients = {
    "P4471": {
        "name": "Patient 4471",
        "age": 58,
        "sex": "M",
        "medications": ["pantoprazole 40mg daily", "lisinopril 10mg daily"],
        "ppi_use": True,
        "ppi_drug": "pantoprazole 40mg daily",
        "ppi_adjustment_pct": 55,
        "renal_function": "eGFR 72 — mildly reduced",
        "relevant_history": "No known neuroendocrine tumor history. Referred for NET workup due to elevated CgA.",
        "stress_factors": "None documented",
        "notes": "PPI use is most likely cause of CgA elevation. Recommend washout before repeat."
    },
    "P1192": {
        "name": "Patient 1192",
        "age": 44,
        "sex": "F",
        "medications": ["omeprazole 20mg daily", "levothyroxine 50mcg"],
        "ppi_use": True,
        "ppi_drug": "omeprazole 20mg daily",
        "ppi_adjustment_pct": 40,
        "renal_function": "eGFR 91 — normal",
        "relevant_history": "Known small intestine NET, grade 1. On active surveillance.",
        "stress_factors": "None documented",
        "notes": "Active NET patient — PPI use complicates CgA interpretation significantly."
    },
    "P8834": {
        "name": "Patient 8834",
        "age": 67,
        "sex": "M",
        "medications": ["metformin 1000mg", "atorvastatin 40mg"],
        "ppi_use": False,
        "ppi_drug": None,
        "ppi_adjustment_pct": 0,
        "renal_function": "eGFR 48 — moderately reduced (CKD stage 3)",
        "relevant_history": "Type 2 diabetes, hypertension. Elevated CgA incidental finding.",
        "stress_factors": "Recent ICU admission (2 weeks ago)",
        "notes": "No PPI but significant renal impairment. Renal clearance reduction can cause CgA accumulation."
    }
}

print("Seeding patients...")
for pid, data in patients.items():
    db.collection("patients").document(pid).set(data)
    print(f"  ✓ {pid}")

# ── SAMPLES ──────────────────────────────────────────────────────────────────
samples = {
    "S-2024-0391": {
        "patient_id": "P4471",
        "collection_date": "2026-03-12",
        "matrix": "serum",
        "time_to_centrifugation_hours": 4.0,
        "freeze_thaw_cycles": 1,
        "storage_temp_c": -20,
        "storage_temp_excursion": False,
        "collection_site": "Outpatient phlebotomy",
        "notes": "Stored at -20C. Single freeze-thaw prior to analysis. 4h delay to centrifugation flagged.",
        "risk_flags": ["delayed_centrifugation", "freeze_thaw"]
    },
    "S-2024-0392": {
        "patient_id": "P1192",
        "collection_date": "2026-03-12",
        "matrix": "plasma",
        "time_to_centrifugation_hours": 1.2,
        "freeze_thaw_cycles": 0,
        "storage_temp_c": -80,
        "storage_temp_excursion": False,
        "collection_site": "Oncology clinic",
        "notes": "Plasma sample — note CgA reads markedly higher in plasma vs serum. Processed within 2h.",
        "risk_flags": ["plasma_matrix"]
    },
    "S-2024-0393": {
        "patient_id": "P8834",
        "collection_date": "2026-03-11",
        "matrix": "serum",
        "time_to_centrifugation_hours": 1.5,
        "freeze_thaw_cycles": 2,
        "storage_temp_c": -20,
        "storage_temp_excursion": True,
        "storage_excursion_details": "Brief exposure to -10C for ~2h during freezer malfunction",
        "collection_site": "Inpatient ward",
        "notes": "Two freeze-thaw cycles. Temperature excursion documented.",
        "risk_flags": ["multiple_freeze_thaw", "temp_excursion"]
    }
}

print("Seeding samples...")
for sid, data in samples.items():
    db.collection("samples").document(sid).set(data)
    print(f"  ✓ {sid}")

# ── INSTRUMENT QC HISTORY ────────────────────────────────────────────────────
instruments = {
    "ELISA-01": {
        "name": "ELISA-01",
        "type": "Microplate reader",
        "assay": "CgA ELISA (Cisbio)",
        "last_calibration": "2026-03-10",
        "current_lot": "LOT-2024-CGA-07",
        "lot_change_date": "2026-03-08",
        "previous_lot": "LOT-2024-CGA-06",
        "recent_cvs": [7.1, 7.8, 8.2, 8.0, 7.9, 8.5, 8.1, 7.6, 8.3, 8.8, 9.1, 8.9, 10.2, 11.1, 11.8, 12.4, 12.9],
        "cv_threshold_pct": 10.0,
        "westgard_violations": [
            "1-2s warning on high QC control (run 16)",
            "1-2s warning on high QC control (run 17)"
        ],
        "qc_status": "WARNING",
        "notes": "CV trending upward since lot change on 2026-03-08. Recalibration recommended."
    },
    "ELISA-02": {
        "name": "ELISA-02",
        "type": "Microplate reader",
        "assay": "CgA ELISA (Cisbio)",
        "last_calibration": "2026-03-11",
        "current_lot": "LOT-2024-CGA-06",
        "lot_change_date": "2026-01-15",
        "previous_lot": "LOT-2024-CGA-05",
        "recent_cvs": [6.8, 7.1, 6.9, 7.3, 7.0, 6.8, 7.2, 7.1, 6.9, 7.4],
        "cv_threshold_pct": 10.0,
        "westgard_violations": [],
        "qc_status": "IN_CONTROL",
        "notes": "Performing within specification. No violations."
    }
}

print("Seeding instruments...")
for iid, data in instruments.items():
    db.collection("instruments").document(iid).set(data)
    print(f"  ✓ {iid}")

print("\n✅ Firestore seed complete.")
print(f"   Collections: patients ({len(patients)}), samples ({len(samples)}), instruments ({len(instruments)})")
print(f"   Project: vital-cedar-456905-q9")
