"""Readout S21: resonator, capacitively coupled to a feedline, terminated by
a real load resistance.

Circuit modeled (see :func:`core.solvers.classical.topology.extract_readout_topology`)::

    resonator (f0, Q) --Ck--> feedline "in" ==TL(Z0, length, eps_eff)== "out" --Rload--> gnd

This is the standard "hanger"/notch-type circuit-QED readout: a lumped LC
resonator side-coupled through a small capacitor to a transmission-line
feedline. S21 is modeled as the product of (1) the notch resonance the
coupled resonator carves into the line's transmission, and (2) the bare
transmission-line propagation/mismatch factor set by the real termination
resistor.

Assumption -- resonator impedance (reused from solver-quantum, same value)
----------------------------------------------------------------------------
The netlist's ``resonator`` element only specifies ``f0`` and ``Q``
(docs/netlist_schema.md section 3) -- no capacitance or characteristic
impedance, so its own lumped ``L``/``C`` are not directly available. Sizing
the coupling to the feedline (the external decay rate ``kappa_ext``, from
the coupling capacitor ``Ck``) needs the resonator's own capacitance. Exactly
as ``core/solvers/quantum/dispersive.py`` already does for delta_V0, we
assume the resonator behaves as if realized with characteristic impedance
``Z_r = 50 ohm`` (the standard on-chip CPW design impedance, and the SAME
value used for ``transmission_line.Z0`` in both bundled examples), giving::

    C_r = 1 / (Z_r * omega_0),   L_r = Z_r / omega_0

This is a solver-side physical assumption (not a netlist schema change); it
is recorded in the HDF5 ``/assumptions`` group for audit, per CLAUDE.md's
physics-validation rule. ``Q`` (the netlist parameter) is interpreted as the
resonator's INTRINSIC/internal quality factor (material and radiative
losses other than the deliberate feedline coupling); the coupling to the
feedline contributes its own external decay rate on top of that, and the
loaded response combines both -- the standard circuit-QED convention
(Goeppl et al., J. Appl. Phys. 104, 113904 (2008); Pozar, *Microwave
Engineering*).

Formulas
--------
External coupling rate from a small series coupling capacitor ``Ck`` feeding
a matched ``Z0`` environment (weak-coupling / RWA limit,
``omega_0 * Ck * Z0 << 1``; Goeppl et al. 2008, eq. 26)::

    kappa_ext = omega_0^2 * Ck^2 * Z0 / C_r      [rad/s]

Internal rate from the netlist's ``Q``: ``kappa_int = omega_0 / Q``.

Notch-resonance transmission (standard input-output theory; e.g. Probst et
al., Rev. Sci. Instrum. 86, 024706 (2015), simplified to the ideal
(symmetric, lossless-line) case appropriate for this MVP)::

    S21_resonator(f) = 1 - (kappa_ext/2) / (i*2*pi*(f-f0) + (kappa_int+kappa_ext)/2)

(all rates expressed consistently as linear-frequency linewidths, i.e.
``kappa_hz = kappa_rad_s / (2*pi)``, matching ``f0`` in Hz.)

Transmission-line propagation/mismatch factor for a lossless line of
characteristic impedance ``Z0``, physical length ``length`` and effective
permittivity ``eps_eff``, terminated by the real resistor ``Rload``
(standard bounce-diagram result for a matched-source-driven line; reduces to
a pure propagation delay ``exp(-i*beta*length)`` when ``Rload == Z0``, the
case in the bundled ``examples/transmon_readout.json``)::

    beta        = 2*pi*f*sqrt(eps_eff) / c
    Gamma_L     = (Rload - Z0) / (Rload + Z0)
    S21_line(f) = (1 + Gamma_L) * exp(-i*beta*length) / (1 - Gamma_L*exp(-2i*beta*length))

Total: ``S21(f) = S21_line(f) * S21_resonator(f)``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.constants import c as _C_LIGHT

# See module docstring: the netlist's `resonator` element has no impedance
# parameter, so we assume the standard on-chip CPW design value -- the same
# assumption (and the same numeric value) already used and approved for
# core/solvers/quantum/dispersive.py's DEFAULT_RESONATOR_IMPEDANCE_OHM.
DEFAULT_RESONATOR_IMPEDANCE_OHM = 50.0


@dataclass(frozen=True)
class S21Curve:
    """A computed S21 transmission curve for the readout circuit.

    Args:
        frequency_hz: Swept probe frequency, in Hz.
        s21: Complex S21 at each frequency (dimensionless).
        f0_hz: Bare resonator resonance frequency, in Hz.
        q_internal: The netlist's ``Q`` (interpreted as intrinsic Q).
        kappa_int_hz, kappa_ext_hz, kappa_total_hz: Internal, external and
            total resonator linewidths, in Hz (linear-frequency convention,
            i.e. already divided by 2*pi).
        resonator_c_f, resonator_l_f: Assumed resonator lumped element
            values (see module docstring), in farads/henries.
        resonator_impedance_ohm: The assumed resonator impedance used to
            derive ``resonator_c_f``/``resonator_l_f``.
        z0_ohm: Feedline characteristic impedance, in ohms.
        termination_ohm: The real termination resistance, in ohms.
        line_length_m: Feedline physical length, in meters.
        eps_eff: Feedline effective relative permittivity (dimensionless).
        coupling_capacitance_f: Total resonator<->feedline coupling
            capacitance, in farads.
    """

    frequency_hz: np.ndarray
    s21: np.ndarray
    f0_hz: float
    q_internal: float
    kappa_int_hz: float
    kappa_ext_hz: float
    kappa_total_hz: float
    resonator_c_f: float
    resonator_l_f: float
    resonator_impedance_ohm: float
    z0_ohm: float
    termination_ohm: float
    line_length_m: float
    eps_eff: float
    coupling_capacitance_f: float


def resonator_lc_from_f0(f0_hz: float, impedance_ohm: float) -> tuple[float, float]:
    """Assumed lumped ``(L, C)`` for a resonator given only its ``f0``.

    See module docstring for the ``Z_r`` assumption. ``omega_0 = 1/sqrt(LC)``
    and ``Z_r = sqrt(L/C)`` together give ``C = 1/(Z_r*omega_0)``,
    ``L = Z_r/omega_0``.

    Args:
        f0_hz: Resonance frequency, in Hz.
        impedance_ohm: Assumed characteristic impedance, in ohms.

    Returns:
        ``(inductance_h, capacitance_f)``.
    """
    omega_0 = 2.0 * math.pi * f0_hz
    capacitance_f = 1.0 / (impedance_ohm * omega_0)
    inductance_h = impedance_ohm / omega_0
    return inductance_h, capacitance_f


def external_kappa_hz(
    f0_hz: float, coupling_capacitance_f: float, resonator_c_f: float, z0_ohm: float
) -> float:
    """External decay rate from a weak series coupling capacitor, in Hz.

    ``kappa_ext = omega_0^2 * Ck^2 * Z0 / C_r`` (rad/s), converted to Hz. See
    module docstring for the derivation and validity regime (weak coupling).

    Args:
        f0_hz: Resonator resonance frequency, in Hz.
        coupling_capacitance_f: Coupling capacitance ``Ck``, in farads.
        resonator_c_f: Assumed resonator capacitance ``C_r`` (see
            :func:`resonator_lc_from_f0`), in farads.
        z0_ohm: Feedline characteristic impedance, in ohms.

    Returns:
        ``kappa_ext`` in Hz (i.e. ``kappa_ext_rad_s / (2*pi)``).
    """
    omega_0 = 2.0 * math.pi * f0_hz
    kappa_ext_rad_s = omega_0**2 * coupling_capacitance_f**2 * z0_ohm / resonator_c_f
    return kappa_ext_rad_s / (2.0 * math.pi)


def line_transmission_factor(
    frequency_hz: np.ndarray,
    z0_ohm: float,
    length_m: float,
    eps_eff: float,
    termination_ohm: float,
) -> np.ndarray:
    """Bare transmission-line propagation/mismatch factor (dimensionless, complex).

    Standard lossless-line bounce-diagram result for a line driven from a
    matched (``Z0``) source and terminated by an arbitrary real resistor
    ``termination_ohm``; see module docstring. Reduces to a pure delay
    ``exp(-i*beta*length)`` when ``termination_ohm == z0_ohm``.

    Args:
        frequency_hz: Probe frequency array, in Hz.
        z0_ohm: Line characteristic impedance, in ohms.
        length_m: Physical line length, in meters.
        eps_eff: Effective relative permittivity (dimensionless).
        termination_ohm: Real termination resistance, in ohms.

    Returns:
        Complex array, same shape as ``frequency_hz``.
    """
    beta = 2.0 * math.pi * frequency_hz * math.sqrt(eps_eff) / _C_LIGHT
    gamma_l = (termination_ohm - z0_ohm) / (termination_ohm + z0_ohm)
    phase = np.exp(-1j * beta * length_m)
    return (1.0 + gamma_l) * phase / (1.0 - gamma_l * phase**2)


def notch_response(
    frequency_hz: np.ndarray, f0_hz: float, kappa_int_hz: float, kappa_ext_hz: float
) -> np.ndarray:
    """Ideal notch-resonator S21 (dimensionless, complex).

    ``S21(f) = 1 - (kappa_ext/2) / (i*2*pi*(f-f0) + (kappa_int+kappa_ext)/2)``.
    See module docstring for grounding.

    Args:
        frequency_hz: Probe frequency array, in Hz.
        f0_hz: Bare resonance frequency, in Hz.
        kappa_int_hz: Internal linewidth, in Hz.
        kappa_ext_hz: External linewidth, in Hz.

    Returns:
        Complex array, same shape as ``frequency_hz``.
    """
    kappa_total_hz = kappa_int_hz + kappa_ext_hz
    detuning_hz = frequency_hz - f0_hz
    return 1.0 - (kappa_ext_hz / 2.0) / (1j * detuning_hz + kappa_total_hz / 2.0)


def compute_s21_curve(
    *,
    f0_hz: float,
    q_internal: float,
    coupling_capacitance_f: float,
    z0_ohm: float,
    line_length_m: float,
    eps_eff: float,
    termination_ohm: float,
    resonator_impedance_ohm: float = DEFAULT_RESONATOR_IMPEDANCE_OHM,
    span_linewidths: float = 20.0,
    n_points: int = 801,
) -> S21Curve:
    """Compute the full S21(f) curve for a resonator-fed, terminated feedline.

    Args:
        f0_hz: Bare resonator resonance frequency, in Hz.
        q_internal: The resonator's netlist ``Q``, interpreted as intrinsic Q.
        coupling_capacitance_f: Total resonator<->feedline coupling
            capacitance, in farads.
        z0_ohm: Feedline characteristic impedance, in ohms.
        line_length_m: Feedline physical length, in meters.
        eps_eff: Feedline effective relative permittivity (dimensionless).
        termination_ohm: Real termination resistance, in ohms.
        resonator_impedance_ohm: Assumed resonator impedance (see module
            docstring); override only for sensitivity testing.
        span_linewidths: Frequency span, in units of the total (loaded)
            linewidth, centered on ``f0_hz``.
        n_points: Number of frequency samples.

    Returns:
        The :class:`S21Curve`.
    """
    inductance_h, capacitance_f = resonator_lc_from_f0(f0_hz, resonator_impedance_ohm)
    kappa_ext_hz = external_kappa_hz(f0_hz, coupling_capacitance_f, capacitance_f, z0_ohm)
    kappa_int_hz = f0_hz / q_internal
    kappa_total_hz = kappa_int_hz + kappa_ext_hz

    half_span = span_linewidths * kappa_total_hz / 2.0
    frequency_hz = np.linspace(f0_hz - half_span, f0_hz + half_span, n_points)

    s21_resonator = notch_response(frequency_hz, f0_hz, kappa_int_hz, kappa_ext_hz)
    s21_line = line_transmission_factor(frequency_hz, z0_ohm, line_length_m, eps_eff, termination_ohm)
    s21 = s21_line * s21_resonator

    return S21Curve(
        frequency_hz=frequency_hz,
        s21=s21,
        f0_hz=f0_hz,
        q_internal=q_internal,
        kappa_int_hz=kappa_int_hz,
        kappa_ext_hz=kappa_ext_hz,
        kappa_total_hz=kappa_total_hz,
        resonator_c_f=capacitance_f,
        resonator_l_f=inductance_h,
        resonator_impedance_ohm=resonator_impedance_ohm,
        z0_ohm=z0_ohm,
        termination_ohm=termination_ohm,
        line_length_m=line_length_m,
        eps_eff=eps_eff,
        coupling_capacitance_f=coupling_capacitance_f,
    )
