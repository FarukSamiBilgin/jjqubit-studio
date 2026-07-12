"""Tests for gui.waveform.energy_level_view.EnergyLevelView.

Loads a REAL quantum-solver HDF5 file (``quantum_result_h5`` fixture, built
from the actual Task #3 pipeline) and checks the ladder diagram, channel
toggle, and CSV/PNG export.
"""
from __future__ import annotations

from gui.waveform.energy_level_view import EnergyLevelView
from gui.waveform.hdf5_reader import load_quantum_result


class TestEnergyLevelView:
    def test_load_file_populates_level_curves(self, qapp, quantum_result_h5):
        view = EnergyLevelView()
        view.load_file(quantum_result_h5)
        result = load_quantum_result(quantum_result_h5)
        assert len(view._level_curves) == len(result.energy_levels_GHz)
        assert view.channel_list.count() == len(result.energy_levels_GHz)
        assert "n=0" in view._level_curves
        assert "n=1" in view._level_curves

    def test_load_file_populates_info_label(self, qapp, quantum_result_h5):
        view = EnergyLevelView()
        view.load_file(quantum_result_h5)
        text = view.info_label.text()
        assert view.result.netlist_name in text
        assert "Ej" in text
        assert "anharmonicity" in text

    def test_reloading_replaces_levels_not_accumulates(self, qapp, quantum_result_h5):
        view = EnergyLevelView()
        view.load_file(quantum_result_h5)
        n_first = len(view._level_curves)
        view.load_file(quantum_result_h5)
        assert len(view._level_curves) == n_first
        assert view.channel_list.count() == n_first

    def test_toggling_channel_hides_curve(self, qapp, quantum_result_h5):
        view = EnergyLevelView()
        view.load_file(quantum_result_h5)
        item = view.channel_list.item(0)
        assert item.text() == "n=0"
        from PySide6.QtCore import Qt

        item.setCheckState(Qt.CheckState.Unchecked)
        assert view._level_curves["n=0"].isVisible() is False
        assert view._level_labels["n=0"].isVisible() is False

    def test_export_csv(self, qapp, quantum_result_h5, tmp_path):
        view = EnergyLevelView()
        view.load_file(quantum_result_h5)
        out = tmp_path / "levels.csv"
        view.export_csv(out)
        lines = out.read_text().strip().splitlines()
        assert lines[0] == "level_index,energy_GHz"
        assert len(lines) == 1 + len(view.result.energy_levels_GHz)

    def test_export_png(self, qapp, quantum_result_h5, tmp_path):
        view = EnergyLevelView()
        view.load_file(quantum_result_h5)
        out = tmp_path / "levels.png"
        view.export_png(out)
        assert out.exists()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    def test_export_without_result_raises(self, qapp, tmp_path):
        view = EnergyLevelView()
        try:
            view.export_csv(tmp_path / "no.csv")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError when exporting with no result loaded")
