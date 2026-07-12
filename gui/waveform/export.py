"""CSV/PNG export helpers shared by the waveform views.

Deliberately Qt-free and schema-independent: callers hand over plain NumPy
arrays and dicts (not pyqtgraph items), so this module has no dependency on
a live plot widget and is trivially testable headlessly -- no ``QApplication``
or offscreen platform plugin needed to exercise it.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # export must work headlessly; no interactive backend needed

import matplotlib.pyplot as plt
import numpy as np


def export_series_csv(
    path: str | Path,
    x_label: str,
    x: np.ndarray,
    series: dict[str, np.ndarray],
) -> None:
    """Write ``x`` plus one or more named y-series to a CSV file.

    Args:
        path: Output file path.
        x_label: Header name for the shared x column.
        x: Shape ``(n,)`` array shared by every series.
        series: Mapping of column name -> shape ``(n,)`` array; every array
            must have the same length as ``x``.

    Raises:
        ValueError: if any series array does not match ``x``'s length.
    """
    x = np.asarray(x)
    columns = {name: np.asarray(values) for name, values in series.items()}
    for name, values in columns.items():
        if len(values) != len(x):
            raise ValueError(
                f"series {name!r} has length {len(values)}, expected {len(x)} (matching x)"
            )

    out_path = Path(path)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([x_label, *columns.keys()])
        for row in zip(x, *columns.values()):
            writer.writerow(list(row))


def save_figure_png(fig: "plt.Figure", path: str | Path) -> None:
    """Save a matplotlib ``Figure`` to ``path`` as PNG, then close it.

    Closing the figure after saving avoids leaking matplotlib figures across
    repeated exports (each view builds a fresh figure per export call).
    """
    fig.savefig(Path(path), format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
