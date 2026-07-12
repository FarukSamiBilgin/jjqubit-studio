"""Tests for gui.waveform.s21_view.S21View.

Loads the synthetic classical-result HDF5 (``classical_result_h5`` fixture,
see ``tests/waveform/classical_synthetic.py``) since solver-classical's
real output isn't available yet -- see that fixture's docstring.
"""
from __future__ import annotations

from PySide6.QtCore import Qt

from gui.waveform.hdf5_reader import load_classical_result
from gui.waveform.s21_view import MAGNITUDE_CHANNEL, PHASE_CHANNEL, S21View


class TestS21View:
    def test_load_file_populates_curves(self, qapp, classical_result_h5):
        view = S21View()
        view.load_file(classical_result_h5)
        result = load_classical_result(classical_result_h5)
        xs, ys = view.mag_curve.getData()
        assert len(xs) == len(result.frequency_GHz)
        assert list(xs) == list(result.frequency_GHz)
        assert list(ys) == list(result.magnitude_dB)
        xs_p, ys_p = view.phase_curve.getData()
        assert list(ys_p) == list(result.phase_deg)

    def test_channel_list_has_magnitude_and_phase(self, qapp, classical_result_h5):
        view = S21View()
        view.load_file(classical_result_h5)
        names = {view.channel_list.item(i).text() for i in range(view.channel_list.count())}
        assert names == {MAGNITUDE_CHANNEL, PHASE_CHANNEL}

    def test_toggling_magnitude_channel_hides_plot(self, qapp, classical_result_h5):
        view = S21View()
        view.load_file(classical_result_h5)
        item = next(
            view.channel_list.item(i)
            for i in range(view.channel_list.count())
            if view.channel_list.item(i).text() == MAGNITUDE_CHANNEL
        )
        item.setCheckState(Qt.CheckState.Unchecked)
        assert view.mag_plot.isVisible() is False
        assert view.phase_plot.isVisible() is True

    def test_export_csv(self, qapp, classical_result_h5, tmp_path):
        view = S21View()
        view.load_file(classical_result_h5)
        out = tmp_path / "s21.csv"
        view.export_csv(out)
        lines = out.read_text().strip().splitlines()
        assert lines[0] == "frequency_GHz,magnitude_dB,phase_deg"
        assert len(lines) == 1 + len(view.result.frequency_GHz)

    def test_export_png(self, qapp, classical_result_h5, tmp_path):
        view = S21View()
        view.load_file(classical_result_h5)
        out = tmp_path / "s21.png"
        view.export_png(out)
        assert out.exists()
        assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
