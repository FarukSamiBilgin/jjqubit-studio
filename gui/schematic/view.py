"""The schematic ``QGraphicsView``: zoom, pan and grid drawing.

Purely presentational -- it draws a background grid at the scene's native
resolution (see ``items.GRID_SIZE``) and handles zoom (mouse wheel / Ctrl+
wheel) and pan (middle-mouse drag, or space+left-drag). No netlist state
lives here.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

from .items import GRID_SIZE

ZOOM_IN_FACTOR = 1.15
ZOOM_OUT_FACTOR = 1.0 / ZOOM_IN_FACTOR
MIN_SCALE = 0.1
MAX_SCALE = 8.0


class SchematicView(QGraphicsView):
    """A ``QGraphicsView`` with grid background, mouse-wheel zoom and panning."""

    def __init__(self, scene=None) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._scale = 1.0
        self._space_panning = False
        self._grid_visible = True

    # -- zoom -----------------------------------------------------------------

    def zoom_by(self, factor: float) -> None:
        """Scale the view by ``factor``, clamped to ``[MIN_SCALE, MAX_SCALE]``."""
        new_scale = self._scale * factor
        if new_scale < MIN_SCALE or new_scale > MAX_SCALE:
            return
        self._scale = new_scale
        self.scale(factor, factor)

    def zoom_in(self) -> None:
        """Zoom in by one step."""
        self.zoom_by(ZOOM_IN_FACTOR)

    def zoom_out(self) -> None:
        """Zoom out by one step."""
        self.zoom_by(ZOOM_OUT_FACTOR)

    def zoom_reset(self) -> None:
        """Reset to 1:1 scale."""
        self.resetTransform()
        self._scale = 1.0

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: D102 - Qt override
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        event.accept()

    # -- grid -------------------------------------------------------------------

    def set_grid_visible(self, visible: bool) -> None:
        """Toggle background grid drawing."""
        self._grid_visible = visible
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: D102
        super().drawBackground(painter, rect)
        if not self._grid_visible:
            return
        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)
        pen = QPen(Qt.gray)
        pen.setWidth(0)
        painter.setPen(pen)
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += GRID_SIZE
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += GRID_SIZE

    # -- pan (space + left-drag, or middle-mouse drag) ---------------------------

    def keyPressEvent(self, event) -> None:  # noqa: D102 - Qt override
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_panning = True
            self.setDragMode(QGraphicsView.ScrollHandDrag)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: D102 - Qt override
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_panning = False
            self.setDragMode(QGraphicsView.RubberBandDrag)
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: D102 - Qt override
        if event.button() == Qt.MiddleButton:
            self._pan_start = (
                event.position() if hasattr(event, "position") else event.pos()
            )
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: D102 - Qt override
        if event.buttons() & Qt.MiddleButton:
            pos = event.position() if hasattr(event, "position") else event.pos()
            delta = pos - self._pan_start
            self._pan_start = pos
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - int(delta.x()))
            v_bar.setValue(v_bar.value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: D102 - Qt override
        if event.button() == Qt.MiddleButton:
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
