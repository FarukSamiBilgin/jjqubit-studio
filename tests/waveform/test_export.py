"""Tests for gui.waveform.export: CSV/PNG writers.

These are plain-Python/NumPy tests -- export.py has no Qt dependency, so no
``qapp`` fixture or offscreen platform is needed here.
"""
from __future__ import annotations

import csv

import matplotlib.pyplot as plt
import numpy as np
import pytest

from gui.waveform.export import export_series_csv, save_figure_png


class TestExportSeriesCsv:
    def test_writes_header_and_rows(self, tmp_path):
        path = tmp_path / "out.csv"
        x = np.array([1.0, 2.0, 3.0])
        export_series_csv(path, "frequency_GHz", x, {"magnitude_dB": np.array([-1.0, -2.0, -3.0])})

        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == ["frequency_GHz", "magnitude_dB"]
        assert rows[1] == ["1.0", "-1.0"]
        assert rows[3] == ["3.0", "-3.0"]

    def test_multiple_series(self, tmp_path):
        path = tmp_path / "out.csv"
        x = np.arange(4)
        export_series_csv(
            path,
            "level_index",
            x,
            {"energy_GHz": np.array([0.0, 5.0, 10.0, 15.0]), "extra": np.array([1, 2, 3, 4])},
        )
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == ["level_index", "energy_GHz", "extra"]
        assert len(rows) == 5  # header + 4 data rows

    def test_mismatched_length_raises(self, tmp_path):
        path = tmp_path / "out.csv"
        with pytest.raises(ValueError):
            export_series_csv(path, "x", np.arange(3), {"y": np.arange(2)})


class TestSaveFigurePng:
    def test_writes_png_file(self, tmp_path):
        path = tmp_path / "out.png"
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [0, 1, 4])
        save_figure_png(fig, path)
        assert path.exists()
        assert path.stat().st_size > 0
        # A PNG file starts with this fixed 8-byte signature.
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
