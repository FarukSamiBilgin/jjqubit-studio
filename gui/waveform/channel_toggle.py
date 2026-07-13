"""Reusable checkable list widget for per-channel show/hide toggles.

Shared by the energy-level view (toggling individual levels) and the S21
view (toggling magnitude/phase traces) -- the list of channel names differs
per-view, but "a checkable list that calls back on toggle" does not.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem


class ChannelToggleList(QListWidget):
    """A ``QListWidget`` of checkable channel names.

    Args:
        on_toggle: Called with ``(channel_name, is_checked)`` whenever a
            checkbox changes state.
    """

    def __init__(
        self, on_toggle: Callable[[str, bool], None], parent: object | None = None
    ) -> None:
        super().__init__(parent)
        self._on_toggle = on_toggle
        self.itemChanged.connect(self._handle_item_changed)

    def add_channel(self, name: str, *, checked: bool = True) -> None:
        """Append a new checkable entry named ``name``."""
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self.addItem(item)

    def clear_channels(self) -> None:
        """Remove every entry (blocking signals so this doesn't fire ``on_toggle``)."""
        self.blockSignals(True)
        self.clear()
        self.blockSignals(False)

    def _handle_item_changed(self, item: QListWidgetItem) -> None:
        self._on_toggle(item.text(), item.checkState() == Qt.CheckState.Checked)
