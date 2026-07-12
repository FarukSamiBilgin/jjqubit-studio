"""Tests for gui.waveform.main_widget.WaveformViewer: format dispatch."""
from __future__ import annotations

import pytest

from gui.waveform.energy_level_view import EnergyLevelView
from gui.waveform.main_widget import WaveformViewer
from gui.waveform.s21_view import S21View


class TestWaveformViewer:
    def test_opens_quantum_file_in_energy_level_view(self, qapp, quantum_result_h5):
        viewer = WaveformViewer()
        viewer.open_file(quantum_result_h5)
        assert viewer.stack.currentWidget() is viewer.energy_level_view
        assert isinstance(viewer.stack.currentWidget(), EnergyLevelView)
        assert viewer.energy_level_view.result is not None
        assert str(quantum_result_h5) in viewer.file_label.text()

    def test_opens_classical_file_in_s21_view(self, qapp, classical_result_h5):
        viewer = WaveformViewer()
        viewer.open_file(classical_result_h5)
        assert viewer.stack.currentWidget() is viewer.s21_view
        assert isinstance(viewer.stack.currentWidget(), S21View)
        assert viewer.s21_view.result is not None

    def test_switching_between_files_swaps_view(self, qapp, quantum_result_h5, classical_result_h5):
        viewer = WaveformViewer()
        viewer.open_file(quantum_result_h5)
        assert viewer.stack.currentWidget() is viewer.energy_level_view
        viewer.open_file(classical_result_h5)
        assert viewer.stack.currentWidget() is viewer.s21_view

    def test_unrecognized_format_raises(self, qapp, tmp_path):
        import h5py

        path = tmp_path / "mystery.h5"
        with h5py.File(path, "w") as f:
            f.attrs["format"] = "nonsense"
        viewer = WaveformViewer()
        with pytest.raises(ValueError):
            viewer.open_file(path)
