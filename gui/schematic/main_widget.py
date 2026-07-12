"""``SchematicEditor``: the top-level widget for Task #4.

Combines the element library (left), the schematic canvas (center) and the
property editor (right) behind a small toolbar (zoom, grid toggle, load/save
netlist, validate). This is the widget ``app-core`` (Task #6) is expected to
embed into the main window; it is fully usable standalone via
``python -m gui.schematic`` (see ``__main__.py``).

This module does no physics and no netlist validation logic of its own -- it
only calls ``core.netlist.load``/``dump``/``collect_errors`` and surfaces
their results.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.netlist import NetlistError, ValidationError, dump, load

from .canvas_model import CanvasModel
from .items import ElementItem
from .library_panel import LibraryPanel
from .property_panel import PropertyPanel
from .scene import SchematicScene
from .view import SchematicView


class SchematicEditor(QWidget):
    """The schematic canvas editor: library + canvas + property panel + toolbar."""

    def __init__(self, model: CanvasModel | None = None) -> None:
        super().__init__()
        self.scene = SchematicScene(model)
        self.view = SchematicView(self.scene)
        self.library = LibraryPanel()
        self.properties = PropertyPanel(self.scene.model)

        self.scene.selection_changed_element.connect(self._on_selection_changed)

        splitter = QSplitter()
        splitter.addWidget(self.library)
        splitter.addWidget(self.view)
        splitter.addWidget(self.properties)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        toolbar = QHBoxLayout()
        zoom_in_btn = QPushButton("Zoom In")
        zoom_out_btn = QPushButton("Zoom Out")
        zoom_reset_btn = QPushButton("Reset Zoom")
        grid_btn = QPushButton("Toggle Grid")
        load_btn = QPushButton("Load Netlist…")
        save_btn = QPushButton("Save Netlist…")
        validate_btn = QPushButton("Validate")
        zoom_in_btn.clicked.connect(self.view.zoom_in)
        zoom_out_btn.clicked.connect(self.view.zoom_out)
        zoom_reset_btn.clicked.connect(self.view.zoom_reset)
        grid_btn.clicked.connect(lambda: self.view.set_grid_visible(not self.view._grid_visible))
        load_btn.clicked.connect(self.prompt_load)
        save_btn.clicked.connect(self.prompt_save)
        validate_btn.clicked.connect(self.prompt_validate)
        for btn in (
            zoom_in_btn,
            zoom_out_btn,
            zoom_reset_btn,
            grid_btn,
            load_btn,
            save_btn,
            validate_btn,
        ):
            toolbar.addWidget(btn)
        toolbar.addStretch(1)

        outer = QVBoxLayout(self)
        outer.addLayout(toolbar)
        outer.addWidget(splitter)

    # -- selection --------------------------------------------------------------

    def _on_selection_changed(self, element_item: ElementItem | None) -> None:
        if element_item is None:
            self.properties.clear()
        else:
            self.properties.show_element(element_item.element_id)

    # -- load / save / validate ---------------------------------------------

    def load_netlist_file(self, path: str) -> None:
        """Load the netlist at ``path`` onto the canvas.

        Raises:
            core.netlist.NetlistError: if the file is malformed (surfaced to
                the user as a dialog by :meth:`prompt_load`).
        """
        netlist = load(path)
        self.scene.load_netlist(netlist)
        self.properties.model = self.scene.model
        self.properties.clear()

    def save_netlist_file(self, path: str, *, validate: bool = True) -> None:
        """Write the current canvas state to ``path`` as netlist JSON.

        Args:
            path: Destination file path.
            validate: If ``True`` (default), run ``core.netlist`` validation
                before writing and raise on failure -- callers that want to
                save a work-in-progress (invalid) circuit should pass
                ``validate=False``.

        Raises:
            core.netlist.ValidationError: if ``validate`` is ``True`` and the
                netlist implied by the canvas is invalid.
        """
        netlist = self.scene.model.to_netlist()
        dump(netlist, path, validate=validate)

    def prompt_load(self) -> None:
        """Open a file dialog and load the chosen netlist JSON file."""
        path, _ = QFileDialog.getOpenFileName(self, "Load Netlist", "", "Netlist JSON (*.json)")
        if not path:
            return
        try:
            self.load_netlist_file(path)
        except NetlistError as exc:
            _show_netlist_error(self, "Failed to load netlist", exc)

    def prompt_save(self) -> None:
        """Open a file dialog and save the canvas as netlist JSON.

        Saves without validation first if the netlist is invalid, after
        warning the user (a schematic in progress is often incomplete).
        """
        path, _ = QFileDialog.getSaveFileName(self, "Save Netlist", "", "Netlist JSON (*.json)")
        if not path:
            return
        errors = self.scene.model.collect_errors()
        if errors:
            joined = "\n".join(f"- {e}" for e in errors)
            choice = QMessageBox.warning(
                self,
                "Netlist has validation errors",
                f"The current circuit does not validate:\n\n{joined}\n\n"
                "Save anyway (unvalidated)?",
                QMessageBox.Save | QMessageBox.Cancel,
            )
            if choice != QMessageBox.Save:
                return
            self.save_netlist_file(path, validate=False)
        else:
            self.save_netlist_file(path, validate=True)

    def prompt_validate(self) -> None:
        """Run validation on the current canvas and show the results."""
        errors = self.scene.model.collect_errors()
        if not errors:
            QMessageBox.information(self, "Validation", "Netlist is valid.")
        else:
            joined = "\n".join(f"- {e}" for e in errors)
            QMessageBox.warning(self, "Validation errors", joined)


def _show_netlist_error(parent: QWidget, title: str, exc: NetlistError) -> None:
    if isinstance(exc, ValidationError):
        joined = "\n".join(f"- {e}" for e in exc.errors)
    else:
        joined = str(exc)
    QMessageBox.critical(parent, title, joined)
