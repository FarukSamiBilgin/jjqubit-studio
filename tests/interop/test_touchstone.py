"""Tests for the 2-port Touchstone (.s2p) importer."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from core.interop import Touchstone2Port, read_touchstone_s2p


def _write(tmp_path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_ri_format(tmp_path):
    """RI (real/imag) values are read verbatim and freq converted to Hz."""
    text = (
        "! a comment\n"
        "# GHz S RI R 50\n"
        "5.0 0.1 0.2  0.9 0.0  0.9 0.0  0.1 -0.2\n"
        "6.0 0.15 0.25  0.85 0.1  0.85 0.1  0.15 -0.25\n"
    )
    path = _write(tmp_path, "ri.s2p", text)
    ts = read_touchstone_s2p(path)

    assert isinstance(ts, Touchstone2Port)
    assert ts.z0_ohm == 50.0
    assert ts.frequencies_hz.shape == (2,)
    np.testing.assert_allclose(ts.frequencies_hz, [5e9, 6e9])
    assert ts.s_params.shape == (2, 2, 2)
    # S11 at first freq.
    assert ts.s_params[0, 0, 0] == complex(0.1, 0.2)
    # S21 at first freq (row 1, col 0).
    assert ts.s_params[0, 1, 0] == complex(0.9, 0.0)
    # S12 at first freq (row 0, col 1).
    assert ts.s_params[0, 0, 1] == complex(0.9, 0.0)
    # S22 at first freq.
    assert ts.s_params[0, 1, 1] == complex(0.1, -0.2)


def test_ma_format(tmp_path):
    """MA (magnitude/angle-deg) is converted to the correct complex value."""
    text = "# MHz S MA R 50\n1000.0  0.5 90.0  1.0 0.0  1.0 0.0  0.5 -90.0\n"
    path = _write(tmp_path, "ma.s2p", text)
    ts = read_touchstone_s2p(path)

    np.testing.assert_allclose(ts.frequencies_hz, [1e9])
    # 0.5 at +90 deg -> 0 + 0.5j
    np.testing.assert_allclose(ts.s_params[0, 0, 0], 0.5j, atol=1e-12)
    # 1.0 at 0 deg -> 1 + 0j
    np.testing.assert_allclose(ts.s_params[0, 1, 0], 1.0 + 0j, atol=1e-12)
    # 0.5 at -90 deg -> 0 - 0.5j
    np.testing.assert_allclose(ts.s_params[0, 1, 1], -0.5j, atol=1e-12)


def test_db_format(tmp_path):
    """DB (dB/angle-deg) magnitude is 10**(dB/20)."""
    text = "# GHz S DB R 50\n7.5  -20.0 0.0  -3.0 45.0  -3.0 45.0  -20.0 180.0\n"
    path = _write(tmp_path, "db.s2p", text)
    ts = read_touchstone_s2p(path)

    # -20 dB at 0 deg -> magnitude 0.1, real.
    np.testing.assert_allclose(ts.s_params[0, 0, 0], 0.1 + 0j, atol=1e-9)
    # -3 dB at 45 deg.
    mag = 10.0 ** (-3.0 / 20.0)
    expected = mag * np.exp(1j * np.deg2rad(45.0))
    np.testing.assert_allclose(ts.s_params[0, 1, 0], expected, atol=1e-9)
    # -20 dB at 180 deg -> -0.1 + ~0j.
    np.testing.assert_allclose(ts.s_params[0, 1, 1], -0.1 + 0j, atol=1e-9)


def test_defaults_when_tokens_omitted(tmp_path):
    """Option line '# S' falls back to MHz / MA / R 50 defaults."""
    text = "# S\n1.0  1.0 0.0  0.0 0.0  0.0 0.0  1.0 0.0\n"
    path = _write(tmp_path, "defaults.s2p", text)
    ts = read_touchstone_s2p(path)
    assert ts.z0_ohm == 50.0
    np.testing.assert_allclose(ts.frequencies_hz, [1e6])  # MHz default


def test_custom_reference_impedance(tmp_path):
    """A non-50-ohm reference impedance is captured."""
    text = "# GHz S RI R 75\n5.0 0.0 0.0 1.0 0.0 1.0 0.0 0.0 0.0\n"
    path = _write(tmp_path, "z75.s2p", text)
    ts = read_touchstone_s2p(path)
    assert ts.z0_ohm == 75.0


def test_comments_and_blank_lines_skipped(tmp_path):
    """Full-line and inline '!' comments plus blank lines are ignored."""
    text = (
        "! header comment\n"
        "\n"
        "# GHz S RI R 50\n"
        "! another comment\n"
        "5.0 0.1 0.0  0.9 0.0  0.9 0.0  0.1 0.0   ! inline note\n"
    )
    path = _write(tmp_path, "comments.s2p", text)
    ts = read_touchstone_s2p(path)
    assert ts.frequencies_hz.shape == (1,)
    assert ts.s_params[0, 0, 0] == complex(0.1, 0.0)


def test_ri_roundtrip(tmp_path):
    """Emit RI data from arrays, read it back, recover the same S-matrix."""
    rng = np.random.default_rng(1)
    freqs = np.array([4e9, 4.5e9, 5e9])
    s = rng.normal(size=(3, 2, 2)) + 1j * rng.normal(size=(3, 2, 2))

    lines = ["# GHz S RI R 50"]
    order = [(0, 0), (1, 0), (0, 1), (1, 1)]
    for k, f in enumerate(freqs):
        parts = [f"{f / 1e9:.10g}"]
        for out_p, in_p in order:
            val = s[k, out_p, in_p]
            parts.append(f"{val.real:.10g}")
            parts.append(f"{val.imag:.10g}")
        lines.append(" ".join(parts))
    path = _write(tmp_path, "rt.s2p", "\n".join(lines) + "\n")

    ts = read_touchstone_s2p(path)
    np.testing.assert_allclose(ts.frequencies_hz, freqs)
    np.testing.assert_allclose(ts.s_params, s, atol=1e-9)


def test_multiline_record_reassembly(tmp_path):
    """Data values split across lines still group into 9-column records."""
    text = "# GHz S RI R 50\n5.0 0.1 0.2\n0.9 0.0 0.9 0.0\n0.1 -0.2\n"
    path = _write(tmp_path, "split.s2p", text)
    ts = read_touchstone_s2p(path)
    assert ts.frequencies_hz.shape == (1,)
    assert ts.s_params[0, 0, 0] == complex(0.1, 0.2)
    assert ts.s_params[0, 1, 1] == complex(0.1, -0.2)


def test_missing_option_line_raises(tmp_path):
    """A file with no '#' option line is rejected."""
    text = "5.0 0.1 0.0 0.9 0.0 0.9 0.0 0.1 0.0\n"
    path = _write(tmp_path, "noopt.s2p", text)
    with pytest.raises(ValueError, match="no '#' option line"):
        read_touchstone_s2p(path)


def test_wrong_column_count_raises(tmp_path):
    """A data block that is not a whole number of 9-col records is rejected."""
    text = "# GHz S RI R 50\n5.0 0.1 0.2 0.9 0.0\n"
    path = _write(tmp_path, "short.s2p", text)
    with pytest.raises(ValueError, match="whole number"):
        read_touchstone_s2p(path)


def test_non_numeric_value_raises(tmp_path):
    """A non-numeric data token is rejected."""
    text = "# GHz S RI R 50\n5.0 0.1 0.2 x 0.0 0.9 0.0 0.1 0.0\n"
    path = _write(tmp_path, "nan.s2p", text)
    with pytest.raises(ValueError, match="Non-numeric"):
        read_touchstone_s2p(path)


def test_no_data_records_raises(tmp_path):
    """An option line with no following data is rejected."""
    text = "# GHz S RI R 50\n! only comments\n"
    path = _write(tmp_path, "nodata.s2p", text)
    with pytest.raises(ValueError, match="no S-parameter data"):
        read_touchstone_s2p(path)


def test_unsupported_parameter_type_raises(tmp_path):
    """Y/Z/H/G parameter types are rejected (only S supported)."""
    text = "# GHz Y RI R 50\n5.0 0.1 0.2 0.9 0.0 0.9 0.0 0.1 0.0\n"
    path = _write(tmp_path, "yparam.s2p", text)
    with pytest.raises(ValueError, match="Unsupported"):
        read_touchstone_s2p(path)


def test_multiple_option_lines_raise(tmp_path):
    """Two option lines are rejected."""
    text = "# GHz S RI R 50\n# MHz S MA R 50\n5.0 0.1 0.2 0.9 0.0 0.9 0.0 0.1 0.0\n"
    path = _write(tmp_path, "twoopt.s2p", text)
    with pytest.raises(ValueError, match="Multiple option lines"):
        read_touchstone_s2p(path)


def test_result_is_frozen(tmp_path):
    """The returned dataclass is immutable."""
    text = "# GHz S RI R 50\n5.0 0.1 0.2 0.9 0.0 0.9 0.0 0.1 0.0\n"
    path = _write(tmp_path, "frozen.s2p", text)
    ts = read_touchstone_s2p(path)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ts.z0_ohm = 75.0  # type: ignore[misc]
