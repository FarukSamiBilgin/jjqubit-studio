"""Standalone launcher for manual testing: ``python -m gui.waveform [result.h5]``.

Opens a bare window hosting :class:`~gui.waveform.main_widget.WaveformViewer`
so the waveform viewer can be exercised without the rest of the application
(Task #6's main window). If a path is given on the command line, it is
opened immediately. Not used by the packaged app; a convenience for
development only.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMainWindow

from .main_widget import WaveformViewer


def main(argv: list[str] | None = None) -> int:
    """Run the standalone waveform viewer window; returns the exit code."""
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    window = QMainWindow()
    window.setWindowTitle("JJQubit Studio — Waveform Viewer (standalone)")
    viewer = WaveformViewer()
    window.setCentralWidget(viewer)
    window.resize(1200, 800)
    window.show()

    args = [a for a in argv[1:] if not a.startswith("-")]
    if args:
        viewer.open_file(args[0])

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
