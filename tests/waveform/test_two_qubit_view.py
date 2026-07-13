"""Tests for the coupled two-qubit view and its dispatch in WaveformViewer."""

from __future__ import annotations

import pathlib

import pytest
from gui.waveform.main_widget import WaveformViewer
from gui.waveform.two_qubit_view import TwoQubitView

# Self-contained (not `from conftest import ...`) to avoid the bare-`conftest`
# module-name collision between test dirs that lack __init__.py.
EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def two_qubit_result_h5(tmp_path) -> pathlib.Path:
    """A real two-qubit-solver HDF5 file built from the bundled example."""
    import jjqubit

    sol = jjqubit.solve_two_qubit(EXAMPLES_DIR / "two_transmon.json")
    out_path = tmp_path / "two_qubit.h5"
    sol.write_hdf5(out_path)
    return out_path


def test_view_loads_coupled_spectrum(qapp, two_qubit_result_h5):
    view = TwoQubitView()
    view.load_file(two_qubit_result_h5)
    assert view.result is not None
    assert len(view.result.coupled_levels_GHz) >= 3
    # Ground level is (essentially) zero, relative to the joint ground state.
    assert view.result.coupled_levels_GHz[0] == pytest.approx(0.0, abs=1e-9)


def test_viewer_dispatches_two_qubit_result(qapp, two_qubit_result_h5):
    viewer = WaveformViewer()
    viewer.open_file(two_qubit_result_h5)
    assert viewer.stack.currentWidget() is viewer.two_qubit_view


def test_info_text_handles_resonant_nan_zz(qapp, two_qubit_result_h5):
    # The bundled example is resonant, so ZZ is NaN -- the panel must render it
    # gracefully as "n/a" rather than the string "nan".
    view = TwoQubitView()
    view.load_file(two_qubit_result_h5)
    text = view._info_text(view.result)
    assert "iSWAP time" in text
    assert "n/a (resonance)" in text


def test_export_csv_writes_levels(qapp, two_qubit_result_h5, tmp_path):
    view = TwoQubitView()
    view.load_file(two_qubit_result_h5)
    out = tmp_path / "levels.csv"
    view.export_csv(out)
    assert out.exists()
    assert out.read_text().strip() != ""
