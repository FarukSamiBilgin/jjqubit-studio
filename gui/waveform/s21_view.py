"""Continuous S21 transmission-curve view (classical-solver results).

Renders magnitude (dB) and phase (deg) vs. frequency as two vertically
stacked, x-linked plots -- a continuous sweep, unlike the discrete
energy-level ladder in :mod:`gui.waveform.energy_level_view`, so it gets
its own plot layout rather than being squeezed into a shared abstraction.

Built against a PROVISIONAL classical-result HDF5 schema (see
``gui/waveform/hdf5_reader.py``) since solver-classical's real output
layout (Task #2) has not been finalized/relayed yet. Only
:func:`gui.waveform.hdf5_reader.load_classical_result` should need to
change once it is -- this view consumes the schema-independent
:class:`~gui.waveform.hdf5_reader.ClassicalResult` dataclass.
"""
from __future__ import annotations

from pathlib import Path

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .channel_toggle import ChannelToggleList
from .cursor_tool import CursorReadout
from .export import export_series_csv, save_figure_png
from .hdf5_reader import ClassicalResult, load_classical_result

MAGNITUDE_CHANNEL = "Magnitude (dB)"
PHASE_CHANNEL = "Phase (deg)"


class S21View(QWidget):
    """Magnitude/phase S21 sweep view with cursor, channel toggle and export."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: ClassicalResult | None = None

        self.graphics = pg.GraphicsLayoutWidget()
        self.graphics.setBackground("k")
        self.mag_plot = self.graphics.addPlot(row=0, col=0)
        self.mag_plot.setLabel("left", "|S21|", units="dB")
        self.mag_plot.showGrid(x=True, y=True, alpha=0.3)
        self.graphics.nextRow()
        self.phase_plot = self.graphics.addPlot(row=1, col=0)
        self.phase_plot.setLabel("left", "phase(S21)", units="deg")
        self.phase_plot.setLabel("bottom", "frequency", units="GHz")
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)
        self.phase_plot.setXLink(self.mag_plot)

        self.mag_curve = self.mag_plot.plot(pen=pg.mkPen(color="cyan", width=2))
        self.phase_curve = self.phase_plot.plot(pen=pg.mkPen(color="magenta", width=2))

        self.mag_cursor = CursorReadout(self.mag_plot, x_unit=" GHz", y_unit=" dB")
        self.phase_cursor = CursorReadout(self.phase_plot, x_unit=" GHz", y_unit=" deg")

        self.info_label = QLabel("No result loaded.")
        self.info_label.setWordWrap(True)

        self.channel_list = ChannelToggleList(self._on_channel_toggled)
        self.channel_list.add_channel(MAGNITUDE_CHANNEL, checked=True)
        self.channel_list.add_channel(PHASE_CHANNEL, checked=True)

        export_csv_btn = QPushButton("Export CSV…")
        export_png_btn = QPushButton("Export PNG…")
        export_csv_btn.clicked.connect(self.prompt_export_csv)
        export_png_btn.clicked.connect(self.prompt_export_png)

        side = QVBoxLayout()
        side.addWidget(QLabel("Channels"))
        side.addWidget(self.channel_list)
        side.addWidget(self.info_label)
        side.addStretch(1)
        export_row = QHBoxLayout()
        export_row.addWidget(export_csv_btn)
        export_row.addWidget(export_png_btn)
        side.addLayout(export_row)

        layout = QHBoxLayout(self)
        layout.addWidget(self.graphics, stretch=3)
        side_widget = QWidget()
        side_widget.setLayout(side)
        layout.addWidget(side_widget, stretch=1)

    # -- data loading -----------------------------------------------------

    def load_file(self, path: str | Path) -> None:
        """Read a classical-solver HDF5 file at ``path`` and display it."""
        self.load_result(load_classical_result(path))

    def load_result(self, result: ClassicalResult) -> None:
        """Populate both curves and the info panel from ``result``."""
        self.result = result
        self.mag_curve.setData(result.frequency_GHz, result.magnitude_dB)
        self.phase_curve.setData(result.frequency_GHz, result.phase_deg)
        self.mag_plot.vb.autoRange()
        self.phase_plot.vb.autoRange()
        self.info_label.setText(
            f"<b>{result.netlist_name}</b><br>"
            f"{len(result.frequency_GHz)} points, "
            f"{result.frequency_GHz.min():.4g}–{result.frequency_GHz.max():.4g} GHz"
        )

    # -- channel toggle -----------------------------------------------------

    def _on_channel_toggled(self, name: str, visible: bool) -> None:
        if name == MAGNITUDE_CHANNEL:
            self.mag_plot.setVisible(visible)
        elif name == PHASE_CHANNEL:
            self.phase_plot.setVisible(visible)

    # -- export -------------------------------------------------------------

    def export_csv(self, path: str | Path) -> None:
        """Write frequency, magnitude (dB) and phase (deg) to a CSV file."""
        if self.result is None:
            raise ValueError("no result loaded")
        export_series_csv(
            path,
            "frequency_GHz",
            self.result.frequency_GHz,
            {
                "magnitude_dB": self.result.magnitude_dB,
                "phase_deg": self.result.phase_deg,
            },
        )

    def export_png(self, path: str | Path) -> None:
        """Render the magnitude/phase sweep to a PNG file via matplotlib."""
        import matplotlib.pyplot as plt

        if self.result is None:
            raise ValueError("no result loaded")
        fig, (ax_mag, ax_phase) = plt.subplots(2, 1, sharex=True, figsize=(6, 6))
        ax_mag.plot(self.result.frequency_GHz, self.result.magnitude_dB, color="tab:blue")
        ax_mag.set_ylabel("|S21| (dB)")
        ax_mag.grid(True, alpha=0.3)
        ax_phase.plot(self.result.frequency_GHz, self.result.phase_deg, color="tab:orange")
        ax_phase.set_ylabel("phase (deg)")
        ax_phase.set_xlabel("frequency (GHz)")
        ax_phase.grid(True, alpha=0.3)
        fig.suptitle(self.result.netlist_name)
        save_figure_png(fig, path)

    def prompt_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if path:
            self.export_csv(path)

    def prompt_export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
        if path:
            self.export_png(path)
