"""RCSJ views: the I-V hysteresis loop and the phase-dynamics time trace.

Two continuous-curve views for the classical-solver ``/rcsj`` group, kept
separate from the S21 view because they carry different axes/physics:

* :class:`IVCurveView` -- voltage (uV) vs. bias current (nA), plotting the
  ascending AND descending sweeps so the retrapping-current hysteresis of
  an underdamped junction is visible (per the ``/rcsj/iv_curve`` up/down
  datasets).
* :class:`PhaseDynamicsView` -- phase (rad) and voltage (uV) vs. time (ns),
  as two x-linked stacked plots (phase and voltage live on very different
  scales, so they get separate y-axes rather than one shared axis).

Both consume the schema-independent dataclasses from
:mod:`gui.waveform.hdf5_reader`, never the HDF5 file directly.
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
from .hdf5_reader import RcsjData

UP_SWEEP_CHANNEL = "Up sweep"
DOWN_SWEEP_CHANNEL = "Down sweep"
PHASE_CHANNEL = "Phase (rad)"
VOLTAGE_CHANNEL = "Voltage (uV)"


def _export_side_panel(
    widget: QWidget,
    channel_list: ChannelToggleList,
    info_label: QLabel,
    on_export_csv,
    on_export_png,
) -> QWidget:
    """Build the shared right-hand column (channel list + info + export buttons)."""
    export_csv_btn = QPushButton("Export CSV…")
    export_png_btn = QPushButton("Export PNG…")
    export_csv_btn.clicked.connect(on_export_csv)
    export_png_btn.clicked.connect(on_export_png)

    side = QVBoxLayout()
    side.addWidget(QLabel("Channels"))
    side.addWidget(channel_list)
    side.addWidget(info_label)
    side.addStretch(1)
    export_row = QHBoxLayout()
    export_row.addWidget(export_csv_btn)
    export_row.addWidget(export_png_btn)
    side.addLayout(export_row)

    side_widget = QWidget(widget)
    side_widget.setLayout(side)
    return side_widget


class IVCurveView(QWidget):
    """Voltage-vs-bias I-V curve (both sweep directions) with cursor and export."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rcsj: RcsjData | None = None

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("k")
        plot_item = self.plot_widget.getPlotItem()
        plot_item.setLabel("bottom", "bias current", units="nA")
        plot_item.setLabel("left", "voltage", units="uV")
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.cursor = CursorReadout(plot_item, x_unit=" nA", y_unit=" uV")

        self.up_curve = self.plot_widget.plot(
            pen=pg.mkPen(color="cyan", width=2), name="up"
        )
        self.down_curve = self.plot_widget.plot(
            pen=pg.mkPen(color="orange", width=2, style=pg.QtCore.Qt.PenStyle.DashLine),
            name="down",
        )

        self.info_label = QLabel("No result loaded.")
        self.info_label.setWordWrap(True)
        self.channel_list = ChannelToggleList(self._on_channel_toggled)
        self.channel_list.add_channel(UP_SWEEP_CHANNEL, checked=True)
        self.channel_list.add_channel(DOWN_SWEEP_CHANNEL, checked=True)

        side_widget = _export_side_panel(
            self,
            self.channel_list,
            self.info_label,
            self.prompt_export_csv,
            self.prompt_export_png,
        )
        layout = QHBoxLayout(self)
        layout.addWidget(self.plot_widget, stretch=3)
        layout.addWidget(side_widget, stretch=1)

    def load_rcsj(self, rcsj: RcsjData) -> None:
        """Populate both sweep curves and the info panel from a :class:`RcsjData`."""
        self.rcsj = rcsj
        iv = rcsj.iv_curve
        self.up_curve.setData(iv.bias_current_up_nA, iv.voltage_up_uV)
        self.down_curve.setData(iv.bias_current_down_nA, iv.voltage_down_uV)
        self.plot_widget.getPlotItem().vb.autoRange()
        self.info_label.setText(
            f"Junction {rcsj.junction_id}<br>"
            f"Ic = {rcsj.Ic_nA:.4g} nA, Rn = {rcsj.Rn_total_ohm:.4g} ohm<br>"
            f"C = {rcsj.C_total_fF:.4g} fF<br>"
            f"quality factor Q = {rcsj.quality_factor:.4g} "
            f"({'underdamped/hysteretic' if rcsj.quality_factor > 1 else 'overdamped'})<br>"
            f"plasma freq = {rcsj.plasma_frequency_GHz:.4g} GHz"
        )

    def _on_channel_toggled(self, name: str, visible: bool) -> None:
        if name == UP_SWEEP_CHANNEL:
            self.up_curve.setVisible(visible)
        elif name == DOWN_SWEEP_CHANNEL:
            self.down_curve.setVisible(visible)

    def export_csv(self, path: str | Path) -> None:
        """Write both sweep directions (bias nA, voltage uV) to a CSV file."""
        if self.rcsj is None:
            raise ValueError("no rcsj result loaded")
        iv = self.rcsj.iv_curve
        export_series_csv(
            path,
            "bias_current_up_nA",
            iv.bias_current_up_nA,
            {
                "voltage_up_uV": iv.voltage_up_uV,
                "bias_current_down_nA": iv.bias_current_down_nA,
                "voltage_down_uV": iv.voltage_down_uV,
            },
        )

    def export_png(self, path: str | Path) -> None:
        """Render the I-V hysteresis loop to a PNG file via matplotlib."""
        import matplotlib.pyplot as plt

        if self.rcsj is None:
            raise ValueError("no rcsj result loaded")
        iv = self.rcsj.iv_curve
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.plot(
            iv.bias_current_up_nA, iv.voltage_up_uV, color="tab:blue", label="up sweep"
        )
        ax.plot(
            iv.bias_current_down_nA,
            iv.voltage_down_uV,
            color="tab:orange",
            linestyle="--",
            label="down sweep",
        )
        ax.set_xlabel("bias current (nA)")
        ax.set_ylabel("voltage (uV)")
        ax.set_title(f"I-V curve — junction {self.rcsj.junction_id}")
        ax.legend()
        ax.grid(True, alpha=0.3)
        save_figure_png(fig, path)

    def prompt_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if path:
            self.export_csv(path)

    def prompt_export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
        if path:
            self.export_png(path)


