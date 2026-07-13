"""Builds a synthetic classical-solver-shaped HDF5 file for testing.

Writes the FINALIZED classical-result schema that
``gui/waveform/hdf5_reader.load_classical_result`` reads (see
``core/solvers/classical/hdf5_io.py`` for the authoritative layout): an
optional ``/readout`` group (S21 sweep) and an optional ``/rcsj`` group
(I-V curve + phase dynamics). This fixture writes BOTH so every classical
sub-view (S21 / I-V / phase) is exercised.

The numbers are fabricated (a textbook single-pole Lorentzian for S21, a
smooth ramp for the I-V/phase traces) -- a real file from solver-classical
comes from an actual RCSJ / transmission-line simulation. This stays a
test-only fixture generator in ``tests/waveform/`` (this teammate's owned
test scope), not part of the shipped reader.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
from gui.waveform.hdf5_reader import CLASSICAL_FORMAT


def write_synthetic_classical_hdf5(
    path: str | Path,
    *,
    netlist_name: str = "Synthetic S21 sweep",
    f0_ghz: float = 7.2,
    q_factor: float = 8000.0,
    n_points: int = 501,
    span_ghz: float = 0.05,
    n_time: int = 400,
) -> None:
    """Write a synthetic classical result (S21 readout + RCSJ analysis) to ``path``.

    Args:
        path: Output file path.
        netlist_name: Stored as the root ``netlist_name`` attr.
        f0_ghz: Resonance center frequency, in GHz.
        q_factor: Resonator quality factor (sets the linewidth kappa = f0/Q).
        n_points: Number of frequency points in the S21 sweep.
        span_ghz: Half-width of the frequency sweep around ``f0_ghz``, in GHz.
        n_time: Number of samples in the phase-dynamics time trace.
    """
    # --- /readout : textbook single-pole (notch) S21 -----------------------
    kappa_ghz = f0_ghz / q_factor
    frequency_ghz = np.linspace(f0_ghz - span_ghz, f0_ghz + span_ghz, n_points)
    detuning = frequency_ghz - f0_ghz
    # 0.95 coupling factor keeps |S21| > 0 exactly at resonance (critical
    # coupling would hit zero and blow up log10) while showing a clear notch.
    s21 = 1.0 - 0.95 * (1j * kappa_ghz / 2.0) / (detuning + 1j * kappa_ghz / 2.0)
    s21_mag_db = 20.0 * np.log10(np.abs(s21))
    s21_phase_deg = np.degrees(np.angle(s21))

    # --- /rcsj : a smooth I-V ramp + a settled phase trace -----------------
    ic_na = 20.0
    rn_ohm = 8000.0
    bias_up_na = np.linspace(0.0, 4.0 * ic_na, 25)
    # Above Ic the running-state law is V ~ I*Rn (underdamped); below, zero.
    # nA * ohm = nV; /1000 -> uV.
    volt_up_uv = np.where(bias_up_na > ic_na, bias_up_na * rn_ohm / 1000.0, 0.0)
    bias_down_na = bias_up_na[::-1]
    # Down-sweep retraps at a much lower current (hysteresis) ~ 0.1*Ic.
    volt_down_uv = np.where(
        bias_down_na > 0.1 * ic_na, bias_down_na * rn_ohm / 1000.0, 0.0
    )

    time_ns = np.linspace(0.0, 50.0, n_time)
    phase_rad = 2.0 * np.pi * 0.9 * time_ns  # phase running (voltage state)
    voltage_uv = np.full_like(time_ns, 25.0 * rn_ohm / 1000.0)

    with h5py.File(path, "w") as f:
        f.attrs["format"] = CLASSICAL_FORMAT
        f.attrs["version"] = "1.0"
        f.attrs["generated_by"] = "tests.waveform.classical_synthetic"
        f.attrs["netlist_name"] = netlist_name

        readout = f.create_group("readout")
        for name, data, unit in (
            ("frequency_GHz", frequency_ghz, "GHz"),
            ("s21_mag_db", s21_mag_db, "dB"),
            ("s21_phase_deg", s21_phase_deg, "deg"),
            ("s21_real", np.real(s21), ""),
            ("s21_imag", np.imag(s21), ""),
        ):
            ds = readout.create_dataset(name, data=data)
            ds.attrs["unit"] = unit
        readout.attrs["f0_GHz"] = f0_ghz
        readout.attrs["Q_internal"] = q_factor
        readout.attrs["kappa_total_MHz"] = kappa_ghz * 1000.0
        readout.attrs["resonator_id"] = "RES1"
        readout.attrs["active_node"] = "r"

        rcsj = f.create_group("rcsj")
        rcsj.attrs["Ic_nA"] = ic_na
        rcsj.attrs["Rn_total_ohm"] = rn_ohm
        rcsj.attrs["C_total_fF"] = 53.0
        rcsj.attrs["bias_current_nA"] = 25.0
        rcsj.attrs["plasma_frequency_GHz"] = 3.0
        rcsj.attrs["quality_factor"] = 14.4
        rcsj.attrs["junction_id"] = "J1"

        iv = rcsj.create_group("iv_curve")
        for name, data, unit in (
            ("bias_current_up_nA", bias_up_na, "nA"),
            ("voltage_up_uV", volt_up_uv, "uV"),
            ("bias_current_down_nA", bias_down_na, "nA"),
            ("voltage_down_uV", volt_down_uv, "uV"),
        ):
            ds = iv.create_dataset(name, data=data)
            ds.attrs["unit"] = unit

        dyn = rcsj.create_group("phase_dynamics")
        for name, data, unit in (
            ("time_ns", time_ns, "ns"),
            ("phase_rad", phase_rad, "rad"),
            ("voltage_uV", voltage_uv, "uV"),
        ):
            ds = dyn.create_dataset(name, data=data)
            ds.attrs["unit"] = unit
        dyn.attrs["dc_voltage_uV"] = float(voltage_uv[0])
        dyn.attrs["bias_current_nA"] = 25.0
