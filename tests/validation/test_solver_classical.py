"""Comparison of solver-classical (RCSJ, Task #2) against the independent reference.

solver-classical has landed (core.solvers.classical), so these are LIVE
comparisons. They are driven off its CLI / HDF5 output and its stable public
``dc_voltage`` API -- NOT by solver-classical importing this suite's internal
reference module (that direction crosses scope and is explicitly not how the
cross-check is owned; validation owns it, from the outside).

The headline analytic limit (CLAUDE.md #3, "I < Ic => V = 0") is checked via the
CLI/HDF5 path on a constructed subcritical netlist. The running state and the
full V_dc(I) curve are cross-checked against two independent references:

  1. reference.rcsj_dc_voltage_volt -- an independent from-scratch RCSJ ODE
     integrator (same equation, separate implementation; supercurrent-branch
     initial condition phi0 = arcsin(I/Ic)).
  2. The underdamped running-state law V ~= I * R (the DC supercurrent
     <Ic sin phi> averages to zero once the phase runs), an analytic anchor
     that shares nothing with either ODE integration.

Reference junction (examples/rcsj_bias.json, inductor L1 excluded from the RCSJ
model by design -- see below): Ic = 20 nA, R_total = 8 kohm, C_total = 53 fF,
quality factor Q ~= 14.4 (underdamped/hysteretic).
"""
from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from core.netlist import Quantity, dump, load

from . import reference as ref

# solver-classical must be importable; skip (not error) if it regresses away.
classical = pytest.importorskip("core.solvers.classical")

_IC_A = 20e-9
_R_OHM = 8e3
_C_F = 53e-15
_V_SCALE = ref.PHI0 / 1e-9  # ~2.07 uV natural Josephson voltage scale


