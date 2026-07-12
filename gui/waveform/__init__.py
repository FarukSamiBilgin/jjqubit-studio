"""Waveform viewer GUI (Task #5): reads solver HDF5 results and plots them.

This package owns the dalga formu (waveform) viewer: a pyqtgraph-based
multi-view plot window with cursor readout, per-channel show/hide, and
CSV/PNG export. It reads HDF5 files produced by ``core/solvers/*`` and does
no physics of its own -- see ``core.solvers.quantum.hdf5_io`` for the
quantum-result layout, and ``gui/waveform/hdf5_reader.py`` for the
(provisional, pending Task #2) classical-result layout.

Layout
------
``hdf5_reader.py``       Format detection + HDF5 -> dataclass readers, no Qt.
``cursor_tool.py``       Schema-independent crosshair/readout, no Qt widgets
                         beyond the pyqtgraph items it manages.
``channel_toggle.py``    Reusable checkable per-channel list widget.
``export.py``            CSV/PNG export helpers, no Qt dependency.
``energy_level_view.py`` Discrete energy-level ladder diagram (quantum).
``s21_view.py``           Continuous magnitude/phase S21 sweep (classical).
``main_widget.py``        ``WaveformViewer``, the widget other teammates embed.

Public entry point for other teammates (e.g. ``app-core``, Task #6):

    from gui.waveform import WaveformViewer
"""
from __future__ import annotations

from .energy_level_view import EnergyLevelView
from .hdf5_reader import ClassicalResult, QuantumResult, detect_result_kind
from .main_widget import WaveformViewer
from .s21_view import S21View

__all__ = [
    "WaveformViewer",
    "EnergyLevelView",
    "S21View",
    "QuantumResult",
    "ClassicalResult",
    "detect_result_kind",
]
