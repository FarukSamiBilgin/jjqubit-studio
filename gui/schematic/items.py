"""QGraphicsItem classes for the schematic canvas.

These are a thin, purely visual mirror of :mod:`gui.schematic.canvas_model`:
every ``ElementItem`` corresponds to one ``CanvasElement``, every ``NodeItem``
to one ``CanvasNode``, and every ``WireItem`` to one ``CanvasWire``. Moving an
item snaps to the grid and updates any attached wires; no netlist or physics
logic lives here -- that stays in ``canvas_model.py``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

from core.netlist import ELEMENT_TYPES

if TYPE_CHECKING:
    from .scene import SchematicScene

GRID_SIZE = 20

TERMINAL_RADIUS = 5.0
BODY_COLOR = QColor("#3a5f8a")
BODY_SELECTED_COLOR = QColor("#e0a030")
TERMINAL_COLOR = QColor("#d0d0d0")
TERMINAL_HOVER_COLOR = QColor("#ffcc00")
NODE_COLOR = QColor("#40a060")
NODE_SELECTED_COLOR = QColor("#e0a030")
WIRE_COLOR = QColor("#a0a0a0")
INVALID_COLOR = QColor("#c0392b")


def snap(value: float, grid: int = GRID_SIZE) -> float:
    """Round ``value`` to the nearest multiple of ``grid``."""
    return round(value / grid) * grid


class TerminalHandle(QGraphicsEllipseItem):
    """A small clickable dot marking one terminal of an :class:`ElementItem`.

    Positioned in the parent element's local coordinates. Clicking it tells
    the owning :class:`SchematicScene` to start (or complete) a wiring
    gesture; the handle itself holds no netlist state.
    """

    def __init__(self, element_item: "ElementItem", terminal: int, name: str) -> None:
        r = TERMINAL_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r, parent=element_item)
        self.element_item = element_item
        self.terminal = terminal
        self.terminal_name = name
        self.setBrush(QBrush(TERMINAL_COLOR))
        self.setPen(QPen(Qt.black, 1))
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip(f"terminal {terminal} ({name})")

    def hoverEnterEvent(self, event) -> None:  # noqa: D102 - Qt override
        self.setBrush(QBrush(TERMINAL_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: D102 - Qt override
        self.setBrush(QBrush(TERMINAL_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: D102 - Qt override
        scene = self.scene()
        if scene is not None and hasattr(scene, "terminal_clicked"):
            scene.terminal_clicked(self.element_item, self.terminal)
        event.accept()

    def is_connected(self) -> bool:
        """Return whether the owning scene currently binds this terminal."""
        scene = self.scene()
        if scene is None or not hasattr(scene, "model"):
            return False
        return (
            scene.model.node_of(self.element_item.element_id, self.terminal)
            is not None
        )


class ElementItem(QGraphicsObject):
    """Visual representation of one circuit element (a labeled box with terminal dots).

    Args:
        element_id: The element's id in the :class:`~gui.schematic.canvas_model.CanvasModel`.
        type_name: Element type key (one of ``core.netlist.ELEMENT_TYPES``).
    """

    WIDTH = 90.0
    HEIGHT = 50.0

    def __init__(self, element_id: str, type_name: str) -> None:
        super().__init__()
        self.element_id = element_id
        self.type_name = type_name
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)
        etype = ELEMENT_TYPES[type_name]
        self.terminal_handles: list[TerminalHandle] = []
        for idx, name in enumerate(etype.terminals):
            handle = TerminalHandle(self, idx, name)
            handle.setPos(self._terminal_local_pos(idx, etype.n_terminals))
            self.terminal_handles.append(handle)

    # -- geometry -----------------------------------------------------------

    def _terminal_local_pos(self, index: int, n_terminals: int) -> QPointF:
        """Local-coordinate position of terminal ``index`` on the body."""
        half_w, half_h = self.WIDTH / 2, self.HEIGHT / 2
        if n_terminals <= 1:
            return QPointF(0, half_h)
        if n_terminals == 2:
            x = -half_w if index == 0 else half_w
            return QPointF(x, 0)
        # Fan out extra terminals evenly along the bottom edge.
        step = self.WIDTH / (n_terminals - 1)
        return QPointF(-half_w + step * index, half_h)

    def boundingRect(self) -> QRectF:  # noqa: D102 - Qt override
        margin = TERMINAL_RADIUS + 2
        return QRectF(
            -self.WIDTH / 2 - margin,
            -self.HEIGHT / 2 - margin,
            self.WIDTH + 2 * margin,
            self.HEIGHT + 2 * margin,
        )

    def terminal_scene_pos(self, terminal: int) -> QPointF:
        """Scene-coordinate position of ``terminal``'s connection point."""
        return self.terminal_handles[terminal].scenePos()

    # -- painting -------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:  # noqa: D102 - Qt override
        rect = QRectF(-self.WIDTH / 2, -self.HEIGHT / 2, self.WIDTH, self.HEIGHT)
        color = BODY_SELECTED_COLOR if self.isSelected() else BODY_COLOR
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.black, 2 if self.isSelected() else 1))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QPen(Qt.white))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(
            rect, Qt.AlignCenter, f"{self.type_name}\n{self.element_id}"
        )

    # -- movement / grid snap ---------------------------------------------

    def itemChange(self, change, value):  # noqa: D102 - Qt override
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            point: QPointF = value
            return QPointF(snap(point.x()), snap(point.y()))
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene() is not None:
            scene: SchematicScene = self.scene()
            if hasattr(scene, "on_element_moved"):
                scene.on_element_moved(self)
        return super().itemChange(change, value)


