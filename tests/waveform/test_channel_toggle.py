"""Tests for gui.waveform.channel_toggle.ChannelToggleList."""
from __future__ import annotations

from PySide6.QtCore import Qt

from gui.waveform.channel_toggle import ChannelToggleList


class TestChannelToggleList:
    def test_add_channel_defaults_to_checked(self, qapp):
        widget = ChannelToggleList(on_toggle=lambda name, checked: None)
        widget.add_channel("Magnitude (dB)")
        item = widget.item(0)
        assert item.text() == "Magnitude (dB)"
        assert item.checkState() == Qt.CheckState.Checked

    def test_add_channel_unchecked(self, qapp):
        widget = ChannelToggleList(on_toggle=lambda name, checked: None)
        widget.add_channel("Phase (deg)", checked=False)
        assert widget.item(0).checkState() == Qt.CheckState.Unchecked

    def test_unchecking_calls_callback_with_false(self, qapp):
        calls = []
        widget = ChannelToggleList(on_toggle=lambda name, checked: calls.append((name, checked)))
        widget.add_channel("n=0", checked=True)
        widget.item(0).setCheckState(Qt.CheckState.Unchecked)
        assert calls == [("n=0", False)]

    def test_clear_channels_does_not_fire_callback(self, qapp):
        calls = []
        widget = ChannelToggleList(on_toggle=lambda name, checked: calls.append((name, checked)))
        widget.add_channel("n=0")
        widget.add_channel("n=1")
        calls.clear()
        widget.clear_channels()
        assert widget.count() == 0
        assert calls == []
