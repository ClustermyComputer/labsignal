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
"""
Unit tests for LabSignal tool functions.
Tests confounder detection, sample chain risk scoring, and instrument QC logic.
Uses mocked Firestore to avoid needing live GCP credentials.
"""

import pytest
from unittest.mock import MagicMock, patch


# ── Helpers to build mock Firestore documents ────────────────────────────────

def make_mock_doc(data: dict) -> MagicMock:
    """Return a mock Firestore DocumentSnapshot with .exists=True and .to_dict()."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = data
    return doc


def make_missing_doc() -> MagicMock:
    """Return a mock Firestore DocumentSnapshot with .exists=False."""
    doc = MagicMock()
    doc.exists = False
    return doc


# ── get_patient_confounders ──────────────────────────────────────────────────

class TestGetPatientConfounders:

    def test_ppi_patient_flags_warning(self):
        """Patient on PPI should trigger a PPI warning in the output."""
        mock_data = {
            "medications": ["pantoprazole 40mg daily"],
            "ppi_use": True,
            "ppi_drug": "pantoprazole 40mg daily",
            "ppi_adjustment_pct": 55,
            "renal_function": "eGFR 72 — mildly reduced",
            "stress_factors": "None documented",
            "relevant_history": "No known NET history",
            "notes": "PPI washout recommended"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_patient_confounders
            result = get_patient_confounders("P4471")
        assert "PPI USE DETECTED" in result
        assert "55%" in result
        assert "pantoprazole" in result.lower()

    def test_non_ppi_patient_no_ppi_warning(self):
        """Patient not on PPI should not trigger PPI warning."""
        mock_data = {
            "medications": ["metformin 1000mg"],
            "ppi_use": False,
            "ppi_drug": None,
            "ppi_adjustment_pct": 0,
            "renal_function": "eGFR 48 — moderately reduced",
            "stress_factors": "Recent ICU admission",
            "relevant_history": "Type 2 diabetes",
            "notes": "Renal impairment may contribute to CgA elevation"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_patient_confounders
            result = get_patient_confounders("P8834")
        assert "PPI USE DETECTED" not in result
        assert "ICU" in result

    def test_unknown_patient_returns_not_found(self):
        """Unknown patient ID should return a not-found message."""
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_missing_doc()
            from app.agent import get_patient_confounders
            result = get_patient_confounders("P9999")
        assert "No record found" in result
        assert "P9999" in result


# ── get_sample_chain_risk ────────────────────────────────────────────────────

class TestGetSampleChainRisk:

    def test_delayed_centrifugation_flagged(self):
        """Sample with >2h centrifugation delay should be flagged."""
        mock_data = {
            "matrix": "serum",
            "time_to_centrifugation_hours": 4.0,
            "freeze_thaw_cycles": 0,
            "storage_temp_c": -20,
            "storage_temp_excursion": False,
            "notes": "4h delay to centrifugation"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_sample_chain_risk
            result = get_sample_chain_risk("S-2024-0391")
        assert "Time to centrifugation" in result
        assert "4.0h" in result

    def test_plasma_matrix_flagged(self):
        """Plasma matrix should trigger a matrix warning."""
        mock_data = {
            "matrix": "plasma",
            "time_to_centrifugation_hours": 1.2,
            "freeze_thaw_cycles": 0,
            "storage_temp_c": -80,
            "storage_temp_excursion": False,
            "notes": "Plasma sample"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_sample_chain_risk
            result = get_sample_chain_risk("S-2024-0392")
        assert "PLASMA" in result

    def test_multiple_freeze_thaw_critical(self):
        """Two or more freeze-thaw cycles should produce CRITICAL risk score."""
        mock_data = {
            "matrix": "serum",
            "time_to_centrifugation_hours": 1.5,
            "freeze_thaw_cycles": 2,
            "storage_temp_c": -20,
            "storage_temp_excursion": True,
            "storage_excursion_details": "Freezer malfunction — 2h at -10C",
            "notes": "Multiple freeze-thaw cycles and temp excursion"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_sample_chain_risk
            result = get_sample_chain_risk("S-2024-0393")
        assert "CRITICAL" in result

    def test_clean_sample_low_risk(self):
        """Sample with no risk factors should return LOW risk."""
        mock_data = {
            "matrix": "serum",
            "time_to_centrifugation_hours": 1.0,
            "freeze_thaw_cycles": 0,
            "storage_temp_c": -80,
            "storage_temp_excursion": False,
            "notes": "Ideal handling"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_sample_chain_risk
            result = get_sample_chain_risk("S-CLEAN-001")
        assert "LOW" in result

    def test_unknown_sample_returns_not_found(self):
        """Unknown sample ID should return a not-found message."""
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_missing_doc()
            from app.agent import get_sample_chain_risk
            result = get_sample_chain_risk("S-9999")
        assert "No chain of custody record found" in result


# ── get_instrument_qc_history ────────────────────────────────────────────────

class TestGetInstrumentQCHistory:

    def test_high_cv_flagged(self):
        """Instrument with CV above threshold should be flagged."""
        mock_data = {
            "name": "ELISA-01",
            "assay": "CgA ELISA (Cisbio)",
            "last_calibration": "2026-03-10",
            "current_lot": "LOT-2024-CGA-07",
            "lot_change_date": "2026-03-08",
            "previous_lot": "LOT-2024-CGA-06",
            "recent_cvs": [8.2, 9.1, 11.4, 12.9],
            "cv_threshold_pct": 10.0,
            "westgard_violations": ["1-2s warning on high QC control (run 4)"],
            "qc_status": "WARNING",
            "notes": "CV trending upward since lot change"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_instrument_qc_history
            result = get_instrument_qc_history("ELISA-01")
        assert "CV EXCEEDS THRESHOLD" in result
        assert "CV IS TRENDING UPWARD" in result
        assert "Westgard" in result

    def test_in_control_instrument_no_warnings(self):
        """Instrument with CV below threshold and no violations should show clean status."""
        mock_data = {
            "name": "ELISA-02",
            "assay": "CgA ELISA (Cisbio)",
            "last_calibration": "2026-03-11",
            "current_lot": "LOT-2024-CGA-06",
            "lot_change_date": "2026-01-15",
            "previous_lot": "LOT-2024-CGA-05",
            "recent_cvs": [6.8, 7.1, 6.9, 7.3, 7.0],
            "cv_threshold_pct": 10.0,
            "westgard_violations": [],
            "qc_status": "IN_CONTROL",
            "notes": "Performing within specification"
        }
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_mock_doc(mock_data)
            from app.agent import get_instrument_qc_history
            result = get_instrument_qc_history("ELISA-02")
        assert "CV EXCEEDS THRESHOLD" not in result
        assert "IN_CONTROL" in result
        assert "None" in result or "no violations" in result.lower() or "None ✓" in result

    def test_unknown_instrument_returns_not_found(self):
        """Unknown instrument ID should return a not-found message."""
        with patch("app.agent.db") as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = make_missing_doc()
            from app.agent import get_instrument_qc_history
            result = get_instrument_qc_history("ELISA-99")
        assert "No QC history found" in result
