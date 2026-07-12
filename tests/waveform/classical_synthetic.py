"""Builds a synthetic classical-solver-shaped HDF5 file for testing.

solver-classical (Task #2) is being built in parallel and its real S21
HDF5 layout is not finalized yet, per Task #5's brief: "Build the S21 view
/ continuous-curve plotting against a synthetic HDF5 file you construct
yourself for now." This module is that synthetic-file builder -- it writes
the PROVISIONAL schema ``gui/waveform/hdf5_reader.load_classical_result``
reads (see that module's docstring), using a textbook single-pole
Lorentzian resonance for the S21 curve so the shape is physically
plausible even though the numbers are fabricated for the test.

Test-only: lives in ``tests/waveform/`` (this teammate's owned test scope),
not in ``gui/waveform/``, since it is not part of the shipped reader --
just a fixture generator.
"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from gui.waveform.hdf5_reader import CLASSICAL_FORMAT_PROVISIONAL


def write_synthetic_classical_hdf5(
    path: str | Path,
    *,
    netlist_name: str = "Synthetic S21 sweep",
    f0_ghz: float = 7.2,
    q_factor: float = 8000.0,
    n_points: int = 501,
    span_ghz: float = 0.05,
) -> None:
    """Write a synthetic single-pole S21 Lorentzian sweep to ``path``.

    Args:
        path: Output file path.
        netlist_name: Stored as the root ``netlist_name`` attr.
        f0_ghz: Resonance center frequency, in GHz.
        q_factor: Resonator quality factor (sets the linewidth kappa = f0/Q).
        n_points: Number of frequency points in the sweep.
        span_ghz: Half-width of the frequency sweep around ``f0_ghz``, in GHz.
    """
    kappa_ghz = f0_ghz / q_factor
    frequency_ghz = np.linspace(f0_ghz - span_ghz, f0_ghz + span_ghz, n_points)
    detuning = frequency_ghz - f0_ghz
    # Textbook (slightly under-coupled) notch-type resonator S21
    # (normalized): a real HDF5 from solver-classical would come from an
    # actual RCSJ/transmission-line simulation, not this closed-form
    # stand-in. The 0.95 coupling factor keeps |S21| > 0 exactly at
    # resonance (critical coupling would hit exactly zero there and blow up
    # log10), while still producing a clearly visible notch.
    s21 = 1.0 - 0.95 * (1j * kappa_ghz / 2.0) / (detuning + 1j * kappa_ghz / 2.0)
    magnitude_db = 20.0 * np.log10(np.abs(s21))
    phase_deg = np.degrees(np.angle(s21))

    with h5py.File(path, "w") as f:
        f.attrs["format"] = CLASSICAL_FORMAT_PROVISIONAL
        f.attrs["version"] = "0.0-provisional"
        f.attrs["generated_by"] = "tests.waveform.classical_synthetic"
        f.attrs["netlist_name"] = netlist_name

        s21_group = f.create_group("s21")
        freq_ds = s21_group.create_dataset("frequency_GHz", data=frequency_ghz)
        freq_ds.attrs["unit"] = "GHz"
        mag_ds = s21_group.create_dataset("magnitude_dB", data=magnitude_db)
        mag_ds.attrs["unit"] = "dB"
        phase_ds = s21_group.create_dataset("phase_deg", data=phase_deg)
        phase_ds.attrs["unit"] = "deg"