def _run_cli(netlist_path, out_path):
    """Run the solver-classical CLI as a subprocess; return the output path.

    Drives the solver exactly as an end user / app-core would, then reads the
    persisted result -- the CLI/HDF5 contract, not an internal call.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "core.solvers.classical", str(netlist_path), str(out_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}\n{proc.stdout}"
    return out_path


def test_classical_cli_subcritical_zero_voltage(examples_dir, tmp_path):
    """I < Ic => V_dc = 0, verified through the real CLI/HDF5 output path.

    We take the shipped RCSJ netlist and dial the bias current DOWN below Ic
    (25 nA -> 10 nA), write it out, run the CLI, and read dc_voltage_uV from the
    HDF5. The junction must sit on the zero-voltage supercurrent branch.
    """
    h5py = pytest.importorskip("h5py")
    netlist = load(str(examples_dir / "rcsj_bias.json"), validate=True)
    bias = netlist.element_by_id("Ib")
    assert bias is not None and bias.type == "current_source"
    bias.params["I"] = Quantity(10.0, "nA")  # 10 nA < Ic = 20 nA
    sub_path = tmp_path / "rcsj_subcritical.json"
    dump(netlist, str(sub_path))

    out = tmp_path / "sub.h5"
    _run_cli(sub_path, out)
    with h5py.File(out, "r") as f:
        assert f.attrs["format"] == "jjqubit-classical-result"
        v_dc_uv = float(f["rcsj/phase_dynamics"].attrs["dc_voltage_uV"])
        bias_na = float(f["rcsj/phase_dynamics"].attrs["bias_current_nA"])
    assert np.isclose(bias_na, 10.0, rtol=1e-9)
    # Zero to numerical noise: far below any running-state voltage (~I*R = 80 uV).
    assert abs(v_dc_uv) < 1e-2  # < 0.01 uV
    # Independent reference agrees it is zero.
    assert abs(ref.rcsj_dc_voltage_volt(_IC_A, _R_OHM, _C_F, 10e-9)) < 1e-4 * _V_SCALE


def test_classical_cli_running_state_matches_reference(examples_dir, tmp_path):
    """Shipped netlist (Ib = 25 nA > Ic): V_dc matches reference and I*R law.

    End-to-end CLI/HDF5 validation, including format and dataset unit tags.
    """
    h5py = pytest.importorskip("h5py")
    out = tmp_path / "run.h5"
    _run_cli(examples_dir / "rcsj_bias.json", out)
    with h5py.File(out, "r") as f:
        assert f.attrs["format"] == "jjqubit-classical-result"
        pd = f["rcsj/phase_dynamics"]
        v_dc_uv = float(pd.attrs["dc_voltage_uV"])
        bias_na = float(pd.attrs["bias_current_nA"])
        assert pd["time_ns"].attrs["unit"] == "ns"
        assert pd["voltage_uV"].attrs["unit"] == "uV"
        q_factor = float(f["rcsj"].attrs["quality_factor"])

    assert np.isclose(bias_na, 25.0, rtol=1e-6)
    assert q_factor > 1.0  # underdamped, as expected

    v_ref_uv = ref.rcsj_dc_voltage_volt(_IC_A, _R_OHM, _C_F, 25e-9) * 1e6
    assert np.isclose(v_dc_uv, v_ref_uv, rtol=1e-3)
    # Independent analytic anchor: underdamped running state V ~= I * R.
    assert np.isclose(v_dc_uv, 25e-9 * _R_OHM * 1e6, rtol=0.01)  # ~200 uV


@pytest.mark.parametrize("frac", [0.0, 0.5, 0.95, 1.25, 2.0, 4.0])
def test_classical_dc_voltage_curve_matches_reference(frac):
    """solver-classical dc_voltage(I) tracks the independent reference everywhere.

    Uses solver-classical's stable public ``dc_voltage`` API for a fine-grained
    V_dc(I) sweep the single-bias CLI cannot provide. Subcritical points must be
    zero; supercritical points must match the independent reference AND the I*R
    running-state law.
    """
    i_bias = frac * _IC_A
    v_solver = classical.dc_voltage(_IC_A, _R_OHM, _C_F, i_bias)
    v_ref = ref.rcsj_dc_voltage_volt(_IC_A, _R_OHM, _C_F, i_bias)
    if frac < 1.0:
        assert abs(v_solver) < 1e-4 * _V_SCALE      # supercurrent branch: V = 0
        assert abs(v_ref) < 1e-4 * _V_SCALE
    else:
        assert np.isclose(v_solver, v_ref, rtol=2e-3)
        assert np.isclose(v_solver, i_bias * _R_OHM, rtol=0.01)  # I*R anchor


def test_classical_iv_curve_shows_hysteresis(examples_dir, tmp_path):
    """The I-V sweep is hysteretic: switches near Ic up, retraps below Ic down.

    An underdamped junction (Q ~= 14) has a switching current ~= Ic on the
    up-sweep and a LOWER retrapping current on the down-sweep, so there is a bias
    window where the descending branch carries voltage while the ascending branch
    is still on the zero-voltage branch. We verify that window exists and that the
    running branch follows V ~= I * R.
    """
    h5py = pytest.importorskip("h5py")
    out = tmp_path / "iv.h5"
    _run_cli(examples_dir / "rcsj_bias.json", out)
    with h5py.File(out, "r") as f:
        iv = f["rcsj/iv_curve"]
        i_up = iv["bias_current_up_nA"][:]
        v_up = iv["voltage_up_uV"][:]
        i_down = iv["bias_current_down_nA"][:]
        v_down = iv["voltage_down_uV"][:]

    ic_na = _IC_A * 1e9
    # Up-sweep: zero-voltage branch below ~Ic, then a finite running voltage.
    assert np.all(np.abs(v_up[i_up < 0.9 * ic_na]) < 1.0)   # < 1 uV below 0.9 Ic
    assert np.any(v_up[i_up > 1.1 * ic_na] > 10.0)          # running above ~Ic

    # Hysteresis: compare up- vs down-sweep at ~0.5 Ic (10 nA).
    def v_at(bias_na, currents, volts):
        return volts[int(np.argmin(np.abs(currents - bias_na)))]

    v_up_10 = v_at(10.0, i_up, v_up)
    v_down_10 = v_at(10.0, i_down, v_down)
    assert abs(v_up_10) < 1.0            # up-sweep: zero-voltage branch
    assert v_down_10 > 10.0             # down-sweep: still running (hysteresis)
    # Running branch obeys V ~= I * R.
    assert np.isclose(v_down_10, 10.0 * _R_OHM * 1e-9 * 1e6, rtol=0.05)


def test_classical_inductor_excluded_from_rcsj_and_disclosed(examples_dir, tmp_path):
    """The shunt inductor L1 is detected but excluded from the RCSJ ODE, and said so.

    Deliberate, physically important scope decision by solver-classical: folding a
    shunt inductor into the phase ODE would add a parabolic confining term that
    makes the "I < Ic => V = 0" limit trivially true for ANY bias (rf-SQUID/
    fluxonium-like, not RCSJ). Validation records that the solver (a) still DETECTS
    the inductor and (b) DISCLOSES the exclusion in /assumptions -- surfaced, not
    silently dropped. If this disclosure ever disappears, the zero-voltage limit
    above could quietly become meaningless.
    """
    h5py = pytest.importorskip("h5py")
    out = tmp_path / "disc.h5"
    _run_cli(examples_dir / "rcsj_bias.json", out)
    with h5py.File(out, "r") as f:
        inductor_ids = f["rcsj"].attrs["inductor_ids"]
        note = f["assumptions"].attrs.get("rcsj_inductor_note", "")
    assert "L1" in inductor_ids                 # inductor detected at bias node
    assert "L1" in note and "not included" in note.lower()  # exclusion disclosed


# ---------------------------------------------------------------------------
# "Dead junction" guards
# ---------------------------------------------------------------------------
# V_dc ~= I*R in the underdamped running state is ALSO what a junction that was
# silently dropped from the ODE would produce (a pure resistor gives V = I*R for
# all I). So I*R agreement alone does NOT prove the Josephson element is in the
# model. The three tests below break that degeneracy: each expected value depends
# on Ic and/or the McCumber damping, so they can only pass if the junction is
# genuinely present and its critical current genuinely enters the physics. All
# expected values are computed here from analytic formulas, never read back from
# the solver.
#
# Grounding:
# * McCumber parameter beta_c = 2*pi*Ic*R^2*C / Phi0, and the damping quality
#   factor Q = sqrt(beta_c) (Stewart 1968; McCumber 1968; Tinkham,
#   *Introduction to Superconductivity* 2nd ed., sec. 6.3). beta_c >> 1 is
#   underdamped/hysteretic, beta_c << 1 is overdamped.
# * Underdamped running state: V ~= I*R (the DC supercurrent averages to zero).
# * Overdamped (RSJ) running state at T=0: V = R*sqrt(I^2 - Ic^2) for I > Ic
#   (Ambegaokar & Halperin 1969; Tinkham eq. 6.29). This value depends on Ic and
#   is the sharpest discriminator against a dead junction.


def _mccumber_beta_c(critical_current_a: float, resistance_ohm: float, capacitance_f: float) -> float:
    """McCumber parameter beta_c = 2*pi*Ic*R^2*C / Phi0 (dimensionless).

    Computed independently of the solver from the netlist's Ic, R, C. Phi0 is the
    superconducting flux quantum (reference.PHI0 = h/2e).
    """
    return 2.0 * np.pi * critical_current_a * resistance_ohm**2 * capacitance_f / ref.PHI0


@pytest.mark.parametrize(
    "capacitance_f, regime",
    [(53e-15, "underdamped"), (0.01e-15, "overdamped")],
)
def test_classical_damping_crossover_proves_junction_alive(capacitance_f, regime):
    """Changing ONLY C flips the running-state law between I*R and R*sqrt(I^2-Ic^2).

    Decisive dead-junction guard. Same Ic=20nA, R=8kohm, Ib=25nA; only C changes:
      * underdamped (C=53 fF, beta_c ~= 206): V_dc ~= I*R = 200 uV.
      * overdamped  (C=0.01 fF, beta_c ~= 0.039): V_dc ~= R*sqrt(I^2-Ic^2)
        = 120 uV, and CLEARLY not I*R (200 uV).
    A junction dropped from the ODE would give I*R in BOTH regimes (no Ic
    dependence, no damping dependence), so the overdamped branch landing near
    120 -- an Ic-dependent value -- can only happen if the junction is alive.

    The R*sqrt(I^2-Ic^2) form is the T=0 overdamped/RSJ (Ambegaokar-Halperin)
    limit; beta_c=0.039 is small but not exactly zero, so a few-percent tolerance
    is used and the key assertion is that the value is near 120 and far from 200.
    """
    beta_c = _mccumber_beta_c(_IC_A, _R_OHM, capacitance_f)
    i_bias = 25e-9
    v = classical.dc_voltage(_IC_A, _R_OHM, capacitance_f, i_bias)
    v_iR = i_bias * _R_OHM                                   # 200 uV
    v_rsj = _R_OHM * np.sqrt(i_bias**2 - _IC_A**2)          # 120 uV

    if regime == "underdamped":
        assert beta_c > 100.0                                # genuinely underdamped
        assert np.isclose(v, v_iR, rtol=0.01)
    else:
        assert beta_c < 0.1                                  # genuinely overdamped
        assert np.isclose(v, v_rsj, rtol=0.05)               # ~R*sqrt(I^2-Ic^2)
        # And unambiguously NOT the dead-junction / I*R value.
        assert abs(v - v_iR) / v_iR > 0.25


@pytest.mark.parametrize(
    "ic_na, expect_zero",
    [(30.0, True), (24.0, False), (20.0, False), (15.0, False)],
)
def test_classical_ic_threshold_proves_junction_alive(ic_na, expect_zero):
    """With Ib=25nA fixed, changing Ic changes the result -> Ic is in the physics.

    Ic > Ib (30 nA): the junction carries the whole bias as supercurrent, V_dc=0.
    Ic <= Ib: the bias exceeds the critical current, the junction switches to the
    running state, V_dc is finite (~I*R for this underdamped junction).
    A dead junction would ignore Ic entirely and give ~I*R for every case, so the
    Ic=30nA -> exactly-zero result is only possible with a live junction.
    """
    i_bias = 25e-9
    v = classical.dc_voltage(ic_na * 1e-9, _R_OHM, _C_F, i_bias)
    if expect_zero:
        assert abs(v) < 1e-4 * _V_SCALE                      # Ic > Ib: blocked, V=0
    else:
        assert np.isclose(v, i_bias * _R_OHM, rtol=0.01)     # Ic < Ib: running, ~I*R


def test_classical_reported_quality_factor_matches_sqrt_beta_c(examples_dir, tmp_path):
    """The solver's reported /rcsj quality_factor equals sqrt(beta_c) from first principles.

    Ties the solver's own reported damping figure to an independent McCumber
    computation from the netlist's Ic, R, C (beta_c ~= 206 -> Q ~= 14.36). If the
    junction (or its Ic/R/C) were not really in the model, this reported number
    could not match the independently computed sqrt(beta_c).
    """
    h5py = pytest.importorskip("h5py")
    out = tmp_path / "q.h5"
    _run_cli(examples_dir / "rcsj_bias.json", out)
    with h5py.File(out, "r") as f:
        q_reported = float(f["rcsj"].attrs["quality_factor"])
    q_expected = np.sqrt(_mccumber_beta_c(_IC_A, _R_OHM, _C_F))
    assert np.isclose(q_reported, q_expected, rtol=1e-3)
    assert q_expected > 1.0  # underdamped, matching the hysteresis seen elsewhere
