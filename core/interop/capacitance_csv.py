"""Read an externally-computed Maxwell capacitance matrix from CSV.

This is a pure file-I/O + validation layer for interoperability with external
electrostatic field solvers (Ansys Q3D, palace, etc.). Those tools export the
capacitance matrix of a multi-node layout; JJQubit consumes that matrix as an
*input* (see the project scope note: we do not solve 3D fields ourselves).

No physics is performed here -- deriving Ec/g from the matrix lives in
``core/solvers/quantum/multiqubit.py`` and must not be duplicated. This module
only parses the file, validates its shape, and hands back a typed container.

All capacitance values are in femtofarads (fF). No Qt (core-wide rule).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

import numpy as np

__all__ = ["CapacitanceMatrix", "read_capacitance_csv"]

# Default absolute+relative tolerance (in fF) for the symmetry check. A Maxwell
# capacitance matrix is symmetric by construction; small asymmetries can appear
# from finite-precision export, so we allow a modest tolerance rather than
# demanding bit-exact equality.
_DEFAULT_SYMMETRY_ATOL_FF = 1e-6
_DEFAULT_SYMMETRY_RTOL = 1e-6


@dataclass(frozen=True)
class CapacitanceMatrix:
    """A validated, symmetric NxN Maxwell capacitance matrix.

    Attributes:
        node_names: Names of the N nodes, in row/column order. When the source
            CSV carries no header, synthetic names ``("node0", "node1", ...)``
            are generated.
        matrix_fF: The NxN capacitance matrix in femtofarads (fF). Guaranteed
            square and symmetric within tolerance at construction time.
    """

    node_names: tuple[str, ...]
    matrix_fF: np.ndarray


def _is_all_text(cells: list[str]) -> bool:
    """Return True if every non-empty cell is non-numeric (a label/header row).

    Empty cells (e.g. the leading corner of a labelled matrix) are ignored. A
    row with a mix of text and numbers is a *data* row with a leading label,
    not a header, so this returns False for it.
    """
    saw_text = False
    for cell in cells:
        token = cell.strip()
        if token == "":
            continue
        try:
            float(token)
        except ValueError:
            saw_text = True
        else:
            return False  # a numeric cell means this is not an all-text row
    return saw_text


def _parse_float(value: str, *, row: int, col: int) -> float:
    """Parse a single matrix cell to float, with a located error message."""
    token = value.strip()
    if token == "":
        raise ValueError(
            f"Empty capacitance cell at row {row}, column {col}; "
            "expected a numeric value in fF."
        )
    try:
        return float(token)
    except ValueError as exc:
        raise ValueError(
            f"Non-numeric capacitance cell {value!r} at row {row}, "
            f"column {col}; expected a number in fF."
        ) from exc


def read_capacitance_csv(
    path: str,
    *,
    symmetry_atol_fF: float = _DEFAULT_SYMMETRY_ATOL_FF,
    symmetry_rtol: float = _DEFAULT_SYMMETRY_RTOL,
) -> CapacitanceMatrix:
    """Read a symmetric NxN Maxwell capacitance matrix (in fF) from a CSV file.

    The CSV may optionally carry a header row and/or a leading label column of
    node names. Layouts supported:

    * Plain NxN grid of numbers (no labels). Node names are auto-generated.
    * Header row of N node names, followed by N rows of N numbers.
    * Header row of node names *and* a matching leading label column, i.e. an
      ``(N+1) x (N+1)`` grid whose top-left corner cell is ignored.

    Args:
        path: Filesystem path to the CSV file.
        symmetry_atol_fF: Absolute tolerance (fF) for the symmetry check.
        symmetry_rtol: Relative tolerance for the symmetry check.

    Returns:
        A frozen :class:`CapacitanceMatrix` with node names and the validated
        matrix in femtofarads (fF).

    Raises:
        ValueError: If the file is empty, rows are ragged (unequal lengths),
            the numeric block is not square, a cell is non-numeric, or the
            matrix is not symmetric within tolerance.
    """
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    # Drop fully-blank rows (trailing newlines, blank separators).
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError(f"Capacitance CSV {path!r} is empty.")

    has_header = _is_all_text(rows[0])
    node_names: tuple[str, ...] | None = None
    has_label_col = False

    if has_header:
        header = [cell.strip() for cell in rows[0]]
        data_rows = rows[1:]
        if not data_rows:
            raise ValueError(f"Capacitance CSV {path!r} has a header but no data rows.")
        # A leading empty corner cell signals a label column is present too.
        has_label_col = header[0] == ""
        node_names = tuple(header[1:] if has_label_col else header)
    else:
        data_rows = rows

    # Enforce rectangular data before slicing off any label column.
    width = len(data_rows[0])
    for i, row in enumerate(data_rows):
        if len(row) != width:
            raise ValueError(
                f"Ragged capacitance CSV {path!r}: data row {i} has "
                f"{len(row)} cells but row 0 has {width}."
            )

    if not has_header and _is_all_text([row[0] for row in data_rows]):
        # No header row, but a leading textual label column is present.
        has_label_col = True

    label_col_names: list[str] = []
    numeric_rows: list[list[str]] = []
    for row in data_rows:
        if has_label_col:
            label_col_names.append(row[0].strip())
            numeric_rows.append(row[1:])
        else:
            numeric_rows.append(row)

    n_rows = len(numeric_rows)
    n_cols = len(numeric_rows[0]) if numeric_rows else 0
    if n_rows != n_cols:
        raise ValueError(
            f"Capacitance matrix in {path!r} is not square: "
            f"{n_rows} rows x {n_cols} columns."
        )
    if n_rows == 0:
        raise ValueError(f"Capacitance CSV {path!r} contains no numeric data.")

    matrix = np.empty((n_rows, n_cols), dtype=float)
    for i, row in enumerate(numeric_rows):
        for j, cell in enumerate(row):
            matrix[i, j] = _parse_float(cell, row=i, col=j)

    if not np.allclose(matrix, matrix.T, atol=symmetry_atol_fF, rtol=symmetry_rtol):
        max_asym = float(np.max(np.abs(matrix - matrix.T)))
        raise ValueError(
            f"Capacitance matrix in {path!r} is not symmetric within "
            f"tolerance (max |C - C^T| = {max_asym:g} fF)."
        )

    if node_names is None:
        if has_label_col and label_col_names:
            node_names = tuple(label_col_names)
        else:
            node_names = tuple(f"node{i}" for i in range(n_rows))

    if len(node_names) != n_rows:
        raise ValueError(
            f"Capacitance CSV {path!r} has {len(node_names)} node name(s) "
            f"but a {n_rows}x{n_cols} matrix."
        )

    return CapacitanceMatrix(node_names=node_names, matrix_fF=matrix)
