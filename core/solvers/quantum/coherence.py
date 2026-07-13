"""Qubit coherence times T1, T2 and pure dephasing Tphi.

Thin layer over scqubits' noise/coherence API (CLAUDE.md "Yapmayacaklarimiz"
#2 -- we do not reimplement the noise physics). scqubits already implements the
standard superconducting-qubit noise channels (1/f flux/charge/critical-current
dephasing, dielectric-loss and charge-impedance T1, quasiparticle tunneling,
flux-bias-line T1) with literature-standard default amplitudes; we call its
``t1_effective`` / ``t2_effective`` and report the result in microseconds, plus
a per-channel breakdown.

Why the qubit object is rebuilt here (not reused from the spectrum): the squid
path collapses flux tuning into an effective Ej and diagonalizes a plain
``Transmon``, which has NO flux-noise channels. But flux noise is the dominant
dephasing source for a tunable qubit AWAY from its flux sweet spot -- ignoring
it would badly overestimate T2. So for a squid we build a real
``scqubits.TunableTransmon`` at the applied flux, which carries
``tphi_1_over_f_flux`` and ``t1_flux_bias_line``; for a fixed junction we build
a ``Transmon``. This reproduces the textbook behavior that T2 is protected at
the sweet spot (flux = 0) and degrades sharply away from it.

Units: with EJ/EC in GHz, scqubits returns coherence times in nanoseconds; we
convert to microseconds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import scqubits as scq

from .quantization import QubitQuantization

# Dilution-refrigerator base temperature (scqubits' own default), in kelvin.
STANDARD_TEMPERATURE_K = 0.015

# Charge basis truncation for the coherence qubit object; 40 is well converged
# in the transmon regime this solver targets (matches the spectrum module).
_NCUT = 40


@dataclass(frozen=True)
class CoherenceResult:
    """Estimated coherence times, in microseconds.

    Args:
        T1_us: Effective relaxation time T1 (all supported T1 channels), in us.
        T2_us: Effective Ramsey coherence time T2 (T1 + pure dephasing), in us.
        Tphi_us: Pure dephasing time from 1/T2 = 1/(2 T1) + 1/Tphi, in us;
            ``inf`` when dephasing is negligible.
        temperature_K: Bath temperature the estimate assumed, in kelvin.
        t1_channels_us: Per-channel T1 contribution (each in us); larger = the
            channel matters less.
        tphi_channels_us: Per-channel pure-dephasing contribution, in us.
    """

    T1_us: float
    T2_us: float
    Tphi_us: float
    temperature_K: float
    t1_channels_us: dict[str, float]
    tphi_channels_us: dict[str, float]


def _build_qubit(quantization: QubitQuantization):
    """Build the scqubits qubit matching the element type (see module docstring)."""
    if quantization.element_type == "squid":
        return scq.TunableTransmon(
            EJmax=quantization.EjMax_GHz,
            EC=quantization.Ec_GHz,
            d=quantization.asymmetry_d,
            flux=quantization.flux,
            ng=0.0,
            ncut=_NCUT,
        )
    return scq.Transmon(
        EJ=quantization.Ej_GHz,
        EC=quantization.Ec_GHz,
        ng=0.0,
        ncut=_NCUT,
    )


def compute_coherence(
    quantization: QubitQuantization,
    *,
    temperature_K: float = STANDARD_TEMPERATURE_K,
) -> CoherenceResult:
    """Estimate T1, T2 and Tphi for the quantized qubit using scqubits defaults.

    Args:
        quantization: Result of
            :func:`core.solvers.quantum.quantization.quantize_circuit`.
        temperature_K: Bath temperature, in kelvin (default 15 mK).

    Returns:
        The :class:`CoherenceResult`, all times in microseconds.
    """
    qubit = _build_qubit(quantization)
    opts = {"T": temperature_K}

    t1_ns = qubit.t1_effective(common_noise_options=opts)
    t2_ns = qubit.t2_effective(common_noise_options=opts)

    # Per-channel breakdown over scqubits' EFFECTIVE channel set -- i.e. the
    # channels that actually feed t1_effective/t2_effective, NOT every supported
    # one. scqubits deliberately omits some supported channels (e.g.
    # t1_charge_impedance, whose default parameters give an unphysically short
    # ~0.2 ns time) from the effective estimate; iterating the effective set
    # keeps this breakdown consistent with the headline T1/T2 and avoids
    # reporting a misleading number.
    #
    # scqubits' t1_* methods take T as a direct kwarg, while tphi_* methods take
    # common_noise_options -- dispatch by prefix.
    t1_channels: dict[str, float] = {}
    tphi_channels: dict[str, float] = {}
    for channel in qubit.effective_noise_channels():
        method = getattr(qubit, channel)
        if channel.startswith("t1"):
            t1_channels[channel] = method(T=temperature_K) / 1e3
        elif channel.startswith("tphi"):
            tphi_channels[channel] = method(common_noise_options=opts) / 1e3

    # Pure dephasing from the standard relation 1/T2 = 1/(2 T1) + 1/Tphi.
    inv_tphi_ns = 1.0 / t2_ns - 1.0 / (2.0 * t1_ns)
    tphi_us = (1.0 / inv_tphi_ns) / 1e3 if inv_tphi_ns > 0 else math.inf

    return CoherenceResult(
        T1_us=t1_ns / 1e3,
        T2_us=t2_ns / 1e3,
        Tphi_us=tphi_us,
        temperature_K=temperature_K,
        t1_channels_us=t1_channels,
        tphi_channels_us=tphi_channels,
    )
