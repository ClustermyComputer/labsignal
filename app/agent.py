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
from google.genai import types

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

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
    # Mock data — Firestore integration comes in Phase 2 Task 2
    mock_patients = {
        "P4471": {
            "medications": ["pantoprazole 40mg daily"],
            "renal_function": "eGFR 72 (mildly reduced)",
            "relevant_history": "No known neuroendocrine tumor history",
            "ppi_use": True,
            "ppi_adjustment": "+55% CgA elevation expected from PPI use alone"
        }
    }
    patient = mock_patients.get(patient_id.upper())
    if not patient:
        return f"No record found for patient {patient_id}. Proceed with caution."
    
    confounders = []
    if patient["ppi_use"]:
        confounders.append(f"⚠️ PPI USE DETECTED: {patient['medications'][0]}. {patient['ppi_adjustment']}")
    confounders.append(f"Renal function: {patient['renal_function']}")
    confounders.append(f"History: {patient['relevant_history']}")
    
    return "\n".join(confounders)


def get_sample_chain_risk(sample_id: str) -> str:
    """Assess pre-analytical risk from sample handling and cold chain records.
    
    Args:
        sample_id: The sample identifier string (e.g. 'S-2024-0391')
    Returns:
        A string describing cold chain and handling risk factors.
    """
    # Mock data — Firestore integration comes in Phase 2 Task 3
    mock_samples = {
        "S-2024-0391": {
            "matrix": "serum",
            "time_to_centrifugation_hours": 4.0,
            "freeze_thaw_cycles": 1,
            "storage_temp_excursion": False,
            "notes": "Stored at -20C, single freeze-thaw prior to analysis"
        }
    }
    sample = mock_samples.get(sample_id.upper())
    if not sample:
        return f"No chain of custody record found for sample {sample_id}."
    
    risks = []
    risks.append(f"Matrix: {sample['matrix']} (note: plasma reads markedly higher than serum for CgA)")
    
    if sample["time_to_centrifugation_hours"] > 2:
        risks.append(f"⚠️ Time to centrifugation: {sample['time_to_centrifugation_hours']}h (>2h increases risk of cell lysis)")
    
    if sample["freeze_thaw_cycles"] >= 1:
        risks.append(f"⚠️ Freeze-thaw cycles: {sample['freeze_thaw_cycles']} (~+23% CgA elevation per cycle reported)")
    
    if not sample["storage_temp_excursion"]:
        risks.append("✓ No temperature excursion detected during storage")
    
    return "\n".join(risks)


def get_instrument_qc_history(instrument_id: str) -> str:
    """Retrieve recent QC run history and CV trends for an instrument.
    
    Args:
        instrument_id: The instrument identifier string (e.g. 'ELISA-01')
    Returns:
        A string summarising recent QC performance and any drift alerts.
    """
    # Mock data — Firestore integration comes in Phase 2 Task 4
    mock_instruments = {
        "ELISA-01": {
            "last_calibration": "2026-03-10",
            "recent_cvs": [8.2, 9.1, 11.4, 12.9],
            "lot_number": "LOT-2024-CGA-07",
            "lot_change_date": "2026-03-08",
            "westgard_violations": ["1-2s warning on high QC control (run 4)"]
        }
    }
    instrument = mock_instruments.get(instrument_id.upper())
    if not instrument:
        return f"No QC history found for instrument {instrument_id}."
    
    alerts = []
    alerts.append(f"Last calibration: {instrument['last_calibration']}")
    alerts.append(f"Lot number: {instrument['lot_number']} (changed {instrument['lot_change_date']})")
    
    cv_trend = instrument["recent_cvs"]
    if cv_trend[-1] > 10:
        alerts.append(f"⚠️ CV trending up: {cv_trend} — most recent run CV {cv_trend[-1]}% (>10% threshold)")
    
    for violation in instrument["westgard_violations"]:
        alerts.append(f"⚠️ Westgard: {violation}")
    
    return "\n".join(alerts)


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
