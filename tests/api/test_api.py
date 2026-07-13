"""Contract tests for the scriptable ``jjqubit`` API.

These check that the thin API layer faithfully exposes the solver core: right
result objects, headline numbers matching the underlying solvers, HDF5 output
that round-trips through the same reader the GUI uses, and correct error
behavior. The physics itself is validated in tests/validation; here we only
guard the API surface.
"""

from __future__ import annotations

import subprocess
import sys

import jjqubit
import pytest
from conftest import EXAMPLES_DIR, REPO_ROOT
from core.netlist import Netlist
from core.netlist.model import Connection, Element

TRANSMON = str(EXAMPLES_DIR / "transmon_readout.json")
RCSJ = str(EXAMPLES_DIR / "rcsj_bias.json")


def test_version_is_a_string():
    assert isinstance(jjqubit.__version__, str)
    assert jjqubit.__version__


def test_import_is_headless():
    """`import jjqubit` must not drag in PySide6 (it is a GUI-free API).

    Checked in a fresh subprocess because the pytest process itself imports
    PySide6 for the GUI test suites, so sys.modules here is already polluted.
    """
    code = "import jjqubit, sys; assert 'PySide6' not in sys.modules; print('ok')"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


def test_load_netlist_returns_validated_netlist():
    net = jjqubit.load_netlist(TRANSMON)
    assert isinstance(net, Netlist)
    assert net.name


class TestSolveQuantum:
    def test_headline_numbers_match_the_reference_transmon(self):
        q = jjqubit.solve_quantum(TRANSMON)
        # examples/transmon_readout.json: Ej/Ec ~ 59, a genuine transmon.
        assert q.Ej_over_Ec == pytest.approx(59.23, rel=1e-2)
        assert q.E01_GHz == pytest.approx(5.211, rel=1e-2)
        # Anharmonicity is negative and near -Ec (transmon regime).
        assert q.anharmonicity_GHz < 0.0
        assert q.anharmonicity_GHz == pytest.approx(-q.Ec_GHz, rel=0.2)
        # Dispersive shift is a small (sub-MHz here) negative number.
        assert q.chi_MHz < 0.0

    def test_summary_keys(self):
        q = jjqubit.solve_quantum(TRANSMON)
        s = q.summary()
        assert set(s) == {
            "Ej_GHz",
            "Ec_GHz",
            "Ej_over_Ec",
            "E01_GHz",
            "anharmonicity_GHz",
            "g_MHz",
            "chi_MHz",
            "Delta_GHz",
        }
        assert all(isinstance(v, float) for v in s.values())

    def test_exposes_coherence_estimates(self):
        q = jjqubit.solve_quantum(TRANSMON)
        assert q.T1_us > 0.0
        assert 0.0 < q.T2_us <= 2.0 * q.T1_us + 1e-6
        assert q.coherence.temperature_K > 0.0

    def test_accepts_path_or_netlist_object_identically(self):
        from_path = jjqubit.solve_quantum(TRANSMON)
        net = jjqubit.load_netlist(TRANSMON)
        from_obj = jjqubit.solve_quantum(net)
        assert from_obj.E01_GHz == pytest.approx(from_path.E01_GHz, rel=1e-12)

    def test_write_hdf5_roundtrips_through_the_gui_reader(self, tmp_path):
        # The GUI's reader is Qt-free; this asserts the API writes the exact
        # format the waveform viewer consumes.
        from gui.waveform.hdf5_reader import (
            detect_result_kind,
            load_quantum_result,
        )

        q = jjqubit.solve_quantum(TRANSMON)
        out = tmp_path / "q.h5"
        q.write_hdf5(out)
        assert detect_result_kind(out) == "quantum"
        assert load_quantum_result(out).E01_GHz == pytest.approx(q.E01_GHz, rel=1e-9)


class TestSolveClassical:
    def test_rcsj_bias_populates_rcsj_only(self):
        c = jjqubit.solve_classical(RCSJ)
        assert c.rcsj is not None
        assert c.readout is None  # rcsj_bias.json has no resonator

    def test_running_state_has_nonzero_dc_voltage(self):
        # rcsj_bias.json biases above Ic, so the junction runs (V_dc != 0).
        c = jjqubit.solve_classical(RCSJ)
        assert c.rcsj.bias_current_a > c.rcsj.critical_current_a
        assert c.rcsj.phase_dynamics.dc_voltage_v > 0.0

    def test_write_hdf5_roundtrips_through_the_gui_reader(self, tmp_path):
        from gui.waveform.hdf5_reader import (
            detect_result_kind,
            load_classical_result,
        )

        c = jjqubit.solve_classical(RCSJ)
        out = tmp_path / "c.h5"
        c.write_hdf5(out)
        assert detect_result_kind(out) == "classical"
        assert load_classical_result(out).rcsj is not None

    def test_unsupported_topology_raises_valueerror(self):
        # A lone capacitor is neither an RCSJ bias nor a readout topology.
        net = Netlist(
            name="just a capacitor",
            nodes=["a", "b"],
            elements=[Element(id="C1", type="capacitor", params={})],
            connections=[
                Connection(element="C1", terminal=0, node="a"),
                Connection(element="C1", terminal=1, node="b"),
            ],
        )
        with pytest.raises(ValueError):
            jjqubit.solve_classical(net)
