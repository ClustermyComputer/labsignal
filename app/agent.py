# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import google.auth
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import google_search
from google.cloud import firestore
from google.genai import types

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

# Firestore client — shared across tool calls
db = firestore.Client(project="vital-cedar-456905-q9")

LABSIGNAL_PROMPT = """
You are LabSignal, an expert AI laboratory intelligence agent specialized in 
hormone and biomarker assay interpretation. You help research scientists and 
solo biotech founders understand variability in immunoassay results — 
particularly when results may be misleading due to pre-analytical factors, 
patient confounders, or instrument drift.

Your domain expertise includes:
- Chromogranin A (CgA) assays and their known inter-kit variability
- Pre-analytical variables: sample matrix (serum vs plasma), cold chain 
  integrity, freeze-thaw cycles, time-to-centrifugation
- Patient confounders: proton pump inhibitor (PPI) use raises CgA by ~55%, 
  renal impairment, stress, and other non-tumor causes of elevation
- Westgard rules and QC interpretation
- Between-lot and between-run CV drift
- Assay-specific reference ranges and their limitations

When a scientist presents a result, you:
1. Call get_patient_confounders() to check for factors that affect the result
2. Call get_sample_chain_risk() to assess pre-analytical handling risk
3. Call get_instrument_qc_history() to check for recent QC drift
4. Synthesize all three into a variability-annotated verdict with a risk score
5. Always cite evidence for any variability adjustments you apply

RISK SCORING GUIDE:
- LOW: No significant confounders, sample handling within spec, instrument in control
- MODERATE: 1-2 minor risk factors present, result should be interpreted cautiously
- HIGH: PPI use AND/OR multiple pre-analytical issues AND/OR instrument out of control
- CRITICAL: Result likely invalid — reject run or repeat sample recommended

IMAGE INTERPRETATION:
When a scientist uploads an image, identify the type and analyze accordingly:

LEVEY-JENNINGS CHART:
- Identify the mean, +/-1SD, +/-2SD, +/-3SD control limits
- Check for Westgard rule violations: 1-3s (rejection), 1-2s (warning), 
  2-2s (two consecutive above 2SD), R-4s (range violation), 7-T (trend of 7)
- Note the direction and magnitude of any trend
- Connect any drift to lot changes or calibration events if visible
- State whether the run should be accepted, warned, or rejected

PLATE READER OUTPUT:
- Identify wells outside expected OD ranges
- Flag QC control wells (typically H11, H12) specifically
- Note any spatial patterns (edge effects, row/column drift)
- Assess whether the standard curve wells show expected gradient

STANDARD CURVE:
- Evaluate R² value — below 0.99 is concerning for most immunoassays
- Check for drift at high concentrations (hook effect risk)
- Assess 4PL fit quality across the full dynamic range
- Flag if the curve shape suggests matrix interference or reagent degradation

You speak like a senior scientist — precise, evidence-based, and direct. 
You never guess. If you are uncertain, you say so and explain why.
You always flag when a result should be repeated or interpreted with caution.
"""


