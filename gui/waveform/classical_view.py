"""``ClassicalView``: tabbed container over the classical-solver sub-views.

A classical result may carry an S21 ``/readout`` group, an ``/rcsj`` group
(I-V curve + phase dynamics), or both. This widget reads the file once and
shows one tab per available dataset -- so a readout-only netlist shows just
the S21 tab, an RCSJ-only netlist shows the I-V and phase-dynamics tabs, and
a netlist with both shows all three. It renders whichever group(s) are
present rather than assuming a fixed set.

Each tab is a self-contained view (:mod:`gui.waveform.s21_view`,
:mod:`gui.waveform.rcsj_view`) with its own cursor, channel toggles and
CSV/PNG export; this widget only routes the loaded
:class:`~gui.waveform.hdf5_reader.ClassicalResult` to them.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .hdf5_reader import ClassicalResult, load_classical_result
from .rcsj_view import IVCurveView, PhaseDynamicsView
from .s21_view import S21View

S21_TAB = "S21 (readout)"
IV_TAB = "I-V curve"
PHASE_TAB = "Phase dynamics"


class ClassicalView(QWidget):
    """Shows a tab per available classical-result dataset (readout / I-V / phase)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.result: ClassicalResult | None = None

        # Persistent sub-views; shown/hidden as tabs depending on what the
        # loaded result contains (kept as attributes so tests and app-core
        # can reach into them, e.g. to trigger an export).
        self.s21_view = S21View()
        self.iv_view = IVCurveView()
        self.phase_view = PhaseDynamicsView()

        self.tabs = QTabWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

    def load_file(self, path: str | Path) -> None:
        """Read a classical-solver HDF5 file at ``path`` and display its tabs."""
        self.load_result(load_classical_result(path))

    def load_result(self, result: ClassicalResult) -> None:
        """Rebuild the tab set from ``result``, one tab per present dataset."""
        self.result = result
        self.tabs.clear()

        if result.readout is not None:
            self.s21_view.load_readout(result.readout)
            self.tabs.addTab(self.s21_view, S21_TAB)

        if result.rcsj is not None:
            self.iv_view.load_rcsj(result.rcsj)
            self.phase_view.load_rcsj(result.rcsj)
            self.tabs.addTab(self.iv_view, IV_TAB)
            self.tabs.addTab(self.phase_view, PHASE_TAB)

    def tab_titles(self) -> list[str]:
        """Return the currently shown tab titles, in order (for tests/debugging)."""
        return [self.tabs.tabText(i) for i in range(self.tabs.count())]
