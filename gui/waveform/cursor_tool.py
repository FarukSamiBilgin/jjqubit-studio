"""Schema-independent crosshair cursor with an (x, y) readout label.

A mouse-tracking crosshair does not care whether the axes hold discrete
energy levels or a continuous S21 sweep, so this is shared by both the
energy-level view and the S21 view rather than reimplemented per-view.
"""

from __future__ import annotations

from typing import Any

import pyqtgraph as pg


class CursorReadout:
    """Crosshair (vertical + horizontal line) plus a floating text label.

    Attaches to a single ``pyqtgraph.PlotItem`` and tracks mouse movement
    over it via a rate-limited ``SignalProxy`` (so it stays responsive
    without flooding Qt with per-pixel updates).
    """

    def __init__(
        self, plot_item: pg.PlotItem, *, x_unit: str = "", y_unit: str = ""
    ) -> None:
        self.plot_item = plot_item
        self.x_unit = x_unit
        self.y_unit = y_unit

        dashed = pg.mkPen(color=(200, 200, 0), style=pg.QtCore.Qt.PenStyle.DashLine)
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=dashed)
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=dashed)
        self.label = pg.TextItem(anchor=(0, 1), color=(255, 255, 0))
        for item in (self.vline, self.hline, self.label):
            plot_item.addItem(item, ignoreBounds=True)
        self.set_visible(False)

        # Keep a reference: pyqtgraph's SignalProxy only stays connected as
        # long as something holds it alive.
        self._proxy = pg.SignalProxy(
            plot_item.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved
        )

    def set_visible(self, visible: bool) -> None:
        """Show or hide the crosshair and label together."""
        self.vline.setVisible(visible)
        self.hline.setVisible(visible)
        self.label.setVisible(visible)

    def update_readout(self, x: float, y: float) -> None:
        """Move the crosshair/label to data coordinates ``(x, y)`` and show it.

        Public (not just wired to mouse movement) so tests can drive the
        cursor directly without simulating real mouse events.
        """
        self.vline.setPos(x)
        self.hline.setPos(y)
        self.label.setText(f"x = {x:.4g}{self.x_unit}\ny = {y:.4g}{self.y_unit}")
        self.label.setPos(x, y)
        self.set_visible(True)

    def _on_mouse_moved(self, evt: tuple[Any, ...]) -> None:
        pos = evt[0]
        if not self.plot_item.sceneBoundingRect().contains(pos):
            self.set_visible(False)
            return
        mouse_point = self.plot_item.vb.mapSceneToView(pos)
        self.update_readout(mouse_point.x(), mouse_point.y())
