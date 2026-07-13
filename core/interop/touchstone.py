"""Read a 2-port Touchstone (.s2p) S-parameter file.

Touchstone is the de-facto interchange format for scattering-parameter data
exported by vector network analyzers and EM solvers, including the readout
characterization of superconducting resonators and filters. This module parses
a 2-port file into a typed container so JJQubit can consume externally-measured
S-parameters without depending on any RF library.

This is pure file I/O + validation: no physics, no renormalization, no port
de-embedding. No Qt (core-wide rule).

Reference: the Touchstone 1.x option line has the form ``# GHz S RI R 50``:
frequency unit, parameter type (S), data format (RI/MA/DB), and the reference
impedance following ``R``. Comment lines start with ``!``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["Touchstone2Port", "read_touchstone_s2p"]

# Frequency-unit multipliers to convert the file's unit into hertz (Hz).
_FREQ_UNIT_HZ: dict[str, float] = {
    "HZ": 1.0,
    "KHZ": 1e3,
    "MHZ": 1e6,
    "GHZ": 1e9,
}

# Supported complex data formats.
_FORMATS = frozenset({"RI", "MA", "DB"})

# Number of scalar data columns after the frequency column for a 2-port file:
# four S-parameters, each two scalars (S11, S21, S12, S22).
_N_PAIRS = 4
_N_DATA_COLS = 1 + 2 * _N_PAIRS


@dataclass(frozen=True)
class Touchstone2Port:
    """Parsed 2-port Touchstone data.

    Attributes:
        frequencies_hz: 1-D array of length ``n`` with frequencies in hertz (Hz).
        s_params: Complex array of shape ``(n, 2, 2)``. ``s_params[k]`` is the
            2x2 scattering matrix at frequency ``frequencies_hz[k]``, indexed
            ``[out_port, in_port]`` (0-based), i.e. ``[0, 0]`` is S11,
            ``[1, 0]`` is S21, ``[0, 1]`` is S12, ``[1, 1]`` is S22.
        z0_ohm: Reference (port) impedance in ohms.
    """

    frequencies_hz: np.ndarray
    s_params: np.ndarray
    z0_ohm: float


def _strip_comment(line: str) -> str:
    """Remove an inline ``!`` comment and surrounding whitespace from a line."""
    bang = line.find("!")
    if bang != -1:
        line = line[:bang]
    return line.strip()


def _parse_option_line(line: str) -> tuple[float, str, float]:
    """Parse the ``#`` option line into (freq_multiplier_hz, format, z0_ohm).

    Defaults follow the Touchstone spec: ``MHz S MA R 50`` when tokens are
    omitted. Only S (scattering) parameters are supported.
    """
    tokens = line[1:].split()  # drop the leading '#'
    freq_mult = _FREQ_UNIT_HZ["MHZ"]
    data_format = "MA"
    z0_ohm = 50.0

    i = 0
    while i < len(tokens):
        tok = tokens[i].upper()
        if tok in _FREQ_UNIT_HZ:
            freq_mult = _FREQ_UNIT_HZ[tok]
        elif tok in _FORMATS:
            data_format = tok
        elif tok == "S":
            pass  # scattering parameters: the only supported type
        elif tok in {"Y", "Z", "H", "G"}:
            raise ValueError(
                f"Unsupported Touchstone parameter type {tok!r}; only "
                "S-parameters are supported."
            )
        elif tok == "R":
            if i + 1 >= len(tokens):
                raise ValueError(
                    "Touchstone option line ends after 'R' with no reference "
                    "impedance value."
                )
            try:
                z0_ohm = float(tokens[i + 1])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid reference impedance {tokens[i + 1]!r} in "
                    "Touchstone option line."
                ) from exc
            i += 1
        else:
            raise ValueError(
                f"Unrecognized token {tokens[i]!r} in Touchstone option line."
            )
        i += 1

    return freq_mult, data_format, z0_ohm


def _to_complex(a: float, b: float, data_format: str) -> complex:
    """Convert a scalar pair (a, b) in the given format to a complex value.

    RI: (real, imag). MA: (magnitude, angle in degrees). DB: (20*log10|.| in
    dB, angle in degrees).
    """
    if data_format == "RI":
        return complex(a, b)
    if data_format == "MA":
        angle_rad = np.deg2rad(b)
        return complex(a * np.cos(angle_rad), a * np.sin(angle_rad))
    # DB
    magnitude = 10.0 ** (a / 20.0)
    angle_rad = np.deg2rad(b)
    return complex(magnitude * np.cos(angle_rad), magnitude * np.sin(angle_rad))


def read_touchstone_s2p(path: str) -> Touchstone2Port:
    """Read a 2-port Touchstone ``.s2p`` file into a :class:`Touchstone2Port`.

    Parses the ``#`` option line (frequency unit, S type, RI/MA/DB format, and
    ``R`` reference impedance), skips ``!`` comment lines, and reads the data
    block. Each data record is::

        freq  S11a S11b  S21a S21b  S12a S12b  S22a S22b

    where ``(a, b)`` is interpreted per the declared format. Frequencies are
    returned in hertz (Hz) regardless of the file's frequency unit.

    Args:
        path: Filesystem path to the ``.s2p`` file.

    Returns:
        A frozen :class:`Touchstone2Port` with frequencies in Hz, a complex
        ``(n, 2, 2)`` S-parameter array, and the reference impedance in ohms.

    Raises:
        ValueError: If the option line is missing or malformed, a data line has
            the wrong number of columns, a value is non-numeric, or the file
            contains no data records.
    """
    with open(path, encoding="utf-8-sig") as handle:
        raw_lines = handle.readlines()

    freq_mult: float | None = None
    data_format = "MA"
    z0_ohm = 50.0
    tokens: list[str] = []

    for raw in raw_lines:
        content = _strip_comment(raw)
        if content == "":
            continue
        if content.startswith("#"):
            if freq_mult is not None:
                # Touchstone permits only one option line.
                raise ValueError(
                    f"Multiple option lines found in {path!r}; a Touchstone "
                    "file must have exactly one."
                )
            freq_mult, data_format, z0_ohm = _parse_option_line(content)
            continue
        tokens.extend(content.split())

    if freq_mult is None:
        raise ValueError(f"Touchstone file {path!r} has no '#' option line.")
    if not tokens:
        raise ValueError(
            f"Touchstone file {path!r} contains no S-parameter data records."
        )
    if len(tokens) % _N_DATA_COLS != 0:
        raise ValueError(
            f"Touchstone file {path!r} has {len(tokens)} data values, which is "
            f"not a whole number of {_N_DATA_COLS}-column 2-port records."
        )

    try:
        values = np.asarray([float(tok) for tok in tokens], dtype=float)
    except ValueError as exc:
        raise ValueError(
            f"Non-numeric value in Touchstone data of {path!r}: {exc}"
        ) from exc

    records = values.reshape(-1, _N_DATA_COLS)
    n = records.shape[0]

    frequencies_hz = records[:, 0] * freq_mult
    s_params = np.empty((n, 2, 2), dtype=complex)
    # Column order within a 2-port record is S11, S21, S12, S22.
    order = [(0, 0), (1, 0), (0, 1), (1, 1)]
    for k in range(n):
        for pair_idx, (out_port, in_port) in enumerate(order):
            a = records[k, 1 + 2 * pair_idx]
            b = records[k, 2 + 2 * pair_idx]
            s_params[k, out_port, in_port] = _to_complex(a, b, data_format)

    return Touchstone2Port(
        frequencies_hz=frequencies_hz,
        s_params=s_params,
        z0_ohm=z0_ohm,
    )
