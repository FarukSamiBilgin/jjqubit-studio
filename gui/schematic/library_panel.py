"""Left panel: the element library, listing every registered element type.

Populated directly from ``core.netlist.ELEMENT_TYPES`` -- adding a new element
type to the frozen registry makes it appear here with no code change needed.
Drag an entry onto the canvas to place that element type.
"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from core.netlist import ELEMENT_TYPES
from .scene import ELEMENT_TYPE_MIME

# Human-friendly labels for the palette; falls back to the raw type name.
_DISPLAY_NAMES: dict[str, str] = {
    "junction": "Josephson Junction",
    "capacitor": "Capacitor",
    "inductor": "Inductor",
    "resistor": "Resistor",
    "resonator": "Resonator (LC)",
    "transmission_line": "Transmission Line",
    "current_source": "Current Source",
    "ground": "Ground",
}


class LibraryPanel(QListWidget):
    """A drag source listing every element type in ``core.netlist.ELEMENT_TYPES``."""

    def __init__(self) -> None:
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        for type_name in ELEMENT_TYPES:
            label = _DISPLAY_NAMES.get(type_name, type_name)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, type_name)
            terminals = ELEMENT_TYPES[type_name].terminals
            item.setToolTip(f"type={type_name!r}  terminals={terminals}")
            self.addItem(item)

    def startDrag(self, supportedActions) -> None:  # noqa: D102 - Qt override
        item = self.currentItem()
        if item is None:
            return
        type_name = item.data(Qt.UserRole)
        mime = QMimeData()
        mime.setData(ELEMENT_TYPE_MIME, type_name.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)
