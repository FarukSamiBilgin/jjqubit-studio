"""``WaveformViewer``: the top-level widget for Task #5.

Reads a solver result HDF5 file, detects whether it is a quantum-solver or
classical-solver result (see ``gui/waveform/hdf5_reader.py``) and shows the
matching view -- :class:`~gui.waveform.energy_level_view.EnergyLevelView`
for discrete spectra, :class:`~gui.waveform.classical_view.ClassicalView`
(tabbed S21 / I-V / phase-dynamics) for continuous classical results. This
is the widget ``app-core`` (Task #6) embeds; it is also usable standalone
via ``python -m gui.waveform`` (see ``__main__.py``).

Does no physics and no HDF5-schema logic of its own -- all of that lives in
``hdf5_reader.py``; this module only wires file I/O to the two view widgets.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .classical_view import ClassicalView
from .energy_level_view import EnergyLevelView
from .hdf5_reader import detect_result_kind


class WaveformViewer(QWidget):
    """Multi-channel waveform viewer: opens an HDF5 result and picks the right view."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.energy_level_view = EnergyLevelView()
        self.classical_view = ClassicalView()
        self._placeholder = QLabel("Open a solver result HDF5 file to begin.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._placeholder)
        self.stack.addWidget(self.energy_level_view)
        self.stack.addWidget(self.classical_view)
        self.stack.setCurrentWidget(self._placeholder)

        open_btn = QPushButton("Open HDF5…")
        open_btn.clicked.connect(self.prompt_open_file)
        self.file_label = QLabel("(no file loaded)")

        toolbar = QHBoxLayout()
        toolbar.addWidget(open_btn)
        toolbar.addWidget(self.file_label)
        toolbar.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self.stack)

    def open_file(self, path: str | Path) -> None:
        """Detect the result kind at ``path`` and display it in the matching view.

        Raises:
            ValueError: if the file's format cannot be recognized as either
                a quantum or a classical solver result.
        """
        kind = detect_result_kind(path)
        if kind == "quantum":
            self.energy_level_view.load_file(path)
            self.stack.setCurrentWidget(self.energy_level_view)
        elif kind == "classical":
            self.classical_view.load_file(path)
            self.stack.setCurrentWidget(self.classical_view)
        else:
            raise ValueError(f"{path!r}: unrecognized result format")
        self.file_label.setText(str(path))

    def prompt_open_file(self) -> None:
        """Open a file dialog and load the chosen HDF5 result file."""
        path, _ = QFileDialog.getOpenFileName(self, "Open Result", "", "HDF5 (*.h5 *.hdf5)")
        if not path:
            return
        try:
            self.open_file(path)
        except (ValueError, OSError, KeyError) as exc:
            QMessageBox.critical(self, "Failed to open result", str(exc))
