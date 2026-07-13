"""Schematic canvas GUI (Task #4): drag-drop circuit editor over the netlist contract.

This package owns the schematic canvas: element library, drag-and-drop
placement, wiring, the per-element property editor, and canvas <-> netlist
JSON conversion. It builds against the frozen ``core.netlist`` contract and
does no physics of its own -- see ``core.netlist`` for the data model this
package produces and consumes.

Layout
------
``canvas_model.py``   Pure-Python (no PySide6) canvas state + netlist
                      conversion; unit-testable without a Qt event loop.
``units_ui.py``       Dimension-aware unit choices for the property editor.
``items.py``          ``QGraphicsItem`` classes (element/node/wire visuals).
``scene.py``          ``QGraphicsScene`` tying the model to the graphics items.
``view.py``           ``QGraphicsView`` with zoom/pan/grid.
``library_panel.py``  Element-type palette (drag source).
``property_panel.py`` Per-element parameter editor.
``main_widget.py``    ``SchematicEditor``, the widget other teammates embed.

Public entry point for other teammates (e.g. ``app-core``, Task #6):

    from gui.schematic import SchematicEditor
"""

from __future__ import annotations

from .canvas_model import (
    CanvasElement,
    CanvasModel,
    CanvasNode,
    CanvasWire,
    from_netlist,
)
from .main_widget import SchematicEditor

__all__ = [
    "SchematicEditor",
    "CanvasModel",
    "CanvasElement",
    "CanvasNode",
    "CanvasWire",
    "from_netlist",
]
