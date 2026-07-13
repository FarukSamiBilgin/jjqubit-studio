"""Tests for the capacitance-matrix CSV importer."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from core.interop import CapacitanceMatrix, read_capacitance_csv


def _write(tmp_path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_plain_matrix_no_header(tmp_path):
    """A bare NxN numeric grid parses with auto-generated node names."""
    path = _write(
        tmp_path,
        "plain.csv",
        "70.0,-5.0,-2.0\n-5.0,68.0,-4.0\n-2.0,-4.0,66.0\n",
    )
    result = read_capacitance_csv(path)

    assert isinstance(result, CapacitanceMatrix)
    assert result.node_names == ("node0", "node1", "node2")
    assert result.matrix_fF.shape == (3, 3)
    assert result.matrix_fF[0, 1] == -5.0
    # Symmetric within tolerance.
    np.testing.assert_allclose(result.matrix_fF, result.matrix_fF.T)


def test_header_row_only(tmp_path):
    """A header row of node names is captured; values in fF are read."""
    path = _write(
        tmp_path,
        "header.csv",
        "Q0,Q1\n80.0,-3.0\n-3.0,79.0\n",
    )
    result = read_capacitance_csv(path)
    assert result.node_names == ("Q0", "Q1")
    np.testing.assert_allclose(result.matrix_fF, np.array([[80.0, -3.0], [-3.0, 79.0]]))


def test_header_row_and_label_column(tmp_path):
    """An (N+1)x(N+1) labelled grid ignores the corner and reads labels once."""
    path = _write(
        tmp_path,
        "labelled.csv",
        ",Qa,Qb\nQa,90.0,-7.0\nQb,-7.0,88.0\n",
    )
    result = read_capacitance_csv(path)
    assert result.node_names == ("Qa", "Qb")
    assert result.matrix_fF[0, 0] == 90.0
    assert result.matrix_fF[1, 0] == -7.0


def test_label_column_without_header(tmp_path):
    """A leading textual label column with no header row is handled."""
    path = _write(
        tmp_path,
        "labelcol.csv",
        "A,50.0,-1.0\nB,-1.0,52.0\n",
    )
    result = read_capacitance_csv(path)
    assert result.node_names == ("A", "B")
    np.testing.assert_allclose(result.matrix_fF, np.array([[50.0, -1.0], [-1.0, 52.0]]))


def test_utf8_bom_and_blank_lines(tmp_path):
    """A BOM prefix and interspersed blank lines do not break parsing."""
    path = tmp_path / "bom.csv"
    path.write_text("﻿10.0,-2.0\n\n-2.0,11.0\n\n", encoding="utf-8")
    result = read_capacitance_csv(str(path))
    assert result.matrix_fF.shape == (2, 2)
    assert result.matrix_fF[0, 0] == 10.0


def test_symmetry_within_tolerance_passes(tmp_path):
    """Tiny asymmetry from export precision is accepted."""
    path = _write(
        tmp_path,
        "near_sym.csv",
        "100.0,-5.0000001\n-5.0,101.0\n",
    )
    result = read_capacitance_csv(path, symmetry_atol_fF=1e-3)
    assert result.matrix_fF.shape == (2, 2)


def test_roundtrip_from_numpy(tmp_path):
    """Writing a symmetric matrix out and reading it back reproduces it."""
    rng = np.random.default_rng(0)
    a = rng.normal(size=(4, 4))
    sym = a + a.T  # guaranteed symmetric
    names = ["n0", "n1", "n2", "n3"]

    lines = [",".join(names)]
    for row in sym:
        lines.append(",".join(f"{v:.10g}" for v in row))
    path = _write(tmp_path, "roundtrip.csv", "\n".join(lines) + "\n")

    result = read_capacitance_csv(path)
    assert result.node_names == tuple(names)
    np.testing.assert_allclose(result.matrix_fF, sym, atol=1e-8)


def test_non_square_raises(tmp_path):
    """A non-square numeric block is rejected."""
    path = _write(tmp_path, "nonsquare.csv", "1.0,2.0,3.0\n4.0,5.0,6.0\n")
    with pytest.raises(ValueError, match="not square"):
        read_capacitance_csv(path)


def test_ragged_rows_raise(tmp_path):
    """Rows of unequal length are rejected as ragged."""
    path = _write(tmp_path, "ragged.csv", "1.0,2.0\n3.0,4.0,5.0\n")
    with pytest.raises(ValueError, match="[Rr]agged"):
        read_capacitance_csv(path)


def test_non_symmetric_raises(tmp_path):
    """A clearly asymmetric matrix is rejected."""
    path = _write(tmp_path, "asym.csv", "10.0,1.0\n9.0,10.0\n")
    with pytest.raises(ValueError, match="not symmetric"):
        read_capacitance_csv(path)


def test_non_numeric_cell_raises(tmp_path):
    """A non-numeric data cell reports its location."""
    path = _write(tmp_path, "bad.csv", "10.0,x\n1.0,10.0\n")
    with pytest.raises(ValueError, match="Non-numeric"):
        read_capacitance_csv(path)


def test_empty_file_raises(tmp_path):
    """An empty file is rejected."""
    path = _write(tmp_path, "empty.csv", "\n\n")
    with pytest.raises(ValueError, match="empty"):
        read_capacitance_csv(path)


def test_header_but_no_data_raises(tmp_path):
    """A header with no following data rows is rejected."""
    path = _write(tmp_path, "headeronly.csv", "Q0,Q1\n")
    with pytest.raises(ValueError, match="no data"):
        read_capacitance_csv(path)


def test_result_is_frozen(tmp_path):
    """The returned dataclass is immutable."""
    path = _write(tmp_path, "f.csv", "1.0,0.0\n0.0,1.0\n")
    result = read_capacitance_csv(path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.node_names = ("x",)  # type: ignore[misc]
