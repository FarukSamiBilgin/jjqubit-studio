"""Tests for gui.waveform.cursor_tool.CursorReadout.

Drives the cursor via ``update_readout`` directly rather than simulating
real mouse events (Qt's synthetic mouse events are unreliable headlessly);
``update_readout`` is the same code path ``_on_mouse_moved`` calls once it
has resolved a scene position to data coordinates, so this still exercises
the readout logic that matters.
"""
from __future__ import annotations

import pyqtgraph as pg

from gui.waveform.cursor_tool import CursorReadout


class TestCursorReadout:
    def test_starts_hidden(self, qapp):
        plot_widget = pg.PlotWidget()
        cursor = CursorReadout(plot_widget.getPlotItem())
        assert cursor.vline.isVisible() is False
        assert cursor.hline.isVisible() is False
        assert cursor.label.isVisible() is False

    def test_update_readout_moves_lines_and_shows_them(self, qapp):
        plot_widget = pg.PlotWidget()
        cursor = CursorReadout(plot_widget.getPlotItem(), x_unit=" GHz", y_unit=" dB")
        cursor.update_readout(7.2, -3.5)
        assert cursor.vline.value() == 7.2
        assert cursor.hline.value() == -3.5
        assert cursor.vline.isVisible() is True
        assert "7.2" in cursor.label.toPlainText()
        assert "-3.5" in cursor.label.toPlainText()
        assert "GHz" in cursor.label.toPlainText()
        assert "dB" in cursor.label.toPlainText()

    def test_set_visible_false_hides_everything(self, qapp):
        plot_widget = pg.PlotWidget()
        cursor = CursorReadout(plot_widget.getPlotItem())
        cursor.update_readout(1.0, 2.0)
        cursor.set_visible(False)
        assert cursor.vline.isVisible() is False
        assert cursor.hline.isVisible() is False
        assert cursor.label.isVisible() is False
