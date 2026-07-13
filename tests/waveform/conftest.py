"""Pytest bootstrap and shared fixtures for the waveform-viewer GUI tests.

Ensures the repository root is importable so ``import core...`` and
``import gui.waveform`` work no matter where pytest is invoked from. Also
forces the Qt "offscreen" platform plugin so widget tests can run headless
(no display required), and provides a shared, session-scoped
``QApplication`` since Qt only allows one per process.

Lives inside ``tests/waveform/`` (this module's owned scope) and touches
nothing outside it.
"""

from __future__ import annotations

import os
import pathlib
import sys

# tests/waveform/conftest.py -> parents[2] is the repository root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXAMPLES_DIR = REPO_ROOT / "examples"

# Run Qt headlessly unless a real display/platform was explicitly requested.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402 - must follow sys.path/env setup
from classical_synthetic import write_synthetic_classical_hdf5  # noqa: E402
from core.netlist import Netlist, load  # noqa: E402
from core.solvers.quantum.dispersive import compute_dispersive_shift  # noqa: E402
from core.solvers.quantum.hdf5_io import write_hdf5  # noqa: E402
from core.solvers.quantum.quantization import quantize_circuit  # noqa: E402
from core.solvers.quantum.spectrum import compute_transmon_spectrum  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """A single shared ``QApplication`` for the whole test session."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture
def transmon_netlist() -> Netlist:
    """The bundled transmon + readout resonator reference circuit, validated."""
    return load(EXAMPLES_DIR / "transmon_readout.json", validate=True)


@pytest.fixture
def quantum_result_h5(tmp_path, transmon_netlist) -> pathlib.Path:
    """A REAL quantum-solver HDF5 file, built with the actual Task #3 solver.

    Runs the real quantization -> spectrum -> dispersive-shift pipeline
    (the same one ``python -m core.solvers.quantum`` runs) against the
    bundled example netlist, then writes it with the real
    ``core.solvers.quantum.hdf5_io.write_hdf5`` -- so tests against this
    fixture exercise the actual solver-output contract, not a hand-rolled
    stand-in.
    """
    quantization = quantize_circuit(transmon_netlist)
    spectrum = compute_transmon_spectrum(quantization.Ej_GHz, quantization.Ec_GHz)
    dispersive = compute_dispersive_shift(quantization, spectrum)
    out_path = tmp_path / "quantum_result.h5"
    write_hdf5(
        out_path,
        netlist_name=transmon_netlist.name,
        quantization=quantization,
        spectrum=spectrum,
        dispersive=dispersive,
    )
    return out_path


@pytest.fixture
def classical_result_h5(tmp_path) -> pathlib.Path:
    """A synthetic classical-result HDF5 file (see ``classical_synthetic.py``).

    Built in the finalized classical schema (Task #2): a ``/readout`` S21
    group plus an ``/rcsj`` I-V + phase-dynamics group, so every classical
    sub-view is exercised. The numbers are fabricated; the layout matches
    what ``core.solvers.classical`` actually writes.
    """
    out_path = tmp_path / "classical_result.h5"
    write_synthetic_classical_hdf5(out_path, netlist_name="Synthetic S21 sweep")
    return out_path