class PhaseDynamicsView(QWidget):
    """Phase (rad) and voltage (uV) vs. time (ns), as two x-linked stacked plots."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rcsj: RcsjData | None = None

        self.graphics = pg.GraphicsLayoutWidget()
        self.graphics.setBackground("k")
        self.phase_plot = self.graphics.addPlot(row=0, col=0)
        self.phase_plot.setLabel("left", "phase", units="rad")
        self.phase_plot.showGrid(x=True, y=True, alpha=0.3)
        self.graphics.nextRow()
        self.voltage_plot = self.graphics.addPlot(row=1, col=0)
        self.voltage_plot.setLabel("left", "voltage", units="uV")
        self.voltage_plot.setLabel("bottom", "time", units="ns")
        self.voltage_plot.showGrid(x=True, y=True, alpha=0.3)
        self.voltage_plot.setXLink(self.phase_plot)

        self.phase_curve = self.phase_plot.plot(pen=pg.mkPen(color="yellow", width=1))
        self.voltage_curve = self.voltage_plot.plot(pen=pg.mkPen(color="lime", width=1))

        self.phase_cursor = CursorReadout(self.phase_plot, x_unit=" ns", y_unit=" rad")
        self.voltage_cursor = CursorReadout(
            self.voltage_plot, x_unit=" ns", y_unit=" uV"
        )

        self.info_label = QLabel("No result loaded.")
        self.info_label.setWordWrap(True)
        self.channel_list = ChannelToggleList(self._on_channel_toggled)
        self.channel_list.add_channel(PHASE_CHANNEL, checked=True)
        self.channel_list.add_channel(VOLTAGE_CHANNEL, checked=True)

        side_widget = _export_side_panel(
            self,
            self.channel_list,
            self.info_label,
            self.prompt_export_csv,
            self.prompt_export_png,
        )
        layout = QHBoxLayout(self)
        layout.addWidget(self.graphics, stretch=3)
        layout.addWidget(side_widget, stretch=1)

    def load_rcsj(self, rcsj: RcsjData) -> None:
        """Populate the phase/voltage time traces and info panel from a :class:`RcsjData`."""
        self.rcsj = rcsj
        dyn = rcsj.phase_dynamics
        self.phase_curve.setData(dyn.time_ns, dyn.phase_rad)
        self.voltage_curve.setData(dyn.time_ns, dyn.voltage_uV)
        self.phase_plot.vb.autoRange()
        self.voltage_plot.vb.autoRange()
        self.info_label.setText(
            f"Junction {rcsj.junction_id}<br>"
            f"bias = {dyn.bias_current_nA:.4g} nA (Ic = {rcsj.Ic_nA:.4g} nA)<br>"
            f"settled DC voltage = {dyn.dc_voltage_uV:.4g} uV<br>"
            f"{len(dyn.time_ns)} samples over "
            f"{dyn.time_ns.min():.4g}–{dyn.time_ns.max():.4g} ns"
        )

    def _on_channel_toggled(self, name: str, visible: bool) -> None:
        if name == PHASE_CHANNEL:
            self.phase_plot.setVisible(visible)
        elif name == VOLTAGE_CHANNEL:
            self.voltage_plot.setVisible(visible)

    def export_csv(self, path: str | Path) -> None:
        """Write time (ns), phase (rad) and voltage (uV) to a CSV file."""
        if self.rcsj is None:
            raise ValueError("no rcsj result loaded")
        dyn = self.rcsj.phase_dynamics
        export_series_csv(
            path,
            "time_ns",
            dyn.time_ns,
            {"phase_rad": dyn.phase_rad, "voltage_uV": dyn.voltage_uV},
        )

    def export_png(self, path: str | Path) -> None:
        """Render the phase/voltage time traces to a PNG file via matplotlib."""
        import matplotlib.pyplot as plt

        if self.rcsj is None:
            raise ValueError("no rcsj result loaded")
        dyn = self.rcsj.phase_dynamics
        fig, (ax_phase, ax_v) = plt.subplots(2, 1, sharex=True, figsize=(6, 6))
        ax_phase.plot(dyn.time_ns, dyn.phase_rad, color="tab:olive")
        ax_phase.set_ylabel("phase (rad)")
        ax_phase.grid(True, alpha=0.3)
        ax_v.plot(dyn.time_ns, dyn.voltage_uV, color="tab:green")
        ax_v.set_ylabel("voltage (uV)")
        ax_v.set_xlabel("time (ns)")
        ax_v.grid(True, alpha=0.3)
        fig.suptitle(f"Phase dynamics — junction {self.rcsj.junction_id}")
        save_figure_png(fig, path)

    def prompt_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV (*.csv)")
        if path:
            self.export_csv(path)

    def prompt_export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
        if path:
            self.export_png(path)
