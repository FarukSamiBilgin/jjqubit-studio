"""Right panel: the property/parameter editor for the selected element.

The form is generated entirely from ``core.netlist.ELEMENT_TYPES[type].params``
-- one row per ``ParamSpec``, a numeric field for the value and a unit combo
box restricted to tokens of that parameter's required dimension (via
``units_ui.units_for_dimension``). No element type gets a hand-written form;
adding a 9th element type to the registry (as ``resistor`` was added post-hoc)
requires zero changes here.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.netlist import ELEMENT_TYPES, Quantity

from .canvas_model import CanvasModel
from .units_ui import default_unit_for, units_for_dimension


class PropertyPanel(QWidget):
    """Displays and edits the parameters of the currently selected element.

    Signals:
        param_changed: Emitted with ``(element_id, param_name)`` after a value
            or unit edit is written back to the model, so listeners (e.g. a
            validation status bar) can refresh.
    """

    param_changed = Signal(str, str)

    def __init__(self, model: CanvasModel) -> None:
        super().__init__()
        self.model = model
        self._element_id: str | None = None
        self._value_boxes: dict[str, QDoubleSpinBox] = {}
        self._unit_boxes: dict[str, QComboBox] = {}

        self._outer = QVBoxLayout(self)
        self._title = QLabel("No element selected")
        self._outer.addWidget(self._title)
        self._form_container = QWidget()
        self._form = QFormLayout(self._form_container)
        self._outer.addWidget(self._form_container)
        self._outer.addStretch(1)

    def clear(self) -> None:
        """Show the empty ("no selection") state."""
        self._element_id = None
        self._title.setText("No element selected")
        self._clear_form()

    def show_element(self, element_id: str) -> None:
        """Populate the form for ``element_id`` from the model + its element type.

        Raises:
            KeyError: if ``element_id`` is not in the model.
        """
        el = self.model.elements[element_id]
        self._element_id = element_id
        etype = ELEMENT_TYPES[el.type]
        self._title.setText(f"{el.type}  —  {el.id}")
        self._clear_form()

        for spec in etype.params:
            quantity = el.params.get(spec.name)
            unit_choices = units_for_dimension(spec.dimension)

            value_box = QDoubleSpinBox()
            value_box.setRange(-1e12, 1e12)
            value_box.setDecimals(6)
            value_box.setValue(quantity.value if quantity is not None else 0.0)
            value_box.valueChanged.connect(
                lambda _v, name=spec.name: self._on_edited(name)
            )
            self._value_boxes[spec.name] = value_box

            unit_box = QComboBox()
            unit_box.addItems(unit_choices)
            current_unit = quantity.unit if quantity is not None else default_unit_for(spec.dimension)
            if current_unit in unit_choices:
                unit_box.setCurrentText(current_unit)
            unit_box.currentTextChanged.connect(
                lambda _u, name=spec.name: self._on_edited(name)
            )
            self._unit_boxes[spec.name] = unit_box

            row = QWidget()
            row_layout = _row_layout(row, value_box, unit_box)
            label = spec.name + ("" if spec.required else " (optional)")
            self._form.addRow(label, row)

        if not etype.params:
            self._form.addRow(QLabel("(no parameters)"))

    def _on_edited(self, param_name: str) -> None:
        if self._element_id is None:
            return
        value_box = self._value_boxes[param_name]
        unit_box = self._unit_boxes[param_name]
        quantity = Quantity(value=value_box.value(), unit=unit_box.currentText())
        self.model.set_param(self._element_id, param_name, quantity)
        self.param_changed.emit(self._element_id, param_name)

    def _clear_form(self) -> None:
        self._value_boxes.clear()
        self._unit_boxes.clear()
        while self._form.rowCount():
            self._form.removeRow(0)


def _row_layout(row: QWidget, value_box: QDoubleSpinBox, unit_box: QComboBox) -> QWidget:
    """Pack ``value_box`` and ``unit_box`` side by side in ``row``."""
    from PySide6.QtWidgets import QHBoxLayout

    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(value_box, 2)
    layout.addWidget(unit_box, 1)
    return row
