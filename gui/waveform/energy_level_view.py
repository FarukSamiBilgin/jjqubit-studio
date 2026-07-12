"""Discrete energy-level diagram view (quantum-solver results).

Renders ``QuantumResult.energy_levels_GHz`` as the classic physics
"ladder" diagram -- one horizontal segment per eigenlevel -- rather than
forcing it through a generic x/y line-plot widget (levels have no
meaningful x-axis; what matters is their relative height and spacing).
The 0->1 transition is highlighted since it is the qubit frequency.
"""
from __future__ import annotations

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

from .channel_toggle import ChannelToggleList
from .cursor_tool import CursorReadout
from .export import export_series_csv, save_figure_png
from .hdf5_reader import QuantumResult, load_quantum_result

_LEVEL_X0, _LEVEL_X1 = 0.0, 1.0
_LABEL_X = _LEVEL_X1 + 0.05


class EnergyLevelView(QWidget):
    """Energy-level ladder diagram + per-level toggle, cursor and export."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: QuantumResult | None = None
        self._level_curves: dict[str, pg.PlotDataItem] = {}
        self._level_labels: dict[str, pg.TextItem] = {}
        self._transition_items: list[pg.GraphicsObject] = []

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("k")
        plot_item = self.plot_widget.getPlotItem()
        plot_item.setLabel("left", "Energy (relative to ground state)", units="GHz")
        plot_item.setLabel("bottom", "")
        plot_item.getAxis("bottom").setStyle(showValues=False)
        plot_item.showGrid(y=True, alpha=0.3)
        self.cursor = CursorReadout(plot_item, y_unit=" GHz")

        self.info_label = QLabel("No result loaded.")
        self.info_label.setWordWrap(True)

        self.channel_list = ChannelToggleList(self._on_channel_toggled)

        export_csv_btn = QPushButton("Export CSV…")
        export_png_btn = QPushButton("Export PNG…")
        export_csv_btn.clicked.connect(self.prompt_export_csv)
        export_png_btn.clicked.connect(self.prompt_export_png)

        side = QVBoxLayout()
        side.addWidget(QLabel("Levels"))
        side.addWidget(self.channel_list)
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
        """Read a quantum-solver HDF5 file at ``path`` and display it."""
        self.load_result(load_quantum_result(path))

    def load_result(self, result: QuantumResult) -> None:
        """Populate the diagram, channel list and info panel from ``result``.

        Removes only the previously-plotted level curves/labels (not
        ``PlotItem.clear()``), so the shared :class:`CursorReadout` -- and
        its mouse-move connection -- survives across repeated loads instead
        of being recreated (and leaked) every time.
        """
        self.result = result
        for curve in self._level_curves.values():
            self.plot_widget.removeItem(curve)
        for label in self._level_labels.values():
            self.plot_widget.removeItem(label)
        for item in self._transition_items:
            self.plot_widget.removeItem(item)
        self._level_curves.clear()
        self._level_labels.clear()
        self._transition_items.clear()
        self.channel_list.clear_channels()

        levels = result.energy_levels_GHz
        for n, energy in enumerate(levels):
            name = f"n={n}"
            color = (255, 140, 0) if n <= 1 else (100, 180, 255)
            curve = self.plot_widget.plot(
                [_LEVEL_X0, _LEVEL_X1], [energy, energy], pen=pg.mkPen(color=color, width=3)
            )
            label = pg.TextItem(f"{name}  ({energy:.4g} GHz)", color=color, anchor=(0, 0.5))
            label.setPos(_LABEL_X, energy)
            self.plot_widget.addItem(label)
            self._level_curves[name] = curve
            self._level_labels[name] = label
            self.channel_list.add_channel(name, checked=True)

        if len(levels) >= 2:
            self._draw_01_transition(levels[0], levels[1], result.E01_GHz, result.anharmonicity_GHz)

        self.plot_widget.getPlotItem().vb.autoRange()
        self.info_label.setText(self._info_text(result))

    def _draw_01_transition(
        self, e0: float, e1: float, e01_ghz: float, anharmonicity_ghz: float
    ) -> None:
        x = 0.5
        arrow = pg.PlotDataItem(
            [x, x],
            [e0, e1],
            pen=pg.mkPen(color="yellow", width=1, style=pg.QtCore.Qt.PenStyle.DotLine),
        )
        self.plot_widget.addItem(arrow)
        note = pg.TextItem(
            f"E01 = {e01_ghz:.4g} GHz\nanharmonicity = {anharmonicity_ghz:.4g} GHz",
            color="yellow",
            anchor=(0, 1),
        )
        note.setPos(x + 0.02, (e0 + e1) / 2)
        self.plot_widget.addItem(note)
        self._transition_items.extend([arrow, note])

    def _info_text(self, result: QuantumResult) -> str:
        return (
            f"<b>{result.netlist_name}</b><br>"
            f"Ej = {result.Ej_GHz:.4g} GHz, Ec = {result.Ec_GHz:.4g} GHz, "
            f"Ej/Ec = {result.Ej_over_Ec:.3g}<br>"
            f"E01 = {result.E01_GHz:.4g} GHz, anharmonicity = {result.anharmonicity_GHz:.4g} GHz<br>"
            f"Resonator {result.resonator_id}: f0 = {result.f0_GHz:.4g} GHz, Q = {result.Q:.4g}, "
            f"kappa = {result.kappa_GHz:.4g} GHz<br>"
            f"g = {result.g_GHz * 1e3:.4g} MHz, chi = {result.chi_GHz * 1e3:.4g} MHz, "
            f"Delta = {result.Delta_GHz:.4g} GHz<br>"
            f"<i>{result.g_GHz_description}</i>"
        )

    # -- channel toggle ---------------------------------------------------

    def _on_channel_toggled(self, name: str, visible: bool) -> None:
        if name in self._level_curves:
            self._level_curves[name].setVisible(visible)
            self._level_labels[name].setVisible(visible)

    # -- export -----------------------------------------------------------

    def _export_series(self) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        if self.result is None:
            raise ValueError("no result loaded")
        levels = self.result.energy_levels_GHz
        return np.arange(len(levels)), {"energy_GHz": np.asarray(levels)}

    def export_csv(self, path: str | Path) -> None:
        """Write level index vs. energy (GHz) to a CSV file."""
        x, series = self._export_series()
        export_series_csv(path, "level_index", x, series)

    def export_png(self, path: str | Path) -> None:
        """Render the energy-level ladder to a PNG file via matplotlib."""
        import matplotlib.pyplot as plt

        if self.result is None:
            raise ValueError("no result loaded")
        fig, ax = plt.subplots(figsize=(4, 6))
        for n, energy in enumerate(self.result.energy_levels_GHz):
            color = "darkorange" if n <= 1 else "steelblue"
            ax.hlines(energy, _LEVEL_X0, _LEVEL_X1, colors=color, linewidth=3)
            ax.text(_LABEL_X, energy, f"n={n}  ({energy:.4g} GHz)", va="center", color=color)
        ax.set_xlim(_LEVEL_X0, _LABEL_X + 1.0)
        ax.set_xticks([])
        ax.set_ylabel("Energy (GHz, relative to ground state)")
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