class NodeItem(QGraphicsObject):
    """Visual representation of one electrical node (a small labeled dot).

    Args:
        node_id: The node's id in the :class:`~gui.schematic.canvas_model.CanvasModel`.
    """

    RADIUS = 7.0

    def __init__(self, node_id: str) -> None:
        super().__init__()
        self.node_id = node_id
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self) -> QRectF:  # noqa: D102 - Qt override
        r = self.RADIUS + 12
        return QRectF(-r, -r, 2 * r, 2 * r + 14)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:  # noqa: D102 - Qt override
        color = NODE_SELECTED_COLOR if self.isSelected() else NODE_COLOR
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.black, 2 if self.isSelected() else 1))
        r = self.RADIUS
        painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))
        painter.setPen(QPen(Qt.black))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(-40, r + 2, 80, 14), Qt.AlignCenter, self.node_id)

    def mousePressEvent(self, event) -> None:  # noqa: D102 - Qt override
        scene = self.scene()
        if scene is not None and hasattr(scene, "node_clicked"):
            scene.node_clicked(self)
        super().mousePressEvent(event)

    def itemChange(self, change, value):  # noqa: D102 - Qt override
        if change == QGraphicsItem.ItemPositionChange and self.scene() is not None:
            point: QPointF = value
            return QPointF(snap(point.x()), snap(point.y()))
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene() is not None:
            scene: SchematicScene = self.scene()
            if hasattr(scene, "on_node_moved"):
                scene.on_node_moved(self)
        return super().itemChange(change, value)


class WireItem(QGraphicsLineItem):
    """A line connecting one element terminal to one node.

    Mirrors exactly one ``CanvasWire`` (``element_id``, ``terminal``,
    ``node_id``). Its endpoints are recomputed whenever the element or node it
    touches moves (see :meth:`update_line`).
    """

    def __init__(self, element_item: ElementItem, terminal: int, node_item: NodeItem) -> None:
        super().__init__()
        self.element_item = element_item
        self.terminal = terminal
        self.node_item = node_item
        self.setZValue(0)
        self.setPen(QPen(WIRE_COLOR, 2))
        self.update_line()

    def update_line(self) -> None:
        """Recompute the endpoints from the current terminal/node positions."""
        p1 = self.element_item.terminal_scene_pos(self.terminal)
        p2 = self.node_item.scenePos()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())