def get_patient_confounders(patient_id: str) -> str:
    """Retrieve patient-level factors that may confound assay results.

    Args:
        patient_id: The patient identifier string (e.g. 'P4471')
    Returns:
        A string describing known confounders for this patient.
    """
    try:
        doc = db.collection("patients").document(patient_id.upper()).get()
        if not doc.exists:
            return f"No record found for patient {patient_id}. Proceed with caution — unknown confounder status."

        p = doc.to_dict()
        lines = []

        if p.get("ppi_use"):
            lines.append(f"⚠️  PPI USE DETECTED: {p['ppi_drug']}")
            lines.append(f"    Expected CgA elevation from PPI alone: +{p['ppi_adjustment_pct']}%")

        lines.append(f"Renal function: {p['renal_function']}")

        if p.get("stress_factors") and p["stress_factors"] != "None documented":
            lines.append(f"⚠️  Stress factors: {p['stress_factors']}")
        else:
            lines.append(f"Stress factors: {p['stress_factors']}")

        lines.append(f"Relevant history: {p['relevant_history']}")
        lines.append(f"Clinical note: {p['notes']}")
        lines.append(f"Medications: {', '.join(p['medications'])}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving patient data for {patient_id}: {str(e)}"


def get_sample_chain_risk(sample_id: str) -> str:
    """Assess pre-analytical risk from sample handling and cold chain records.

    Args:
        sample_id: The sample identifier string (e.g. 'S-2024-0391')
    Returns:
        A string describing cold chain and handling risk factors with a computed risk score.
    """
    try:
        doc = db.collection("samples").document(sample_id.upper()).get()
        if not doc.exists:
            return f"No chain of custody record found for sample {sample_id}."

        s = doc.to_dict()
        lines = []
        risk_points = 0

        # Matrix check
        if s["matrix"] == "plasma":
            lines.append("⚠️  Matrix: PLASMA — CgA reads markedly higher in plasma vs serum.")
            lines.append("    Inter-matrix difference can exceed 30%. Ensure reference range matches matrix.")
            risk_points += 2
        else:
            lines.append(f"Matrix: {s['matrix']} ✓")

        # Time to centrifugation
        ttc = s["time_to_centrifugation_hours"]
        if ttc > 2:
            lines.append(f"⚠️  Time to centrifugation: {ttc}h — exceeds 2h recommended window.")
            lines.append("    Risk of cell lysis and proteolytic degradation of CgA fragments.")
            risk_points += 2
        else:
            lines.append(f"Time to centrifugation: {ttc}h ✓ (within 2h window)")

        # Freeze-thaw cycles
        ftc = s["freeze_thaw_cycles"]
        if ftc == 1:
            lines.append(f"⚠️  Freeze-thaw cycles: {ftc} — approximately +23% CgA elevation reported per cycle.")
            risk_points += 1
        elif ftc >= 2:
            lines.append(f"🚨 Freeze-thaw cycles: {ftc} — significant pre-analytical artifact expected (+{ftc * 23}% cumulative estimate).")
            risk_points += 3
        else:
            lines.append(f"Freeze-thaw cycles: {ftc} ✓")

        # Temperature excursion
        if s.get("storage_temp_excursion"):
            lines.append(f"🚨 Temperature excursion: {s.get('storage_excursion_details', 'Details not recorded')}")
            risk_points += 3
        else:
            lines.append(f"Cold chain: No temperature excursion detected ✓")

        # Risk score
        if risk_points == 0:
            risk_label = "LOW"
        elif risk_points <= 2:
            risk_label = "MODERATE"
        elif risk_points <= 4:
            risk_label = "HIGH"
        else:
            risk_label = "CRITICAL"

        lines.append(f"\nPre-analytical Risk Score: {risk_label} ({risk_points} points)")
        lines.append(f"Notes: {s['notes']}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving sample data for {sample_id}: {str(e)}"


def get_instrument_qc_history(instrument_id: str) -> str:
    """Retrieve recent QC run history and CV trends for an instrument.

    Args:
        instrument_id: The instrument identifier string (e.g. 'ELISA-01')
    Returns:
        A string summarising recent QC performance, Westgard violations, and drift alerts.
    """
    try:
        doc = db.collection("instruments").document(instrument_id.upper()).get()
        if not doc.exists:
            return f"No QC history found for instrument {instrument_id}."

        inst = doc.to_dict()
        lines = []

        lines.append(f"Instrument: {inst['name']} | Assay: {inst['assay']}")
        lines.append(f"Last calibration: {inst['last_calibration']}")
        lines.append(f"Current lot: {inst['current_lot']} (changed {inst['lot_change_date']})")
        lines.append(f"Previous lot: {inst['previous_lot']}")

        # CV trend analysis
        cvs = inst["recent_cvs"]
        threshold = inst["cv_threshold_pct"]
        current_cv = cvs[-1]
        trend = cvs[-4:]  # last 4 runs
        trending_up = all(trend[i] < trend[i+1] for i in range(len(trend)-1))

        lines.append(f"\nRecent CV trend: {[round(c, 1) for c in cvs[-6:]]}")
        lines.append(f"Current CV: {current_cv}% (threshold: {threshold}%)")

        if current_cv > threshold:
            lines.append(f"⚠️  CV EXCEEDS THRESHOLD — precision is degraded")
        if trending_up:
            lines.append(f"⚠️  CV IS TRENDING UPWARD — systematic drift detected")

        # Westgard violations
        violations = inst.get("westgard_violations", [])
        if violations:
            lines.append(f"\nWestgard violations:")
            for v in violations:
                lines.append(f"  ⚠️  {v}")
        else:
            lines.append(f"\nWestgard violations: None ✓")

        lines.append(f"\nQC Status: {inst['qc_status']}")
        lines.append(f"Notes: {inst['notes']}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error retrieving instrument data for {instrument_id}: {str(e)}"


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-3-flash-preview",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=LABSIGNAL_PROMPT,
    tools=[get_patient_confounders, get_sample_chain_risk, get_instrument_qc_history, google_search],
)

app = App(
    root_agent=root_agent,
    name="app",
)
