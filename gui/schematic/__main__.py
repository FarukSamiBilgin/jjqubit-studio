"""Standalone launcher for manual testing: ``python -m gui.schematic``.

Opens a bare window hosting :class:`~gui.schematic.main_widget.SchematicEditor`
so the schematic canvas can be exercised without the rest of the application
(Task #6's main window). Not used by the packaged app; a convenience for
development only.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from .main_widget import SchematicEditor


def main() -> int:
    """Run the standalone schematic editor window; returns the exit code."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("JJQubit Studio — Schematic Canvas (standalone)")
    window.setCentralWidget(SchematicEditor())
    window.resize(1200, 800)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
