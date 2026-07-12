"""RCSJ time-domain phase dynamics: the resistively-and-capacitively-shunted
Josephson junction driven by a DC bias current.

Physics
-------
The gauge-invariant phase ``phi`` across a current-biased RCSJ junction obeys
(Tinkham, *Introduction to Superconductivity*, 2nd ed., eq. 6.28)::

    (hbar C / 2e) phi'' + (hbar / 2e R) phi' + Ic sin(phi) = I_bias

with the Josephson voltage ``V = (hbar / 2e) phi'``. This is the SAME
equation (and the same from-scratch integration strategy) used by the
independent validation reference,
``tests/validation/reference.rcsj_dc_voltage_volt`` -- deliberately: the two
are meant to be cross-checked against each other, not to share code (see
``tests/solvers_classical/test_rcsj.py`` and the note below on the
zero-voltage limit).

``R`` and ``C`` here are the TOTAL shunt resistance/capacitance seen by the
junction at its bias node, as extracted by
:func:`core.solvers.classical.topology.extract_rcsj_topology`:

* ``C_total = Cj + sum(shunt/coupling capacitors on the bias node)``.
* ``R_total`` combines the junction's own ``Rn`` in parallel with any
  *separate* ``resistor`` element(s) also wired to the bias node
  (``1/R_total = 1/Rn + sum(1/R_i)``); for the bundled
  ``examples/rcsj_bias.json`` there are none, so ``R_total = Rn``.

Scope decision -- inductors are NOT part of this v1 model
-----------------------------------------------------------
``examples/rcsj_bias.json`` also wires an ``inductor`` (L1) in parallel
across the same bias node (see ``docs/netlist_schema.md`` section 6: the two
bundled examples *together* exercise all 8 MVP element types, and
``inductor`` only appears in this one). A shunt inductor there is NOT a
minor addition to the RCSJ model -- it changes the qualitative physics: the
node's potential becomes a tilted washboard PLUS a parabolic term
(``propto (phi-phi0)^2``) from the inductor's own flux-phase relation, and
because that parabolic term grows without bound, the combined potential
always has a static equilibrium for ANY bias current. That would make the
"I < Ic => V=0" acceptance limit trivially true for ALL bias values once an
inductor is present -- a fundamentally different circuit (closer to an
rf-SQUID / fluxonium shunt) than the "RCSJ" model docs/task.md names for
Gorev 2 ("RCSJ (resistively and capacitively shunted junction) modeli").
Given CLAUDE.md's explicit rule to not guess on circuit physics, this solver
implements the literal RCSJ model (R, C, junction only) and does NOT fold any
inductor into the phase ODE. :func:`core.solvers.classical.topology.extract_rcsj_topology`
still DETECTS inductors at the bias node (``RCSJTopology.inductor_ids``) so
their presence is surfaced rather than silently ignored: the HDF5
``/assumptions`` group records a note whenever this occurs. This was flagged
to `main` for awareness; see the CLI/HDF5 output for the live disclosure.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.constants import e as _ELEMENTARY_CHARGE
from scipy.constants import hbar as _HBAR
from scipy.integrate import solve_ivp

# Phase-to-voltage factor: V = PHI0_OVER_2PI * dphi/dt (Josephson voltage-phase relation).
PHI0_OVER_2PI: float = _HBAR / (2.0 * _ELEMENTARY_CHARGE)


def plasma_frequency_rad_s(critical_current_a: float, capacitance_f: float) -> float:
    """Junction plasma frequency ``omega_p = sqrt(2e*Ic / (hbar*C))``, in rad/s.

    Sets the natural oscillation timescale of the RCSJ phase particle in the
    washboard potential; used to size the integration step/span.

    Args:
        critical_current_a: Junction critical current ``Ic``, in amperes.
        capacitance_f: Total shunt capacitance ``C``, in farads.

    Returns:
        ``omega_p`` in rad/s.
    """
    return float(np.sqrt(critical_current_a / (PHI0_OVER_2PI * capacitance_f)))


@dataclass(frozen=True)
class PhaseDynamicsResult:
    """A time-domain RCSJ phase-dynamics trace.

    Args:
        time_s: Time samples, in seconds (ascending, starting at 0).
        phase_rad: Gauge-invariant junction phase ``phi(t)``, in radians.
        voltage_v: Josephson voltage ``V(t) = PHI0_OVER_2PI * dphi/dt``, in volts.
        dc_voltage_v: Time-averaged voltage over the last ``settle_fraction``
            of the trace (the "settled" DC value reported for I-V curves).
        critical_current_a, resistance_ohm, capacitance_f, bias_current_a: The
            physical parameters this trace was integrated with (SI units),
            kept for HDF5 provenance.
    """

    time_s: np.ndarray
    phase_rad: np.ndarray
    voltage_v: np.ndarray
    dc_voltage_v: float
    critical_current_a: float
    resistance_ohm: float
    capacitance_f: float
    bias_current_a: float


def _rcsj_rhs(
    _t: float,
    y: np.ndarray,
    critical_current_a: float,
    resistance_ohm: float,
    capacitance_f: float,
    bias_current_a: float,
) -> list[float]:
    """Right-hand side of the RCSJ ODE, state ``y = [phi, dphi/dt]``."""
    phi, phidot = y
    phiddot = (
        bias_current_a
        - critical_current_a * np.sin(phi)
        - (PHI0_OVER_2PI / resistance_ohm) * phidot
    ) / (capacitance_f * PHI0_OVER_2PI)
    return [phidot, phiddot]


def integrate_phase_dynamics(
    critical_current_a: float,
    resistance_ohm: float,
    capacitance_f: float,
    bias_current_a: float,
    *,
    phi0_rad: float | None = None,
    phidot0_rad_s: float = 0.0,
    n_plasma_periods: float = 400.0,
    n_points: int = 20000,
    settle_fraction: float = 0.5,
    rtol: float = 1e-8,
    atol: float = 1e-10,
) -> PhaseDynamicsResult:
    """Integrate the RCSJ phase equation for a fixed DC bias current.

    ``(hbar C / 2e) phi'' + (hbar / 2e R) phi' + Ic sin(phi) = I_bias``,
    Josephson voltage ``V = (hbar / 2e) phi'``.

    By default the integration starts ON the zero-voltage supercurrent
    branch, at the static fixed point ``phi0 = arcsin(clip(I/Ic, -1, 1))``
    with ``phi' = 0``. This isolates the branch property the CLAUDE.md limit
    ("I < Ic => V=0") is about, rather than the separate (and, for an
    underdamped junction, legitimately hysteretic) question of what happens
    if the bias is stepped suddenly from rest. Callers doing a continuation
    sweep (see :func:`sweep_iv_curve`) override ``phi0_rad``/``phidot0_rad_s``
    with the previous operating point to capture that hysteresis instead.

    Args:
        critical_current_a: Junction critical current ``Ic``, in amperes.
        resistance_ohm: Total shunt resistance ``R``, in ohms.
        capacitance_f: Total shunt capacitance ``C``, in farads.
        bias_current_a: Applied DC bias current, in amperes.
        phi0_rad: Initial phase, in radians. Defaults to the supercurrent-branch
            fixed point ``arcsin(clip(I/Ic, -1, 1))``.
        phidot0_rad_s: Initial ``dphi/dt``, in rad/s (default 0).
        n_plasma_periods: Integration span, in units of the plasma period
            ``2*pi/omega_p``.
        n_points: Number of output time samples.
        settle_fraction: Fraction of the trace (from the start) discarded as
            transient before averaging ``dphi/dt`` into ``dc_voltage_v``.
        rtol, atol: Relative/absolute tolerances passed to
            :func:`scipy.integrate.solve_ivp`. The defaults match the
            independent validation reference
            (``tests/validation/reference.rcsj_dc_voltage_volt``) for the
            closest possible cross-check; callers doing many integrations
            (e.g. :func:`sweep_iv_curve`) may loosen these for speed.

    Returns:
        The :class:`PhaseDynamicsResult`.
    """
    if phi0_rad is None:
        phi0_rad = float(np.arcsin(np.clip(bias_current_a / critical_current_a, -1.0, 1.0)))

    omega_p = plasma_frequency_rad_s(critical_current_a, capacitance_f)
    t_end = n_plasma_periods * (2.0 * np.pi / omega_p)
    t_eval = np.linspace(0.0, t_end, n_points)

    sol = solve_ivp(
        _rcsj_rhs,
        (0.0, t_end),
        y0=[phi0_rad, phidot0_rad_s],
        args=(critical_current_a, resistance_ohm, capacitance_f, bias_current_a),
        t_eval=t_eval,
        method="RK45",
        rtol=rtol,
        atol=atol,
        max_step=(2.0 * np.pi / omega_p) / 40.0,
    )

    phase_rad = sol.y[0]
    phidot = sol.y[1]
    voltage_v = PHI0_OVER_2PI * phidot

    start = int(settle_fraction * len(phidot))
    dc_voltage_v = float(np.mean(voltage_v[start:]))

    return PhaseDynamicsResult(
        time_s=sol.t,
        phase_rad=phase_rad,
        voltage_v=voltage_v,
        dc_voltage_v=dc_voltage_v,
        critical_current_a=critical_current_a,
        resistance_ohm=resistance_ohm,
        capacitance_f=capacitance_f,
        bias_current_a=bias_current_a,
    )


def dc_voltage(
    critical_current_a: float,
    resistance_ohm: float,
    capacitance_f: float,
    bias_current_a: float,
    **kwargs: float,
) -> float:
    """Time-averaged DC voltage across an RCSJ junction, in volts.

    Thin wrapper around :func:`integrate_phase_dynamics` that starts on the
    supercurrent branch (the default ``phi0_rad``) and returns just the
    settled DC voltage -- this is the function the "I < Ic => V=0" analytic
    limit is checked against (see ``tests/solvers_classical/test_rcsj.py``)
    and the one to cross-check against
    ``tests/validation/reference.rcsj_dc_voltage_volt``.

    Args:
        critical_current_a: Junction critical current ``Ic``, in amperes.
        resistance_ohm: Total shunt resistance ``R``, in ohms.
        capacitance_f: Total shunt capacitance ``C``, in farads.
        bias_current_a: Applied DC bias current, in amperes.
        **kwargs: Forwarded to :func:`integrate_phase_dynamics` (e.g.
            ``n_plasma_periods``, ``settle_fraction``).

    Returns:
        The settled DC (time-averaged) voltage, in volts.
    """
    return integrate_phase_dynamics(
        critical_current_a, resistance_ohm, capacitance_f, bias_current_a, **kwargs
    ).dc_voltage_v


@dataclass(frozen=True)
class IVCurveResult:
    """A hysteretic I-V sweep of an RCSJ junction.

    Args:
        bias_current_up_a, voltage_up_v: Ascending sweep (0 -> I_max), in
            amperes/volts. Each point continues from the previous point's
            final phase state, so the sweep captures the switching current
            (the point where the phase leaves the zero-voltage branch).
        bias_current_down_a, voltage_down_v: Descending sweep (I_max -> 0),
            continuation likewise, capturing the (lower) retrapping current
            of an underdamped junction.
        critical_current_a, resistance_ohm, capacitance_f: The physical
            parameters this sweep was computed with (SI units).
    """

    bias_current_up_a: np.ndarray
    voltage_up_v: np.ndarray
    bias_current_down_a: np.ndarray
    voltage_down_v: np.ndarray
    critical_current_a: float
    resistance_ohm: float
    capacitance_f: float


def sweep_iv_curve(
    critical_current_a: float,
    resistance_ohm: float,
    capacitance_f: float,
    bias_currents_a: np.ndarray,
    *,
    n_plasma_periods: float = 200.0,
    n_points: int = 4000,
    settle_fraction: float = 0.5,
) -> IVCurveResult:
    """Sweep the DC bias current up then down, tracking hysteresis.

    Each successive bias point is integrated starting from the PREVIOUS
    point's final ``(phi, dphi/dt)`` (a continuation/quasi-static sweep, the
    standard way to reproduce an experimental I-V trace), rather than always
    restarting on the supercurrent branch. This is what lets an underdamped
    junction (``examples/rcsj_bias.json`` has quality factor
    ``Q = Rn*sqrt(2e*Ic/(hbar*C)) ~ 14`` -- underdamped) show its
    characteristic hysteresis loop: switching to the running state above
    ``Ic`` on the way up, and only retrapping onto the zero-voltage branch
    at a LOWER current on the way down.

    Args:
        critical_current_a: Junction critical current ``Ic``, in amperes.
        resistance_ohm: Total shunt resistance ``R``, in ohms.
        capacitance_f: Total shunt capacitance ``C``, in farads.
        bias_currents_a: Ascending, non-negative bias-current samples (A) to
            sweep up through and then back down through (in reverse order).
        n_plasma_periods: Integration span per point, in plasma periods. Kept
            shorter than :func:`integrate_phase_dynamics`'s default since a
            sweep integrates many points.
        n_points: Output time samples per point (only the settled average is
            kept, so this need not be large).
        settle_fraction: Fraction of each point's trace discarded as
            transient before averaging.

    Returns:
        The :class:`IVCurveResult`.
    """
    bias_currents_a = np.asarray(bias_currents_a, dtype=float)

    def _run(currents: np.ndarray) -> np.ndarray:
        voltages = np.empty(len(currents))
        phi, phidot = 0.0, 0.0
        for i, i_bias in enumerate(currents):
            result = integrate_phase_dynamics(
                critical_current_a,
                resistance_ohm,
                capacitance_f,
                float(i_bias),
                phi0_rad=phi,
                phidot0_rad_s=phidot,
                n_plasma_periods=n_plasma_periods,
                n_points=n_points,
                settle_fraction=settle_fraction,
            )
            voltages[i] = result.dc_voltage_v
            phi = float(result.phase_rad[-1])
            phidot = float((result.voltage_v[-1]) / PHI0_OVER_2PI)
        return voltages

    voltage_up_v = _run(bias_currents_a)
    voltage_down_v = _run(bias_currents_a[::-1])

    return IVCurveResult(
        bias_current_up_a=bias_currents_a,
        voltage_up_v=voltage_up_v,
        bias_current_down_a=bias_currents_a[::-1],
        voltage_down_v=voltage_down_v,
        critical_current_a=critical_current_a,
        resistance_ohm=resistance_ohm,
        capacitance_f=capacitance_f,
    )
