"""Coupled two-qubit energy-level view (two-qubit-solver results).

Renders ``TwoQubitResult.coupled_levels_GHz`` as a ladder diagram (like the
single-qubit :class:`~gui.waveform.energy_level_view.EnergyLevelView`) and an
info panel with the two-qubit design metrics: bare frequencies, detuning,
exchange coupling J, static ZZ, iSWAP gate time, and per-qubit anharmonicity.
The single-excitation manifold (levels 1 and 2) is highlighted because its
splitting is the avoided crossing (= 2J on resonance).

Does no physics or HDF5-schema logic of its own -- all of that lives in
``hdf5_reader.py``; this widget only plots the loaded dataclass.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .cursor_tool import CursorReadout
from .export import export_series_csv, save_figure_png
from .hdf5_reader import TwoQubitResult, load_two_qubit_result

_LEVEL_X0, _LEVEL_X1 = 0.0, 1.0
_LABEL_X = _LEVEL_X1 + 0.05


class TwoQubitView(QWidget):
    """Coupled-spectrum ladder diagram + two-qubit metrics panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: TwoQubitResult | None = None
        self._level_items: list[pg.GraphicsObject] = []

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("k")
        plot_item = self.plot_widget.getPlotItem()
        plot_item.setLabel("left", "Joint energy (relative to ground)", units="GHz")
        plot_item.setLabel("bottom", "")
        plot_item.getAxis("bottom").setStyle(showValues=False)
        plot_item.showGrid(y=True, alpha=0.3)
        self.cursor = CursorReadout(plot_item, y_unit=" GHz")

        self.info_label = QLabel("No result loaded.")
        self.info_label.setWordWrap(True)

        export_csv_btn = QPushButton("Export CSV…")
        export_png_btn = QPushButton("Export PNG…")
        export_csv_btn.clicked.connect(self.prompt_export_csv)
        export_png_btn.clicked.connect(self.prompt_export_png)

        side = QVBoxLayout()
        side.addWidget(QLabel("Coupled two-qubit spectrum"))
        side.addWidget(self.info_label)
        side.addStretch(1)
        export_row = QHBoxLayout()
        export_row.addWidget(export_csv_btn)
        export_row.addWidget(export_png_btn)
        side.addLayout(export_row)

        layout = QHBoxLayout(self)
        layout.addWidget(self.plot_widget, stretch=3)
        side_widget = QWidget()
        side_widget.setLayout(side)
        layout.addWidget(side_widget, stretch=1)

    # -- data loading ---------------------------------------------------

    def load_file(self, path: str | Path) -> None:
        """Read a two-qubit-solver HDF5 file at ``path`` and display it."""
        self.load_result(load_two_qubit_result(path))

    def load_result(self, result: TwoQubitResult) -> None:
        """Populate the diagram and info panel from ``result``."""
        self.result = result
        for item in self._level_items:
            self.plot_widget.removeItem(item)
        self._level_items.clear()

        levels = result.coupled_levels_GHz
        for n, energy in enumerate(levels):
            # Ground (0), single-excitation manifold (1,2) highlighted; higher
            # (two-excitation) levels in a cooler colour.
            if n == 0:
                color = (160, 160, 160)
            elif n in (1, 2):
                color = (255, 140, 0)
            else:
                color = (100, 180, 255)
            curve = self.plot_widget.plot(
                [_LEVEL_X0, _LEVEL_X1],
                [energy, energy],
                pen=pg.mkPen(color=color, width=3),
            )
            label = pg.TextItem(
                f"|{n}>  ({energy:.4g} GHz)", color=color, anchor=(0, 0.5)
            )
            label.setPos(_LABEL_X, energy)
            self.plot_widget.addItem(label)
            self._level_items.extend([curve, label])

        # Mark the single-excitation splitting (the avoided crossing).
        if len(levels) >= 3:
            self._draw_splitting(levels[1], levels[2], result)

        self.plot_widget.getPlotItem().vb.autoRange()
        self.info_label.setText(self._info_text(result))

    def _draw_splitting(
        self, e_lower: float, e_upper: float, result: TwoQubitResult
    ) -> None:
        x = 0.5
        arrow = pg.PlotDataItem(
            [x, x],
            [e_lower, e_upper],
            pen=pg.mkPen(color="yellow", width=1, style=pg.QtCore.Qt.PenStyle.DotLine),
        )
        self.plot_widget.addItem(arrow)
        note = pg.TextItem(
            f"splitting = {result.one_excitation_splitting_GHz * 1e3:.3g} MHz\n"
            f"J = {result.J_GHz * 1e3:.3g} MHz",
            color="yellow",
            anchor=(0, 1),
        )
        note.setPos(x + 0.02, (e_lower + e_upper) / 2)
        self.plot_widget.addItem(note)
        self._level_items.extend([arrow, note])

    def _info_text(self, result: TwoQubitResult) -> str:
        zz = (
            "n/a (resonance)"
            if math.isnan(result.zz_MHz)
            else f"{result.zz_MHz:.3g} MHz"
        )
        iswap = (
            "inf (uncoupled)"
            if math.isinf(result.iswap_gate_time_ns)
            else f"{result.iswap_gate_time_ns:.3g} ns"
        )
        return (
            f"<b>{result.netlist_name}</b><br>"
            f"w1 = {result.omega1_GHz:.4g} GHz, w2 = {result.omega2_GHz:.4g} GHz, "
            f"detuning = {result.detuning_GHz * 1e3:.3g} MHz<br>"
            f"g = {result.g_GHz * 1e3:.3g} MHz (Cc = {result.Cc_fF:.3g} fF)<br>"
            f"J = {result.J_GHz * 1e3:.3g} MHz, ZZ = {zz}<br>"
            f"iSWAP time = {iswap}<br>"
            f"anharmonicity: q1 = {result.anharmonicity1_MHz:.3g} MHz, "
            f"q2 = {result.anharmonicity2_MHz:.3g} MHz"
        )

    # -- export -----------------------------------------------------------

    def _export_series(self) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        if self.result is None:
            raise ValueError("no result loaded")
        levels = self.result.coupled_levels_GHz
        return np.arange(len(levels)), {"joint_energy_GHz": np.asarray(levels)}

    def export_csv(self, path: str | Path) -> None:
        """Write joint-level index vs. energy (GHz) to a CSV file."""
        x, series = self._export_series()
        export_series_csv(path, "level_index", x, series)

    def export_png(self, path: str | Path) -> None:
        """Render the coupled-level ladder to a PNG file via matplotlib."""
        import matplotlib.pyplot as plt

        if self.result is None:
            raise ValueError("no result loaded")
        fig, ax = plt.subplots(figsize=(4, 6))
        for n, energy in enumerate(self.result.coupled_levels_GHz):
            color = "darkorange" if n in (1, 2) else "steelblue"
            ax.hlines(energy, _LEVEL_X0, _LEVEL_X1, colors=color, linewidth=3)
            ax.text(
                _LABEL_X, energy, f"|{n}>  ({energy:.4g} GHz)", va="center", color=color
            )
        ax.set_xlim(_LEVEL_X0, _LABEL_X + 1.0)
        ax.set_xticks([])
        ax.set_ylabel("Joint energy (GHz, relative to ground)")
        ax.set_title(self.result.netlist_name)
        save_figure_png(fig, path)

    def prompt_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if path:
            self.export_csv(path)

    def prompt_export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
        if path:
            self.export_png(path)
