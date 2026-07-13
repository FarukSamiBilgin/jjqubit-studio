"""Tests for gui.waveform.hdf5_reader: format detection and HDF5 -> dataclass readers.

Verifies the quantum-result reader against a file produced by the REAL
Task #3 solver pipeline (``quantum_result_h5`` fixture, see conftest.py),
and the classical-result reader against the synthetic file this teammate
constructs in the finalized classical schema (``classical_synthetic.py``).
"""

from __future__ import annotations

import h5py
import numpy as np
import pytest
from gui.waveform.hdf5_reader import (
    CLASSICAL_FORMAT,
    QUANTUM_FORMAT,
    detect_result_kind,
    load_classical_result,
    load_quantum_result,
)


class TestDetectResultKind:
    def test_quantum_file_detected(self, quantum_result_h5):
        assert detect_result_kind(quantum_result_h5) == "quantum"

    def test_classical_file_detected(self, classical_result_h5):
        assert detect_result_kind(classical_result_h5) == "classical"

    def test_unknown_format_falls_back_to_structural_groups(self, tmp_path):
        # A file with neither the known format string nor /qubit, /rcsj, /readout.
        path = tmp_path / "mystery.h5"
        with h5py.File(path, "w") as f:
            f.attrs["format"] = "something-else"
            f.create_group("nonsense")
        assert detect_result_kind(path) == "unknown"

    def test_structural_detection_without_format_string(self, tmp_path):
        # A classical file written under a DIFFERENT format string should still
        # be recognized via the /rcsj or /readout group -- the structural
        # fallback that keeps working regardless of the format string.
        path = tmp_path / "future_classical.h5"
        with h5py.File(path, "w") as f:
            f.attrs["format"] = "some-other-classical-format"
            readout = f.create_group("readout")
            readout.create_dataset("frequency_GHz", data=np.array([1.0, 2.0]))
        assert detect_result_kind(path) == "classical"


class TestLoadQuantumResult:
    def test_matches_real_solver_output(self, quantum_result_h5, transmon_netlist):
        result = load_quantum_result(quantum_result_h5)
        assert result.netlist_name == transmon_netlist.name
        assert result.junction_id == "J1"
        assert result.island_node == "q"
        assert result.resonator_id == "RES1"
        # Known-good numbers for the bundled example (see quantization.py docstring).
        assert result.Ej_GHz == pytest.approx(14.9005, abs=1e-3)
        assert result.Ec_GHz == pytest.approx(0.2516, abs=1e-3)
        assert result.Ej_over_Ec == pytest.approx(59.23, abs=0.1)
        assert result.E01_GHz > 0
        assert result.anharmonicity_GHz < 0  # transmons have negative anharmonicity
        assert len(result.energy_levels_GHz) == 10
        assert result.energy_levels_GHz[0] == pytest.approx(0.0)
        assert np.all(np.diff(result.energy_levels_GHz) > 0)  # monotonically increasing

    def test_g_description_present_and_readable(self, quantum_result_h5):
        # The task brief: g_GHz is the COMPLETE physical coupling, and this
        # description string is what tells a reader/label not to rescale it.
        result = load_quantum_result(quantum_result_h5)
        assert "physical" in result.g_GHz_description.lower()
        assert result.g_GHz > 0

    def test_wrong_format_raises(self, classical_result_h5):
        with pytest.raises(ValueError, match=QUANTUM_FORMAT):
            load_quantum_result(classical_result_h5)


class TestLoadClassicalResult:
    def test_reads_readout_sweep(self, classical_result_h5):
        result = load_classical_result(classical_result_h5)
        assert result.netlist_name == "Synthetic S21 sweep"
        assert result.readout is not None
        readout = result.readout
        assert (
            len(readout.frequency_GHz)
            == len(readout.magnitude_dB)
            == len(readout.phase_deg)
        )
        assert len(readout.frequency_GHz) == 501
        # A resonance dip should exist somewhere near the sweep center.
        assert readout.magnitude_dB.min() < readout.magnitude_dB[0]

    def test_reads_rcsj_analysis(self, classical_result_h5):
        result = load_classical_result(classical_result_h5)
        assert result.rcsj is not None
        rcsj = result.rcsj
        assert rcsj.Ic_nA > 0
        assert len(rcsj.iv_curve.bias_current_up_nA) == len(rcsj.iv_curve.voltage_up_uV)
        assert len(rcsj.phase_dynamics.time_ns) == len(rcsj.phase_dynamics.voltage_uV)

    def test_format_attr_is_classical(self, classical_result_h5):
        with h5py.File(classical_result_h5, "r") as f:
            assert f.attrs["format"] == CLASSICAL_FORMAT

    def test_result_with_neither_group_raises(self, tmp_path):
        path = tmp_path / "empty_classical.h5"
        with h5py.File(path, "w") as f:
            f.attrs["format"] = CLASSICAL_FORMAT
        with pytest.raises(ValueError):
            load_classical_result(path)
